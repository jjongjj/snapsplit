# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression: modal operators must not keep bpy struct references across undo.

Blender 5.2 crashed (EXCEPTION_ACCESS_VIOLATION in IDP_GetPropertyFromGroup, read of
0x18) when Adjust Split Axis read ``self.props.split_offset_mm`` after an undo step
had re-read the Scene's ID properties: ``self.props`` (= ``context.scene.snapsplit``,
cached in invoke) pointed to the freed property group. The Scene ID itself keeps its
address, so Python does not invalidate the nested reference.

Modal operators cannot run in background mode, so invoke()/modal() are called on a
stand-in instance carrying the operator class' methods, with a context whose
window manager accepts modal_handler_add(). Between invoke and modal a real
``ed.undo`` re-allocates ``scene.snapsplit``. Before the fix the modal wrote the
new offset into freed memory (the live property stayed 0.0, or Blender crashed);
now every event resolves the scene settings and objects again.

Also covered: the click-connector preview objects (freed by the undo) are kept by
name and rebuilt on the next mouse move, and cancel() - called by Blender on file
load / window close - removes all preview objects. The real GUI path (simulated
input, real file load) is ``python3 tests/run_tests.py --gui``.
"""

import bpy
from mathutils import Vector

import lib


def _cached_struct_refs(op):
    """Non-ID bpy structs stored on the instance (these dangle after undo)."""
    bad = []
    for key, value in vars(op).items():
        values = value if isinstance(value, (list, tuple)) else [value]
        for v in values:
            if isinstance(v, bpy.types.bpy_struct) and not isinstance(v, bpy.types.ID):
                bad.append((key, type(v).__name__))
    return bad


def _undo_reallocating_props():
    """Undo one step that changed scene.snapsplit; returns (before, after) group pointers."""
    before = bpy.context.scene.snapsplit.as_pointer()
    assert bpy.ops.ed.undo.poll(), "ed.undo not available"
    bpy.ops.ed.undo()
    after = bpy.context.scene.snapsplit.as_pointer()
    # Precondition of this regression: the undo really re-allocated the property group
    assert before != after, "undo did not re-allocate scene.snapsplit; test is not meaningful"
    return before, after


def _preview_names():
    """Connector preview objects currently in the file."""
    return sorted(o.name for o in bpy.data.objects if o.name.startswith("SnapSplit_Preview"))


def _push(message):
    bpy.ops.ed.undo_push(message=message)


def _check_adjust_split_axis(ops_split):
    cube = lib.make_cube(40.0)
    cube.name = "UndoSafety_Cube"
    lib.select_only([cube])
    props = bpy.context.scene.snapsplit
    props.split_axis = 'Z'
    props.parts_count = 2
    props.split_offset_mm = 0.0
    _push("adjust: base")
    bpy.context.scene.snapsplit.parts_count = 3
    _push("adjust: settings changed")

    op, _reports = lib.stand_in(ops_split.SNAP_OT_adjust_split_axis)
    ctx = lib.modal_context()
    assert ops_split.SNAP_OT_adjust_split_axis.invoke(op, ctx, lib.ModalEvent('NONE')) == {'RUNNING_MODAL'}
    assert not _cached_struct_refs(op), _cached_struct_refs(op)

    _undo_reallocating_props()
    assert bpy.context.scene.snapsplit.split_offset_mm == 0.0

    # Wheel up moves the plane: must write the LIVE property, not the freed group
    ret = ops_split.SNAP_OT_adjust_split_axis.modal(op, ctx, lib.ModalEvent('WHEELUPMOUSE'))
    assert ret == {'RUNNING_MODAL'}, ret
    live = bpy.context.scene.snapsplit.split_offset_mm
    assert live > 0.0, f"modal wrote to a stale property group (live offset {live})"

    # Mouse move after a second undo/redo cycle keeps working as well
    _push("adjust: moved")
    bpy.context.scene.snapsplit.parts_count = 2
    _push("adjust: settings changed again")
    _undo_reallocating_props()
    before = bpy.context.scene.snapsplit.split_offset_mm
    ret = ops_split.SNAP_OT_adjust_split_axis.modal(op, ctx, lib.ModalEvent('MOUSEMOVE', 'NOTHING', -50, 0))
    assert ret == {'RUNNING_MODAL'}, ret
    assert bpy.context.scene.snapsplit.split_offset_mm != before
    assert not _cached_struct_refs(op), _cached_struct_refs(op)

    # cancel() (file load / window close) cleans up like Esc
    op2, _reports2 = lib.stand_in(ops_split.SNAP_OT_adjust_split_axis)
    assert ops_split.SNAP_OT_adjust_split_axis.invoke(op2, ctx, lib.ModalEvent('NONE')) == {'RUNNING_MODAL'}
    assert any(o.name.startswith(ops_split.PREVIEW_PLANE_PREFIX) for o in bpy.data.objects)
    ops_split.SNAP_OT_adjust_split_axis.cancel(op2, ctx)
    leftovers = [o.name for o in bpy.data.objects if o.name.startswith(ops_split.PREVIEW_PLANE_PREFIX)]
    assert not leftovers, leftovers

    # Object vanished (e.g. undone): the modal ends cleanly instead of raising
    bpy.data.objects.remove(bpy.data.objects["UndoSafety_Cube"])
    ret = ops_split.SNAP_OT_adjust_split_axis.modal(op, ctx, lib.ModalEvent('TIMER', 'NOTHING'))
    assert ret == {'CANCELLED'}, ret
    leftovers = [o.name for o in bpy.data.objects if o.name.startswith(ops_split.PREVIEW_PLANE_PREFIX)]
    assert not leftovers, leftovers


def _check_place_connectors_click(ops_connectors):
    cube = lib.make_cube(40.0)
    lib.select_only([cube])
    props = bpy.context.scene.snapsplit
    props.split_axis = 'Z'
    props.parts_count = 2
    props.connector_type = 'CYL_PIN'
    bpy.ops.snapsplit.planar_split()
    parts = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    assert len(parts) == 2, [o.name for o in parts]
    names = sorted(o.name for o in parts)
    lib.select_only(parts)
    _push("connectors: base")
    bpy.context.scene.snapsplit.pin_length_mm = bpy.context.scene.snapsplit.pin_length_mm + 1.0
    _push("connectors: settings changed")

    cls = ops_connectors.SNAP_OT_place_connectors_click
    op, _reports = lib.stand_in(cls)
    ctx = lib.modal_context()
    assert cls.invoke(op, ctx, lib.ModalEvent('NONE')) == {'RUNNING_MODAL'}
    assert not _cached_struct_refs(op), _cached_struct_refs(op)

    _undo_reallocating_props()
    live = bpy.context.scene.snapsplit
    # Every settings read after the undo goes to the live group
    assert op.props.as_pointer() == live.as_pointer()
    frame = op._build_frame_at(Vector((0.0, 0.0, 0.0)))
    embed = float(live.pin_embed_pct) * 0.01 * float(live.pin_length_mm) * ops_connectors.unit_mm()
    lib.assert_close(frame.translation.length, embed, rel=1e-6, abs_=1e-9,
                     msg="frame built from stale settings")
    assert sorted([op.a.name, op.b.name]) == names

    # The undo freed the preview objects created by invoke(); only names were kept,
    # so nothing dangles and the next mouse move rebuilds the preview
    assert not op.preview_objs and op.preview_obj is None, _preview_names()
    ret = cls.modal(op, ctx, lib.ModalEvent('MOUSEMOVE', 'NOTHING'))
    assert ret == {'RUNNING_MODAL'}, ret
    assert op.preview_obj is not None and op.preview_objs, "preview not rebuilt after undo"
    assert sorted(o.name for o in op.preview_objs) == _preview_names()

    # cancel() (Blender calls it on file load / window close) removes the preview
    cls.cancel(op, ctx)
    assert not _preview_names(), _preview_names()
    assert op.preview_objs == [] and op.preview_obj is None

    # A part vanished: the modal ends cleanly and leaves no preview behind
    op, _reports = lib.stand_in(cls)
    lib.select_only([bpy.data.objects[n] for n in names])
    assert cls.invoke(op, ctx, lib.ModalEvent('NONE')) == {'RUNNING_MODAL'}
    assert _preview_names()
    bpy.data.objects.remove(bpy.data.objects[names[0]])
    ret = cls.modal(op, ctx, lib.ModalEvent('MOUSEMOVE', 'NOTHING'))
    assert ret == {'CANCELLED'}, ret
    assert not _preview_names(), _preview_names()


def run(ctx):
    lib.set_scene_mm()
    bpy.context.preferences.edit.undo_steps = 64
    _check_adjust_split_axis(ctx.module("ops_split"))
    _check_place_connectors_click(ctx.module("ops_connectors"))
