# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# core/boolean.py
"""Boolean of a mesh object with a bmesh operand, verified, with solver fallback.

The operand becomes a temporary object that is never linked to a scene and is
removed before returning. A result counts only if it is manifold and changed
the volume in the expected direction; otherwise the next solver is tried and,
when all fail, the target keeps its mesh unchanged.
"""

from dataclasses import dataclass

import bmesh
import bpy

from . import compat, log, meshlib

OPERAND_NAME = "_SplitForge_Operand"
MODIFIER_NAME = "_SplitForge_Boolean"


@dataclass
class BooleanResult:
    ok: bool
    solver: str = ""
    message: str = ""


def _mesh_volume_manifold(mesh):
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        return meshlib.bm_volume(bm), meshlib.bm_is_manifold(bm)
    finally:
        bm.free()


def _evaluate(target, operand, operation, solver, self_intersect=False):
    """Mesh of ``target`` with one boolean modifier evaluated (modifier removed again)."""
    mod = target.modifiers.new(MODIFIER_NAME, 'BOOLEAN')
    try:
        mod.operation = operation
        mod.solver = solver
        mod.object = operand
        if solver == 'EXACT':
            mod.use_self = self_intersect
            mod.use_hole_tolerant = False
        depsgraph = bpy.context.evaluated_depsgraph_get()
        depsgraph.update()
        return bpy.data.meshes.new_from_object(target.evaluated_get(depsgraph), depsgraph=depsgraph)
    finally:
        target.modifiers.remove(mod)


def apply(target, operand_bm, operation, preference='AUTO', self_intersect=False):
    """Apply UNION/DIFFERENCE of ``operand_bm`` (target object space) to ``target``.

    ``target`` must be visible in the active view layer (otherwise it is not
    evaluated). ``self_intersect``: the operand's solids may intersect each
    other (exact solver option). Returns a BooleanResult.
    """
    if not operand_bm.faces:
        return BooleanResult(True, "", "empty operand")
    before, _ = _mesh_volume_manifold(target.data)
    tol = max(before * 1e-6, 1e-9)
    op_mesh = bpy.data.meshes.new(OPERAND_NAME)
    operand_bm.to_mesh(op_mesh)
    operand = bpy.data.objects.new(OPERAND_NAME, op_mesh)
    tried = []
    try:
        for solver in compat.boolean_solver_order(preference):
            new_mesh = _evaluate(target, operand, operation, solver, self_intersect)
            try:
                after, manifold = _mesh_volume_manifold(new_mesh)
            except Exception:
                bpy.data.meshes.remove(new_mesh)
                raise
            grew = after > before + tol
            shrank = after < before - tol
            if manifold and (grew if operation == 'UNION' else shrank):
                old = target.data
                name = old.name
                target.data = new_mesh
                if old.users == 0:
                    bpy.data.meshes.remove(old)
                new_mesh.name = name
                if tried:
                    log.info("boolean %s on %s: fallback=%s after %s", operation, target.name, solver, tried)
                return BooleanResult(True, solver)
            tried.append(f"{solver}(manifold={manifold}, volume {before:.6g}->{after:.6g})")
            bpy.data.meshes.remove(new_mesh)
    finally:
        bpy.data.objects.remove(operand)
        bpy.data.meshes.remove(op_mesh)
    msg = f"boolean {operation} on {target.name} failed: " + ", ".join(tried)
    log.warning(msg)
    return BooleanResult(False, "", msg)
