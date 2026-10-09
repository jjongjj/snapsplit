# SPDX-License-Identifier: GPL-3.0-or-later
"""P1-8: connectors/placement.py is the single placement implementation.

frame_matrix maps (u, v, rotation) on a seam frame to world space; distribute_points
spreads LINE/GRID positions inside a seam outline (also into the walls of a hollow seam).
"""

import math
import os
import re

from mathutils import Vector

import lib


def _close(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def run(ctx):
    pl = ctx.module("connectors.placement")
    meshlib = ctx.module("core.meshlib")

    # Unit frame: u along X, v along Y, Z = normal
    m = pl.frame_matrix(Vector((0, 0, 0)), Vector((0, 0, 1)), Vector((1, 0, 0)), u=5.0, v=0.0)
    assert _close(m.translation, (5, 0, 0)), m.translation
    assert _close(m.col[2][:3], (0, 0, 1))
    m = pl.frame_matrix(Vector((1, 2, 3)), Vector((0, 0, 1)), Vector((1, 0, 0)), u=5.0, v=-2.0)
    assert _close(m.translation, (6, 0, 3)), m.translation

    # Frame rotated 90 deg around Z (tangent = Y): u moves along Y, v along -X
    m = pl.frame_matrix(Vector(), Vector((0, 0, 1)), Vector((0, 1, 0)), u=5.0, v=3.0)
    assert _close(m.translation, (-3, 5, 0)), m.translation
    # Tilted frame: normal X, tangent Y -> b = X x Y = Z
    m = pl.frame_matrix(Vector(), Vector((1, 0, 0)), Vector((0, 1, 0)), u=2.0, v=4.0)
    assert _close(m.translation, (0, 2, 4)), m.translation
    assert _close(m.col[2][:3], (1, 0, 0))
    # In-plane rotation turns the local X axis, keeps the position and normal
    m = pl.frame_matrix(Vector(), Vector((0, 0, 1)), Vector((1, 0, 0)), u=1.0, rotation_deg=90.0)
    assert _close(m.col[0][:3], (0, 1, 0)) and _close(m.col[1][:3], (-1, 0, 0)), m
    assert _close(m.translation, (1, 0, 0))
    assert abs(m.to_3x3().determinant() - 1.0) < 1e-9
    # seam_coords is the inverse for points on the plane
    u, v = pl.seam_coords(Vector((1, 2, 3)), Vector((0, 0, 1)), Vector((1, 0, 0)), Vector((4, -1, 3)))
    assert _close((u, v), (3, -3))

    # LINE: 3 points, 10 % margin, inside a 40 x 20 seam (longer extent = U)
    rect = [[(-20, -10), (20, -10), (20, 10), (-20, 10)]]
    pts = pl.distribute_points(rect, 'LINE', 3, margin_pct=10.0)
    assert _close([p[0] for p in pts], (-16, 0, 16)) and all(abs(p[1]) < 1e-9 for p in pts), pts
    for u, v in pts:
        assert -20 < u < 20 and -10 < v < 10
    assert pl.distribute_points(rect, 'LINE', 1) == [(0.0, 0.0)]
    # Taller than wide -> the line runs along V
    tall = [[(-5, -30), (5, -30), (5, 30), (-5, 30)]]
    pts = pl.distribute_points(tall, 'LINE', 2, margin_pct=0.0)
    assert _close(pts[0], (0, -30), 1e-3) and _close(pts[1], (0, 30), 1e-3), pts

    # Hollow seam (40 outer, 36 inner): line points sit in the 2 mm walls, not in the cavity
    ring = [[(-20, -20), (20, -20), (20, 20), (-20, 20)], [(-18, -18), (-18, 18), (18, 18), (18, -18)]]
    pts = pl.distribute_points(ring, 'LINE', 3, margin_pct=10.0)
    assert len(pts) == 3
    for p in pts:
        assert meshlib.point_in_polys_2d(p, ring), f"{p} in the cavity"
        assert abs(abs(p[1]) - 19.0) < 1e-6, p

    # GRID drops points in holes
    grid = pl.distribute_points(ring, 'GRID', 3, rows=3, margin_pct=0.0)
    assert len(grid) == 8 and all(abs(u) > 1 or abs(v) > 1 for u, v in grid), grid
    assert all(meshlib.point_in_polys_2d(p, ring) for p in grid), grid
    assert pl.distribute_points([], 'LINE', 3) == []

    # Inset: every point keeps the connector reach from all seam edges
    tri = [[(0, 0), (30, 0), (0, 12)]]
    for dist in ('LINE', 'GRID'):
        pts = pl.distribute_points(tri, dist, 4, rows=3, margin_pct=0.0, inset=3.0)
        assert pts, dist
        for p in pts:
            assert pl.edge_distance(p, tri) >= 3.0 - 1e-9, (dist, p)
    assert pl.distribute_points(rect, 'LINE', 3, inset=11.0) == []  # 20 mm wide seam, 22 mm needed
    assert _close(pl.area_centroid(rect[0]), (0, 0)) and _close(pl.area_centroid(tri[0]), (10, 4))

    # Exactly one distribute_points implementation in connectors/
    root = os.path.dirname(os.path.dirname(pl.__file__))
    defs = []
    for dirpath, _dirs, files in os.walk(os.path.join(root, "connectors")):
        for f in files:
            if f.endswith(".py"):
                with open(os.path.join(dirpath, f), encoding="utf-8") as fh:
                    defs += re.findall(r"^def distribute_points\b", fh.read(), re.M)
    assert len(defs) == 1, defs
