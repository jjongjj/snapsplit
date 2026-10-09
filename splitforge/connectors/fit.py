# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# connectors/fit.py
"""Does a connector stay inside its own two parts?

A pin sticks out of its face by length/2 along the cut normal and the socket
reaches length/2 + clearance into the other side. Two things can go wrong:

- On an oblique cut the walls are slanted against that axis, so the pin or
  socket can break through the OUTER surface (defect D1).
- The pin or socket can cross ANOTHER cut plane and end up in a third part
  that has no matching socket (defect D7): the parts collide on assembly.

``check`` samples the outer surface of the pin and socket solids (the spans
and sizes Build uses) on a grid with at most ``max_step`` spacing and tests:

1. every OTHER enabled cut plane: all samples stay on the connector's side,
   beyond that cut's half gap plus the wall margin;
2. the uncut source: every sample is inside (nearest-face normal, confirmed by
   ray parity when in doubt) and at least ``wall`` deep;
3. no segment between neighbouring samples crosses the source surface, so
   features thinner than the sample spacing are not pierced silently.

Pure mathutils (BVHTree of the world-space source), no Blender data.
"""

import math
from dataclasses import dataclass

from mathutils import Vector

from . import shapes

MIN_RING = 24
MIN_RINGS = 9
# Skewed directions for the parity test (never parallel to axis-aligned faces/edges)
_RAY_DIRS = (Vector((0.5773, 0.5774, 0.5775)).normalized(),
             Vector((-0.7071, 0.1234, 0.6963)).normalized(),
             Vector((0.2311, -0.9123, 0.3379)).normalized())


@dataclass
class FitResult:
    plane_margin: float = math.inf      # smallest clearance to another cut (beyond its half gap)
    surface_depth: float = math.inf     # smallest depth inside the source
    pierced: bool = False               # a sample segment crosses the source surface

    def ok(self, wall):
        return self.plane_margin >= wall and self.surface_depth >= wall and not self.pierced


