# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# core/units.py
"""Exact millimeter <-> scene unit conversion.

Convention (3D printing): one Blender unit (BU) stands for one ``length_unit``
multiplied by ``scale_length``. A "millimeter scene" (Metric, Millimeters,
Unit Scale 1.0) therefore has 1 BU == 1 mm, which is also what STL slicers
assume; Metric/Meters with Unit Scale 0.001 is a millimeter scene as well.

All functions accept a Scene, its UnitSettings or ``None`` (active scene).
"""

import bpy

# Size of one length unit in millimeters
LENGTH_UNIT_MM = {
    'KILOMETERS': 1_000_000.0,
    'METERS': 1000.0,
    'CENTIMETERS': 10.0,
    'MILLIMETERS': 1.0,
    'MICROMETERS': 0.001,
    'MILES': 1_609_344.0,
    'FEET': 304.8,
    'INCHES': 25.4,
    'THOU': 0.0254,
}

# Unit used for 'ADAPTIVE' (and system 'NONE'): the base unit of the system
_BASE_UNIT = {'METRIC': 'METERS', 'IMPERIAL': 'FEET', 'NONE': 'METERS'}


def _unit_settings(scene_or_units=None):
    if scene_or_units is None:
        scene_or_units = bpy.context.scene
    return getattr(scene_or_units, "unit_settings", scene_or_units)


def length_unit_mm(system, length_unit):
    """Millimeters per ``length_unit`` (pure function, no bpy access)."""
    if system == 'NONE' or length_unit not in LENGTH_UNIT_MM:
        length_unit = _BASE_UNIT.get(system, 'METERS')
    return LENGTH_UNIT_MM[length_unit]


def exact_scale(scale_length):
    """``scale_length`` as the decimal the user typed.

    Blender stores it as a 32-bit float (0.001 reads back as 0.0010000000475);
    rounding to 7 significant digits recovers the typed value.
    """
    return float(f"{float(scale_length):.7g}")


def bu_to_mm_factor(scene_or_units=None):
    """Millimeters represented by one Blender unit in the given scene."""
    us = _unit_settings(scene_or_units)
    return length_unit_mm(us.system, us.length_unit) * exact_scale(us.scale_length)


def mm_to_scene(mm, scene_or_units=None):
    """Length in millimeters -> scene units (BU)."""
    return float(mm) / bu_to_mm_factor(scene_or_units)


def scene_to_mm(value, scene_or_units=None):
    """Length in scene units (BU) -> millimeters."""
    return float(value) * bu_to_mm_factor(scene_or_units)


def is_mm_scene(scene_or_units=None, tol=1e-9):
    """True when one BU is exactly one millimeter."""
    return abs(bu_to_mm_factor(scene_or_units) - 1.0) <= tol
