# SPDX-License-Identifier: GPL-3.0-or-later
"""P2-3: curved (stroke) cuts in Build and Easy, with gap.

Cube 40 mm with an S stroke drawn in the front view (extruded along +Y), gap 0.5:
two manifold parts, part A above the S, volume sum = cube - gap volume (gap volume
= gap x ribbon length inside the cube x depth), parts do not interpenetrate and keep
the gap between them, the source is unchanged. A two-point stroke equals the
matching plane cut. A filled Suzanne (eyes = separate shells that intersect the
head): a stroke through the muzzle leaves the eyes whole on their side with an info
report; a stroke through the eyes cuts them. Stroke + plane: 4 parts. Disable,
remove, rebuild leave no leftovers; an invalid stored stroke fails Build with a
message and changes nothing; Easy stroke (gap + connectors) builds in one call.
"""

import math

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

import lib

D = (0.0, 1.0, 0.0)   # front view direction


def s_points(z_amp=8.0, z_off=0.0, x0=-26.0, x1=26.0, n=40):
    return [(x0 + (x1 - x0) * i / (n - 1), 0.0, z_off + z_amp * math.sin(2 * math.pi * i / (n - 1)))
            for i in range(n)]


def add_stroke(points, direction=D, **kw):
    lib.run_op(bpy.ops.splitforge.stack_add_stroke, points=[{"name": "", "co": p} for p in points],
               direction=direction, **kw)


def parts_of(name):
    return sorted((o for o in bpy.data.objects if o.get("splitforge_source") == name), key=lambda o: o.name)


def bvh(obj):
    bm = lib.bm_of(obj)
    try:
        return BVHTree.FromBMesh(bm)
    finally:
        bm.free()


def assert_apart(fit, a, b, gap):
    """No vertex of one part inside the other; the parts keep (almost) the gap apart."""
    ta, tb = bvh(a), bvh(b)
    for x, tx, y in ((a, tb, b), (b, ta, a)):
        inside = [(tuple(v.co), fit.depth_inside(tx, x.matrix_world @ v.co)) for v in x.data.vertices
                  if fit.depth_inside(tx, x.matrix_world @ v.co) > 1e-3]
        assert not inside, f"{len(inside)} vertices of {x.name} inside {y.name}: {inside[:3]}"
    if gap > 0:
        closest = min(tb.find_nearest(a.matrix_world @ v.co)[3] for v in a.data.vertices)
        assert closest >= 0.9 * gap, f"{a.name}-{b.name} only {closest:.4f} apart (gap {gap})"


def expect_error(call, text):
    """The operator reports an error containing ``text`` (bpy.ops raises it as RuntimeError)."""
    try:
        result = call()
    except RuntimeError as ex:
        assert text in str(ex), (text, str(ex))
        return
    raise AssertionError(f"no error ({result}), expected {text!r}")


