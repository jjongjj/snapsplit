# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# connectors/custom_socket.py
"""Socket of a custom connector mesh: the pin grown by the clearance in every direction.

The socket is the Minkowski sum of the pin and a ball of radius ``c`` (the
clearance), approximated by a polytope ball whose faces are all at least ``c``
from its center (so the clearance is never less than ``c``, at most ~3 % more):

1. Convex pin: the convex hull of every pin vertex plus the ball points. This is
   the exact Minkowski sum, needs no boolean and takes milliseconds.
2. Otherwise the vertex-normal offset (every vertex moved outward along its
   normal times the shell factor, like Solidify's even thickness): exact for
   smooth shapes, but it folds where a slot or notch is narrower than twice the
   clearance and loses clearance at concave or sharp corners (defect D17). It is
   checked: it must unite into a clean solid and keep at least
   ``MIN_CLEARANCE_SHARE`` x clearance from every sample of the pin surface
   (vertices, edge points, face centers).
3. If the offset fails: the pin united with one convex hull per face (the face's
   vertices plus the ball points = the face grown by the clearance, with its edges
   and corners rounded). Correct for any shape (slots narrower than 2 x clearance
   simply fill), one union of F + 1 convex pieces, used for meshes of at most
   MINKOWSKI_MAX_TRIS triangles. (Defect D19: this replaced a sum of face prisms,
   edge cylinders and vertex balls that took 20-45 s for a 17-face cone.)

If no candidate reaches the required clearance, the best one is used and a note
(Build warning) says how much clearance it has.

Results are cached per shape, size, clearance and sample step (plain
vertex/face lists, in a canonical connector frame: the pin side, gap and insert
depth only move the result rigidly, see shapes.connector_solids), so Distribute's
fit checks, both pin sides and repeated builds compute a socket once per session.
The slow path (3) shows a wait cursor and a status bar text in the UI
(core/progress.busy). Uses temporary objects through core/boolean.py (Build /
operator context only).
"""

import math

import bmesh
from mathutils import Matrix
from mathutils.bvhtree import BVHTree

from ..core import boolean, progress
from . import fit

MIN_CLEARANCE_SHARE = 0.9
MINKOWSKI_MAX_TRIS = 4000
# Ball polytope: icosphere subdivisions (2: 42 points, its corners 2.6 % beyond the inner radius;
# 3: 162 points, 0.7 %); a convex pin's hull uses 3 while vertices x points stays below the limit
BALL_SUBDIVISIONS = 2
CONVEX_BALL_SUBDIVISIONS = 3
CONVEX_MAX_POINTS = 400000
CACHE_SIZE = 64

_CACHE = {}
_BALLS = {}


def _bm(verts, faces):
    bm = bmesh.new()
    bv = [bm.verts.new(v) for v in verts]
    for f in faces:
        bm.faces.new([bv[i] for i in f])
    bm.normal_update()
    return bm


def _to_lists(bm):
    bm.verts.index_update()
    return [v.co.copy() for v in bm.verts], [tuple(v.index for v in f.verts) for f in bm.faces]


def pin_samples(bm, step):
    """Points on the pin surface: vertices, points along edges (at most ``step`` apart), face centers."""
    pts = [v.co.copy() for v in bm.verts]
    for e in bm.edges:
        a, b = e.verts[0].co, e.verts[1].co
        n = max(1, math.ceil((b - a).length / step))
        pts += [a + (b - a) * (k / n) for k in range(1, n)]
    pts += [f.calc_center_median() for f in bm.faces]
    return pts


def clearance(socket_bm, samples):
    """Smallest distance of the samples inside the socket surface (negative: a sample sticks out)."""
    bvh = BVHTree.FromBMesh(socket_bm)
    return min(fit.depth_inside(bvh, p) for p in samples)


def _offset(bm, distance):
    return [v.co + v.normal * distance * min(v.calc_shell_factor(), 3.0) for v in bm.verts]


def ball_points(c, subdivisions=BALL_SUBDIVISIONS):
    """Vertices of an icosphere whose faces are all at least ``c`` from its center (inner radius c)."""
    key = (subdivisions,)
    unit = _BALLS.get(key)
    if unit is None:
        bm = bmesh.new()
        try:
            bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=1.0)
            bm.normal_update()
            inner = min(f.normal.dot(f.verts[0].co) for f in bm.faces)
            unit = _BALLS[key] = [v.co / inner for v in bm.verts]
        finally:
            bm.free()
    return [p * c for p in unit]


def is_convex(bm, tol):
    """True if no vertex lies more than ``tol`` outside the plane of any face (normals current)."""
    verts = [v.co for v in bm.verts]
    for f in bm.faces:
        p, n = f.verts[0].co, f.normal
        if n.length < 0.5:
            continue
        if any((q - p).dot(n) > tol for q in verts):
            return False
    return True


