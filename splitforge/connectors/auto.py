# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# connectors/auto.py
"""Automatic connector records for a cut: seam regions of the final parts + distribute_points."""

from ..core import meshlib, units
from ..cuts import build, plane
from ..model import stack as stack_api
from . import placement


def seam_regions_mm(context, obj, cut):
    """Seams of ``cut`` between final parts, each a list of (u, v) loops in mm.

    The source is first cut by every OTHER enabled cut of the stack (with their
    gaps), then each piece is sectioned by this cut: a seam crossed by another
    cut becomes separate regions, so no connector lands on another cut plane.
    """
    stack = stack_api.get_stack(obj)
    others = [c for c in stack.cuts if c.enabled and c.uid != cut.uid]
    co, n, t, b = plane.world_frame(obj.matrix_world, cut.origin, cut.normal, cut.tangent)
    pieces = build.cut_pieces(build.source_bmesh(obj, context.evaluated_depsgraph_get()),
                              build.cut_planes(obj, others, context.scene), [])
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


def add_auto(context, obj, cut, kind, width_mm, height_mm, length_mm, replace=True):
    """Fill ``cut.connectors`` from its distribution settings (per seam region).

    Returns the number added; nothing changes when the seam is empty (the cut misses the object).
    """
    points = []
    for loops in seam_regions_mm(context, obj, cut):
        points += placement.distribute_points(loops, cut.distribution, cut.connector_count,
                                              cut.connector_rows, cut.margin_pct)
    if not points:
        return 0
    if replace:
        cut.connectors.clear()
    for u, v in points:
        c = cut.connectors.add()
        c.kind = kind
        c.u, c.v = u, v
        c.width_mm, c.height_mm, c.length_mm = width_mm, height_mm, length_mm
    cut.active_connector = max(0, len(cut.connectors) - 1)
    return len(points)
