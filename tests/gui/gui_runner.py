# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SnapSplit.
"""GUI scenario runner for modal operators (started by ``tests/run_tests.py --gui``).

blender --factory-startup --enable-event-simulate --python gui_runner.py -- \
    --repo <dir containing the package> --package NAME --scenario NAME --out <json> --shots <dir> --label <str>

Modal operators only run in a real window, so these scenarios start a GUI Blender
(with simulated input, real input is blocked) and drive it step by step from a
persistent ``bpy.app.timers`` callback: one simulated event per step, so Blender
processes every event (and mouse_prev) like real input. Each scenario records checks
in a JSON report, saves viewport screenshots to ``--shots`` and quits Blender.
A crash (no report / non-zero exit code / blender.crash.txt) is a FAIL in run_tests.py.

Units follow the standard 3D-print setup (Metric, Millimeters, Unit Scale 0.001, so
1 BU = 1 mm in Blender and in the add-on, see docs/MANUAL_QA.md): the cube is 40 BU = 40 mm.

Scenarios
    p1_adjust_plane    QA-5: cut plane overlay, splitforge.cut_adjust_plane drag/wheel/X/LMB/Esc,
                       real Ctrl+Z / Ctrl+Shift+Z, undo during the modal, file load -> cancel()
    p1_panel           QA-6: sidebar buttons clicked for real (add, undo, toggle, remove,
                       Distribute, Build, Export, Clear)
    p2_stroke          QA-7: stroke cut drawn with LMB, ribbon preview, Enter, undo/redo, modal
                       Build, Esc/RMB, Shift snap, Redraw, file load -> cancel()
    p2_build_progress  QA-8: modal Build progress on a 130k-face Suzanne, Esc mid-build
    p3_connector_click QA-9: splitforge.connector_add_click: preview follows the cursor, LMB
                       places at the cursor, S flips the pin side, real Ctrl+Z / Ctrl+Shift+Z
                       one connector per step (during and after the modal), Build, file load
    p3_connector_types QA-10: one connector of every type on a bar, built and pulled apart
                       (screenshots of the pins and sockets)
"""

import argparse
import io
import json
import math
import os
import sys
import traceback

import bmesh
import bpy
from bpy_extras import view3d_utils
import mathutils
from mathutils import Euler, Vector

