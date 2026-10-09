# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# cuts/polyline.py
"""Polyline (manual points) cut: straight segments between clicked points.

A polyline cut is a ribbon cut like a stroke (cuts/stroke.py: the points on the
plane through the object's center facing the view, extruded along the view
direction, ends extended straight to beyond the object, gap as two offset
ribbons, same validity rules) whose points are kept as clicked: no resampling
or smoothing, so the corners stay sharp. Its connector frame uses the segment
directions (``stroke.Centerline(sharp=True)``): a pin stands square on the flat
face of its segment; the curved-seam check keeps connectors away from corners.

Screen-space helpers for the click modal (ops/ops_cut_points.py) live here so
they can be tested without a viewport.
"""

import math

# Ctrl while placing a point: the segment direction snaps to multiples of this angle on screen
SNAP_DEGREES = 15.0
# A click within this many pixels of the first point closes a polygon
CLOSE_PIXELS = 12.0


def snap_screen(prev, cur, step_deg=SNAP_DEGREES):
    """``cur`` moved so the screen direction prev -> cur is a multiple of ``step_deg`` (length kept)."""
    dx, dy = cur[0] - prev[0], cur[1] - prev[1]
    length = math.hypot(dx, dy)
    if length == 0.0:
        return tuple(cur)
    step = math.radians(step_deg)
    a = round(math.atan2(dy, dx) / step) * step
    return (prev[0] + length * math.cos(a), prev[1] + length * math.sin(a))


def near(a, b, pixels=CLOSE_PIXELS):
    return math.dist(a, b) <= pixels
