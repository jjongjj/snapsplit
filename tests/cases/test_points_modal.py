# SPDX-License-Identifier: GPL-3.0-or-later
"""P4-1/P4-2 (headless part): the click modal of splitforge.stack_add_polyline / stack_add_polygon.

Stand-in operator (tests/lib) with a fake VIEW_3D area/region and a synthetic front orthographic
view: LMB clicks add points on the plane through the object center (stored in object space,
direction = view direction), a rubber band follows the mouse (MOUSEMOVE passes through), Ctrl
snaps the new segment to 15 degree steps on screen, Backspace and Ctrl+Z remove the last point,
Enter confirms (polyline >= 2 points, polygon >= 3), clicking the first point closes a polygon,
invalid points are refused at Enter with the reason (no cut, modal keeps running), Esc/RMB leave
nothing and remove the draw handler, ``ed.undo`` between events is harmless (no bpy structs kept),
the object vanishing or ``cancel()`` end the modal cleanly, view navigation passes through, a
second modal is refused, redraw keeps uid/connectors, and the points are kept as clicked (no
smoothing). The real mouse path runs in tests/gui (p4_points).
"""

import math
import os
import sys

import bpy

import lib

sys.path.insert(0, os.path.dirname(__file__))
from test_stroke_modal import FakeArea, FakePoints, struct_refs  # noqa: E402


def event(type_, value='PRESS', xy=(0, 0), ctrl=False, shift=False, alt=False):
    e = lib.ModalEvent(type_, value)
    e.mouse_region_x, e.mouse_region_y = int(round(xy[0])), int(round(xy[1]))
    e.ctrl, e.shift, e.alt = ctrl, shift, alt
    return e


