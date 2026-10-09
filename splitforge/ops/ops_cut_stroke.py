# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# ops/ops_cut_stroke.py
"""Stroke (curved) cut: draw in the viewport, or pass the points (scripts).

Modal: LMB drag draws the stroke (on the plane through the object's center
facing the view), releasing LMB shows the cut ribbon; Shift held at release
straightens the stroke and snaps it to the nearest world axis direction in the
view. Enter/Space commits, LMB again redraws, Esc/RMB cancels. View navigation
passes through between strokes. ``replace_uid`` redraws an existing stroke cut
(its connectors and settings are kept); ``easy`` adds Easy connectors and builds
right away (one undo step, like Easy Cut).

Undo safety: between events only plain values are kept (object name, cut uid,
point tuples, the region's pointer as an int to restrict drawing to it). The
preview is drawn by a gpu handler from a module-level plain-data state, never
from Blender data; nothing is created until the commit.
"""

import bpy
import gpu
from bpy.props import BoolProperty, CollectionProperty, FloatVectorProperty, StringProperty
from bpy.types import Operator
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from ..core import log, naming, units
from ..cuts import build, stroke
from ..model import props as model_props
from ..model import stack as stack_api

# Captured screen points closer than this (pixels) are skipped while drawing
MIN_PIXELS = 2.0
# Prepared stroke spacing: object bounding box diagonal / SPACING_DIVISIONS
SPACING_DIVISIONS = 150

STROKE_COLOR = (1.0, 0.45, 0.0, 1.0)
RIBBON_COLOR = (1.0, 0.55, 0.05, 0.8)
INVALID_COLOR = (1.0, 0.15, 0.12, 0.9)

# Preview of the running operator (plain data only) and its draw handler
_PREVIEW = {"region": 0, "lines": []}
_HANDLE = None
_RUNNING = []


def _draw():
    if not _PREVIEW["lines"]:
        return
    region = getattr(bpy.context, "region", None)
    if region is None or region.as_pointer() != _PREVIEW["region"]:
        return
    try:
        try:
            shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
            polyline = True
        except Exception:
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            polyline = False
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')
        shader.bind()
        for color, width, coords in _PREVIEW["lines"]:
            if len(coords) < 2:
                continue
            shader.uniform_float("color", color)
            if polyline:
                shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
                shader.uniform_float("lineWidth", width)
            batch_for_shader(shader, 'LINE_STRIP', {"pos": coords}).draw(shader)
        gpu.state.blend_set('NONE')
    except Exception as ex:  # never raise from a draw callback
        log.error("stroke preview draw failed: %s", ex)
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


def _find_cut(obj, uid):
    stack = stack_api.get_stack(obj)
    for i, cut in enumerate(stack.cuts if stack is not None else ()):
        if cut.uid == uid:
            return i, cut
    return -1, None


def prepare(context, obj, points_world, direction, snap=False, gap=0.0, clean=True):
    """Validated stroke for ``obj``: (prepared world points, unit direction, cutter).

    ``clean``: resample and smooth the points (stroke.prepare_points); off for
    points that were prepared already. Raises stroke.StrokeError with a message
    for the user: degenerate or self-crossing stroke, too tight for the gap, or
    not crossing the object.
    """
    d = Vector(direction).normalized()
    pts = [Vector(p) for p in points_world]
    if snap and len(pts) >= 2:
        pts = stroke.snap_to_axis(pts, d)
    if clean:
        pts = stroke.prepare_points(pts, d, Vector(_diag_vector(obj)).length / SPACING_DIVISIONS)
    cutter = stroke.build_cutter(pts, d, build.world_corners(obj), gap)
    bm = build.source_bmesh(obj, context.evaluated_depsgraph_get())
    try:
        source = BVHTree.FromBMesh(bm)
    finally:
        bm.free()
    ribbon = cutter.ribbon()
    try:
        crosses = bool(source.overlap(BVHTree.FromBMesh(ribbon)))
    finally:
        ribbon.free()
    if not crosses:
        raise stroke.StrokeError("The stroke does not cross the object: draw across it")
    return pts, d, cutter


def _diag_vector(obj):
    corners = build.world_corners(obj)
    return [max(c[i] for c in corners) - min(c[i] for c in corners) for i in range(3)]


