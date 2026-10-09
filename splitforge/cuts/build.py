# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# cuts/build.py
"""Build pipeline: source copy -> enabled cuts in order -> connectors -> result collection.

The source object is never modified: its evaluated mesh (modifiers applied) is
copied into a bmesh, transformed to world space and split there. The parts are
new objects with identity transforms in the collection
``naming.build_collection_name(source)``; a rebuild replaces that collection's
previous parts (same collection, no leftovers). Only the source's viewport
visibility (``hide_set``) changes.

Cuts are applied to every current piece in stack order:

- PLANE: bisect with gap + cap (cuts/plane.py, no boolean)
- STROKE: two boolean DIFFERENCEs with the ribbon cutters (cuts/stroke.py) on
  pieces the ribbon touches, verified as a pair (volume conservation: part A +
  part B + gap volume = piece) and retried with the next solver when the pair
  does not add up; pieces it does not touch are kept whole on their side.

``build_steps`` is a generator that yields after each progress step (two per
piece and cut, one per connector boolean), so the Build operator can run it
from a modal timer with progress feedback; ``build`` runs it to the end. All
stack data is read into plain values before the first yield.
"""

from dataclasses import dataclass, field

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from ..connectors import apply as conn_apply
from ..connectors import fit, placement
from ..core import boolean, log, meshlib, naming, progress, units
from ..model import stack as stack_api
from . import plane, stroke


# Largest spacing of the connector surface samples (connectors/fit.py)
FIT_STEP_MM = 1.0
# Stroke split: part A + part B + gap volume must match the piece volume within
# PAIR_TOLERANCE (relative) + PAIR_ABS_TOLERANCE x bbox diagonal^3. Pieces are triangulated
# before the booleans, so no solver can change the volume by re-triangulating non-planar faces
# (defect D13). Loose only where it must be: intersecting shells left overlapping (Fast) and the
# voxel fallback (approximated surface).
PAIR_TOLERANCE = 1e-3
PAIR_TOLERANCE_LOOSE = 0.04
PAIR_ABS_TOLERANCE = 1e-7


class BuildError(Exception):
    pass


@dataclass
class BuildResult:
    collection: str
    parts: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    infos: list = field(default_factory=list)
    booleans: list = field(default_factory=list)   # [(label, solver, attempts)]


@dataclass
class _Piece:
    bm: object
    sides: str = ""


# ---------------------------------------------------------------------------
# Cut specs (world space, Blender units, plain values)
# ---------------------------------------------------------------------------

@dataclass
class PlaneCut:
    label: str
    uid: str
    co: Vector
    n: Vector
    t: Vector
    gap: float
    cap: bool
    kind: str = 'PLANE'

    def barrier(self):
        return fit.PlaneBarrier(self.co, self.n, self.gap)

    def matrix(self, u, v, rotation_deg):
        return placement.frame_matrix(self.co, self.n, self.t, u, v, rotation_deg)

    def side(self, p):
        return 1 if (Vector(p) - self.co).dot(self.n) >= 0.0 else -1


@dataclass
class StrokeCut:
    label: str
    uid: str
    cutter: object        # stroke.StrokeCutter
    gap: float
    kind: str = 'STROKE'
    _barrier: object = None
    _centerline: object = None

    def barrier(self):
        """fit.RibbonBarrier: ribbon BVH + exact side test (built once)."""
        if self._barrier is None:
            ribbon = self.cutter.ribbon()
            try:
                self._barrier = fit.RibbonBarrier(BVHTree.FromBMesh(ribbon), self.gap, self.cutter.is_positive,
                                                  self.cutter.ribbon_face_interior)
            finally:
                ribbon.free()
        return self._barrier

    def centerline(self):
        if self._centerline is None:
            self._centerline = stroke.centerline(self.cutter)
        return self._centerline

    def matrix(self, u, v, rotation_deg):
        return self.centerline().matrix(u, v, rotation_deg)

    def side(self, p):
        return 1 if self.barrier().positive(Vector(p)) else -1


def stroke_world(matrix_world, cut):
    """(world points, world extrusion direction) of a STROKE cut."""
    m = matrix_world
    points = [m @ p for p in stack_api.stroke_points(cut)]
    return points, (m.to_3x3() @ Vector(cut.direction)).normalized()


def world_corners(obj):
    return [obj.matrix_world @ Vector(c) for c in obj.bound_box]


