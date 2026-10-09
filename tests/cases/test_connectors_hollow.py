# SPDX-License-Identifier: GPL-3.0-or-later
"""D8 + Distribute reporting: hollow parts, dropped counts and reasons.

- 40 mm hollow box with 8 mm walls, Z cut, default Distribute (LINE 2, margin 15 %):
  the line targets (u = +-14) fall 2 mm from the cavity, too close for a 5 mm pin;
  the sideways search moves them into the middle of the wall (u = +-16). GRID 5x5
  also finds wall positions. Build applies them (manifold, volumes change).
- Dropped counts include positions rejected in 2D (no room at all): 8 pins asked on a
  thin-walled box -> added + dropped == 8 per region, reason "no room".
- The warning names the real reason: on the steep cross-cut repro (D7) the dropped
  positions are counted as "would reach across another cut", and the Distribute
  operator's warning says so (not "break through the surface").
"""

import bpy

import lib


def run(ctx):
    build = ctx.module("cuts.build")
    auto = ctx.module("connectors.auto")
    placement = ctx.module("connectors.placement")
    ops = ctx.module("ops.ops_connector")
    lib.set_scene_mm()
    scene = bpy.context.scene

    # --- 8 mm walls: LINE finds the wall ------------------------------------------------------
    box = lib.make_hollow_box(40.0, 8.0)
    box.name = "Hollow8"
    lib.select_only([box])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    cut = box.splitforge_stack.cuts[0]
    res = auto.add_auto(bpy.context, box, cut, 'CYL_PIN', 5.0, 5.0, 10.0)
    ctx.metric("line", f"{res.added}/{res.moved}/{res.dropped}")
    assert res.added == 2 and res.dropped == 0, res
    for c in cut.connectors:
        assert 14.5 < abs(c.u) < 17.5 or 14.5 < abs(c.v) < 17.5, (c.u, c.v)   # in the wall (12..20)
    result = build.build(bpy.context, box)
    assert not result.warnings, result.warnings
    parts = [bpy.data.objects[n] for n in result.parts]
    assert len(parts) == 2 and all(lib.is_manifold(p) for p in parts)
    with_pins = sorted(lib.volume(p) for p in parts)
    for c in cut.connectors:
        c.enabled = False
    lib.select_only([box])
    box.hide_set(False)
    plain = sorted(lib.volume(bpy.data.objects[n]) for n in build.build(bpy.context, box).parts)
    assert with_pins[0] < plain[0] - 10.0 and with_pins[1] > plain[1] + 10.0, (with_pins, plain)

    # GRID 5x5 on the same seam: wall positions only
    cut.distribution = 'GRID'
    cut.connector_count, cut.connector_rows = 5, 5
    res = auto.add_auto(bpy.context, box, cut, 'CYL_PIN', 5.0, 5.0, 10.0)
    ctx.metric("grid", f"{res.added}/{res.moved}/{res.dropped}")
    assert res.added >= 4, res
    for c in cut.connectors:
        assert max(abs(c.u), abs(c.v)) > 12.0 + 2.5, (c.u, c.v)

    # The 2D search alone (pure function): targets inside the hole move into the wall
    outer = [(-20, -20), (20, -20), (20, 20), (-20, 20)]
    hole = [(-12, -12), (-12, 12), (12, 12), (12, -12)]
    rejected = []
    pts = placement.distribute_points([outer, hole], 'LINE', 2, 2, 15.0, 3.1, rejected)
    assert len(pts) == 2 and not rejected and all(abs(abs(p[0]) - 16.0) < 0.5 for p in pts), pts

    # --- dropped counts include 2D rejects -------------------------------------------------
    thin = lib.make_hollow_box(40.0, 3.0)
    thin.name = "Thin3"
    lib.select_only([thin])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    tcut = thin.splitforge_stack.cuts[0]
    tcut.connector_count = 8
    res = auto.add_auto(bpy.context, thin, tcut, 'CYL_PIN', 5.0, 5.0, 10.0)
    ctx.metric("thin", f"{res.added}/{res.moved}/{res.dropped} {res.describe()}")
    assert res.added == 0 and res.dropped == 8 and res.reasons["edge"] == 8, res
    assert "no room" in res.describe()
    rejected = []
    assert placement.distribute_points([outer, [(-18.5, -18.5), (-18.5, 18.5), (18.5, 18.5), (18.5, -18.5)]],
                                       'LINE', 3, 2, 15.0, 3.1, rejected) == []
    assert len(rejected) == 3

    # --- reason text: other cut, not surface (steep D7 repro) ------------------------------
    cube = lib.make_cube(40.0)
    cube.name = "Steep"
    lib.select_only([cube])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z', offset_mm=-6.0)
    lib.run_op(bpy.ops.splitforge.stack_add_plane, use_plane=True, origin=(0.0, 0.0, 2.0), normal=(1.0, 0.2, 1.2))
    stack = cube.splitforge_stack
    stack.cuts[1].gap_mm = 0.5
    stack.active_index = 0
    res = auto.add_auto(bpy.context, cube, stack.cuts[0], 'CYL_PIN', 5.0, 5.0, 10.0)
    ctx.metric("steep", f"{res.added}/{res.moved}/{res.dropped} {res.describe()}")
    assert res.dropped >= 1 and res.reasons["other cut"] >= 1, res
    assert "reach across another cut" in res.describe()
    # The operator reports it
    op, reports = lib.stand_in(ops.SPLITFORGE_OT_connector_add_auto)
    op.cut_index, op.replace = 0, True
    assert ops.SPLITFORGE_OT_connector_add_auto.execute(op, bpy.context) == {'FINISHED'}
    warnings = [m for level, m in reports if 'WARNING' in level]
    assert any("reach across another cut" in m for m in warnings), reports
    assert not any("break through" in m for m in warnings if "reach across" not in m), reports
