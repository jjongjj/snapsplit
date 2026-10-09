# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# ops/ops_cut_points.py
"""Polyline and polygon cuts: click points in the viewport, or pass them (scripts).

Modal (both): LMB adds a point on the plane through the object's center facing
the view (the view direction is taken at the first click and kept, so the view
may be orbited between clicks: later clicks land on the same plane along the
current mouse ray). Ctrl at the click snaps the new segment to 15 degree steps
on screen. Backspace / Delete / Ctrl+Z remove the last point. Enter/Space
confirms, Esc/RMB cancels. A polygon also closes (and confirms) with a click on
its first point. View navigation passes through. A rubber band follows the
cursor; the preview turns red with the reason when the points do not make a
valid cut.

- ``splitforge.stack_add_polyline``: straight segments between the points, a
  ribbon cut like a stroke (cuts/polyline.py); at least 2 points.
- ``splitforge.stack_add_polygon``: a closed polygon whose region is cut out as
  its own part (cuts/polygon.py), through the object or ``depth_mm`` deep; at
  least 3 points.

``replace_uid`` redraws an existing cut of the same kind (connectors and
settings kept); ``easy`` adds Easy connectors and builds at once (one undo
step). Undo safety as the stroke modal: only plain values between events
(object name, cut uid, point tuples, the region pointer as an int); the preview
is drawn from module-level plain data; nothing is created before the commit.
"""

import bpy
import gpu
from bpy.props import BoolProperty, CollectionProperty, FloatProperty, FloatVectorProperty, StringProperty
from bpy.types import Operator
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import intersect_line_plane

from ..core import log, naming, units
from ..cuts import build, polygon, polyline, stroke
from ..model import props as model_props
from ..model import stack as stack_api

LINE_COLOR = (1.0, 0.45, 0.0, 1.0)
BAND_COLOR = (1.0, 0.8, 0.3, 0.8)
CUTTER_COLOR = (1.0, 0.55, 0.05, 0.8)
INVALID_COLOR = (1.0, 0.15, 0.12, 0.9)

_PREVIEW = {"region": 0, "lines": [], "points": []}
_HANDLE = None
_RUNNING = []


def _draw():
    if not _PREVIEW["lines"] and not _PREVIEW["points"]:
        return
    region = getattr(bpy.context, "region", None)
    if region is None or region.as_pointer() != _PREVIEW["region"]:
        return
    try:
        try:
            shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
            polyline_shader = True
        except Exception:
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            polyline_shader = False
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')
        shader.bind()
        for color, width, coords in _PREVIEW["lines"]:
            if len(coords) < 2:
                continue
            shader.uniform_float("color", color)
            if polyline_shader:
                shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
                shader.uniform_float("lineWidth", width)
            batch_for_shader(shader, 'LINE_STRIP', {"pos": coords}).draw(shader)
        if _PREVIEW["points"]:
            point_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            point_shader.bind()
            point_shader.uniform_float("color", LINE_COLOR)
            gpu.state.point_size_set(8.0)
            batch_for_shader(point_shader, 'POINTS', {"pos": _PREVIEW["points"]}).draw(point_shader)
            gpu.state.point_size_set(1.0)
        gpu.state.blend_set('NONE')
    except Exception as ex:  # never raise from a draw callback
        log.error("point cut preview draw failed: %s", ex)
        _PREVIEW["lines"] = []
        _PREVIEW["points"] = []


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
    _PREVIEW["points"] = []
    _PREVIEW["region"] = 0


def _find_cut(obj, uid):
    stack = stack_api.get_stack(obj)
    for i, cut in enumerate(stack.cuts if stack is not None else ()):
        if cut.uid == uid:
            return i, cut
    return -1, None


def _source_bvh(context, obj):
    bm = build.source_bmesh(obj, context.evaluated_depsgraph_get())
    try:
        return BVHTree.FromBMesh(bm)
    finally:
        bm.free()