def cut_spec(obj, cut, scene):
    """PlaneCut/StrokeCut of a stack cut in world space (BU). Raises BuildError for a bad stroke."""
    mm = units.mm_to_scene(1.0, scene)
    gap = cut.gap_mm * mm
    if cut.kind == 'STROKE':
        points, d = stroke_world(obj.matrix_world, cut)
        try:
            cutter = stroke.build_cutter(points, d, world_corners(obj), gap)
        except stroke.StrokeError as ex:
            raise BuildError(f"{cut.name}: {ex}") from None
        return StrokeCut(cut.name, cut.uid, cutter, gap)
    co, n, t, _b = plane.world_frame(obj.matrix_world, cut.origin, cut.normal, cut.tangent)
    return PlaneCut(cut.name, cut.uid, co, n, t, gap, cut.cap)


def cut_specs(obj, cuts, scene):
    return [cut_spec(obj, cut, scene) for cut in cuts]


def fit_planes(obj, cuts, scene):
    """{cut uid: fit barrier} (world space / BU) of ``cuts``, for connectors/fit.check."""
    return {s.uid: s.barrier() for s in cut_specs(obj, cuts, scene)}


def source_bmesh(obj, depsgraph):
    """World-space bmesh of the evaluated source object (caller frees it)."""
    bm = bmesh.new()
    bm.from_object(obj, depsgraph)
    meshlib.transform_bm(bm, obj.matrix_world)
    return bm


# ---------------------------------------------------------------------------
# Splitting pieces
# ---------------------------------------------------------------------------

def _plane_split(piece, spec, warnings, prog):
    """Generator: (positive, negative) halves of a piece bmesh by a PlaneCut (2 progress steps)."""
    half = max(spec.gap, 0.0) * 0.5
    lo, hi = plane.signed_distances(piece, spec.co, spec.n)
    eps = max(meshlib.bm_diagonal(piece) * 1e-6, 1e-7)
    pos = neg = None
    ok = True
    prog.step(f"{spec.label}: side A")
    yield
    if lo >= half - eps:
        pos = piece.copy()
    elif hi > half - eps:
        pos, ok_p = meshlib.half_space(piece, spec.co + spec.n * half, spec.n, True, spec.cap, eps)
        ok = ok and ok_p
    prog.step(f"{spec.label}: side B")
    yield
    if hi <= -half + eps:
        neg = piece.copy()
    elif lo < -half + eps:
        neg, ok_n = meshlib.half_space(piece, spec.co - spec.n * half, spec.n, False, spec.cap, eps)
        ok = ok and ok_n
    if not ok:
        warnings.append(f"{spec.label}: a section loop could not be capped")
    out = []
    for bm in (pos, neg):
        if bm is not None and not bm.faces:
            bm.free()
            bm = None
        out.append(bm)
    return out[0], out[1]


def ribbon_bvh(cutter, curve):
    """BVHTree of the ribbon of a 2D curve of ``cutter`` (open surface over its depth range, sliced)."""
    bm = bmesh.new()
    try:
        cutter.ribbon(bm, curve)
        return BVHTree.FromBMesh(bm)
    finally:
        bm.free()


def cap_area(bm, bvh, eps):
    """Area of the faces of ``bm`` lying on the surface in ``bvh`` (seam faces a boolean created)."""
    area = 0.0
    for f in bm.faces:
        hit = bvh.find_nearest(f.calc_center_median())
        if hit[0] is not None and hit[3] <= eps:
            area += f.calc_area()
    return area


