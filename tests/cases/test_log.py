# SPDX-License-Identifier: GPL-3.0-or-later
"""debug_log (default off) controls the [<AddonName> DEBUG] output of the legacy split."""

import io
import logging

import bpy

import lib


def _split_and_capture(ctx, handler):
    """Run a capped monkey split; return what the add-on logger printed."""
    buf = io.StringIO()
    old = handler.setStream(buf)
    try:
        bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
        lib.set_scene_mm()
        lib.select_only([lib.make_monkey_manifold(40.0)])
        lib.run_op(bpy.ops.snapsplit.planar_split)
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
    assert f"[{name} DEBUG] ---- cap_single_object_hollow_style:" in out, out[:2000]

    out = _split_and_capture(ctx, handlers[0])
    assert "DEBUG" not in out, out
