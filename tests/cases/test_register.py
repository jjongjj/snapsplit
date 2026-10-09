# SPDX-License-Identifier: GPL-3.0-or-later
"""Register -> unregister -> register again; key types exist only while enabled.

Covers the legacy operators/settings and the new SplitForge types (operators,
PropertyGroups and the Object/Scene properties named in core/naming.py).
"""

import bpy

LEGACY = ("SNAPSPLIT_OT_planar_split", "SNAPSPLIT_OT_freehand_cut", "SNAP_PT_panel")
NEW = ("SPLITFORGE_OT_stack_add_plane", "SPLITFORGE_OT_stack_remove", "SPLITFORGE_OT_stack_move",
       "SPLITFORGE_OT_stack_duplicate", "SPLITFORGE_OT_stack_clear", "SPLITFORGE_OT_cut_adjust_plane",
       "SPLITFORGE_OT_build", "SPLITFORGE_OT_clear_build", "SPLITFORGE_OT_easy_cut",
       "SPLITFORGE_OT_validate", "SPLITFORGE_OT_connector_add_auto", "SPLITFORGE_OT_connector_add",
       "SPLITFORGE_OT_connector_remove", "SPLITFORGE_OT_export_parts")


def _props(ctx):
    naming = ctx.module("core.naming")
    return ((bpy.types.Scene, "snapsplit"), (bpy.types.Scene, naming.SCENE_SETTINGS),
            (bpy.types.Object, naming.OBJECT_STACK))


def _assert_registered(ctx, props):
    assert ctx.addon_module in bpy.context.preferences.addons
    for name in LEGACY + NEW:
        assert hasattr(bpy.types, name), f"{name} not registered"
    for owner, name in props:
        assert hasattr(owner, name), f"{owner.__name__}.{name} missing"
    naming = ctx.module("core.naming")
    stack = bpy.types.Object.bl_rna.properties[naming.OBJECT_STACK].fixed_type
    assert stack.identifier == "SPLITFORGE_PG_CutStack", stack.identifier
    cut = stack.properties["cuts"].fixed_type
    assert cut.identifier == "SPLITFORGE_PG_Cut", cut.identifier
    assert cut.properties["connectors"].fixed_type.identifier == "SPLITFORGE_PG_Connector"
    settings = bpy.types.Scene.bl_rna.properties[naming.SCENE_SETTINGS].fixed_type
    assert settings.identifier == "SPLITFORGE_PG_Settings", settings.identifier


def run(ctx):
    props = _props(ctx)
    _assert_registered(ctx, props)
    for _ in range(3):
        bpy.ops.preferences.addon_disable(module=ctx.addon_module)
        assert ctx.addon_module not in bpy.context.preferences.addons
        for name in LEGACY + NEW:
            assert not hasattr(bpy.types, name), f"{name} still registered after disable"
        for owner, name in props:
            assert not hasattr(owner, name), f"{owner.__name__}.{name} left after disable"
        bpy.ops.preferences.addon_enable(module=ctx.addon_module)
        _assert_registered(ctx, props)
