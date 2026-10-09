# SPDX-License-Identifier: GPL-3.0-or-later
"""P4-1: polyline (manual points) cut -- straight segments between clicked points.

Four points across a 40 mm cube (front view, extruded along +Y): the points are stored as given
(no resampling or smoothing, sharp corners), both cutter solids are closed manifold, the ribbon
follows the straight segments, Build gives two manifold parts whose volumes add up to the cube
minus the gap slab (gap x ribbon length inside the cube x depth), part A on the positive side.
Connectors: Distribute puts them on the flat faces of the segments with the pin axis square to the
segment (sharp seam frame, not interpolated across a corner) and Build applies them without
warnings (pin part grows, socket part shrinks). A connector placed on a corner is skipped by Build
("bends into"). Two points = the same split as the equivalent plane cut. Invalid point sets are
refused with a reason (one point, crossing segments, missing the object); the object moving
afterwards moves the cut (object-local points). Redraw (replace_uid) keeps uid and connectors.
Easy polyline builds at once (gap + connectors). Undo after adding restores the stack.
"""

import math

import bpy
from mathutils import Vector

import lib

PTS = [(-30.0, 0.0, -5.0), (-6.0, 0.0, 8.0), (6.0, 0.0, -8.0), (30.0, 0.0, 5.0)]
GAP = 0.5


def add(points, direction=(0.0, 1.0, 0.0), **kw):
    return bpy.ops.splitforge.stack_add_polyline(points=[{"name": "", "co": p} for p in points],
                                                 direction=direction, **kw)


def parts(name):
    return sorted((o for o in bpy.data.objects if o.get("splitforge_source") == name), key=lambda o: o.name)


def expect_error(fn, text):
    try:
        fn()
    except RuntimeError as ex:
        assert text in str(ex), (text, str(ex))
        return str(ex)
    raise AssertionError(f"expected an error containing {text!r}")


def clipped_length(pts, half=20.0):
    """Length of the XZ polyline inside the square |x|, |z| <= half (sampled)."""
    total = 0.0
    for a, b in zip(pts, pts[1:]):
        n = 2000
        for k in range(n):
            p = Vector(a).lerp(Vector(b), (k + 0.5) / n)
            if abs(p.x) <= half and abs(p.z) <= half:
                total += (Vector(b) - Vector(a)).length / n
    return total


