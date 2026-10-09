# SPDX-License-Identifier: GPL-3.0-or-later
"""P2-4 (headless part): splitforge.stack_add_stroke modal, undo safety.

Modal operators cannot run in background mode, so invoke()/modal() run on a stand-in
(tests/lib) with a fake VIEW_3D area, a fake region and a synthetic front orthographic
view (FakeView). Checks: LMB drag + release validates the stroke and shows the ribbon
preview (plain data, drawn only in the starting region), Enter adds a STROKE cut
(object-local points, direction along the view), ``ed.undo`` between events is
harmless (nothing but names and tuples kept), Esc/RMB leave nothing (no cut, draw
handler removed), Shift-release snaps to a straight axis line, an invalid stroke is
refused at Enter with a message, Redraw replaces the points of an existing cut and
keeps its uid/connectors, the object vanishing or cancel() end it cleanly, view
navigation passes through. The real mouse/keyboard path runs in tests/gui (p2_stroke).
"""

import math

import bpy

import lib


class FakeArea:
    type = 'VIEW_3D'

    def __init__(self):
        self.header = "unset"

    def header_text_set(self, text):
        self.header = text

    def tag_redraw(self):
        pass


class FakePoints(list):
    def add(self):
        class P:
            co = (0.0, 0.0, 0.0)
        self.append(P())
        return self[-1]


def struct_refs(op):
    bad = []
    for key, value in vars(op).items():
        for v in (value if isinstance(value, (list, tuple)) else [value]):
            if isinstance(v, bpy.types.bpy_struct) and not isinstance(v, bpy.types.ID):
                bad.append((key, type(v).__name__))
    return bad


def event(type_, value='PRESS', xy=(0, 0), shift=False, alt=False):
    e = lib.ModalEvent(type_, value)
    e.mouse_region_x, e.mouse_region_y = int(round(xy[0])), int(round(xy[1]))
    e.shift, e.alt = shift, alt
    return e


