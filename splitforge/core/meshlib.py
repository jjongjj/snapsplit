# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# core/meshlib.py
"""BMesh-only mesh helpers: plane split with gap, capping, sections, volume.

Nothing here creates Blender data-blocks; every function works on ``bmesh``
objects owned by the caller. The capping logic is the legacy
``cap_single_object_hollow_style`` (ops_split.py, removed in Phase 3) moved here without edit mode
and without the world-axis assumption: loops are found on the actual cut plane
and nested in the plane's own 2D basis, so any plane normal works.
"""

import bmesh
from mathutils import Vector

from . import log


# ---------------------------------------------------------------------------
# Small geometry helpers (pure)
# ---------------------------------------------------------------------------

def orthonormal_basis(normal, hint=None):
    """Return (n, t, b): unit normal, tangent and bitangent (b = n x t).

    The tangent is ``hint`` projected into the plane; without a usable hint the
    world X axis is used (world Y when the normal is close to X), so the basis
    is deterministic.
    """
    n = Vector(normal).normalized()
    t = None
    if hint is not None:
        h = Vector(hint)
        h = h - n * h.dot(n)
        if h.length > 1e-9:
            t = h.normalized()
    if t is None:
        ref = Vector((1.0, 0.0, 0.0)) if abs(n.x) < 0.9 else Vector((0.0, 1.0, 0.0))
        t = (ref - n * ref.dot(n)).normalized()
    b = n.cross(t).normalized()
    return n, t, b


def poly_area_2d(pts):
    """Absolute area of a 2D polygon (shoelace)."""
    s = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return abs(s) * 0.5


def point_in_poly_2d(pt, poly):
    """Ray casting point-in-polygon test."""
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def point_in_polys_2d(pt, polys):
    """Even-odd test against several loops (outer loops and holes)."""
    return sum(1 for p in polys if point_in_poly_2d(pt, p)) % 2 == 1


def loop_inside_loop_2d(inner, outer):
    """True if every point of ``inner`` lies inside ``outer``."""
    ox = [p[0] for p in outer]
    oy = [p[1] for p in outer]
    x0, x1, y0, y1 = min(ox), max(ox), min(oy), max(oy)
    if any(not (x0 <= x <= x1 and y0 <= y <= y1) for x, y in inner):
        return False
    return all(point_in_poly_2d(p, outer) for p in inner)


def bm_diagonal(bm):
    if not bm.verts:
        return 0.0
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    zs = [v.co.z for v in bm.verts]
    return Vector((max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))).length


def bm_volume(bm):
    return abs(bm.calc_volume(signed=False))


# Grid of the ray integration in winding_volume (rays per bbox side); offsets avoid mesh-aligned rays
WINDING_GRID = 96
_WINDING_JITTER = (0.3819660, 0.6180340)


def winding_volume(bm, grid=WINDING_GRID, bounds=None):
    """Volume of the region a mesh encloses with winding number > 0 (overlaps counted once).

    Integrates along ``grid`` x ``grid`` parallel rays (+Z) over the XY bounds
    (``bounds`` = (x0, x1, y0, y1, z0), default the mesh's): every surface
    crossing changes the winding number by +-1 (by the face normal), and the
    ray length where it is positive is summed. For intersecting shells this is
    the volume of their union, independent of any boolean solver; it is a
    sampled estimate (comparable between meshes only on the same ``bounds``).
    Inward-facing cavity shells subtract as they should.
    """
    from mathutils.bvhtree import BVHTree
    if not bm.faces:
        return 0.0
    if bounds is None:
        bounds = bm_bounds(bm)
    x0, x1, y0, y1, z0 = bounds
    dx, dy = (x1 - x0) / grid, (y1 - y0) / grid
    if dx <= 0.0 or dy <= 0.0:
        return 0.0
    bvh = BVHTree.FromBMesh(bm)
    scale = max(x1 - x0, y1 - y0, 1e-9)
    start_z = z0 - 0.01 * scale
    eps = 1e-7 * scale
    up = Vector((0.0, 0.0, 1.0))
    total = 0.0
    for i in range(grid):
        x = x0 + (i + _WINDING_JITTER[0]) * dx
        for j in range(grid):
            origin = Vector((x, y0 + (j + _WINDING_JITTER[1]) * dy, start_z))
            winding, inside_from, length = 0, None, 0.0
            last_z, last_sign = None, 0
            for _ in range(100000):
                hit, normal, _index, _dist = bvh.ray_cast(origin, up)
                if hit is None:
                    break
                sign = -1 if normal.z > 0.0 else 1      # entering a solid: normal against the ray
                # The same crossing reported twice (ray through a shared edge or vertex)
                if not (last_z is not None and sign == last_sign and hit.z - last_z < 10.0 * eps):
                    before = winding
                    winding += sign
                    if before <= 0 < winding:
                        inside_from = hit.z
                    elif winding <= 0 < before and inside_from is not None:
                        length += hit.z - inside_from
                        inside_from = None
                    last_z, last_sign = hit.z, sign
                origin = Vector((origin.x, origin.y, hit.z + eps))
            total += length
    return total * dx * dy


