# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SnapSplit.
"""GUI scenario runner for modal operators (started by ``tests/run_tests.py --gui``).

blender --factory-startup --enable-event-simulate --python gui_runner.py -- \
    --repo <dir containing snapsplit/> --scenario NAME --out <json> --shots <dir> --label <str>

Modal operators only run in a real window, so these scenarios start a GUI Blender
(with simulated input, real input is blocked) and drive it step by step from a
persistent ``bpy.app.timers`` callback: one simulated event per step, so Blender
processes every event (and mouse_prev) like real input. Each scenario records checks
in a JSON report, saves viewport screenshots to ``--shots`` and quits Blender.
A crash (no report / non-zero exit code / blender.crash.txt) is a FAIL in run_tests.py.

Units follow the harness convention (Metric, Millimeters, Unit Scale 1.0, 1 BU = 1 mm
for the add-on, see docs/MANUAL_QA.md): the cube is 40 BU.

Scenarios
    qa1_preview_color  QA-1: split preview planes are orange in Solid view
                       (screenshot pixel check against preview off), no orphan meshes
    qa2_adjust         QA-2: mouse drag moves offset + plane; LMB and Enter confirm
                       (offset kept, modal ended); Esc cancels and cleans up
    qa3_connectors     QA-3: click placement on a Z-split cube: preview follows the cursor,
                       LMB places at the cursor on the seam (pin side +, socket side -),
                       S swaps pin/socket, RMB cancels; both parts manifold
    qa4_freehand       QA-4: LMB stroke across a filled Suzanne (front view), Shift-release
                       axis snap, Enter -> 2 manifold parts with the original volume;
                       Esc exits without changes; file load -> cancel()
    adjust_undo_wheel  ed.undo/redo while Adjust Split Axis runs, wheel events write
                       the offset (crashed with EXCEPTION_ACCESS_VIOLATION before
                       the undo-safety fix)
    conn_undo          ed.undo/redo while Place Connectors (click) runs; the preview is
                       gone after undo, rebuilt on the next mouse move, cleaned up on Esc
    load_adjust        file load while Adjust Split Axis runs -> cancel() ran (report
                       printed, X-Ray released)
    load_conn          file load while Place Connectors (click) runs -> cancel() ran
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
from mathutils import Euler, Vector

REPO_NAME = "snapsplit_gui_test"
ADDON = f"bl_ext.{REPO_NAME}.snapsplit"

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser(prog="gui_runner.py")
ap.add_argument("--repo", required=True)
ap.add_argument("--scenario", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--shots", default="")
ap.add_argument("--label", default="")
ARGS = ap.parse_args(argv)

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


def printed(text):
    return text in "".join(STDOUT.lines)


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


def set_shading_solid():
    space = view3d()[1].spaces.active
    space.shading.type = 'SOLID'
    space.shading.color_type = 'MATERIAL'
    space.overlay.show_overlays = False


# --- scene helpers ------------------------------------------------------------

STATE = {"shots": {}}


def preview_objects():
    planes = mod("ops_split").PREVIEW_PLANE_PREFIX
    return [o.name for o in bpy.data.objects
            if o.name.startswith(planes) or o.name.startswith("SnapSplit_Preview")]


def orphan_preview_meshes():
    planes = mod("ops_split").PREVIEW_PLANE_PREFIX
    return [m.name for m in bpy.data.meshes
            if m.users == 0 and (m.name.startswith(planes) or m.name.startswith("SnapSplit_Preview"))]


def xray_reasons():
    return sorted(r for s in mod("utils")._XRAY_STATES.values() for r in s["reasons"])


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
    units.scale_length = 1.0


def setup_cube():
    with override():
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o)
        setup_scene_mm()
        bpy.ops.mesh.primitive_cube_add('EXEC_DEFAULT', True, size=40.0)
        bpy.context.active_object.name = "GUI_Cube"
        props = bpy.context.scene.snapsplit
        props.split_axis = 'Z'
        props.parts_count = 2
        props.split_offset_mm = 0.0
    set_shading_solid()


def split_into_parts():
    with override():
        cube = bpy.data.objects["GUI_Cube"]
        bpy.context.view_layer.objects.active = cube
        cube.select_set(True)
        bpy.context.scene.snapsplit.connector_type = 'CYL_PIN'
        bpy.ops.snapsplit.planar_split('EXEC_DEFAULT', True)
        parts = [o for o in bpy.context.selected_objects if o.type == 'MESH']
        for o in parts:
            o.select_set(True)
        bpy.context.view_layer.objects.active = parts[0]
    STATE["parts"] = sorted(o.name for o in parts)
    check("two parts", len(parts) == 2, STATE["parts"])


def push_settings_change():
    """Two undo steps that differ only in scene.snapsplit (undo re-allocates the group)."""
    with override():
        bpy.ops.ed.undo_push(message="gui: base")
        bpy.context.scene.snapsplit.parts_count = 3
        bpy.ops.ed.undo_push(message="gui: settings")


def invoke(idname):
    def step():
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
    STATE["xray_before_load"] = xray_reasons()
    with override():
        bpy.ops.wm.read_homefile()
    log("read_homefile; X-Ray reasons before:", STATE["xray_before_load"])


def check_running(idname, expect=True):
    return named(f"check_running_{idname}_{expect}", lambda: check(
        f"{idname} {'running' if expect else 'ended'}",
        (idname in modal_ops()) == expect, modal_ops()))


def check_clean(what):
    def step():
        check(f"{what}: modal ended", not modal_ops(), modal_ops())
        check(f"{what}: no preview objects left", not preview_objects(), preview_objects())
        check(f"{what}: no orphan preview meshes", not orphan_preview_meshes(), orphan_preview_meshes())
        check(f"{what}: X-Ray released", not xray_reasons(), xray_reasons())
    return named(f"check_clean_{what}", step)


def check_cancel_ran(message, reason):
    def step():
        check(f"cancel(): X-Ray reason '{reason}' held before the load",
              reason in STATE.get("xray_before_load", []), STATE.get("xray_before_load"))
        check(f"cancel(): reported '{message}'", printed(message))
    return named("check_cancel_ran", step)


# --- QA-1: preview colour -----------------------------------------------------

def qa1_select_cube():
    cube = bpy.data.objects["GUI_Cube"]
    bpy.context.view_layer.objects.active = cube
    cube.select_set(True)


def qa1_preview(on):
    def step():
        with override():
            props = bpy.context.scene.snapsplit
            props.split_axis = 'X'
            props.parts_count = 3
            props.show_split_preview = on
    return named(f"preview_{on}", step)


def qa1_check_colour():
    off = warm_pixels(STATE["shots"]["preview_off"])
    on = warm_pixels(STATE["shots"]["preview_on"])
    log(f"warm pixel fraction off={off:.4f} on={on:.4f}")
    check("preview planes are orange in Solid view (warm pixels on >> off)",
          on > 0.01 and on > 5 * off, f"off={off:.4f} on={on:.4f}")
    mat = bpy.data.materials.get(mod("ops_split").PREVIEW_MAT_NAME)
    check("material diffuse_color orange", mat and mat.diffuse_color[0] > 0.9 and mat.diffuse_color[2] < 0.1,
          tuple(mat.diffuse_color) if mat else None)


def qa1_toggle_many():
    with override():
        props = bpy.context.scene.snapsplit
        for i in range(6):
            props.show_split_preview = True
            props.split_offset_mm = float(i)
            props.show_split_preview = False
    check("no orphan preview meshes after toggles", not orphan_preview_meshes(), orphan_preview_meshes())


# --- QA-2: Adjust Split Axis -------------------------------------------------

def plane_z():
    o = bpy.data.objects.get(mod("ops_split").PREVIEW_PLANE_PREFIX + "GUI_Cube_1")
    return None if o is None else o.matrix_world.translation.z


def record_adjust(tag):
    def step():
        STATE[tag] = (bpy.context.scene.snapsplit.split_offset_mm, plane_z())
        log(tag, STATE[tag], modal_ops())
    return named(f"record_{tag}", step)


def check_drag_moved(before, after):
    def step():
        (o0, z0), (o1, z1) = STATE[before], STATE[after]
        check(f"drag changed the offset ({before}->{after})", abs(o1 - o0) > 0.5, (o0, o1))
        check(f"plane followed the offset ({after})", z1 is not None and abs(z1 - o1) < 1e-3, (o1, z1))
        check(f"plane moved ({before}->{after})", z0 is not None and z1 is not None and abs(z1 - z0) > 0.5,
              (z0, z1))
    return named("check_drag_moved", step)


def check_confirmed(tag_before):
    def step():
        o_before = STATE[tag_before][0]
        o_now = bpy.context.scene.snapsplit.split_offset_mm
        check(f"confirm kept the offset ({tag_before})", abs(o_now - o_before) < 1e-6 and o_now != 0.0,
              (o_before, o_now))
        check(f"confirm ended the modal ({tag_before})",
              'SNAPSPLIT_OT_adjust_split_axis' not in modal_ops(), modal_ops())
        check("reported 'Split axis adjusted.'", printed("Split axis adjusted."))
    return named("check_confirmed", step)


def adjust_preview(on):
    def step():
        with override():
            bpy.context.scene.snapsplit.show_split_preview = on
            bpy.context.scene.snapsplit.split_offset_mm = 0.0
    return named(f"adjust_preview_{on}", step)


def drag(steps=4, dy=25):
    """One MOUSEMOVE per step, moving up from the region centre."""
    out = [move(region_center)]
    for i in range(1, steps + 1):
        out.append(move(lambda i=i: (region_center()[0], region_center()[1] + i * dy)))
    return out


def check_orphans_zero(tag):
    return named(f"orphans_{tag}", lambda: check(f"no orphan preview meshes ({tag})",
                                                 not orphan_preview_meshes(), orphan_preview_meshes()))


# --- QA-3: click connectors ----------------------------------------------------

SEAM_Z = 0.0
P1 = (-8.0, 5.0, SEAM_Z)
P2 = (8.0, -6.0, SEAM_Z)


def conn_record(tag):
    def step():
        STATE[tag] = {n: volume(bpy.data.objects[n]) for n in STATE["parts"]}
        log(tag, STATE[tag])
    return named(f"conn_record_{tag}", step)


def conn_check_preview_at(point):
    def step():
        o = bpy.data.objects.get("SnapSplit_Preview_Conn")
        check(f"preview exists at {point}", o is not None, preview_objects())
        if o is None:
            return
        # Expected: mouse ray hits the seam plane at the target point
        x, y = world_to_window(point)
        origin, direction = window_ray(x, y)
        t = (SEAM_Z - origin.z) / direction.z
        hit = origin + direction * t
        loc = o.matrix_world.translation
        check(f"preview follows the cursor ({point})",
              abs(loc.x - hit.x) < 0.5 and abs(loc.y - hit.y) < 0.5, (tuple(loc), tuple(hit)))
        STATE.setdefault("preview_xy", []).append((loc.x, loc.y))
    return named("conn_check_preview_at", step)


def conn_check_preview_moved():
    xy = STATE.get("preview_xy", [])
    check("preview position changed with the mouse",
          len(xy) >= 2 and math.dist(xy[-1], xy[-2]) > 5.0, xy)


def conn_check_placed(before, after, point, expect_gainer=None):
    def step():
        v0, v1 = STATE[before], STATE[after]
        delta = {n: v1[n] - v0[n] for n in v0}
        gainer = [n for n, d in delta.items() if d > 1e-3]
        loser = [n for n, d in delta.items() if d < -1e-3]
        check(f"placement at {point}: pin side +, socket side -", len(gainer) == 1 and len(loser) == 1, delta)
        if expect_gainer == "other" and gainer:
            check("S swapped pin/socket side", gainer[0] != STATE.get("first_gainer"),
                  (gainer[0], STATE.get("first_gainer")))
        if gainer:
            STATE.setdefault("first_gainer", gainer[0])
            # Vertices of the pin side that protrude past the seam are the new pin
            obj = bpy.data.objects[gainer[0]]
            home = 1.0 if (obj.matrix_world @ Vector(obj.bound_box[0])).z + \
                (obj.matrix_world @ Vector(obj.bound_box[6])).z > 0 else -1.0
            verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
            pin = [v for v in verts if v.z * home < -1e-3]
            near = [v for v in pin if math.dist((v.x, v.y), point[:2]) < 6.0]
            check(f"pin placed at the cursor location {point[:2]}", near,
                  f"{len(pin)} protruding verts, {len(near)} near the target")
        for n in STATE["parts"]:
            check(f"{n} manifold after placement", is_manifold(bpy.data.objects[n]))
    return named("conn_check_placed", step)


# --- QA-4: freehand ------------------------------------------------------------

def setup_suzanne():
    with override():
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o)
        setup_scene_mm()
        bpy.ops.mesh.primitive_monkey_add('EXEC_DEFAULT', True, size=40.0)
        obj = bpy.context.active_object
        obj.name = "GUI_Suzanne"
        # Keep only the head shell: Freehand Cut (stage B3) refuses separate shells the
        # cut does not cross, and Suzanne's eyes are separate shells.
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        islands, seen = [], set()
        for v in bm.verts:
            if v.index in seen:
                continue
            stack, island = [v], []
            seen.add(v.index)
            while stack:
                cur = stack.pop()
                island.append(cur)
                for e in cur.link_edges:
                    other = e.other_vert(cur)
                    if other.index not in seen:
                        seen.add(other.index)
                        stack.append(other)
            islands.append(island)
        islands.sort(key=len)
        bmesh.ops.delete(bm, geom=[v for island in islands[:-1] for v in island], context='VERTS')
        bm.to_mesh(obj.data)
        bm.free()
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.fill_holes(sides=0)
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode='OBJECT')
    set_shading_solid()
    STATE["suzanne_volume"] = volume(obj)
    STATE["objects_before"] = sorted(o.name for o in bpy.data.objects)
    check("Suzanne manifold", is_manifold(obj))


def fh_point(fx, fz):
    """Window position of a point on the Suzanne front plane (fractions of 40 BU)."""
    return lambda: world_to_window((fx * 20.0, -30.0, fz * 20.0))


def fh_stroke(shift_release):
    # Slightly slanted line through the muzzle (below eyes and ears); Shift snaps it level
    z0, z1 = -0.30, -0.42
    steps = [key('LEFTMOUSE', 'PRESS', fh_point(-1.2, z0))]
    n = 10
    for i in range(1, n + 1):
        f = i / n
        steps.append(move(fh_point(-1.2 + 2.4 * f, z0 + (z1 - z0) * f)))
    steps.append(key('LEFTMOUSE', 'RELEASE', fh_point(1.2, z1), shift=shift_release))
    return steps


def fh_active():
    ops = mod("ops_freehand")._ACTIVE_OPERATORS
    return ops[0] if ops else None


def fh_check_preview(expect_snap=True):
    op = fh_active()
    check("freehand preview built", op is not None and op._selected_count > 0,
          None if op is None else op._selected_count)
    if expect_snap and op is not None and op._plane_normal is not None:
        n = op._plane_normal
        check("Shift-release snapped the plane to an axis", max(abs(n.x), abs(n.y), abs(n.z)) > 0.999,
              tuple(n))


def fh_check_committed():
    parts = [o for o in bpy.data.objects if o.name.startswith("GUI_Suzanne_Freehand_")]
    check("Enter committed 2 parts", len(parts) == 2, [o.name for o in parts])
    for o in parts:
        check(f"{o.name} manifold", is_manifold(o))
    total = sum(volume(o) for o in parts)
    v0 = STATE["suzanne_volume"]
    check("part volumes sum to the original", abs(total - v0) <= 0.01 * v0, (total, v0))
    check("freehand modal ended", fh_active() is None and not modal_ops(), modal_ops())


def fh_check_unchanged(what):
    def step():
        check(f"{what}: objects unchanged", sorted(o.name for o in bpy.data.objects) == STATE["objects_before"],
              sorted(o.name for o in bpy.data.objects))
        check(f"{what}: freehand modal ended", fh_active() is None and not modal_ops(), modal_ops())
    return named(f"fh_unchanged_{what}", step)


def fh_load_check():
    check("file load: freehand cancel() cleaned up", fh_active() is None and not modal_ops(),
          (fh_active(), modal_ops()))


# --- undo / file-load scenarios ---------------------------------------------------

OFFSETS = []


def record_offset():
    OFFSETS.append(bpy.context.scene.snapsplit.split_offset_mm)
    log("offset", OFFSETS[-1], modal_ops())


def check_offsets_followed_wheel():
    check("live offset followed the wheel", len(set(OFFSETS)) > 1 and any(OFFSETS), OFFSETS)


def conn_undo_step():
    undo()
    check("preview gone right after undo", not preview_objects(), preview_objects())


def check_connectors_preview_rebuilt():
    check("connectors running", 'SNAPSPLIT_OT_place_connectors_click' in modal_ops(), modal_ops())
    check("preview rebuilt after undo", preview_objects(), preview_objects())


def pos(dx=0, dy=0):
    return lambda: (region_center()[0] + dx, region_center()[1] + dy)


SCENARIOS = {
    "qa1_preview_color": [
        setup_cube, qa1_select_cube, set_oblique_view(1.3), wait, screenshot("preview_off"),
        qa1_preview(True), wait, wait, screenshot("preview_on"), qa1_check_colour,
        qa1_preview(False), wait, qa1_toggle_many, check_clean("preview off"),
    ],
    "qa2_adjust": (
        [setup_cube, qa1_select_cube, set_view('FRONT', 1.3), adjust_preview(True), wait]
        # 1) drag + LMB confirm
        + [invoke("snapsplit.adjust_split_axis"), record_adjust("start")] + drag()
        + [wait, record_adjust("dragged"), check_drag_moved("start", "dragged"), screenshot("dragged"),
           check_orphans_zero("drag, preview on")]
        + click('LEFTMOUSE', pos(0, 100)) + [wait, check_confirmed("dragged"), screenshot("confirmed_lmb")]
        # 2) drag + Enter confirm, preview OFF (no delete/recreate churn)
        + [adjust_preview(False), invoke("snapsplit.adjust_split_axis"), record_adjust("start2")]
        + drag(steps=3, dy=-30)
        + [wait, record_adjust("dragged2"), check_drag_moved("start2", "dragged2"),
           check_orphans_zero("drag, preview off")]
        + [key('RET'), wait, check_confirmed("dragged2"), check_clean("after Enter, preview off")]
        # 3) Esc cancels
        + [invoke("snapsplit.adjust_split_axis")] + drag(steps=2)
        + [wait, key('ESC'), wait, check_clean("after Esc"),
           named("esc_report", lambda: check("reported 'Adjust split axis cancelled.'",
                                             printed("Adjust split axis cancelled.")))]
    ),
    "qa3_connectors": (
        [setup_cube, split_into_parts, set_view('TOP', 1.4), wait, conn_record("v0"),
         invoke("snapsplit.place_connectors_click"),
         move(lambda: world_to_window(P2)), wait, conn_check_preview_at(P2),
         move(lambda: world_to_window(P1)), wait, conn_check_preview_at(P1), conn_check_preview_moved,
         screenshot("preview_follows")]
        + click('LEFTMOUSE', lambda: world_to_window(P1))
        + [wait, conn_record("v1"), conn_check_placed("v0", "v1", P1), screenshot("placed")]
        + [key('S'), wait, move(lambda: world_to_window(P2)), wait]
        + click('LEFTMOUSE', lambda: world_to_window(P2))
        + [wait, conn_record("v2"), conn_check_placed("v1", "v2", P2, expect_gainer="other"),
           screenshot("placed_swapped")]
        + click('RIGHTMOUSE') + [wait, check_clean("after RMB")]
    ),
    "qa4_freehand": (
        [setup_suzanne, set_view('FRONT', 1.2), wait,
         invoke("snapsplit.freehand_cut"), wait]
        + fh_stroke(shift_release=True)
        + [wait, fh_check_preview, screenshot("stroke_preview"), key('RET'), wait, wait,
           fh_check_committed, screenshot("committed")]
        # Esc exits without changes (fresh Suzanne)
        + [setup_suzanne, wait, invoke("snapsplit.freehand_cut"), wait] + fh_stroke(shift_release=False)
        + [wait, named("fh_preview_no_snap", lambda: fh_check_preview(False)), key('ESC'), wait,
           fh_check_unchanged("Esc")]
        # File load while drawing mode is active -> cancel()
        + [invoke("snapsplit.freehand_cut"), wait, load_homefile, wait, fh_load_check]
    ),
    "adjust_undo_wheel": (
        [setup_cube, push_settings_change, invoke("snapsplit.adjust_split_axis"),
         key('WHEELUPMOUSE'), wait, record_offset]
        + [undo, key('WHEELUPMOUSE'), key('WHEELUPMOUSE'), wait, record_offset,
           redo, key('WHEELDOWNMOUSE'), wait, record_offset] * 6
        + [check_running('SNAPSPLIT_OT_adjust_split_axis'), check_offsets_followed_wheel,
           key('ESC'), wait, check_clean("adjust")]
    ),
    "conn_undo": (
        [setup_cube, split_into_parts, set_view('TOP', 1.4), push_settings_change,
         invoke("snapsplit.place_connectors_click"), move(pos(10)), wait]
        + [conn_undo_step, move(pos(20)), wait, check_connectors_preview_rebuilt, key('S'),
           redo, move(pos(-20)), wait] * 4
        + [key('ESC'), wait, check_clean("connectors")]
    ),
    "load_adjust": [setup_cube, qa1_select_cube, invoke("snapsplit.adjust_split_axis"), key('WHEELUPMOUSE'),
                    wait, load_homefile, wait, check_clean("adjust after file load"),
                    check_cancel_ran("Adjust split axis cancelled.", "adjust_axis")],
    "load_conn": [setup_cube, split_into_parts, invoke("snapsplit.place_connectors_click"), move(pos(10)),
                  wait, load_homefile, wait, check_clean("connectors after file load"),
                  check_cancel_ran("Placement cancelled.", "click_place")],
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
    write_report()  # keep a report on disk even if a later step crashes Blender
    return 0.2


bpy.app.timers.register(tick, first_interval=2.0, persistent=True)
