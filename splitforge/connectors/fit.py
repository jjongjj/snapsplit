# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# connectors/fit.py
"""Does a connector stay inside its own two parts?

A pin sticks out of its face by length/2 along the cut normal and the socket
reaches length/2 + clearance into the other side. Two things can go wrong:

- On an oblique cut the walls are slanted against that axis, so the pin or
  socket can break through the OUTER surface (defect D1).
- The pin or socket can cross ANOTHER cut and end up in a third part that has
  no matching socket (defect D7): the parts collide on assembly.
- On a curved (stroke) seam the straight pin can cross its OWN seam again
  where the ribbon bends towards it.

``check`` samples the outer surface of the pin and socket solids (the spans
and sizes Build uses) on a grid with at most ``max_step`` spacing and tests:

1. every OTHER enabled cut (a "barrier": PlaneBarrier for planes, the
   infinite plane; RibbonBarrier for strokes, the actual extended ribbon via
   its positive-side solid): all samples stay on the connector's side, beyond
   that cut's half gap plus the wall margin; for a stroke seam also its own
   ribbon (``own``): samples beyond the crossing zone stay on their side;
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
# Curved seams: samples within half gap + max(wall, OWN_SKIP * length) of the seam straddle it by design
# (own_margin gives them a fading bonus)
OWN_SKIP = 0.05
# Skewed directions for the parity test (never parallel to axis-aligned faces/edges)
_RAY_DIRS = (Vector((0.5773, 0.5774, 0.5775)).normalized(),
             Vector((-0.7071, 0.1234, 0.6963)).normalized(),
             Vector((0.2311, -0.9123, 0.3379)).normalized())


# Distribute (wall > 0) wants own-seam clearance >= OWN_SAFETY x wall; Build skips only below 0,
# so a position Distribute accepts never trips Build (defect D11)
OWN_SAFETY = 0.25


def own_required(wall):
    return OWN_SAFETY * wall if wall > 0.0 else 0.0


@dataclass
class FitResult:
    plane_margin: float = math.inf      # smallest clearance to another cut (beyond its half gap)
    surface_depth: float = math.inf     # smallest depth inside the source
    pierced: bool = False               # a sample segment crosses the source surface
    own_margin: float = math.inf        # curved seam: clearance from its own ribbon (beyond half gap)

    def ok(self, wall):
        return (self.plane_margin >= wall and self.own_margin >= own_required(wall)
                and self.surface_depth >= wall and not self.pierced)

    def reason(self, wall):
        """Short reason the connector does not fit ("" if it does)."""
        if self.plane_margin < wall:
            return "other cut"
        if self.own_margin < own_required(wall):
            return "own seam"
        if self.surface_depth < wall or self.pierced:
            return "surface"
        return ""


class PlaneBarrier:
    """Another planar cut: the infinite plane (co, n) with its gap (world space)."""

    def __init__(self, co, n, gap):
        self.co, self.n, self.gap = Vector(co), Vector(n).normalized(), gap

    def margin(self, samples, center):
        side = 1.0 if (center - self.co).dot(self.n) >= 0.0 else -1.0
        return min(side * (p - self.co).dot(self.n) for p in samples) - 0.5 * self.gap


class RibbonBarrier:
    """A stroke cut: its open ribbon (BVH, depth-sliced) and an exact side test.

    The side of a point comes from the nearest ribbon face's normal (ribbon
    normals point to the positive side) only when the nearest point lies inside
    that face (``interior_fn(face index, point)``): then the offset is along the
    normal and the sign is exact. Nearest to an edge or corner of the curve, the
    face normal can point the wrong way (sharp raw corners, defect D15), so
    ``side_fn`` (exact 2D point-in-polygon) decides. A ray-parity test on the
    cutter prism had misclassified points next to its sliver faces (D11).
    """

    def __init__(self, ribbon_bvh, gap, side_fn, interior_fn=None):
        self.ribbon_bvh, self.gap, self.side_fn = ribbon_bvh, gap, side_fn
        self.interior_fn = interior_fn
        self.exact_calls = 0

    def positive(self, p):
        co, normal, index, dist = self.ribbon_bvh.find_nearest(p)
        if co is not None and dist > 0.0 and self.interior_fn is not None and self.interior_fn(index, co):
            return (p - co).dot(normal) > 0.0
        self.exact_calls += 1
        return self.side_fn(p)

    def distance(self, p):
        hit = self.ribbon_bvh.find_nearest(p)
        return math.inf if hit[0] is None else hit[3]

    def margin(self, samples, center):
        side = self.positive(center)
        worst = math.inf
        for p in samples:
            d = self.distance(p)
            worst = min(worst, d if self.positive(p) == side else -d)
        return worst - 0.5 * self.gap


def _barrier(item):
    """Barrier object for an item of ``planes`` (a barrier, or a legacy (co, n, gap) tuple)."""
    return PlaneBarrier(*item) if isinstance(item, tuple) else item


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
    grazing an edge or passing through a vertex), or when the normal cannot
    tell (the nearest point is on an edge or corner, so the offset is
    perpendicular to the returned face normal), two more skewed rays decide by
    majority.
    """
    co, normal, _index, dist = bvh.find_nearest(point)
    if co is None:
        return False
    dot = (point - co).dot(normal)
    by_normal = dot < 0.0
    first = _crossings(bvh, point, _RAY_DIRS[0]) % 2 == 1
    if first == by_normal and abs(dot) > 1e-3 * dist:
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
    """Smallest distance of the connector beyond the half gap of each OTHER cut.

    ``planes``: barriers (PlaneBarrier/RibbonBarrier, or (co, n, gap) tuples) in
    world space. The connector's side of a cut is the side of its seam point; a
    negative result means the pin or socket reaches across that cut (into a
    third part) or into its gap.
    """
    if not planes:
        return math.inf
    center = spec.matrix.translation
    samples = spec_samples(spec, pin_positive, max_step)
    return min(_barrier(item).margin(samples, center) for item in planes)