def bm_bounds(bm):
    """(x0, x1, y0, y1, z0) of the vertices (for winding_volume)."""
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    zs = [v.co.z for v in bm.verts]
    return min(xs), max(xs), min(ys), max(ys), min(zs)


def bm_is_manifold(bm):
    """Every edge has exactly two faces, there are faces and no loose verts."""
    return (len(bm.faces) > 0
            and all(e.is_manifold for e in bm.edges)
            and all(v.link_faces for v in bm.verts))


# ---------------------------------------------------------------------------
# Boundary loops on a plane
# ---------------------------------------------------------------------------

def _decompose_cycles(edges):
    """Split boundary edges into closed cycles (edge lists).

    Open chains are peeled off and returned separately; vertices of degree 4
    (two loops touching in one point) are split into two simple cycles.
    """
    adj = {}
    for e in edges:
        v0, v1 = e.verts
        adj.setdefault(v0, []).append((e, v1))
        adj.setdefault(v1, []).append((e, v0))
    remaining = set(edges)

    def degree(v):
        return sum(1 for e, _ in adj.get(v, ()) if e in remaining)

    chains = []
    while True:
        start = next((v for v in adj if degree(v) == 1), None)
        if start is None:
            break
        chain, cur = [], start
        while True:
            nxt = next(((e, o) for e, o in adj[cur] if e in remaining), None)
            if nxt is None:
                break
            remaining.discard(nxt[0])
            chain.append(nxt[0])
            cur = nxt[1]
            if degree(cur) != 1:  # reached the other end or a branch vertex
                break
        chains.append(chain)

    cycles = []
    while remaining:
        start = next(iter(remaining))
        cur = start.verts[0]
        stack_v, stack_e, index = [cur], [], {cur: 0}
        while True:
            nxt = next(((e, o) for e, o in adj[cur] if e in remaining), None)
            if nxt is None:
                break
            e, other = nxt
            remaining.discard(e)
            i = index.get(other)
            if i is not None:
                cyc = stack_e[i:] + [e]
                if len(cyc) >= 3:
                    cycles.append(cyc)
                for v in stack_v[i + 1:]:
                    del index[v]
                stack_v = stack_v[:i + 1]
                stack_e = stack_e[:i]
            else:
                index[other] = len(stack_v)
                stack_v.append(other)
                stack_e.append(e)
            cur = other
        remaining.discard(start)
    return cycles, chains


def _ordered_verts(cycle_edges):
    """Vertices of a simple closed edge cycle in walking order (None if not simple)."""
    adj = {}
    for e in cycle_edges:
        a, b = e.verts
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    if not adj or any(len(n) != 2 for n in adj.values()):
        return None
    start = next(iter(adj))
    ordered, prev, cur = [start], None, start
    while True:
        n0, n1 = adj[cur]
        nxt = n0 if (prev is None or n0 != prev) else n1
        if nxt == start:
            break
        ordered.append(nxt)
        prev, cur = cur, nxt
        if len(ordered) > len(adj):
            return None
    return ordered if len(ordered) == len(adj) else None


def plane_boundary_cycles(bm, co, no, eps):
    """Closed boundary cycles (edge lists) lying on the plane (co, no)."""
    n = Vector(no).normalized()
    co = Vector(co)

    def on_plane(v):
        return abs((v.co - co).dot(n)) <= eps

    edges = [e for e in bm.edges
             if e.is_boundary and on_plane(e.verts[0]) and on_plane(e.verts[1])]
    cycles, chains = _decompose_cycles(edges)
    if chains:
        log.info("%d open boundary chain(s) on the cut plane cannot be capped "
                 "(the mesh was open there before the cut)", len(chains))
    return cycles


