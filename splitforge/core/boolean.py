# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# core/boolean.py
"""Booleans with a verified result and a solver fallback chain.

``apply`` runs UNION/DIFFERENCE/INTERSECT of a bmesh operand on a mesh object
through a Boolean modifier that is evaluated and removed again; ``apply_bm``
does the same for a bmesh target (through a temporary object). The operand
becomes a temporary object that is never linked to a scene.

Attempts (``attempt_order``, order set by the quality setting AUTO / ACCURATE /
FAST, see there), each verified by ``check_result``; the accurate chain is:

1. EXACT
2. EXACT with self-intersection handling. Needed when the target (or the
   operand) has intersecting shells: a filled Suzanne's eyes cut into the head
   shell, and EXACT without it returns an empty or wrong mesh (that is why the
   connector UNION on the large Suzanne "lost volume" and fell back before).
3. MANIFOLD (Blender 4.5+), then the float solver (FAST / FLOAT in 5.x)
4. Voxel remesh of the target, then EXACT with self-intersection (last resort;
   changes the surface, so it is reported as a warning)

A result counts only if it has faces, is manifold and its volume lies in the
range the operation allows (``check_result``; callers may narrow it with
``expect``). When every attempt fails the target keeps its mesh unchanged and
the result carries one line per attempt.
"""

import time
from dataclasses import dataclass, field

import bmesh
import bpy

from . import compat, log, meshlib

OPERAND_NAME = "_SplitForge_Operand"
TARGET_NAME = "_SplitForge_Target"
MODIFIER_NAME = "_SplitForge_Boolean"
REMESH_NAME = "_SplitForge_Remesh"

EXACT = 'EXACT'
EXACT_SELF = 'EXACT_SELF'
MANIFOLD = 'MANIFOLD'
VOXEL = 'VOXEL'

# Voxel size of the last-resort remesh: bounding box diagonal / VOXEL_DIVISIONS (0.35 mm on a
# 40 mm cube; finer remeshes made the exact boolean after them take minutes)
VOXEL_DIVISIONS = 200

# Auto quality: targets with more faces than this try MANIFOLD first
LARGE_FACES = 200_000

# Relative volume tolerance of the checks (float noise of the solvers)
VOLUME_TOLERANCE = 1e-6

# unite_bm: the united shells and the input must enclose the same volume within this fraction
# (winding-number ray integral on the same rays over the same triangles: input and result differ by
# < 0.01 % on Suzanne; a 1 % loss is rejected)
UNION_TOLERANCE = 0.002


@dataclass
class BooleanResult:
    ok: bool
    solver: str = ""
    message: str = ""
    attempts: list = field(default_factory=list)   # [(attempt, "ok" or reason, seconds)]

    @property
    def fallback(self):
        """True if an attempt before the successful one failed."""
        return self.ok and len(self.attempts) > 1


def attempt_order(quality='AUTO', self_intersect=False, voxel=True, faces=0):
    """Attempt names in order for a quality setting (Scene setting ``boolean_quality``).

    - ACCURATE: EXACT, EXACT_SELF, MANIFOLD, float, VOXEL. The exact solver with
      self-intersection unites intersecting shells (a filled Suzanne's eyes and head).
    - FAST: MANIFOLD first, then the accurate chain. MANIFOLD is much faster on
      large meshes (0.5 s vs 29 s on 514k faces) but leaves intersecting shells
      overlapping (each shell is cut on its own; slicers unite them).
    - AUTO: FAST for targets with more than LARGE_FACES faces, ACCURATE below.

    ``self_intersect``: the inputs are known to intersect themselves, so plain
    EXACT is skipped. Every attempt is validated (check_result) whatever the
    order. Without MANIFOLD (Blender < 4.5) FAST equals ACCURATE.
    """
    quality = {'EXACT': 'ACCURATE'}.get(quality, quality)
    if quality == 'AUTO':
        quality = 'FAST' if faces > LARGE_FACES else 'ACCURATE'
    exact = [EXACT_SELF] if self_intersect else [EXACT, EXACT_SELF]
    manifold = [MANIFOLD] if MANIFOLD in compat.boolean_solvers() else []
    if quality == 'FAST':
        order = manifold + exact + [compat.float_solver()]
    else:
        order = exact + manifold + [compat.float_solver()]
    if voxel:
        order.append(VOXEL)
    return order


def mesh_volume_manifold(mesh):
    """(volume, manifold, face count) of a mesh data-block."""
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        return meshlib.bm_volume(bm), meshlib.bm_is_manifold(bm), len(bm.faces)
    finally:
        bm.free()


