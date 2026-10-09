# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# core/log.py
"""Add-on logger.

Debug messages are only emitted when the add-on preference ``debug_log`` is
enabled; INFO and above are always printed to stdout.
"""

import logging
import sys

import bpy

from .naming import ADDON_NAME

# Package of the add-on itself (e.g. "bl_ext.<repo>.splitforge")
ADDON_PACKAGE = __package__.rpartition(".")[0]

_logger = logging.getLogger(ADDON_PACKAGE)
_logger.propagate = False
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter(f"[{ADDON_NAME} %(levelname)s] %(message)s"))
    _logger.addHandler(_handler)
_logger.setLevel(logging.INFO)


def set_debug(enabled):
    """Enable or disable DEBUG output."""
    _logger.setLevel(logging.DEBUG if enabled else logging.INFO)


def sync_from_preferences():
    """Apply the ``debug_log`` add-on preference (False if unavailable)."""
    addon = bpy.context.preferences.addons.get(ADDON_PACKAGE)
    prefs = getattr(addon, "preferences", None)
    set_debug(bool(getattr(prefs, "debug_log", False)))


def debug(msg, *args):
    _logger.debug(msg, *args)


def info(msg, *args):
    _logger.info(msg, *args)


def warning(msg, *args):
    _logger.warning(msg, *args)


def error(msg, *args):
    _logger.error(msg, *args)
