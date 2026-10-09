# SPDX-License-Identifier: GPL-3.0-or-later
"""Slow: ~510k-face Suzanne, legacy split into 3 parts + 3 CYL_PIN per seam, timed."""

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
