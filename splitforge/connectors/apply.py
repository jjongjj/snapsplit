# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# connectors/apply.py
"""Pins (UNION) and sockets (DIFFERENCE) on built parts.

All connectors of a build are first assigned to parts: the pin goes to the
part just behind the seam on the pin side, the socket to the part on the other
side (point-in-mesh probes, so any number of earlier/later cuts works). A
double-sided dowel has a socket in both parts and becomes a separate dowel
part. The solids of one part (connectors/shapes.py) are joined into a single
operand, so every part gets at most one UNION and one DIFFERENCE, however many
connectors it carries. A connector whose own solids overlap (snap bumps on their
pin, a custom mesh) is first united into one clean solid; connectors placed into
each other mark the part, so its booleans use self-intersection handling.
"""

from dataclasses import dataclass, field

import bmesh
import bpy
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
    taper: float = 0.0            # DOVETAIL kinds: fraction of the width the tip loses
    embed: float = 0.5            # share of the length inside the pin part
    chamfer: float = 0.0          # pin tip / dowel end chamfer
    snap_count: int = 2           # SNAP kinds: bumps around the pin
    snap_diameter: float = 2.0
    snap_protrusion: float = 0.6  # how far a bump stands out of the pin surface
    custom: object = None         # CUSTOM: shapes.CustomShape


@dataclass
class DowelSpec:
    """A separate dowel part (world-space lengths, Blender units)."""
    label: str
    diameter: float
    length: float
    chamfer: float
    matrix: Matrix = None     # connector frame (Z = dowel axis, origin on the seam): assembly position


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
    skipped with a warning (connectors/fit.py, samples at most ``max_step`` apart).
    Returns ``Assignment`` (``pins``/``sockets``: dicts piece index -> bmesh, the
    caller frees them; ``overlapping``: piece indices whose operands have
    intersecting solids; ``dowels``: DowelSpec list).
    """
    bvhs = [BVHTree.FromBMesh(bm) for bm in pieces]
    out = Assignment()
    capsules = {}
    for spec in specs:
        center = spec.matrix.translation
        n = Vector(spec.matrix.col[2][:3]).normalized()
        positive = spec.pin_positive or spec.kind == 'DOWEL'
        s = 1.0 if positive else -1.0
        depth = spec.gap * 0.5 + 0.25 * spec.length
        pin_piece = _containing_piece(bvhs, center + n * (s * depth))
        socket_piece = _containing_piece(bvhs, center - n * (s * depth))
        if pin_piece is None or socket_piece is None or pin_piece == socket_piece:
            out.warnings.append(f"{spec.label}: not on a seam between two parts, skipped")
            continue
        if source_bvh is not None:
            others = [pl for uid, pl in (planes or {}).items() if uid != spec.cut_uid]
            own = (planes or {}).get(spec.cut_uid)
            own = own if isinstance(own, fit.RibbonBarrier) else None
            tol = -SURFACE_TOLERANCE * spec.length
            res = fit.check(spec, source_bvh, others, tol, max_step=max_step, own=own)
            if res.plane_margin < tol:
                out.warnings.append(f"{spec.label}: pin or socket would reach across another cut into a part "
                                    "without a socket, skipped (move it, or Distribute again)")
                continue
            if res.own_margin < 0.0:
                out.warnings.append(f"{spec.label}: the curved seam bends into the pin or socket, skipped "
                                    "(move it to a flatter part of the seam, or use a shorter connector)")
                continue
            if not res.ok(tol):
                out.warnings.append(f"{spec.label}: pin or socket would break through the outer surface, "
                                    "skipped (move it inward, or Distribute again)")
                continue
        solids = shapes.connector_solids(spec)
        out.warnings += [f"{spec.label}: {note}" for note in solids.notes]
        capsule = shapes.capsule(spec, solids)
        for piece in (pin_piece, socket_piece):
            if any(_capsules_touch(capsule, other) for other in capsules.get(piece, ())):
                out.overlapping.add(piece)
            capsules.setdefault(piece, []).append(capsule)
        for table, piece, group in ((out.pins, pin_piece, solids.pin),
                                    (out.sockets, pin_piece, solids.pin_socket),
                                    (out.sockets, socket_piece, solids.socket)):
            if not group:
                continue
            target = table.setdefault(piece, bmesh.new())
            if len(group) == 1 and spec.kind != 'CUSTOM':
                group[0].add_to(target)
                continue
            # Snap bumps overlap their pin (dimples their socket), an offset custom mesh may fold:
            # unite them into one clean solid first (small), so the part's boolean needs no
            # self-intersection handling (slow on large parts); if that fails, the part gets it.
            joined = bmesh.new()
            try:
                for solid in group:
                    solid.add_to(joined)
                united, _why = boolean.unite_bm(joined)
                if united is None:
                    out.overlapping.add(piece)
                    _append(target, joined)
                else:
                    _append(target, united)
                    united.free()
            finally:
                joined.free()
        if solids.dowel is not None:
            out.dowels.append(DowelSpec(spec.label, *solids.dowel, matrix=spec.matrix.copy()))
    return out


def _append(dst, src):
    """Add the geometry of bmesh ``src`` to bmesh ``dst`` (through a temporary mesh)."""
    mesh = bpy.data.meshes.new("_SplitForge_Append")
    try:
        src.to_mesh(mesh)
        dst.from_mesh(mesh)
    finally:
        bpy.data.meshes.remove(mesh)


@dataclass
class Assignment:
    pins: dict = field(default_factory=dict)
    sockets: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    overlapping: set = field(default_factory=set)
    dowels: list = field(default_factory=list)


def operations(pins, sockets):
    """[(piece index, operand bmesh, operation)] in the order apply_step runs them."""
    out = []
    for index in sorted(set(pins) | set(sockets)):
        for table, operation in ((pins, 'UNION'), (sockets, 'DIFFERENCE')):
            if index in table:
                out.append((index, table[index], operation))
    return out


def apply_step(obj, operand, operation, quality='AUTO', self_intersect=False):
    """One connector boolean on a part. Returns the BooleanResult.

    The part must have an identity transform (its mesh is in world space) and be
    visible in the view layer; the caller frees the operand bmesh.
    ``self_intersect``: the operand has intersecting solids, or the part has
    intersecting shells (the exact solver then needs self-intersection handling).
    """
    return boolean.apply(obj, operand, operation, quality, self_intersect=self_intersect)


def apply_to_parts(part_objects, pins, sockets, quality='AUTO', overlapping=()):
    """One UNION (pins) and one DIFFERENCE (sockets) per part. Returns warnings.

    ``overlapping``: piece indices whose boolean needs self-intersection handling.
    """
    warnings = []
    for index, operand, operation in operations(pins, sockets):
        result = apply_step(part_objects[index], operand, operation, quality, index in overlapping)
        if not result.ok:
            warnings.append(result.message)
    return warnings
