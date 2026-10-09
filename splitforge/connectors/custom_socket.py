# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# connectors/custom_socket.py
"""Socket of a custom connector mesh: the pin grown by the clearance in every direction.

The quick way is to move every vertex outward along its normal (times the shell
factor, like Solidify's even thickness). That is exact for convex shapes, but
it folds where a slot or notch is narrower than twice the clearance (the two
walls' offsets cross) and loses clearance at concave or sharp corners (defect
D17). So the result is checked: the offset mesh must unite into a clean solid
and keep at least ``MIN_CLEARANCE_SHARE`` x clearance from every sample of the
pin surface (vertices, edge points, face centers). If it does not, the socket is
built as a Minkowski sum instead: the pin united with a prism over every face
(the face pushed out by the clearance), a cylinder around every edge and a
ball at every vertex (polygons sized so their inner radius is the clearance).
That is correct for any shape, slots narrower than 2 x clearance simply fill,
but costs one larger union, so it is only used when needed and for meshes of at
most MINKOWSKI_MAX_TRIS triangles. If no candidate reaches the required
clearance, the best one is used and a note (Build warning) says how much
clearance it has.

Results are cached per shape, size and clearance (plain vertex/face lists): the
fit checks of Distribute ask for the same socket many times. Uses temporary
objects through core/boolean.py (Build / operator context only).
"""

import math

import bmesh
from mathutils import Matrix
from mathutils.bvhtree import BVHTree

from ..core import boolean
from . import fit

MIN_CLEARANCE_SHARE = 0.9
MINKOWSKI_MAX_TRIS = 4000
EDGE_SEGMENTS = 8
FLAT_DOT = 1.0 - 1e-6        # edges between (nearly) coplanar faces need no cylinder
CACHE_SIZE = 64

_CACHE = {}


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


def _minkowski(pin, c):
    """Pin + clearance ball as one bmesh of overlapping pieces (to be united)."""
    # Prisms over the polygons (not their triangles: coplanar neighbour prisms would share walls,
    # which the exact solver cannot resolve); only non-planar polygons are triangulated
    tri = pin.copy()
    tri.normal_update()
    first = next(iter(tri.verts)).co.copy()
    size = max((v.co - first).length for v in tri.verts)
    bent = [f for f in tri.faces if max(abs((v.co - f.verts[0].co).dot(f.normal)) for v in f.verts) > 1e-6 * size]
    if bent:
        bmesh.ops.triangulate(tri, faces=bent)
        tri.normal_update()
    out = pin.copy()
    for f in tri.faces:
        n = f.normal
        if n.length < 0.5:
            continue
        base = [v.co.copy() for v in f.verts]
        k = len(base)
        top = [p + n * c for p in base]
        # Reach slightly below the face so the prism overlaps the pin instead of touching it
        low = [p - n * (0.05 * c) for p in base]
        vs = [out.verts.new(p) for p in low + top]
        out.faces.new(list(reversed(vs[:k])))
        out.faces.new(vs[k:])
        for i in range(k):
            j = (i + 1) % k
            out.faces.new((vs[i], vs[j], vs[k + j], vs[k + i]))
    r_edge = c / math.cos(math.pi / EDGE_SEGMENTS)
    corners = set()
    for e in tri.edges:
        if len(e.link_faces) == 2 and e.link_faces[0].normal.dot(e.link_faces[1].normal) > FLAT_DOT:
            continue
        a, b = e.verts[0].co, e.verts[1].co
        d = b - a
        if d.length < 1e-9:
            continue
        rot = d.normalized().to_track_quat('Z', 'X').to_matrix().to_4x4()
        bmesh.ops.create_cone(out, cap_ends=True, segments=EDGE_SEGMENTS, radius1=r_edge, radius2=r_edge,
                              depth=d.length, matrix=Matrix.Translation((a + b) * 0.5) @ rot)
        corners.update((e.verts[0].index, e.verts[1].index))
    tri.verts.ensure_lookup_table()
    for i in corners:
        # An icosphere (2 subdivisions) of radius R keeps all its faces at least 0.98 R from its center
        bmesh.ops.create_icosphere(out, subdivisions=2, radius=c / 0.975,
                                   matrix=Matrix.Translation(tri.verts[i].co))
    tri.free()
    # Consistent outward normals for every piece (the union counts windings)
    bmesh.ops.recalc_face_normals(out, faces=out.faces[:])
    return out


def _share(got, c):
    return f"{100.0 * max(got, 0.0) / c:.0f} %" if c > 0.0 else "0 %"


def socket(verts, faces, c, step):
    """(socket verts, socket faces, achieved clearance, note) for a custom pin given in its connector frame.

    ``step``: sample spacing of the clearance check. ``note`` is "" when the
    clearance is at least MIN_CLEARANCE_SHARE x ``c``.
    """
    key = (tuple(tuple(round(x, 9) for x in v) for v in verts), tuple(faces), round(c, 9), round(step, 9))
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    pin = _bm(verts, faces)
    try:
        samples = pin_samples(pin, step)
        need = MIN_CLEARANCE_SHARE * c
        candidates = []
        # 1. vertex-normal offset (exact for convex shapes)
        off = _bm(_offset(pin, c), faces)
        united, _why = boolean.unite_bm(off)
        off.free()
        if united is not None:
            candidates.append(("offset", united, clearance(united, samples)))
        # 2. Minkowski sum, when the offset folded or lost clearance
        if not candidates or candidates[0][2] < need:
            n_tris = sum(len(f) - 2 for f in faces)
            if n_tris <= MINKOWSKI_MAX_TRIS:
                pieces = _minkowski(pin, c)
                united, _why = boolean.unite_bm(pieces)
                pieces.free()
                if united is not None:
                    candidates.append(("minkowski", united, clearance(united, samples)))
        if not candidates:
            off = _bm(_offset(pin, c), faces)
            result = (*_to_lists(off), clearance(off, samples), "")
            off.free()
            result = (result[0], result[1], result[2],
                      f"the custom socket could not be built cleanly (it keeps {_share(result[2], c)} of the "
                      "clearance); simplify the custom mesh")
        else:
            _method, best, got = max(candidates, key=lambda cand: cand[2])
            note = "" if got >= need else (f"the custom socket keeps only {_share(got, c)} of the clearance "
                                           "somewhere (a slot or corner finer than the clearance); "
                                           "simplify the custom mesh")
            result = (*_to_lists(best), got, note)
        for _m, bm, _g in candidates:
            bm.free()
    finally:
        pin.free()
    if len(_CACHE) >= CACHE_SIZE:
        _CACHE.clear()
    _CACHE[key] = result
    return result
