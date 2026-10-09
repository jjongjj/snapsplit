# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# connectors/shapes.py
"""Connector solids: one description used for the geometry AND the fit checks.

Every connector type is a set of closed solids in the connector's local frame
(Z along the cut normal, the seam plane at z = 0, ``matrix`` maps the frame to
world space, see placement.frame_matrix):

- ``Loft``: a cross-section (ROUND circle or RECT rectangle) swept through
  sections (z, half width u, half width v). Prisms, tapered (dovetail) frusta
  and chamfered tips are lofts.
- ``Ball``: a sphere (snap bumps on the pin, snap dimples in the socket).
- ``MeshSolid``: a user mesh (custom connector), scaled into the connector box.

``connector_solids(spec)`` returns which solids are added to the pin part
(UNION), cut from the pin part (DIFFERENCE, only the double-sided dowel) and cut
from the socket part (DIFFERENCE). Build adds them to bmeshes (``add_to``);
connectors/fit.py samples their surfaces (``samples``/``segments_for``), so the
containment checks always test exactly the geometry that is built.

Clearance is applied per face, perpendicular to it (a mitered offset, never
a scale): prisms grow by the clearance on every side; tapered faces by
clearance / cos(taper angle) at a given height, so the gap measured normal to
the slanted face is the clearance; snap dimples by the clearance in radius; a
custom mesh is grown by the clearance in every direction (connectors/custom_socket.py:
vertex-normal offset when that is clean, else a Minkowski sum; checked). The socket follows the pin as it sits after
assembly: the pin part moves by the gap towards the socket part, so tapered
sockets and snap dimples are shifted by the gap.

Spans along Z (pin side s = +1 for pin side A, -1 for B; hg = gap / 2; e =
embed fraction; L = length; c = clearance):

- pin: from s*(hg + e*L) (embedded base) to s*(hg - (1 - e)*L) (tip)
- socket: from s*(hg + 0.1*L) (behind the seam, so the boolean never meets a
  coplanar face) to -s*(hg + (1 - e)*L + c) (tip depth + clearance)
- dowel: no pin; both parts get a socket of depth L/2 + c, and the dowel is a
  separate part (``Solids.dowel``).

Pure mathutils/bmesh, except the custom socket (connectors/custom_socket.py, temporary booleans).
"""

import math
from dataclasses import dataclass, field

import bmesh
from mathutils import Matrix, Vector

CYLINDER_SEGMENTS = 32
BALL_SEGMENTS = 16
BALL_RINGS = 8

# Sampling of the fit checks (connectors/fit.py)
MIN_RING = 24
MIN_RINGS = 9
MIN_BALL_RINGS = 5

ROUND_KINDS = {'CYL_PIN', 'SNAP_PIN', 'DOWEL'}
RECT_KINDS = {'RECT_TENON', 'SNAP_TENON', 'DOVETAIL', 'SNAP_DOVETAIL'}
SNAP_KINDS = {'SNAP_PIN', 'SNAP_TENON', 'SNAP_DOVETAIL'}
TAPER_KINDS = {'DOVETAIL', 'SNAP_DOVETAIL'}
ALL_KINDS = ROUND_KINDS | RECT_KINDS | {'CUSTOM'}

# Largest taper (fraction of the base width the tip loses) and chamfer share
MAX_TAPER = 0.6
MAX_CHAMFER_SHARE = 0.45


def profile_of(kind):
    return 'ROUND' if kind in ROUND_KINDS else 'RECT'


# ---------------------------------------------------------------------------
# Sampling helpers
# ---------------------------------------------------------------------------

def _clean(x, r):
    # cos(pi/2) = 6e-17, not 0: near-zero noise next to exact zeros (axis-aligned connectors, faces)
    # made the exact boolean return non-manifold results
    return 0.0 if abs(x) < 1e-12 * r else x


def _round_outline(r, n):
    return [(_clean(r * math.cos(2 * math.pi * k / n), r), _clean(r * math.sin(2 * math.pi * k / n), r))
            for k in range(n)]


def _rect_outline(hu, hv, per_edge=1):
    pts = []
    for (x0, y0), (x1, y1) in (((-hu, -hv), (hu, -hv)), ((hu, -hv), (hu, hv)),
                               ((hu, hv), (-hu, hv)), ((-hu, hv), (-hu, -hv))):
        pts += [(x0 + (x1 - x0) * k / per_edge, y0 + (y1 - y0) * k / per_edge) for k in range(per_edge)]
    return pts


