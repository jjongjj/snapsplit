# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# core/naming.py
"""Single source of truth for the add-on identity.

The product name is a temporary working name. Renaming the add-on means
changing the constants below (and the extension ``id``/``name`` in
``blender_manifest.toml``); everything new derives its operator ids, type
names, property names and collection names from here. Python class names use
the ``SPLITFORGE_`` prefix literally (Blender derives nothing from them because
every class sets ``bl_idname`` from these constants).

The legacy SnapSplit operators (``snapsplit.*``) and ``Scene.snapsplit`` keep
their upstream names until the legacy UI is removed (Phase 3).
"""

ADDON_NAME = "SplitForge"

# Operator namespace: bpy.ops.<OP>.<name>, bl_idname "<OP>.<name>"
OP = "splitforge"
# Prefix of registered type names: <CLS>_PT_main, <CLS>_UL_cuts, ...
CLS = "SPLITFORGE"

# RNA properties added to Blender types
SCENE_SETTINGS = "splitforge"          # Scene.<..> -> global settings
OBJECT_STACK = "splitforge_stack"      # Object.<..> -> cut stack

# ID custom properties written on build results
PROP_SOURCE = "splitforge_source"
PROP_CUT_IDS = "splitforge_cut_ids"
# ID references (survive renames): on parts the source object, on a build
# collection the source object that owns it
PROP_SOURCE_OBJECT = "splitforge_source_object"
PROP_OWNER = "splitforge_owner"
# On a dowel part: label of the connector it belongs to
PROP_DOWEL = "splitforge_dowel"

# Dowel part names: <source><DOWEL_SUFFIX><n>
DOWEL_SUFFIX = "_Dowel_"

# Collections
BUILD_COLLECTION_PREFIX = "SplitForge_Build_"

# N-panel tab
UI_CATEGORY = ADDON_NAME


def op(name):
    """bl_idname of a new operator, e.g. op("build") -> "splitforge.build"."""
    return f"{OP}.{name}"


def cls(kind, name):
    """Registered type name, e.g. cls("PT", "main") -> "SPLITFORGE_PT_main"."""
    return f"{CLS}_{kind}_{name}"


def build_collection_name(obj_name):
    return BUILD_COLLECTION_PREFIX + obj_name
