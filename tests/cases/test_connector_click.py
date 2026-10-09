# SPDX-License-Identifier: GPL-3.0-or-later
"""P3-5 (headless part): splitforge.connector_add_click modal, undo safety.

The modal runs on a stand-in with a fake VIEW_3D area and a synthetic top orthographic
view (tests/lib FakeView). Checks: the preview follows the cursor on the seam (plain data,
green inside the object, red outside), LMB places a connector of the new-connector type at
the cursor (u, v within half a pixel), each click is one undo step (ed.undo removes them one
by one, ed.redo brings them back), S flips the pin side for the next clicks, a click outside
the object or where the connector would break through the surface places nothing and says
why, ed.undo between events is harmless (only names and plain data kept), the object
vanishing / cancel() end it cleanly, a curved (stroke) seam is hit through its ribbon
(the placed connector sits where the ray met the ribbon), dowels and an unusable custom
mesh. The real mouse/keyboard path runs in tests/gui (p3_connector_click).
"""

import math

import bpy
from mathutils import Quaternion, Vector

import lib


class FakeArea:
    type = 'VIEW_3D'

    def __init__(self):
        self.header = "unset"

    def header_text_set(self, text):
        self.header = text

    def tag_redraw(self):
        pass


def struct_refs(op):
    bad = []
    for key, value in vars(op).items():
        for v in (value if isinstance(value, (list, tuple)) else [value]):
            if ((isinstance(v, bpy.types.bpy_struct) and not isinstance(v, bpy.types.ID))
                    or isinstance(v, (FakeArea, lib.FakeRegion, lib.FakeView))):
                bad.append((key, type(v).__name__))
    return bad


def event(type_, value='PRESS', xy=(0, 0)):
    e = lib.ModalEvent(type_, value)
    e.mouse_region_x, e.mouse_region_y = int(round(xy[0])), int(round(xy[1]))
    return e