def check_result(operation, before, operand_volume, after, manifold, faces, expect=None):
    """Reason the result is rejected, or "" when it is plausible.

    ``before``/``after``: target volume, ``operand_volume``: operand volume (for
    intersecting operand solids an upper bound). ``expect``: optional (lo, hi)
    the caller knows the result volume must lie in.
    """
    tol = max(before, operand_volume) * VOLUME_TOLERANCE + 1e-9
    if faces == 0:
        return "empty result"
    if not manifold:
        return "not manifold"
    if operation == 'UNION':
        if not after > before + tol:
            return f"volume did not grow ({before:.6g} -> {after:.6g})"
        if after > before + operand_volume + tol:
            return f"volume grew more than the operand has ({before:.6g} -> {after:.6g})"
    elif operation == 'DIFFERENCE':
        if not after < before - tol:
            return f"volume did not shrink ({before:.6g} -> {after:.6g})"
        if after < before - operand_volume - tol:
            return f"lost more volume than the operand has ({before:.6g} -> {after:.6g})"
    elif operation == 'INTERSECT':
        if after > min(before, operand_volume) + tol:
            return f"intersection larger than an input ({before:.6g} -> {after:.6g})"
    if expect is not None:
        lo, hi = expect
        if not lo - tol <= after <= hi + tol:
            return f"volume {after:.6g} outside the expected {lo:.6g}..{hi:.6g}"
    return ""


def _voxel_size(target):
    xs, ys, zs = zip(*(tuple(c) for c in target.bound_box))
    diag = ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2 + (max(zs) - min(zs)) ** 2) ** 0.5
    return max(diag / VOXEL_DIVISIONS, 1e-5)


def _evaluate(target, operand, operation, attempt):
    """Mesh of ``target`` with the attempt's modifiers evaluated (modifiers removed again)."""
    mods = []
    try:
        if attempt == VOXEL:
            remesh = target.modifiers.new(REMESH_NAME, 'REMESH')
            mods.append(remesh)
            remesh.mode = 'VOXEL'
            remesh.voxel_size = _voxel_size(target)
        mod = target.modifiers.new(MODIFIER_NAME, 'BOOLEAN')
        mods.append(mod)
        mod.operation = operation
        mod.object = operand
        if attempt in (EXACT, EXACT_SELF, VOXEL):
            mod.solver = 'EXACT'
            mod.use_self = attempt != EXACT
            mod.use_hole_tolerant = False
        else:
            mod.solver = attempt
        depsgraph = bpy.context.evaluated_depsgraph_get()
        depsgraph.update()
        return bpy.data.meshes.new_from_object(target.evaluated_get(depsgraph), depsgraph=depsgraph)
    finally:
        for m in reversed(mods):
            target.modifiers.remove(m)


def _united(target):
    """New mesh: ``target`` with intersecting shells united (EXACT, self-intersection).

    The exact solver only resolves self-intersections together with an operand,
    so a tiny cube far outside the target is the operand and its shell is
    deleted again from the result.
    """
    xs = [c[0] for c in target.bound_box]
    size = max(max(xs) - min(xs), 1e-3)
    far = max(xs) + 10.0 * size
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size * 0.01)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(far, 0.0, 0.0))
    op_mesh = bpy.data.meshes.new(OPERAND_NAME)
    bm.to_mesh(op_mesh)
    bm.free()
    operand = bpy.data.objects.new(OPERAND_NAME, op_mesh)
    try:
        mesh = _evaluate(target, operand, 'UNION', EXACT_SELF)
    finally:
        bpy.data.objects.remove(operand)
        bpy.data.meshes.remove(op_mesh)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.x > far - size], context='VERTS')
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def united_volume(target):
    """Volume of ``target`` with intersecting shells united (counts overlaps once), or None."""
    mesh = _united(target)
    try:
        volume, manifold, faces = mesh_volume_manifold(mesh)
    finally:
        bpy.data.meshes.remove(mesh)
    return volume if manifold and faces else None


def unite_bm(bm, name=TARGET_NAME):
    """Copy of ``bm`` with intersecting shells united: (bmesh, "") or (None, reason). Caller frees.

    The input is triangulated first: a non-planar n-gon has no well-defined volume (each
    triangulation encloses a different one), so the solver and the volume checks must see the
    same triangles. The result must be manifold, not larger than the input and enclose the same
    volume as the input's shells together (winding-number ray integral, defect D16).
    """
    bm = bm.copy()
    bm.normal_update()   # n-gons are triangulated in their plane: normals must be current
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    try:
        before = meshlib.bm_volume(bm)
        united = _united(obj)
        out = bmesh.new()
        try:
            after, manifold, faces = mesh_volume_manifold(united)
            if not faces or not manifold or after > before * (1.0 + VOLUME_TOLERANCE) + 1e-9:
                out.free()
                return None, f"uniting the shells failed (manifold={manifold}, volume {before:.6g} -> {after:.6g})"
            out.from_mesh(united)
            # Lower bound (defect D16): the result must enclose what the shells enclose together. The
            # winding-number ray integral of the input counts each overlap once, independent of the solver;
            # both are sampled on the same rays, so a lost shell or a shrunk result shows up.
            # Rays along all three axes: a thin shell (thinner than the ray spacing) lost by the union
            # slips between the rays of one family but is crossed by the others.
            bounds = meshlib.bm_box(bm)
            for expected, got in zip(meshlib.winding_volumes(bm, bounds), meshlib.winding_volumes(out, bounds)):
                if abs(got - expected) > UNION_TOLERANCE * expected:
                    out.free()
                    return None, (f"uniting the shells changed the enclosed volume ({expected:.6g} -> {got:.6g}, "
                                  f"exact {before:.6g} -> {after:.6g})")
            return out, ""
        finally:
            bpy.data.meshes.remove(united)
    finally:
        _drop(obj)
        bpy.data.meshes.remove(mesh)
        bm.free()


