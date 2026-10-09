# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# connectors/apply.py
"""Pins (UNION) and sockets (DIFFERENCE) on built parts.

All connectors of a build are first assigned to parts: the pin goes to the
part just behind the seam on the pin side, the socket to the part on the other
side (point-in-mesh probes, so any number of earlier/later cuts works). The
solids of one part are joined into a single operand, so every part gets at most
one UNION and one DIFFERENCE, however many connectors it carries.
"""

from dataclasses import dataclass

import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from ..core import boolean
from . import shapes


@dataclass
class ConnectorSpec:
    """One connector in world space; lengths in Blender units."""
    label: str
    matrix: Matrix        # placement.frame_matrix(...): Z = cut normal
    kind: str
    width: float
    height: float
    length: float
    clearance: float
    gap: float
    pin_positive: bool


def _containing_piece(bvhs, point):
    """Index of the closed piece containing ``point`` (None if outside all)."""
    best, best_dist = None, None
    for i, bvh in enumerate(bvhs):
        co, normal, _index, dist = bvh.find_nearest(point)
        if co is None or (point - co).dot(normal) >= 0.0:
            continue
        if best_dist is None or dist < best_dist:
            best, best_dist = i, dist
    return best


def assign(pieces, specs):
    """Build the joined pin/socket operands per piece.

    ``pieces``: world-space bmeshes of the parts. Returns
    ``(pins, sockets, warnings, overlapping)``: ``pins``/``sockets`` are dicts
    piece index -> bmesh (caller frees them), ``overlapping`` the set of piece
    indices where two connector solids may intersect.
    """
    bvhs = [BVHTree.FromBMesh(bm) for bm in pieces]
    pins, sockets, warnings = {}, {}, []
    spheres, overlapping = {}, set()
    for spec in specs:
        center = spec.matrix.translation
        n = Vector(spec.matrix.col[2][:3]).normalized()
        s = 1.0 if spec.pin_positive else -1.0
        depth = spec.gap * 0.5 + 0.25 * spec.length
        pin_piece = _containing_piece(bvhs, center + n * (s * depth))
        socket_piece = _containing_piece(bvhs, center - n * (s * depth))
        if pin_piece is None or socket_piece is None or pin_piece == socket_piece:
            warnings.append(f"{spec.label}: not on a seam between two parts, skipped")
            continue
        radius = 0.5 * (Vector((spec.width, spec.height, spec.length)).length + 2.0 * spec.clearance)
        for piece in (pin_piece, socket_piece):
            if any((center - c).length < radius + r for c, r in spheres.get(piece, ())):
                overlapping.add(piece)
            spheres.setdefault(piece, []).append((center.copy(), radius))
        pin_span, socket_span = shapes.pin_and_socket_spans(
            spec.length, spec.clearance, spec.gap, spec.pin_positive)
        shapes.add_solid(pins.setdefault(pin_piece, bmesh.new()), spec.kind, spec.width, spec.height,
                         *pin_span, spec.matrix)
        c2 = 2.0 * spec.clearance
        shapes.add_solid(sockets.setdefault(socket_piece, bmesh.new()), spec.kind, spec.width + c2,
                         spec.height + c2, *socket_span, spec.matrix)
    return pins, sockets, warnings, overlapping


def apply_to_parts(part_objects, pins, sockets, preference='AUTO', overlapping=()):
    """One UNION (pins) and one DIFFERENCE (sockets) per part. Returns warnings.

    Part objects must have identity transforms (their mesh is in world space)
    and be visible in the view layer. The caller frees the operand bmeshes.
    ``overlapping``: piece indices whose joined operand has intersecting solids
    (the exact solver then needs self-intersection handling).
    """
    warnings = []
    for index, obj in enumerate(part_objects):
        for table, operation in ((pins, 'UNION'), (sockets, 'DIFFERENCE')):
            bm = table.get(index)
            if bm is None:
                continue
            result = boolean.apply(obj, bm, operation, preference, self_intersect=index in overlapping)
            if not result.ok:
                warnings.append(result.message)
    return warnings
