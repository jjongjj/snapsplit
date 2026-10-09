# SPDX-License-Identifier: GPL-3.0-or-later
"""Split-preview planes never leave orphan meshes; Adjust Split Axis does not churn them.

Before the fix every preview toggle left the plane meshes behind, and Adjust Split
Axis with "Show split preview" OFF deleted the plane on each offset write (property
update callback) and recreated it in the modal: one orphan mesh per event.
Also: an unexpected error inside the modal ends it through finish() (no plane left).
"""

import bpy

import lib


def _orphans(ops_split):
    return sorted(m.name for m in bpy.data.meshes
                  if m.name.startswith(ops_split.PREVIEW_PLANE_PREFIX) and m.users == 0)


def _planes(ops_split):
    return [o for o in bpy.data.objects if o.name.startswith(ops_split.PREVIEW_PLANE_PREFIX)]


def _adjust_session(ops_split, show_preview, events=20):
    props = bpy.context.scene.snapsplit
    props.show_split_preview = show_preview
    cls = ops_split.SNAP_OT_adjust_split_axis
    op, _reports = lib.stand_in(cls)
    ctx = lib.modal_context()
    assert cls.invoke(op, ctx, lib.ModalEvent('NONE')) == {'RUNNING_MODAL'}
    lead_mesh = bpy.data.objects[op._plane_name].data.name
    meshes_before = len(bpy.data.meshes)
    for i in range(events):
        assert cls.modal(op, ctx, lib.ModalEvent('WHEELUPMOUSE')) == {'RUNNING_MODAL'}
    assert props.split_offset_mm != 0.0
    # Same plane object and mesh all along: no delete/recreate churn
    assert op._plane_name in bpy.data.objects, "lead plane vanished"
    assert bpy.data.objects[op._plane_name].data.name == lead_mesh, "plane was recreated"
    assert len(bpy.data.meshes) == meshes_before, (meshes_before, len(bpy.data.meshes))
    assert not _orphans(ops_split), _orphans(ops_split)
    assert cls.modal(op, ctx, lib.ModalEvent('RET')) == {'FINISHED'}
    assert not _orphans(ops_split), _orphans(ops_split)
    if not show_preview:
        assert not _planes(ops_split), [o.name for o in _planes(ops_split)]
    props.show_split_preview = False
    props.split_offset_mm = 0.0
    assert not _planes(ops_split) and not _orphans(ops_split)


def run(ctx):
    ops_split = ctx.module("ops_split")
    lib.set_scene_mm()
    cube = lib.make_cube(40.0)
    lib.select_only([cube])
    props = bpy.context.scene.snapsplit

    # Toggling and editing the preview settings
    for axis in ('X', 'Y', 'Z'):
        props.split_axis = axis
        for parts in (2, 3, 4):
            props.parts_count = parts
            props.show_split_preview = True
            props.split_offset_mm = 1.5
            props.split_offset_mm = -2.0
            assert len(_planes(ops_split)) == parts - 1
            props.show_split_preview = False
    assert not _planes(ops_split)
    assert not _orphans(ops_split), _orphans(ops_split)
    ctx.metric("toggles", 9)

    _adjust_session(ops_split, show_preview=False)
    _adjust_session(ops_split, show_preview=True)

    # An unexpected error in the modal ends it cleanly through finish()
    cls = ops_split.SNAP_OT_adjust_split_axis
    op, _reports = lib.stand_in(cls)
    mctx = lib.modal_context()
    assert cls.invoke(op, mctx, lib.ModalEvent('NONE')) == {'RUNNING_MODAL'}
    assert _planes(ops_split)
    original = ops_split.build_preview_matrix

    def broken(*_args, **_kwargs):
        raise RuntimeError("simulated failure")

    ops_split.build_preview_matrix = broken
    try:
        assert cls.modal(op, mctx, lib.ModalEvent('WHEELUPMOUSE')) == {'CANCELLED'}
    finally:
        ops_split.build_preview_matrix = original
    assert not _planes(ops_split), [o.name for o in _planes(ops_split)]
    assert not ops_split._ADJUST_RUNNING, "modal still registered as running"
    assert not _orphans(ops_split), _orphans(ops_split)
