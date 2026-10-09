# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# cuts/polygon.py
"""Polygonal cut: cut out the region inside a closed polygon (region removal).

The polygon is drawn in the view like a stroke (cuts/stroke.py): points on the
plane through the object's center facing the view, extruded along the view
direction ``d``. Its prism splits every piece in two:

    part A (the cut-out region) = piece  INTERSECT  prism(inner)
    part B (the rest)           = piece  DIFFERENCE prism(outer)

``inner``/``outer`` are the polygon offset inward/outward by gap/2 (mitered,
like stroke offsets), so the walls between the two parts are ``gap`` apart.
The prism starts in front of the object (beyond its bounding box towards the
viewer) and ends at the floor: ``depth`` measured from the front of the
object's bounding box along ``d``, or behind the object (depth 0 = through
everything). A cut-out with a floor leaves a pocket in part B and a plug
(part A) that sits on the pocket floor (no gap at the floor).

Connectors of a polygon cut sit on that floor (a planar seam, normal -d, i.e.
pointing into the plug); a cut through the whole object has no floor and no
connectors. Point side test (``is_inside``): inside the polygon and in front
of the floor.

Invalid polygons raise stroke.StrokeError with a user message: fewer than
three points, crossing edges, no area, an inward offset that folds (the gap is
too wide for a narrow part of the polygon), a floor in front of the object.

Pure mathutils/bmesh; no data-blocks.
"""

import math
from dataclasses import dataclass

import bmesh
from mathutils import Vector

from ..core.boolean import VOLUME_TOLERANCE
from . import stroke

MARGIN_FRACTION = stroke.MARGIN_FRACTION
# Smallest cut-out (defects D21, D22), three checks with their own messages:
# - width: about MIN_SIZE_MM across (2 x area / perimeter >= MIN_SIZE_MM / 2: a square of side
#   MIN_SIZE_MM, a strip MIN_SIZE_MM / 2 wide) -- absolute, below anything printable;
# - depth: at least MIN_DEPTH_MM of the object inside the prism (absolute);
# - volume: the volume it removes must be visible to the boolean result check (core/boolean.py rejects a
#   DIFFERENCE that does not shrink the piece by more than VOLUME_TOLERANCE x its volume, float noise):
#   at least VOLUME_MARGIN x that tolerance of the object's bounding box volume (an upper bound of any
#   piece). Only this one grows with the object, and only as far as the boolean check really needs
#   (a 500 mm cube: 250 mm^3, a 10 x 10 x 5 mm pocket is 500). D21 used 1e-5 of the box (10x too strict).
MIN_SIZE_MM = 0.5
MIN_DEPTH_MM = 0.2
VOLUME_MARGIN = 2.0


def signed_area(poly):
    """Shoelace area of a closed 2D polygon (counter-clockwise > 0)."""
    a = 0.0
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return 0.5 * a


