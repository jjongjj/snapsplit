# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# ui/panel.py
"""N-panel: Draft/Easy workflow (main panel + Connectors, Build & Export, Settings).

The legacy SnapSplit panel is registered afterwards as a collapsed "Legacy"
sub-panel of the main panel (see ui.py).
"""

import bpy
from bpy.types import Panel, UIList

from ..core import naming, units, validate
from ..model import stack as stack_api
from ..ops.ops_export import built_parts

OP = naming.op
MAIN_PANEL = naming.cls("PT", "main")


def _owner_stack(context):
    obj = stack_api.context_owner(context)
    return obj, stack_api.get_stack(obj)


class SPLITFORGE_UL_cuts(UIList):
    """Cuts: checkbox + name only, so names stay readable in a narrow sidebar
    (gap and connector count are shown in the box under the list)."""
    bl_idname = naming.cls("UL", "cuts")

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="")
        row.prop(item, "name", text="", emboss=False)
        if item.kind == 'STROKE' and item.problem:
            row.label(text="", icon='ERROR')


class SPLITFORGE_UL_connectors(UIList):
    """Connectors: short label (number, type, pin side); position/size in the box below."""
    bl_idname = naming.cls("UL", "connectors")

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="")
        kind = "Pin" if item.kind == 'CYL_PIN' else "Tenon"
        row.label(text=f"{index + 1} {kind}  pin {item.pin_side}")


class _Base:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = naming.UI_CATEGORY


def draw_checks(context, layout, obj):
    """Live print checks (cheap ones only; the full mesh scan is the Check Mesh button)."""
    box = layout.box()
    row = box.row(align=True)
    scale_ok = validate.transform_is_applied(obj)
    mm_ok = units.is_mm_scene(context.scene)
    row.label(text="Transforms", icon='CHECKMARK' if scale_ok else 'ERROR')
    row.label(text=f"1 unit = {units.bu_to_mm_factor(context.scene):g} mm",
              icon='CHECKMARK' if mm_ok else 'INFO')
    row.operator(OP("validate"), text="", icon='VIEWZOOM')


def draw_easy(context, layout):
    s = getattr(context.scene, naming.SCENE_SETTINGS)
    col = layout.column(align=True)
    col.row(align=True).prop(s, "easy_axis", expand=True)
    col.prop(s, "easy_offset_mm")
    col.prop(s, "easy_gap_mm")
    col.prop(s, "easy_connector_count")
    row = layout.row(align=True)
    row.operator(OP("easy_cut"), text="Cut", icon='MOD_BOOLEAN')
    draw = row.row(align=True)
    draw.operator_context = 'INVOKE_REGION_WIN'
    draw.operator(OP("stack_add_stroke"), text="Draw Cut", icon='CURVE_BEZCURVE').easy = True


def draw_draft(context, layout, stack):
    row = layout.row()
    row.template_list(naming.cls("UL", "cuts"), "", stack, "cuts", stack, "active_index", rows=4)
    col = row.column(align=True)
    for axis in ('X', 'Y', 'Z'):
        col.operator(OP("stack_add_plane"), text=axis).axis = axis
    stroke_col = col.column(align=True)
    stroke_col.operator_context = 'INVOKE_REGION_WIN'
    stroke_col.operator(OP("stack_add_stroke"), text="", icon='CURVE_BEZCURVE')
    col.separator()
    col.operator(OP("stack_remove"), text="", icon='REMOVE')
    col.operator(OP("stack_duplicate"), text="", icon='DUPLICATE')
    col.separator()
    col.operator(OP("stack_move"), text="", icon='TRIA_UP').direction = 'UP'
    col.operator(OP("stack_move"), text="", icon='TRIA_DOWN').direction = 'DOWN'
    col.separator()
    col.operator(OP("stack_clear"), text="", icon='TRASH')

    if not stack.cuts:
        layout.label(text="Add a cut (X/Y/Z or stroke), then Build", icon='INFO')
        return
    cut = stack.cuts[min(stack.active_index, len(stack.cuts) - 1)]
    box = layout.box()
    box.row().prop(cut, "name", text="")
    box.label(text=f"Gap {cut.gap_mm:g} mm, {len(cut.connectors)} connector(s)")
    row = box.row(align=True)
    row.prop(cut, "enabled")
    if cut.kind == 'STROKE':
        box.prop(cut, "gap_mm")
        if cut.problem:
            col = box.column(align=True)
            col.alert = True
            col.label(text="Cannot build this cut:", icon='ERROR')
            for line in _wrap(cut.problem, 34):
                col.label(text=line)
        box.label(text=f"Stroke: {len(cut.points)} points", icon='CURVE_BEZCURVE')
        op_row = box.row()
        op_row.operator_context = 'INVOKE_REGION_WIN'
        op_row.operator(OP("stack_add_stroke"), text="Redraw in Viewport",
                        icon='GREASEPENCIL').replace_uid = cut.uid
        return
    row.prop(cut, "cap")
    box.prop(cut, "gap_mm")
    col = box.column(align=True)
    col.prop(cut, "origin")
    col = box.column(align=True)
    col.prop(cut, "normal")
    op_row = box.row()
    op_row.operator_context = 'INVOKE_REGION_WIN'
    op_row.operator(OP("cut_adjust_plane"), text="Adjust in Viewport", icon='ORIENTATION_GLOBAL')