def grid_samples(grid):
    rings, caps = grid
    return list(caps) + [p for ring in rings for p in ring]


def grid_segments(grid):
    """Segments between neighbouring samples of a (rings, caps) grid (rings of equal length)."""
    rings, caps = grid
    out = []
    for i, ring in enumerate(rings):
        n = len(ring)
        for k in range(n):
            out.append((ring[k], ring[(k + 1) % n]))
            if i + 1 < len(rings):
                out.append((ring[k], rings[i + 1][k]))
    if caps:
        out += [(caps[0], p) for p in rings[0]]
        out += [(caps[-1], p) for p in rings[-1]]
    return out


# ---------------------------------------------------------------------------
# Solids
# ---------------------------------------------------------------------------

class Loft:
    """A ROUND or RECT cross-section through sections [(z, hu, hv)] (local frame)."""

    def __init__(self, profile, sections, matrix, segments=CYLINDER_SEGMENTS):
        self.profile = profile
        self.sections = sorted(((z, max(hu, 1e-9), max(hv, 1e-9)) for z, hu, hv in sections),
                               key=lambda s: s[0])
        self.matrix = matrix
        self.segments = segments

    def _outline(self, hu, hv, max_step=None):
        if self.profile == 'ROUND':
            n = self.segments if max_step is None else max(MIN_RING, math.ceil(2 * math.pi * hu / max_step))
            return _round_outline(hu, n)
        per_edge = 1 if max_step is None else max(4, math.ceil(2 * max(hu, hv) / max_step))
        return _rect_outline(hu, hv, per_edge)

    def add_to(self, bm):
        m = self.matrix
        rings = [[bm.verts.new(m @ Vector((x, y, z))) for x, y in self._outline(hu, hv)]
                 for z, hu, hv in self.sections]
        n = len(rings[0])
        for lo, hi in zip(rings, rings[1:]):
            for k in range(n):
                bm.faces.new((lo[k], lo[(k + 1) % n], hi[(k + 1) % n], hi[k]))
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])

    def at(self, z):
        """(hu, hv) at height z (linear between sections, constant beyond the ends)."""
        secs = self.sections
        for (z0, u0, v0), (z1, u1, v1) in zip(secs, secs[1:]):
            if z0 <= z <= z1:
                f = 0.0 if z1 == z0 else (z - z0) / (z1 - z0)
                return u0 + (u1 - u0) * f, v0 + (v1 - v0) * f
        return (secs[0][1], secs[0][2]) if z < secs[0][0] else (secs[-1][1], secs[-1][2])

    def grid(self, max_step=None):
        z0, z1 = self.sections[0][0], self.sections[-1][0]
        n_rings = MIN_RINGS if not max_step else max(MIN_RINGS, math.ceil(abs(z1 - z0) / max_step) + 1)
        zs = sorted({z0 + (z1 - z0) * k / (n_rings - 1) for k in range(n_rings)} | {s[0] for s in self.sections})
        hu_max = max(s[1] for s in self.sections)
        hv_max = max(s[2] for s in self.sections)
        # One point count for every ring (neighbouring rings are connected point by point)
        base = self._outline(hu_max, hv_max, max_step)
        m = self.matrix
        rings = []
        for z in zs:
            hu, hv = self.at(z)
            sx = hu / hu_max
            sy = sx if self.profile == 'ROUND' else hv / hv_max
            rings.append([m @ Vector((x * sx, y * sy, z)) for x, y in base])
        caps = [m @ Vector((0.0, 0.0, z)) for z in (zs[0], zs[-1])]
        return rings, caps

    def samples(self, max_step=None):
        return grid_samples(self.grid(max_step))

    def segments_for(self, max_step=None):
        return grid_segments(self.grid(max_step))

    def reach(self):
        if self.profile == 'ROUND':
            return max(s[1] for s in self.sections)
        return max(math.hypot(s[1], s[2]) for s in self.sections)

    def z_range(self):
        return self.sections[0][0], self.sections[-1][0]