def run(ctx):
    module = ctx.module("ops.ops_cut_points")
    polyline = ctx.module("cuts.polyline")
    lib.set_scene_mm()
    bpy.context.preferences.edit.undo_steps = 64
    cube = lib.make_cube(40.0)
    cube.name = "PtCube"
    cube.location = (5.0, 0.0, 0.0)
    lib.select_only([cube])
    bpy.ops.ed.undo_push(message="base")
    cube["tag"] = 1
    bpy.ops.ed.undo_push(message="tag")

    view = lib.front_view(scale=0.1, center=(5.0, 0.0, 0.0))
    area = FakeArea()
    mctx = lib._Context(window_manager=lib._WindowManager(), area=area, region=view.region, region_data=view)

    def screen(x, z):
        return tuple(view.to_region((x, 0.0, z)))

    def new_op(cls, kind, replace_uid="", depth=-1.0):
        op, reports = lib.stand_in(cls)
        op.KIND, op.MIN_POINTS = kind, (3 if kind == 'POLYGON' else 2)
        op.points, op.direction, op.replace_uid, op.easy, op.depth_mm = FakePoints(), (0, 1, 0), replace_uid, \
            False, depth
        assert cls.invoke(op, mctx, event('NONE')) == {'RUNNING_MODAL'}
        assert not struct_refs(op), struct_refs(op)
        return op, reports

    def click(cls, op, xy, **kw):
        result = cls.modal(op, mctx, event('LEFTMOUSE', 'PRESS', xy, **kw))
        assert not struct_refs(op), struct_refs(op)
        return result

    pl = module.SPLITFORGE_OT_stack_add_polyline
    pg = module.SPLITFORGE_OT_stack_add_polygon

    # --- polyline: clicks, rubber band, Backspace / Ctrl+Z, undo between events, Enter --------
    op, reports = new_op(pl, 'POLYLINE')
    assert "0 point(s)" in area.header and module._HANDLE is not None and module._RUNNING
    second, _ = lib.stand_in(pl)
    second.replace_uid = ""
    assert pl.invoke(second, mctx, event('NONE')) == {'CANCELLED'}, "a second points modal must be refused"
    targets = [(-25.0, -4.0), (-5.0, 7.0), (10.0, -7.0), (35.0, 3.0)]
    for x, z in targets:
        assert click(pl, op, screen(x, z)) == {'RUNNING_MODAL'}
    assert len(op._world) == 4 and op._valid, (op._world, op._message)
    for (x, z), p in zip(targets, op._world):
        assert abs(p[0] - x) < 0.06 and abs(p[2] - z) < 0.06 and abs(p[1]) < 1e-6, (p, x, z)
    assert pl.modal(op, mctx, event('MOUSEMOVE', 'NOTHING', screen(20.0, 10.0))) == {'PASS_THROUGH'}
    band = module._PREVIEW["lines"][1]
    assert abs(band[2][1][0] - 20.0) < 0.06, band
    assert len(module._PREVIEW["lines"]) >= 5, "the cutter outline stays while the rubber band moves"
    assert pl.modal(op, mctx, event('BACK_SPACE')) == {'RUNNING_MODAL'} and len(op._world) == 3
    assert pl.modal(op, mctx, event('Z', ctrl=True)) == {'RUNNING_MODAL'} and len(op._world) == 2
    for x, z in targets[2:]:
        click(pl, op, screen(x, z))
    assert pl.modal(op, mctx, event('MIDDLEMOUSE')) == {'PASS_THROUGH'}
    bpy.ops.ed.undo()                       # memfile undo re-reads the object's ID properties
    assert "tag" not in bpy.data.objects["PtCube"], "undo did not run; test not meaningful"
    assert pl.modal(op, mctx, event('RET')) == {'FINISHED'}
    cube = bpy.data.objects["PtCube"]
    cut = cube.splitforge_stack.cuts[0]
    assert cut.kind == 'POLYLINE' and len(cut.points) == 4, (cut.kind, len(cut.points))
    for (x, z), p in zip(targets, cut.points):     # object space: the cube sits at x = 5
        assert abs(p.co.x - (x - 5.0)) < 0.06 and abs(p.co.z - z) < 0.06, tuple(p.co)
    assert tuple(round(c, 6) for c in cut.direction) == (0.0, 1.0, 0.0)
    assert module._HANDLE is None and not module._RUNNING and area.header is None
    assert len(op.points) == 4, "redo keeps the clicked points"
    uid = cut.uid

    # --- orbiting between clicks: later clicks land on the plane of the first click's view -------
    from mathutils import Euler
    op, reports = new_op(pl, 'POLYLINE')
    click(pl, op, screen(-30.0, 1.0))
    tilted = lib.FakeView(Euler((math.radians(70.0), 0.0, math.radians(25.0))).to_quaternion(),
                          center=(5.0, 0.0, 0.0), scale=0.1)
    tctx = lib._Context(window_manager=lib._WindowManager(), area=area, region=tilted.region, region_data=tilted)
    assert pl.modal(op, tctx, event('LEFTMOUSE', 'PRESS', tuple(tilted.to_region((30.0, 0.0, -1.0))))) == \
        {'RUNNING_MODAL'}
    p = op._world[-1]
    assert abs(p[0] - 30.0) < 0.06 and abs(p[1]) < 1e-5 and abs(p[2] + 1.0) < 0.06, ("not on the first plane", p)
    assert tuple(round(c, 6) for c in op._dir) == (0.0, 1.0, 0.0), op._dir
    assert pl.modal(op, tctx, event('ESC')) == {'CANCELLED'}

    # --- Ctrl: 15 degree steps on screen --------------------------------------------------------
    a = screen(-25.0, 0.0)
    b = (a[0] + 200.0, a[1] + 61.0)                # 16.96 degrees -> 15
    snapped = polyline.snap_screen(a, b)
    assert abs(math.degrees(math.atan2(snapped[1] - a[1], snapped[0] - a[0])) - 15.0) < 1e-9
    op, reports = new_op(pl, 'POLYLINE')
    click(pl, op, a)
    click(pl, op, b, ctrl=True)
    (x0, _, z0), (x1, _, z1) = op._world
    assert abs(math.degrees(math.atan2(z1 - z0, x1 - x0)) - 15.0) < 0.05, (op._world,)

    # --- invalid: too few points, crossing; Esc / RMB leave nothing ------------------------------
    assert pl.modal(op, mctx, event('BACK_SPACE')) == {'RUNNING_MODAL'}
    assert pl.modal(op, mctx, event('RET')) == {'RUNNING_MODAL'}
    assert any("at least 2 points" in m for _l, m in reports), reports
    for x, z in ((25.0, 0.0), (25.0, 10.0), (0.0, -10.0)):
        click(pl, op, screen(x, z))
    assert not op._valid and "crosses itself" in op._message, op._message
    assert pl.modal(op, mctx, event('RET')) == {'RUNNING_MODAL'}
    assert "crosses itself" in area.header
    assert pl.modal(op, mctx, event('ESC')) == {'CANCELLED'}
    op, reports = new_op(pl, 'POLYLINE')
    click(pl, op, screen(-30.0, 0.0))
    assert pl.modal(op, mctx, event('RIGHTMOUSE')) == {'CANCELLED'}
    assert len(cube.splitforge_stack.cuts) == 1
    assert module._HANDLE is None and not module._RUNNING and not module._PREVIEW["lines"]

    # --- polygon: close by clicking the first point --------------------------------------------
    op, reports = new_op(pg, 'POLYGON', depth=8.0)
    corners = [(-5.0, -10.0), (15.0, -10.0), (15.0, 10.0), (-5.0, 10.0)]
    for x, z in corners:
        click(pg, op, screen(x, z))
    assert op._valid, op._message
    first = screen(*corners[0])
    assert click(pg, op, (first[0] + 3, first[1] - 2)) == {'FINISHED'}, "a click on the first point closes"
    cut = cube.splitforge_stack.cuts[1]
    assert cut.kind == 'POLYGON' and len(cut.points) == 4 and math.isclose(cut.depth_mm, 8.0), \
        (cut.kind, len(cut.points), cut.depth_mm)
    # polygon with two points cannot close; a crossing polygon is refused at Enter
    op, reports = new_op(pg, 'POLYGON')
    click(pg, op, screen(-10.0, -10.0))
    click(pg, op, screen(10.0, 10.0))
    assert pg.modal(op, mctx, event('RET')) == {'RUNNING_MODAL'}
    assert any("at least 3 points" in m for _l, m in reports), reports
    click(pg, op, screen(10.0, -10.0))
    click(pg, op, screen(-10.0, 10.0))
    assert not op._valid and "crosses itself" in op._message, op._message
    assert pg.modal(op, mctx, event('ESC')) == {'CANCELLED'}
    assert len(cube.splitforge_stack.cuts) == 2

    # --- redraw keeps uid and connectors -------------------------------------------------------
    cube.splitforge_stack.cuts[0].connectors.add()
    op, reports = new_op(pl, 'POLYLINE', replace_uid=uid)
    for x, z in ((-30.0, 2.0), (35.0, -2.0)):
        click(pl, op, screen(x, z))
    assert pl.modal(op, mctx, event('SPACE')) == {'FINISHED'}
    cut = cube.splitforge_stack.cuts[0]
    assert cut.uid == uid and len(cut.points) == 2 and len(cut.connectors) == 1
    assert any("redrawn" in m for _l, m in reports), reports
    # redrawing a cut of the other kind is refused
    op, reports = lib.stand_in(pg)
    op.KIND, op.replace_uid = 'POLYGON', uid
    assert pg.invoke(op, mctx, event('NONE')) == {'CANCELLED'}

    # --- the object vanishes; cancel() --------------------------------------------------------
    op, reports = new_op(pl, 'POLYLINE')
    click(pl, op, screen(-30.0, 0.0))
    bpy.data.objects["PtCube"].name = "PtRenamed"
    assert pl.modal(op, mctx, event('MOUSEMOVE', 'NOTHING', screen(0.0, 0.0))) == {'CANCELLED'}
    assert module._HANDLE is None and not module._RUNNING
    bpy.data.objects["PtRenamed"].name = "PtCube"
    op, reports = new_op(pg, 'POLYGON')
    click(pg, op, screen(-10.0, -10.0))
    bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
    pg.cancel(op, mctx)
    assert module._HANDLE is None and not module._RUNNING and area.header is None

    # --- no viewport: invoke runs execute with the given points ---------------------------------
    lib.set_scene_mm()
    cube = lib.make_cube(40.0)
    lib.select_only([cube])
    op, reports = lib.stand_in(pg)
    pts = FakePoints()
    for co in ((-8.0, -8.0, 30.0), (8.0, -8.0, 30.0), (8.0, 8.0, 30.0)):
        pts.add().co = co
    op.KIND, op.MIN_POINTS = 'POLYGON', 3
    op.points, op.direction, op.replace_uid, op.easy, op.depth_mm = pts, (0, 0, -1), "", False, 4.0
    assert pg.invoke(op, lib.modal_context(), event('NONE')) == {'FINISHED'}, reports
    assert cube.splitforge_stack.cuts[0].kind == 'POLYGON'