def run(ctx):
    build = ctx.module("cuts.build")
    stroke = ctx.module("cuts.stroke")
    meshlib = ctx.module("core.meshlib")
    lib.set_scene_mm()
    cube = lib.make_cube(40.0)
    cube.name = "PL"
    lib.select_only([cube])
    bpy.ops.ed.undo_push(message="before polyline")
    assert add(PTS) == {'FINISHED'}
    cut = cube.splitforge_stack.cuts[0]
    assert cut.kind == 'POLYLINE' and cut.name.startswith("Polyline"), (cut.kind, cut.name)
    assert [tuple(round(c, 6) for c in p.co) for p in cut.points] == PTS, "points must be kept as clicked"

    # cutter: closed solids, ribbon along the straight segments
    cut.gap_mm = GAP
    spec = build.cut_spec(cube, cut, bpy.context.scene)
    assert spec.kind == 'POLYLINE'
    for maker in (spec.cutter.remove_for_a, spec.cutter.remove_for_b):
        bm = maker()
        try:
            assert meshlib.bm_is_manifold(bm) and meshlib.bm_volume(bm) > 0.0
        finally:
            bm.free()
    for a, b in zip(PTS, PTS[1:]):
        for f in (0.25, 0.5, 0.75):
            p = Vector(a).lerp(Vector(b), f)
            assert spec.barrier().distance(p) < 1e-4, ("ribbon off the segment", p)

    # build
    res = build.build(bpy.context, cube)
    a, b = bpy.data.objects["PL_A"], bpy.data.objects["PL_B"]
    assert lib.is_manifold(a) and lib.is_manifold(b)
    slab = GAP * clipped_length(PTS) * 40.0
    lib.assert_close(lib.volume(a) + lib.volume(b), 64000.0 - slab, rel=0.005, msg="A + B = cube - gap")
    assert (sum((a.matrix_world @ v.co for v in a.data.vertices), Vector()) / len(a.data.vertices)).z > \
        (sum((b.matrix_world @ v.co for v in b.data.vertices), Vector()) / len(b.data.vertices)).z, "A above"
    ctx.metric("parts", f"{lib.volume(a):.1f}/{lib.volume(b):.1f} slab {slab:.1f} {res.infos[-1]}")
    va, vb = lib.volume(a), lib.volume(b)

    # connectors on the flat faces, axis square to the segment
    lib.select_only([cube])
    cube.hide_set(False)
    assert bpy.ops.splitforge.connector_add_auto() == {'FINISHED'}
    cut = cube.splitforge_stack.cuts[0]
    assert len(cut.connectors) == 2, len(cut.connectors)
    spec = build.cut_spec(cube, cut, bpy.context.scene)
    segs = [(Vector(p), Vector(q)) for p, q in zip(PTS, PTS[1:])]
    for c in cut.connectors:
        m = spec.matrix(c.u, c.v, 0.0)
        axis = Vector(m.col[2][:3])
        p = m.translation
        seg = min(segs, key=lambda s: ((p - s[0]) - (s[1] - s[0]) * max(0.0, min(1.0, (p - s[0]).dot(s[1] - s[0])
                                                                                  / (s[1] - s[0]).length_squared))).length)
        assert abs(axis.dot((seg[1] - seg[0]).normalized())) < 1e-6, ("pin axis not square to its segment", axis)
    res = build.build(bpy.context, cube)
    assert not res.warnings, res.warnings
    a, b = bpy.data.objects["PL_A"], bpy.data.objects["PL_B"]
    assert lib.is_manifold(a) and lib.is_manifold(b)
    assert lib.volume(a) > va and lib.volume(b) < vb, "pins on A, sockets in B"
    # a connector on a corner: Build skips it (the seam bends into it)
    lib.select_only([cube])
    corner = spec.centerline().uv_of(Vector(PTS[1]))
    c = cut.connectors.add()
    c.u, c.v, c.width_mm, c.length_mm = corner[0], 0.0, 5.0, 10.0
    res = build.build(bpy.context, cube)
    assert any("bends into" in w for w in res.warnings), res.warnings
    cut.connectors.remove(len(cut.connectors) - 1)

    # two points = the plane cut
    two = lib.make_cube(40.0)
    two.name = "PL2"
    lib.select_only([two])
    assert add([(-30.0, 0.0, 3.0), (30.0, 0.0, 3.0)]) == {'FINISHED'}
    build.build(bpy.context, two)
    plane = lib.make_cube(40.0)
    plane.name = "PLP"
    lib.select_only([plane])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z', offset_mm=3.0)
    build.build(bpy.context, plane)
    for side in "AB":
        lib.assert_close(lib.volume(bpy.data.objects[f"PL2_{side}"]), lib.volume(bpy.data.objects[f"PLP_{side}"]),
                         rel=1e-4, msg=f"two-point polyline side {side}")

    # invalid point sets
    bad = lib.make_cube(40.0)
    bad.name = "PLBad"
    lib.select_only([bad])
    expect_error(lambda: add([(0.0, 0.0, 0.0)]), "at least 2 points")
    expect_error(lambda: add([(-30, 0, 0), (30, 0, 0), (30, 0, 10), (0, 0, -10)]), "polyline crosses itself: place the points without loops")
    expect_error(lambda: add([(-30, 0, 60), (30, 0, 60)]), "does not cross the object")
    assert len(bad.splitforge_stack.cuts) == 0

    # moving the object moves the cut (local points)
    lib.select_only([cube])
    before = [tuple(cube.matrix_world @ Vector(p.co)) for p in cube.splitforge_stack.cuts[0].points]
    cube.location.x += 7.0
    bpy.context.view_layer.update()
    after = [tuple(cube.matrix_world @ Vector(p.co)) for p in cube.splitforge_stack.cuts[0].points]
    assert all(math.isclose(q[0] - p[0], 7.0, abs_tol=1e-5) for p, q in zip(before, after))
    cube.location.x -= 7.0
    bpy.context.view_layer.update()

    # redraw keeps uid and connectors
    cut = cube.splitforge_stack.cuts[0]
    uid, n_conn = cut.uid, len(cut.connectors)
    assert add([(-30.0, 0.0, 4.0), (0.0, 0.0, -4.0), (30.0, 0.0, 4.0)], replace_uid=uid) == {'FINISHED'}
    cut = cube.splitforge_stack.cuts[0]
    assert cut.uid == uid and len(cut.connectors) == n_conn and len(cut.points) == 3 and cut.kind == 'POLYLINE'
    expect_error(lambda: bpy.ops.splitforge.stack_add_stroke(
        points=[{"name": "", "co": p} for p in PTS], direction=(0, 1, 0), replace_uid="nope"), "No cut")

    # Easy: gap + connectors + build in one step
    easy = lib.make_cube(40.0)
    easy.name = "PLE"
    lib.select_only([easy])
    s = bpy.context.scene.splitforge
    s.easy_gap_mm, s.easy_connector_count = 0.3, 2
    assert add(PTS, easy=True) == {'FINISHED'}
    ps = parts("PLE")
    assert len(ps) == 2 and all(lib.is_manifold(p) for p in ps), ps
    assert len(easy.splitforge_stack.cuts[0].connectors) == 2
    assert math.isclose(easy.splitforge_stack.cuts[0].gap_mm, 0.3, abs_tol=1e-6)

    # undo after adding restores the stack
    bpy.ops.ed.undo_push(message="after")
    n = len(bpy.data.objects["PLE"].splitforge_stack.cuts)
    lib.select_only([bpy.data.objects["PLBad"]])
    assert add(PTS) == {'FINISHED'}
    bpy.ops.ed.undo_push(message="added")
    bpy.ops.ed.undo()
    assert len(bpy.data.objects["PLBad"].splitforge_stack.cuts) == 0
    assert len(bpy.data.objects["PLE"].splitforge_stack.cuts) == n
    assert stroke.RIBBON_KINDS == ('STROKE', 'POLYLINE')
