# SPDX-License-Identifier: GPL-3.0-or-later
"""The split-preview material can be built (shadow_method no longer exists in 4.2+)."""

import bpy


def run(ctx):
    ops_split = ctx.module("ops_split")
    mat = ops_split.build_orange_preview_material()
    assert isinstance(mat, bpy.types.Material), type(mat)
    assert mat.name == ops_split.PREVIEW_MAT_NAME, mat.name
    # Second call reuses the existing material
    assert ops_split.build_orange_preview_material() == mat
