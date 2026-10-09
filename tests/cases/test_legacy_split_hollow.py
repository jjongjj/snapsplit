# SPDX-License-Identifier: GPL-3.0-or-later
"""Legacy split of a hollow box (2 mm wall): seams get ring caps, cavity stays open."""

import bpy

import lib


def run(ctx):
    lib.set_scene_mm()
    box = lib.make_hollow_box(40.0, 2.0)
    vol = lib.volume(box, signed=True)
    lib.assert_close(vol, 40.0 ** 3 - 36.0 ** 3, rel=1e-6, msg="hollow box volume")
    lib.select_only([box])

    props = bpy.context.scene.snapsplit
    props.split_axis = 'Z'
    props.parts_count = 2
    lib.run_op(bpy.ops.snapsplit.planar_split)

    parts = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    assert len(parts) == 2, [o.name for o in parts]
    for p in parts:
        assert lib.is_manifold(p), f"{p.name} not manifold"
    # A solid (non-ring) cap would fill the cavity and add ~36*36*... of volume
    lib.assert_close(sum(lib.volume(p, signed=True) for p in parts), vol, rel=0.01,
                     msg="part volume sum (ring caps)")
