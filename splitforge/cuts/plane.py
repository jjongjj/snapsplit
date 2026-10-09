# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# cuts/plane.py
"""Planar cuts: plane frames (local <-> world) and the bmesh split with gap + cap.

Pure functions on mathutils/bmesh values; no Blender data-blocks are created.
"""

from mathutils import Matrix, Vector

from ..core import meshlib

AXES = {'X': Vector((1.0, 0.0, 0.0)), 'Y': Vector((0.0, 1.0, 0.0)), 'Z': Vector((0.0, 0.0, 1.0))}


def world_frame(matrix_world, origin, normal, tangent=None):
    """Seam frame in world space: (co, n, t, b), unit n/t/b, b = n x t.

    ``origin``/``normal``/``tangent`` are object-local (as stored on a cut).
    Normals transform with the inverse transpose, so non-uniform scale keeps
    the plane exact; the tangent is mapped as a direction and projected into
    the plane.
    """
    m = Matrix(matrix_world)
    m3 = m.to_3x3()
    co = m @ Vector(origin)
    n = m3.inverted_safe().transposed() @ Vector(normal)
    if n.length < 1e-12:
        n = Vector((0.0, 0.0, 1.0))
    t = m3 @ Vector(tangent) if tangent is not None else None
    n, t, b = meshlib.orthonormal_basis(n, t)
    return co, n, t, b


def local_frame(matrix_world, co, n, t):
    """Inverse of world_frame: world (co, n, t) -> local (origin, normal, tangent)."""
    m = Matrix(matrix_world)
    m3 = m.to_3x3()
    origin = m.inverted_safe() @ Vector(co)
    normal = (m3.transposed() @ Vector(n)).normalized()
    tangent = (m3.inverted_safe() @ Vector(t)).normalized()
    return origin, normal, tangent


def axis_plane(matrix_world, center_world, axis, offset):
    """Local (origin, normal, tangent) of a world-axis plane.

    The plane passes through ``center_world + axis * offset`` (offset in
    Blender units, i.e. already converted from mm).
    """
    n = AXES[axis]
    n, t, _b = meshlib.orthonormal_basis(n)
    return local_frame(matrix_world, Vector(center_world) + n * offset, n, t)


def signed_distances(bm, co, n):
    """(min, max) signed distance of the vertices of ``bm`` to the plane."""
    if not bm.verts:
        return 0.0, 0.0
    d = [(v.co - co).dot(n) for v in bm.verts]
    return min(d), max(d)


def split(bm, co, n, gap, cap=True):
    """Split a world-space bmesh by the plane (co, n) with a ``gap`` (BU).

    Returns ``(positive, negative, cap_ok)``; a side is None when no material
    is left there. Pieces entirely on one side are returned as a copy without
    bisecting, so later cuts that miss a piece leave it untouched.
    """
    co, n = Vector(co), Vector(n).normalized()
    half = max(gap, 0.0) * 0.5
    lo, hi = signed_distances(bm, co, n)
    eps = max(meshlib.bm_diagonal(bm) * 1e-6, 1e-7)
    if lo >= half - eps:
        return bm.copy(), None, True
    if hi <= -half + eps:
        return None, bm.copy(), True
    pos, neg, ok = meshlib.split_by_plane(bm, co, n, gap, cap)
    if not pos.faces:
        pos.free()
        pos = None
    if not neg.faces:
        neg.free()
        neg = None
    return pos, neg, ok
