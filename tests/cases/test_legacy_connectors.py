# SPDX-License-Identifier: GPL-3.0-or-later
"""Baseline: legacy add_connectors with 3 CYL_PIN on a Z-split cube keeps both parts manifold."""

import bpy

import lib


def run(ctx):
    lib.set_scene_mm()
    cube = lib.make_cube(40.0)
    lib.select_only([cube])

    props = bpy.context.scene.snapsplit
    props.split_axis = 'Z'
    props.parts_count = 2
    lib.run_op(bpy.ops.snapsplit.planar_split)
    parts = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    assert len(parts) == 2, [o.name for o in parts]
    half = [lib.volume(p) for p in parts]

    props.connector_type = 'CYL_PIN'
    props.connectors_per_seam = 3
    lib.select_only(parts)
    lib.run_op(bpy.ops.snapsplit.add_connectors)

    for p in parts:
        assert p.name in bpy.data.objects, "part removed by add_connectors"
        assert lib.is_manifold(p), f"{p.name} not manifold after connectors"
    after = [lib.volume(p) for p in parts]
    # One part gained pins (UNION), the other got sockets (DIFFERENCE)
    gained = [a > h * 1.001 for a, h in zip(after, half)]
    lost = [a < h * 0.999 for a, h in zip(after, half)]
    assert sorted(gained) == [False, True] and sorted(lost) == [False, True], (half, after)