def _stroke_split(piece, spec, quality, self_intersect, prog, booleans, warnings):
    """Generator: (positive, negative) bmeshes of a piece cut by a StrokeCut (2 progress steps).

    A side is computed with a boolean only where the piece crosses that side's
    ribbon; otherwise the piece lies wholly on one side (kept as a copy, or
    nothing). With both sides cut, the pair must conserve the volume (tightly,
    unless shells intersect or the voxel fallback was used); if not, both are
    redone with the solvers after the ones that produced them. A voxel fallback
    is reported in ``warnings``.
    """
    cutter = spec.cutter
    piece_bvh = BVHTree.FromBMesh(piece)
    tri = None
    plus_bvh = ribbon_bvh(cutter, cutter.plus)
    minus_bvh = plus_bvh if cutter.minus is cutter.plus else ribbon_bvh(cutter, cutter.minus)
    crosses = {'A': bool(piece_bvh.overlap(plus_bvh)), 'B': bool(piece_bvh.overlap(minus_bvh))}
    probe = cutter.frame.to2d(next(iter(piece.verts)).co) if piece.verts else (0.0, 0.0)
    keep = {'A': stroke.point_in_polygon(probe, stroke.left_polygon(cutter.plus, cutter.box)),
            'B': not stroke.point_in_polygon(probe, stroke.left_polygon(cutter.minus, cutter.box))}
    makers = {'A': cutter.remove_for_a, 'B': cutter.remove_for_b}

    order = boolean.attempt_order(quality, self_intersect, faces=len(piece.faces))
    start = 0
    while True:
        results, out = {}, {}
        try:
            for key in ('A', 'B'):
                prog.step(f"{spec.label}: side {key}")
                yield
                if not crosses[key]:
                    out[key] = piece.copy() if keep[key] else None
                    continue
                if tri is None:
                    tri = piece.copy()
                    bmesh.ops.triangulate(tri, faces=tri.faces[:])
                operand = makers[key]()
                try:
                    res, bm = boolean.apply_bm(tri, operand, 'DIFFERENCE', quality, order=order[start:])
                finally:
                    operand.free()
                results[key] = res
                booleans.append((f"{spec.label} side {key}", res.solver, res.attempts))
                if not res.ok:
                    raise BuildError(f"{spec.label}: the curved cut failed with every boolean solver "
                                     f"({res.message}). Nothing was changed.")
                out[key] = bm
        except BaseException:
            for bm in out.values():
                if bm is not None:
                    bm.free()
            if tri is not None:
                tri.free()
            raise
        if len(results) < 2:
            if tri is not None:
                tri.free()
            return out['A'], out['B']
        volume = meshlib.bm_volume(tri)
        va, vb = meshlib.bm_volume(out['A']), meshlib.bm_volume(out['B'])
        eps = max(meshlib.bm_diagonal(piece) * 1e-4, 1e-6)
        gap_volume = cutter.gap * 0.5 * (cap_area(out['A'], plus_bvh, eps) + cap_area(out['B'], minus_bvh, eps))
        loose = self_intersect or any(r.solver == boolean.VOXEL for r in results.values())
        diag = meshlib.bm_diagonal(piece)
        tight = volume * PAIR_TOLERANCE + PAIR_ABS_TOLERANCE * diag ** 3
        tol = volume * PAIR_TOLERANCE_LOOSE if loose else tight
        lo = volume - gap_volume - tol
        hi = volume - gap_volume + tight
        if lo <= va + vb <= hi:
            warnings.extend(r.message for r in results.values() if r.message)
            tri.free()
            return out['A'], out['B']
        used = max(order.index(r.solver) for r in results.values())
        msg = (f"{spec.label}: parts A + B = {va + vb:.6g} for a piece of {volume:.6g} "
               f"(gap {gap_volume:.6g}) with {', '.join(r.solver for r in results.values())}")
        for bm in out.values():
            bm.free()
        if used + 1 >= len(order):
            tri.free()
            raise BuildError(msg + "; no solver left. Nothing was changed.")
        log.info("%s; retrying with %s", msg, order[used + 1])
        start = used + 1
        prog.set_total(prog.total + 2)


def iter_cut_pieces(bm, specs, warnings, quality='AUTO', prog=None, self_intersect=False, booleans=None):
    """Generator applying ``specs`` in order (yields after each progress step). Consumes ``bm``.

    Returns (StopIteration value) a list of _Piece; ``sides`` has one letter per
    cut (A = positive side, B = negative side).
    """
    prog = prog if prog is not None else progress.Progress(2 * len(specs), "Cut")
    booleans = booleans if booleans is not None else []
    pieces, out = [_Piece(bm)], []
    try:
        for i, spec in enumerate(specs):
            prog.set_total(prog.done + 2 * len(pieces) + 2 * (len(specs) - i - 1))
            out = []
            while pieces:
                piece = pieces.pop(0)
                try:
                    if spec.kind == 'STROKE':
                        pos, neg = yield from _stroke_split(piece.bm, spec, quality, self_intersect, prog,
                                                            booleans, warnings)
                    else:
                        pos, neg = yield from _plane_split(piece.bm, spec, warnings, prog)
                finally:
                    piece.bm.free()
                if pos is not None:
                    out.append(_Piece(pos, piece.sides + "A"))
                if neg is not None:
                    out.append(_Piece(neg, piece.sides + "B"))
            pieces, out = out, []
    except BaseException:
        for p in pieces + out:
            p.bm.free()
        raise
    return pieces


