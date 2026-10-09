# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# ops/ops_cut_plane.py
"""Interactive plane adjustment of a stack cut (modal).

Mouse movement slides the plane along its normal, the wheel steps by 1 mm
(Ctrl: 0.1 mm), X/Y/Z align the normal with a world axis, LMB/Enter confirm,
RMB/Esc restore the initial plane. Without a viewport (scripts, redo panel)
``execute`` sets origin/normal directly.

Undo safety: between events only the object NAME, the cut UID and plain
floats are kept; the object and cut are looked up again on every event, and the
operator ends cleanly when they are gone (undo, file load).
"""

import bpy
from bpy.props import FloatVectorProperty, IntProperty
from bpy.types import Operator
from bpy_extras import view3d_utils
from mathutils import Vector

from ..core import log, meshlib, naming, units
from ..cuts import plane
from ..model import stack as stack_api

WHEEL_STEP_MM = 1.0
FINE_STEP_MM = 0.1


def find_cut(obj_name, uid):
    """(object, cut index) for a stored name/uid, or (None, -1)."""
    obj = bpy.data.objects.get(obj_name)
    stack = stack_api.get_stack(obj)
    if stack is None:
        return None, -1
    for i, cut in enumerate(stack.cuts):
        if cut.uid == uid:
            return obj, i
    return None, -1


