# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# ops/ops_build.py
"""Build, clear build, Easy cut and mesh validation operators."""

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty
from bpy.types import Operator

from ..connectors import auto
from ..core import naming, units, validate
from ..cuts import build
from ..model import stack as stack_api
from .ops_stack import AXIS_ITEMS


def _report_result(op, result):
    for w in result.warnings:
        op.report({'WARNING'}, w)
    op.report({'INFO'}, f"Built {len(result.parts)} part(s) in {result.collection}")


class SPLITFORGE_OT_build(Operator):
    """Build the enabled cuts into a result collection (the original object is not modified). With a built part selected, the source object's stack is built"""
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
        cut = stack_api.get_stack(obj).cuts[index]
        if count > 0:
            cut.distribution = 'LINE'
            cut.connector_count = count
            res = auto.add_auto(context, obj, cut, s.new_connector_kind, s.new_connector_width_mm,
                                s.new_connector_height_mm, s.new_connector_length_mm)
            if res.dropped:
                self.report({'WARNING'}, f"{res.dropped} connector position(s) did not fit and were dropped")
        try:
            result = build.build(context, obj)
        except build.BuildError as ex:
            # CANCELLED pushes no undo step: leave no trace
            stack_api.remove_cut(obj, index)
            stack_api.get_stack(obj).next_uid = next_uid
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        _report_result(self, result)
        return {'FINISHED'}


class SPLITFORGE_OT_validate(Operator):
    """Check the source mesh for printing: manifold, loose geometry, applied transforms, mm units"""
    bl_idname = naming.op("validate")
    bl_label = "Check Mesh"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return stack_api.context_owner(context) is not None

    def execute(self, context):
        rep = validate.validate(stack_api.context_owner(context), context.scene)
        if rep.ok:
            self.report({'INFO'}, "Mesh is ready: manifold, transforms applied, 1 unit = 1 mm")
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