class Ball:
    """Sphere at ``center`` (local frame) with ``radius``."""

    def __init__(self, center, radius, matrix):
        self.center, self.radius, self.matrix = Vector(center), radius, matrix

    def add_to(self, bm):
        bmesh.ops.create_uvsphere(bm, u_segments=BALL_SEGMENTS, v_segments=BALL_RINGS, radius=self.radius,
                                  matrix=self.matrix @ Matrix.Translation(self.center))

    def grid(self, max_step=None):
        r = self.radius
        n = MIN_RING if not max_step else max(MIN_RING, math.ceil(2 * math.pi * r / max_step))
        n_lat = MIN_BALL_RINGS if not max_step else max(MIN_BALL_RINGS, math.ceil(math.pi * r / max_step) - 1)
        m = self.matrix
        c = self.center
        rings = []
        for i in range(1, n_lat + 1):
            phi = math.pi * i / (n_lat + 1)
            z, rr = -r * math.cos(phi), r * math.sin(phi)
            rings.append([m @ (c + Vector((x, y, z))) for x, y in _round_outline(rr, n)])
        caps = [m @ (c + Vector((0.0, 0.0, -r))), m @ (c + Vector((0.0, 0.0, r)))]
        return rings, caps

    def samples(self, max_step=None):
        return grid_samples(self.grid(max_step))

    def segments_for(self, max_step=None):
        return grid_segments(self.grid(max_step))

    def reach(self):
        return Vector((self.center.x, self.center.y)).length + self.radius

    def z_range(self):
        return self.center.z - self.radius, self.center.z + self.radius


class MeshSolid:
    """A closed user mesh: local vertices + faces (outward winding)."""

    def __init__(self, verts, faces, matrix):
        self.verts, self.faces, self.matrix = [Vector(v) for v in verts], faces, matrix

    def add_to(self, bm):
        m = self.matrix
        new = [bm.verts.new(m @ v) for v in self.verts]
        for f in self.faces:
            bm.faces.new([new[i] for i in f])

    def _edges(self):
        edges = set()
        for f in self.faces:
            for i in range(len(f)):
                a, b = f[i], f[(i + 1) % len(f)]
                edges.add((min(a, b), max(a, b)))
        return edges

    def _edge_points(self, max_step):
        out = []
        for a, b in self._edges():
            pa, pb = self.verts[a], self.verts[b]
            n = 1 if not max_step else max(1, math.ceil((pb - pa).length / max_step))
            out.append([pa + (pb - pa) * k / n for k in range(n + 1)])
        return out

    def _center(self, f):
        return sum((self.verts[i] for i in f), Vector()) / len(f)

    def samples(self, max_step=None):
        m = self.matrix
        pts = [m @ v for v in self.verts]
        for chain in self._edge_points(max_step):
            pts += [m @ p for p in chain[1:-1]]
        pts += [m @ self._center(f) for f in self.faces]
        return pts

    def segments_for(self, max_step=None):
        m = self.matrix
        out = []
        for chain in self._edge_points(max_step):
            w = [m @ p for p in chain]
            out += list(zip(w, w[1:]))
        for f in self.faces:
            c = m @ self._center(f)
            out += [(c, m @ self.verts[i]) for i in f]
        return out

    def reach(self):
        return max(Vector((v.x, v.y)).length for v in self.verts)

    def z_range(self):
        zs = [v.z for v in self.verts]
        return min(zs), max(zs)


# ---------------------------------------------------------------------------
# Custom connector meshes
# ---------------------------------------------------------------------------

# Largest face count of a custom connector mesh (it is copied into every connector)
CUSTOM_MAX_FACES = 20000
# Thinnest bbox side of a custom mesh, relative to its largest (flat meshes are rejected)
CUSTOM_MIN_ASPECT = 0.01


@dataclass
class CustomShape:
    """A custom connector mesh normalized to the unit box: x, y in [-0.5, 0.5], z in [0, 1]
    (z = 0 is the embedded base, z = 1 the tip). Faces wind outward."""
    name: str
    verts: list
    faces: list


