# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# connectors/auto.py
"""Automatic connector records for a cut.

Positions come from distribute_points over each seam region of the final parts,
inset by the connector's reach (radius + clearance + MIN_WALL_MM). Each position
is then checked in 3D (connectors/fit.py: pin and socket, for both pin sides,
inside the source with at least MIN_WALL_MM of material, not reaching across
any other enabled cut, no thin feature pierced) and against the connectors
already placed (sockets at least MIN_WALL_MM apart); a position that
does not fit is moved step by step towards the region's center and dropped if
no step fits.
"""

import math
from dataclasses import dataclass

from mathutils.bvhtree import BVHTree

from ..core import meshlib, naming, units
from ..cuts import build, plane
from ..model import stack as stack_api
from . import fit, placement

# Material kept around a pin or socket (mm)
MIN_WALL_MM = 0.4
MOVE_STEPS = 8


@dataclass
class AutoResult:
    added: int = 0
    moved: int = 0
    dropped: int = 0


def seam_regions_mm(context, obj, cut):
    """(regions, source_bvh) for ``cut``.

    ``regions``: seams of ``cut`` between final parts, each a list of (u, v)
    loops in mm. The source is first cut by every OTHER enabled cut of the stack
    (with their gaps), then each piece is sectioned by this cut: a seam crossed
    by another cut becomes separate regions, so no connector lands on another
    cut plane. ``source_bvh``: BVHTree of the uncut world-space source.
    """
    stack = stack_api.get_stack(obj)
    others = [c for c in stack.cuts if c.enabled and c.uid != cut.uid]
    co, n, t, b = plane.world_frame(obj.matrix_world, cut.origin, cut.normal, cut.tangent)
    bm = build.source_bmesh(obj, context.evaluated_depsgraph_get())
    source_bvh = BVHTree.FromBMesh(bm)
    pieces = build.cut_pieces(bm, build.cut_planes(obj, others, context.scene), [])
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
    return regions, source_bvh


def reach_mm(kind, width_mm, height_mm):
    """Largest in-plane distance of a connector's outline from its center (any rotation)."""
    if kind == 'RECT_TENON':
        return 0.5 * math.hypot(width_mm, height_mm)
    return 0.5 * width_mm


def add_auto(context, obj, cut, kind, width_mm, height_mm, length_mm, replace=True):
    """Fill ``cut.connectors`` from its distribution settings (per seam region).

    Returns an AutoResult (positions added / moved inward / dropped). Nothing
    changes when no position fits (the cut misses the object, or every seam is
    too small for the connector).
    """
    scene = context.scene
    clearance = build.default_clearance(getattr(scene, naming.SCENE_SETTINGS, None))
    inset = reach_mm(kind, width_mm, height_mm) + clearance + MIN_WALL_MM
    spacing = 2.0 * (reach_mm(kind, width_mm, height_mm) + clearance) + MIN_WALL_MM
    wall = units.mm_to_scene(MIN_WALL_MM, scene)
    regions, bvh = seam_regions_mm(context, obj, cut)
    stack = stack_api.get_stack(obj)
    others = [pl for uid, pl in build.fit_planes(obj, [c for c in stack.cuts if c.enabled], scene).items()
              if uid != cut.uid]
    step = units.mm_to_scene(build.FIT_STEP_MM, scene)

    def fits(u, v):
        spec = build.make_spec(obj, cut, scene, "", u, v, 0.0, kind, width_mm, height_mm, length_mm,
                               clearance, 'A')
        return fit.check(spec, bvh, others, wall, both_sides=True, max_step=step).ok(wall)

    result, points = AutoResult(), []
    for loops in regions:
        cu, cv = placement.area_centroid(max(loops, key=meshlib.poly_area_2d))
        for u, v in placement.distribute_points(loops, cut.distribution, cut.connector_count,
                                                cut.connector_rows, cut.margin_pct, inset):
            for k in range(MOVE_STEPS + 1):
                f = k / MOVE_STEPS
                p = (u + (cu - u) * f, v + (cv - v) * f)
                if (placement.fits_2d(p, loops, inset)
                        and all(math.dist(p, q) >= spacing for q in points) and fits(*p)):
                    points.append(p)
                    result.moved += k > 0
                    break
            else:
                result.dropped += 1
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
