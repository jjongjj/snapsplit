# SPDX-License-Identifier: GPL-3.0-or-later
"""Register -> unregister -> register again; key types exist only while enabled.

Covers the SplitForge types (operators, panels, PropertyGroups and the Object/Scene
properties named in core/naming.py), and that nothing of the retired legacy SnapSplit
UI (snapsplit.* operators, SNAP_* types, Scene.snapsplit) is registered any more.
"""

import bpy

LEGACY = ("SNAPSPLIT_OT_planar_split", "SNAPSPLIT_OT_freehand_cut", "SNAPSPLIT_OT_place_connectors_click",
          "SNAPSPLIT_OT_add_connectors", "SNAPSPLIT_OT_align_faces", "SNAP_PT_panel")
NEW = ("SPLITFORGE_OT_stack_add_plane", "SPLITFORGE_OT_stack_remove", "SPLITFORGE_OT_stack_move",
       "SPLITFORGE_OT_stack_duplicate", "SPLITFORGE_OT_stack_clear", "SPLITFORGE_OT_cut_adjust_plane",
       "SPLITFORGE_OT_build", "SPLITFORGE_OT_clear_build", "SPLITFORGE_OT_easy_cut",
       "SPLITFORGE_OT_validate", "SPLITFORGE_OT_connector_add_auto", "SPLITFORGE_OT_connector_add",
       "SPLITFORGE_OT_connector_remove", "SPLITFORGE_OT_connector_add_click",
       "SPLITFORGE_OT_connector_custom_size", "SPLITFORGE_OT_export_parts", "SPLITFORGE_OT_stack_add_stroke",
       "SPLITFORGE_OT_stack_add_polyline", "SPLITFORGE_OT_stack_add_polygon", "SPLITFORGE_OT_fix_transforms",
       "SPLITFORGE_OT_fix_units", "SPLITFORGE_OT_fix_normals", "SPLITFORGE_OT_fix_merge", "SPLITFORGE_OT_fix_holes",
       "SPLITFORGE_PT_main", "SPLITFORGE_PT_connectors", "SPLITFORGE_PT_build", "SPLITFORGE_PT_settings",
       "SPLITFORGE_UL_cuts", "SPLITFORGE_UL_connectors")


def _props(ctx):
    naming = ctx.module("core.naming")
    return ((bpy.types.Scene, naming.SCENE_SETTINGS),
            (bpy.types.Object, naming.OBJECT_STACK))


def _assert_registered(ctx, props):
    assert ctx.addon_module in bpy.context.preferences.addons
    for name in NEW:
        assert hasattr(bpy.types, name), f"{name} not registered"
    for name in LEGACY:
        assert not hasattr(bpy.types, name), f"retired legacy type {name} is registered"
    assert not hasattr(bpy.types.Scene, "snapsplit"), "legacy Scene.snapsplit is registered"
    assert not dir(bpy.ops.snapsplit), f"legacy operators registered: {dir(bpy.ops.snapsplit)}"
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
        assert ctx.module("ui.overlay")._handle is None, "overlay draw handler left after disable"
        bpy.ops.preferences.addon_enable(module=ctx.addon_module)
        _assert_registered(ctx, props)