def own_margin(spec, own, pin_positive=None, max_step=None, skip=None):
    """Clearance of a connector on a curved seam from its own ribbon.

    Every sample beyond the gap (local |z| >= half gap) must lie on the side its
    local z points to (+z = positive side). Its clearance is its distance from
    the ribbon minus the half gap; samples within ``skip`` of the gap (default
    OWN_SKIP x length) straddle the seam by design and get a bonus that fades
    from ``skip`` to 0 over that zone, so the measure is continuous (a hard
    zone edge made a sample ring flip in or out with float rounding, defect
    D11). Negative: the ribbon bends into the pin or socket.
    """
    if own is None:
        return math.inf
    skip = OWN_SKIP * spec.length if skip is None else skip
    inv = spec.matrix.inverted_safe()
    half = 0.5 * own.gap
    worst = math.inf
    for p in spec_samples(spec, pin_positive, max_step):
        z = (inv @ p).z
        if abs(z) < half:
            continue
        d = own.distance(p)
        signed = d if own.positive(p) == (z > 0.0) else -d
        worst = min(worst, signed - half + max(0.0, half + skip - abs(z)))
    return worst


def check(spec, bvh, planes=(), wall=0.0, both_sides=False, max_step=None, own=None):
    """FitResult of a connector against the other cuts, its own curved seam and the source surface.

    Stops at the first failed test. ``both_sides`` also checks the mirrored pin
    side, so flipping pin_side later stays valid. ``own``: RibbonBarrier of the
    connector's own stroke cut (None for planar cuts).
    """
    res = FitResult()
    sides = (True, False) if both_sides else (spec.pin_positive,)
    for side in sides:
        res.plane_margin = min(res.plane_margin, plane_margin(spec, planes, side, max_step))
        if res.plane_margin < wall:
            return res
        res.own_margin = min(res.own_margin, own_margin(spec, own, side, max_step,
                                                        max(wall, OWN_SKIP * spec.length)))
        if res.own_margin < own_required(wall):
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
