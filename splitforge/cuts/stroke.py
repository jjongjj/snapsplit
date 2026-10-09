# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# cuts/stroke.py
"""Curved cuts: a drawn stroke extruded along the view direction (a ribbon).

A stroke cut is a polyline (world space) and an extrusion direction ``d``: the
cut surface is the curve swept along ``d`` (cookie cutter), so it is parallel
to the view direction it was drawn in. The cut record stores the polyline and
``d`` in object space; nothing here depends on a viewport except
``points_from_view``.

2D frame: ``e1``, ``e2`` span the plane perpendicular to ``d`` with
e1 x e2 = -d, i.e. screen right / screen up when ``d`` is the view direction.
The curve normal is n = t x d, the left normal of the curve in (e1, e2): the
positive side (part A) of a stroke drawn left to right is above it.

Cutter solids are prisms over 2D polygons, from below to beyond the object's
bounding box along ``d``. The curve is extended straight along its end
directions to a rectangle R around the object (and the stroke) with a margin;
a side polygon is the curve plus the walk around R's boundary on that side.
With a gap the two sides use the curve offset by +gap/2 / -gap/2:

    part A = piece - right_side(curve + gap/2)     (cutter_remove_for_a)
    part B = piece - left_side(curve - gap/2)      (cutter_remove_for_b)

Both are one boolean DIFFERENCE each (core/boolean.py). Strokes that cross
themselves, whose straight extension crosses the stroke, or that bend sharper
than the gap allows are rejected with StrokeError.

Pure mathutils/bmesh; no data-blocks.
"""

import math
from dataclasses import dataclass

import bmesh
from mathutils import Matrix, Vector
from mathutils.geometry import tessellate_polygon

from ..core import meshlib

# Points of a prepared stroke: at most this many, resampled evenly
MAX_POINTS = 400
SMOOTH_ITERATIONS = 2
# Margin of the cutter rectangle/depth beyond the object: fraction of its bbox diagonal
MARGIN_FRACTION = 0.1
# Ribbon surfaces for distance queries: face height <= RIBBON_ASPECT x segment length
RIBBON_ASPECT = 6.0
RIBBON_MAX_SLICES = 64


# Cut kinds whose cutter is a ribbon (a drawn stroke, or straight segments between clicked points)
RIBBON_KINDS = ('STROKE', 'POLYLINE')


class StrokeError(ValueError):
    """The stroke cannot be turned into a valid cutter (message for the user)."""


# ---------------------------------------------------------------------------
# Frame and 2D polyline helpers
# ---------------------------------------------------------------------------

@dataclass
class Frame:
    """Plane through ``origin`` perpendicular to ``d``; (x, y, z) = e1, e2, d coordinates."""
    origin: Vector
    e1: Vector
    e2: Vector
    d: Vector

    @classmethod
    def from_direction(cls, d, origin):
        d = Vector(d).normalized()
        _n, e1, e2 = meshlib.orthonormal_basis(-d)   # e2 = (-d) x e1  ->  e1 x e2 = -d
        return cls(Vector(origin), e1, e2, d)

    def to2d(self, p):
        q = Vector(p) - self.origin
        return (q.dot(self.e1), q.dot(self.e2))

    def depth(self, p):
        return (Vector(p) - self.origin).dot(self.d)

    def to3d(self, x, y, z=0.0):
        return self.origin + self.e1 * x + self.e2 * y + self.d * z

    def dir3d(self, x, y):
        return self.e1 * x + self.e2 * y