def _outline(kind, width, height, max_step=None):
    """Closed cross-section outline (local XY) of a CYL_PIN or RECT_TENON."""
    if kind == 'RECT_TENON':
        hw, hh = width * 0.5, height * 0.5
        per_edge = 4 if not max_step else max(4, math.ceil(max(width, height) / max_step))
        pts = []
        for (x0, y0), (x1, y1) in (((-hw, -hh), (hw, -hh)), ((hw, -hh), (hw, hh)),
                                   ((hw, hh), (-hw, hh)), ((-hw, hh), (-hw, -hh))):
            pts += [(x0 + (x1 - x0) * k / per_edge, y0 + (y1 - y0) * k / per_edge) for k in range(per_edge)]
        return pts
    r = width * 0.5
    n = MIN_RING if not max_step else max(MIN_RING, math.ceil(2 * math.pi * r / max_step))
    return [(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def solid_grid(kind, width, height, z0, z1, matrix, max_step=None):
    """Point rings covering the side of a connector solid, plus the two cap centers.

    Returns ``(rings, caps)``: closed world-space point rings from z0 to z1,
    and the cap centers at z0 and z1.
    """
    outline = _outline(kind, width, height, max_step)
    n_rings = MIN_RINGS if not max_step else max(MIN_RINGS, math.ceil(abs(z1 - z0) / max_step) + 1)
    rings = []
    for k in range(n_rings):
        z = z0 + (z1 - z0) * k / (n_rings - 1)
        rings.append([matrix @ Vector((x, y, z)) for x, y in outline])
    return rings, [matrix @ Vector((0.0, 0.0, z)) for z in (z0, z1)]


def solid_samples(kind, width, height, z0, z1, matrix, max_step=None):
    """World points on the surface of a connector solid spanning z0..z1."""
    rings, caps = solid_grid(kind, width, height, z0, z1, matrix, max_step)
    return caps + [p for ring in rings for p in ring]


def _grids(spec, pin_positive, max_step):
    pin, socket = shapes.pin_and_socket_spans(spec.length, spec.clearance, spec.gap, pin_positive)
    c2 = 2.0 * spec.clearance
    return (solid_grid(spec.kind, spec.width, spec.height, *pin, spec.matrix, max_step),
            solid_grid(spec.kind, spec.width + c2, spec.height + c2, *socket, spec.matrix, max_step))


def spec_samples(spec, pin_positive=None, max_step=None):
    """Surface samples of the pin and the socket of a ConnectorSpec."""
    side = spec.pin_positive if pin_positive is None else pin_positive
    return [p for rings, caps in _grids(spec, side, max_step) for p in caps + [q for r in rings for q in r]]


def _crossings(bvh, point, direction):
    """Number of surface crossings of the ray point + t * direction (t > 0)."""
    count, origin = 0, point.copy()
    for _ in range(100000):
        hit = bvh.ray_cast(origin, direction)[0]
        if hit is None:
            return count
        count += 1
        origin = hit + direction * 1e-6 * max(1.0, hit.length)
    return count


def is_inside(bvh, point):
    """Robust inside test of a closed mesh.

    The nearest-face normal and the parity of one skewed ray usually agree.
    When they do not (a point in a face's extended plane beyond its edge, a ray
    grazing an edge) two more skewed rays decide by majority.
    """
    co, normal, _index, _dist = bvh.find_nearest(point)
    if co is None:
        return False
    by_normal = (point - co).dot(normal) < 0.0
    first = _crossings(bvh, point, _RAY_DIRS[0]) % 2 == 1
    if first == by_normal:
        return by_normal
    votes = [first] + [_crossings(bvh, point, d) % 2 == 1 for d in _RAY_DIRS[1:]]
    return sum(votes) >= 2


def depth_inside(bvh, point):
    """Distance of ``point`` inside the closed mesh (negative = outside)."""
    co, _normal, _index, dist = bvh.find_nearest(point)
    if co is None:
        return -math.inf
    return dist if is_inside(bvh, point) else -dist


def _segment_hits(bvh, a, b):
    d = b - a
    length = d.length
    if length < 1e-12:
        return False
    return bvh.ray_cast(a, d / length, length)[0] is not None


def _pierced(bvh, grid):
    """True if a segment between neighbouring samples crosses the surface."""
    rings, caps = grid
    for i, ring in enumerate(rings):
        n = len(ring)
        for k in range(n):
            if _segment_hits(bvh, ring[k], ring[(k + 1) % n]):
                return True
            if i + 1 < len(rings) and _segment_hits(bvh, ring[k], rings[i + 1][k]):
                return True
    for center, ring in ((caps[0], rings[0]), (caps[1], rings[-1])):
        if any(_segment_hits(bvh, center, p) for p in ring):
            return True
    return False


def plane_margin(spec, planes, pin_positive=None, max_step=None):
    """Smallest distance of the connector beyond the half gap of each OTHER cut plane.

    ``planes``: [(co, n, gap)] in world space. The connector's side of a plane is
    the side of its seam point; a negative result means the pin or socket
    reaches across that cut (into a third part) or into its gap.
    """
    if not planes:
        return math.inf
    center = spec.matrix.translation
    samples = spec_samples(spec, pin_positive, max_step)
    worst = math.inf
    for co, n, gap in planes:
        side = 1.0 if (center - co).dot(n) >= 0.0 else -1.0
        worst = min(worst, min(side * (p - co).dot(n) for p in samples) - 0.5 * gap)
    return worst


def check(spec, bvh, planes=(), wall=0.0, both_sides=False, max_step=None):
    """FitResult of a connector against the other cut planes and the source surface.

    Stops at the first failed test. ``both_sides`` also checks the mirrored pin
    side, so flipping pin_side later stays valid.
    """
    res = FitResult()
    sides = (True, False) if both_sides else (spec.pin_positive,)
    for side in sides:
        res.plane_margin = min(res.plane_margin, plane_margin(spec, planes, side, max_step))
        if res.plane_margin < wall:
            return res
    for side in sides:
        grids = _grids(spec, side, max_step)
        for rings, caps in grids:
            for p in caps + [q for r in rings for q in r]:
                res.surface_depth = min(res.surface_depth, depth_inside(bvh, p))
                if res.surface_depth < wall:
                    return res
        if any(_pierced(bvh, g) for g in grids):
            res.pierced = True
            return res
    return res


def worst_depth(bvh, spec, both_sides=False):
    """Smallest depth_inside over the connector's samples (negative: breaks through)."""
    sides = (True, False) if both_sides else (spec.pin_positive,)
    return min(depth_inside(bvh, p) for side in sides for p in spec_samples(spec, side))
