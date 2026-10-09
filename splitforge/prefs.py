'''
Copyright (C) 2026 Christoph Medicus
https://dev.betakontext.de
dev@betakontext.de

This file is part of SplitForge, a fork of SnapSplit by Christoph Medicus.

SplitForge is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 3
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, see <https://www.gnu.org/licenses>.
'''

# prefs.py

import bpy
from bpy.props import BoolProperty
from bpy.types import AddonPreferences

from .core import log


def _update_debug_log(self, context):
    """Apply the debug log toggle immediately."""
    log.set_debug(self.debug_log)


class SPLITFORGE_AddonPreferences(AddonPreferences):
    """Add-on preferences."""
    bl_idname = __package__

    debug_log: BoolProperty(
        name="Debug log",
        default=False,
        description="Print detailed debug messages to the system console",
        update=_update_debug_log,
    )

    def draw(self, context):
        self.layout.prop(self, "debug_log")


classes = (SPLITFORGE_AddonPreferences,)


def register():
    """Register add-on preferences."""
    for c in classes:
        bpy.utils.register_class(c)
    log.sync_from_preferences()


def unregister():
    """Unregister add-on preferences."""
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
