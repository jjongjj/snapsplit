# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# ops/ops_build.py
"""Build, clear build, Easy cut and mesh validation operators.

Build from the UI runs modal: a timer advances ``cuts.build.build_steps`` one
step (one boolean or plane side) per event, so the cursor progress and the
status bar text update while it works; Esc cancels and leaves the previous
result untouched. Every other event is swallowed (no undo while building),
view navigation passes through. ``execute`` (scripts, headless) builds at once.
Between events the operator keeps the step generator (plain data, the source
object as an ID) and the window manager's timer, nothing else.
"""

import traceback

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty
from bpy.types import Operator

from ..connectors import auto
from ..core import log, naming, units, validate
from ..cuts import build
from ..model import stack as stack_api
from .ops_stack import AXIS_ITEMS

NAVIGATION = {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM',
              'MOUSEROTATE', 'MOUSESMARTZOOM', 'NDOF_MOTION'}


def _report_result(op, result):
    for w in result.warnings:
        op.report({'WARNING'}, w)
    for i in result.infos:
        op.report({'INFO'}, i)
    op.report({'INFO'}, f"Built {len(result.parts)} part(s) in {result.collection}")


class SPLITFORGE_OT_build(Operator):
    """Build the enabled cuts into a result collection (the original object is not modified). With a built part selected, the source object's stack is built. Esc cancels a running build"""
    bl_idname = naming.op("build")
    bl_label = "Build"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        stack = stack_api.get_stack(stack_api.context_owner(context))
        return context.mode == 'OBJECT' and stack is not None and any(c.enabled for c in stack.cuts)

    def execute(self, context):
        obj = stack_api.context_owner(context)
        try:
            result = build.build(context, obj)
        except build.BuildError as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        _report_result(self, result)
        return {'FINISHED'}

    def invoke(self, context, event):
        if bpy.app.background or context.window is None:
            return self.execute(context)
        self._gen = build.build_steps(stack_api.context_owner(context))
        self._timer = context.window_manager.event_timer_add(0.01, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _finish(self, context):
        timer, self._timer = getattr(self, "_timer", None), None
        if timer is not None:
            context.window_manager.event_timer_remove(timer)
        gen, self._gen = getattr(self, "_gen", None), None
        if gen is not None:
            gen.close()

    def modal(self, context, event):
        if event.type == 'ESC' and event.value == 'PRESS':
            self._finish(context)
            self.report({'WARNING'}, "Build cancelled; the previous result is unchanged")
            log.info("Build cancelled.")
            return {'CANCELLED'}
        if event.type in NAVIGATION:
            return {'PASS_THROUGH'}
        if event.type != 'TIMER' or self._gen is None:
            return {'RUNNING_MODAL'}
        try:
            next(self._gen)
        except StopIteration as stop:
            self._gen = None
            self._finish(context)
            _report_result(self, stop.value)
            return {'FINISHED'}
        except build.BuildError as ex:
            self._gen = None
            self._finish(context)
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        except Exception as ex:
            self._gen = None
            self._finish(context)
            log.error("build failed: %s", traceback.format_exc())
            self.report({'ERROR'}, f"Build failed: {ex}")
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        """File load / window close: stop and drop what this build created."""
        self._finish(context)
        log.info("Build cancelled.")


class SPLITFORGE_OT_clear_build(Operator):
    """Delete the built parts and show the original object again"""
    bl_idname = naming.op("clear_build")
    bl_label = "Clear Build"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = stack_api.context_owner(context)
        return context.mode == 'OBJECT' and obj is not None and build.result_collection(obj) is not None

    def execute(self, context):
        removed = build.clear_build(context, stack_api.context_owner(context))
        self.report({'INFO'}, f"Removed {removed} part(s)")
        return {'FINISHED'}


class SPLITFORGE_OT_easy_cut(Operator):
    """Easy mode: add one axis cut (with connectors) to the stack and build immediately"""
    bl_idname = naming.op("easy_cut")
    bl_label = "Easy Cut"
    bl_options = {'REGISTER', 'UNDO'}

    # SKIP_SAVE: invoke() falls back to the scene's Easy settings, not to the last call
    axis: EnumProperty(name="Axis", items=AXIS_ITEMS, default='Z', options={'SKIP_SAVE'})
    offset_mm: FloatProperty(name="Offset (mm)", default=0.0, options={'SKIP_SAVE'},
                             description="Distance from the bounding box center along the axis")
    connector_count: IntProperty(name="Connectors", default=-1, min=-1, max=16,
                                 description="Pins on the seam (-1 = scene setting)")

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and stack_api.context_owner(context) is not None

    def invoke(self, context, event):
        # Panel button: take the Easy settings unless the caller passed explicit values
        s = getattr(context.scene, naming.SCENE_SETTINGS)
        if not self.properties.is_property_set("axis"):
            self.axis = s.easy_axis
        if not self.properties.is_property_set("offset_mm"):
            self.offset_mm = s.easy_offset_mm
        return self.execute(context)

    def execute(self, context):
        obj = stack_api.context_owner(context)
        s = getattr(context.scene, naming.SCENE_SETTINGS)
        count = s.easy_connector_count if self.connector_count < 0 else self.connector_count
        next_uid = stack_api.get_stack(obj).next_uid
        index = stack_api.add_axis_cut(obj, self.axis, units.mm_to_scene(self.offset_mm, context.scene))
        return easy_finish(self, context, obj, index, count, next_uid)


def easy_finish(op, context, obj, index, count, next_uid):
    """Easy mode after adding cut ``index``: Easy gap, connectors along the seam, build.

    On failure the cut is removed again (CANCELLED pushes no undo step, so no
    trace is left). Returns the operator result set.
    """
    s = getattr(context.scene, naming.SCENE_SETTINGS)
    cut = stack_api.get_stack(obj).cuts[index]
    cut.gap_mm = s.easy_gap_mm
    try:
        if count > 0:
            cut.distribution = 'LINE'
            cut.connector_count = count
            res = auto.add_auto(context, obj, cut, template=s.new_connector)
            if res.dropped:
                op.report({'WARNING'}, f"{res.dropped} connector position(s) dropped: {res.describe()}")
        result = build.build(context, obj)
    except build.BuildError as ex:
        stack_api.remove_cut(obj, index)
        stack_api.get_stack(obj).next_uid = next_uid
        op.report({'ERROR'}, str(ex))
        return {'CANCELLED'}
    _report_result(op, result)
    return {'FINISHED'}


class SPLITFORGE_OT_validate(Operator):
    """Check the source mesh for printing: holes and non-manifold edges, loose geometry, normals, duplicate vertices, applied transforms, mm units (results and Fix buttons in the panel)"""
    bl_idname = naming.op("validate")
    bl_label = "Check Mesh"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return stack_api.context_owner(context) is not None

    def execute(self, context):
        rep = validate.validate(stack_api.context_owner(context), context.scene)
        if rep.ok:
            self.report({'INFO'}, "Mesh is ready: closed, normals outward, no duplicates, transforms applied, "
                                  "1 unit = 1 mm")
        for m in rep.messages:
            self.report({'WARNING'}, m)
        return {'FINISHED'}


classes = (
    SPLITFORGE_OT_build,
    SPLITFORGE_OT_clear_build,
    SPLITFORGE_OT_easy_cut,
    SPLITFORGE_OT_validate,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