def prepare(context, obj, kind, points_world, direction, gap=0.0, depth=0.0):
    """Validated cutter of clicked points for ``obj``: (unit direction, cutter).

    ``kind`` POLYLINE (stroke.StrokeCutter, points kept as clicked) or POLYGON
    (polygon.PolygonCutter). Raises stroke.StrokeError with a message for the
    user: too few points, crossing segments, too tight for the gap, a floor in
    front of the object, or not crossing the object.
    """
    d = Vector(direction).normalized()
    pts = [Vector(p) for p in points_world]
    corners = build.world_corners(obj)
    source = _source_bvh(context, obj)
    if kind == 'POLYGON':
        cutter = polygon.build_cutter(pts, d, corners, gap, depth,
                                       units.mm_to_scene(1.0, context.scene))
        surface = cutter.solid()
        what = "polygon"
    else:
        if len(pts) < 2:
            raise stroke.StrokeError("A polyline needs at least 2 points")
        cutter = stroke.build_cutter(pts, d, corners, gap, kind)
        surface = cutter.ribbon()
        what = "polyline"
    try:
        crosses = bool(source.overlap(BVHTree.FromBMesh(surface)))
    finally:
        surface.free()
    if not crosses:
        raise stroke.StrokeError(f"The {what} does not cross the object: place the points across it"
                                 if kind != 'POLYGON' else
                                 "The polygon does not cross the object's surface: draw it over the object "
                                 "(a polygon around the whole object or inside it cuts nothing)")
    return d, cutter