REPO_NAME = "splitforge_gui_test"

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser(prog="gui_runner.py")
ap.add_argument("--repo", required=True)
ap.add_argument("--package", default="splitforge")
ap.add_argument("--scenario", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--shots", default="")
ap.add_argument("--label", default="")
ARGS = ap.parse_args(argv)
ADDON = f"bl_ext.{REPO_NAME}.{ARGS.package}"

REPORT = {"blender": bpy.app.version_string, "scenario": ARGS.scenario,
          "tempdir": bpy.app.tempdir, "checks": [], "log": [], "screenshots": [],
          "ok": False, "completed": False}


def log(*parts):
    REPORT["log"].append(" ".join(str(p) for p in parts))


def check(name, cond, detail=""):
    REPORT["checks"].append({"name": name, "ok": bool(cond), "detail": str(detail)})


def write_report():
    REPORT["ok"] = bool(REPORT["checks"]) and all(c["ok"] for c in REPORT["checks"])
    with open(ARGS.out, "w", encoding="utf-8") as f:
        json.dump(REPORT, f, indent=1)


class _Tee(io.TextIOBase):
    """Keep a copy of stdout so add-on reports (report_user prints) can be checked."""

    def __init__(self, orig):
        self.orig = orig
        self.lines = []

    def write(self, text):
        self.lines.append(text)
        try:
            return self.orig.write(text)
        except Exception:
            return len(text)

    def flush(self):
        try:
            self.orig.flush()
        except Exception:
            pass


STDOUT = _Tee(sys.stdout)
sys.stdout = STDOUT


def printed(text, since=0):
    """True if ``text`` was printed after output position ``since`` (see output_mark)."""
    return text in "".join(STDOUT.lines)[since:]


def output_mark():
    return len("".join(STDOUT.lines))


# --- add-on -----------------------------------------------------------------

repos = bpy.context.preferences.extensions.repos
repo = repos.get(REPO_NAME) or repos.new(name=REPO_NAME, module=REPO_NAME, custom_directory=ARGS.repo)
repo.use_custom_directory = True
repo.enabled = True
bpy.ops.extensions.repo_refresh_all()
bpy.ops.preferences.addon_enable(module=ADDON)
bpy.context.preferences.edit.undo_steps = 64


def mod(name):
    return sys.modules[f"{ADDON}.{name}"]


# --- viewport / input helpers -------------------------------------------------

def view3d():
    win = bpy.context.window_manager.windows[0]
    area = max((a for a in win.screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return win, area, region


def override():
    win, area, region = view3d()
    return bpy.context.temp_override(window=win, area=area, region=region, screen=win.screen)


def modal_ops():
    return [o.bl_idname for o in view3d()[0].modal_operators]


def named(name, fn):
    fn.__name__ = name
    return fn


def region_center():
    _win, _area, region = view3d()
    return region.x + region.width // 2, region.y + region.height // 2


def world_to_window(co):
    """Window coordinates of a world point in the 3D viewport."""
    _win, area, region = view3d()
    p = view3d_utils.location_3d_to_region_2d(region, area.spaces.active.region_3d, Vector(co))
    return region.x + int(round(p.x)), region.y + int(round(p.y))


def window_ray(x, y):
    _win, area, region = view3d()
    rv3d = area.spaces.active.region_3d
    co = (x - region.x, y - region.y)
    return (view3d_utils.region_2d_to_origin_3d(region, rv3d, co),
            view3d_utils.region_2d_to_vector_3d(region, rv3d, co))


def event(type_, value, xy, **mods):
    win = view3d()[0]
    win.event_simulate(type=type_, value=value, x=int(xy[0]), y=int(xy[1]), **mods)


def move(xy_fn):
    """One MOUSEMOVE per step; xy_fn() is evaluated when the step runs."""
    return named("move", lambda: event('MOUSEMOVE', 'NOTHING', xy_fn()))


def key(type_, value='PRESS', xy_fn=region_center, **mods):
    return named(f"{type_}_{value}", lambda: event(type_, value, xy_fn(), **mods))


def click(type_='LEFTMOUSE', xy_fn=region_center, **mods):
    return [key(type_, 'PRESS', xy_fn, **mods), key(type_, 'RELEASE', xy_fn, **mods)]


def wait():
    pass


def screenshot(name):
    def step():
        if not ARGS.shots:
            return
        os.makedirs(ARGS.shots, exist_ok=True)
        path = os.path.join(ARGS.shots, f"{ARGS.scenario}_{ARGS.label}_{name}.png")
        with override():
            bpy.ops.screen.screenshot_area(filepath=path)
        REPORT["screenshots"].append(path)
        STATE["shots"][name] = path
    return named(f"screenshot_{name}", step)


def set_oblique_view(distance_factor=1.0):
    def step():
        with override():
            bpy.ops.view3d.view_all()
        rv3d = view3d()[1].spaces.active.region_3d
        rv3d.view_perspective = 'ORTHO'
        rv3d.view_rotation = Euler((math.radians(60), 0.0, math.radians(35))).to_quaternion()
        rv3d.view_location = (0.0, 0.0, 0.0)
        with override():
            bpy.ops.view3d.view_all()
        rv3d.view_distance *= distance_factor
    return named("view_oblique", step)


def set_view(axis_type, distance_factor=1.0):
    def step():
        with override():
            bpy.ops.view3d.view_axis(type=axis_type)
            bpy.ops.view3d.view_all()
        rv3d = view3d()[1].spaces.active.region_3d
        rv3d.view_distance *= distance_factor
    return named(f"view_{axis_type}", step)


def set_shading_solid(overlays=False):
    """Solid shading with material colors. Overlays off keeps pixel checks free of grid/axis
    colors; scenarios whose previews are drawn by the overlay engine (wireframe objects,
    gpu draw handlers) keep them on so the screenshots show what they are named for."""
    space = view3d()[1].spaces.active
    space.shading.type = 'SOLID'
    space.shading.color_type = 'MATERIAL'
    space.overlay.show_overlays = overlays


# --- scene helpers ------------------------------------------------------------

STATE = {"shots": {}}


def volume(obj):
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.transform(obj.matrix_world)
        return bm.calc_volume()
    finally:
        bm.free()


def is_manifold(obj):
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        return (len(bm.faces) > 0 and all(e.is_manifold for e in bm.edges)
                and all(not v.is_wire and v.link_faces for v in bm.verts))
    finally:
        bm.free()


def warm_pixels(path):
    """Fraction of warm (orange-tinted) pixels in a screenshot.

    The planes are seen through X-Ray (50 % alpha) with studio lighting, so they look
    brownish orange; grey UI/cube pixels have r == g == b. Warm: r - b > 0.06, r > g.
    """
    img = bpy.data.images.load(path, check_existing=False)
    try:
        px = list(img.pixels[:])
    finally:
        bpy.data.images.remove(img)
    n = len(px) // 4
    warm = sum(1 for i in range(0, len(px), 4) if px[i] - px[i + 2] > 0.06 and px[i] > px[i + 1])
    return warm / max(1, n)


def setup_scene_mm():
    units = bpy.context.scene.unit_settings
    units.system = 'METRIC'
    units.length_unit = 'MILLIMETERS'
    units.scale_length = 0.001


def setup_cube(overlays=False):
    with override():
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o)
        setup_scene_mm()
        bpy.ops.mesh.primitive_cube_add('EXEC_DEFAULT', True, size=40.0)
        bpy.context.active_object.name = "GUI_Cube"
    set_shading_solid(overlays)


def invoke(idname):
    def step():
        STATE["out_mark"] = output_mark()  # reports of this run only
        event('MOUSEMOVE', 'NOTHING', region_center())
        with override():
            group, name = idname.split(".")
            ret = getattr(getattr(bpy.ops, group), name)('INVOKE_DEFAULT', True)
        check(f"{idname} invoked", ret == {'RUNNING_MODAL'}, ret)
    return named(f"invoke_{idname}", step)


def undo():
    with override():
        bpy.ops.ed.undo()


def redo():
    with override():
        bpy.ops.ed.redo()


def load_homefile():
    with override():
        bpy.ops.wm.read_homefile()
    log("read_homefile")


def check_running(idname, expect=True):
    return named(f"check_running_{idname}_{expect}", lambda: check(
        f"{idname} {'running' if expect else 'ended'}",
        (idname in modal_ops()) == expect, modal_ops()))


def drag(steps=4, dy=25):
    """One MOUSEMOVE per step, moving up from the region centre."""
    out = [move(region_center)]
    for i in range(1, steps + 1):
        out.append(move(lambda i=i: (region_center()[0], region_center()[1] + i * dy)))
    return out


def pos(dx=0, dy=0):
    return lambda: (region_center()[0] + dx, region_center()[1] + dy)


# --- P1: SplitForge Draft workflow --------------------------------------------------

def sf():
    return bpy.context.scene.splitforge


def sf_cuts():
    o = bpy.data.objects.get("GUI_Cube")
    return None if o is None else o.splitforge_stack.cuts


def sf_parts():
    return sorted(o.name for o in bpy.data.objects if o.get("splitforge_source") == "GUI_Cube")


def sf_setup(n_cuts=1):
    def step():
        setup_cube(overlays=True)
        with override():
            cube = bpy.data.objects["GUI_Cube"]
            bpy.context.view_layer.objects.active = cube
            cube.select_set(True)
            sf().show_overlay = True
            sf().export_directory = os.path.join(bpy.app.tempdir, "p1_export") + os.sep
            for axis in ('Z', 'X', 'Y')[:n_cuts]:
                bpy.ops.splitforge.stack_add_plane('EXEC_DEFAULT', True, axis=axis)
            bpy.ops.ed.undo_push(message="gui: setup")
    return named("sf_setup", step)


def sf_overlay(on):
    def step():
        sf().show_overlay = on
        view3d()[1].tag_redraw()
    return named(f"sf_overlay_{on}", step)


def sf_check_overlay_colour():
    off = warm_pixels(STATE["shots"]["overlay_off"])
    on = warm_pixels(STATE["shots"]["overlay_on"])
    log(f"warm pixel fraction overlay off={off:.4f} on={on:.4f}")
    check("cut plane overlay is drawn (orange active cut, warm pixels on >> off)",
          on > 0.01 and on > 3 * off, f"off={off:.4f} on={on:.4f}")


def sf_record(tag):
    def step():
        cut = sf_cuts()[0]
        STATE[tag] = (tuple(cut.origin), tuple(cut.normal))
        log(tag, STATE[tag], modal_ops())
    return named(f"sf_record_{tag}", step)


def sf_check(name, fn):
    def step():
        ok, detail = fn()
        check(name, ok, detail)
    return named("sf_check", step)


def sf_z(tag):
    return STATE[tag][0][2]


def ctrl_key(type_, shift=False):
    """Ctrl(+Shift)+key as a user types it: modifier press, key, modifier release."""
    def step():
        xy = region_center()
        event('LEFT_CTRL', 'PRESS', xy)
        if shift:
            event('LEFT_SHIFT', 'PRESS', xy)
        event(type_, 'PRESS', xy, ctrl=True, shift=shift)
        event(type_, 'RELEASE', xy, ctrl=True, shift=shift)
        if shift:
            event('LEFT_SHIFT', 'RELEASE', xy)
        event('LEFT_CTRL', 'RELEASE', xy)
    return named(f"ctrl_{type_}", step)


ADJUST = "SPLITFORGE_OT_cut_adjust_plane"


def sf_printed_since_invoke(text):
    return named("sf_printed", lambda: check(f"reported '{text}'", printed(text, STATE["out_mark"])))


# Sidebar buttons are found by hovering: a hovered button is the context button of
# ui.copy_python_command_button (operator buttons) / ui.copy_data_path_button (properties).

def ui_region():
    _win, area, _r = view3d()
    return next(r for r in area.regions if r.type == 'UI')


def sf_open_sidebar():
    view3d()[1].spaces.active.show_region_ui = True
    STATE["tab_y"] = 0


def sf_tab_click():
    """Click down the tab column until the SplitForge tab is active (positions depend on DPI)."""
    if ui_region().active_panel_category == "SplitForge":
        return
    STATE["tab_y"] += 15
    r = ui_region()
    xy = (r.x + r.width - 10, r.y + r.height - STATE["tab_y"])
    event('MOUSEMOVE', 'NOTHING', xy)
    event('LEFTMOUSE', 'PRESS', xy)
    event('LEFTMOUSE', 'RELEASE', xy)


def sf_scroll_sidebar():
    r = ui_region()
    event('WHEELDOWNMOUSE', 'PRESS', (r.x + r.width // 2, r.y + r.height // 2))


def sf_no_overlay_errors():
    check("overlay draw handler raised nothing", not printed("overlay draw failed"))


def sf_check_tab():
    check("SplitForge sidebar tab active", ui_region().active_panel_category == "SplitForge",
          ui_region().active_panel_category)


def fast(fn, delay=0.03):
    fn.delay = delay
    return fn


SCAN_COLUMNS = (0.1, 0.45, 0.7, 0.85)  # list checkboxes, wide buttons, side icon columns


def sf_scan(step_px=12):
    """Hover a grid over the sidebar and record which button sits where."""
    steps = [named("scan_reset", lambda: STATE.__setitem__("buttons", {}))]
    for fy in range(20, 2400, step_px):
        for fx in SCAN_COLUMNS:
            def hover(fx=fx, fy=fy):
                r = ui_region()
                if fy >= r.height:
                    return
                event('MOUSEMOVE', 'NOTHING', (r.x + int(r.width * fx), r.y + r.height - fy))

            def record(fx=fx, fy=fy):
                win, area, _r = view3d()
                r = ui_region()
                if fy >= r.height:
                    return
                wm = bpy.context.window_manager
                found = None
                with bpy.context.temp_override(window=win, area=area, region=r, screen=win.screen):
                    for op, kw in ((bpy.ops.ui.copy_python_command_button, {}),
                                   (bpy.ops.ui.copy_data_path_button, {"full_path": True})):
                        if op.poll():
                            wm.clipboard = ""
                            op(**kw)
                            found = wm.clipboard
                            break
                if found:
                    STATE["buttons"].setdefault(found, []).append((r.x + int(r.width * fx), r.y + r.height - fy))
            steps += [fast(named("scan_hover", hover)), fast(named("scan_record", record))]
    steps.append(named("scan_log", lambda: log("buttons", sorted(STATE["buttons"]))))
    return steps


def button_xy(command):
    def xy():
        hits = STATE["buttons"].get(command)
        if not hits:
            raise KeyError(f"button not found: {command}; have {sorted(STATE['buttons'])}")
        # Topmost occurrence (a property may also appear further down, e.g. in the
        # active-cut box), middle of the hits on that button
        top = max(p[1] for p in hits)
        same = sorted(p for p in hits if top - p[1] <= 15)
        return same[len(same) // 2]
    return xy


def press_button(command):
    return [move(button_xy(command)), wait] + click('LEFTMOUSE', button_xy(command)) + [wait]


CUT0_ENABLED = 'bpy.data.objects["GUI_Cube"].splitforge_stack.cuts[0].enabled'
BTN = {
    "add_x": "bpy.ops.splitforge.stack_add_plane(axis='X')",
    "remove": "bpy.ops.splitforge.stack_remove()",
    "distribute": "bpy.ops.splitforge.connector_add_auto()",
    "build": "bpy.ops.splitforge.build()",
    "export": "bpy.ops.splitforge.export_parts()",
    "clear": "bpy.ops.splitforge.clear_build()",
}


def sf_check_buttons(keys):
    def step():
        missing = [k for k in keys if (BTN.get(k, k)) not in STATE["buttons"]]
        check(f"sidebar buttons found: {', '.join(keys)}", not missing, f"missing {missing}")
    return named("sf_check_buttons", step)


def sf_check_build():
    parts = sf_parts()
    check("Build button: 4 parts", len(parts) == 4, parts)
    for n in parts:
        check(f"{n} manifold", is_manifold(bpy.data.objects[n]))
    src = bpy.data.objects["GUI_Cube"]
    check("source hidden, unchanged", src.hide_get() and len(src.data.vertices) == 8)


def sf_check_export():
    d = sf().export_directory
    files = sorted(os.listdir(d)) if os.path.isdir(d) else []
    check("Export button wrote one STL per part (4)",
          len(files) == 4 and files == [n + ".stl" for n in sf_parts()], (d, files))


def sf_select_cube():
    with override():
        cube = bpy.data.objects["GUI_Cube"]
        bpy.context.view_layer.objects.active = cube
        cube.select_set(True)


# --- P2: stroke (curved) cuts, modal Build with progress ---------------------------------

STROKE_OP = "SPLITFORGE_OT_stack_add_stroke"
BUILD_OP = "SPLITFORGE_OT_build"


def p2_setup_monkey(levels=0):
    """Filled Suzanne (eyes = separate shells intersecting the head), front view, overlays on."""
    def step():
        with override():
            for o in list(bpy.data.objects):
                bpy.data.objects.remove(o)
            setup_scene_mm()
            bpy.ops.mesh.primitive_monkey_add('EXEC_DEFAULT', True, size=40.0)
            obj = bpy.context.active_object
            obj.name = "GUI_Monkey"
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.fill_holes(sides=0)
            bpy.ops.mesh.normals_make_consistent(inside=False)
            bpy.ops.object.mode_set(mode='OBJECT')
            if levels:
                m = obj.modifiers.new("subsurf", 'SUBSURF')
                m.levels = levels
                bpy.ops.object.modifier_apply(modifier=m.name)
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            sf().show_overlay = True
            bpy.ops.ed.undo_push(message="gui: monkey")
        set_shading_solid(overlays=True)
        STATE["monkey_faces"] = len(obj.data.polygons)
        STATE["objects_before"] = sorted(o.name for o in bpy.data.objects)
        check("Suzanne manifold", is_manifold(obj))
    return named(f"p2_setup_monkey_{levels}", step)


def monkey():
    return bpy.data.objects.get("GUI_Monkey")


def monkey_cuts():
    return monkey().splitforge_stack.cuts


def monkey_parts():
    return sorted(o.name for o in bpy.data.objects if o.get("splitforge_source") == "GUI_Monkey")


def stroke_state():
    return mod("ops.ops_cut_stroke")


def front_xy(x, z):
    """Window position of a point on the plane y = 0 (front view)."""
    return lambda: world_to_window((x, 0.0, z))


def s_stroke_steps(z0=-7.0, amp=2.5, n=16, shift=False, x0=-28.0, x1=28.0):
    """LMB drag along an S (world x0..x1 at height z0 +- amp), one MOUSEMOVE per step."""
    pts = [(x0 + (x1 - x0) * i / (n - 1), z0 + amp * math.sin(2 * math.pi * i / (n - 1))) for i in range(n)]
    steps = [move(front_xy(*pts[0])), key('LEFTMOUSE', 'PRESS', front_xy(*pts[0]))]
    steps += [move(front_xy(*p)) for p in pts[1:]]
    steps.append(key('LEFTMOUSE', 'RELEASE', front_xy(*pts[-1]), shift=shift))
    return steps


def invoke_with(idname, **props):
    def step():
        STATE["out_mark"] = output_mark()
        event('MOUSEMOVE', 'NOTHING', region_center())
        with override():
            group, name = idname.split(".")
            ret = getattr(getattr(bpy.ops, group), name)('INVOKE_DEFAULT', True, **props)
        check(f"{idname} invoked {props}", ret == {'RUNNING_MODAL'}, ret)
    return named(f"invoke_{idname}", step)


def p2_check_preview():
    st = stroke_state()
    lines = st._PREVIEW["lines"]
    check("stroke preview: stroke + ribbon lines drawn from plain data", len(lines) >= 4, len(lines))
    check("stroke preview: valid stroke (orange, not red)", lines and lines[0][0][1] > 0.3, lines[0][0] if lines else None)
    check("stroke modal running", STROKE_OP in modal_ops(), modal_ops())


def p2_check_committed(n_cuts, points=None):
    def step():
        cuts = monkey_cuts()
        check(f"Enter added a STROKE cut ({n_cuts} cuts)", len(cuts) == n_cuts and cuts[-1].kind == 'STROKE',
              [(c.name, c.kind) for c in cuts])
        if points is not None:
            check(f"stroke has {points} points", len(cuts[-1].points) == points, len(cuts[-1].points))
        else:
            check("stroke stored (prepared, many points)", len(cuts[-1].points) > 20, len(cuts[-1].points))
        check("direction = view direction (+Y)", tuple(round(c, 4) for c in cuts[-1].direction) == (0.0, 1.0, 0.0),
              tuple(cuts[-1].direction))
        st = stroke_state()
        check("modal ended, draw handler removed", STROKE_OP not in modal_ops() and st._HANDLE is None
              and not st._RUNNING, (modal_ops(), st._HANDLE, st._RUNNING))
    return named(f"p2_check_committed_{n_cuts}", step)


def p2_check_unchanged(what, n_cuts):
    def step():
        st = stroke_state()
        check(f"{what}: no cut added", len(monkey_cuts()) == n_cuts, len(monkey_cuts()))
        check(f"{what}: objects unchanged", sorted(o.name for o in bpy.data.objects) == STATE["objects_before"],
              sorted(o.name for o in bpy.data.objects))
        check(f"{what}: modal ended, handler removed",
              STROKE_OP not in modal_ops() and st._HANDLE is None and not st._RUNNING and not st._PREVIEW["lines"],
              (modal_ops(), st._HANDLE, st._RUNNING))
    return named(f"p2_check_unchanged_{what}", step)


def p2_record_uid():
    STATE["stroke_uid"] = monkey_cuts()[0].uid
    STATE["stroke_points"] = [tuple(p.co) for p in monkey_cuts()[0].points]


def p2_check_redrawn():
    cut = monkey_cuts()[0]
    check("Redraw kept the uid", cut.uid == STATE["stroke_uid"], (cut.uid, STATE["stroke_uid"]))
    check("Redraw replaced the points", [tuple(p.co) for p in cut.points] != STATE["stroke_points"])


def p2_check_colour(off, on, what, factor):
    def step():
        a = warm_pixels(STATE["shots"][off])
        b = warm_pixels(STATE["shots"][on])
        log(f"warm pixels {off}={a:.4f} {on}={b:.4f}")
        check(f"{what} visible (warm pixels {on} > {factor} x {off})", b > a + 0.001 and b > factor * a,
              f"{a:.4f} -> {b:.4f}")
    return named(f"p2_colour_{on}", step)


def p2_wait_build(limit=600):
    """Wait (one runner step each) until the modal Build ended."""
    def step():
        if BUILD_OP in modal_ops() and STATE.get("build_wait", 0) < limit:
            STATE["build_wait"] = STATE.get("build_wait", 0) + 1
            STATE["i"] -= 1          # run this step again
            return
        STATE["build_wait"] = 0
        check("modal Build ended", BUILD_OP not in modal_ops(), modal_ops())
    return named("p2_wait_build", step)


def p2_check_built(n_parts):
    def step():
        parts = monkey_parts()
        check(f"Build: {n_parts} parts", len(parts) == n_parts, parts)
        for n in parts:
            check(f"{n} manifold", is_manifold(bpy.data.objects[n]))
        check("source hidden", monkey().hide_get())
        STATE["parts_meshes"] = {n: bpy.data.objects[n].data.name for n in parts}
    return named(f"p2_check_built_{n_parts}", step)


def p2_listen():
    STATE["progress"] = []
    mod("core.progress").listeners.append(lambda done, total, text: STATE["progress"].append((done, total, text)))


def p2_window_shot(name):
    def step():
        if not ARGS.shots:
            return
        path = os.path.join(ARGS.shots, f"{ARGS.scenario}_{ARGS.label}_{name}.png")
        win = view3d()[0]
        with bpy.context.temp_override(window=win, screen=win.screen):
            bpy.ops.screen.screenshot(filepath=path)
        REPORT["screenshots"].append(path)
        STATE["shots"][name] = path
        STATE.setdefault("shot_progress", {})[name] = list(STATE.get("progress", []))
    return named(f"window_shot_{name}", step)


def p2_when_mid_build(action, name, limit=400):
    """Repeat each runner tick until the modal Build has done some but not all steps, then ``action``."""
    def step():
        steps = [p for p in STATE.get("progress", []) if p[2]]
        mid = BUILD_OP in modal_ops() and steps and steps[-1][0] < steps[-1][1]
        if not mid and BUILD_OP in modal_ops() and STATE.get("mid_wait", 0) < limit:
            STATE["mid_wait"] = STATE.get("mid_wait", 0) + 1
            STATE["i"] -= 1
            return
        STATE["mid_wait"] = 0
        check(f"{name}: caught the Build mid-way", mid, steps[-1:] if steps else None)
        if mid:
            action()
    return named(f"mid_build_{name}", step)


def p2_check_progress():
    steps = [p for p in STATE["progress"] if p[2]]
    check("progress steps reported (cut sides, connectors)",
          any("side A" in t for _d, _t, t in steps) and any("connectors" in t for _d, _t, t in steps),
          [t for _d, _t, t in steps][:12])
    check("last step == total", steps and steps[-1][0] == steps[-1][1], steps[-3:])
    during = STATE.get("shot_progress", {}).get("building", [])
    check("window screenshot taken while the build was running (some steps done, not all)",
          during and 0 < during[-1][0] < steps[-1][1], (during[-1:] if during else None, steps[-1:]))


def p2_separate_parts():
    """Lift part A (above the S) so the curved seam faces show in the screenshot."""
    for n in monkey_parts():
        if n.endswith("_A"):
            bpy.data.objects[n].location.z += 10.0


def p2_show_source():
    """Back to the source for more strokes (parts stay); remember the objects present now."""
    with override():
        monkey().hide_set(False)
        bpy.context.view_layer.objects.active = monkey()
    STATE["objects_before"] = sorted(o.name for o in bpy.data.objects)


def p2_check_cancelled_build():
    check("Esc ended the modal Build", BUILD_OP not in modal_ops(), modal_ops())
    parts = monkey_parts()
    check("Esc mid-build: previous parts untouched",
          {n: bpy.data.objects[n].data.name for n in parts} == STATE["parts_meshes"], parts)
    check("reported 'Build cancelled'", printed("Build cancelled", STATE["out_mark"]))
    steps = [p for p in STATE["progress"] if p[2]]
    check("Esc came mid-build (some steps done, not all)", steps and steps[-1][0] < steps[-1][1], steps[-2:])


def p2_add_plane_and_connectors():
    with override():
        bpy.ops.splitforge.stack_add_plane('EXEC_DEFAULT', True, axis='X', offset_mm=3.0)
        for i in range(len(monkey_cuts())):
            monkey().splitforge_stack.active_index = i
            bpy.ops.splitforge.connector_add_auto('EXEC_DEFAULT', True)
        STATE["n_connectors"] = sum(len(c.connectors) for c in monkey_cuts())
    check("Distribute put connectors on the stroke and the plane cut",
          all(len(c.connectors) > 0 for c in monkey_cuts()), [len(c.connectors) for c in monkey_cuts()])


# --- P3: connectors (click placement, all types) ------------------------------------------

CLICK_OP = "SPLITFORGE_OT_connector_add_click"
CLICKS = [(10.0, -4.0, 0.0), (-8.0, 6.0, 0.0), (2.0, 12.0, 0.0)]


def click_state():
    return mod("ops.ops_connector_click")


def p3_setup():
    """40 mm cube with a Z cut (gap 0.4), new connectors CYL_PIN 5 x 10, top view, overlays on."""
    with override():
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o)
        setup_scene_mm()
        bpy.ops.mesh.primitive_cube_add('EXEC_DEFAULT', True, size=40.0)
        cube = bpy.context.active_object
        cube.name = "GUI_Cube"
        cube.select_set(True)
        sf().show_overlay = True
        t = sf().new_connector
        t.kind, t.width_mm, t.length_mm, t.pin_side = 'CYL_PIN', 5.0, 10.0, 'A'
        bpy.ops.splitforge.stack_add_plane('EXEC_DEFAULT', True, axis='Z')
        sf_cuts()[0].gap_mm = 0.4
        bpy.ops.ed.undo_push(message="gui: p3 setup")
    set_shading_solid(overlays=True)
    STATE["objects_before"] = sorted(o.name for o in bpy.data.objects)
    STATE["collections_before"] = sorted(c.name for c in bpy.data.collections)


def p3_conns():
    return sf_cuts()[0].connectors


def p3_check_preview(at):
    def step():
        st = click_state()
        lines = st._PREVIEW["lines"]
        check("click modal running", CLICK_OP in modal_ops(), modal_ops())
        center = sum((Vector(p) for p in lines), Vector()) / max(1, len(lines))
        check(f"preview drawn at the cursor on the seam {at[:2]}", lines and (center - Vector(at)).length < 0.6,
              (len(lines), tuple(round(c, 2) for c in center)))
        check("preview green inside the object", st._PREVIEW["color"] == st.FIT_COLOR, st._PREVIEW["color"])
        check("no preview objects or collections created",
              sorted(o.name for o in bpy.data.objects) == STATE["objects_before"]
              and sorted(c.name for c in bpy.data.collections) == STATE["collections_before"],
              (sorted(o.name for o in bpy.data.objects), sorted(c.name for c in bpy.data.collections)))
    return named("p3_check_preview", step)


def p3_check_count(n, what):
    return named(f"p3_count_{n}", lambda: check(f"{what}: {n} connector(s)", len(p3_conns()) == n,
                                                [(round(c.u, 2), round(c.v, 2), c.pin_side) for c in p3_conns()]))


def p3_check_placed():
    conns = p3_conns()
    ok = len(conns) == 3 and all(abs(c.u - x) < 0.5 and abs(c.v - y) < 0.5 for c, (x, y, _z) in zip(conns, CLICKS))
    check("3 clicks placed 3 connectors at the clicked seam points", ok,
          [(round(c.u, 2), round(c.v, 2)) for c in conns])
    check("S flipped the pin side of the third", [c.pin_side for c in conns] == ['A', 'A', 'B'],
          [c.pin_side for c in conns])


def p3_check_ended():
    st = click_state()
    check("click modal ended, handler removed", CLICK_OP not in modal_ops() and st._HANDLE is None
          and not st._RUNNING, (modal_ops(), st._HANDLE, st._RUNNING))


def p3_build_and_lift(name, lift=14.0):
    def step():
        with override():
            src = bpy.data.objects[name]
            bpy.context.view_layer.objects.active = src
            src.hide_set(False)
            res = mod("cuts.build").build(bpy.context, src)
        parts = [bpy.data.objects[n] for n in res.parts]
        check(f"{name}: Build without warnings", not res.warnings, res.warnings)
        for p in parts:
            check(f"{p.name} manifold", is_manifold(p))
            if p.name.endswith("_A"):
                p.location.z += lift
        STATE.setdefault("built", {})[name] = [p.name for p in parts]
    return named(f"p3_build_{name}", step)


def p3_check_dowel(layout):
    """The bar's dowel part sits where the layout puts it (its connector is at u = 77 on the Z cut, lifted A)."""
    def step():
        d = bpy.data.objects["GUI_Bar_Dowel_1"]
        pts = [d.matrix_world @ v.co for v in d.data.vertices]
        lo = Vector([min(p[i] for p in pts) for i in range(3)])
        hi = Vector([max(p[i] for p in pts) for i in range(3)])
        center, size = (lo + hi) / 2, hi - lo
        if layout == 'ASSEMBLED':
            ok = (center - Vector((77.0, 0.0, 0.0))).length < 0.01 and abs(size.z - 14.0) < 0.05
        elif layout == 'UPRIGHT':
            ok = abs(size.z - 14.0) < 0.05 and abs(lo.z + 15.0) < 1e-3 and lo.x > 90.0
        else:
            ok = abs(size.x - 14.0) < 0.05 and abs(lo.z + 15.0) < 1e-3 and lo.x > 90.0
        check(f"dowel layout {layout}: placed", ok, (tuple(round(c, 2) for c in center), tuple(round(c, 2) for c in size)))
    return step


def p3_setup_types():
    """A 180 x 30 x 30 bar, Z cut, one connector of every type along it; dowels lie beside it."""
    with override():
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o)
        setup_scene_mm()
        bpy.ops.mesh.primitive_cube_add('EXEC_DEFAULT', True, size=1.0)
        bar = bpy.context.active_object
        bar.name = "GUI_Bar"
        bar.data.transform(mathutils.Matrix.Diagonal((180.0, 30.0, 30.0, 1.0)))
        knob = bpy.data.objects.new("GUI_Knob", bpy.data.meshes.new("GUI_Knob"))
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=1.0, radius2=0.6, depth=2.0)
        bm.to_mesh(knob.data)
        bm.free()
        bpy.context.scene.collection.objects.link(knob)
        knob.location = (0.0, 60.0, 0.0)
        bpy.context.view_layer.objects.active = bar
        bar.select_set(True)
        sf().show_overlay = True
        bpy.ops.splitforge.stack_add_plane('EXEC_DEFAULT', True, axis='Z')
        cut = bar.splitforge_stack.cuts[0]
        cut.gap_mm = 0.4
        kinds = ['CYL_PIN', 'RECT_TENON', 'DOVETAIL', 'SNAP_PIN', 'SNAP_TENON', 'SNAP_DOVETAIL', 'CUSTOM', 'DOWEL']
        for i, kind in enumerate(kinds):
            t = sf().new_connector
            t.kind, t.width_mm, t.height_mm, t.length_mm = kind, 8.0, 6.0, 14.0
            t.taper_pct, t.chamfer_mm, t.custom_object = 30.0, 0.6 if kind in ('CYL_PIN', 'DOWEL') else 0.0, knob
            bpy.ops.splitforge.connector_add('EXEC_DEFAULT', True, u=-77.0 + 22.0 * i, v=0.0)
        bpy.ops.ed.undo_push(message="gui: types")
    set_shading_solid(overlays=True)


SCENARIOS = {
    "p1_adjust_plane": (
        [sf_setup(1), set_oblique_view(1.6), sf_overlay(False), wait, screenshot("overlay_off"),
         sf_overlay(True), wait, wait, screenshot("overlay_on"), sf_check_overlay_colour, sf_record("start")]
        # Mouse drag up the screen moves the Z plane up; wheel adds exactly 1 mm; LMB confirms
        + [invoke("splitforge.cut_adjust_plane")] + drag(steps=4, dy=25)
        + [wait, sf_record("dragged"),
           sf_check("drag moved the plane up along its normal",
                    lambda: (sf_z("dragged") > 0.5 and STATE["dragged"][1] == STATE["start"][1],
                             (STATE["start"], STATE["dragged"]))),
           screenshot("dragging"), key('WHEELUPMOUSE'), wait, sf_record("wheel"),
           sf_check("wheel step 1 mm", lambda: (abs(sf_z("wheel") - sf_z("dragged") - 1.0) < 1e-4,
                                                (sf_z("dragged"), sf_z("wheel"))))]
        + click('LEFTMOUSE', pos(0, 100))
        + [wait, check_running(ADJUST, False), sf_printed_since_invoke("Cut plane adjusted."),
           sf_record("confirmed"),
           sf_check("LMB kept the plane", lambda: (STATE["confirmed"] == STATE["wheel"], STATE["confirmed"]))]
        # Real Ctrl+Z / Ctrl+Shift+Z: one undo step per confirmed adjustment
        + [ctrl_key('Z'), wait, sf_record("undone"),
           sf_check("Ctrl+Z restored the plane", lambda: (STATE["undone"] == STATE["start"], STATE["undone"])),
           ctrl_key('Z', shift=True), wait, sf_record("redone"),
           sf_check("Ctrl+Shift+Z redid it", lambda: (STATE["redone"] == STATE["confirmed"], STATE["redone"]))]
        # X re-orients, Esc restores everything
        + [invoke("splitforge.cut_adjust_plane")] + drag(steps=2, dy=-30)
        + [key('X'), wait, sf_record("x_axis"),
           sf_check("X aligned the normal with world X",
                    lambda: (tuple(round(c, 5) for c in STATE["x_axis"][1]) == (1.0, 0.0, 0.0), STATE["x_axis"])),
           key('ESC'), wait, check_running(ADJUST, False), sf_record("escaped"),
           sf_check("Esc restored the plane", lambda: (STATE["escaped"] == STATE["redone"], STATE["escaped"])),
           sf_printed_since_invoke("Adjust cut plane cancelled.")]
        # ed.undo/redo while the modal runs (undo-safety regression), then file load -> cancel()
        + [invoke("splitforge.cut_adjust_plane"), key('WHEELUPMOUSE'), wait]
        + [undo, key('WHEELUPMOUSE'), wait, redo, key('WHEELDOWNMOUSE'), wait] * 4
        + [check_running(ADJUST), key('ESC'), wait, check_running(ADJUST, False)]
        + [invoke("splitforge.cut_adjust_plane"), key('WHEELUPMOUSE'), wait, load_homefile, wait,
           check_running(ADJUST, False), sf_printed_since_invoke("Adjust cut plane cancelled."),
           sf_no_overlay_errors]
    ),
    "p1_panel": (
        [sf_setup(1), set_oblique_view(1.8), sf_open_sidebar, wait] + [sf_tab_click, wait] * 40
        + [sf_check_tab] + sf_scan()
        + [sf_check_buttons(["add_x", "remove", "distribute", "build", CUT0_ENABLED]),
           screenshot("panel_start")]
        # Add X with the sidebar button, undo/redo with real key events
        + press_button(BTN["add_x"])
        + [sf_check("X button added a cut", lambda: (len(sf_cuts()) == 2, [c.name for c in sf_cuts()])),
           ctrl_key('Z'), wait,
           sf_check("Ctrl+Z removed it", lambda: (len(sf_cuts()) == 1, len(sf_cuts()))),
           ctrl_key('Z', shift=True), wait,
           sf_check("Ctrl+Shift+Z re-added it", lambda: (len(sf_cuts()) == 2, len(sf_cuts())))]
        # Toggle the first cut off and on with its list checkbox
        + press_button(CUT0_ENABLED)
        + [sf_check("checkbox disabled cut 0", lambda: (not sf_cuts()[0].enabled, sf_cuts()[0].enabled))]
        + press_button(CUT0_ENABLED)
        + [sf_check("checkbox enabled cut 0", lambda: (sf_cuts()[0].enabled, sf_cuts()[0].enabled))]
        # Remove the active (X) cut, add it again, distribute connectors on it
        + press_button(BTN["remove"])
        + [sf_check("remove button removed the active cut", lambda: ([c.name for c in sf_cuts()] == ["Cut Z"],
                                                                      [c.name for c in sf_cuts()]))]
        + press_button(BTN["add_x"]) + press_button(BTN["distribute"])
        + [sf_check("Distribute added 2 connectors per seam region (Z splits the X seam: 4)",
                    lambda: (len(sf_cuts()[1].connectors) == 4, len(sf_cuts()[1].connectors)))]
        # The connector list and the new-connector box moved the Build box down: scroll, find the buttons again
        + [sf_scroll_sidebar, wait] * 8
        + sf_scan() + [sf_check_buttons(["build"])]
        + press_button(BTN["build"]) + [wait, sf_check_build, screenshot("panel_built")]
        # The panel is now taller than the sidebar: scroll it with the wheel, find the buttons again
        + [sf_scroll_sidebar, wait] * 12
        + sf_scan() + [sf_check_buttons(["export", "clear"])]
        + press_button(BTN["export"]) + [sf_check_export]
        + press_button(BTN["clear"])
        + [sf_check("Clear removed the parts and shows the source",
                    lambda: (not sf_parts() and not bpy.data.objects["GUI_Cube"].hide_get(), sf_parts())),
           sf_no_overlay_errors]
    ),
    "p2_stroke": (
        [p2_setup_monkey(0), set_oblique_view(1.5), wait, screenshot("before"), set_view('FRONT', 1.3), wait]
        # Draw an S through the muzzle (below the eyes) in the front view; the ribbon preview is
        # shown from an oblique view (navigation while the modal waits for Enter), then Enter
        + [invoke("splitforge.stack_add_stroke"), wait] + s_stroke_steps()
        + [wait, p2_check_preview, screenshot("stroke_front"), set_oblique_view(1.5), wait,
           screenshot("stroke_preview"),
           p2_check_colour("before", "stroke_preview", "stroke + ribbon preview", 1.3),
           key('RET'), wait, p2_check_committed(1), wait, screenshot("committed"),
           p2_check_colour("before", "committed", "stroke cut overlay (ribbon surface)", 2.0),
           set_view('FRONT', 1.3), wait]
        # Real Ctrl+Z / Ctrl+Shift+Z: one undo step per stroke cut
        + [ctrl_key('Z'), wait,
           named("undo_removed", lambda: check("Ctrl+Z removed the stroke cut", len(monkey_cuts()) == 0,
                                               len(monkey_cuts()))),
           ctrl_key('Z', shift=True), wait,
           named("redo_added", lambda: check("Ctrl+Shift+Z re-added it", len(monkey_cuts()) == 1,
                                             len(monkey_cuts())))]
        # Build (modal, progress): 2 manifold parts, the eyes stay whole (info)
        + [invoke("splitforge.build"), wait, p2_wait_build(), wait, p2_check_built(2),
           named("shell_info", lambda: check("info: eyes not crossed stay whole",
                                             printed("2 separate shell(s)", STATE["out_mark"]))),
           set_oblique_view(1.6), p2_separate_parts, sf_overlay(False), wait, screenshot("built_apart"),
           sf_overlay(True), set_view('FRONT', 1.3)]
        # Esc / RMB leave nothing
        + [p2_show_source,
           invoke("splitforge.stack_add_stroke"), wait] + s_stroke_steps(z0=-4.0)
        + [wait, key('ESC'), wait, p2_check_unchanged("Esc", 1)]
        + [invoke("splitforge.stack_add_stroke"), wait] + s_stroke_steps(z0=-4.0)
        + [wait] + click('RIGHTMOUSE', front_xy(0.0, 25.0)) + [wait, p2_check_unchanged("RMB", 1)]
        # Shift at release: straight axis line (2 points, horizontal in the front view)
        + [invoke("splitforge.stack_add_stroke"), wait] + s_stroke_steps(z0=2.0, amp=1.5, shift=True)
        + [wait, key('RET'), wait, p2_check_committed(2, points=2),
           named("shift_level", lambda: check("Shift snapped the line level (normal = Z)",
                                              abs(abs(monkey_cuts()[1].normal[2]) - 1.0) < 1e-4,
                                              tuple(monkey_cuts()[1].normal)))]
        # Redraw the first stroke (same uid, new points)
        + [named("active0", lambda: setattr(monkey().splitforge_stack, "active_index", 0)), p2_record_uid,
           named("redraw", lambda: invoke_with("splitforge.stack_add_stroke",
                                               replace_uid=STATE["stroke_uid"])())]
        + [wait] + s_stroke_steps(z0=-9.0, amp=1.5)
        + [wait, key('RET'), wait, p2_check_redrawn, screenshot("redrawn")]
        # File load while drawing -> cancel() removes the handler
        + [invoke("splitforge.stack_add_stroke"), wait] + s_stroke_steps(z0=-4.0)
        + [wait, load_homefile, wait,
           named("load_cancel", lambda: check("file load: stroke modal cancelled, handler removed",
                                              STROKE_OP not in modal_ops() and stroke_state()._HANDLE is None
                                              and not stroke_state()._RUNNING,
                                              (modal_ops(), stroke_state()._HANDLE))),
           sf_no_overlay_errors]
    ),
    "p2_build_progress": (
        [p2_setup_monkey(4), set_view('FRONT', 1.3), wait]
        + [invoke("splitforge.stack_add_stroke"), wait] + s_stroke_steps(z0=2.0, amp=3.0)
        + [wait, key('RET'), wait, p2_check_committed(1), p2_add_plane_and_connectors, p2_listen,
           set_oblique_view(1.4)]
        # Modal Build with progress: a full-window screenshot while it runs (status bar text)
        + [invoke("splitforge.build"), p2_when_mid_build(p2_window_shot("building"), "screenshot"),
           p2_wait_build(), wait, p2_check_built(4), p2_check_progress, p2_window_shot("built")]
        # Esc in the middle of a rebuild keeps the previous parts
        + [named("relisten", lambda: STATE.__setitem__("progress", [])),
           named("change_gap", lambda: setattr(monkey_cuts()[0], "gap_mm", 0.5)),
           invoke("splitforge.build"), p2_when_mid_build(key('ESC'), "Esc"), wait, p2_wait_build(), wait,
           p2_check_cancelled_build, sf_no_overlay_errors]
    ),
    "p3_connector_click": (
        [p3_setup, set_view('TOP', 1.5), wait, screenshot("before"),
         invoke("splitforge.connector_add_click"), move(lambda: world_to_window(CLICKS[0])), wait,
         p3_check_preview(CLICKS[0]), screenshot("preview")]
        + click('LEFTMOUSE', lambda: world_to_window(CLICKS[0])) + [wait, p3_check_count(1, "first click")]
        + [move(lambda: world_to_window(CLICKS[1])), wait] + click('LEFTMOUSE', lambda: world_to_window(CLICKS[1]))
        + [wait, key('S'), wait, move(lambda: world_to_window(CLICKS[2])), wait]
        + click('LEFTMOUSE', lambda: world_to_window(CLICKS[2]))
        + [wait, p3_check_placed, screenshot("placed")]
        # A click outside the object places nothing
        + click('LEFTMOUSE', lambda: world_to_window((30.0, 0.0, 0.0))) + [wait, p3_check_count(3, "outside click")]
        # Real Ctrl+Z / Ctrl+Shift+Z while placing: one connector per step
        + [ctrl_key('Z'), wait, p3_check_count(2, "Ctrl+Z"), ctrl_key('Z'), wait, p3_check_count(1, "Ctrl+Z"),
           ctrl_key('Z'), wait, p3_check_count(0, "Ctrl+Z"),
           ctrl_key('Z', shift=True), wait, ctrl_key('Z', shift=True), wait, ctrl_key('Z', shift=True), wait,
           p3_check_count(3, "Ctrl+Shift+Z"), p3_check_placed, check_running(CLICK_OP)]
        + [key('ESC'), wait, p3_check_ended]
        # After the modal: still one undo step per click
        + [ctrl_key('Z'), wait, p3_check_count(2, "Ctrl+Z after Esc"), ctrl_key('Z', shift=True), wait,
           p3_check_count(3, "Ctrl+Shift+Z after Esc")]
        # Build: pins and sockets where clicked
        + [p3_build_and_lift("GUI_Cube", lift=22.0), set_oblique_view(1.2), sf_overlay(False), wait,
           screenshot("built"), named("view_below_cube", lambda: setattr(
               view3d()[1].spaces.active.region_3d, "view_rotation",
               Euler((math.radians(105), 0.0, math.radians(25))).to_quaternion())), wait,
           screenshot("built_pins"), sf_overlay(True)]
        # File load while placing -> cancel()
        + [named("show_src", lambda: (bpy.data.objects["GUI_Cube"].hide_set(False),
                                      setattr(bpy.context.view_layer.objects, "active", bpy.data.objects["GUI_Cube"]))),
           set_view('TOP', 1.5), invoke("splitforge.connector_add_click"), move(pos(10)), wait, load_homefile, wait,
           p3_check_ended, sf_no_overlay_errors]
    ),
    "p3_connector_types": (
        [p3_setup_types, set_oblique_view(1.1), wait, screenshot("records"),
         p3_build_and_lift("GUI_Bar", lift=26.0),
         named("types_parts", lambda: check("A, B and one dowel part", sorted(STATE["built"]["GUI_Bar"]) ==
                                            ["GUI_Bar_A", "GUI_Bar_B", "GUI_Bar_Dowel_1"], STATE["built"]["GUI_Bar"])),
         sf_overlay(False), wait, screenshot("built"),
         named("view_below", lambda: setattr(view3d()[1].spaces.active.region_3d, "view_rotation",
                                             Euler((math.radians(115), 0.0, math.radians(20))).to_quaternion())),
         named("zoom", lambda: setattr(view3d()[1].spaces.active.region_3d, "view_distance",
                                       view3d()[1].spaces.active.region_3d.view_distance * 0.6)),
         wait, screenshot("pins_from_below"),
         # Dowel layouts: the dowel moves into its sockets (assembly preview), upright, and back flat
         named("dowel_assembled", lambda: sf().__setattr__("dowel_layout", 'ASSEMBLED')), set_oblique_view(0.9),
         named("check_dowel_assembled", p3_check_dowel('ASSEMBLED')), wait, screenshot("dowel_assembled"),
         named("dowel_upright", lambda: sf().__setattr__("dowel_layout", 'UPRIGHT')),
         named("check_dowel_upright", p3_check_dowel('UPRIGHT')), wait, screenshot("dowel_upright"),
         named("dowel_flat", lambda: sf().__setattr__("dowel_layout", 'FLAT')), named("check_dowel_flat", p3_check_dowel('FLAT'))]
    ),
}


def _flatten(steps):
    out = []
    for s in steps:
        if isinstance(s, (list, tuple)):
            out.extend(_flatten(s))
        else:
            out.append(s)
    return out


def close_splash():
    """--factory-startup shows the splash screen, which would swallow the first events."""
    win, area, _region = view3d()
    win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=area.x + 5, y=area.y + 5)
    win.event_simulate(type='ESC', value='PRESS', x=area.x + 5, y=area.y + 5)
    win.event_simulate(type='ESC', value='RELEASE', x=area.x + 5, y=area.y + 5)


STEPS = [close_splash, wait] + _flatten(SCENARIOS[ARGS.scenario])
STATE["i"] = 0


def tick():
    if STATE["i"] >= len(STEPS):
        REPORT["completed"] = True
        write_report()
        sys.stdout = STDOUT.orig
        bpy.ops.wm.quit_blender()
        return None
    step = STEPS[STATE["i"]]
    STATE["i"] += 1
    try:
        step()
    except Exception:
        check(f"step {step.__name__} raised", False, traceback.format_exc())
    delay = getattr(step, "delay", None)
    if delay is None:
        write_report()  # keep a report on disk even if a later step crashes Blender
    return delay or 0.2


bpy.app.timers.register(tick, first_interval=2.0, persistent=True)