def run(ctx):
    module = ctx.module("ops.ops_cut_stroke")
    cls = module.SPLITFORGE_OT_stack_add_stroke
    lib.set_scene_mm()
    bpy.context.preferences.edit.undo_steps = 64
    cube = lib.make_cube(40.0)
    cube.name = "ModalCube"
    lib.select_only([cube])
    bpy.ops.ed.undo_push(message="base")
    cube["tag"] = 1
    bpy.ops.ed.undo_push(message="tag")

    view = lib.front_view(scale=0.1)
    area = FakeArea()
    mctx = lib._Context(window_manager=lib._WindowManager(), area=area, region=view.region, region_data=view)

    def screen(x, z):
        return tuple(view.to_region((x, 0.0, z)))

    s_curve = [screen(-26.0 + 52.0 * i / 39, 6.0 * math.sin(2 * math.pi * i / 39)) for i in range(40)]

    def new_op(replace_uid=""):
        op, reports = lib.stand_in(cls)
        op.points, op.direction, op.snap, op.replace_uid, op.easy, op.clean = FakePoints(), (0, 1, 0), False, \
            replace_uid, False, True
        assert cls.invoke(op, mctx, event('NONE')) == {'RUNNING_MODAL'}
        assert not struct_refs(op), struct_refs(op)
        return op, reports

    def draw(op, coords, shift=False):
        assert cls.modal(op, mctx, event('LEFTMOUSE', 'PRESS', coords[0])) == {'RUNNING_MODAL'}
        for xy in coords[1:]:
            cls.modal(op, mctx, event('MOUSEMOVE', 'NOTHING', xy))
        assert cls.modal(op, mctx, event('LEFTMOUSE', 'RELEASE', coords[-1], shift=shift)) == {'RUNNING_MODAL'}
        assert not struct_refs(op), struct_refs(op)

    # --- draw, undo between events, Enter ----------------------------------------------
    op, reports = new_op()
    assert "Draw a stroke" in area.header, area.header
    assert module._HANDLE is not None and module._RUNNING
    second, rep2 = lib.stand_in(cls)
    second.replace_uid = ""
    assert cls.invoke(second, mctx, event('NONE')) == {'CANCELLED'}, "a second stroke modal must be refused"
    draw(op, s_curve)
    assert op._valid, (op._message, reports)
    assert "Enter: confirm" in area.header
    lines = module._PREVIEW["lines"]
    assert module._PREVIEW["region"] == view.region.as_pointer() and len(lines) >= 3, len(lines)
    assert cls.modal(op, mctx, event('MIDDLEMOUSE')) == {'PASS_THROUGH'}
    bpy.ops.ed.undo()                       # memfile undo re-reads the object's ID properties
    assert "tag" not in bpy.data.objects["ModalCube"], "undo did not run; test not meaningful"
    assert cls.modal(op, mctx, event('RET')) == {'FINISHED'}
    cube = bpy.data.objects["ModalCube"]
    cuts = cube.splitforge_stack.cuts
    assert len(cuts) == 1 and cuts[0].kind == 'STROKE' and len(cuts[0].points) > 40, (len(cuts), cuts[0].kind)
    assert tuple(round(c, 6) for c in cuts[0].direction) == (0.0, 1.0, 0.0), tuple(cuts[0].direction)
    assert all(abs(p.co.y) < 1e-4 for p in cuts[0].points), "points on the plane through the object center"
    assert module._HANDLE is None and not module._RUNNING and area.header is None
    assert len(op.points) == len(cuts[0].points) and op.clean is False   # redo uses the prepared points
    uid = cuts[0].uid

    # --- Esc / RMB leave nothing -------------------------------------------------------------
    for key in ('ESC', 'RIGHTMOUSE'):
        op, reports = new_op()
        draw(op, s_curve)
        assert cls.modal(op, mctx, event(key)) == {'CANCELLED'}
        assert len(cube.splitforge_stack.cuts) == 1, key
        assert module._HANDLE is None and not module._RUNNING and not module._PREVIEW["lines"]

    # --- Shift at release: straight line snapped to an axis -------------------------------
    op, reports = new_op()
    slanted = [screen(-26.0 + 52.0 * i / 9, -3.0 + 0.8 * i) for i in range(10)]
    draw(op, slanted, shift=True)
    assert op._valid and len(op._world) == 2, op._world
    (x0, _y0, z0), (x1, _y1, z1) = op._world
    assert abs(z1 - z0) < 1e-6 and abs(x1 - x0) > 40.0, op._world
    assert cls.modal(op, mctx, event('NUMPAD_ENTER')) == {'FINISHED'}
    snapped = cube.splitforge_stack.cuts[1]
    assert len(snapped.points) == 2 and abs(abs(snapped.normal[2]) - 1.0) < 1e-6, tuple(snapped.normal)

    # --- invalid stroke: Enter refused with the reason ------------------------------------
    op, reports = new_op()
    loop = [screen(10 * math.cos(a), 10 * math.sin(a)) for a in [i * 0.3 for i in range(25)]]
    draw(op, loop)
    assert not op._valid and "crosses itself" in op._message, op._message
    assert cls.modal(op, mctx, event('RET')) == {'RUNNING_MODAL'}
    assert any("crosses itself" in m for _l, m in reports), reports
    assert "crosses itself" in area.header
    # A stroke beside the object is refused too
    draw(op, [screen(-26.0 + 52.0 * i / 9, 26.0) for i in range(10)])
    assert not op._valid and "does not cross" in op._message, op._message
    assert cls.modal(op, mctx, event('ESC')) == {'CANCELLED'}
    assert len(cube.splitforge_stack.cuts) == 2

    # --- redraw an existing cut: same uid, connectors kept ---------------------------------
    first = cube.splitforge_stack.cuts[0]
    first.connectors.add()
    before = [tuple(p.co) for p in first.points]
    op, reports = new_op(replace_uid=uid)
    assert "Redraw" in area.header
    draw(op, [screen(-26.0 + 52.0 * i / 39, -4.0 + 5.0 * math.sin(math.pi * i / 39)) for i in range(40)])
    assert cls.modal(op, mctx, event('RET')) == {'FINISHED'}
    first = cube.splitforge_stack.cuts[0]
    assert first.uid == uid and len(first.connectors) == 1 and len(cube.splitforge_stack.cuts) == 2
    assert [tuple(p.co) for p in first.points] != before
    assert any("redrawn" in m for _l, m in reports), reports

    # --- the object vanishes while drawing; cancel() ----------------------------------------
    op, reports = new_op()
    cls.modal(op, mctx, event('LEFTMOUSE', 'PRESS', s_curve[0]))
    bpy.data.objects["ModalCube"].name = "Renamed"
    assert cls.modal(op, mctx, event('MOUSEMOVE', 'NOTHING', s_curve[1])) == {'CANCELLED'}
    assert module._HANDLE is None and not module._RUNNING
    bpy.data.objects["Renamed"].name = "ModalCube"
    op, reports = new_op()
    draw(op, s_curve)
    bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
    cls.cancel(op, mctx)
    assert module._HANDLE is None and not module._RUNNING and area.header is None

    # --- no viewport: invoke runs execute with the given points ----------------------------
    lib.set_scene_mm()
    cube = lib.make_cube(40.0)
    lib.select_only([cube])
    op, reports = lib.stand_in(cls)
    pts = FakePoints()
    for x in (-30.0, 30.0):
        pts.add().co = (x, 0.0, 3.0)
    op.points, op.direction, op.snap, op.replace_uid, op.easy, op.clean = pts, (0, 1, 0), False, "", False, True
    assert cls.invoke(op, lib.modal_context(), event('NONE')) == {'FINISHED'}, reports
    assert cube.splitforge_stack.cuts[0].kind == 'STROKE'