def edges_cross(poly):
    """True if two edges of the closed polygon that share no vertex intersect, or an edge folds
    back onto its neighbour."""
    n = len(poly)
    segs = [(poly[i], poly[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        a, b = segs[i]
        c = segs[(i + 1) % n][1]
        u, v = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
        lu, lv = math.hypot(*u), math.hypot(*v)
        if lu > 0 and lv > 0 and (u[0] * v[0] + u[1] * v[1]) / (lu * lv) < -0.999:
            return True
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue   # neighbours through the closing vertex
            if stroke.segments_cross(*segs[i], *segs[j]):
                return True
    return False


def mitre_scales_closed(poly):
    """1 / cos(half the turn) at each vertex of a closed polygon (exact mitre, stroke.MITER_LIMIT)."""
    n = len(poly)
    segs = [stroke._unit((poly[(i + 1) % n][0] - poly[i][0], poly[(i + 1) % n][1] - poly[i][1]))
            for i in range(n)]
    out = []
    for i in range(n):
        s0, s1 = segs[i - 1], segs[i]
        t = stroke._unit((s0[0] + s1[0], s0[1] + s1[1]))
        cos_half = abs(s0[0] * t[0] + s0[1] * t[1]) if t != (0.0, 0.0) else 0.0
        out.append(1.0 / cos_half if cos_half > 1e-12 else math.inf)
    return out


def offset_closed(poly, h):
    """Closed polygon offset by ``h`` along the left normal of its edges (inward for a
    counter-clockwise polygon), exact mitre joins like stroke.offset (defect D20)."""
    n = len(poly)
    segs = [stroke._unit((poly[(i + 1) % n][0] - poly[i][0], poly[(i + 1) % n][1] - poly[i][1]))
            for i in range(n)]
    out = []
    for i, scale in enumerate(mitre_scales_closed(poly)):
        s0, s1 = segs[i - 1], segs[i]
        t = stroke._unit((s0[0] + s1[0], s0[1] + s1[1]))
        if t == (0.0, 0.0):
            t = s1
        scale = min(scale, 1e6)
        nx, ny = -t[1], t[0]
        out.append((poly[i][0] + nx * h * scale, poly[i][1] + ny * h * scale))
    return out


def _folded(poly, off):
    """True if an offset edge runs against its original edge (a part narrower than the offset)."""
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        c, d = off[i], off[(i + 1) % n]
        if (b[0] - a[0]) * (d[0] - c[0]) + (b[1] - a[1]) * (d[1] - c[1]) <= 0.0:
            return True
    return False


def ring(poly, frame, z0, z1, bm=None, slices=1):
    """Open wall surface of a closed polygon over z0..z1 (normals outward for a CCW polygon)."""
    bm = bm if bm is not None else bmesh.new()
    rows = [[bm.verts.new(frame.to3d(x, y, z0 + (z1 - z0) * k / slices)) for x, y in poly]
            for k in range(slices + 1)]
    n = len(poly)
    for lo, hi in zip(rows, rows[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    bm.normal_update()
    return bm


@dataclass
class PolygonCutter:
    """Cutter geometry of a polygon cut in world space (see module docstring)."""
    frame: stroke.Frame
    poly: list           # counter-clockwise 2D polygon (no gap)
    inner: list          # offset inward by gap/2
    outer: list          # offset outward by gap/2
    z0: float            # in front of the object
    z_floor: float       # end of the prism: the floor, or behind the object
    gap: float
    through: bool        # the prism goes through the whole object (no floor)

    def inside_solid(self):
        """Prism over the inner polygon: part A = piece INTERSECT this."""
        return stroke.prism(self.inner, self.frame, self.z0, self.z_floor)

    def outside_remove(self):
        """Prism over the outer polygon: part B = piece DIFFERENCE this."""
        return stroke.prism(self.outer, self.frame, self.z0, self.z_floor)

    def solid(self, bm=None):
        """Closed prism over the polygon itself (no gap), for distance and side queries."""
        return stroke.prism(self.poly, self.frame, self.z0, self.z_floor, bm)

    def walls(self, poly=None):
        """Open walls of ``poly`` (default: the polygon) over the prism's depth, sliced like a ribbon."""
        poly = self.poly if poly is None else poly
        lengths = sorted(math.dist(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))
        typical = max(lengths[len(lengths) // 2], 1e-9)
        slices = max(1, min(stroke.RIBBON_MAX_SLICES,
                            math.ceil((self.z_floor - self.z0) / (stroke.RIBBON_ASPECT * typical))))
        return ring(poly, self.frame, self.z0, self.z_floor, slices=slices)

    def is_inside(self, p):
        """True if world point ``p`` is inside the polygon prism (part A side, no gap)."""
        if self.frame.depth(p) > self.z_floor:
            return False
        return stroke.point_in_polygon(self.frame.to2d(p), self.poly)

    # --- floor seam (connectors) -------------------------------------------------

    def floor_frame(self):
        """(co, n, t) of the floor seam: the polygon's area centroid on the floor, n = -d (into the
        cut-out part), t = the frame's e1."""
        cx, cy = _centroid(self.poly)
        return self.frame.to3d(cx, cy, self.z_floor), -self.frame.d, self.frame.e1.copy()


def _centroid(poly):
    a = cx = cy = 0.0
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    if abs(a) < 1e-30:
        return sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n
    return cx / (3.0 * a), cy / (3.0 * a)


def clean_points(pts, eps):
    """Dedupe a closed 2D point list (also the closing duplicate)."""
    out = stroke.dedupe(pts, eps)
    while len(out) > 1 and math.dist(out[0], out[-1]) <= eps:
        out.pop()
    return out


def build_cutter(points, direction, corners, gap=0.0, depth=0.0, mm=0.0):
    """PolygonCutter for a closed polygon (world points, extrusion ``direction``) around an object.

    ``corners``: world points bounding the object, ``gap``: kerf width,
    ``depth``: how far the cut-out reaches from the front of the object along
    ``direction`` (0 = through everything); all in the same unit. ``mm``: one
    millimeter in that unit, for the minimum size checks (0 skips them). Raises
    stroke.StrokeError with a user message for an unusable polygon.
    """
    d = Vector(direction)
    if d.length < 1e-12:
        raise stroke.StrokeError("The polygon has no extrusion direction")
    pts3 = [Vector(p) for p in points]
    if len(pts3) < 3:
        raise stroke.StrokeError("A polygon needs at least 3 points")
    frame = stroke.Frame.from_direction(d, sum(pts3, Vector()) / len(pts3))
    corners = [Vector(c) for c in corners]
    diag = max(Vector([max(c[i] for c in corners) - min(c[i] for c in corners) for i in range(3)]).length, 1e-6)
    poly = clean_points([frame.to2d(p) for p in pts3], diag * 1e-7)
    if len(poly) < 3:
        raise stroke.StrokeError("A polygon needs at least 3 points")
    if edges_cross(poly):
        raise stroke.StrokeError("The polygon crosses itself: click the corners in order around the region")
    area = signed_area(poly)
    if abs(area) < (diag * 1e-4) ** 2:
        raise stroke.StrokeError("The polygon encloses no area")
    if area < 0.0:
        poly.reverse()
    half = max(gap, 0.0) * 0.5
    if half > 0.0:
        sharpest = max(mitre_scales_closed(poly))
        if sharpest > stroke.MITER_LIMIT:
            angle = 2.0 * math.degrees(math.asin(min(1.0, 1.0 / sharpest)))
            raise stroke.StrokeError(
                f"A corner of the polygon is too sharp for a gap ({angle:.1f} degrees; with a gap corners need "
                f"at least {stroke.MIN_CORNER_DEG:g}): widen the corner or "
                "set the gap to 0")
        inner, outer = offset_closed(poly, half), offset_closed(poly, -half)
        if (_folded(poly, inner) or _folded(poly, outer) or edges_cross(inner) or edges_cross(outer)
                or signed_area(inner) <= 0.0):
            raise stroke.StrokeError(f"The polygon is too narrow or too sharp for its gap ({2 * half:g}): "
                                     "widen it or reduce the gap")
    else:
        inner = outer = list(poly)
    margin = diag * MARGIN_FRACTION + 4.0 * half
    depths = [frame.depth(c) for c in corners]
    front, back = min(depths), max(depths)
    z0 = front - margin
    through = depth <= 0.0 or front + depth >= back
    z_floor = back + margin if through else front + depth
    if mm > 0.0:
        min_width = 0.5 * MIN_SIZE_MM * mm
        n = len(poly)
        perimeter = sum(math.dist(poly[i], poly[(i + 1) % n]) for i in range(n))
        width = 2.0 * abs(area) / perimeter
        box = [max(c[i] for c in corners) - min(c[i] for c in corners) for i in range(3)]
        thickness = (back - front) if through else min(depth, back - front)
        volume = abs(area) * thickness
        needed = VOLUME_MARGIN * VOLUME_TOLERANCE * box[0] * box[1] * box[2]
        if width < min_width * (1.0 - 1e-6):
            raise stroke.StrokeError(f"The polygon is too narrow to cut out ({2.0 * width / mm:.3g} mm across): "
                                     f"draw a region at least {MIN_SIZE_MM:g} mm across")
        if thickness < MIN_DEPTH_MM * mm * (1.0 - 1e-6):
            raise stroke.StrokeError(f"The cut-out is too shallow ({thickness / mm:.3g} mm): set a Depth of at "
                                     f"least {MIN_DEPTH_MM:g} mm")
        if volume < needed:
            raise stroke.StrokeError(f"The cut-out is too small for an object this large ({volume / mm ** 3:.3g} "
                                     f"mm^3; the booleans need at least {needed / mm ** 3:.3g} mm^3 here): draw "
                                     "a larger region or a deeper cut-out")
    return PolygonCutter(frame, poly, inner, outer, z0, z_floor, max(gap, 0.0), through)


def polygon_frame(points, direction, corners, depth=0.0):
    """(co, n, t) display frame of a polygon: its floor frame (or the plane of the points without
    a usable polygon)."""
    try:
        return build_cutter(points, direction, corners, 0.0, depth).floor_frame()
    except stroke.StrokeError:
        pts3 = [Vector(p) for p in points]
        frame = stroke.Frame.from_direction(direction, sum(pts3, Vector()) / max(len(pts3), 1))
        return frame.origin, -frame.d, frame.e1.copy()
