# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# connectors/auto.py
"""Automatic connector records for a cut.

Positions come from distribute_points over each seam region of the final parts,
inset by the connector's reach (radius + clearance + MIN_WALL_MM). Each position
is then checked in 3D (connectors/fit.py: pin and socket, for both pin sides,
inside the source with at least MIN_WALL_MM of material, not reaching across
any other enabled cut, not crossing its own curved seam, no thin feature
pierced) and against the connectors already placed (sockets at least
MIN_WALL_MM apart); a position that does not fit is moved step by step towards
the region's center and dropped if no step fits. Dropped positions are counted
with their reason.

Seam regions in (u, v) mm:

- planar cut: the section loops of each piece of the source cut by the OTHER
  enabled cuts (exact, bisect / booleans);
- stroke cut: the ribbon unrolled (u = arc length from the middle of the
  stroke, v = depth along the extrusion direction), sampled on a raster: a
  sample is material when it lies inside the source and outside the other
  cuts' gaps; samples are grouped by their side of each other cut, and each
  group's cell boundary gives the loops. The raster (at most RASTER_SAMPLES
  cells, at least RASTER_MIN_MM) only guides placement; the 3D check decides.
"""

import math
from collections import Counter
from dataclasses import dataclass, field

from mathutils.bvhtree import BVHTree

from ..core import meshlib, naming, units
from ..cuts import build
from ..model import stack as stack_api
from . import fit, placement

# Material kept around a pin or socket (mm)
MIN_WALL_MM = 0.4
MOVE_STEPS = 8
# Stroke seam raster: at most this many samples, cells at least this size (mm)
RASTER_SAMPLES = 30000
RASTER_MIN_MM = 0.25

REASONS = {
    "edge": "no room inside the seam outline",
    "surface": "would break through the surface",
    "other cut": "would reach across another cut",
    "own seam": "the curved seam bends into it",
    "spacing": "too close to another connector",
}


@dataclass
class AutoResult:
    added: int = 0
    moved: int = 0
    dropped: int = 0
    reasons: Counter = field(default_factory=Counter)

    def describe(self):
        """E.g. '2 would break through the surface, 1 would reach across another cut'."""
        return ", ".join(f"{n} {REASONS[r]}" for r, n in self.reasons.most_common())


def _plane_regions(context, obj, spec, others):
    co, n, t = spec.co, spec.n, spec.t
    b = n.cross(t)
    bm = build.source_bmesh(obj, context.evaluated_depsgraph_get())
    pieces = build.cut_pieces(bm, others, [])
    f = units.scene_to_mm(1.0, context.scene)
    regions = []
    try:
        for piece in pieces:
            loops = meshlib.section_loops_2d(piece.bm, co, n, t, b)
            if loops:
                regions.append([[(u * f, v * f) for u, v in loop] for loop in loops])
    finally:
        for piece in pieces:
            piece.bm.free()
    return regions


def stroke_regions(spec, source_bvh, others, corners, scene):
    """Seam regions of a StrokeCut (loops in mm in unrolled (u, v)), see module docstring."""
    cl = spec.centerline()
    cutter = spec.cutter
    ext0 = math.dist(cutter.extended[0], cutter.curve[0])
    ext1 = math.dist(cutter.extended[-1], cutter.curve[-1])
    u_lo, u_hi = -cl.total * 0.5 - ext0, cl.total * 0.5 + ext1
    depths = [cutter.frame.depth(c) for c in corners]
    v_lo, v_hi = min(depths), max(depths)
    step = max(math.sqrt(max(u_hi - u_lo, 1e-9) * max(v_hi - v_lo, 1e-9) / RASTER_SAMPLES),
               units.mm_to_scene(RASTER_MIN_MM, scene))
    nu = max(1, math.ceil((u_hi - u_lo) / step))
    nv = max(1, math.ceil((v_hi - v_lo) / step))
    barriers = [o.barrier() for o in others]
    labels = {}
    d = cutter.frame.d
    for i in range(nu):
        base = cl.frame_at(u_lo + (i + 0.5) * step, 0.0)[0]
        for j in range(nv):
            p = base + d * (v_lo + (j + 0.5) * step)
            if not fit.is_inside(source_bvh, p):
                continue
            label = []
            for bar in barriers:
                if isinstance(bar, fit.PlaneBarrier):
                    dist = (p - bar.co).dot(bar.n)
                    positive, dist = dist >= 0.0, abs(dist)
                else:
                    positive, dist = bar.positive(p), bar.distance(p)
                if dist < 0.5 * bar.gap:
                    break
                label.append(positive)
            else:
                labels[(i, j)] = tuple(label)
    f = units.scene_to_mm(1.0, scene)
    regions = []
    for key in sorted(set(labels.values())):
        loops = placement.mask_loops(lambda i, j: labels.get((i, j)) == key, nu, nv, u_lo, v_lo, step)
        if loops:
            regions.append([[(u * f, v * f) for u, v in loop] for loop in loops])
    return regions


