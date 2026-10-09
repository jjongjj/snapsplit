# SPDX-License-Identifier: GPL-3.0-or-later
"""P1-5/P1-6 on an organic mesh: filled Suzanne (eyes are separate overlapping shells).

Section loops are classified by face winding, so an eye loop lying inside the head
loop is capped as its own island instead of becoming a hole in the head cap (that
lost ~4 % of the volume at the bbox-center cut before).
"""

import bpy

import lib


def run(ctx):
    lib.set_scene_mm()
    monkey = lib.make_monkey_manifold(40.0)
    # Booleans Auto/Accurate unite the intersecting eye shells before cutting: the parts add up to
    # the united volume (the plain mesh volume counts the eye/head overlap twice)
    boolean = ctx.module("core.boolean")
    bm = lib.bm_of(monkey)
    united, why = boolean.unite_bm(bm)
    bm.free()
    assert united is not None, why
    v0 = united.calc_volume(signed=True)
    united.free()
    ctx.metric("overlap_pct", round(100.0 * (1.0 - v0 / lib.volume(monkey, signed=True)), 2))
    for offset in (0.0, 4.0, 8.0, -2.0):
        lib.select_only([bpy.data.objects["Suzanne"]])
        stack = bpy.data.objects["Suzanne"].splitforge_stack
        stack.cuts.clear()
        lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z', offset_mm=offset)
        lib.run_op(bpy.ops.splitforge.build)
        parts = [o for o in bpy.data.objects if o.get("splitforge_source") == "Suzanne"]
        assert len(parts) == 2, [o.name for o in parts]
        for p in parts:
            assert lib.is_manifold(p), f"offset {offset}: {p.name} not manifold"
        total = sum(lib.volume(p, signed=True) for p in parts)
        lib.assert_close(total, v0, rel=0.001, msg=f"offset {offset}: volume sum")
    # Oblique cut with a gap and connectors
    stack = bpy.data.objects["Suzanne"].splitforge_stack
    stack.cuts.clear()
    lib.select_only([bpy.data.objects["Suzanne"]])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, use_plane=True, origin=(0.0, 0.0, 2.0), normal=(0.3, 0.2, 1.0))
    stack.cuts[0].gap_mm = 0.4
    stack.cuts[0].connector_count = 2
    lib.run_op(bpy.ops.splitforge.connector_add_auto)
    lib.run_op(bpy.ops.splitforge.build)
    parts = [o for o in bpy.data.objects if o.get("splitforge_source") == "Suzanne"]
    assert len(parts) == 2
    for p in parts:
        assert lib.is_manifold(p), f"oblique: {p.name} not manifold"
