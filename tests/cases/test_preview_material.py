# SPDX-License-Identifier: GPL-3.0-or-later
"""The split-preview material can be built (shadow_method no longer exists in 4.2+)
and is orange in Solid view too (Solid/Workbench use Material.diffuse_color)."""

import bpy

import lib


def _is_orange(color):
    r, g, b, _a = color
    return r > 0.9 and 0.3 < g < 0.7 and b < 0.1


def run(ctx):
    ops_split = ctx.module("ops_split")
    mat = ops_split.build_orange_preview_material()
    assert isinstance(mat, bpy.types.Material), type(mat)
    assert mat.name == ops_split.PREVIEW_MAT_NAME, mat.name
    # Second call reuses the existing material
    assert ops_split.build_orange_preview_material() == mat
    assert _is_orange(mat.diffuse_color), f"Solid-view color is not orange: {tuple(mat.diffuse_color)}"

    # A material saved by an older version (grey viewport color) is corrected on reuse
    mat.diffuse_color = (0.8, 0.8, 0.8, 1.0)
    assert _is_orange(ops_split.build_orange_preview_material().diffuse_color)

    # The planes created by the preview carry that material
    lib.set_scene_mm()
    cube = lib.make_cube(40.0)
    lib.select_only([cube])
    bpy.context.scene.snapsplit.show_split_preview = True
    planes = [o for o in bpy.data.objects if o.name.startswith(ops_split.PREVIEW_PLANE_PREFIX)]
    assert planes, "no preview plane"
    for plane in planes:
        assert plane.active_material == mat, plane.active_material
    bpy.context.scene.snapsplit.show_split_preview = False
