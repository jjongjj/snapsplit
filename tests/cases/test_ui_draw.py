# SPDX-License-Identifier: GPL-3.0-or-later
"""P1-12: every new panel and UI list draws without errors in each workflow state.

Panels are drawn with a recording stand-in layout inside ``context.temp_override``.
The stand-in also checks that every ``prop()`` names an existing property and every
``operator()`` an existing operator, so a renamed property cannot break the panel
silently. The overlay geometry (gpu draw handler) is computed for the same states.
"""

import math

import bpy

import lib


class Layout:
    """Accepts the UILayout API used by the panels and records what was drawn."""

    def __init__(self, log):
        self._log = log
        self.enabled = True
        self.active = True
        self.alert = False
        self.scale_y = 1.0
        self.operator_context = 'INVOKE_DEFAULT'

    def _sub(self, *args, **kwargs):
        return Layout(self._log)

    row = column = box = split = _sub

    def label(self, text="", icon='NONE', **kwargs):
        self._log.append(("label", text))

    def separator(self, **kwargs):
        pass

    def prop(self, data, prop, **kwargs):
        assert prop in data.bl_rna.properties, f"{type(data).__name__}.{prop} does not exist"
        self._log.append(("prop", prop))

    def operator(self, idname, **kwargs):
        group, name = idname.split(".")
        rna = getattr(getattr(bpy.ops, group), name).get_rna_type()
        self._log.append(("operator", idname))

        class Props:
            def __setattr__(self, key, value):
                assert key in rna.properties, f"{idname} has no property {key}"
                object.__setattr__(self, key, value)
        return Props()

    def template_list(self, list_type, list_id, data, prop, active_data, active_prop, **kwargs):
        assert hasattr(bpy.types, list_type), f"UI list {list_type} not registered"
        assert prop in data.bl_rna.properties and active_prop in active_data.bl_rna.properties
        self._log.append(("list", list_type))
        ul = getattr(bpy.types, list_type)
        for index, item in enumerate(getattr(data, prop)):
            ul.draw_item(None, bpy.context, Layout(self._log), data, item, 0, active_data, active_prop, index)


PANELS = ("SPLITFORGE_PT_main", "SPLITFORGE_PT_connectors", "SPLITFORGE_PT_build", "SPLITFORGE_PT_settings")


def _draw_all(state):
    log = []
    with bpy.context.temp_override():
        for name in PANELS:
            cls = getattr(bpy.types, name)
            if hasattr(cls, "poll") and not cls.poll(bpy.context):
                log.append(("hidden", name))
                continue
            panel = type("Stub", (), {"layout": Layout(log)})()
            cls.draw(panel, bpy.context)
            log.append(("drawn", name))
    return log


