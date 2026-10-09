# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# ops/ops_connector_click.py
"""Place connectors on the active cut's seam by clicking in the viewport (modal).

The mouse ray is intersected with the seam: the cut plane, the ribbon of a
stroke or polyline cut, or the floor of a polygon cut-out. A preview of the new connector (the scene's new-connector type and
size) follows the cursor, green where the seam lies inside the object, red
elsewhere. LMB places a connector there if it fits in 3D (inside the object
with MIN_WALL_MM of material, not across another cut or its own curved seam,
connectors/fit.py), otherwise the header says why. S flips the pin side for the
next clicks; Enter, Esc or RMB end the placement. Only plain S / LMB are taken:
with Ctrl, Alt, Shift or Cmd held (Ctrl+Z / Ctrl+Shift+Z undo, Ctrl+S save,
Alt+LMB navigation) the event passes through, as does view navigation.

Undo: every placed connector is its own undo step (``ed.undo_push`` after each
click), so Ctrl+Z removes them one by one. The operator therefore has no UNDO
flag (that would add one more, empty step at the end).

Undo safety: between events only the object name, the cut uid, plain tuples and
mathutils trees (rebuilt when their inputs change) are kept; the object and cut
are looked up again on every event, and the operator ends cleanly when they are
gone. The preview is drawn by a gpu handler from module-level plain data.
"""

import bpy
import gpu
from bpy.types import Operator
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import intersect_line_plane

from ..connectors import auto, fit, placement, shapes
from ..core import log, naming, units
from ..cuts import build
from ..cuts.stroke import RIBBON_KINDS
from ..model import stack as stack_api

FIT_COLOR = (0.2, 1.0, 0.35, 1.0)
MISS_COLOR = (1.0, 0.2, 0.15, 1.0)

_PREVIEW = {"region": 0, "lines": [], "color": FIT_COLOR}
_HANDLE = None
_RUNNING = []


def _draw():
    if not _PREVIEW["lines"]:
        return
    region = getattr(bpy.context, "region", None)
    if region is None or region.as_pointer() != _PREVIEW["region"]:
        return
    try:
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')
        shader.bind()
        shader.uniform_float("color", _PREVIEW["color"])
        batch_for_shader(shader, 'LINES', {"pos": _PREVIEW["lines"]}).draw(shader)
        gpu.state.blend_set('NONE')
    except Exception as ex:  # never raise from a draw callback
        log.error("connector preview draw failed: %s", ex)
        _PREVIEW["lines"] = []


def _add_handler():
    global _HANDLE
    if _HANDLE is None:
        _HANDLE = bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_VIEW')


def _remove_handler():
    global _HANDLE
    if _HANDLE is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_HANDLE, 'WINDOW')
        _HANDLE = None
    _PREVIEW["lines"] = []
    _PREVIEW["region"] = 0


def find_cut(obj_name, uid):
    """(object, cut) for a stored name/uid, or (None, None)."""
    obj = bpy.data.objects.get(obj_name)
    stack = stack_api.get_stack(obj)
    for cut in (stack.cuts if stack is not None else ()):
        if cut.uid == uid:
            return obj, cut
    return None, None