def _wrap(text, width):
    """Split a message into lines of about ``width`` characters (labels do not wrap)."""
    lines, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return lines + ([cur] if cur else [])


class SPLITFORGE_PT_main(_Base, Panel):
    bl_idname = MAIN_PANEL
    bl_label = naming.ADDON_NAME

    def draw(self, context):
        layout = self.layout
        obj, stack = _owner_stack(context)
        if stack is None:
            layout.label(text="Select a mesh object", icon='INFO')
            return
        active = context.active_object
        if active is not None and active != obj:
            # Built parts have no stack of their own: edits go to the source's stack
            col = layout.column(align=True)
            col.label(text=f"Part of {obj.name}", icon='LINKED')
            col.label(text="Editing the source's cuts")
        else:
            layout.label(text=obj.name, icon='OBJECT_DATA')

        draw_checks(context, layout, obj)
        layout.row().prop(stack, "mode", expand=True)
        if stack.mode == 'EASY':
            draw_easy(context, layout)
        else:
            draw_draft(context, layout, stack)

class SPLITFORGE_PT_connectors(_Base, Panel):
    bl_idname = naming.cls("PT", "connectors")
    bl_label = "Connectors"
    bl_parent_id = MAIN_PANEL

    @classmethod
    def poll(cls, context):
        _obj, stack = _owner_stack(context)
        return stack is not None and stack.mode == 'DRAFT' and len(stack.cuts) > 0

    def draw(self, context):
        layout = self.layout
        _obj, stack = _owner_stack(context)
        cut = stack.cuts[min(stack.active_index, len(stack.cuts) - 1)]
        s = getattr(context.scene, naming.SCENE_SETTINGS)
        layout.label(text=f"On {cut.name}")

        col = layout.column(align=True)
        col.prop(s, "new_connector_kind", text="")
        row = col.row(align=True)
        row.prop(s, "new_connector_width_mm", text="W")
        if s.new_connector_kind == 'RECT_TENON':
            row.prop(s, "new_connector_height_mm", text="H")
        row.prop(s, "new_connector_length_mm", text="L")
        col = layout.column(align=True)
        col.row(align=True).prop(cut, "distribution", expand=True)
        row = col.row(align=True)
        row.prop(cut, "connector_count")
        if cut.distribution == 'GRID':
            row.prop(cut, "connector_rows")
        col.prop(cut, "margin_pct")
        row = layout.row(align=True)
        row.operator(OP("connector_add_auto"), text="Distribute", icon='SNAP_FACE_CENTER')
        row.operator(OP("connector_add"), text="", icon='ADD')
        row.operator(OP("connector_remove"), text="", icon='REMOVE')

        layout.template_list(naming.cls("UL", "connectors"), "", cut, "connectors", cut, "active_connector",
                             rows=3)
        if not cut.connectors:
            return
        c = cut.connectors[min(cut.active_connector, len(cut.connectors) - 1)]
        box = layout.box()
        box.prop(c, "kind", text="")
        row = box.row(align=True)
        row.prop(c, "u")
        row.prop(c, "v")
        box.prop(c, "rotation_deg")
        row = box.row(align=True)
        row.prop(c, "width_mm", text="W")
        if c.kind == 'RECT_TENON':
            row.prop(c, "height_mm", text="H")
        row.prop(c, "length_mm", text="L")
        row = box.row(align=True)
        row.label(text="Pin on")
        row.prop(c, "pin_side", expand=True)
        box.prop(c, "clearance_mm")


class SPLITFORGE_PT_build(_Base, Panel):
    bl_idname = naming.cls("PT", "build")
    bl_label = "Build & Export"
    bl_parent_id = MAIN_PANEL

    @classmethod
    def poll(cls, context):
        _obj, stack = _owner_stack(context)
        return stack is not None

    def draw(self, context):
        layout = self.layout
        obj, stack = _owner_stack(context)
        parts = built_parts(obj)
        row = layout.row(align=True)
        row.scale_y = 1.4
        row.operator(OP("build"), text="Rebuild" if parts else "Build", icon='MOD_BUILD')
        row.operator(OP("clear_build"), text="", icon='X')
        if parts:
            layout.label(text=f"{len(parts)} part(s) in {parts[0].users_collection[0].name}",
                         icon='OUTLINER_COLLECTION')
        s = getattr(context.scene, naming.SCENE_SETTINGS)
        col = layout.column(align=True)
        col.prop(s, "export_directory", text="")
        col.row(align=True).prop(s, "export_formats", expand=True)
        layout.operator(OP("export_parts"), icon='EXPORT')


class SPLITFORGE_PT_settings(_Base, Panel):
    bl_idname = naming.cls("PT", "settings")
    bl_label = "Settings"
    bl_parent_id = MAIN_PANEL
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        s = getattr(context.scene, naming.SCENE_SETTINGS)
        layout.prop(s, "show_overlay")
        row = layout.row(align=True)
        row.prop(s, "material", text="")
        row.prop(s, "clearance_mm")
        layout.prop(s, "boolean_quality")


classes = (
    SPLITFORGE_UL_cuts,
    SPLITFORGE_UL_connectors,
    SPLITFORGE_PT_main,
    SPLITFORGE_PT_connectors,
    SPLITFORGE_PT_build,
    SPLITFORGE_PT_settings,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