def hull(points):
    """Closed convex hull bmesh (outward normals) of ``points``; caller frees it."""
    bm = bmesh.new()
    verts = [bm.verts.new(p) for p in points]
    bmesh.ops.convex_hull(bm, input=verts)
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.normal_update()
    return bm


def _convex_face(f, tol):
    """True for a planar convex polygon (a triangle always)."""
    if len(f.verts) == 3:
        return True
    n = f.normal
    co = [v.co for v in f.verts]
    if any(abs((q - co[0]).dot(n)) > tol for q in co):
        return False
    k = len(co)
    return all((co[(i + 1) % k] - co[i]).cross(co[(i + 2) % k] - co[(i + 1) % k]).dot(n) >= -tol * tol
               for i in range(k))


def minkowski_pieces(pin, c):
    """Pin + one convex hull per (convex) face of the pin grown by the ball, as one bmesh of
    overlapping closed pieces (to be united). Non-planar or concave faces are triangulated."""
    tri = pin.copy()
    tri.normal_update()
    size = max(bm_size(tri), 1e-9)
    tol = 1e-6 * size
    bad = [f for f in tri.faces if not _convex_face(f, tol)]
    if bad:
        bmesh.ops.triangulate(tri, faces=bad)
        tri.normal_update()
    ball = ball_points(c)
    out = pin.copy()
    for f in tri.faces:
        piece = hull([v.co + b for v in f.verts for b in ball])
        try:
            _append_bm(out, piece)
        finally:
            piece.free()
    tri.free()
    return out


def bm_size(bm):
    first = next(iter(bm.verts)).co
    return max((v.co - first).length for v in bm.verts)


def _append_bm(dst, src):
    """Copy the faces of ``src`` into ``dst`` (plain bmesh copy, no data-blocks)."""
    vmap = {v: dst.verts.new(v.co) for v in src.verts}
    for f in src.faces:
        dst.faces.new([vmap[v] for v in f.verts])


def _share(got, c):
    return f"{100.0 * max(got, 0.0) / c:.0f} %" if c > 0.0 else "0 %"


def socket(verts, faces, c, step, name="custom"):
    """(socket verts, socket faces, achieved clearance, note) for a custom pin given in its connector frame.

    ``step``: sample spacing of the clearance check. ``note`` is "" when the
    clearance is at least MIN_CLEARANCE_SHARE x ``c``. ``name``: the mesh, for the
    status text of the slow path.
    """
    key = (tuple(tuple(round(x, 9) for x in v) for v in verts), tuple(faces), round(c, 9), round(step, 9))
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    pin = _bm(verts, faces)
    candidates = []
    try:
        samples = pin_samples(pin, step)
        need = MIN_CLEARANCE_SHARE * c
        # 1. convex pin: the hull of the vertices grown by the ball is the exact Minkowski sum
        n_verts = len(pin.verts)
        if c > 0.0 and is_convex(pin, 1e-6 * max(bm_size(pin), 1e-9)):
            subdiv = next((k for k in (CONVEX_BALL_SUBDIVISIONS, BALL_SUBDIVISIONS)
                           if n_verts * len(ball_points(1.0, k)) <= CONVEX_MAX_POINTS), None)
            if subdiv is not None:
                ball = ball_points(c, subdiv)
                grown = hull([v.co + b for v in pin.verts for b in ball])
                candidates.append(("hull", grown, clearance(grown, samples)))
        # 2. vertex-normal offset (exact for smooth shapes)
        if not candidates or candidates[0][2] < need:
            off = _bm(_offset(pin, c), faces)
            united, _why = boolean.unite_bm(off)
            off.free()
            if united is not None:
                candidates.append(("offset", united, clearance(united, samples)))
        # 3. Minkowski sum of convex pieces, when the offset folded or lost clearance
        if not candidates or max(cand[2] for cand in candidates) < need:
            n_tris = sum(len(f) - 2 for f in faces)
            if n_tris <= MINKOWSKI_MAX_TRIS:
                with progress.busy(f"building the socket of custom connector '{name}' ({len(faces)} faces)"):
                    pieces = minkowski_pieces(pin, c)
                    united, _why = boolean.unite_bm(pieces)
                    pieces.free()
                if united is not None:
                    candidates.append(("minkowski", united, clearance(united, samples)))
        if not candidates:
            off = _bm(_offset(pin, c), faces)
            got = clearance(off, samples)
            result = (*_to_lists(off), got,
                      f"the custom socket could not be built cleanly (it keeps {_share(got, c)} of the "
                      "clearance); simplify the custom mesh")
            off.free()
        else:
            _method, best, got = max(candidates, key=lambda cand: cand[2])
            note = "" if got >= need else (f"the custom socket keeps only {_share(got, c)} of the clearance "
                                           "somewhere (a slot or corner finer than the clearance); "
                                           "simplify the custom mesh")
            result = (*_to_lists(best), got, note)
    finally:
        for _m, bm, _g in candidates:
            bm.free()
        pin.free()
    if len(_CACHE) >= CACHE_SIZE:
        _CACHE.clear()
    _CACHE[key] = result
    return result