class SPLITFORGE_OT_stack_add_stroke(Operator):
    """Draw a curved cut: the stroke is extruded along the view direction through the whole object (LMB draw, Enter confirm, Esc cancel, Shift at release: straight axis line)"""
    bl_idname = naming.op("stack_add_stroke")
    bl_label = "Add Stroke Cut"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    points: CollectionProperty(type=model_props.SPLITFORGE_PG_Point, options={'SKIP_SAVE'},
                               description="Stroke points in world space (scripts; the modal fills them)")
    direction: FloatVectorProperty(name="Direction", size=3, default=(0.0, 1.0, 0.0), subtype='XYZ',
                                   options={'SKIP_SAVE'}, description="Extrusion (view) direction, world space")
    snap: BoolProperty(name="Snap to axis", default=False, options={'SKIP_SAVE'},
                       description="Straighten the stroke and align it with the nearest world axis in the view")
    replace_uid: StringProperty(name="Replace", default="", options={'SKIP_SAVE'},
                                description="Redraw this stroke cut instead of adding a new one")
    easy: BoolProperty(name="Easy", default=False, options={'SKIP_SAVE'},
                       description="Easy mode: add connectors and build immediately")
    clean: BoolProperty(name="Smooth", default=True, options={'SKIP_SAVE', 'HIDDEN'},
                        description="Resample and smooth the points (off: they were prepared already)")

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and stack_api.context_owner(context) is not None

    # --- commit (execute and modal) -------------------------------------------

    def _commit(self, context, points_world, direction, snap, clean=True):
        obj = stack_api.context_owner(context)
        s = getattr(context.scene, naming.SCENE_SETTINGS)
        index, cut = (-1, None)
        if self.replace_uid:
            index, cut = _find_cut(obj, self.replace_uid)
            if cut is None:
                self.report({'ERROR'}, f"No cut with id {self.replace_uid}")
                return {'CANCELLED'}
        gap_mm = self._gap_mm(context, cut)
        try:
            pts, d, _cutter = prepare(context, obj, points_world, direction, snap,
                                      units.mm_to_scene(gap_mm, context.scene), clean)
        except stroke.StrokeError as ex:
            self.report({'ERROR'}, str(ex))
            return None
        inv = obj.matrix_world.inverted_safe()
        local = [inv @ p for p in pts]
        d_local = (inv.to_3x3() @ d).normalized()
        if cut is not None:
            stack_api.set_stroke(cut, local, d_local)
            self.report({'INFO'}, f"{cut.name} redrawn; {len(cut.connectors)} connector(s) kept "
                                  "(Distribute again if they no longer fit)")
            return {'FINISHED'}
        stack = stack_api.get_stack(obj)
        next_uid = stack.next_uid
        index = stack_api.add_stroke_cut(obj, local, d_local)
        if self.easy:
            from .ops_build import easy_finish
            return easy_finish(self, context, obj, index, s.easy_connector_count, next_uid)
        self.report({'INFO'}, f"{stack_api.get_stack(obj).cuts[index].name} added")
        return {'FINISHED'}

    def _gap_mm(self, context, cut):
        s = getattr(context.scene, naming.SCENE_SETTINGS)
        return cut.gap_mm if cut is not None else (s.easy_gap_mm if self.easy else 0.0)

    def execute(self, context):
        result = self._commit(context, [Vector(p.co) for p in self.points], self.direction, self.snap,
                              self.clean)
        return result if result is not None else {'CANCELLED'}

    # --- modal ------------------------------------------------------------------

    def invoke(self, context, event):
        if context.area is None or context.area.type != 'VIEW_3D' or context.region_data is None:
            return self.execute(context)
        if _RUNNING:
            self.report({'WARNING'}, "A stroke is already being drawn")
            return {'CANCELLED'}
        obj = stack_api.context_owner(context)
        if self.replace_uid and _find_cut(obj, self.replace_uid)[1] is None:
            self.report({'ERROR'}, f"No cut with id {self.replace_uid}")
            return {'CANCELLED'}
        self._obj_name = obj.name
        self._screen = []        # region coordinates of the stroke being drawn
        self._world = []         # its world points (tuples) on the plane through the object center
        self._dir = None         # view direction at the start of the stroke (tuple)
        self._drawing = False
        self._valid = False
        self._snap = False
        self._message = ""
        _RUNNING.append(True)
        _PREVIEW["region"] = context.region.as_pointer()
        _PREVIEW["lines"] = []
        _add_handler()
        context.window_manager.modal_handler_add(self)
        self._header(context)
        return {'RUNNING_MODAL'}

    def _header(self, context):
        if context.area is None:
            return
        if self._drawing:
            text = "Drawing stroke | release LMB (Shift: straight axis line)"
        elif self._valid:
            text = "Enter: confirm cut | LMB: draw again | Esc/RMB: cancel"
        else:
            text = "Draw a stroke across the object with LMB | Esc/RMB: cancel"
        if self._message:
            text = f"{self._message} | {text}"
        what = "Redraw stroke" if self.replace_uid else "Stroke cut"
        context.area.header_text_set(f"{what}: {text}")

    def _end(self, context):
        _remove_handler()
        if _RUNNING:
            _RUNNING.pop()
        area = getattr(context, "area", None)
        if area is not None:
            area.header_text_set(None)
            area.tag_redraw()

    def _to_world(self, context, coords):
        obj = bpy.data.objects.get(self._obj_name)
        center = sum(build.world_corners(obj), Vector()) / 8.0
        pts, d = stroke.points_from_view(context.region, context.region_data, coords, center)
        return [tuple(p) for p in pts], tuple(d)

    def _update_preview(self, context, cutter=None):
        lines = []
        if self._world:
            lines.append((STROKE_COLOR if self._valid or self._drawing else INVALID_COLOR, 3.0, self._world))
        if cutter is not None:
            f = cutter.frame
            for z in (cutter.z0, cutter.z1, 0.5 * (cutter.z0 + cutter.z1)):
                lines.append((RIBBON_COLOR, 1.5, [tuple(f.to3d(x, y, z)) for x, y in cutter.extended]))
            for x, y in (cutter.extended[0], cutter.extended[-1]):
                lines.append((RIBBON_COLOR, 1.5, [tuple(f.to3d(x, y, cutter.z0)), tuple(f.to3d(x, y, cutter.z1))]))
        _PREVIEW["lines"] = lines
        if context.area is not None:
            context.area.tag_redraw()

    def _finish_stroke(self, context, shift):
        """LMB released: validate the stroke and show the ribbon (or why it is invalid)."""
        self._drawing = False
        self._snap = shift
        self._world, d = self._to_world(context, self._screen)
        self._dir = d
        obj = bpy.data.objects.get(self._obj_name)
        cut = _find_cut(obj, self.replace_uid)[1] if self.replace_uid else None
        gap = units.mm_to_scene(self._gap_mm(context, cut), context.scene)
        cutter = None
        try:
            pts, _d, cutter = prepare(context, obj, self._world, d, shift, gap)
            self._world = [tuple(p) for p in pts]
            self._valid, self._message = True, ""
        except stroke.StrokeError as ex:
            self._valid, self._message = False, str(ex)
            self.report({'WARNING'}, str(ex))
        self._update_preview(context, cutter)

    def modal(self, context, event):
        obj = bpy.data.objects.get(self._obj_name)
        if obj is None or stack_api.get_stack(obj) is None or context.region_data is None:
            self._end(context)
            log.info("Stroke cut cancelled.")
            return {'CANCELLED'}
        if self.replace_uid and _find_cut(obj, self.replace_uid)[1] is None:
            self._end(context)
            log.info("Stroke cut cancelled.")
            return {'CANCELLED'}
        x, y = event.mouse_region_x, event.mouse_region_y
        region = context.region
        inside = region is not None and 0 <= x < region.width and 0 <= y < region.height

        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._end(context)
            self.report({'INFO'}, "Stroke cut cancelled.")
            log.info("Stroke cut cancelled.")
            return {'CANCELLED'}
        if self._drawing:
            if event.type == 'MOUSEMOVE':
                last = self._screen[-1]
                if (x - last[0]) ** 2 + (y - last[1]) ** 2 >= MIN_PIXELS ** 2:
                    self._screen.append((x, y))
                    self._world = self._to_world(context, self._screen)[0]
                    self._update_preview(context)
            elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                if self._screen[-1] != (x, y):
                    self._screen.append((x, y))
                self._finish_stroke(context, event.shift)
                self._header(context)
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and inside and not event.alt:
            self._drawing, self._valid, self._message = True, False, ""
            self._screen = [(x, y)]
            self._world = self._to_world(context, self._screen)[0]
            self._update_preview(context)
            self._header(context)
            return {'RUNNING_MODAL'}
        if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} and event.value == 'PRESS':
            if not self._valid:
                self.report({'WARNING'}, self._message or "Draw a stroke across the object first")
                return {'RUNNING_MODAL'}
            result = self._commit(context, [Vector(p) for p in self._world], self._dir, False, clean=False)
            if result is None:
                self._valid = False
                self._message = "Stroke rejected"
                self._update_preview(context)
                self._header(context)
                return {'RUNNING_MODAL'}
            self.direction = self._dir
            self.snap = False
            self.clean = False
            self.points.clear()
            for p in self._world:
                self.points.add().co = p
            self._end(context)
            log.info("Stroke cut confirmed.")
            return result
        if (event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}
                or event.type.startswith(("NDOF", "TRACKPAD", "NUMPAD_"))):
            return {'PASS_THROUGH'}
        self._header(context)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        """Blender ends the modal (file load, window closed): drop the preview, write nothing."""
        self._end(context)
        log.info("Stroke cut cancelled.")


classes = (SPLITFORGE_OT_stack_add_stroke,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    _remove_handler()
    _RUNNING.clear()
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
