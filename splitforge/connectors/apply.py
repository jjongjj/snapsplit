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

import math
from dataclasses import dataclass

import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from ..core import boolean
from . import fit, shapes

# Samples may sit this far outside (fraction of the pin length): float noise on flush faces
SURFACE_TOLERANCE = 1e-4


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
    cut_uid: str = ""     # cut the connector belongs to (its plane is not an "other" plane)


def _containing_piece(bvhs, point):
    """Index of the closed piece containing ``point`` (None if outside all)."""
    best, best_dist = None, None
    for i, bvh in enumerate(bvhs):
        if not fit.is_inside(bvh, point):
            continue
        dist = bvh.find_nearest(point)[3]
        if best_dist is None or dist < best_dist:
            best, best_dist = i, dist
    return best


def _segment_distance(p0, p1, q0, q1):
    """Shortest distance between segments p0-p1 and q0-q1."""
    d1, d2, r = p1 - p0, q1 - q0, p0 - q0
    a, e, f = d1.dot(d1), d2.dot(d2), d2.dot(r)
    if a < 1e-18 and e < 1e-18:
        return r.length
    if a < 1e-18:
        s, t = 0.0, max(0.0, min(1.0, f / e))
    else:
        c = d1.dot(r)
        if e < 1e-18:
            s, t = max(0.0, min(1.0, -c / a)), 0.0
        else:
            b = d1.dot(d2)
            denom = a * e - b * b
            s = max(0.0, min(1.0, (b * f - c * e) / denom)) if denom > 1e-18 else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                s, t = max(0.0, min(1.0, -c / a)), 0.0
            elif t > 1.0:
                s, t = max(0.0, min(1.0, (b - c) / a)), 1.0
    return ((p0 + d1 * s) - (q0 + d2 * t)).length


def _capsules_touch(a, b):
    return _segment_distance(a[0], a[1], b[0], b[1]) < a[2] + b[2]


def assign(pieces, specs, source_bvh=None, planes=None, max_step=None):
    """Build the joined pin/socket operands per piece.

    ``pieces``: world-space bmeshes of the parts. With ``source_bvh`` (BVHTree of
    the uncut source) and ``planes`` ({cut uid: fit barrier} of the enabled
    cuts) a connector whose pin or socket would break through the outer surface,
    reach across another cut into a third part or cross its own curved seam is
    skipped with a warning (connectors/fit.py, samples at most ``max_step`` apart). Returns
    ``(pins, sockets, warnings, overlapping)``: ``pins``/``sockets`` are dicts
    piece index -> bmesh (caller frees them), ``overlapping`` the set of piece
    indices where two connector solids may intersect.
    """
    bvhs = [BVHTree.FromBMesh(bm) for bm in pieces]
    pins, sockets, warnings = {}, {}, []
    capsules, overlapping = {}, set()
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
        if source_bvh is not None:
            others = [pl for uid, pl in (planes or {}).items() if uid != spec.cut_uid]
            own = (planes or {}).get(spec.cut_uid)
            own = own if isinstance(own, fit.RibbonBarrier) else None
            tol = -SURFACE_TOLERANCE * spec.length
            res = fit.check(spec, source_bvh, others, tol, max_step=max_step, own=own)
            if res.plane_margin < tol:
                warnings.append(f"{spec.label}: pin or socket would reach across another cut into a part "
                                "without a socket, skipped (move it, or Distribute again)")
                continue
            if res.own_margin < 0.0:
                warnings.append(f"{spec.label}: the curved seam bends into the pin or socket, skipped "
                                "(move it to a flatter part of the seam, or use a shorter connector)")
                continue
            if not res.ok(tol):
                warnings.append(f"{spec.label}: pin or socket would break through the outer surface, skipped "
                                "(move it inward, or Distribute again)")
                continue
        pin_span, socket_span = shapes.pin_and_socket_spans(
            spec.length, spec.clearance, spec.gap, spec.pin_positive)
        # Capsule around pin + socket: axis segment and in-plane reach
        zs = pin_span + socket_span
        capsule = (spec.matrix @ Vector((0.0, 0.0, min(zs))), spec.matrix @ Vector((0.0, 0.0, max(zs))),
                   0.5 * math.hypot(spec.width, spec.height if spec.kind == 'RECT_TENON' else 0.0)
                   + spec.clearance)
        for piece in (pin_piece, socket_piece):
            if any(_capsules_touch(capsule, other) for other in capsules.get(piece, ())):
                overlapping.add(piece)
            capsules.setdefault(piece, []).append(capsule)
        shapes.add_solid(pins.setdefault(pin_piece, bmesh.new()), spec.kind, spec.width, spec.height,
                         *pin_span, spec.matrix)
        c2 = 2.0 * spec.clearance
        shapes.add_solid(sockets.setdefault(socket_piece, bmesh.new()), spec.kind, spec.width + c2,
                         spec.height + c2, *socket_span, spec.matrix)
    return pins, sockets, warnings, overlapping


def operations(pins, sockets):
    """[(piece index, operand bmesh, operation)] in the order apply_step runs them."""
    out = []
    for index in sorted(set(pins) | set(sockets)):
        for table, operation in ((pins, 'UNION'), (sockets, 'DIFFERENCE')):
            if index in table:
                out.append((index, table[index], operation))
    return out


def apply_step(obj, operand, operation, preference='AUTO', self_intersect=False):
    """One connector boolean on a part. Returns the BooleanResult.

    The part must have an identity transform (its mesh is in world space) and be
    visible in the view layer; the caller frees the operand bmesh.
    ``self_intersect``: the operand has intersecting solids, or the part has
    intersecting shells (the exact solver then needs self-intersection handling).
    """
    return boolean.apply(obj, operand, operation, preference, self_intersect=self_intersect)


def apply_to_parts(part_objects, pins, sockets, preference='AUTO', overlapping=()):
    """One UNION (pins) and one DIFFERENCE (sockets) per part. Returns warnings.

    ``overlapping``: piece indices whose boolean needs self-intersection handling.
    """
    warnings = []
    for index, operand, operation in operations(pins, sockets):
        result = apply_step(part_objects[index], operand, operation, preference, index in overlapping)
        if not result.ok:
            warnings.append(result.message)
    return warnings
