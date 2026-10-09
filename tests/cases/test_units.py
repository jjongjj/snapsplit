# SPDX-License-Identifier: GPL-3.0-or-later
"""Legacy unit helper: a millimeter scene has 1 scene unit per mm."""

import lib


def run(ctx):
    lib.set_scene_mm()
    utils = ctx.module("utils")
    assert utils.unit_mm() == 1.0, utils.unit_mm()
    assert utils.mm_to_scene(2.5) == 2.5, utils.mm_to_scene(2.5)