class SPLITFORGE_OT_cut_adjust_plane(Operator):
    """Move or re-orient a cut plane in the viewport"""
    bl_idname = naming.op("cut_adjust_plane")
    bl_label = "Adjust Cut Plane"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    index: IntProperty(name="Index", default=-1, min=-1, description="Cut index (-1 = active cut)")
    origin: FloatVectorProperty(name="Origin", size=3, subtype='TRANSLATION',
                                description="Point on the plane (object local space)")
    normal: FloatVectorProperty(name="Normal", size=3, default=(0.0, 0.0, 1.0), subtype='DIRECTION',
                                description="Plane normal (object local space)")

    @classmethod
    def poll(cls, context):
        stack = stack_api.get_stack(stack_api.context_owner(context))
        return stack is not None and len(stack.cuts) > 0

    def _target(self, context):
        obj = stack_api.context_owner(context)
        stack = stack_api.get_stack(obj)
        index = stack.active_index if self.index < 0 else self.index
        if not 0 <= index < len(stack.cuts):
            return obj, None
        return obj, stack.cuts[index]

    def execute(self, context):
        obj, cut = self._target(context)
        if cut is None:
            self.report({'ERROR'}, f"No cut at index {self.index}")
            return {'CANCELLED'}
        if Vector(self.normal).length < 1e-9:
            self.report({'ERROR'}, "Normal must not be zero")
            return {'CANCELLED'}
        n, t, _b = meshlib.orthonormal_basis(self.normal, cut.tangent)
        cut.origin = self.origin
        cut.normal = n
        cut.tangent = t
        return {'FINISHED'}

    # --- modal --------------------------------------------------------------

    def invoke(self, context, event):
        if context.area is None or context.area.type != 'VIEW_3D':
            return self.execute(context)
        obj, cut = self._target(context)
        if cut is None:
            self.report({'ERROR'}, "No cut to adjust")
            return {'CANCELLED'}
        self._obj_name = obj.name
        self._uid = cut.uid
        # _start: restored on cancel; _base: plane the mouse/wheel offsets are relative to
        self._start = (tuple(cut.origin), tuple(cut.normal), tuple(cut.tangent))
        self._base = self._start
        self._mouse0 = (event.mouse_region_x, event.mouse_region_y)
        self._offset = 0.0          # BU along the world normal, relative to the initial plane
        self._wheel = 0.0
        context.window_manager.modal_handler_add(self)
        self._header(context)
        return {'RUNNING_MODAL'}

    def _world(self, obj):
        origin, normal, tangent = self._base
        return plane.world_frame(obj.matrix_world, origin, normal, tangent)

    def _header(self, context):
        mm = units.scene_to_mm(self._offset + self._wheel, context.scene)
        if context.area is not None:
            context.area.header_text_set(
                f"Cut offset {mm:+.2f} mm | Mouse: move  Wheel: 1 mm (Ctrl 0.1)  X/Y/Z: axis  "
                f"LMB/Enter: confirm  RMB/Esc: cancel")

    def _pixels_to_offset(self, context, obj, event):
        """Mouse travel projected on the screen direction of the normal -> BU."""
        region, rv3d = context.region, context.region_data
        co, n, _t, _b = self._world(obj)
        size = max(obj.dimensions.length, 1e-6)
        p0 = view3d_utils.location_3d_to_region_2d(region, rv3d, co)
        p1 = view3d_utils.location_3d_to_region_2d(region, rv3d, co + n * size)
        delta = Vector((event.mouse_region_x - self._mouse0[0], event.mouse_region_y - self._mouse0[1]))
        if p0 is None or p1 is None or (p1 - p0).length < 4.0:
            # Normal points at the viewer: vertical mouse travel, one region height = object size
            return delta.y / max(region.height, 1) * size
        axis = p1 - p0
        return delta.dot(axis.normalized()) * size / axis.length

    def _apply(self, context, obj, cut_index, normal_world=None):
        co, n, t, _b = self._world(obj)
        if normal_world is not None:
            n = Vector(normal_world)
            n, t, _b = meshlib.orthonormal_basis(n, t)
        origin, normal, tangent = plane.local_frame(obj.matrix_world, co + n * (self._offset + self._wheel), n, t)
        cut = stack_api.get_stack(obj).cuts[cut_index]
        cut.origin = origin
        cut.normal = normal
        cut.tangent = tangent
        self.origin = origin
        self.normal = normal

    def _done(self, message):
        """Report in the UI and the console (scripted QA reads the console)."""
        self.report({'INFO'}, message)
        log.info(message)

    def _end(self, context):
        if context.area is not None:
            context.area.header_text_set(None)
            context.area.tag_redraw()

    def _restore(self):
        obj, i = find_cut(self._obj_name, self._uid)
        if obj is None:
            return
        cut = stack_api.get_stack(obj).cuts[i]
        cut.origin, cut.normal, cut.tangent = self._start

    def modal(self, context, event):
        obj, i = find_cut(self._obj_name, self._uid)
        if obj is None:
            self._end(context)
            self._done("Adjust cut plane cancelled.")
            return {'CANCELLED'}

        if event.type == 'MOUSEMOVE':
            self._offset = self._pixels_to_offset(context, obj, event)
            self._apply(context, obj, i)
        elif event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.value == 'PRESS':
            step = units.mm_to_scene(FINE_STEP_MM if event.ctrl else WHEEL_STEP_MM, context.scene)
            self._wheel += step if event.type == 'WHEELUPMOUSE' else -step
            self._apply(context, obj, i)
        elif event.type in {'X', 'Y', 'Z'} and event.value == 'PRESS':
            # Re-orient around the current plane point, keeping the travel so far
            co, n, t, _b = self._world(obj)
            new_co = co + n * (self._offset + self._wheel)
            n_new = plane.AXES[event.type]
            self._base = tuple(tuple(v) for v in plane.local_frame(
                obj.matrix_world, new_co, n_new, meshlib.orthonormal_basis(n_new)[1]))
            self._offset = self._wheel = 0.0
            self._mouse0 = (event.mouse_region_x, event.mouse_region_y)
            self._apply(context, obj, i)
        elif event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            self._end(context)
            self._done("Cut plane adjusted.")
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            self._restore()
            self._end(context)
            self._done("Adjust cut plane cancelled.")
            return {'CANCELLED'}
        else:
            # Let view navigation through, swallow everything else
            if event.type == 'MIDDLEMOUSE' or event.type.startswith(("NDOF", "TRACKPAD")):
                return {'PASS_THROUGH'}
            return {'RUNNING_MODAL'}
        self._header(context)
        if context.area is not None:
            context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        """Called by Blender on file load / window close.

        The data may already belong to another file, so nothing is written back.
        """
        self._end(context)
        self._done("Adjust cut plane cancelled.")


classes = (SPLITFORGE_OT_cut_adjust_plane,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
