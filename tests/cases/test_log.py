# SPDX-License-Identifier: GPL-3.0-or-later
"""The debug_log preference (default off) switches DEBUG output of core.log."""

import logging

import bpy


def run(ctx):
    log = ctx.module("core.log")
    logger = logging.getLogger(log.ADDON_PACKAGE)
    prefs = bpy.context.preferences.addons[ctx.addon_module].preferences
    assert prefs.debug_log is False
    assert not logger.isEnabledFor(logging.DEBUG)
    try:
        prefs.debug_log = True
        assert logger.isEnabledFor(logging.DEBUG)
    finally:
        prefs.debug_log = False
    assert not logger.isEnabledFor(logging.DEBUG)