def seam_regions_mm(context, obj, cut):
    """(regions, source_bvh) for ``cut``.

    ``regions``: seams of ``cut`` between final parts, each a list of (u, v)
    loops in mm (see module docstring): a seam crossed by another cut becomes
    separate regions, so no connector lands on another cut. ``source_bvh``:
    BVHTree of the uncut world-space source.
    """
    scene = context.scene
    stack = stack_api.get_stack(obj)
    spec = build.cut_spec(obj, cut, scene)
    others = build.cut_specs(obj, [c for c in stack.cuts if c.enabled and c.uid != cut.uid], scene)
    bm = build.source_bmesh(obj, context.evaluated_depsgraph_get())
    try:
        source_bvh = BVHTree.FromBMesh(bm)
    finally:
        bm.free()
    if spec.kind == 'STROKE':
        return stroke_regions(spec, source_bvh, others, build.world_corners(obj), scene), source_bvh
    return _plane_regions(context, obj, spec, others), source_bvh


def reach_mm(kind, width_mm, height_mm):
    """Largest in-plane distance of a connector's outline from its center (any rotation)."""
    if kind == 'RECT_TENON':
        return 0.5 * math.hypot(width_mm, height_mm)
    return 0.5 * width_mm


def add_auto(context, obj, cut, kind, width_mm, height_mm, length_mm, replace=True):
    """Fill ``cut.connectors`` from its distribution settings (per seam region).

    Returns an AutoResult (positions added / moved inward / dropped, with the
    reasons for the dropped ones). Nothing changes when no position fits (the
    cut misses the object, or every seam is too small for the connector).
    Raises build.BuildError for an invalid stroke cut.
    """
    scene = context.scene
    clearance = build.default_clearance(getattr(scene, naming.SCENE_SETTINGS, None))
    inset = reach_mm(kind, width_mm, height_mm) + clearance + MIN_WALL_MM
    spacing = 2.0 * (reach_mm(kind, width_mm, height_mm) + clearance) + MIN_WALL_MM
    wall = units.mm_to_scene(MIN_WALL_MM, scene)
    regions, bvh = seam_regions_mm(context, obj, cut)
    stack = stack_api.get_stack(obj)
    spec = build.cut_spec(obj, cut, scene)
    others = [s.barrier() for s in build.cut_specs(
        obj, [c for c in stack.cuts if c.enabled and c.uid != cut.uid], scene)]
    own = spec.barrier() if spec.kind == 'STROKE' else None
    step = units.mm_to_scene(build.FIT_STEP_MM, scene)

    def misfit(u, v):
        """'' when a connector at (u, v) fits in 3D, else the reason key."""
        cspec = build.make_spec(obj, cut, scene, "", u, v, 0.0, kind, width_mm, height_mm, length_mm,
                                clearance, 'A', spec)
        return fit.check(cspec, bvh, others, wall, both_sides=True, max_step=step, own=own).reason(wall)

    result, points = AutoResult(), []
    for loops in regions:
        cu, cv = placement.area_centroid(max(loops, key=meshlib.poly_area_2d))
        rejected = []
        for u, v in placement.distribute_points(loops, cut.distribution, cut.connector_count,
                                                cut.connector_rows, cut.margin_pct, inset, rejected):
            reason = ""
            for k in range(MOVE_STEPS + 1):
                f = k / MOVE_STEPS
                p = (u + (cu - u) * f, v + (cv - v) * f)
                if not placement.fits_2d(p, loops, inset):
                    reason = reason or "edge"
                    continue
                if not all(math.dist(p, q) >= spacing for q in points):
                    reason = "spacing"
                    continue
                reason = misfit(*p)
                if not reason:
                    points.append(p)
                    result.moved += k > 0
                    break
            else:
                result.dropped += 1
                result.reasons[reason or "edge"] += 1
        result.dropped += len(rejected)
        if rejected:
            result.reasons["edge"] += len(rejected)
    if not points:
        return result
    if replace:
        cut.connectors.clear()
    for u, v in points:
        c = cut.connectors.add()
        c.kind = kind
        c.u, c.v = u, v
        c.width_mm, c.height_mm, c.length_mm = width_mm, height_mm, length_mm
    cut.active_connector = max(0, len(cut.connectors) - 1)
    result.added = len(points)
    return result
