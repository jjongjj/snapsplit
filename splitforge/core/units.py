# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# core/units.py
"""Exact millimeter <-> scene unit conversion, following Blender's own display.

Blender shows a length of ``x`` Blender units (BU) as ``x * scale_length``
meters, whatever ``length_unit`` is used for display. The add-on uses the same
rule, so a millimeter value in the add-on always equals what Blender shows in
millimeters:

- Millimeters + Unit Scale 0.001 (the usual 3D-print setup): 1 BU = 1 mm.
- Meters + Unit Scale 1.0: 1 BU = 1000 mm.
- Millimeters + Unit Scale 1.0: also 1 BU = 1000 mm (Blender shows a 40 BU
  cube as 40000 mm).

All functions accept a Scene, its UnitSettings or ``None`` (active scene).
"""

import bpy


def _unit_settings(scene_or_units=None):
    if scene_or_units is None:
        scene_or_units = bpy.context.scene
    return getattr(scene_or_units, "unit_settings", scene_or_units)


def exact_scale(scale_length):
    """``scale_length`` as the decimal the user typed.

    Blender stores it as a 32-bit float (0.001 reads back as 0.0010000000475);
    rounding to 7 significant digits recovers the typed value.
    """
    return float(f"{float(scale_length):.7g}")


def bu_to_mm_factor(scene_or_units=None):
    """Millimeters represented by one Blender unit (1000 x Unit Scale)."""
    return 1000.0 * exact_scale(_unit_settings(scene_or_units).scale_length)


def mm_to_scene(mm, scene_or_units=None):
    """Length in millimeters -> scene units (BU)."""
    return float(mm) / bu_to_mm_factor(scene_or_units)


def scene_to_mm(value, scene_or_units=None):
    """Length in scene units (BU) -> millimeters."""
    return float(value) * bu_to_mm_factor(scene_or_units)


def is_mm_scene(scene_or_units=None, tol=1e-9):
    """True when one BU is exactly one millimeter (Unit Scale 0.001)."""
    return abs(bu_to_mm_factor(scene_or_units) - 1.0) <= tol