def custom_shape(mesh_bm, name="custom"):
    """(CustomShape, "") from a bmesh in the object's local space, or (None, reason).

    The mesh must be closed and manifold, enclose a volume, have at most
    CUSTOM_MAX_FACES faces and no flat bounding box. Normals are recalculated
    outward (flipped user normals would invert the socket).
    """
    bm = mesh_bm.copy()
    try:
        if not bm.faces:
            return None, f"custom connector '{name}' has no faces"
        if len(bm.faces) > CUSTOM_MAX_FACES:
            return None, f"custom connector '{name}' has {len(bm.faces)} faces (at most {CUSTOM_MAX_FACES})"
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context='VERTS')
        if not all(e.is_manifold for e in bm.edges):
            return None, (f"custom connector '{name}' is not a closed manifold mesh (open or shared edges); "
                          "use a watertight solid")
        xs = [v.co.x for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        zs = [v.co.z for v in bm.verts]
        ext = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
        if min(ext) <= CUSTOM_MIN_ASPECT * max(ext):
            return None, (f"custom connector '{name}' is flat "
                          f"(bounding box {ext[0]:.3g} x {ext[1]:.3g} x {ext[2]:.3g})")
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        if bm.calc_volume(signed=True) < 0.0:
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        if bm.calc_volume(signed=True) < 1e-3 * ext[0] * ext[1] * ext[2]:
            return None, f"custom connector '{name}' encloses almost no volume"
        cx, cy = (max(xs) + min(xs)) * 0.5, (max(ys) + min(ys)) * 0.5
        z0 = min(zs)
        bm.verts.index_update()
        verts = [((v.co.x - cx) / ext[0], (v.co.y - cy) / ext[1], (v.co.z - z0) / ext[2]) for v in bm.verts]
        faces = [tuple(v.index for v in f.verts) for f in bm.faces]
        return CustomShape(name, verts, faces), ""
    finally:
        bm.free()


def _custom_local(shape, width, height, length, z_base, s):
    """Vertices of a custom shape in the connector frame: x -> width, y -> height, z from the base
    (z_base) towards the tip (direction -s). For s = +1 the frame turns 180 degrees about X
    (y flips with z), a rotation, so the faces keep their outward winding."""
    sigma = -s
    return [Vector((x * width, sigma * y * height, z_base - s * z * length)) for x, y, z in shape.verts]


# ---------------------------------------------------------------------------
# Connector -> solids
# ---------------------------------------------------------------------------

@dataclass
class Solids:
    pin: list = field(default_factory=list)          # UNION on the pin part
    pin_socket: list = field(default_factory=list)   # DIFFERENCE on the pin part (dowel)
    socket: list = field(default_factory=list)       # DIFFERENCE on the socket part
    dowel: tuple = None                              # (diameter, length, chamfer) of a separate dowel part
    notes: list = field(default_factory=list)        # warnings about the geometry (custom socket clearance)

    def all(self):
        return self.pin + self.pin_socket + self.socket


def snap_bumps(spec, pin_loft, z):
    """[(local center, radius)] of the snap bumps around a pin loft at height z (evenly around)."""
    hu, hv = pin_loft.at(z)
    rs = 0.5 * spec.snap_diameter
    count = max(1, spec.snap_count)
    out = []
    for i in range(count):
        a = 2 * math.pi * i / count
        ca, sa = math.cos(a), math.sin(a)
        if pin_loft.profile == 'ROUND':
            r = hu
        else:
            r = min(hu / abs(ca) if abs(ca) > 1e-9 else math.inf, hv / abs(sa) if abs(sa) > 1e-9 else math.inf)
        d = r + spec.snap_protrusion - rs
        out.append((Vector((d * ca, d * sa, z)), rs))
    return out


def connector_solids(spec, pin_positive=None):
    """Solids of a ConnectorSpec (lengths in Blender units), see the module docstring."""
    side = spec.pin_positive if pin_positive is None else pin_positive
    m = spec.matrix
    L, c, hg = spec.length, spec.clearance, max(spec.gap, 0.0) * 0.5
    kind = spec.kind
    if kind == 'DOWEL':
        r = spec.width * 0.5
        sock_neg = Loft('ROUND', [(hg + 0.1 * L, r + c, r + c), (-(hg + 0.5 * L + c), r + c, r + c)], m)
        sock_pos = Loft('ROUND', [(-(hg + 0.1 * L), r + c, r + c), (hg + 0.5 * L + c, r + c, r + c)], m)
        # The dowel's "pin part" is the positive side: it gets the positive socket
        return Solids(pin_socket=[sock_pos], socket=[sock_neg], dowel=(spec.width, L, spec.chamfer))
    s = 1.0 if side else -1.0
    e = min(max(spec.embed, 0.05), 0.95)
    z_base, z_tip = s * (hg + e * L), s * (hg - (1.0 - e) * L)
    z_sock0, z_sock1 = s * (hg + 0.1 * L), -s * (hg + (1.0 - e) * L + c)

    if kind == 'CUSTOM':
        from . import custom_socket
        shape = spec.custom
        verts = _custom_local(shape, spec.width, spec.height, L, z_base, s)
        step = max(min(spec.width, spec.height, L) / 16.0, 1e-6)
        sock, sock_faces, _got, note = custom_socket.socket(verts, shape.faces, c, step)
        sock = [v - Vector((0.0, 0.0, s * spec.gap)) for v in sock]
        return Solids(pin=[MeshSolid(verts, shape.faces, m)], socket=[MeshSolid(sock, sock_faces, m)],
                      notes=[note] if note else [])

    profile = profile_of(kind)
    hu = spec.width * 0.5
    hv = hu if profile == 'ROUND' else spec.height * 0.5
    taper = min(max(spec.taper, 0.0), MAX_TAPER) if kind in TAPER_KINDS else 0.0
    tu, tv = hu * (1.0 - taper), hv * (1.0 - taper)

    def pin_half(z):
        f = (z - z_base) / (z_tip - z_base)
        return hu + (tu - hu) * f, hv + (tv - hv) * f

    sections = [(z_base, hu, hv)]
    ch = min(spec.chamfer, MAX_CHAMFER_SHARE * min(tu, tv), MAX_CHAMFER_SHARE * (1.0 - e) * L)
    if ch > 1e-9:
        zc = z_tip + s * ch
        u, v = pin_half(zc)
        sections += [(zc, u, v), (z_tip, tu - ch, tv - ch)]
    else:
        sections.append((z_tip, tu, tv))
    pin = Loft(profile, sections, m)
    # Mitered offset of the (gap-shifted) pin: c / cos(slope) wider at each height
    sec_u = math.sqrt(1.0 + ((hu - tu) / L) ** 2)
    sec_v = math.sqrt(1.0 + ((hv - tv) / L) ** 2)

    def socket_half(z):
        u, v = pin_half(z + s * spec.gap)
        return u + c * sec_u, v + c * sec_v
    socket = Loft(profile, [(z, *socket_half(z)) for z in (z_sock0, z_sock1)], m)
    out = Solids(pin=[pin], socket=[socket])
    if kind in SNAP_KINDS:
        unchamfered = Loft(profile, [(z_base, hu, hv), (z_tip, tu, tv)], m)
        z_b = s * (hg - 0.5 * (1.0 - e) * L)
        for center, rs in snap_bumps(spec, unchamfered, z_b):
            out.pin.append(Ball(center, rs, m))
            out.socket.append(Ball(center - Vector((0.0, 0.0, s * spec.gap)), rs + c, m))
    return out


def capsule(spec, solids):
    """(axis start, axis end, radius) in world space around all solids of a connector."""
    z0 = min(sd.z_range()[0] for sd in solids.all())
    z1 = max(sd.z_range()[1] for sd in solids.all())
    r = max(sd.reach() for sd in solids.all())
    return spec.matrix @ Vector((0.0, 0.0, z0)), spec.matrix @ Vector((0.0, 0.0, z1)), r


def seam_outline(kind, width, height, segments=24):
    """Cross-section outline at the seam (local XY), for the viewport overlay."""
    if kind == 'CUSTOM' or profile_of(kind) == 'RECT':
        return _rect_outline(width * 0.5, height * 0.5)
    return _round_outline(width * 0.5, segments)


def reach(kind, width, height, snap_protrusion=0.0):
    """Largest in-plane distance of a connector's seam outline from its center (any rotation)."""
    r = 0.5 * math.hypot(width, height) if kind == 'CUSTOM' or profile_of(kind) == 'RECT' else 0.5 * width
    return r + (snap_protrusion if kind in SNAP_KINDS else 0.0)


def dowel_bmesh(bm, diameter, length, chamfer, matrix):
    """A dowel (cylinder along local Z centered at the origin, chamfered ends) added to ``bm``."""
    r = diameter * 0.5
    ch = min(chamfer, MAX_CHAMFER_SHARE * r, 0.25 * length)
    h = length * 0.5
    if ch > 1e-9:
        sections = [(-h, r - ch, r - ch), (-h + ch, r, r), (h - ch, r, r), (h, r - ch, r - ch)]
    else:
        sections = [(-h, r, r), (h, r, r)]
    Loft('ROUND', sections, matrix).add_to(bm)
