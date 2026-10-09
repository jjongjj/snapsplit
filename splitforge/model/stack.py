# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# model/stack.py
"""Cut stack manipulation (add/remove/move/duplicate/clear) and owner lookup.

Every function takes the object (an ID) and resolves its stack on each call;
callers must not keep the returned PropertyGroups across undo steps or events.
"""

import bpy
from mathutils import Vector

from ..core import meshlib, naming
from ..cuts import plane, stroke

CUT_FIELDS = ("enabled", "kind", "origin", "normal", "tangent", "direction", "gap_mm", "cap", "distribution",
              "connector_count", "connector_rows", "margin_pct")
# Connector type and size (copied from the scene's new-connector template onto new connectors)
TEMPLATE_FIELDS = ("kind", "rotation_deg", "width_mm", "height_mm", "length_mm", "pin_side", "clearance_mm",
                   "embed_pct", "taper_pct", "chamfer_mm", "snap_count", "snap_diameter_mm",
                   "snap_protrusion_mm", "custom_object")
CONNECTOR_FIELDS = ("enabled", "u", "v") + TEMPLATE_FIELDS


def get_stack(obj):
    """The cut stack of ``obj`` (None for non-mesh objects)."""
    if obj is None or obj.type != 'MESH':
        return None
    return getattr(obj, naming.OBJECT_STACK, None)


def owner_of(obj):
    """The object whose stack applies to ``obj``.

    A built part points back to its source (ID reference, survives renames;
    the source name as fallback); every other mesh object owns its own stack.
    """
    if obj is None or obj.type != 'MESH':
        return None
    src = obj.get(naming.PROP_SOURCE_OBJECT)
    if not isinstance(src, bpy.types.Object):
        name = obj.get(naming.PROP_SOURCE)
        src = bpy.data.objects.get(name) if name else None
    if src is not None and src != obj and src.type == 'MESH':
        return src
    return obj


def context_owner(context):
    return owner_of(getattr(context, "active_object", None))


def active_cut(obj):
    stack = get_stack(obj)
    if stack is None or not stack.cuts:
        return None
    return stack.cuts[min(stack.active_index, len(stack.cuts) - 1)]


