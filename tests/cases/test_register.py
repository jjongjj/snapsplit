# SPDX-License-Identifier: GPL-3.0-or-later
"""Register -> unregister -> register again; key types exist only while enabled."""

import bpy

OPERATORS = ("SNAPSPLIT_OT_planar_split", "SNAPSPLIT_OT_freehand_cut")


def _assert_registered(ctx):
    assert ctx.addon_module in bpy.context.preferences.addons
    for name in OPERATORS:
        assert hasattr(bpy.types, name), f"{name} not registered"
    assert hasattr(bpy.context.scene, "snapsplit"), "scene.snapsplit missing"


def run(ctx):
    _assert_registered(ctx)

    bpy.ops.preferences.addon_disable(module=ctx.addon_module)
    assert ctx.addon_module not in bpy.context.preferences.addons
    for name in OPERATORS:
        assert not hasattr(bpy.types, name), f"{name} still registered after disable"
    assert not hasattr(bpy.context.scene, "snapsplit"), "scene.snapsplit left after disable"

    bpy.ops.preferences.addon_enable(module=ctx.addon_module)
    _assert_registered(ctx)
