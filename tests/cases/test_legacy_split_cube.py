# SPDX-License-Identifier: GPL-3.0-or-later
"""Baseline: legacy planar_split of a 40 mm cube along Z into 2 parts."""

import bpy

import lib


def run(ctx):
    lib.set_scene_mm()
    cube = lib.make_cube(40.0)
    src_name = cube.name
    vol = lib.volume(cube)
    lib.select_only([cube])

    props = bpy.context.scene.snapsplit
    props.split_axis = 'Z'
    props.parts_count = 2
    lib.run_op(bpy.ops.snapsplit.planar_split)

    parts = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    assert len(parts) == 2, [o.name for o in parts]
    for p in parts:
        assert lib.is_manifold(p), f"{p.name} not manifold"
    lib.assert_close(sum(lib.volume(p) for p in parts), vol, rel=0.01, msg="part volume sum")
    assert src_name in bpy.data.objects, "original object was removed"
