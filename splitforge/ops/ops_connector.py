# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# ops/ops_connector.py
"""Connector record operators for the active cut: auto distribution, add one, remove."""

import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty
from bpy.types import Operator

from ..connectors import auto
from ..cuts import build
from ..core import naming
from ..model import stack as stack_api


def _settings(context):
    return getattr(context.scene, naming.SCENE_SETTINGS)


class _CutOp:
    bl_options = {'REGISTER', 'UNDO'}

    cut_index: IntProperty(name="Cut", default=-1, min=-1, description="Cut index (-1 = active cut)")

    @classmethod
    def poll(cls, context):
        stack = stack_api.get_stack(stack_api.context_owner(context))
        return stack is not None and len(stack.cuts) > 0

    def _cut(self, obj):
        stack = stack_api.get_stack(obj)
        index = stack.active_index if self.cut_index < 0 else self.cut_index
        if not 0 <= index < len(stack.cuts):
            self.report({'ERROR'}, f"No cut at index {self.cut_index}")
            return None
        return stack.cuts[index]


class SPLITFORGE_OT_connector_add_auto(_CutOp, Operator):
    """Distribute connectors over the seam of the cut (Line or Grid), using the new-connector settings"""
    bl_idname = naming.op("connector_add_auto")
    bl_label = "Auto Connectors"

    replace: BoolProperty(name="Replace", default=True, description="Remove the cut's existing connectors")

    def execute(self, context):
        obj = stack_api.context_owner(context)
        cut = self._cut(obj)
        if cut is None:
            return {'CANCELLED'}
        s = _settings(context)
        try:
            res = auto.add_auto(context, obj, cut, s.new_connector_kind, s.new_connector_width_mm,
                                s.new_connector_height_mm, s.new_connector_length_mm, self.replace)
        except build.BuildError as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        if res.dropped:
            self.report({'WARNING'}, f"{res.dropped} position(s) dropped: {res.describe()} "
                                     "(a smaller connector or fewer per seam may fit)")
        if not res.added:
            self.report({'WARNING'}, "No connector fits on this cut (or it does not cross the object)")
            return {'CANCELLED'}
        moved = f", {res.moved} moved inward to fit" if res.moved else ""
        self.report({'INFO'}, f"{res.added} connector(s) on {cut.name}{moved}")
        return {'FINISHED'}


class SPLITFORGE_OT_connector_add(_CutOp, Operator):
    """Add one connector at (U, V) on the seam of the cut"""
    bl_idname = naming.op("connector_add")
    bl_label = "Add Connector"

    u: FloatProperty(name="U (mm)", default=0.0)
    v: FloatProperty(name="V (mm)", default=0.0)

    def execute(self, context):
        obj = stack_api.context_owner(context)
        cut = self._cut(obj)
        if cut is None:
            return {'CANCELLED'}
        s = _settings(context)
        c = cut.connectors.add()
        c.kind = s.new_connector_kind
        c.u, c.v = self.u, self.v
        c.width_mm, c.height_mm, c.length_mm = (s.new_connector_width_mm, s.new_connector_height_mm,
                                                s.new_connector_length_mm)
        cut.active_connector = len(cut.connectors) - 1
        return {'FINISHED'}


class SPLITFORGE_OT_connector_remove(_CutOp, Operator):
    """Remove a connector from the cut"""
    bl_idname = naming.op("connector_remove")
    bl_label = "Remove Connector"

    index: IntProperty(name="Connector", default=-1, min=-1, description="-1 = active connector")

    def execute(self, context):
        obj = stack_api.context_owner(context)
        cut = self._cut(obj)
        if cut is None:
            return {'CANCELLED'}
        index = cut.active_connector if self.index < 0 else self.index
        if not 0 <= index < len(cut.connectors):
            self.report({'ERROR'}, "No connector to remove")
            return {'CANCELLED'}
        cut.connectors.remove(index)
        cut.active_connector = max(0, min(cut.active_connector, len(cut.connectors) - 1))
        return {'FINISHED'}


classes = (
    SPLITFORGE_OT_connector_add_auto,
    SPLITFORGE_OT_connector_add,
    SPLITFORGE_OT_connector_remove,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
