# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# cuts/build.py
"""Build pipeline: source copy -> enabled cuts in order -> connectors -> result collection.

The source object is never modified: its evaluated mesh (modifiers applied) is
copied into a bmesh, transformed to world space and split there. The parts are
new objects with identity transforms in the collection
``naming.build_collection_name(source)``; a rebuild replaces that collection's
previous parts (same collection, no leftovers). Only the source's viewport
visibility (``hide_set``) changes.
"""

from dataclasses import dataclass, field

import bmesh
import bpy
from mathutils.bvhtree import BVHTree

from ..connectors import apply as conn_apply
from ..connectors import placement
from ..core import log, meshlib, naming, units
from ..model import stack as stack_api
from . import plane


class BuildError(Exception):
    pass


@dataclass
class BuildResult:
    collection: str
    parts: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass
class _Piece:
    bm: object
    sides: str = ""


def source_bmesh(obj, depsgraph):
    """World-space bmesh of the evaluated source object (caller frees it)."""
    bm = bmesh.new()
    bm.from_object(obj, depsgraph)
    meshlib.transform_bm(bm, obj.matrix_world)
    return bm


def cut_pieces(bm, planes, warnings):
    """Apply ``planes`` = [(label, co, n, gap, cap)] in order. Consumes ``bm``.

    Returns a list of _Piece; ``sides`` has one letter per plane (A = positive
    side of the normal, B = negative side).
    """
    pieces = [_Piece(bm)]
    for label, co, n, gap, cap in planes:
        out = []
        for piece in pieces:
            pos, neg, ok = plane.split(piece.bm, co, n, gap, cap)
            if not ok:
                warnings.append(f"{label}: a section loop could not be capped")
            piece.bm.free()
            if pos is not None:
                out.append(_Piece(pos, piece.sides + "A"))
            if neg is not None:
                out.append(_Piece(neg, piece.sides + "B"))
        pieces = out
    return pieces


def cut_planes(obj, cuts, scene):
    """[(label, co, n, gap, cap)] in world space / BU for cut_pieces()."""
    mm = units.mm_to_scene(1.0, scene)
    planes = []
    for cut in cuts:
        co, n, _t, _b = plane.world_frame(obj.matrix_world, cut.origin, cut.normal, cut.tangent)
        planes.append((cut.name, co, n, cut.gap_mm * mm, cut.cap))
    return planes


def make_spec(obj, cut, scene, label, u_mm, v_mm, rotation_deg, kind, width_mm, height_mm, length_mm,
              clearance_mm, pin_side):
    """ConnectorSpec (world space, BU) of one connector on ``cut``; lengths given in mm."""
    mm = units.mm_to_scene(1.0, scene)
    co, n, t, _b = plane.world_frame(obj.matrix_world, cut.origin, cut.normal, cut.tangent)
    return conn_apply.ConnectorSpec(
        label=label, matrix=placement.frame_matrix(co, n, t, u_mm * mm, v_mm * mm, rotation_deg),
        kind=kind, width=width_mm * mm, height=height_mm * mm, length=length_mm * mm,
        clearance=clearance_mm * mm, gap=cut.gap_mm * mm, pin_positive=(pin_side == 'A'))


def default_clearance(settings):
    return settings.clearance_mm if settings is not None else 0.2


def connector_specs(obj, cuts, scene, settings):
    """ConnectorSpec list (world space, BU) for the enabled connectors of ``cuts``."""
    specs = []
    for cut in cuts:
        for i, c in enumerate(cut.connectors):
            if not c.enabled:
                continue
            clearance = c.clearance_mm if c.clearance_mm >= 0.0 else default_clearance(settings)
            specs.append(make_spec(obj, cut, scene, f"{cut.name} connector {i + 1}", c.u, c.v, c.rotation_deg,
                                   c.kind, c.width_mm, c.height_mm, c.length_mm, clearance, c.pin_side))
    return specs


def result_collection(obj):
    """Existing build collection of ``obj`` or None.

    The collection references its owner object (an ID reference, so renaming
    the source keeps it). A duplicated source copies the
    ``last_build_collection`` pointer, but the collection still names the
    original as owner, so the duplicate gets its own collection.
    """
    stack = stack_api.get_stack(obj)
    for coll in (stack.last_build_collection,
                 bpy.data.collections.get(naming.build_collection_name(obj.name))):
        if coll is not None and coll.get(naming.PROP_OWNER) in (obj, None):
            return coll
    return None


