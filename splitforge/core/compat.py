# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# core/compat.py
"""Blender version differences in one place (4.2 LTS .. 5.x)."""

import bpy


def boolean_solvers():
    """Boolean modifier solver identifiers available in this Blender."""
    prop = bpy.types.BooleanModifier.bl_rna.properties['solver']
    return [item.identifier for item in prop.enum_items]


def float_solver():
    """Name of the fast floating point solver ('FAST' until 4.5, 'FLOAT' in 5.x)."""
    solvers = boolean_solvers()
    return 'FLOAT' if 'FLOAT' in solvers else 'FAST'


def boolean_solver_order(preference='AUTO'):
    """Solvers to try, in order, for ``preference`` in {'AUTO', 'EXACT', 'FAST'}.

    AUTO/EXACT try EXACT first, then MANIFOLD (Blender 4.5+), then the float
    solver. FAST starts with the float solver.
    """
    fast = float_solver()
    order = [fast, 'EXACT'] if preference == 'FAST' else ['EXACT', fast]
    if 'MANIFOLD' in boolean_solvers():
        order.insert(1, 'MANIFOLD')
    return order


def _op_available(module, name):
    try:
        getattr(getattr(bpy.ops, module), name).get_rna_type()
        return True
    except (AttributeError, KeyError):
        return False


def export_formats():
    """Export formats usable in this Blender: subset of ('STL', 'OBJ', 'FBX')."""
    out = []
    if _op_available("wm", "stl_export"):
        out.append('STL')
    if _op_available("wm", "obj_export"):
        out.append('OBJ')
    if _op_available("export_scene", "fbx"):
        out.append('FBX')
    return out


def export_selected(fmt, filepath, global_scale):
    """Export the selected objects of the current context to ``filepath``.

    Modifiers are applied, Z is up and -Y forward (Blender's own axes, what
    slicers expect), materials are not written.
    """
    if fmt == 'STL':
        return bpy.ops.wm.stl_export(
            filepath=filepath, export_selected_objects=True, global_scale=global_scale,
            use_scene_unit=False, ascii_format=False, apply_modifiers=True,
            forward_axis='Y', up_axis='Z')
    if fmt == 'OBJ':
        return bpy.ops.wm.obj_export(
            filepath=filepath, export_selected_objects=True, global_scale=global_scale,
            apply_modifiers=True, export_materials=False, export_uv=False,
            forward_axis='Y', up_axis='Z')
    if fmt == 'FBX':
        # FBX stores centimeters (UnitScaleFactor 1) and the exporter multiplies by 100
        # without unit scaling: global_scale / 1000 makes 1 mm come out as 0.1 cm.
        return bpy.ops.export_scene.fbx(
            filepath=filepath, use_selection=True, global_scale=global_scale / 1000.0,
            apply_unit_scale=False, apply_scale_options='FBX_SCALE_NONE', object_types={'MESH'},
            use_mesh_modifiers=True, axis_forward='Y', axis_up='Z')
    raise ValueError(f"unknown export format {fmt!r}")


def import_stl(filepath):
    """Import an STL file (used by tests and round-trip checks)."""
    return bpy.ops.wm.stl_import(filepath=filepath, forward_axis='Y', up_axis='Z')
