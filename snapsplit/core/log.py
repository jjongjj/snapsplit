# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SnapSplit.

# core/log.py
"""Add-on logger.

Debug messages are only emitted when the add-on preference ``debug_log`` is
enabled; INFO and above are always printed to stdout.
"""

import logging
import sys

import bpy

# Package of the add-on itself ("snapsplit" or "bl_ext.<repo>.snapsplit")
ADDON_PACKAGE = __package__.rpartition(".")[0]

_logger = logging.getLogger(ADDON_PACKAGE)
_logger.propagate = False
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("[SnapSplit %(levelname)s] %(message)s"))
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