def _drop(obj):
    """Remove a temporary object linked to the scene collection and resync the view layer
    (otherwise ``view_layer.objects`` yields None for it until the next update)."""
    collection = bpy.context.scene.collection
    if obj.name in collection.objects:
        collection.objects.unlink(obj)
    bpy.data.objects.remove(obj)
    bpy.context.view_layer.update()


VOLUME_REASONS = ("did not grow", "did not shrink", "more than the operand", "more volume than", "larger than")


def apply(target, operand_bm, operation, quality='AUTO', self_intersect=False, expect=None, voxel=True,
          order=None):
    """Apply UNION/DIFFERENCE/INTERSECT of ``operand_bm`` (target object space) to ``target``.

    ``target`` must be visible in the active view layer (otherwise it is not
    evaluated). ``self_intersect``: the inputs are known to intersect
    themselves (plain EXACT is skipped). ``expect``: optional (lo, hi) range of
    the result volume. ``order``: explicit attempt list (default
    ``attempt_order(quality, self_intersect, voxel, target face count)``). Returns a
    BooleanResult; on failure the target mesh is unchanged.
    """
    if not operand_bm.faces:
        return BooleanResult(True, "", "empty operand")
    before, _manifold, _faces = mesh_volume_manifold(target.data)
    operand_volume = meshlib.bm_volume(operand_bm)
    op_mesh = bpy.data.meshes.new(OPERAND_NAME)
    operand_bm.to_mesh(op_mesh)
    operand = bpy.data.objects.new(OPERAND_NAME, op_mesh)
    attempts = []
    merged = None
    try:
        if order is None:
            order = attempt_order(quality, self_intersect, voxel, len(target.data.polygons))
        for attempt in order:
            t0 = time.perf_counter()
            new_mesh = _evaluate(target, operand, operation, attempt)
            try:
                after, manifold, faces = mesh_volume_manifold(new_mesh)
            except Exception:
                bpy.data.meshes.remove(new_mesh)
                raise
            reason = check_result(operation, before, operand_volume, after, manifold, faces, expect)
            if (reason and self_intersect and attempt in (EXACT_SELF, VOXEL)
                    and any(r in reason for r in VOLUME_REASONS)):
                # These attempts unite intersecting shells: compare with the united target (the
                # plain volume counts the overlap twice, defect D14). Computed once per call.
                if merged is None:
                    merged = united_volume(target) or before
                reason = check_result(operation, merged, operand_volume, after, manifold, faces, expect)
            attempts.append((attempt, reason or "ok", round(time.perf_counter() - t0, 3)))
            log.debug("boolean %s on %s: %s -> %s (%.3f s)", operation, target.name, attempt, reason or "ok",
                      attempts[-1][2])
            if reason:
                bpy.data.meshes.remove(new_mesh)
                continue
            old = target.data
            name = old.name
            target.data = new_mesh
            if old.users == 0:
                bpy.data.meshes.remove(old)
            new_mesh.name = name
            result = BooleanResult(True, attempt, "", attempts)
            if result.fallback:
                log.info("boolean %s on %s: fallback=%s after %s", operation, target.name, attempt,
                         "; ".join(f"{a}: {r}" for a, r, _s in attempts[:-1]))
            if attempt == VOXEL:
                result.message = (f"{target.name}: boolean {operation} only succeeded after a voxel remesh "
                                  "(surface detail is approximated)")
            return result
    finally:
        bpy.data.objects.remove(operand)
        bpy.data.meshes.remove(op_mesh)
    msg = (f"boolean {operation} on {target.name} failed with every solver: "
           + "; ".join(f"{a}: {r}" for a, r, _s in attempts))
    log.warning(msg)
    return BooleanResult(False, "", msg, attempts)


def apply_bm(target_bm, operand_bm, operation, quality='AUTO', self_intersect=False, expect=None,
             name=TARGET_NAME, order=None):
    """``apply`` on a bmesh target (same space as the operand).

    Returns ``(BooleanResult, bmesh or None)``; the caller frees the returned
    bmesh. A temporary object is linked to the scene for the evaluation and
    removed again whatever happens; ``target_bm`` is not changed.
    """
    mesh = bpy.data.meshes.new(name)
    target_bm.to_mesh(mesh)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    try:
        result = apply(obj, operand_bm, operation, quality, self_intersect, expect, order=order)
        out = None
        if result.ok:
            out = bmesh.new()
            out.from_mesh(obj.data)
        return result, out
    finally:
        # apply() replaced and removed ``mesh`` on success: only the object's mesh is left
        final = obj.data
        _drop(obj)
        if final.users == 0:
            bpy.data.meshes.remove(final)
