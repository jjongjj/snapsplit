# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# ui/overlay.py
"""Viewport overlay (gpu draw handler) for the cut stack of the active object.

Draws each cut plane as a translucent quad and each stroke cut as its ribbon
over the object's depth (active cut orange, others blue, disabled ones as a
grey outline), and each connector as a circle/rectangle on its seam with a
short stroke towards the pin side. Nothing is cached: every
redraw resolves the active object's stack again, and no data-blocks are ever
created (undo safe).
"""

import math

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from ..connectors import placement
from ..core import log, naming, units
from ..cuts import plane, stroke
from ..model import stack as stack_api

ACTIVE_FILL = (1.0, 0.45, 0.0, 0.30)
ACTIVE_LINE = (1.0, 0.55, 0.05, 1.0)
OTHER_FILL = (0.2, 0.55, 1.0, 0.15)
OTHER_LINE = (0.3, 0.65, 1.0, 0.9)
DISABLED_LINE = (0.55, 0.55, 0.55, 0.8)
CONNECTOR_LINE = (1.0, 1.0, 0.3, 1.0)

_handle = None
_reported = set()


def plane_quad(obj, co, n, t, b):
    """Corners of a square on the plane, centered on the projected bbox center."""
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    center = sum(corners, Vector()) / 8.0
    center -= n * (center - co).dot(n)
    half = max((corners[6] - corners[0]).length * 0.6, 1e-4)
    return [center + t * su * half + b * sv * half for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def connector_outline(matrix, kind, width, height, segments=24):
    """Closed outline of a connector cross-section in world space (seam plane)."""
    if kind == 'RECT_TENON':
        pts = [(-width / 2, -height / 2), (width / 2, -height / 2), (width / 2, height / 2), (-width / 2, height / 2)]
    else:
        r = width / 2
        pts = [(r * math.cos(2 * math.pi * i / segments), r * math.sin(2 * math.pi * i / segments))
               for i in range(segments)]
    return [matrix @ Vector((x, y, 0.0)) for x, y in pts]


def _loop_lines(points):
    out = []
    for i, p in enumerate(points):
        out += [p, points[(i + 1) % len(points)]]
    return out


def stroke_ribbon(obj, cut):
    """(quads as triangle list, outline segments, matrix_fn) of a stroke cut's ribbon in world space.

    The ribbon spans the object's depth along the stroke direction; matrix_fn(u, v, rot)
    is the connector placement on it (same frame as the Build).
    """
    m = obj.matrix_world
    pts = [m @ Vector(p.co) for p in cut.points]
    d = (m.to_3x3() @ Vector(cut.direction)).normalized()
    if len(pts) < 2 or d.length < 1e-9:
        return [], [], None
    frame = stroke.Frame.from_direction(d, sum(pts, Vector()) / len(pts))
    pts2 = stroke.dedupe([frame.to2d(p) for p in pts], 1e-12)
    if len(pts2) < 2:
        return [], [], None
    depths = [frame.depth(m @ Vector(c)) for c in obj.bound_box]
    z0, z1 = min(depths), max(depths)
    lo = [frame.to3d(x, y, z0) for x, y in pts2]
    hi = [frame.to3d(x, y, z1) for x, y in pts2]
    tris, segs = [], []
    for i in range(len(pts2) - 1):
        tris += [lo[i], lo[i + 1], hi[i + 1], lo[i], hi[i + 1], hi[i]]
        segs += [lo[i], lo[i + 1], hi[i], hi[i + 1]]
        mid_a, mid_b = (lo[i] + hi[i]) * 0.5, (lo[i + 1] + hi[i + 1]) * 0.5
        segs += [mid_a, mid_b]
    segs += [lo[0], hi[0], lo[-1], hi[-1]]
    return tris, segs, stroke.Centerline(frame, pts2).matrix


def geometry(context):
    """(fills, lines) for the current context: lists of (color, coords)."""
    settings = getattr(context.scene, naming.SCENE_SETTINGS, None)
    obj = stack_api.context_owner(context)
    stack = stack_api.get_stack(obj)
    if settings is None or not settings.show_overlay or stack is None:
        return [], []
    mm = units.mm_to_scene(1.0, context.scene)
    fills, lines = [], []
    for i, cut in enumerate(stack.cuts):
        active = i == stack.active_index
        if cut.kind == 'STROKE':
            tris, outline, matrix_fn = stroke_ribbon(obj, cut)
        else:
            co, n, t, b = plane.world_frame(obj.matrix_world, cut.origin, cut.normal, cut.tangent)
            quad = plane_quad(obj, co, n, t, b)
            tris, outline = [quad[0], quad[1], quad[2], quad[0], quad[2], quad[3]], _loop_lines(quad)

            def matrix_fn(u, v, rot, co=co, n=n, t=t):
                return placement.frame_matrix(co, n, t, u, v, rot)
        if not cut.enabled:
            lines.append((DISABLED_LINE, outline))
            continue
        if tris:
            fills.append((ACTIVE_FILL if active else OTHER_FILL, tris))
        lines.append((ACTIVE_LINE if active else OTHER_LINE, outline))
        if matrix_fn is None:
            continue
        for c in cut.connectors:
            if not c.enabled:
                continue
            m = matrix_fn(c.u * mm, c.v * mm, c.rotation_deg)
            seg = _loop_lines(connector_outline(m, c.kind, c.width_mm * mm, c.height_mm * mm))
            side = 1.0 if c.pin_side == 'A' else -1.0
            tip = m @ Vector((0.0, 0.0, side * c.length_mm * mm * 0.5))
            seg += [m.translation.copy(), tip]
            lines.append((CONNECTOR_LINE, seg))
    return fills, lines


def _draw():
    try:
        fills, lines = geometry(bpy.context)
        if not fills and not lines:
            return
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')
        shader.bind()
        for color, coords in fills:
            if not coords:
                continue
            shader.uniform_float("color", color)
            batch_for_shader(shader, 'TRIS', {"pos": coords}).draw(shader)
        for color, coords in lines:
            if not coords:
                continue
            shader.uniform_float("color", color)
            batch_for_shader(shader, 'LINES', {"pos": coords}).draw(shader)
        gpu.state.blend_set('NONE')
    except Exception as ex:  # a draw callback must never raise every redraw
        key = repr(ex)
        if key not in _reported:
            _reported.add(key)
            log.error("overlay draw failed: %s", key)


def register():
    global _handle
    if _handle is None:
        _handle = bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_VIEW')


def unregister():
    global _handle
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
        _handle = None
    _reported.clear()