def group_loops_by_nesting(loops_2d):
    """Group 2D loops into outer loops with their direct holes.

    ``loops_2d`` is a list of point lists. A loop enclosed by an odd number of
    other loops is a hole. Returns a list of (outer_index, [hole_indices]).
    """
    areas = [poly_area_2d(p) for p in loops_2d]
    n = len(loops_2d)
    depth, parent = [0] * n, [None] * n
    for j in range(n):
        containers = [i for i in range(n)
                      if i != j and areas[i] > areas[j]
                      and loop_inside_loop_2d(loops_2d[j], loops_2d[i])]
        depth[j] = len(containers)
        parent[j] = min(containers, key=lambda i: areas[i]) if containers else None
    groups = []
    for j in range(n):
        if depth[j] % 2:
            continue
        holes = [k for k in range(n) if depth[k] % 2 == 1 and parent[k] == j]
        groups.append((j, holes))
    return groups


def _fill_group(bm, edges, normal, n_holes, expected_area):
    """Fill one outer loop (+ holes); verify the area so holes stay open."""
    if n_holes == 0:
        try:
            res = bmesh.ops.contextual_create(bm, geom=edges)
            if any(f.is_valid for f in res.get('faces', [])):
                return True
        except Exception as ex:  # contextual_create refuses odd edge nets
            log.debug("contextual_create failed: %s", ex)

    variants = (
        dict(use_beauty=True, use_dissolve=False, normal=normal),
        dict(use_beauty=True, use_dissolve=False),
        dict(use_beauty=True, use_dissolve=True, normal=normal),
    )
    for kwargs in variants:
        res = bmesh.ops.triangle_fill(bm, edges=edges, **kwargs)
        faces = [g for g in res.get('geom', []) if isinstance(g, bmesh.types.BMFace)]
        if not faces:
            continue
        area = sum(f.calc_area() for f in faces)
        if abs(area - expected_area) <= max(0.02 * expected_area, 1e-12):
            return True
        log.debug("triangle_fill area %.6g != expected %.6g, retrying", area, expected_area)
        bmesh.ops.delete(bm, geom=faces, context='FACES')

    if n_holes == 1:
        res = bmesh.ops.bridge_loops(bm, edges=edges, use_pairs=False, use_cyclic=False,
                                     use_merge=False, merge_factor=0.5, twist_offset=0)
        if res.get('faces'):
            return True
    return False


def winding_area_2d(cycle_edges, co, t, b):
    """Signed area of a boundary cycle walked in the winding order of its faces.

    For a solid with consistent normals, outer section loops and hole loops
    come out with opposite signs (overlapping separate shells, e.g. Suzanne's
    eyes inside the head, share the sign of outer loops).
    """
    s = 0.0
    for e in cycle_edges:
        face = e.link_faces[0]
        loop = next(lp for lp in face.loops if lp.edge == e)
        p, q = loop.vert.co - co, loop.link_loop_next.vert.co - co
        s += p.dot(t) * q.dot(b) - q.dot(t) * p.dot(b)
    return 0.5 * s


def group_loops_by_winding(loops_2d, signed_areas):
    """Outer loops with their holes, decided by face winding (see winding_area_2d).

    The largest loop is an outer loop; loops with its sign are outer loops (even
    when nested in another one: a separate overlapping shell), loops with the
    other sign are holes of the smallest outer loop containing them. Returns
    None when a hole has no container (inconsistent normals): the caller then
    falls back to even-odd nesting.
    """
    largest = max(range(len(loops_2d)), key=lambda i: abs(signed_areas[i]))
    sign = 1.0 if signed_areas[largest] > 0 else -1.0
    outers = [i for i, a in enumerate(signed_areas) if a * sign > 0]
    areas = [poly_area_2d(p) for p in loops_2d]
    groups = {i: [] for i in outers}
    for j, a in enumerate(signed_areas):
        if a * sign > 0:
            continue
        containers = [i for i in outers if areas[i] > areas[j] and loop_inside_loop_2d(loops_2d[j], loops_2d[i])]
        if not containers:
            return None
        groups[min(containers, key=lambda i: areas[i])].append(j)
    return sorted(groups.items())


def cap_plane(bm, co, no, eps):
    """Cap the open boundary loops of ``bm`` that lie on the plane.

    Returns (ok, n_loops): ok is False if a loop group could not be filled.
    """
    n, t, b = orthonormal_basis(no)
    co = Vector(co)
    cycles = plane_boundary_cycles(bm, co, n, eps)
    loops, loops_2d, signed = [], [], []
    for cyc in cycles:
        verts = _ordered_verts(cyc)
        if verts is None or len(verts) < 3:
            continue
        loops.append(cyc)
        loops_2d.append([((v.co - co).dot(t), (v.co - co).dot(b)) for v in verts])
        signed.append(winding_area_2d(cyc, co, t, b))
    if not loops:
        return True, 0

    groups = group_loops_by_winding(loops_2d, signed)
    if groups is None:
        log.info("section loops have inconsistent winding; using even-odd nesting")
        groups = group_loops_by_nesting(loops_2d)
    ok = True
    before = set(bm.faces)
    for outer, holes in groups:
        edges = list(loops[outer])
        for k in holes:
            edges += loops[k]
        expected = poly_area_2d(loops_2d[outer]) - sum(poly_area_2d(loops_2d[k]) for k in holes)
        if not _fill_group(bm, edges, n, len(holes), expected):
            log.warning("could not cap a section loop (%d hole(s))", len(holes))
            ok = False
    # Orient the new caps like their surroundings: recalc only the connected
    # regions that received a cap. A separate shell the cut did not touch (an
    # internal cavity, whose normals point into the void) must keep its normals.
    capped = [f for f in bm.faces if f not in before]
    if capped:
        bmesh.ops.recalc_face_normals(bm, faces=connected_faces(capped))
    return ok, len(loops)