def polyline_length(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def dedupe(pts, eps):
    out = []
    for p in pts:
        if not out or math.dist(out[-1], p) > eps:
            out.append((float(p[0]), float(p[1])))
    return out


def resample(pts, count):
    """``count`` points evenly spaced by arc length, keeping both ends."""
    lengths = [0.0]
    for a, b in zip(pts, pts[1:]):
        lengths.append(lengths[-1] + math.dist(a, b))
    total = lengths[-1]
    if count < 2 or total <= 0.0:
        return list(pts)
    out, seg = [], 0
    for i in range(count):
        s = total * i / (count - 1)
        while seg < len(pts) - 2 and lengths[seg + 1] < s:
            seg += 1
        span = lengths[seg + 1] - lengths[seg]
        f = (s - lengths[seg]) / span if span > 0.0 else 0.0
        (x0, y0), (x1, y1) = pts[seg], pts[seg + 1]
        out.append((x0 + (x1 - x0) * f, y0 + (y1 - y0) * f))
    return out


def smooth(pts, iterations=SMOOTH_ITERATIONS):
    """Laplacian (1/4, 1/2, 1/4) smoothing with fixed end points."""
    pts = list(pts)
    for _ in range(iterations):
        pts = [pts[0]] + [((a[0] + 2 * b[0] + c[0]) / 4.0, (a[1] + 2 * b[1] + c[1]) / 4.0)
                          for a, b, c in zip(pts, pts[1:], pts[2:])] + [pts[-1]]
    return pts


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def segments_cross(p1, p2, q1, q2, eps=0.0):
    """True if the closed segments p1-p2 and q1-q2 intersect (touching counts)."""
    if (max(p1[0], p2[0]) < min(q1[0], q2[0]) - eps or max(q1[0], q2[0]) < min(p1[0], p2[0]) - eps
            or max(p1[1], p2[1]) < min(q1[1], q2[1]) - eps or max(q1[1], q2[1]) < min(p1[1], p2[1]) - eps):
        return False
    d1, d2 = _cross(q1, q2, p1), _cross(q1, q2, p2)
    d3, d4 = _cross(p1, p2, q1), _cross(p1, p2, q2)
    if ((d1 > 0) != (d2 > 0) or d1 == 0 or d2 == 0) and ((d3 > 0) != (d4 > 0) or d3 == 0 or d4 == 0):
        return True
    return False


def first_self_crossing(pts):
    """(i, j) of the first pair of non-adjacent crossing segments, or None.

    Adjacent segments that fold back onto each other count as crossing.
    """
    segs = list(zip(pts, pts[1:]))
    boxes = [(min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1])) for a, b in segs]
    for i in range(len(segs) - 1):
        a, b = segs[i]
        c = segs[i + 1][1]
        u, v = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
        lu, lv = math.hypot(*u), math.hypot(*v)
        if lu > 0 and lv > 0 and (u[0] * v[0] + u[1] * v[1]) / (lu * lv) < -0.999:
            return i, i + 1
    for i in range(len(segs)):
        bi = boxes[i]
        for j in range(i + 2, len(segs)):
            bj = boxes[j]
            if bj[0] > bi[1] or bi[0] > bj[1] or bj[2] > bi[3] or bi[2] > bj[3]:
                continue
            if segments_cross(*segs[i], *segs[j]):
                return i, j
    return None


def crossing_between(a_pts, b_pts):
    """True if any segment of polyline a crosses any segment of polyline b."""
    sa, sb = list(zip(a_pts, a_pts[1:])), list(zip(b_pts, b_pts[1:]))
    for p in sa:
        bp = (min(p[0][0], p[1][0]), max(p[0][0], p[1][0]), min(p[0][1], p[1][1]), max(p[0][1], p[1][1]))
        for q in sb:
            if (max(q[0][0], q[1][0]) < bp[0] or min(q[0][0], q[1][0]) > bp[1]
                    or max(q[0][1], q[1][1]) < bp[2] or min(q[0][1], q[1][1]) > bp[3]):
                continue
            if segments_cross(*p, *q):
                return True
    return False


def _unit(v):
    length = math.hypot(*v)
    return (v[0] / length, v[1] / length) if length > 0 else (0.0, 0.0)


def vertex_tangents(pts):
    """Unit tangent at each vertex (average of the adjacent segment directions)."""
    segs = [_unit((b[0] - a[0], b[1] - a[1])) for a, b in zip(pts, pts[1:])]
    out = [segs[0]]
    for s0, s1 in zip(segs, segs[1:]):
        avg = _unit((s0[0] + s1[0], s0[1] + s1[1]))
        out.append(avg if avg != (0.0, 0.0) else s0)
    out.append(segs[-1])
    return out


