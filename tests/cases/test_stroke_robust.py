# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 2 verification round 3: D13, D14, D15.

- D14: on a part whose shells intersect (filled Suzanne, eyes in the head) a correct
  EXACT_SELF connector result was rejected because the plain volume counts the
  overlap twice. Now EXACT_SELF / VOXEL results are checked against the united
  volume: accepted without fallback. A non-manifold EXACT_SELF result is still
  rejected. Accurate Build unites the shells first: the planar build's connector
  booleans are all plain EXACT, no fallback.
- D13: curved-cut pieces are triangulated before the booleans, so re-triangulating
  non-planar faces cannot hide a loss: on a raw Suzanne head, a jittered cube and a
  cylinder with non-planar 64-gon caps, a correct cut passes on the first try and a
  side that lost 0.5 % or 3 % is rejected and redone.
- D15: the ribbon side test agrees with the exact 2D test on raw strokes with sharp
  corners (zig-zag, V), and its exact fallback is exercised there.
"""

import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

import lib

D = (0.0, 1.0, 0.0)


def obj_from_bm(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


def add_stroke(points, clean=True):
    lib.run_op(bpy.ops.splitforge.stack_add_stroke, points=[{"name": "", "co": p} for p in points],
               direction=D, clean=clean)


def s_points(amp, z0=0.0, n=40, x0=-30.0, x1=30.0):
    return [(x0 + (x1 - x0) * i / (n - 1), 0.0, z0 + amp * math.sin(2 * math.pi * i / (n - 1))) for i in range(n)]


def run(ctx):
    build = ctx.module("cuts.build")
    boolean = ctx.module("core.boolean")
    meshlib = ctx.module("core.meshlib")
    lib.set_scene_mm()
    scene = bpy.context.scene

    # --- D14: EXACT_SELF on intersecting shells is validated against the united volume ------
    monkey = lib.make_monkey_manifold(40.0)
    monkey.name = "Overlap"
    pin = bmesh.new()
    bmesh.ops.create_cone(pin, cap_ends=True, segments=24, radius1=2.5, radius2=2.5, depth=10.0,
                          matrix=Matrix.Translation((0.0, -14.0, 4.0)) @ Matrix.Rotation(math.pi / 2, 4, 'X'))
    res = boolean.apply(monkey, pin, 'UNION', order=['EXACT_SELF', 'MANIFOLD'], self_intersect=True)
    ctx.metric("d14_union", f"{res.solver} {res.attempts}")
    assert res.ok and res.solver == 'EXACT_SELF' and not res.fallback, res.attempts
    assert lib.is_manifold(monkey)
    # A non-manifold EXACT_SELF result is still rejected (no volume recheck rescues it)
    original = boolean._evaluate

    def broken(target, operand, operation, attempt):
        mesh = original(target, operand, operation, attempt)
        if attempt == 'EXACT_SELF':
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bmesh.ops.delete(bm, geom=[bm.faces[:][0]], context='FACES_ONLY')
            bm.to_mesh(mesh)
            bm.free()
        return mesh
    m2 = lib.make_monkey_manifold(40.0)
    boolean._evaluate = broken
    try:
        res = boolean.apply(m2, pin, 'UNION', order=['EXACT_SELF', 'MANIFOLD'], self_intersect=True)
    finally:
        boolean._evaluate = original
    pin.free()
    assert res.solver == 'MANIFOLD' and res.attempts[0][1] == "not manifold", res.attempts

    # Accurate planar Build with connectors: shells united once, every boolean plain EXACT
    acc = lib.make_monkey_manifold(40.0)
    acc.name = "AccPlanar"
    lib.select_only([acc])
    for offset in (-5.0, 5.0):
        lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z', offset_mm=offset)
        lib.run_op(bpy.ops.splitforge.connector_add_auto)
    scene.splitforge.boolean_quality = 'ACCURATE'
    result = build.build(bpy.context, acc)
    scene.splitforge.boolean_quality = 'AUTO'
    ctx.metric("d14_planar", ",".join(entry[1] for entry in result.booleans))
    assert result.booleans and all(e[1] == 'EXACT' and len(e[2]) == 1 for e in result.booleans), result.booleans
    assert any("united into one solid" in i for i in result.infos), result.infos
    assert all(lib.is_manifold(bpy.data.objects[n]) for n in result.parts)

    # --- D13: triangulated pieces, tight pair check on coarse non-planar meshes -------------
    def raw_head():
        m = lib.make_monkey_manifold(40.0)
        bm = lib.bm_of(m, world=False)
        shells = sorted(meshlib.shells(bm), key=len)
        bmesh.ops.delete(bm, geom=[v for s in shells[:-1] for v in s], context='VERTS')
        bm.to_mesh(m.data)
        bm.free()
        return m

    def jitter_cube():
        random.seed(1)
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=40.0)
        bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=3, use_grid_fill=True)
        for v in bm.verts:
            v.co += Vector([random.uniform(-4.0, 4.0) for _ in range(3)])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        return obj_from_bm("Jitter", bm)

    def ngon_cylinder():
        random.seed(2)
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=64, radius1=20, radius2=20, depth=40)
        for v in bm.verts:
            v.co.z += random.uniform(-5.0, 5.0)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        o = obj_from_bm("NgonCyl", bm)
        o.rotation_euler = (math.pi / 2, 0.0, 0.0)   # the caps face the view: the ribbon crosses both
        bpy.context.view_layer.update()
        return o

    for maker, amp in ((raw_head, 3.0), (jitter_cube, 6.0), (ngon_cylinder, 6.0)):
        for loss in (0.0, 0.005, 0.03):
            obj = maker()
            name = obj.name
            lib.select_only([obj])
            add_stroke(s_points(amp))
            obj.splitforge_stack.cuts[0].gap_mm = 0.3
            factor = (1.0 - loss) ** (1.0 / 3.0)

            def lossy(target, operand, operation, attempt):
                mesh = original(target, operand, operation, attempt)
                if loss and attempt == 'EXACT' and target.name.startswith("_SplitForge_Target") and not lossy.done:
                    lossy.done = True
                    mesh.transform(Matrix.Scale(factor, 4))
                return mesh
            lossy.done = False
            boolean._evaluate = lossy
            try:
                res = build.build(bpy.context, obj)
            finally:
                boolean._evaluate = original
            sides = [(label, solver) for label, solver, _a in res.booleans if label.startswith("Stroke")]
            ctx.metric(f"d13_{name}_{loss}", sides)
            if loss:
                assert lossy.done and len(sides) == 4 and sides[2][1] != 'EXACT', (name, loss, sides)
            else:
                assert len(sides) == 2 and all(s == 'EXACT' for _l, s in sides), (name, sides)
            assert all(lib.is_manifold(bpy.data.objects[n]) for n in res.parts), name
            for o in [bpy.data.objects[n] for n in res.parts] + [obj]:
                bpy.data.objects.remove(o)

    # --- D15: side test on raw sharp strokes ------------------------------------------------
    random.seed(7)
    strokes = {
        "zigzag_raw": [(-26 + 52 * i / 12, 0.0, 6.0 if i % 2 else -6.0) for i in range(13)],
        "sharpV_raw": [(-26, 0.0, 18), (0, 0.0, -15), (26, 0.0, 18)],
    }
    for name, pts in strokes.items():
        cube = lib.make_cube(40.0)
        cube.name = name
        lib.select_only([cube])
        add_stroke(pts, clean=False)
        spec = build.cut_spec(cube, cube.splitforge_stack.cuts[0], scene)
        bar = spec.barrier()
        bad = n = 0
        for k in range(20000):
            if k % 2:
                x, z = spec.cutter.curve[random.randrange(len(spec.cutter.curve))]
                p = spec.cutter.frame.to3d(x + random.gauss(0, 0.5), z + random.gauss(0, 0.5), random.uniform(-20, 20))
            else:
                p = Vector([random.uniform(-21.0, 21.0) for _ in range(3)])
            n += 1
            bad += bar.positive(p) != spec.cutter.is_positive(p)
        ctx.metric(f"d15_{name}", f"{bad}/{n} exact fallback {bar.exact_calls}")
        assert bad == 0, (name, bad)
        assert bar.exact_calls > 50, (name, bar.exact_calls)