class _PointsCut:
    """Shared modal of the polyline and polygon operators (``KIND``, ``MIN_POINTS``)."""
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}
    KIND = 'POLYLINE'
    MIN_POINTS = 2

    points: CollectionProperty(type=model_props.SPLITFORGE_PG_Point, options={'SKIP_SAVE'},
                               description="Points in world space (scripts; the modal fills them)")
    direction: FloatVectorProperty(name="Direction", size=3, default=(0.0, 1.0, 0.0), subtype='XYZ',
                                   options={'SKIP_SAVE'}, description="Extrusion (view) direction, world space")
    replace_uid: StringProperty(name="Replace", default="", options={'SKIP_SAVE'},
                                description="Redraw this cut instead of adding a new one")
    easy: BoolProperty(name="Easy", default=False, options={'SKIP_SAVE'},
                       description="Easy mode: add connectors and build immediately")

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and stack_api.context_owner(context) is not None

    # --- commit (execute and modal) -------------------------------------------

    def _depth_mm(self, cut):
        return 0.0

    def _commit(self, context, points_world, direction):
        obj = stack_api.context_owner(context)
        s = getattr(context.scene, naming.SCENE_SETTINGS)
        cut = None
        if self.replace_uid:
            _index, cut = _find_cut(obj, self.replace_uid)
            if cut is None or cut.kind != self.KIND:
                self.report({'ERROR'}, f"No {self.KIND.lower()} cut with id {self.replace_uid}")
                return {'CANCELLED'}
        gap_mm = cut.gap_mm if cut is not None else (s.easy_gap_mm if self.easy else 0.0)
        depth_mm = self._depth_mm(cut)
        try:
            d, cutter = prepare(context, obj, self.KIND, points_world, direction,
                                units.mm_to_scene(gap_mm, context.scene), units.mm_to_scene(depth_mm, context.scene))
        except stroke.StrokeError as ex:
            self.report({'ERROR'}, str(ex))
            return None
        inv = obj.matrix_world.inverted_safe()
        local = [inv @ Vector(p) for p in points_world]
        d_local = (inv.to_3x3() @ d).normalized()
        if cut is not None:
            cut.depth_mm = depth_mm
            stack_api.set_stroke(cut, local, d_local, self.KIND, [Vector(c) for c in obj.bound_box])
            self.report({'INFO'}, f"{cut.name} redrawn; {len(cut.connectors)} connector(s) kept "
                                  "(Distribute again if they no longer fit)")
            return {'FINISHED'}
        stack = stack_api.get_stack(obj)
        next_uid = stack.next_uid
        index = stack_api.add_stroke_cut(obj, local, d_local, kind=self.KIND, depth_mm=depth_mm)
        if self.easy:
            from .ops_build import easy_finish
            count = s.easy_connector_count
            if self.KIND == 'POLYGON' and cutter.through and count > 0:
                self.report({'INFO'}, "A polygon through the whole object gets no connectors (set a Depth "
                                      "for a cut-out with a floor)")
                count = 0
            return easy_finish(self, context, obj, index, count, next_uid)
        self.report({'INFO'}, f"{stack_api.get_stack(obj).cuts[index].name} added")
        return {'FINISHED'}

    def execute(self, context):
        result = self._commit(context, [Vector(p.co) for p in self.points], self.direction)
        return result if result is not None else {'CANCELLED'}

    # --- modal ------------------------------------------------------------------

    def invoke(self, context, event):
        if context.area is None or context.area.type != 'VIEW_3D' or context.region_data is None:
            return self.execute(context)
        if _RUNNING:
            self.report({'WARNING'}, "Points are already being placed")
            return {'CANCELLED'}
        obj = stack_api.context_owner(context)
        if self.replace_uid:
            cut = _find_cut(obj, self.replace_uid)[1]
            if cut is None or cut.kind != self.KIND:
                self.report({'ERROR'}, f"No {self.KIND.lower()} cut with id {self.replace_uid}")
                return {'CANCELLED'}
        self._obj_name = obj.name
        self._world = []          # clicked points (tuples) on the plane through the object center
        self._dir = None          # view direction at the first click (tuple)
        self._cursor = None       # rubber band end (world tuple) or None
        self._message = ""
        self._valid = False
        self._cutter_lines = []   # cutter outline of the last valid points (plain tuples)
        _RUNNING.append(True)
        _PREVIEW["region"] = context.region.as_pointer()
        _PREVIEW["lines"] = []
        _PREVIEW["points"] = []
        _add_handler()
        context.window_manager.modal_handler_add(self)
        self._header(context)
        return {'RUNNING_MODAL'}

    def _what(self):
        return "Polygon cut" if self.KIND == 'POLYGON' else "Polyline cut"

    def _header(self, context):
        if context.area is None:
            return
        n = len(self._world)
        text = (f"{n} point(s) | LMB: add point (Ctrl: 15 degree steps)  Backspace/Ctrl+Z: remove last  "
                "Enter: confirm  Esc/RMB: cancel")
        if self.KIND == 'POLYGON':
            text += "  (click the first point to close)"
        if self._message:
            text = f"{self._message} | {text}"
        context.area.header_text_set(f"{self._what()}: {text}")

    def _end(self, context):
        _remove_handler()
        if _RUNNING:
            _RUNNING.pop()
        area = getattr(context, "area", None)
        if area is not None:
            area.header_text_set(None)
            area.tag_redraw()

    def _project(self, context, co):
        """World point (tuple) of region coordinates ``co`` on the drawing plane, or None."""
        obj = bpy.data.objects.get(self._obj_name)
        center = sum(build.world_corners(obj), Vector()) / 8.0
        region, rv3d = context.region, context.region_data
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, Vector(co))
        ray = view3d_utils.region_2d_to_vector_3d(region, rv3d, Vector(co))
        if self._dir is None:
            d = (Matrix(rv3d.view_rotation.to_matrix()) @ Vector((0.0, 0.0, -1.0))).normalized()
        else:
            d = Vector(self._dir)
            if abs(ray.normalized().dot(d)) < 1e-3:
                return None, d   # the view looks along the drawing plane
        hit = intersect_line_plane(origin, origin + ray, center, d)
        return (tuple(hit) if hit is not None else None), d

    @staticmethod
    def _screen_of(context, point):
        """Region coordinates of a stored world point in the CURRENT view (the view may have been
        orbited since it was clicked), or None when it is behind the view."""
        co = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, Vector(point))
        return None if co is None else (co.x, co.y)

    def _cursor_co(self, context, event):
        co = (event.mouse_region_x, event.mouse_region_y)
        if event.ctrl and self._world:
            prev = self._screen_of(context, self._world[-1])
            if prev is not None:
                co = polyline.snap_screen(prev, co)
        return co

    def _validate(self, context):
        """Check the current points: sets _valid/_message, returns the cutter or None."""
        if len(self._world) < self.MIN_POINTS:
            self._valid, self._message = False, ""
            return None
        obj = bpy.data.objects.get(self._obj_name)
        cut = _find_cut(obj, self.replace_uid)[1] if self.replace_uid else None
        s = getattr(context.scene, naming.SCENE_SETTINGS)
        gap = units.mm_to_scene(cut.gap_mm if cut is not None else (s.easy_gap_mm if self.easy else 0.0),
                                context.scene)
        depth = units.mm_to_scene(self._depth_mm(cut), context.scene)
        try:
            _d, cutter = prepare(context, obj, self.KIND, self._world, self._dir, gap, depth)
        except stroke.StrokeError as ex:
            self._valid, self._message = False, str(ex)
            return None
        self._valid, self._message = True, ""
        return cutter

    def _update_preview(self, context, cutter=None):
        pts = list(self._world)
        color = LINE_COLOR if self._valid or len(pts) < self.MIN_POINTS else INVALID_COLOR
        lines = []
        if pts:
            loop = pts + [pts[0]] if self.KIND == 'POLYGON' and len(pts) >= 3 else pts
            lines.append((color, 3.0, loop))
            if self._cursor is not None:
                band = [pts[-1], self._cursor] + ([pts[0]] if self.KIND == 'POLYGON' and len(pts) >= 2 else [])
                lines.append((BAND_COLOR, 1.5, band))
        if cutter is not None:
            # plain tuples, kept for the following rubber band redraws
            self._cutter_lines = self._cutter_preview(cutter)
        elif not self._valid:
            self._cutter_lines = []
        lines += self._cutter_lines
        _PREVIEW["lines"] = lines
        _PREVIEW["points"] = pts
        if context.area is not None:
            context.area.tag_redraw()

    def _cutter_preview(self, cutter):
        f = cutter.frame
        out = []
        if self.KIND == 'POLYGON':
            for z in ((cutter.z_floor,) if not cutter.through else (cutter.z0, cutter.z_floor)):
                out.append((CUTTER_COLOR, 1.5, [tuple(f.to3d(x, y, z)) for x, y in cutter.poly + cutter.poly[:1]]))
            for x, y in cutter.poly:
                out.append((CUTTER_COLOR, 1.0, [tuple(f.to3d(x, y, cutter.z0)), tuple(f.to3d(x, y, cutter.z_floor))]))
        else:
            for z in (cutter.z0, cutter.z1, 0.5 * (cutter.z0 + cutter.z1)):
                out.append((CUTTER_COLOR, 1.5, [tuple(f.to3d(x, y, z)) for x, y in cutter.extended]))
        return out

    def _confirm(self, context):
        """Enter (or closing a polygon): commit valid points. Returns the modal result or None."""
        if len(self._world) < self.MIN_POINTS:
            self._message = f"Place at least {self.MIN_POINTS} points"
            self.report({'WARNING'}, self._message)
            return None
        cutter = self._validate(context)
        if cutter is None:
            self.report({'WARNING'}, self._message)
            self._update_preview(context)
            return None
        result = self._commit(context, [Vector(p) for p in self._world], self._dir)
        if result is None:
            self._valid, self._message = False, "Points rejected"
            return None
        self.direction = self._dir
        self.points.clear()
        for p in self._world:
            self.points.add().co = p
        self._end(context)
        log.info("%s confirmed.", self._what())
        return result

    def _changed(self, context):
        self._update_preview(context, self._validate(context))
        self._header(context)

    def modal(self, context, event):
        obj = bpy.data.objects.get(self._obj_name)
        if obj is None or stack_api.get_stack(obj) is None or context.region_data is None or (
                self.replace_uid and _find_cut(obj, self.replace_uid)[1] is None):
            self._end(context)
            log.info("%s cancelled.", self._what())
            return {'CANCELLED'}
        x, y = event.mouse_region_x, event.mouse_region_y
        region = context.region
        inside = region is not None and 0 <= x < region.width and 0 <= y < region.height

        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._end(context)
            self.report({'INFO'}, f"{self._what()} cancelled.")
            log.info("%s cancelled.", self._what())
            return {'CANCELLED'}
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            if self._world:
                self._cursor = self._project(context, self._cursor_co(context, event))[0]
                self._update_preview(context, None)
            return {'PASS_THROUGH'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and inside and not (event.alt or event.shift):
            co = self._cursor_co(context, event)
            if (self.KIND == 'POLYGON' and len(self._world) >= 3
                    and self._screen_of(context, self._world[0]) is not None
                    and polyline.near(co, self._screen_of(context, self._world[0]))):
                result = self._confirm(context)
                if result is not None:
                    return result
                self._header(context)
                return {'RUNNING_MODAL'}
            hit, d = self._project(context, co)
            if hit is None:
                self._message = "The view looks along the drawing plane: orbit back to add points"
                self._header(context)
                return {'RUNNING_MODAL'}
            if self._dir is None:
                self._dir = tuple(d)
            self._world.append(hit)
            self._cursor = None
            self._changed(context)
            return {'RUNNING_MODAL'}
        if event.value == 'PRESS' and (event.type in {'BACK_SPACE', 'DEL'} or (
                event.type == 'Z' and (event.ctrl or event.oskey) and not event.shift)):
            if self._world:
                self._world.pop()
                if not self._world:
                    self._dir = None
            self._cursor = None
            self._changed(context)
            return {'RUNNING_MODAL'}
        if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} and event.value == 'PRESS':
            result = self._confirm(context)
            if result is not None:
                return result
            self._header(context)
            return {'RUNNING_MODAL'}
        if (event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}
                or event.type.startswith(("NDOF", "TRACKPAD", "NUMPAD_"))
                or (event.type == 'LEFTMOUSE' and event.alt)):
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        """Blender ends the modal (file load, window closed): drop the preview, write nothing."""
        self._end(context)
        log.info("%s cancelled.", self._what())