def _managed_parts(coll):
    """Built parts in a build collection (anything carrying the source property)."""
    return [o for o in coll.objects if o.get(naming.PROP_SOURCE) is not None]


def _remove_objects(objs):
    for o in objs:
        mesh = o.data
        bpy.data.objects.remove(o)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def _find_layer_collection(layer_coll, coll):
    if layer_coll.collection == coll:
        return layer_coll
    for child in layer_coll.children:
        found = _find_layer_collection(child, coll)
        if found is not None:
            return found
    return None


def _prepare_collection(context, obj):
    """Build collection of ``obj`` (created if missing), linked and visible in the view layer."""
    scene = context.scene
    coll = result_collection(obj)
    name = naming.build_collection_name(obj.name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    elif coll.name != name and name not in bpy.data.collections:
        coll.name = name  # source was renamed
    coll[naming.PROP_OWNER] = obj
    if coll not in _all_children(scene.collection):
        scene.collection.children.link(coll)
    layer = _find_layer_collection(context.view_layer.layer_collection, coll)
    if layer is not None:
        layer.exclude = False
        layer.hide_viewport = False
    coll.hide_viewport = False
    stack_api.get_stack(obj).last_build_collection = coll
    return coll


def _all_children(coll):
    out = []
    for child in coll.children:
        out.append(child)
        out.extend(_all_children(child))
    return out


def build(context, obj):
    """Build the enabled cuts of ``obj``'s stack. Returns a BuildResult; raises BuildError."""
    stack = stack_api.get_stack(obj)
    if stack is None:
        raise BuildError("Active object is not a mesh")
    cuts = [c for c in stack.cuts if c.enabled]
    if not cuts:
        raise BuildError("No enabled cuts in the stack")
    scene = context.scene
    settings = getattr(scene, naming.SCENE_SETTINGS, None)
    warnings = []
    planes = cut_planes(obj, cuts, scene)
    bm = source_bmesh(obj, context.evaluated_depsgraph_get())
    if not bm.faces:
        bm.free()
        raise BuildError("Source mesh has no faces")
    source_bvh = BVHTree.FromBMesh(bm)  # keeps its own copy of the geometry
    pieces = cut_pieces(bm, planes, warnings)
    pins = sockets = None
    try:
        if len(pieces) < 2:
            raise BuildError("The cuts do not intersect the object")
        pins, sockets, conn_warnings, overlapping = conn_apply.assign(
            [p.bm for p in pieces], connector_specs(obj, cuts, scene, settings), source_bvh)
        warnings += conn_warnings

        coll = _prepare_collection(context, obj)
        old_parts = _managed_parts(coll)
        cut_ids = ",".join(c.uid for c in cuts)
        parts, names = [], []
        try:
            for piece in pieces:
                name = f"{obj.name}_{piece.sides}"
                names.append(name)
                mesh = bpy.data.meshes.new(name)
                piece.bm.to_mesh(mesh)
                part = bpy.data.objects.new(name, mesh)
                part[naming.PROP_SOURCE] = obj.name
                part[naming.PROP_SOURCE_OBJECT] = obj
                part[naming.PROP_CUT_IDS] = cut_ids
                coll.objects.link(part)
                parts.append(part)
            warnings += conn_apply.apply_to_parts(parts, pins, sockets, stack.solver, overlapping)
        except Exception:
            # Leave the previous result untouched; drop what this run created
            _remove_objects(parts)
            raise
    finally:
        for p in pieces:
            p.bm.free()
        for table in (pins, sockets):
            for bm in (table or {}).values():
                bm.free()

    # Success: replace the previous parts, then take over their names
    _remove_objects(old_parts)
    for part, name in zip(parts, names):
        part.name = name
        part.data.name = part.name

    if obj.name in context.view_layer.objects:
        obj.hide_set(True)
        obj.select_set(False)
    for part in parts:
        if part.name in context.view_layer.objects:
            part.select_set(True)
    context.view_layer.objects.active = parts[0]
    for w in warnings:
        log.warning(w)
    return BuildResult(coll.name, [p.name for p in parts], warnings)


def clear_build(context, obj):
    """Remove the build result of ``obj`` and show the source again. Returns removed part count."""
    stack = stack_api.get_stack(obj)
    coll = result_collection(obj)
    removed = 0
    if coll is not None:
        old = _managed_parts(coll)
        removed = len(old)
        _remove_objects(old)
        if not coll.objects and not coll.children:
            bpy.data.collections.remove(coll)
    stack.last_build_collection = None
    if obj.name in context.view_layer.objects:
        obj.hide_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
    return removed
