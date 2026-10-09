# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# ops/ops_export.py
"""Export the built parts, one file per part and format (STL/OBJ/FBX)."""

import os

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator

from ..core import compat, naming, units
from ..cuts import build
from ..model import stack as stack_api

FORMAT_ITEMS = [('STL', "STL", "Binary STL"), ('OBJ', "OBJ", "Wavefront OBJ"), ('FBX', "FBX", "Autodesk FBX")]
EXTENSIONS = {'STL': ".stl", 'OBJ': ".obj", 'FBX': ".fbx"}


def built_parts(obj):
    """Part objects of the last build of ``obj`` (the stack owner), sorted by name."""
    coll = build.result_collection(obj)
    if coll is None:
        return []
    return sorted((o for o in coll.objects if o.get(naming.PROP_SOURCE) is not None), key=lambda o: o.name)


class SPLITFORGE_OT_export_parts(Operator):
    """Export every built part of the active object to its own file"""
    bl_idname = naming.op("export_parts")
    bl_label = "Export Parts"
    bl_options = {'REGISTER'}

    directory: StringProperty(name="Folder", subtype='DIR_PATH', default="",
                              description="Target folder (empty = scene setting)")
    formats: EnumProperty(name="Formats", items=FORMAT_ITEMS, options={'ENUM_FLAG'}, default=set(),
                          description="File formats (none = scene setting)")
    apply_scale_mm: BoolProperty(name="Write millimeters", default=True,
                                 description="Scale so that file units are millimeters (what slicers expect)")

    @classmethod
    def poll(cls, context):
        obj = stack_api.context_owner(context)
        return obj is not None and bool(built_parts(obj))

    def execute(self, context):
        settings = getattr(context.scene, naming.SCENE_SETTINGS)
        raw = self.directory or settings.export_directory
        formats = set(self.formats) or set(settings.export_formats)
        # "//" is relative to the .blend file: meaningless (cwd) while the file is unsaved
        if not raw or (raw.startswith("//") and not bpy.data.filepath):
            self.report({'ERROR'}, "Save the file first or choose an absolute export folder")
            return {'CANCELLED'}
        directory = bpy.path.abspath(raw)
        if not os.path.isabs(directory):
            self.report({'ERROR'}, f"Export folder must be absolute: {directory}")
            return {'CANCELLED'}
        missing = formats - set(compat.export_formats())
        if missing:
            self.report({'ERROR'}, f"Exporter not available in this Blender: {', '.join(sorted(missing))}")
            return {'CANCELLED'}
        if not formats:
            self.report({'ERROR'}, "No export format selected")
            return {'CANCELLED'}
        os.makedirs(directory, exist_ok=True)

        all_parts = built_parts(stack_api.context_owner(context))
        parts = [p for p in all_parts if p.visible_get()]
        hidden = len(all_parts) - len(parts)
        if hidden:
            self.report({'WARNING'}, f"{hidden} hidden part(s) not exported")
        if not parts:
            self.report({'ERROR'}, "No visible parts to export")
            return {'CANCELLED'}
        scale = units.bu_to_mm_factor(context.scene) if self.apply_scale_mm else 1.0
        view_layer = context.view_layer
        selected = [o.name for o in context.selected_objects]
        active = view_layer.objects.active.name if view_layer.objects.active else None
        written = []
        try:
            for part in parts:
                for o in context.selected_objects:
                    o.select_set(False)
                part.select_set(True)
                view_layer.objects.active = part
                for fmt in sorted(formats):
                    path = os.path.join(directory, bpy.path.clean_name(part.name) + EXTENSIONS[fmt])
                    compat.export_selected(fmt, path, scale)
                    written.append(path)
        finally:
            for o in context.selected_objects:
                o.select_set(False)
            for name in selected:
                o = bpy.data.objects.get(name)
                if o is not None and o.name in view_layer.objects and o.visible_get():
                    o.select_set(True)
            view_layer.objects.active = bpy.data.objects.get(active) if active else None
        self.report({'INFO'}, f"Exported {len(written)} file(s) to {directory}")
        return {'FINISHED'}


classes = (SPLITFORGE_OT_export_parts,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
