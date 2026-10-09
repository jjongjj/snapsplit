# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# core/boolean.py
"""Booleans with a verified result and a solver fallback chain.

``apply`` runs UNION/DIFFERENCE/INTERSECT of a bmesh operand on a mesh object
through a Boolean modifier that is evaluated and removed again; ``apply_bm``
does the same for a bmesh target (through a temporary object). The operand
becomes a temporary object that is never linked to a scene.

Attempts (``attempt_order``), each verified by ``check_result``:

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

# Relative volume tolerance of the checks (float noise of the solvers)
VOLUME_TOLERANCE = 1e-6


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


def attempt_order(preference='AUTO', self_intersect=False, voxel=True):
    """Attempt names in order for ``preference`` in {'AUTO', 'EXACT', 'FAST'}.

    ``self_intersect``: the inputs are known to intersect themselves, so plain
    EXACT is skipped.
    """
    fast = compat.float_solver()
    exact = [EXACT_SELF] if self_intersect else [EXACT, EXACT_SELF]
    manifold = [MANIFOLD] if MANIFOLD in compat.boolean_solvers() else []
    if preference == 'FAST':
        order = [fast] + exact + manifold
    else:
        order = exact + manifold + [fast]
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


def apply(target, operand_bm, operation, preference='AUTO', self_intersect=False, expect=None, voxel=True,
          order=None):
    """Apply UNION/DIFFERENCE/INTERSECT of ``operand_bm`` (target object space) to ``target``.

    ``target`` must be visible in the active view layer (otherwise it is not
    evaluated). ``self_intersect``: the inputs are known to intersect
    themselves (plain EXACT is skipped). ``expect``: optional (lo, hi) range of
    the result volume. ``order``: explicit attempt list (default
    ``attempt_order(preference, self_intersect, voxel)``). Returns a
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
    try:
        for attempt in (order if order is not None else attempt_order(preference, self_intersect, voxel)):
            t0 = time.perf_counter()
            new_mesh = _evaluate(target, operand, operation, attempt)
            try:
                after, manifold, faces = mesh_volume_manifold(new_mesh)
            except Exception:
                bpy.data.meshes.remove(new_mesh)
                raise
            reason = check_result(operation, before, operand_volume, after, manifold, faces, expect)
            attempts.append((attempt, reason or "ok", round(time.perf_counter() - t0, 3)))
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


def apply_bm(target_bm, operand_bm, operation, preference='AUTO', self_intersect=False, expect=None,
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
        result = apply(obj, operand_bm, operation, preference, self_intersect, expect, order=order)
        out = None
        if result.ok:
            out = bmesh.new()
            out.from_mesh(obj.data)
        return result, out
    finally:
        # apply() replaced and removed ``mesh`` on success: only the object's mesh is left
        final = obj.data
        bpy.data.objects.remove(obj)
        if final.users == 0:
            bpy.data.meshes.remove(final)