def offset(pts, h):
    """Polyline offset by ``h`` along the left normal (miter joins, limited)."""
    segs = [_unit((b[0] - a[0], b[1] - a[1])) for a, b in zip(pts, pts[1:])]
    tans = vertex_tangents(pts)
    out = []
    for i, (p, t) in enumerate(zip(pts, tans)):
        n = (-t[1], t[0])
        scale = 1.0
        if 0 < i < len(pts) - 1:
            s0 = segs[i - 1]
            cos_half = max(abs(s0[0] * t[0] + s0[1] * t[1]), 0.25)
            scale = 1.0 / cos_half
        out.append((p[0] + n[0] * h * scale, p[1] + n[1] * h * scale))
    return out


def folded(pts, off):
    """True if an offset curve runs backwards somewhere (a bend tighter than the offset)."""
    for (a, b), (c, d) in zip(zip(pts, pts[1:]), zip(off, off[1:])):
        if (b[0] - a[0]) * (d[0] - c[0]) + (b[1] - a[1]) * (d[1] - c[1]) <= 0.0:
            return True
    return False


# ---------------------------------------------------------------------------
# Rectangle walk and side polygons
# ---------------------------------------------------------------------------

def _exit_point(p, t, box):
    """Point where the ray p + t*l (l > 0) leaves the rectangle ``box`` = (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    ls = []
    if t[0] > 1e-15:
        ls.append((x1 - p[0]) / t[0])
    elif t[0] < -1e-15:
        ls.append((x0 - p[0]) / t[0])
    if t[1] > 1e-15:
        ls.append((y1 - p[1]) / t[1])
    elif t[1] < -1e-15:
        ls.append((y0 - p[1]) / t[1])
    lam = min(ls)
    x, y = p[0] + t[0] * lam, p[1] + t[1] * lam
    return (min(max(x, x0), x1), min(max(y, y0), y1))


def extend_to_box(pts, box):
    """The polyline with both ends extended straight (end tangents) to the rectangle boundary."""
    t0 = _unit((pts[0][0] - pts[1][0], pts[0][1] - pts[1][1]))
    t1 = _unit((pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]))
    return [_exit_point(pts[0], t0, box)] + list(pts) + [_exit_point(pts[-1], t1, box)]


def _perimeter_param(p, box):
    """Position on the rectangle boundary, counter-clockwise from (x0, y0): 0..4."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    dists = [abs(p[1] - y0), abs(p[0] - x1), abs(p[1] - y1), abs(p[0] - x0)]
    edge = dists.index(min(dists))
    if edge == 0:
        return (p[0] - x0) / w
    if edge == 1:
        return 1.0 + (p[1] - y0) / h
    if edge == 2:
        return 2.0 + (x1 - p[0]) / w
    return 3.0 + (y1 - p[1]) / h


def _corners(box):
    x0, y0, x1, y1 = box
    return {1: (x1, y0), 2: (x1, y1), 3: (x0, y1), 4: (x0, y0)}


def walk_ccw(a, b, box):
    """Rectangle corners met walking counter-clockwise from boundary point a to b."""
    pa, pb = _perimeter_param(a, box), _perimeter_param(b, box)
    if pb <= pa:
        pb += 4.0
    corners = _corners(box)
    out = []
    k = math.floor(pa) + 1
    while k < pb:
        out.append(corners[(k - 1) % 4 + 1])
        k += 1
    return out


def left_polygon(curve, box):
    """Polygon left of an extended curve (ends on the box boundary), counter-clockwise."""
    return list(curve) + walk_ccw(curve[-1], curve[0], box)


def right_polygon(curve, box):
    """Polygon right of an extended curve, counter-clockwise."""
    rev = list(reversed(curve))
    return rev + walk_ccw(rev[-1], rev[0], box)


def point_in_polygon(pt, poly):
    return meshlib.point_in_poly_2d(pt, poly)


def distance_to_polyline(pt, pts):
    best = math.inf
    px, py = pt
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        ll = dx * dx + dy * dy
        f = 0.0 if ll == 0.0 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / ll))
        best = min(best, math.hypot(px - (x0 + f * dx), py - (y0 + f * dy)))
    return best


# ---------------------------------------------------------------------------
# Prism solids
# ---------------------------------------------------------------------------

