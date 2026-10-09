# SPDX-License-Identifier: GPL-3.0-or-later
"""Baseline: legacy planar_split of a hole-filled Suzanne; seams are capped."""

import bpy

import lib


def run(ctx):
    lib.set_scene_mm()
    monkey = lib.make_monkey_manifold(40.0)
    assert lib.is_manifold(monkey), "input Suzanne not manifold"
    src_name = monkey.name
    lib.select_only([monkey])

    props = bpy.context.scene.snapsplit
    assert props.cap_seams_during_split, "auto-cap is expected to be on by default"
    props.split_axis = 'Z'
    props.parts_count = 2
    lib.run_op(bpy.ops.snapsplit.planar_split)

    parts = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    assert len(parts) == 2, [o.name for o in parts]
    for p in parts:
        assert lib.is_manifold(p), f"{p.name} not manifold (seam not capped)"
        assert lib.volume(p) > 0.0, f"{p.name} has no volume"
    # No volume-sum check: Suzanne's eye shells intersect the head, so the
    # volume of the input is not well defined (the sum differs by ~4%).
    assert src_name in bpy.data.objects, "original object was removed"