def cut_pieces(bm, specs, warnings, quality='AUTO'):
    """``iter_cut_pieces`` run to the end (no progress UI). Consumes ``bm``."""
    return run_steps(iter_cut_pieces(bm, specs, warnings, quality))


# ---------------------------------------------------------------------------
# Shells
# ---------------------------------------------------------------------------

def _bvh_of(verts):
    index = {v: i for i, v in enumerate(verts)}
    faces = {f for v in verts for f in v.link_faces}
    return BVHTree.FromPolygons([v.co for v in verts], [[index[v] for v in f.verts] for f in faces])


def analyse_shells(bm, specs):
    """(uncrossed, self_intersecting) for a world-space source bmesh.

    ``uncrossed``: separate shells (of several) that no cut crosses; they stay
    whole in the part on their side, which is the side of their centroid.
    ``self_intersecting``: two shells intersect (e.g. Suzanne's eyes and head):
    the booleans then start with the exact solver's self-intersection mode.
    """
    groups = meshlib.shells(bm)
    if len(groups) < 2:
        return 0, False
    uncrossed = 0
    for verts in groups:
        crossed = False
        for spec in specs:
            sides = set()
            for v in verts:
                sides.add(spec.side(v.co))
                if len(sides) == 2:
                    crossed = True
                    break
            if crossed:
                break
        uncrossed += not crossed
    boxes = []
    for verts in groups:
        xs = [v.co.x for v in verts]
        ys = [v.co.y for v in verts]
        zs = [v.co.z for v in verts]
        boxes.append((min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
    bvhs = {}
    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            a, b = boxes[i], boxes[j]
            if a[1] < b[0] or b[1] < a[0] or a[3] < b[2] or b[3] < a[2] or a[5] < b[4] or b[5] < a[4]:
                continue
            for k in (i, j):
                if k not in bvhs:
                    bvhs[k] = _bvh_of(groups[k])
            if bvhs[i].overlap(bvhs[j]):
                return uncrossed, True
    return uncrossed, False


# ---------------------------------------------------------------------------
# Connectors
# ---------------------------------------------------------------------------

def make_spec(obj, cut, scene, label, u_mm, v_mm, rotation_deg, kind, width_mm, height_mm, length_mm,
              clearance_mm, pin_side, spec=None):
    """ConnectorSpec (world space, BU) of one connector on ``cut``; lengths given in mm.

    ``spec``: the cut's PlaneCut/StrokeCut if already built (saves rebuilding a stroke cutter).
    """
    mm = units.mm_to_scene(1.0, scene)
    spec = spec if spec is not None else cut_spec(obj, cut, scene)
    return conn_apply.ConnectorSpec(
        label=label, matrix=spec.matrix(u_mm * mm, v_mm * mm, rotation_deg),
        kind=kind, width=width_mm * mm, height=height_mm * mm, length=length_mm * mm,
        clearance=clearance_mm * mm, gap=cut.gap_mm * mm, pin_positive=(pin_side == 'A'), cut_uid=cut.uid)


def default_clearance(settings):
    return settings.clearance_mm if settings is not None else 0.2


def connector_specs(obj, cuts, scene, settings, specs=None):
    """ConnectorSpec list (world space, BU) for the enabled connectors of ``cuts``."""
    specs = specs if specs is not None else cut_specs(obj, cuts, scene)
    out = []
    for cut, spec in zip(cuts, specs):
        for i, c in enumerate(cut.connectors):
            if not c.enabled:
                continue
            clearance = c.clearance_mm if c.clearance_mm >= 0.0 else default_clearance(settings)
            out.append(make_spec(obj, cut, scene, f"{cut.name} connector {i + 1}", c.u, c.v, c.rotation_deg,
                                 c.kind, c.width_mm, c.height_mm, c.length_mm, clearance, c.pin_side, spec))
    return out


# ---------------------------------------------------------------------------
# Result collection
# ---------------------------------------------------------------------------

def result_collection(obj):
    """Existing build collection of ``obj`` or None.

    The collection references its owner object (an ID reference, so renaming
    the source keeps it). A duplicated source copies the
    ``last_build_collection`` pointer, but the collection still names the
    original as owner, so the duplicate gets its own collection.
    """
    stack = stack_api.get_stack(obj)
    for coll in (stack.last_build_collection,
                 bpy.data.collections.get(naming.build_collection_name(obj.name))):
        if coll is not None and coll.get(naming.PROP_OWNER) in (obj, None):
            return coll
    return None


def _managed_parts(coll):
    """Built parts in a build collection (anything carrying the source property)."""
    return [o for o in coll.objects if o.get(naming.PROP_SOURCE) is not None]


def _remove_objects(objs):
    for o in objs:
        try:
            mesh = o.data
            bpy.data.objects.remove(o)
        except ReferenceError:  # already gone (file loaded while a modal build ran)
            continue
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def _find_layer_collection(layer_coll, coll):
    if layer_coll.collection == coll:
        return layer_coll
    for child in layer_coll.children:
        found = _find_layer_collection(child, coll)
        if found is not None:
            return found
    return None


def _prepare_collection(context, obj):
    """Build collection of ``obj`` (created if missing), linked and visible in the view layer."""
    scene = context.scene
    coll = result_collection(obj)
    name = naming.build_collection_name(obj.name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    elif coll.name != name and name not in bpy.data.collections:
        coll.name = name  # source was renamed
    coll[naming.PROP_OWNER] = obj
    if coll not in _all_children(scene.collection):
        scene.collection.children.link(coll)
    layer = _find_layer_collection(context.view_layer.layer_collection, coll)
    if layer is not None:
        layer.exclude = False
        layer.hide_viewport = False
    coll.hide_viewport = False
    stack_api.get_stack(obj).last_build_collection = coll
    return coll


def _remove_new_collection(obj):
    """Drop the empty build collection a cancelled first build created (if still there)."""
    try:
        coll = result_collection(obj)
        if coll is not None and not coll.objects and not coll.children:
            bpy.data.collections.remove(coll)
            stack_api.get_stack(obj).last_build_collection = None
    except ReferenceError:  # file loaded meanwhile
        pass


def _all_children(coll):
    out = []
    for child in coll.children:
        out.append(child)
        out.extend(_all_children(child))
    return out


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_steps(obj):
    """Generator building the enabled cuts of ``obj``'s stack.

    Yields after each progress step, returns (StopIteration value) a
    BuildResult; raises BuildError. Closing the generator early removes
    whatever it created and leaves the previous result untouched. Uses
    ``bpy.context`` (valid in each modal event) and keeps no stack
    PropertyGroups across yields.
    """
    context = bpy.context
    stack = stack_api.get_stack(obj)
    if stack is None:
        raise BuildError("Active object is not a mesh")
    cuts = [c for c in stack.cuts if c.enabled]
    if not cuts:
        raise BuildError("No enabled cuts in the stack")
    scene = context.scene
    settings = getattr(scene, naming.SCENE_SETTINGS, None)
    specs = cut_specs(obj, cuts, scene)
    conn_specs = connector_specs(obj, cuts, scene, settings, specs)
    barriers = {s.uid: s.barrier() for s in specs}
    quality = settings.boolean_quality if settings is not None else 'AUTO'
    cut_ids = ",".join(c.uid for c in cuts)
    max_step = units.mm_to_scene(FIT_STEP_MM, scene)
    del stack, cuts, settings

    warnings, infos, booleans = [], [], []
    prog = progress.Progress(2 * len(specs), f"{naming.ADDON_NAME} Build")
    prog.begin()
    bm = source_bmesh(obj, context.evaluated_depsgraph_get())
    pieces, pins, sockets, parts, names = [], None, None, [], []
    had_collection = True
    try:
        if not bm.faces:
            raise BuildError("Source mesh has no faces")
        source_bvh = BVHTree.FromBMesh(bm)  # keeps its own copy of the geometry
        uncrossed, self_intersect = analyse_shells(bm, specs)
        if uncrossed:
            infos.append(f"{uncrossed} separate shell(s) not crossed by any cut stay whole in the part "
                         "that contains them")
        if self_intersect:
            if unites_shells(quality, len(bm.faces)):
                # Accurate: unite the intersecting shells once, so every later boolean sees clean
                # input and is validated against the right volume (defect D14)
                prog.set_total(prog.total + 1)
                prog.step("uniting intersecting shells")
                yield
                united, why = boolean.unite_bm(bm)
                if united is not None:
                    bm.free()
                    bm, self_intersect = united, False
                    infos.append(f"Intersecting shells were united into one solid "
                                 f"(Booleans: {QUALITY_NAMES[quality]})")
                else:
                    warnings.append(f"Intersecting shells could not be united ({why}); they stay overlapping")
            else:
                infos.append(f"Intersecting shells stay overlapping in the parts (Booleans: "
                             f"{QUALITY_NAMES[quality]}); slicers unite them, Accurate unites them here")
        consumed, bm = bm, None
        pieces = yield from iter_cut_pieces(consumed, specs, warnings, quality, prog, self_intersect, booleans)
        if len(pieces) < 2:
            raise BuildError("The cuts do not intersect the object")
        pins, sockets, conn_warnings, overlapping = conn_apply.assign(
            [p.bm for p in pieces], conn_specs, source_bvh, barriers, max_step)
        warnings += conn_warnings
        operations = conn_apply.operations(pins, sockets)
        prog.set_total(prog.done + len(operations))

        had_collection = result_collection(obj) is not None
        coll = _prepare_collection(bpy.context, obj)
        old_parts = _managed_parts(coll)
        for piece in pieces:
            name = f"{obj.name}_{piece.sides}"
            names.append(name)
            mesh = bpy.data.meshes.new(name)
            piece.bm.to_mesh(mesh)
            part = bpy.data.objects.new(name, mesh)
            part[naming.PROP_SOURCE] = obj.name
            part[naming.PROP_SOURCE_OBJECT] = obj
            part[naming.PROP_CUT_IDS] = cut_ids
            coll.objects.link(part)
            parts.append(part)
        for index, operand, operation in operations:
            prog.step(f"connectors: {operation.lower()} on {names[index]}")
            yield
            res = conn_apply.apply_step(parts[index], operand, operation, quality,
                                        self_intersect or index in overlapping)
            booleans.append((f"connectors {operation.lower()} {names[index]}", res.solver, res.attempts))
            if res.message:
                warnings.append(res.message)
    except BaseException:
        # Failure or cancel: leave the previous result untouched, drop what this run created
        _remove_objects(parts)
        if not had_collection:
            _remove_new_collection(obj)
        raise
    finally:
        if bm is not None:
            bm.free()
        for p in pieces:
            p.bm.free()
        for table in (pins, sockets):
            for operand in (table or {}).values():
                operand.free()
        prog.end()

    # Success: replace the previous parts, then take over their names
    context = bpy.context
    _remove_objects(old_parts)
    for part, name in zip(parts, names):
        part.name = name
        part.data.name = part.name

    if obj.name in context.view_layer.objects:
        obj.hide_set(True)
        obj.select_set(False)
    for part in parts:
        if part.name in context.view_layer.objects:
            part.select_set(True)
    context.view_layer.objects.active = parts[0]
    for w in warnings:
        log.warning(w)
    for i in infos:
        log.info(i)
    summary = solver_summary(booleans, quality)
    if summary:
        infos.append(summary)
        log.info(summary)
    return BuildResult(coll.name, [p.name for p in parts], warnings, infos, booleans)


QUALITY_NAMES = {'AUTO': "Auto", 'ACCURATE': "Accurate", 'FAST': "Fast"}


def unites_shells(quality, faces):
    """True if the quality setting unites intersecting shells (Accurate, or Auto below the size limit)."""
    return quality == 'ACCURATE' or (quality == 'AUTO' and faces <= boolean.LARGE_FACES)


def solver_summary(booleans, quality):
    """'Booleans (Auto): 2x MANIFOLD, 2x EXACT_SELF; fallbacks: Stroke 1 side A -> EXACT_SELF' or ''."""
    if not booleans:
        return ""
    counts = {}
    for _label, used, _attempts in booleans:
        counts[used or "failed"] = counts.get(used or "failed", 0) + 1
    text = f"Booleans ({QUALITY_NAMES.get(quality, quality)}): " + ", ".join(f"{n}x {k}" for k, n in counts.items())
    fallbacks = [f"{label} -> {used}" for label, used, attempts in booleans if len(attempts) > 1]
    if fallbacks:
        text += "; fallbacks: " + ", ".join(fallbacks)
    return text


def run_steps(gen):
    """Run a step generator to the end; returns its result."""
    while True:
        try:
            next(gen)
        except StopIteration as stop:
            return stop.value


def build(context, obj):
    """Build the enabled cuts of ``obj``'s stack. Returns a BuildResult; raises BuildError."""
    return run_steps(build_steps(obj))


def clear_build(context, obj):
    """Remove the build result of ``obj`` and show the source again. Returns removed part count."""
    stack = stack_api.get_stack(obj)
    coll = result_collection(obj)
    removed = 0
    if coll is not None:
        old = _managed_parts(coll)
        removed = len(old)
        _remove_objects(old)
        if not coll.objects and not coll.children:
            bpy.data.collections.remove(coll)
    stack.last_build_collection = None
    if obj.name in context.view_layer.objects:
        obj.hide_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
    return removed