def prism(poly, frame, z0, z1, bm=None):
    """Closed prism over a simple 2D polygon from depth z0 to z1, outward normals."""
    bm = bm if bm is not None else bmesh.new()
    eps = 1e-9 * max(1.0, max(abs(c) for p in poly for c in p))
    poly = dedupe(poly, eps)
    if math.dist(poly[0], poly[-1]) <= eps:
        poly = poly[:-1]
    if len(poly) < 3:
        raise StrokeError("degenerate cutter polygon")
    lo = [bm.verts.new(frame.to3d(x, y, z0)) for x, y in poly]
    hi = [bm.verts.new(frame.to3d(x, y, z1)) for x, y in poly]
    tris = tessellate_polygon([[Vector((x, y, 0.0)) for x, y in poly]])
    faces = []
    for a, b, c in tris:
        faces.append(bm.faces.new((lo[a], lo[c], lo[b])))
        faces.append(bm.faces.new((hi[a], hi[b], hi[c])))
    n = len(poly)
    for i in range(n):
        j = (i + 1) % n
        faces.append(bm.faces.new((lo[i], lo[j], hi[j], hi[i])))
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    bm.normal_update()
    return bm


# ---------------------------------------------------------------------------
# Stroke preparation and cutter
# ---------------------------------------------------------------------------

def prepare_points(points, direction, spacing, iterations=SMOOTH_ITERATIONS):
    """Clean a captured stroke: project along ``direction``, dedupe, resample, smooth.

    ``points``: world points (any depth), ``spacing``: wanted point distance
    (same unit). Returns world points on the plane through their centroid
    perpendicular to ``direction``. Raises StrokeError for a too short stroke.
    """
    pts3 = [Vector(p) for p in points]
    if len(pts3) < 2:
        raise StrokeError("The stroke is too short: drag across the object")
    centroid = sum(pts3, Vector()) / len(pts3)
    frame = Frame.from_direction(direction, centroid)
    pts = dedupe([frame.to2d(p) for p in pts3], max(spacing * 1e-3, 1e-9))
    total = polyline_length(pts)
    if len(pts) < 2 or total < spacing:
        raise StrokeError("The stroke is too short: drag across the object")
    count = max(2, min(MAX_POINTS, math.ceil(total / spacing) + 1))
    if len(pts) > 2:
        pts = resample(smooth(resample(pts, count), iterations), count)
    return [frame.to3d(x, y) for x, y in pts]


def snap_to_axis(points, direction):
    """Straight two-point stroke from the first to the last point's projection, snapped
    to the world axis (projected into the view plane) closest to its direction."""
    a, b = Vector(points[0]), Vector(points[-1])
    d = Vector(direction).normalized()
    chord = (b - a) - d * (b - a).dot(d)
    if chord.length < 1e-12:
        return [a, b]
    best = None
    for axis in (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))):
        proj = axis - d * axis.dot(d)
        if proj.length < 1e-6:
            continue
        proj.normalize()
        score = abs(proj.dot(chord.normalized()))
        if best is None or score > best[0]:
            best = (score, proj if proj.dot(chord) > 0 else -proj)
    mid = (a + b) * 0.5
    half = chord.length * 0.5
    return [mid - best[1] * half, mid + best[1] * half]


