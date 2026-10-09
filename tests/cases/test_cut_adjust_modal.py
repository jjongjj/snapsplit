# SPDX-License-Identifier: GPL-3.0-or-later
"""splitforge.cut_adjust_plane modal: no bpy structs kept across events, undo safe.

Modal operators cannot run in background mode, so invoke()/modal() run on a stand-in
instance (tests/lib) with a fake VIEW_3D area. An ``ed.undo`` between events re-reads
the object's ID properties (the stack); every event must write the LIVE cut. Mouse
dragging and the real Ctrl+Z path are covered by the GUI scenario p1_adjust_plane.
"""

import bpy
from mathutils import Vector

import lib


class FakeArea:
    type = 'VIEW_3D'

    def __init__(self):
        self.header = "unset"

    def header_text_set(self, text):
        self.header = text

    def tag_redraw(self):
        pass


def _cached_struct_refs(op):
    bad = []
    for key, value in vars(op).items():
        for v in (value if isinstance(value, (list, tuple)) else [value]):
            if isinstance(v, bpy.types.bpy_struct) and not isinstance(v, bpy.types.ID):
                bad.append((key, type(v).__name__))
    return bad


def _cut():
    return bpy.data.objects["AdjCube"].splitforge_stack.cuts[0]


def _new_op(module, ctx):
    cls = module.SPLITFORGE_OT_cut_adjust_plane
    op, reports = lib.stand_in(cls)
    op.index, op.origin, op.normal = -1, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)
    assert cls.invoke(op, ctx, lib.ModalEvent('NONE')) == {'RUNNING_MODAL'}
    assert not _cached_struct_refs(op), _cached_struct_refs(op)
    return cls, op, reports


def run(ctx):
    module = ctx.module("ops.ops_cut_plane")
    lib.set_scene_mm()
    bpy.context.preferences.edit.undo_steps = 64
    cube = lib.make_cube(40.0)
    cube.name = "AdjCube"
    lib.select_only([cube])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    bpy.ops.ed.undo_push(message="base")
    _cut().gap_mm = 0.5
    bpy.ops.ed.undo_push(message="gap")

    area = FakeArea()
    mctx = lib._Context(window_manager=lib._WindowManager(), area=area, region=None, region_data=None)
    cls, op, reports = _new_op(module, mctx)
    assert "Cut offset" in area.header

    before = _cut().as_pointer()
    bpy.ops.ed.undo()
    assert _cut().as_pointer() != before, "undo did not re-read the stack; test not meaningful"
    assert _cut().gap_mm == 0.0
    # Wheel: +1 mm, Ctrl+wheel: +0.1 mm, written to the live cut
    assert cls.modal(op, mctx, lib.ModalEvent('WHEELUPMOUSE')) == {'RUNNING_MODAL'}
    lib.assert_close(_cut().origin[2], 1.0, abs_=1e-6, msg="wheel step")
    fine = lib.ModalEvent('WHEELUPMOUSE')
    fine.ctrl = True
    cls.modal(op, mctx, fine)
    lib.assert_close(_cut().origin[2], 1.1, abs_=1e-6, msg="fine wheel step")
    # X re-orients around the current plane point
    cls.modal(op, mctx, lib.ModalEvent('X'))
    assert tuple(round(x, 6) for x in _cut().normal) == (1.0, 0.0, 0.0), tuple(_cut().normal)
    lib.assert_close(_cut().origin[2], 1.1, abs_=1e-6)
    assert not _cached_struct_refs(op)
    # Esc restores the plane the modal started with
    assert cls.modal(op, mctx, lib.ModalEvent('ESC')) == {'CANCELLED'}
    assert tuple(_cut().origin) == (0.0, 0.0, 0.0) and tuple(round(x, 6) for x in _cut().normal) == (0, 0, 1)
    assert area.header is None
    assert any("cancelled" in m for _lvl, m in reports), reports

    # Confirm keeps the new plane and records it on the operator (redo panel)
    cls, op, reports = _new_op(module, mctx)
    cls.modal(op, mctx, lib.ModalEvent('WHEELDOWNMOUSE'))
    cls.modal(op, mctx, lib.ModalEvent('WHEELDOWNMOUSE'))
    assert cls.modal(op, mctx, lib.ModalEvent('RET')) == {'FINISHED'}
    lib.assert_close(_cut().origin[2], -2.0, abs_=1e-6)
    lib.assert_close(op.origin[2], -2.0, abs_=1e-6)

    # Cut removed (undo / script) while running: the modal ends cleanly
    cls, op, reports = _new_op(module, mctx)
    bpy.data.objects["AdjCube"].splitforge_stack.cuts.clear()
    assert cls.modal(op, mctx, lib.ModalEvent('WHEELUPMOUSE')) == {'CANCELLED'}
    # cancel() (file load) only clears the header, never writes into the new file
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    cls, op, reports = _new_op(module, mctx)
    cls.modal(op, mctx, lib.ModalEvent('WHEELUPMOUSE'))
    bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
    cls.cancel(op, mctx)
    assert area.header is None
    # No viewport: invoke falls back to execute with explicit origin/normal
    lib.set_scene_mm()
    cube = lib.make_cube(40.0)
    cube.name = "AdjCube"
    lib.select_only([cube])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    op, _r = lib.stand_in(module.SPLITFORGE_OT_cut_adjust_plane)
    op.index, op.origin, op.normal = 0, Vector((0, 0, 3)), Vector((0, 1, 0))
    assert module.SPLITFORGE_OT_cut_adjust_plane.invoke(op, lib.modal_context(), lib.ModalEvent('NONE')) == {'FINISHED'}
    assert tuple(_cut().origin) == (0, 0, 3) and tuple(round(x, 6) for x in _cut().normal) == (0, 1, 0)
