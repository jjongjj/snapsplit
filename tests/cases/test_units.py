# SPDX-License-Identifier: GPL-3.0-or-later
"""P1-1: core/units.py converts mm <-> scene units for every length unit and scale.

Convention: one Blender unit is one ``length_unit`` times ``scale_length``.
The legacy helpers in utils.py delegate to core/units.py.
"""

import bpy

import lib

# (system, length_unit, scale_length) -> scene units per millimeter
CASES = [
    (('METRIC', 'MILLIMETERS', 1.0), 1.0),
    (('METRIC', 'METERS', 1.0), 0.001),
    (('METRIC', 'CENTIMETERS', 1.0), 0.1),
    (('METRIC', 'METERS', 0.001), 1.0),
    (('IMPERIAL', 'INCHES', 1.0), 1.0 / 25.4),
    (('METRIC', 'ADAPTIVE', 1.0), 0.001),
    (('NONE', 'ADAPTIVE', 1.0), 0.001),
]


def run(ctx):
    units = ctx.module("core.units")
    utils = ctx.module("utils")
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
        # Legacy helpers use the same conversion
        lib.assert_close(utils.unit_mm(), per_mm, abs_=1e-9, msg=label + " utils.unit_mm")

    lib.set_scene_mm()
    assert utils.unit_mm() == 1.0, utils.unit_mm()
    assert utils.mm_to_scene(2.5) == 2.5, utils.mm_to_scene(2.5)
    # Pure function, no bpy access
    assert units.length_unit_mm('IMPERIAL', 'FEET') == 304.8
