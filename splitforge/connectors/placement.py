# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# connectors/placement.py
"""Connector placement on a seam: the single source of truth.

A seam frame is (co, n, t, b): a point on the cut plane, the unit normal, the
unit tangent (U axis) and b = n x t (V axis). A connector at (u, v, rotation)
sits at ``co + t*u + b*v`` with its local Z along ``n`` and its local X
rotated by ``rotation`` from ``t`` around ``n``. Build, auto distribution and
the viewport overlay all call ``frame_matrix``/``distribute_points``.

Pure functions (mathutils only); lengths are in whatever unit the caller uses
consistently (the operators use millimeters for u/v and seam outlines).
"""

import math

from mathutils import Matrix, Vector

from ..core import meshlib


def frame_matrix(co, n, t, u=0.0, v=0.0, rotation_deg=0.0):
    """World matrix of a connector at (u, v) on the seam frame, rotated around n."""
    n, t, b = meshlib.orthonormal_basis(n, t)
    a = math.radians(rotation_deg)
    x = t * math.cos(a) + b * math.sin(a)
    y = n.cross(x)
    loc = Vector(co) + t * u + b * v
    m = Matrix.Identity(4)
    for row in range(3):
        m[row][0], m[row][1], m[row][2], m[row][3] = x[row], y[row], n[row], loc[row]
    return m


def seam_coords(co, n, t, point):
    """(u, v) of a world point projected onto the seam frame."""
    n, t, b = meshlib.orthonormal_basis(n, t)
    d = Vector(point) - Vector(co)
    return d.dot(t), d.dot(b)


def _bounds(loops):
    us = [p[0] for loop in loops for p in loop]
    vs = [p[1] for loop in loops for p in loop]
    return min(us), max(us), min(vs), max(vs)


def line_intervals(loops, axis, value):
    """Inside intervals (even-odd) of the line ``coord[axis] == value`` across the loops.

    Returns sorted (start, end) pairs along the other axis.
    """
    other = 1 - axis
    hits = []
    for loop in loops:
        n = len(loop)
        for i in range(n):
            p, q = loop[i], loop[(i + 1) % n]
            if (p[axis] > value) != (q[axis] > value):
                f = (value - p[axis]) / (q[axis] - p[axis])
                hits.append(p[other] + f * (q[other] - p[other]))
    hits.sort()
    return [(hits[i], hits[i + 1]) for i in range(0, len(hits) - 1, 2)]


def edge_distance(point, loops):
    """Distance of a 2D point to the nearest loop edge."""
    px, py = point
    best = math.inf
    for loop in loops:
        n = len(loop)
        for i in range(n):
            (x0, y0), (x1, y1) = loop[i], loop[(i + 1) % n]
            dx, dy = x1 - x0, y1 - y0
            ll = dx * dx + dy * dy
            f = 0.0 if ll == 0.0 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / ll))
            best = min(best, math.hypot(px - (x0 + f * dx), py - (y0 + f * dy)))
    return best


def fits_2d(point, loops, inset=0.0):
    """Inside the material (even-odd) and at least ``inset`` away from every edge."""
    return meshlib.point_in_polys_2d(point, loops) and edge_distance(point, loops) >= inset


def area_centroid(loop):
    """Area centroid of a closed 2D loop (vertex mean for degenerate loops)."""
    a = cx = cy = 0.0
    n = len(loop)
    for i in range(n):
        (x0, y0), (x1, y1) = loop[i], loop[(i + 1) % n]
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    if abs(a) < 1e-12:
        return sum(p[0] for p in loop) / n, sum(p[1] for p in loop) / n
    return cx / (3.0 * a), cy / (3.0 * a)


def _spread(lo, hi, count, margin_pct, inset=0.0):
    # A hair inside even at 0 %: a line exactly on the outline crosses nothing
    m = max((hi - lo) * max(margin_pct / 100.0, 1e-6), inset)
    lo, hi = lo + m, hi - m
    if lo > hi:
        return []
    if count == 1:
        return [(lo + hi) * 0.5]
    return [lo + (hi - lo) * i / (count - 1) for i in range(count)]


def distribute_points(loops, distribution='LINE', count=2, rows=2, margin_pct=15.0, inset=0.0):
    """Connector positions (u, v) inside a seam outline.

    ``loops``: closed 2D loops of the seam section (outer loops and holes,
    even-odd). LINE spreads ``count`` points along the longer extent of the
    outline, each centered in the widest material interval across the line
    (so hollow walls get their pin in the wall). GRID lays ``count`` x ``rows``
    points over the bounds and keeps those inside the material. ``margin_pct``
    is kept free at both ends, as percent of the extent. ``inset`` is the
    smallest allowed distance from a seam edge (connector radius + clearance +
    wall); points closer to an edge are dropped.
    """
    loops = [loop for loop in loops if len(loop) >= 3]
    if not loops or count < 1:
        return []
    u0, u1, v0, v1 = _bounds(loops)
    if distribution == 'GRID':
        points = []
        for v in _spread(v0, v1, max(1, rows), margin_pct, inset):
            for u in _spread(u0, u1, count, margin_pct, inset):
                if fits_2d((u, v), loops, inset):
                    points.append((u, v))
        return points

    axis = 0 if (u1 - u0) >= (v1 - v0) else 1
    lo, hi = (u0, u1) if axis == 0 else (v0, v1)
    mid = (v0 + v1) * 0.5 if axis == 0 else (u0 + u1) * 0.5
    points = []
    for s in _spread(lo, hi, count, margin_pct, inset):
        intervals = [(b + inset, e - inset) for b, e in line_intervals(loops, axis, s) if e - b > 2 * inset]
        if not intervals:
            continue
        widest = max(e - b for b, e in intervals)
        # Widest interval; among (nearly) equally wide ones the one closest to the middle
        b, e = min((iv for iv in intervals if iv[1] - iv[0] >= 0.9 * widest),
                   key=lambda iv: abs((iv[0] + iv[1]) * 0.5 - mid))
        c = (b + e) * 0.5
        point = (s, c) if axis == 0 else (c, s)
        if fits_2d(point, loops, inset):
            points.append(point)
    return points
