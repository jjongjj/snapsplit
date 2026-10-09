# SPDX-License-Identifier: GPL-3.0-or-later
"""P1-1: core/units.py follows Blender's display: 1 BU = Unit Scale meters.

A millimeter value in the add-on equals what Blender shows in millimeters, whatever
the display length unit.
"""

import bpy

import lib

# (system, length_unit, scale_length) -> scene units per millimeter
CASES = [
    (('METRIC', 'MILLIMETERS', 0.001), 1.0),        # standard 3D-print setup
    (('METRIC', 'METERS', 0.001), 1.0),
    (('METRIC', 'METERS', 1.0), 0.001),             # Blender default: 1 BU = 1 m
    (('METRIC', 'MILLIMETERS', 1.0), 0.001),        # Blender shows 40 BU as 40000 mm
    (('METRIC', 'CENTIMETERS', 0.01), 0.1),         # 1 BU = 1 cm
    (('IMPERIAL', 'INCHES', 0.0254), 1.0 / 25.4),   # 1 BU = 1 inch
    (('METRIC', 'ADAPTIVE', 1.0), 0.001),
    (('NONE', 'ADAPTIVE', 1.0), 0.001),
]


def run(ctx):
    units = ctx.module("core.units")
    us = bpy.context.scene.unit_settings
    for (system, length_unit, scale), per_mm in CASES:
        us.system = system
        if system != 'NONE':
            us.length_unit = length_unit
        us.scale_length = scale
        label = f"{system}/{length_unit}/{scale}"
        lib.assert_close(units.mm_to_scene(1.0), per_mm, abs_=1e-9, msg=label)
        lib.assert_close(units.scene_to_mm(per_mm), 1.0, abs_=1e-9, msg=label + " inverse")
        lib.assert_close(units.mm_to_scene(2.5, bpy.context.scene), 2.5 * per_mm, abs_=1e-9, msg=label)
        assert units.is_mm_scene() == (abs(per_mm - 1.0) < 1e-12), label
        # Same number Blender itself uses for a typed "25 mm" (meters / Unit Scale = BU)
        typed = bpy.utils.units.to_value('METRIC', 'LENGTH', "25 mm") / units.exact_scale(us.scale_length)
        lib.assert_close(units.mm_to_scene(25.0), typed, rel=1e-6, msg=label + " vs Blender's own conversion")

    lib.set_scene_mm()
    assert units.mm_to_scene(2.5) == 2.5, units.mm_to_scene(2.5)