def world_bbox_center(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return sum(corners, Vector()) / 8.0


def _new_uid(stack):
    uid = f"C{stack.next_uid}"
    stack.next_uid += 1
    return uid


def add_cut(obj, origin, normal, tangent=None, name=None):
    """Append a plane cut (local origin/normal/tangent) and make it active. Returns its index."""
    stack = get_stack(obj)
    cut = stack.cuts.add()
    cut.uid = _new_uid(stack)
    cut.name = name or f"Cut {len(stack.cuts)}"
    n, t, _b = meshlib.orthonormal_basis(normal, tangent)
    cut.origin = Vector(origin)
    cut.normal = n
    cut.tangent = t
    stack.active_index = len(stack.cuts) - 1
    return stack.active_index


def set_stroke(cut, points, direction):
    """Store a stroke (object-local points and extrusion direction) on ``cut``.

    The display frame (origin/normal/tangent) is the seam frame in the middle of
    the stroke. Raises stroke.StrokeError for a degenerate stroke.
    """
    co, n, t = stroke.curve_frame(points, direction)
    cut.kind = 'STROKE'
    cut.points.clear()
    for p in points:
        cut.points.add().co = Vector(p)
    cut.direction = Vector(direction).normalized()
    cut.origin = co
    cut.normal = n
    cut.tangent = t


def stroke_problem(obj, cut, scene):
    """'' if the stroke cut can be built with its gap on ``obj``, else the reason (StrokeError text)."""
    from ..core import units
    m = obj.matrix_world
    points = [m @ p for p in stroke_points(cut)]
    d = (m.to_3x3() @ Vector(cut.direction)).normalized()
    corners = [m @ Vector(c) for c in obj.bound_box]
    try:
        stroke.build_cutter(points, d, corners, units.mm_to_scene(cut.gap_mm, scene))
    except stroke.StrokeError as ex:
        return str(ex)
    return ""


# (object name, cut uid) -> (inputs, message): the panel asks on every redraw; the stroke check
# only runs again when something it depends on changed (points, direction, gap, the object's
# transform and bounds, the unit scale). Plain Python values only.
_PROBLEMS = {}


def stroke_problem_cached(obj, cut, scene):
    """stroke_problem() for drawing code: recomputed only when its inputs changed."""
    inputs = (tuple(round(x, 9) for row in obj.matrix_world for x in row),
              tuple(round(x, 9) for c in obj.bound_box for x in c),
              round(scene.unit_settings.scale_length, 12), round(cut.gap_mm, 9), tuple(cut.direction),
              len(cut.points), hash(tuple(tuple(p.co) for p in cut.points)))
    key = (obj.name, cut.uid)
    hit = _PROBLEMS.get(key)
    if hit is None or hit[0] != inputs:
        if len(_PROBLEMS) > 256:
            _PROBLEMS.clear()
        hit = _PROBLEMS[key] = (inputs, stroke_problem(obj, cut, scene))
    return hit[1]


def stroke_points(cut):
    """Object-local stroke points of a STROKE cut as Vectors."""
    return [Vector(p.co) for p in cut.points]


def add_stroke_cut(obj, points, direction, name=None):
    """Append a stroke cut (object-local points + direction) and make it active. Returns its index."""
    stack = get_stack(obj)
    cut = stack.cuts.add()
    try:
        set_stroke(cut, points, direction)
    except stroke.StrokeError:
        stack.cuts.remove(len(stack.cuts) - 1)
        raise
    cut.uid = _new_uid(stack)
    cut.name = name or f"Stroke {len(stack.cuts)}"
    stack.active_index = len(stack.cuts) - 1
    return stack.active_index


def add_axis_cut(obj, axis, offset, name=None):
    """Add a cut perpendicular to a world axis through the bbox center + offset (BU)."""
    origin, normal, tangent = plane.axis_plane(obj.matrix_world, world_bbox_center(obj), axis, offset)
    return add_cut(obj, origin, normal, tangent, name or f"Cut {axis}")


def _resolve_index(stack, index):
    if index < 0:
        index = stack.active_index
    if not 0 <= index < len(stack.cuts):
        raise IndexError(f"no cut at index {index}")
    return index


def remove_cut(obj, index=-1):
    stack = get_stack(obj)
    index = _resolve_index(stack, index)
    stack.cuts.remove(index)
    stack.active_index = max(0, min(stack.active_index, len(stack.cuts) - 1))


def move_cut(obj, index, direction):
    """Move a cut 'UP' (towards index 0) or 'DOWN'. Returns the new index."""
    stack = get_stack(obj)
    index = _resolve_index(stack, index)
    target = index - 1 if direction == 'UP' else index + 1
    if not 0 <= target < len(stack.cuts):
        return index
    stack.cuts.move(index, target)
    stack.active_index = target
    return target


def copy_connector(src, dst, fields=CONNECTOR_FIELDS):
    for f in fields:
        setattr(dst, f, getattr(src, f))


def add_connector(cut, template, u, v):
    """Append a connector at (u, v) mm with the template's type and size; make it active. Returns it."""
    c = cut.connectors.add()
    copy_connector(template, c, TEMPLATE_FIELDS)
    c.u, c.v = u, v
    cut.active_connector = len(cut.connectors) - 1
    return c


def duplicate_cut(obj, index=-1):
    """Insert a copy (new uid, same connectors) right after the cut. Returns its index."""
    stack = get_stack(obj)
    index = _resolve_index(stack, index)
    src = stack.cuts[index]
    dst = stack.cuts.add()
    for f in CUT_FIELDS:
        setattr(dst, f, getattr(src, f))
    for p in src.points:
        dst.points.add().co = p.co
    for c in src.connectors:
        copy_connector(c, dst.connectors.add())
    dst.uid = _new_uid(stack)
    dst.name = src.name + " copy"
    new_index = len(stack.cuts) - 1
    stack.cuts.move(new_index, index + 1)
    stack.active_index = index + 1
    return index + 1


def clear(obj):
    stack = get_stack(obj)
    stack.cuts.clear()
    stack.active_index = 0