def _mesh_key(obj):
    """Cheap fingerprint of the evaluated source (changes after edits/undo that alter it)."""
    me = obj.data
    n = len(me.vertices)
    probe = tuple(tuple(me.vertices[i].co) for i in {0, n // 2, n - 1} if n) if n else ()
    return (me.name, n, len(me.polygons), probe, len(obj.modifiers))


class _Seam:
    """Plain-data seam of a cut for ray hits: spec, ribbon BVH (stroke), source BVH."""

    def __init__(self, context, obj, cut):
        scene = context.scene
        self.spec = build.cut_spec(obj, cut, scene)
        bm = build.source_bmesh(obj, context.evaluated_depsgraph_get())
        try:
            self.source = BVHTree.FromBMesh(bm)
        finally:
            bm.free()
        self.ribbon = None
        if self.spec.kind in RIBBON_KINDS:
            ribbon = self.spec.cutter.ribbon()
            try:
                self.ribbon = BVHTree.FromBMesh(ribbon)
            finally:
                ribbon.free()
        self.f = units.scene_to_mm(1.0, scene)

    @staticmethod
    def key(context, obj, cut):
        return (obj.name, tuple(tuple(r) for r in obj.matrix_world), cut.uid, cut.kind, tuple(cut.origin),
                tuple(cut.normal), tuple(cut.tangent), round(cut.gap_mm, 9), round(cut.depth_mm, 9), tuple(cut.direction),
                hash(tuple(tuple(p.co) for p in cut.points)), _mesh_key(obj),
                round(context.scene.unit_settings.scale_length, 12))

    def hit(self, origin, direction):
        """(world point, u_mm, v_mm, inside the object) where the ray meets the seam, or None."""
        spec = self.spec
        if spec.kind in RIBBON_KINDS:
            p = self.ribbon.ray_cast(origin, direction)[0]
            if p is None:
                return None
            u, v = spec.centerline().uv_of(p)
        else:
            p = intersect_line_plane(origin, origin + direction, spec.co, spec.n)
            if p is None or (p - origin).dot(direction) <= 0.0:
                return None
            u, v = placement.seam_coords(spec.co, spec.n, spec.t, p)
        return p, u * self.f, v * self.f, fit.is_inside(self.source, p)


class SPLITFORGE_OT_connector_add_click(Operator):
    """Click on the seam of the active cut to place connectors (new-connector type and size)"""
    bl_idname = naming.op("connector_add_click")
    bl_label = "Place Connectors"
    # No UNDO flag: each placed connector pushes its own undo step (see the module docstring)
    bl_options = {'REGISTER', 'BLOCKING'}

    @classmethod
    def poll(cls, context):
        return stack_api.active_cut(stack_api.context_owner(context)) is not None

    def invoke(self, context, event):
        if context.area is None or context.area.type != 'VIEW_3D' or context.region_data is None:
            self.report({'ERROR'}, "Run this from the 3D viewport")
            return {'CANCELLED'}
        if _RUNNING:
            self.report({'WARNING'}, "Connector placement is already running")
            return {'CANCELLED'}
        obj = stack_api.context_owner(context)
        cut = stack_api.active_cut(obj)
        s = getattr(context.scene, naming.SCENE_SETTINGS)
        if s.new_connector.kind == 'CUSTOM':
            shape, why = build.custom_shape_of(s.new_connector.custom_object, context.evaluated_depsgraph_get())
            if shape is None:
                self.report({'ERROR'}, why[:1].upper() + why[1:])
                return {'CANCELLED'}
        try:
            no_floor = auto.through_polygon_message(build.cut_spec(obj, cut, context.scene))
        except build.BuildError as ex:
            no_floor = str(ex)
        if no_floor:
            self.report({'ERROR'}, no_floor)
            return {'CANCELLED'}
        self._obj_name = obj.name
        self._uid = cut.uid
        self._side = s.new_connector.pin_side
        self._placed = 0
        self._message = ""
        self._seam = None
        self._seam_key = None
        self._last = None          # (u_mm, v_mm, inside) under the cursor
        _RUNNING.append(True)
        _PREVIEW["region"] = context.region.as_pointer()
        _PREVIEW["lines"] = []
        _add_handler()
        context.window_manager.modal_handler_add(self)
        self._update(context, obj, cut, event)
        return {'RUNNING_MODAL'}

    # --- helpers ------------------------------------------------------------

    def _seam_for(self, context, obj, cut):
        key = _Seam.key(context, obj, cut)
        if key != self._seam_key:
            self._seam, self._seam_key = _Seam(context, obj, cut), key
        return self._seam

    def _header(self, context, cut):
        if context.area is None:
            return
        where = ""
        if self._last is not None:
            where = f"U {self._last[0]:.1f}  V {self._last[1]:.1f} mm | "
        text = (f"Place connectors on {cut.name}: {where}pin side {self._side} | LMB: place  S: pin side  "
                f"Enter/Esc/RMB: done ({self._placed} placed)")
        if self._message:
            text = f"{self._message} | {text}"
        context.area.header_text_set(text)

    def _update(self, context, obj, cut, event):
        """Ray under the mouse -> seam position and preview."""
        region, rv3d = context.region, context.region_data
        co = Vector((event.mouse_region_x, event.mouse_region_y))
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, co)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, co).normalized()
        try:
            hit = self._seam_for(context, obj, cut).hit(origin, direction)
        except build.BuildError as ex:
            self._message, hit = str(ex), None
        if hit is None:
            self._last = None
            _PREVIEW["lines"] = []
        else:
            p, u, v, inside = hit
            self._last = (u, v, inside)
            t = getattr(context.scene, naming.SCENE_SETTINGS).new_connector
            mm = units.mm_to_scene(1.0, context.scene)
            m = self._seam.spec.matrix(u * mm, v * mm, t.rotation_deg)
            outline = [m @ Vector((x, y, 0.0)) for x, y in shapes.seam_outline(t.kind, t.width_mm * mm,
                                                                                  t.height_mm * mm)]
            lines = []
            for i, a in enumerate(outline):
                lines += [tuple(a), tuple(outline[(i + 1) % len(outline)])]
            sides = (1.0, -1.0) if t.kind == 'DOWEL' else ((1.0 if self._side == 'A' else -1.0),)
            for side in sides:
                lines += [tuple(m.translation), tuple(m @ Vector((0.0, 0.0, side * t.length_mm * mm * 0.5)))]
            _PREVIEW["lines"] = lines
            _PREVIEW["color"] = FIT_COLOR if inside else MISS_COLOR
        self._header(context, cut)
        if context.area is not None:
            context.area.tag_redraw()

    def place(self, context, obj, cut, u, v):
        """Add a connector at (u, v) mm if it fits; one undo step. Returns '' or the reason it does not fit."""
        scene = context.scene
        s = getattr(scene, naming.SCENE_SETTINGS)
        t = s.new_connector
        seam = self._seam_for(context, obj, cut)
        stack = stack_api.get_stack(obj)
        others = [o.barrier() for o in build.cut_specs(
            obj, [c for c in stack.cuts if c.enabled and c.uid != cut.uid], scene)]
        own = seam.spec.barrier() if seam.spec.kind != 'PLANE' else None
        custom = None
        if t.kind == 'CUSTOM':
            custom, why = build.custom_shape_of(t.custom_object, context.evaluated_depsgraph_get())
            if custom is None:
                return why
        values = build.connector_values(t)
        clearance = t.clearance_mm if t.clearance_mm >= 0.0 else build.default_clearance(s)
        spec = build.make_spec(obj, cut, scene, "", u, v, t.rotation_deg, values.pop("kind"),
                               values.pop("width_mm"), values.pop("height_mm"), values.pop("length_mm"),
                               clearance, self._side, seam.spec, custom=custom, **values)
        wall = units.mm_to_scene(auto.MIN_WALL_MM, scene)
        reason = fit.check(spec, seam.source, others, wall, max_step=units.mm_to_scene(build.FIT_STEP_MM, scene),
                           own=own).reason(wall)
        if reason:
            return auto.REASONS[reason]
        c = stack_api.add_connector(cut, t, u, v)
        c.pin_side = self._side
        self._placed += 1
        bpy.ops.ed.undo_push(message="Place connector")
        return ""

    def _end(self, context):
        _remove_handler()
        if _RUNNING:
            _RUNNING.pop()
        area = getattr(context, "area", None)
        if area is not None:
            area.header_text_set(None)
            area.tag_redraw()

    # --- modal --------------------------------------------------------------

    def modal(self, context, event):
        obj, cut = find_cut(self._obj_name, self._uid)
        if obj is None or context.region_data is None:
            self._end(context)
            log.info("Connector placement ended.")
            return {'CANCELLED'}
        x, y = event.mouse_region_x, event.mouse_region_y
        region = context.region
        inside_region = region is not None and 0 <= x < region.width and 0 <= y < region.height

        if event.type in {'ESC', 'RIGHTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            self._end(context)
            msg = f"{self._placed} connector(s) placed on {cut.name}"
            self.report({'INFO'}, msg)
            log.info(msg)
            return {'FINISHED'}
        plain = not (event.ctrl or event.alt or event.shift or event.oskey)
        if event.type == 'S' and event.value == 'PRESS' and plain:
            self._side = 'B' if self._side == 'A' else 'A'
            self._message = ""
            self._update(context, obj, cut, event)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and inside_region and plain:
            self._update(context, obj, cut, event)
            if self._last is None:
                self._message = "Click on the seam of the cut"
            elif not self._last[2]:
                self._message = "Outside the object"
            else:
                reason = self.place(context, obj, cut, self._last[0], self._last[1])
                self._message = f"Does not fit here: {reason}" if reason else ""
                if reason:
                    self.report({'WARNING'}, self._message)
            obj, cut = find_cut(self._obj_name, self._uid)
            self._header(context, cut)
            return {'RUNNING_MODAL'}
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            self._update(context, obj, cut, event)
            return {'PASS_THROUGH'}
        if not plain:
            # Ctrl+Z / Ctrl+Shift+Z (one placed connector per step; data is looked up again next event),
            # Ctrl+S, Alt+LMB view navigation, ...: Blender handles them
            self._message = ""
            return {'PASS_THROUGH'}
        if (event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}
                or event.type.startswith(("NDOF", "TRACKPAD", "NUMPAD_"))):
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        """Blender ends the modal (file load, window closed): drop the preview, write nothing."""
        self._end(context)
        log.info("Connector placement ended.")


classes = (SPLITFORGE_OT_connector_add_click,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    _remove_handler()
    _RUNNING.clear()
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
