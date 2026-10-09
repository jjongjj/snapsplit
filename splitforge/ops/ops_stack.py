# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# ops/ops_stack.py
"""Cut stack operators: add plane, remove, move, duplicate, clear.

All of them act on the stack owner of the active object (the source object, or
the source of an active built part) and are undoable.
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty
from bpy.types import Operator

from ..core import naming, units
from ..model import stack as stack_api

AXIS_ITEMS = [('X', "X", "Perpendicular to world X"), ('Y', "Y", "Perpendicular to world Y"),
              ('Z', "Z", "Perpendicular to world Z")]


class _StackOp:
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return stack_api.context_owner(context) is not None


class _StackIndexOp(_StackOp):
    index: IntProperty(name="Index", default=-1, min=-1, description="Cut index (-1 = active cut)")

    @classmethod
    def poll(cls, context):
        stack = stack_api.get_stack(stack_api.context_owner(context))
        return stack is not None and len(stack.cuts) > 0

    def _index_ok(self, obj):
        stack = stack_api.get_stack(obj)
        index = stack.active_index if self.index < 0 else self.index
        if not 0 <= index < len(stack.cuts):
            self.report({'ERROR'}, f"No cut at index {self.index}")
            return False
        return True


class SPLITFORGE_OT_stack_add_plane(_StackOp, Operator):
    """Add a planar cut to the stack"""
    bl_idname = naming.op("stack_add_plane")
    bl_label = "Add Plane Cut"

    axis: EnumProperty(name="Axis", items=AXIS_ITEMS, default='Z')
    offset_mm: FloatProperty(name="Offset (mm)", default=0.0,
                             description="Distance from the bounding box center along the axis")
    use_plane: BoolProperty(name="Explicit plane", default=False,
                            description="Use Origin/Normal (object local space) instead of Axis/Offset")
    origin: FloatVectorProperty(name="Origin", size=3, subtype='TRANSLATION')
    normal: FloatVectorProperty(name="Normal", size=3, default=(0.0, 0.0, 1.0), subtype='DIRECTION')

    def execute(self, context):
        obj = stack_api.context_owner(context)
        if self.use_plane:
            if sum(c * c for c in self.normal) < 1e-12:
                self.report({'ERROR'}, "Normal must not be zero")
                return {'CANCELLED'}
            stack_api.add_cut(obj, self.origin, self.normal)
        else:
            stack_api.add_axis_cut(obj, self.axis, units.mm_to_scene(self.offset_mm, context.scene))
        return {'FINISHED'}


class SPLITFORGE_OT_stack_remove(_StackIndexOp, Operator):
    """Remove a cut from the stack"""
    bl_idname = naming.op("stack_remove")
    bl_label = "Remove Cut"

    def execute(self, context):
        obj = stack_api.context_owner(context)
        if not self._index_ok(obj):
            return {'CANCELLED'}
        stack_api.remove_cut(obj, self.index)
        return {'FINISHED'}


class SPLITFORGE_OT_stack_move(_StackIndexOp, Operator):
    """Move a cut up or down (cuts are applied top to bottom)"""
    bl_idname = naming.op("stack_move")
    bl_label = "Move Cut"

    direction: EnumProperty(name="Direction", items=[('UP', "Up", ""), ('DOWN', "Down", "")], default='UP')

    def execute(self, context):
        obj = stack_api.context_owner(context)
        if not self._index_ok(obj):
            return {'CANCELLED'}
        stack_api.move_cut(obj, self.index, self.direction)
        return {'FINISHED'}


class SPLITFORGE_OT_stack_duplicate(_StackIndexOp, Operator):
    """Duplicate a cut with its connectors"""
    bl_idname = naming.op("stack_duplicate")
    bl_label = "Duplicate Cut"

    def execute(self, context):
        obj = stack_api.context_owner(context)
        if not self._index_ok(obj):
            return {'CANCELLED'}
        stack_api.duplicate_cut(obj, self.index)
        return {'FINISHED'}


class SPLITFORGE_OT_stack_clear(_StackIndexOp, Operator):
    """Remove all cuts from the stack"""
    bl_idname = naming.op("stack_clear")
    bl_label = "Clear Stack"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        stack_api.clear(stack_api.context_owner(context))
        return {'FINISHED'}


classes = (
    SPLITFORGE_OT_stack_add_plane,
    SPLITFORGE_OT_stack_remove,
    SPLITFORGE_OT_stack_move,
    SPLITFORGE_OT_stack_duplicate,
    SPLITFORGE_OT_stack_clear,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