def run(ctx):
    module = ctx.module("ops.ops_connector_click")
    cls = module.SPLITFORGE_OT_connector_add_click
    lib.set_scene_mm()
    bpy.context.preferences.edit.undo_steps = 64
    cube = lib.make_cube(40.0)
    cube.name = "ClickCube"
    lib.select_only([cube])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    bpy.context.scene.splitforge.new_connector.kind = 'CYL_PIN'
    bpy.ops.ed.undo_push(message="cut")

    view = lib.FakeView(Quaternion(), center=(0.0, 0.0, 0.0), scale=0.1)   # top view, looking down -Z
    area = FakeArea()
    mctx = lib._Context(window_manager=lib._WindowManager(), area=area, region=view.region, region_data=view)

    def screen(x, y, z=0.0):
        return tuple(view.to_region((x, y, z)))

    def conns():
        return bpy.data.objects["ClickCube"].splitforge_stack.cuts[0].connectors

    def new_op(at=(0.0, 0.0)):
        op, reports = lib.stand_in(cls)
        assert cls.invoke(op, mctx, event('MOUSEMOVE', 'NOTHING', screen(*at))) == {'RUNNING_MODAL'}, reports
        assert not struct_refs(op), struct_refs(op)
        return op, reports

    # --- preview follows the cursor ----------------------------------------------------------
    op, reports = new_op((5.0, 3.0))
    assert module._HANDLE is not None and module._RUNNING
    assert module._PREVIEW["lines"] and module._PREVIEW["color"] == module.FIT_COLOR
    first = [Vector(p) for p in module._PREVIEW["lines"]]
    assert cls.modal(op, mctx, event('MOUSEMOVE', 'NOTHING', screen(10.0, -4.0))) == {'PASS_THROUGH'}
    moved = [Vector(p) for p in module._PREVIEW["lines"]]
    shift = sum(moved, Vector()) / len(moved) - sum(first, Vector()) / len(first)
    assert (shift - Vector((5.0, -7.0, 0.0))).length < 0.15, shift
    assert "U 10.0" in area.header and "pin side A" in area.header, area.header
    cls.modal(op, mctx, event('MOUSEMOVE', 'NOTHING', screen(30.0, 0.0)))
    assert module._PREVIEW["color"] == module.MISS_COLOR, "outside the object: red"

    # --- clicks: one connector and one undo step each; S flips the pin side --------------------
    clicks = [(10.0, -4.0), (-8.0, 6.0), (2.0, 12.0)]
    for i, (x, y) in enumerate(clicks):
        if i == 2:
            assert cls.modal(op, mctx, event('S')) == {'RUNNING_MODAL'}
            assert "pin side B" in area.header
        assert cls.modal(op, mctx, event('LEFTMOUSE', 'PRESS', screen(x, y))) == {'RUNNING_MODAL'}
        assert len(conns()) == i + 1, (i, op._message)
        c = conns()[i]
        assert abs(c.u - x) < 0.051 and abs(c.v - y) < 0.051, (c.u, c.v)
        assert c.kind == 'CYL_PIN' and c.pin_side == ('B' if i == 2 else 'A')
        assert not struct_refs(op), struct_refs(op)
    # Outside the object / at the edge: nothing placed, reason in the header
    cls.modal(op, mctx, event('LEFTMOUSE', 'PRESS', screen(30.0, 0.0)))
    assert len(conns()) == 3 and "Outside the object" in area.header, area.header
    cls.modal(op, mctx, event('LEFTMOUSE', 'PRESS', screen(18.6, 0.0)))
    assert len(conns()) == 3 and "break through the surface" in area.header, area.header
    assert any("Does not fit here" in m for _l, m in reports), reports
    # Navigation and modified keys pass through: Ctrl+Z, Ctrl+S (no pin-side flip), Alt+LMB (no placement)
    assert cls.modal(op, mctx, event('MIDDLEMOUSE')) == {'PASS_THROUGH'}
    for key, mod in (('Z', 'ctrl'), ('S', 'ctrl'), ('S', 'oskey'), ('LEFTMOUSE', 'alt'), ('LEFTMOUSE', 'shift')):
        e = event(key, 'PRESS', screen(-12.0, -12.0))
        setattr(e, mod, True)
        assert cls.modal(op, mctx, e) == {'PASS_THROUGH'}, (key, mod)
    assert len(conns()) == 3 and "pin side B" in area.header, (len(conns()), area.header)
    # ed.undo between events (what Ctrl+Z does): one click per step, the modal keeps going
    bpy.ops.ed.undo()
    assert len(conns()) == 2
    assert cls.modal(op, mctx, event('MOUSEMOVE', 'NOTHING', screen(0.0, 0.0))) == {'PASS_THROUGH'}
    bpy.ops.ed.undo()
    assert len(conns()) == 1
    bpy.ops.ed.redo()
    assert len(conns()) == 2
    cls.modal(op, mctx, event('LEFTMOUSE', 'PRESS', screen(-4.0, -12.0)))
    assert len(conns()) == 3 and abs(conns()[2].u + 4.0) < 0.051
    assert cls.modal(op, mctx, event('RET')) == {'FINISHED'}
    assert module._HANDLE is None and not module._RUNNING and area.header is None
    assert any("connector(s) placed" in m for _l, m in reports), reports
    for n in (2, 1, 0):
        bpy.ops.ed.undo()
        assert len(conns()) == n, (n, len(conns()))
    for n in (1, 2, 3):
        bpy.ops.ed.redo()
        assert len(conns()) == n

    # --- object gone / cancel() ----------------------------------------------------------------
    op, reports = new_op()
    bpy.data.objects["ClickCube"].name = "Gone"
    assert cls.modal(op, mctx, event('MOUSEMOVE', 'NOTHING', screen(1.0, 1.0))) == {'CANCELLED'}
    assert module._HANDLE is None and not module._RUNNING
    bpy.data.objects["Gone"].name = "ClickCube"
    op, reports = new_op()
    second, rep2 = lib.stand_in(cls)
    assert cls.invoke(second, mctx, event('NONE')) == {'CANCELLED'}, "a second placement modal is refused"
    cls.cancel(op, mctx)
    assert module._HANDLE is None and not module._RUNNING and area.header is None

    # --- curved seam: the ray hits the ribbon --------------------------------------------------
    scube = lib.make_cube(40.0)
    scube.name = "ClickS"
    scube.location.x = 100.0
    lib.select_only([scube])
    pts = [(100.0 - 26.0 + 52.0 * i / 39, 0.0, 6.0 * math.sin(2 * math.pi * i / 39)) for i in range(40)]
    lib.run_op(bpy.ops.splitforge.stack_add_stroke, points=[{"name": "", "co": p} for p in pts],
               direction=(0.0, 1.0, 0.0))
    view2 = lib.FakeView(Quaternion(), center=(100.0, 0.0, 0.0), scale=0.1)
    mctx2 = lib._Context(window_manager=lib._WindowManager(), area=area, region=view2.region, region_data=view2)
    op, reports = lib.stand_in(cls)
    target = (100.0 - 9.0, 7.0)
    xy = tuple(view2.to_region((target[0], target[1], 0.0)))
    assert cls.invoke(op, mctx2, event('MOUSEMOVE', 'NOTHING', xy)) == {'RUNNING_MODAL'}
    assert cls.modal(op, mctx2, event('LEFTMOUSE', 'PRESS', xy)) == {'RUNNING_MODAL'}
    cut = scube.splitforge_stack.cuts[0]
    assert len(cut.connectors) == 1, (op._message, reports)
    c = cut.connectors[0]
    build = ctx.module("cuts.build")
    m = build.cut_spec(scube, cut, bpy.context.scene).matrix(c.u, c.v, 0.0)
    # The connector center is on the ribbon below the cursor: same x / y as the ray
    assert abs(m.translation.x - target[0]) < 0.1 and abs(m.translation.y - target[1]) < 0.06, m.translation
    assert abs(m.translation.z - 6.0 * math.sin(2 * math.pi * (target[0] - 74.0) / 52.0)) < 0.3, m.translation
    assert cls.modal(op, mctx2, event('ESC')) == {'FINISHED'}
    res = build.build(bpy.context, scube)
    assert not res.warnings and len(res.parts) == 2, res.warnings

    # --- dowel template; unusable custom mesh refuses to start -----------------------------------
    lib.select_only([bpy.data.objects["ClickCube"]])
    settings = bpy.context.scene.splitforge
    settings.new_connector.kind = 'DOWEL'
    op, reports = new_op()
    cls.modal(op, mctx, event('LEFTMOUSE', 'PRESS', screen(0.0, -10.0)))
    assert conns()[-1].kind == 'DOWEL'
    cls.modal(op, mctx, event('ESC'))
    settings.new_connector.kind = 'CUSTOM'
    settings.new_connector.custom_object = None
    op, reports = lib.stand_in(cls)
    assert cls.invoke(op, mctx, event('NONE')) == {'CANCELLED'}
    assert any("custom mesh" in m for _l, m in reports), reports
    assert module._HANDLE is None and not module._RUNNING
