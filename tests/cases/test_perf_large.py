# SPDX-License-Identifier: GPL-3.0-or-later
"""Slow: ~510k-face Suzanne: legacy split (3 parts + 3 CYL_PIN per seam) and SplitForge Build, timed."""

import time

import bpy

import lib

SLOW = True


def run(ctx):
    lib.set_scene_mm()
    monkey = lib.make_monkey_manifold(80.0)
    mod = monkey.modifiers.new("subsurf", 'SUBSURF')
    mod.levels = 5
    bpy.ops.object.modifier_apply(modifier=mod.name)
    faces = len(monkey.data.polygons)
    ctx.metric("faces", faces)
    assert faces > 500_000, faces
    lib.select_only([monkey])

    props = bpy.context.scene.snapsplit
    props.split_axis = 'Z'
    props.parts_count = 3
    t0 = time.perf_counter()
    lib.run_op(bpy.ops.snapsplit.planar_split)
    ctx.metric("split_s", round(time.perf_counter() - t0, 2))
    parts = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    assert len(parts) == 3, [o.name for o in parts]
    # The cut through the eyes once made capping random (eye loops sometimes
    # taken as holes of the head loop); face counts must now be identical per run.
    ctx.metric("part_faces", "/".join(str(len(p.data.polygons)) for p in sorted(parts, key=lambda o: o.name)))
    for p in parts:
        assert lib.is_manifold(p), f"{p.name} not manifold after split"

    props.connector_type = 'CYL_PIN'
    props.connectors_per_seam = 3
    lib.select_only(parts)
    t0 = time.perf_counter()
    lib.run_op(bpy.ops.snapsplit.add_connectors)
    ctx.metric("connectors_s", round(time.perf_counter() - t0, 2))
    for p in parts:
        assert p.name in bpy.data.objects, "part removed by add_connectors"
        assert lib.is_manifold(p), f"{p.name} not manifold"

    # SplitForge Build on the same mesh: 2 Z cuts (3 parts) with 3 pins per seam region
    bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
    lib.set_scene_mm()
    monkey = lib.make_monkey_manifold(80.0)
    mod = monkey.modifiers.new("subsurf", 'SUBSURF')
    mod.levels = 5
    bpy.ops.object.modifier_apply(modifier=mod.name)
    lib.select_only([monkey])
    for offset in (-10.0, 10.0):
        lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z', offset_mm=offset)
        cut = monkey.splitforge_stack.cuts[-1]
        cut.connector_count = 3
        lib.run_op(bpy.ops.splitforge.connector_add_auto)
    t0 = time.perf_counter()
    lib.run_op(bpy.ops.splitforge.build)
    ctx.metric("build_s", round(time.perf_counter() - t0, 2))
    parts = [o for o in bpy.data.objects if o.get("splitforge_source") == monkey.name]
    assert len(parts) == 3, [o.name for o in parts]
    for p in parts:
        assert lib.is_manifold(p), f"{p.name} not manifold after build"

    # P2-7: curved (S) stroke cut on the same ~510k-face Suzanne, gap 0.3 mm, Distribute + Build
    bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
    lib.set_scene_mm()
    monkey = lib.make_monkey_manifold(80.0)
    mod = monkey.modifiers.new("subsurf", 'SUBSURF')
    mod.levels = 5
    bpy.ops.object.modifier_apply(modifier=mod.name)
    lib.select_only([monkey])
    import math
    pts = [(-56.0 + 112.0 * i / 39, 0.0, 4.0 + 6.0 * math.sin(2 * math.pi * i / 39)) for i in range(40)]
    t0 = time.perf_counter()
    lib.run_op(bpy.ops.splitforge.stack_add_stroke, points=[{"name": "", "co": p} for p in pts],
               direction=(0.0, 1.0, 0.0))
    ctx.metric("stroke_add_s", round(time.perf_counter() - t0, 2))
    cut = monkey.splitforge_stack.cuts[0]
    cut.gap_mm = 0.3
    cut.connector_count = 2
    t0 = time.perf_counter()
    lib.run_op(bpy.ops.splitforge.connector_add_auto)
    ctx.metric("stroke_distribute_s", round(time.perf_counter() - t0, 2))
    ctx.metric("stroke_connectors", len(cut.connectors))
    build = ctx.module("cuts.build")
    t0 = time.perf_counter()
    result = build.build(bpy.context, monkey)
    elapsed = time.perf_counter() - t0
    ctx.metric("stroke_build_s", round(elapsed, 2))
    ctx.metric("stroke_booleans", "; ".join(f"{label}={solver}({'/'.join(f'{a}:{s}s' for a, _r, s in att)})"
                                           for label, solver, att in result.booleans))
    assert not result.warnings, result.warnings
    parts = [bpy.data.objects[n] for n in result.parts]
    assert len(parts) == 2, result.parts
    for p in parts:
        assert lib.is_manifold(p), f"{p.name} not manifold after stroke build"
    if bpy.app.version >= (5, 0, 0):
        assert elapsed < 120.0, f"stroke build took {elapsed:.1f} s (limit 120 s on 5.2)"