@dataclass
class StrokeCutter:
    """Cutter geometry of one stroke cut in world space (see module docstring)."""
    frame: Frame
    curve: list          # smoothed polyline, 2D (not extended)
    box: tuple           # rectangle (x0, y0, x1, y1) around object and stroke
    z0: float
    z1: float
    gap: float
    extended: list       # curve extended to the box boundary
    plus: list           # extended curve offset by +gap/2 (= extended without gap)
    minus: list          # extended curve offset by -gap/2
    _left: list = None   # cached positive-side polygon

    # --- solids ---------------------------------------------------------------

    def remove_for_a(self):
        """Solid subtracted from a piece to keep part A (positive side beyond gap/2)."""
        return prism(right_polygon(self.plus, self.box), self.frame, self.z0, self.z1)

    def remove_for_b(self):
        """Solid subtracted from a piece to keep part B (negative side beyond gap/2)."""
        return prism(left_polygon(self.minus, self.box), self.frame, self.z0, self.z1)

    def positive_solid(self):
        """Closed solid of the positive side of the ribbon itself (no gap), for side tests."""
        return prism(left_polygon(self.extended, self.box), self.frame, self.z0, self.z1)

    def slab(self):
        """The gap between the two offset ribbons as a closed solid (None without gap)."""
        if self.gap <= 0.0:
            return None
        poly = list(self.plus) + _short_walk(self.plus[-1], self.minus[-1], self.box) \
            + list(reversed(self.minus)) + _short_walk(self.minus[0], self.plus[0], self.box)
        return prism(poly, self.frame, self.z0, self.z1)

    def ribbon(self, bm=None, curve=None):
        """Open ribbon surface: ``curve`` (default: the extended curve) swept along d over the depth range.

        The depth is sliced so faces are at most RIBBON_ASPECT times taller than
        the curve's typical segment: Blender's closest-point queries (BVHTree,
        float32) are off by ~0.01 mm on 1:100 sliver triangles.
        """
        bm = bm if bm is not None else bmesh.new()
        curve = self.extended if curve is None else curve
        lengths = sorted(math.dist(a, b) for a, b in zip(curve, curve[1:]))
        typical = max(lengths[len(lengths) // 2], 1e-9)
        slices = max(1, min(RIBBON_MAX_SLICES, math.ceil((self.z1 - self.z0) / (RIBBON_ASPECT * typical))))
        rows = [[bm.verts.new(self.frame.to3d(x, y, self.z0 + (self.z1 - self.z0) * k / slices))
                 for x, y in curve] for k in range(slices + 1)]
        for lo, hi in zip(rows, rows[1:]):
            for i in range(len(lo) - 1):
                bm.faces.new((lo[i], lo[i + 1], hi[i + 1], hi[i]))
        bm.normal_update()
        return bm

    # --- point queries --------------------------------------------------------

    def ribbon_face_interior(self, index, co):
        """True if world point ``co`` on ribbon face ``index`` (of ``ribbon()``) lies strictly
        between the face's two vertical edges, i.e. not on a corner of the curve."""
        n = len(self.extended) - 1
        i = index % n
        (x0, y0), (x1, y1) = self.extended[i], self.extended[i + 1]
        x, y = self.frame.to2d(co)
        dx, dy = x1 - x0, y1 - y0
        ll = dx * dx + dy * dy
        if ll <= 0.0:
            return False
        f = ((x - x0) * dx + (y - y0) * dy) / ll
        eps = 1e-4
        return eps < f < 1.0 - eps

    def is_positive(self, p):
        """True if world point ``p`` is on the positive side of the ribbon (exact, 2D)."""
        if self._left is None:
            self._left = left_polygon(self.extended, self.box)
        return point_in_polygon(self.frame.to2d(p), self._left)

    def side(self, p):
        """+1 if world point ``p`` is on the positive side of the ribbon, else -1."""
        return 1 if self.is_positive(p) else -1

    def distance(self, p):
        """Distance of world point ``p`` from the ribbon (perpendicular to d)."""
        return distance_to_polyline(self.frame.to2d(p), self.extended)


# Polyline cuts reuse the stroke rules; their messages speak of clicked points
_POLYLINE_WORDS = (("drag across the object", "place the points across the object"),
                   ("draw an open curve without loops", "place the points without loops"),
                   ("draw a smoother curve", "use wider corners"),
                   ("stroke", "polyline"))


def build_cutter(points, direction, corners, gap=0.0, kind='STROKE'):
    """StrokeCutter for a stroke (world points, extrusion ``direction``) around an object.

    ``corners``: world points bounding the object (e.g. its bbox corners),
    ``gap``: kerf width (same unit). Raises StrokeError with a user message
    when the stroke cannot be used (worded for ``kind`` STROKE or POLYLINE).
    """
    try:
        return _build_cutter(points, direction, corners, gap)
    except StrokeError as ex:
        if kind != 'POLYLINE':
            raise
        text = str(ex)
        for old, new in _POLYLINE_WORDS:
            text = text.replace(old, new)
        raise StrokeError(text) from None


def _build_cutter(points, direction, corners, gap=0.0):
    d = Vector(direction)
    if d.length < 1e-12:
        raise StrokeError("The stroke has no extrusion direction")
    pts3 = [Vector(p) for p in points]
    if len(pts3) < 2:
        raise StrokeError("The stroke is too short: drag across the object")
    frame = Frame.from_direction(d, sum(pts3, Vector()) / len(pts3))
    corners = [Vector(c) for c in corners]
    diag = max(Vector([max(c[i] for c in corners) - min(c[i] for c in corners) for i in range(3)]).length, 1e-6)
    pts = dedupe([frame.to2d(p) for p in pts3], diag * 1e-7)
    if len(pts) < 2 or polyline_length(pts) < diag * 1e-4:
        raise StrokeError("The stroke is too short: drag across the object")
    half = max(gap, 0.0) * 0.5
    margin = diag * MARGIN_FRACTION + 4.0 * half
    xy = [frame.to2d(c) for c in corners] + pts
    box = (min(p[0] for p in xy) - margin, min(p[1] for p in xy) - margin,
           max(p[0] for p in xy) + margin, max(p[1] for p in xy) + margin)
    depths = [frame.depth(c) for c in corners]
    z0, z1 = min(depths) - margin, max(depths) + margin

    hit = first_self_crossing(pts)
    if hit is not None:
        raise StrokeError("The stroke crosses itself: draw an open curve without loops")
    extended = extend_to_box(pts, box)
    hit = first_self_crossing(extended)
    if hit is not None:
        raise StrokeError("The straight extension beyond a stroke end crosses the stroke: "
                          "start and end the stroke heading away from the object")
    if half > 0.0:
        raw_plus, raw_minus = offset(pts, half), offset(pts, -half)
        plus, minus = extend_to_box(raw_plus, box), extend_to_box(raw_minus, box)
        if folded(pts, raw_plus) or folded(pts, raw_minus):
            raise StrokeError(f"The stroke bends too sharply for its gap ({2 * half:g}): "
                              "draw a smoother curve or reduce the gap")
        # Part A = left of plus, part B = right of minus: disjoint only if plus lies left of minus
        left_of_minus = left_polygon(minus, box)
        if (first_self_crossing(plus) is not None or first_self_crossing(minus) is not None
                or crossing_between(plus, minus) or crossing_between(plus, extended)
                or crossing_between(minus, extended)
                or not all(point_in_polygon(((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5), left_of_minus)
                           for a, b in zip(raw_plus, raw_plus[1:]))):
            raise StrokeError(f"The stroke comes back too close to itself for its gap ({2 * half:g}): "
                              "draw a smoother curve or reduce the gap")
    else:
        plus = minus = extended
    return StrokeCutter(frame, pts, box, z0, z1, max(gap, 0.0), extended, plus, minus)


def _short_walk(a, b, box):
    """Corners between boundary points a and b along the shorter way round the rectangle."""
    ccw = walk_ccw(a, b, box)
    pa, pb = _perimeter_param(a, box), _perimeter_param(b, box)
    if (pb - pa) % 4.0 <= 2.0:
        return ccw
    return list(reversed(walk_ccw(b, a, box)))


# ---------------------------------------------------------------------------
# Seam frame along the curve (connector placement)
# ---------------------------------------------------------------------------

class Centerline:
    """Arc length parametrisation of a stroke's (unextended) curve.

    ``u`` is the arc length from the middle of the curve (beyond the ends the
    straight extension continues), ``v`` the depth along ``d`` from the stroke
    plane. ``frame(u)`` returns the seam frame (point, n, t): t the tangent
    (interpolated between vertex tangents), n = t x d the ribbon normal.
    ``sharp`` (polyline cuts, cuts/polyline.py): the points are corners of
    straight segments, so t is the direction of the segment (pins stand square
    on its flat face; no interpolation across a corner).
    """

    def __init__(self, frame, pts, sharp=False):
        self.frame = frame
        self.sharp = sharp
        self.pts = list(pts)
        self.tans = vertex_tangents(self.pts)
        self.s = [0.0]
        for a, b in zip(self.pts, self.pts[1:]):
            self.s.append(self.s[-1] + math.dist(a, b))
        self.total = self.s[-1]

    def _at(self, u):
        s = u + self.total * 0.5
        if s <= 0.0:
            t = self.tans[0]
            return (self.pts[0][0] + t[0] * s, self.pts[0][1] + t[1] * s), t
        if s >= self.total:
            t = self.tans[-1]
            e = s - self.total
            return (self.pts[-1][0] + t[0] * e, self.pts[-1][1] + t[1] * e), t
        lo, hi = 0, len(self.s) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.s[mid] <= s:
                lo = mid
            else:
                hi = mid
        span = self.s[hi] - self.s[lo]
        f = (s - self.s[lo]) / span if span > 0.0 else 0.0
        (x0, y0), (x1, y1) = self.pts[lo], self.pts[hi]
        if self.sharp:
            t = _unit((x1 - x0, y1 - y0))
            return (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f), t
        t0, t1 = self.tans[lo], self.tans[hi]
        t = _unit((t0[0] + (t1[0] - t0[0]) * f, t0[1] + (t1[1] - t0[1]) * f))
        return (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f), t

    def uv_of(self, point):
        """(u, v) of a world point: the arc length of the nearest curve point (the straight
        extensions beyond the ends included) and the depth along ``d``."""
        x, y = self.frame.to2d(point)
        best = None
        n = len(self.pts)
        for i in range(n - 1):
            (x0, y0), (x1, y1) = self.pts[i], self.pts[i + 1]
            dx, dy = x1 - x0, y1 - y0
            ll = dx * dx + dy * dy
            f = 0.0 if ll == 0.0 else ((x - x0) * dx + (y - y0) * dy) / ll
            lo = -math.inf if i == 0 else 0.0          # the first/last segment continue straight on
            hi = math.inf if i == n - 2 else 1.0
            f = max(lo, min(hi, f))
            d2 = (x - x0 - f * dx) ** 2 + (y - y0 - f * dy) ** 2
            if best is None or d2 < best[0]:
                best = (d2, self.s[i] + f * math.sqrt(ll))
        return best[1] - self.total * 0.5, self.frame.depth(point)

    def frame_at(self, u, v=0.0):
        """World (point, n, t) of the seam at (u, v)."""
        (x, y), (tx, ty) = self._at(u)
        t = self.frame.dir3d(tx, ty).normalized()
        n = t.cross(self.frame.d).normalized()
        return self.frame.to3d(x, y, v), n, t

    def matrix(self, u, v=0.0, rotation_deg=0.0):
        """Connector matrix at (u, v): Z = ribbon normal, X = tangent rotated around Z."""
        co, n, t = self.frame_at(u, v)
        a = math.radians(rotation_deg)
        b = n.cross(t)
        x = t * math.cos(a) + b * math.sin(a)
        y = n.cross(x)
        m = Matrix.Identity(4)
        for row in range(3):
            m[row][0], m[row][1], m[row][2], m[row][3] = x[row], y[row], n[row], co[row]
        return m


def centerline(cutter, sharp=False):
    return Centerline(cutter.frame, cutter.curve, sharp)


def curve_frame(points, direction, sharp=False):
    """(point, n, t) in the middle of a stroke (world points, extrusion direction)."""
    pts3 = [Vector(p) for p in points]
    frame = Frame.from_direction(direction, sum(pts3, Vector()) / len(pts3))
    pts = dedupe([frame.to2d(p) for p in pts3], 1e-12)
    if len(pts) < 2:
        raise StrokeError("The stroke is too short: drag across the object")
    return Centerline(frame, pts, sharp).frame_at(0.0)


def points_from_view(region, rv3d, coords, center, ray_fn=None):
    """World points of 2D region coordinates on the plane through ``center`` facing the view.

    Returns ``(points, d)``: ``d`` is the view direction (into the screen).
    ``ray_fn(region, rv3d, co) -> (origin, direction)`` defaults to
    bpy_extras.view3d_utils (any object with the region/rv3d attributes those
    functions read works, so tests can pass synthetic views).
    """
    from bpy_extras import view3d_utils
    from mathutils.geometry import intersect_line_plane
    if ray_fn is None:
        def ray_fn(reg, rv, co):
            return (view3d_utils.region_2d_to_origin_3d(reg, rv, co),
                    view3d_utils.region_2d_to_vector_3d(reg, rv, co))
    d = (Matrix(rv3d.view_rotation.to_matrix()) @ Vector((0.0, 0.0, -1.0))).normalized()
    center = Vector(center)
    out = []
    for co in coords:
        origin, direction = ray_fn(region, rv3d, Vector(co))
        hit = intersect_line_plane(origin, origin + direction, center, d)
        if hit is not None:
            out.append(hit)
    return out, d