def connected_faces(seeds):
    """All faces edge-connected to ``seeds`` (flood fill)."""
    seen = set(seeds)
    stack = list(seeds)
    while stack:
        f = stack.pop()
        for e in f.edges:
            for g in e.link_faces:
                if g not in seen:
                    seen.add(g)
                    stack.append(g)
    return list(seen)


# ---------------------------------------------------------------------------
# Plane split
# ---------------------------------------------------------------------------

def _eps_for(bm):
    return max(bm_diagonal(bm) * 1e-6, 1e-7)


def half_space(bm, co, no, keep_positive, cap=True, eps=None):
    """Copy of ``bm`` clipped to one side of the plane, optionally capped.

    Returns (bm_half, cap_ok). ``bm_half`` has no faces when nothing remains.
    """
    eps = _eps_for(bm) if eps is None else eps
    out = bm.copy()
    geom = out.verts[:] + out.edges[:] + out.faces[:]
    bmesh.ops.bisect_plane(out, geom=geom, dist=eps, plane_co=Vector(co), plane_no=Vector(no),
                           use_snap_center=False,
                           clear_outer=not keep_positive, clear_inner=keep_positive)
    # Remove what bisect left dangling (wire edges, lone vertices)
    loose = [e for e in out.edges if not e.link_faces]
    if loose:
        bmesh.ops.delete(out, geom=loose, context='EDGES')
    lone = [v for v in out.verts if not v.link_edges]
    if lone:
        bmesh.ops.delete(out, geom=lone, context='VERTS')
    cap_ok = True
    if cap and out.faces:
        cap_ok, _ = cap_plane(out, co, no, eps * 10.0)
    out.normal_update()
    return out, cap_ok


def split_by_plane(bm, co, no, gap=0.0, cap=True):
    """Split ``bm`` by a plane into (positive, negative) halves with a gap.

    The positive half keeps everything above ``co + no*gap/2``, the negative
    half everything below ``co - no*gap/2``; ``gap`` is in the same units as
    the mesh. Returns (bm_pos, bm_neg, cap_ok).
    """
    n = Vector(no).normalized()
    co = Vector(co)
    half = max(gap, 0.0) * 0.5
    eps = _eps_for(bm)
    pos, ok_p = half_space(bm, co + n * half, n, True, cap, eps)
    neg, ok_n = half_space(bm, co - n * half, n, False, cap, eps)
    return pos, neg, ok_p and ok_n


def section_loops_2d(bm, co, no, t, b):
    """Cross-section of a closed mesh with the plane as 2D loops in (t, b) coordinates."""
    co = Vector(co)
    eps = _eps_for(bm)
    tmp, _ = half_space(bm, co, no, True, cap=False, eps=eps)
    try:
        loops = []
        for cyc in plane_boundary_cycles(tmp, co, no, eps * 10.0):
            verts = _ordered_verts(cyc)
            if verts and len(verts) >= 3:
                loops.append([((v.co - co).dot(t), (v.co - co).dot(b)) for v in verts])
        return loops
    finally:
        tmp.free()


def transform_bm(bm, matrix):
    """Apply a 4x4 matrix to all vertices, keeping normals outward for mirrors."""
    bm.transform(matrix)
    if matrix.to_3x3().determinant() < 0.0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    bm.normal_update()


def shells(bm):
    """Connected shells of ``bm`` as lists of vertices (edge-connected flood fill)."""
    seen = set()
    out = []
    for v in bm.verts:
        if v in seen:
            continue
        seen.add(v)
        stack, shell = [v], []
        while stack:
            cur = stack.pop()
            shell.append(cur)
            for e in cur.link_edges:
                other = e.other_vert(cur)
                if other not in seen:
                    seen.add(other)
                    stack.append(other)
        out.append(shell)
    return out