class SPLITFORGE_OT_stack_add_polyline(_PointsCut, Operator):
    """Click points for a cut along straight segments, extruded along the view direction through the whole object (LMB add point, Ctrl: 15 degree steps, Backspace remove last, Enter confirm, Esc cancel)"""
    bl_idname = naming.op("stack_add_polyline")
    bl_label = "Add Polyline Cut"
    KIND = 'POLYLINE'
    MIN_POINTS = 2


class SPLITFORGE_OT_stack_add_polygon(_PointsCut, Operator):
    """Click the corners of a region to cut it out as its own part (a prism along the view direction, through the object or Depth deep; LMB add point, click the first point or Enter to close, Backspace remove last, Esc cancel)"""
    bl_idname = naming.op("stack_add_polygon")
    bl_label = "Add Polygon Cut"
    KIND = 'POLYGON'
    MIN_POINTS = 3

    depth_mm: FloatProperty(name="Depth (mm)", default=-1.0, min=-1.0, soft_max=200.0, options={'SKIP_SAVE'},
                            description="How deep the cut-out reaches from the object's front along the view "
                                        "(0 = through the whole object; -1 = keep the redrawn cut's depth, "
                                        "Easy: the Easy depth, otherwise 0)")

    def _depth_mm(self, cut):
        if self.depth_mm >= 0.0:
            return self.depth_mm
        if cut is not None:
            return cut.depth_mm
        if self.easy:
            return getattr(bpy.context.scene, naming.SCENE_SETTINGS).easy_depth_mm
        return 0.0


classes = (SPLITFORGE_OT_stack_add_polyline, SPLITFORGE_OT_stack_add_polygon)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    _remove_handler()
    _RUNNING.clear()
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
