# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# core/compat.py
"""Exporter/importer calls in one place (SplitForge supports Blender 5.2; the 4.x solver-name
shims were removed with that decision)."""

import bpy


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

    Coordinates are written unchanged: forward 'Y' + up 'Z' is the identity
    mapping for all three exporters (file X/Y/Z = Blender world X/Y/Z, Z up,
    what slicers expect; tests/cases/test_export.py checks the raw STL/OBJ
    values). ``global_scale`` multiplies the coordinates (STL/OBJ are unitless,
    so passing the mm-per-unit factor writes millimeters); FBX is written in
    its own centimeter unit with the same physical size. Modifiers are
    applied, materials are not written.
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
        # (axis_forward 'Y' / axis_up 'Z' keep Blender's axes, like forward_axis/up_axis above.)
        return bpy.ops.export_scene.fbx(
            filepath=filepath, use_selection=True, global_scale=global_scale / 1000.0,
            apply_unit_scale=False, apply_scale_options='FBX_SCALE_NONE', object_types={'MESH'},
            use_mesh_modifiers=True, axis_forward='Y', axis_up='Z')
    raise ValueError(f"unknown export format {fmt!r}")


def import_stl(filepath):
    """Import an STL file (used by tests and round-trip checks)."""
    return bpy.ops.wm.stl_import(filepath=filepath, forward_axis='Y', up_axis='Z')
