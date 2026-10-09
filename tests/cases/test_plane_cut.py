# SPDX-License-Identifier: GPL-3.0-or-later
"""P1-5: cuts/plane.split + core/meshlib: any plane normal, gap +-gap/2, capped (rings too)."""

import math

import bmesh
from mathutils import Vector

import lib


def _bm(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    return bm


def _manifold(bm):
    return (len(bm.faces) > 0 and all(e.is_manifold for e in bm.edges)
            and all(v.link_faces for v in bm.verts))


def _faces_on_plane(bm, co, n, eps=1e-4):
    return [f for f in bm.faces
            if all(abs((v.co - co).dot(n)) < eps for v in f.verts) and abs(abs(f.normal.dot(n)) - 1) < 1e-4]


def _check_split(plane, bm, co, n, gap, expected_total, gap_volume, label):
    pos, neg, ok = plane.split(bm, co, n, gap, cap=True)
    try:
        assert ok and pos is not None and neg is not None, label
        assert _manifold(pos) and _manifold(neg), f"{label}: parts not manifold"
        total = pos.calc_volume() + neg.calc_volume()
        lib.assert_close(total, expected_total, rel=0.02, msg=f"{label} volume sum")
        removed = bm.calc_volume() - total
        lib.assert_close(removed, gap_volume, rel=0.02, msg=f"{label} gap volume")
        # Every vertex keeps its side of the gap
        for part, side in ((pos, 1.0), (neg, -1.0)):
            d = [(v.co - co).dot(n) * side for v in part.verts]
            assert min(d) >= gap / 2 - 1e-4, f"{label}: vertex inside the gap ({min(d)})"
        return pos, neg
    except Exception:
        pos and pos.free()
        neg and neg.free()
        raise


def run(ctx):
    plane = ctx.module("cuts.plane")
    lib.set_scene_mm()

    # Solid cube, diagonal plane through the center, gap 0.4 mm
    cube = lib.make_cube(40.0)
    bm = _bm(cube)
    n = Vector((1.0, 1.0, 0.0)).normalized()
    section = 40.0 * math.sqrt(2.0) * 40.0
    pos, neg = _check_split(plane, bm, Vector(), n, 0.4, 40.0 ** 3 - 0.4 * section, 0.4 * section, "cube")
    for part in (pos, neg):
        caps = _faces_on_plane(part, n * (0.2 if part is pos else -0.2), n)
        assert caps, "cube: no cap face on the cut plane"
        part.free()
    bm.free()

    # Off-center tilted plane, no gap: volumes add up exactly
    bm = _bm(lib.make_cube(40.0))
    n2 = Vector((0.3, -0.5, 0.8)).normalized()
    pos, neg, ok = plane.split(bm, Vector((3.0, 2.0, -4.0)), n2, 0.0)
    assert ok and _manifold(pos) and _manifold(neg)
    lib.assert_close(pos.calc_volume() + neg.calc_volume(), 64000.0, rel=1e-6, msg="no-gap volume")
    pos.free(), neg.free(), bm.free()

    # Plane missing the mesh: one side None, the other an unchanged copy
    bm = _bm(lib.make_cube(40.0))
    pos, neg, ok = plane.split(bm, Vector((0.0, 0.0, 30.0)), Vector((0.0, 0.0, 1.0)), 0.5)
    assert ok and pos is None and neg is not None and len(neg.faces) == 6
    neg.free(), bm.free()

    # Hollow box (2 mm wall): both parts manifold, ring caps, cavity stays open
    box = lib.make_hollow_box(40.0, 2.0)
    bm = _bm(box)
    hollow = 40.0 ** 3 - 36.0 ** 3
    c = 0.2 * math.sqrt(2.0)  # x + z of the cap planes at +-gap/2 along (1, 0, 1)/sqrt(2)
    for normal, ring, cap_ring in (
            ((0.0, 0.0, 1.0), 40.0 ** 2 - 36.0 ** 2, 40.0 ** 2 - 36.0 ** 2),
            ((1.0, 0.0, 1.0), math.sqrt(2.0) * (40.0 ** 2 - 36.0 ** 2),
             math.sqrt(2.0) * ((40.0 - c) * 40.0 - (36.0 - c) * 36.0))):
        nn = Vector(normal).normalized()
        pos, neg = _check_split(plane, bm, Vector(), nn, 0.4, hollow - 0.4 * ring, 0.4 * ring, f"hollow {normal}")
        for part, side in ((pos, 1.0), (neg, -1.0)):
            caps = _faces_on_plane(part, nn * 0.2 * side, nn)
            # A ring cannot be a single n-gon per side
            assert len(caps) > 2, f"hollow {normal}: cap is not a ring ({len(caps)} face(s))"
            cap_area = sum(f.calc_area() for f in caps)
            lib.assert_close(cap_area, cap_ring, rel=1e-3, msg=f"hollow {normal} ring area")
            part.free()
    bm.free()

    # Internal cavity the cut does not touch (0.3 mm slab at z 3.45..3.75): capping
    # must not flip its normals (it used to recalc every face, turning the void into
    # added volume)
    cav = lib.make_cube(40.0)
    slab = bmesh.new()
    bmesh.ops.create_cube(slab, size=1.0)
    for v in slab.verts:
        v.co.x *= 30.0
        v.co.y *= 30.0
        v.co.z = 3.6 + v.co.z * 0.3
    bmesh.ops.reverse_faces(slab, faces=slab.faces)
    slab.normal_update()
    bm = bmesh.new()
    bm.from_mesh(cav.data)
    for f in slab.faces:
        bm.faces.new([bm.verts.new(v.co) for v in f.verts])
    slab.free()
    bm.normal_update()
    lib.assert_close(bm.calc_volume(signed=True), 64000.0 - 270.0, rel=1e-6, msg="cavity source")
    pos, neg, ok = plane.split(bm, Vector((0.0, 0.0, 0.0)), Vector((0.0, 0.0, 1.0)), 0.0)
    assert ok
    lib.assert_close(pos.calc_volume(signed=True), 32000.0 - 270.0, rel=1e-6, msg="cavity kept as a void")
    lib.assert_close(neg.calc_volume(signed=True), 32000.0, rel=1e-6)
    pos.free(), neg.free(), bm.free()
