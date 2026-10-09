# SPDX-License-Identifier: GPL-3.0-or-later
"""debug_log (default off) controls the [<AddonName> DEBUG] output (Build: one line per boolean attempt)."""

import io
import logging

import bpy

import lib


def _split_and_capture(ctx, handler):
    """Build a cube with a Z cut and a pin; return what the add-on logger printed."""
    buf = io.StringIO()
    old = handler.setStream(buf)
    try:
        bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
        lib.set_scene_mm()
        lib.select_only([lib.make_cube(40.0)])
        lib.run_op(bpy.ops.splitforge.easy_cut, axis='Z', offset_mm=0.0, connector_count=1)
    finally:
        handler.setStream(old)
    return buf.getvalue()


def run(ctx):
    log = ctx.module("core.log")
    handlers = logging.getLogger(log.ADDON_PACKAGE).handlers
    assert len(handlers) == 1, handlers
    prefs = bpy.context.preferences.addons[ctx.addon_module].preferences
    assert prefs.debug_log is False

    out = _split_and_capture(ctx, handlers[0])
    assert "DEBUG" not in out, out

    prefs.debug_log = True
    try:
        out = _split_and_capture(ctx, handlers[0])
    finally:
        prefs.debug_log = False
    name = ctx.module("core.naming").ADDON_NAME
    assert f"[{name} DEBUG] boolean UNION on Cube_" in out, out[:2000]

    out = _split_and_capture(ctx, handlers[0])
    assert "DEBUG" not in out, out