def run(ctx):
    build = ctx.module("cuts.build")
    stroke = ctx.module("cuts.stroke")
    fit = ctx.module("connectors.fit")
    lib.set_scene_mm()

    # --- S cut through a cube with a 0.5 mm gap --------------------------------------
    cube = lib.make_cube(40.0)
    cube.name = "SCube"
    lib.select_only([cube])
    h0 = lib.mesh_hash(cube)
    add_stroke(s_points())
    stack = cube.splitforge_stack
    cut = stack.cuts[0]
    assert cut.kind == 'STROKE' and len(cut.points) > 50 and cut.name.startswith("Stroke"), (cut.kind, len(cut.points))
    assert (Vector(cut.direction) - Vector(D)).length < 1e-6
    cut.gap_mm = 0.5
    result = build.build(bpy.context, cube)
    assert not result.warnings, result.warnings
    parts = parts_of("SCube")
    assert [p.name for p in parts] == ["SCube_A", "SCube_B"], [p.name for p in parts]
    for p in parts:
        assert lib.is_manifold(p), p.name
    a, b = parts
    spec = build.cut_spec(cube, cut, bpy.context.scene)
    inside = [p for p in spec.cutter.curve if abs(p[0]) <= 20.0]
    length = stroke.polyline_length(inside)
    gap_volume = 0.5 * length * 40.0
    total = lib.volume(a) + lib.volume(b)
    ctx.metric("s_volume", f"{total:.1f}/{64000 - gap_volume:.1f}")
    lib.assert_close(total, 64000.0 - gap_volume, rel=0.01, msg="cube S cut volume")
    assert lib.mesh_hash(cube) == h0, "source changed"
    ca = sum((a.matrix_world @ v.co for v in a.data.vertices), Vector()) / len(a.data.vertices)
    cb = sum((b.matrix_world @ v.co for v in b.data.vertices), Vector()) / len(b.data.vertices)
    assert ca.z > cb.z, "part A must be on the positive side (above a left-to-right stroke)"
    assert_apart(fit, a, b, 0.5)
    # Every boolean of the cut is recorded with the solver that produced it
    cut_bools = [entry for entry in result.booleans if entry[0].startswith(cut.name)]
    assert len(cut_bools) == 2 and all(entry[1] for entry in cut_bools), result.booleans
    ctx.metric("s_solvers", ",".join(entry[1] for entry in cut_bools))

    # --- pair check: a plausible single result whose pair loses volume is redone -----------
    boolean = ctx.module("core.boolean")
    original = boolean._evaluate

    def lossy(target, operand, operation, attempt):
        """The first EXACT side result shrunk by 10 %: still manifold and smaller (passes the
        single-boolean check), but A + B no longer adds up to the piece."""
        mesh = original(target, operand, operation, attempt)
        if attempt == 'EXACT' and target.name.startswith("_SplitForge_Target") and not lossy.done:
            lossy.done = True
            mesh.transform(Matrix.Scale(0.9, 4))
        return mesh
    lossy.done = False
    lib.select_only([cube])
    cube.hide_set(False)
    boolean._evaluate = lossy
    try:
        retried = build.build(bpy.context, cube)
    finally:
        boolean._evaluate = original
    side = [entry for entry in retried.booleans if entry[0].startswith(cut.name)]
    ctx.metric("pair_retry", "; ".join(f"{label}={solver}" for label, solver, _a in side))
    assert lossy.done and len(side) == 4, side             # A, B, then both redone
    assert side[2][1] != 'EXACT' and side[3][1] != 'EXACT', side
    total = sum(lib.volume(bpy.data.objects[n]) for n in retried.parts)
    lib.assert_close(total, 64000.0 - gap_volume, rel=0.01, msg="volume after the pair retry")

    # --- disable / rebuild / remove: no leftovers --------------------------------------
    n_objects, n_meshes = len(bpy.data.objects), len(bpy.data.meshes)
    lib.select_only([cube])
    cube.hide_set(False)
    build.build(bpy.context, cube)
    assert (len(bpy.data.objects), len(bpy.data.meshes)) == (n_objects, n_meshes), "rebuild leaked data"
    assert not [o for o in bpy.data.objects if o.name.startswith("_SplitForge")]
    assert not [m for m in bpy.data.meshes if m.users == 0], [m.name for m in bpy.data.meshes if m.users == 0]

    # Duplicate copies the stroke (points, direction) under a new uid
    lib.run_op(bpy.ops.splitforge.stack_duplicate, index=0)
    dup = cube.splitforge_stack.cuts[1]
    src = cube.splitforge_stack.cuts[0]
    assert dup.kind == 'STROKE' and dup.uid != src.uid
    assert [tuple(p.co) for p in dup.points] == [tuple(p.co) for p in src.points]
    assert tuple(dup.direction) == tuple(src.direction) and dup.gap_mm == src.gap_mm
    lib.run_op(bpy.ops.splitforge.stack_remove, index=1)

    # --- two points = the matching plane cut ----------------------------------------------
    line = [(-30.0, 0.0, 2.0), (30.0, 0.0, 6.0)]
    pa = lib.make_cube(40.0)
    pa.name = "LineCube"
    lib.select_only([pa])
    add_stroke(line)
    pa.splitforge_stack.cuts[0].gap_mm = 0.4
    build.build(bpy.context, pa)
    t = (Vector(line[1]) - Vector(line[0])).normalized()
    n = t.cross(Vector(D))
    pb = lib.make_cube(40.0)
    pb.name = "PlaneCube"
    lib.select_only([pb])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, use_plane=True, origin=line[0], normal=n)
    pb.splitforge_stack.cuts[0].gap_mm = 0.4
    build.build(bpy.context, pb)
    for side in ("A", "B"):
        vs = lib.volume(bpy.data.objects[f"LineCube_{side}"])
        vp = lib.volume(bpy.data.objects[f"PlaneCube_{side}"])
        lib.assert_close(vs, vp, rel=0.01, msg=f"two-point stroke vs plane, side {side}")

    # --- Suzanne: eyes are separate shells intersecting the head ------------------------
    monkey = lib.make_monkey_manifold(40.0)
    monkey.name = "SMonkey"
    v_monkey = lib.volume(monkey)
    lib.select_only([monkey])
    # Muzzle stroke (below the eyes, front view): the eyes are not crossed
    add_stroke(s_points(z_amp=2.5, z_off=-6.0, x0=-30.0, x1=30.0))
    result = build.build(bpy.context, monkey)
    parts = parts_of("SMonkey")
    assert len(parts) == 2 and all(lib.is_manifold(p) for p in parts), [p.name for p in parts]
    assert any("2 separate shell(s)" in i for i in result.infos), result.infos
    total = sum(lib.volume(p) for p in parts)
    # The exact solver unites the overlapping eye/head volume (~1.7 %): sum <= source, within 4 %
    assert v_monkey * 0.96 <= total <= v_monkey * 1.0001, (total, v_monkey)
    ctx.metric("monkey_muzzle", f"{total:.0f}/{v_monkey:.0f} {result.booleans[0][1]}")
    # Accurate (Auto on a small mesh) unites the intersecting eye shells first, then cuts with EXACT
    assert any("united into one solid" in i for i in result.infos), result.infos
    assert all(entry[1] == 'EXACT' and len(entry[2]) == 1 for entry in result.booleans), result.booleans
    # Through the eyes (z ~ +5 at the front): the eyes are cut as well
    stack = monkey.splitforge_stack
    stack.cuts.clear()
    lib.select_only([monkey])
    monkey.hide_set(False)
    add_stroke(s_points(z_amp=1.5, z_off=4.0, x0=-30.0, x1=30.0))
    result = build.build(bpy.context, monkey)
    parts = parts_of("SMonkey")
    assert len(parts) == 2 and all(lib.is_manifold(p) for p in parts)
    assert not any("separate shell" in i for i in result.infos), result.infos

    # --- stroke + plane: 4 parts ------------------------------------------------------------
    combo = lib.make_cube(40.0)
    combo.name = "Combo"
    lib.select_only([combo])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z', offset_mm=-4.0)
    vertical = [(3.0 * math.sin(2 * math.pi * i / 39), 0.0, -26.0 + 52.0 * i / 39) for i in range(40)]
    add_stroke(vertical)
    combo.splitforge_stack.cuts[1].gap_mm = 0.3
    result = build.build(bpy.context, combo)
    parts = parts_of("Combo")
    assert len(parts) == 4, [p.name for p in parts]
    assert all(lib.is_manifold(p) for p in parts)
    total = sum(lib.volume(p) for p in parts)
    lib.assert_close(total, 64000.0 - 0.3 * 40.0 * 40.0, rel=0.01, msg="plane + stroke volume")
    for i, p in enumerate(parts):
        for q in parts[i + 1:]:
            assert_apart(fit, p, q, 0.0)
    # Disabled stroke: back to the plane's 2 parts in the same collection
    combo.splitforge_stack.cuts[1].enabled = False
    lib.select_only([combo])
    combo.hide_set(False)
    result = build.build(bpy.context, combo)
    assert len(parts_of("Combo")) == 2

    # --- invalid stored stroke: Build fails with a message, nothing changes -----------
    bad = lib.make_cube(40.0)
    bad.name = "Bad"
    lib.select_only([bad])
    add_stroke(s_points())
    loop = [Vector((10 * math.cos(x), 0, 10 * math.sin(x))) for x in [i * 0.3 for i in range(25)]]
    ctx.module("model.stack").set_stroke(bad.splitforge_stack.cuts[0], loop, Vector(D))
    before = len(bpy.data.objects)
    try:
        build.build(bpy.context, bad)
        raise AssertionError("self-crossing stroke built")
    except build.BuildError as ex:
        assert "crosses itself" in str(ex), str(ex)
    assert len(bpy.data.objects) == before and not parts_of("Bad")
    expect_error(lambda: bpy.ops.splitforge.build(), "crosses itself")

    # A stroke that misses the object is refused when it is added
    far = [(-30.0, 0.0, 40.0), (30.0, 0.0, 45.0)]
    expect_error(lambda: bpy.ops.splitforge.stack_add_stroke(points=[{"name": "", "co": p} for p in far],
                                                            direction=D), "does not cross the object")
    assert len(bad.splitforge_stack.cuts) == 1

    # --- Easy: stroke + gap + connectors, one call ----------------------------------------
    easy = lib.make_cube(40.0)
    easy.name = "EasyS"
    lib.select_only([easy])
    s = bpy.context.scene.splitforge
    s.easy_gap_mm = 0.3
    s.easy_connector_count = 2
    add_stroke(s_points(z_amp=4.0), easy=True)
    cut = easy.splitforge_stack.cuts[0]
    assert cut.kind == 'STROKE' and abs(cut.gap_mm - 0.3) < 1e-6 and len(cut.connectors) >= 2, \
        (cut.kind, cut.gap_mm, len(cut.connectors))
    parts = parts_of("EasyS")
    assert len(parts) == 2 and all(lib.is_manifold(p) for p in parts)
    assert easy.hide_get()
    ctx.metric("easy_connectors", len(cut.connectors))
