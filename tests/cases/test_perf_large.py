# SPDX-License-Identifier: GPL-3.0-or-later
"""Slow: ~510k-face Suzanne: SplitForge Build timed.

Planar (2 Z cuts + 3 pins per seam region), Phase 3 connector types (one Z cut with a dovetail,
a snap pin, a custom mesh pin and a dowel) and curved (S stroke, gap 0.3, 2 pins) builds run
with the Boolean quality Auto (MANIFOLD first above 200k faces) and Accurate (exact chain).
(The legacy SnapSplit split + connectors timings were removed with the legacy code in Phase 3.)"""

import math
import time

import bmesh
import bpy

import lib

SLOW = True


def big_monkey():
    monkey = lib.make_monkey_manifold(80.0)
    mod = monkey.modifiers.new("subsurf", 'SUBSURF')
    mod.levels = 5
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return monkey


def run(ctx):
    lib.set_scene_mm()
    monkey = big_monkey()
    faces = len(monkey.data.polygons)
    ctx.metric("faces", faces)
    assert faces > 500_000, faces

    # SplitForge Build: 2 Z cuts (3 parts) with 3 pins per seam region
    lib.select_only([monkey])
    for offset in (-10.0, 10.0):
        lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z', offset_mm=offset)
        cut = monkey.splitforge_stack.cuts[-1]
        cut.connector_count = 3
        lib.run_op(bpy.ops.splitforge.connector_add_auto)
    build = ctx.module("cuts.build")
    for quality in ('AUTO', 'ACCURATE'):
        bpy.context.scene.splitforge.boolean_quality = quality
        lib.select_only([monkey])
        monkey.hide_set(False)
        t0 = time.perf_counter()
        result = build.build(bpy.context, monkey)
        ctx.metric(f"build_s_{quality.lower()}", round(time.perf_counter() - t0, 2))
        ctx.metric(f"build_booleans_{quality.lower()}", "; ".join(
            f"{label}={solver}({'/'.join(f'{a}:{s}s' for a, _r, s in att)})" for label, solver, att in result.booleans))
        parts = [o for o in bpy.data.objects if o.get("splitforge_source") == monkey.name]
        assert len(parts) == 3, [o.name for o in parts]
        for p in parts:
            assert lib.is_manifold(p), f"{p.name} not manifold after build ({quality})"

    # P3: every heavier connector type on one Z cut (dovetail, snap pin, custom mesh, dowel)
    bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
    lib.set_scene_mm()
    monkey = big_monkey()
    knob = bpy.data.objects.new("Knob", bpy.data.meshes.new("Knob"))
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=1.0, radius2=0.7, depth=2.0)
    bm.to_mesh(knob.data)
    bm.free()
    bpy.context.scene.collection.objects.link(knob)
    lib.select_only([monkey])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z', offset_mm=-4.0)
    cut = monkey.splitforge_stack.cuts[0]
    # Positions from Distribute with a wider pin (its reach covers every type below), then the types
    t = bpy.context.scene.splitforge.new_connector
    t.kind, t.width_mm, t.custom_object = 'CYL_PIN', 8.0, knob
    cut.distribution, cut.connector_count, cut.connector_rows = 'GRID', 2, 2
    lib.run_op(bpy.ops.splitforge.connector_add_auto)
    assert len(cut.connectors) == 4, len(cut.connectors)
    for c, kind in zip(cut.connectors, ('DOVETAIL', 'SNAP_PIN', 'CUSTOM', 'DOWEL')):
        c.kind, c.width_mm, c.height_mm = kind, 5.0, 5.0
    for quality in ('AUTO', 'ACCURATE'):
        bpy.context.scene.splitforge.boolean_quality = quality
        lib.select_only([monkey])
        monkey.hide_set(False)
        t0 = time.perf_counter()
        result = build.build(bpy.context, monkey)
        elapsed = time.perf_counter() - t0
        q = quality.lower()
        ctx.metric(f"types_build_s_{q}", round(elapsed, 2))
        ctx.metric(f"types_booleans_{q}", "; ".join(
            f"{label}={solver}({'/'.join(f'{a}:{s}s' for a, _r, s in att)})" for label, solver, att in result.booleans))
        assert not result.warnings, result.warnings
        assert sorted(n[len("Suzanne_"):] for n in result.parts) == ["A", "B", "Dowel_1"], result.parts
        for name in result.parts:
            assert lib.is_manifold(bpy.data.objects[name]), f"{name} not manifold ({quality})"
        if bpy.app.version >= (5, 0, 0):
            assert elapsed < 120.0, f"types build ({quality}) took {elapsed:.1f} s (limit 120 s on 5.x)"

    # P2-7: curved (S) stroke cut on the same ~510k-face Suzanne, gap 0.3 mm, Distribute + Build
    bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
    lib.set_scene_mm()
    monkey = big_monkey()
    lib.select_only([monkey])
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
    for quality in ('AUTO', 'ACCURATE'):
        bpy.context.scene.splitforge.boolean_quality = quality
        lib.select_only([monkey])
        monkey.hide_set(False)
        t0 = time.perf_counter()
        result = build.build(bpy.context, monkey)
        elapsed = time.perf_counter() - t0
        q = quality.lower()
        ctx.metric(f"stroke_build_s_{q}", round(elapsed, 2))
        ctx.metric(f"stroke_booleans_{q}", "; ".join(
            f"{label}={solver}({'/'.join(f'{a}:{s}s' for a, _r, s in att)})" for label, solver, att in result.booleans))
        assert not result.warnings, result.warnings
        parts = [bpy.data.objects[n] for n in result.parts]
        assert len(parts) == 2, result.parts
        for p in parts:
            assert lib.is_manifold(p), f"{p.name} not manifold after stroke build ({quality})"
        if bpy.app.version >= (5, 0, 0):
            assert elapsed < 120.0, f"stroke build ({quality}) took {elapsed:.1f} s (limit 120 s on 5.x)"