def run(ctx):
    overlay = ctx.module("ui.overlay")
    lib.set_scene_mm()

    log = _draw_all("no object")
    assert ("label", "Select a mesh object") in log, log
    assert ("hidden", "SPLITFORGE_PT_connectors") in log

    cube = lib.make_cube(40.0)
    cube.name = "UiCube"
    lib.select_only([cube])
    log = _draw_all("empty stack")
    assert ("drawn", "SPLITFORGE_PT_main") in log and ("hidden", "SPLITFORGE_PT_connectors") in log
    assert ("operator", "splitforge.stack_add_plane") in log
    assert overlay.geometry(bpy.context) == ([], [])

    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='X')
    lib.run_op(bpy.ops.splitforge.connector_add_auto)
    cube.splitforge_stack.cuts[1].connectors[0].kind = 'RECT_TENON'
    cube.splitforge_stack.cuts[1].active_connector = 0
    cube.splitforge_stack.cuts[0].enabled = False
    log = _draw_all("draft")
    for item in (("drawn", "SPLITFORGE_PT_connectors"), ("list", "SPLITFORGE_UL_cuts"),
                 ("list", "SPLITFORGE_UL_connectors"), ("operator", "splitforge.cut_adjust_plane"),
                 ("operator", "splitforge.build"), ("prop", "pin_side"), ("prop", "height_mm")):
        assert item in log, (item, log)
    fills, lines = overlay.geometry(bpy.context)
    # Cut 0 disabled (outline only), cut 1 active (fill + outline + one per connector)
    n_conn = len(cube.splitforge_stack.cuts[1].connectors)
    assert n_conn == 4, n_conn  # 2 per seam region, the Z cut splits the X seam in two
    assert len(fills) == 1 and len(lines) == 2 + n_conn, (len(fills), len(lines))

    # Every connector type: its own fields for the active connector and the new-connector template
    active = cube.splitforge_stack.cuts[1].connectors[0]
    template = bpy.context.scene.splitforge.new_connector
    expect = {
        'CYL_PIN': ({"embed_pct", "chamfer_mm", "pin_side"}, {"height_mm", "taper_pct", "snap_count"}),
        'RECT_TENON': ({"height_mm", "embed_pct"}, {"taper_pct", "snap_count", "custom_object"}),
        'DOVETAIL': ({"taper_pct", "height_mm"}, {"snap_count"}),
        'SNAP_PIN': ({"snap_count", "snap_diameter_mm", "snap_protrusion_mm"}, {"taper_pct", "height_mm"}),
        'SNAP_TENON': ({"snap_count", "height_mm"}, {"taper_pct"}),
        'SNAP_DOVETAIL': ({"snap_count", "taper_pct"}, set()),
        'CUSTOM': ({"custom_object", "height_mm"}, {"chamfer_mm", "taper_pct"}),
        'DOWEL': ({"chamfer_mm"}, {"pin_side", "embed_pct", "height_mm"}),
    }
    for kind, (shown, hidden) in expect.items():
        active.kind = kind
        template.kind = kind
        log = _draw_all(kind)
        props = {e[1] for e in log if e[0] == "prop"}
        assert shown <= props and not (hidden & props), (kind, shown - props, hidden & props)
        assert ("operator", "splitforge.connector_add_click") in log, kind
        if kind == 'CUSTOM':
            assert ("operator", "splitforge.connector_custom_size") in log
            assert ("label", "no custom mesh object chosen") in log, log
        fills, lines = overlay.geometry(bpy.context)
        assert len(lines) == 2 + n_conn, (kind, len(lines))
    active.kind = template.kind = 'RECT_TENON'

    cube.splitforge_stack.cuts[0].enabled = True
    lib.run_op(bpy.ops.splitforge.build)
    # Active object is now a part: the panel shows the source stack and the result
    log = _draw_all("built")
    assert ("label", "Part of UiCube") in log, log
    assert ("operator", "splitforge.export_parts") in log
    assert any(e[0] == "label" and "part(s) in SplitForge_Build_UiCube" in e[1] for e in log), log

    # A stroke cut: Redraw button instead of the plane fields, ribbon + connectors in the overlay
    lib.select_only([cube])
    cube.hide_set(False)
    lib.run_op(bpy.ops.splitforge.stack_add_stroke, direction=(0.0, 1.0, 0.0),
               points=[{"name": "", "co": (-26.0 + 52.0 * i / 19, 0.0, 6.0 + 1.5 * math.sin(i / 3.0))}
                       for i in range(20)])
    lib.run_op(bpy.ops.splitforge.connector_add_auto)
    log = _draw_all("stroke")
    assert ("operator", "splitforge.stack_add_stroke") in log, log
    assert any(e[0] == "label" and e[1].startswith("Stroke:") for e in log), log
    assert ("operator", "splitforge.cut_adjust_plane") not in log
    stroke_cut = cube.splitforge_stack.cuts[-1]
    tris, segs, matrix_fn = overlay.stroke_ribbon(cube, stroke_cut)
    assert len(tris) == 6 * (len(stroke_cut.points) - 1) and segs and matrix_fn is not None
    fills, lines = overlay.geometry(bpy.context)
    assert len(fills) == 3 and len(lines) == 3 + n_conn + len(stroke_cut.connectors), (len(fills), len(lines))

    # Polyline and polygon cuts: their own label, Redraw operator, Depth (polygon), overlay
    lib.run_op(bpy.ops.splitforge.stack_add_polyline, direction=(0.0, 1.0, 0.0),
               points=[{"name": "", "co": co} for co in ((-30.0, 0.0, -8.0), (0.0, 0.0, -2.0), (30.0, 0.0, -8.0))])
    log = _draw_all("polyline")
    assert ("operator", "splitforge.stack_add_polyline") in log and ("prop", "depth_mm") not in log, log
    assert any(e[0] == "label" and e[1] == "Polyline: 3 points" for e in log), log
    tris, segs, matrix_fn = overlay.stroke_ribbon(cube, cube.splitforge_stack.cuts[-1])
    assert len(tris) == 6 * 2 and matrix_fn is not None
    lib.run_op(bpy.ops.splitforge.stack_add_polygon, direction=(0.0, 0.0, -1.0), depth_mm=6.0,
               points=[{"name": "", "co": co} for co in ((-8.0, -8.0, 30.0), (8.0, -8.0, 30.0), (0.0, 9.0, 30.0))])
    log = _draw_all("polygon")
    assert ("prop", "depth_mm") in log and any(e[0] == "label" and e[1] == "Polygon: 3 corners" for e in log), log
    poly = cube.splitforge_stack.cuts[-1]
    tris, segs, matrix_fn = overlay.polygon_prism(cube, poly, 1.0)
    assert len(tris) == 6 * 3 and len(segs) == 2 * 3 * 2 + 2 * 3 and matrix_fn is not None
    assert abs(matrix_fn(0.0, 0.0, 0.0).translation.z - 14.0) < 1e-4, "connectors on the floor (20 - 6)"
    poly.depth_mm = 0.0
    assert overlay.polygon_prism(cube, poly, 1.0)[2] is None, "no floor, no connector frame"
    log = _draw_all("polygon through")
    assert ("label", "Polygon through the object: set a Depth for connectors on its floor") in log, log
    poly.depth_mm = 6.0
    fills, lines = overlay.geometry(bpy.context)
    assert len(fills) == 5, len(fills)

    cube.splitforge_stack.mode = 'EASY'
    log = _draw_all("easy")
    assert ("operator", "splitforge.stack_add_polyline") in log and ("operator", "splitforge.stack_add_polygon") in log
    assert ("prop", "easy_depth_mm") in log
    assert ("operator", "splitforge.easy_cut") in log and ("hidden", "SPLITFORGE_PT_connectors") in log
    assert ("prop", "easy_gap_mm") in log and log.count(("operator", "splitforge.stack_add_stroke")) == 1

    bpy.context.scene.splitforge.show_overlay = False
    assert overlay.geometry(bpy.context) == ([], [])
