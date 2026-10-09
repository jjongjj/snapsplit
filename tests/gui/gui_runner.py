# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SnapSplit.
"""GUI scenario runner for modal operators (started by ``tests/run_tests.py --gui``).

blender --factory-startup --enable-event-simulate --python gui_runner.py -- \
    --repo <dir containing snapsplit/> --scenario NAME --out <json>

Modal operators only run in a real window, so these scenarios start a GUI Blender
(with simulated input, real input is blocked) and drive it step by step from a
persistent ``bpy.app.timers`` callback, the same way the Blender MCP add-on runs
scripts. Each scenario records checks in a JSON report and quits Blender. A crash
(no report / non-zero exit code / blender.crash.txt) is a FAIL in run_tests.py.

Scenarios
    adjust_undo_wheel  ed.undo/redo while Adjust Split Axis runs, wheel events write
                       the offset (crashed with EXCEPTION_ACCESS_VIOLATION before
                       the undo-safety fix)
    conn_undo          ed.undo/redo while Place Connectors (click) runs; the preview
                       is rebuilt after undo and cleaned up on Esc
    load_adjust        file load while Adjust Split Axis runs -> cancel() cleans up
    load_conn          file load while Place Connectors (click) runs -> cancel()
"""

import argparse
import json
import sys
import traceback

import bpy

REPO_NAME = "snapsplit_gui_test"
ADDON = f"bl_ext.{REPO_NAME}.snapsplit"

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser(prog="gui_runner.py")
ap.add_argument("--repo", required=True)
ap.add_argument("--scenario", required=True)
ap.add_argument("--out", required=True)
ARGS = ap.parse_args(argv)

REPORT = {"blender": bpy.app.version_string, "scenario": ARGS.scenario,
          "tempdir": bpy.app.tempdir, "checks": [], "log": [], "ok": False, "completed": False}


def log(*parts):
    REPORT["log"].append(" ".join(str(p) for p in parts))


def check(name, cond, detail=""):
    REPORT["checks"].append({"name": name, "ok": bool(cond), "detail": str(detail)})


def write_report():
    REPORT["ok"] = bool(REPORT["checks"]) and all(c["ok"] for c in REPORT["checks"])
    with open(ARGS.out, "w", encoding="utf-8") as f:
        json.dump(REPORT, f, indent=1)


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


# --- helpers ----------------------------------------------------------------

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


def preview_objects():
    planes = mod("ops_split").PREVIEW_PLANE_PREFIX
    return [o.name for o in bpy.data.objects
            if o.name.startswith(planes) or o.name.startswith("SnapSplit_Preview")]


def xray_reasons():
    return sorted(r for s in mod("utils")._XRAY_STATES.values() for r in s["reasons"])


def sim(type_, value='PRESS', **kw):
    def step():
        win, area, _region = view3d()
        x, y = area.x + area.width // 2, area.y + area.height // 2
        win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
        win.event_simulate(type=type_, value=value, x=x, y=y, **kw)
    step.__name__ = f"sim_{type_}"
    return step


def mousemove(dx):
    def step():
        win, area, _region = view3d()
        x, y = area.x + area.width // 2, area.y + area.height // 2
        win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x + dx, y=y)
    step.__name__ = f"mousemove_{dx}"
    return step


def wait():
    pass


def setup_cube():
    with override():
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o)
        units = bpy.context.scene.unit_settings
        units.system = 'METRIC'
        units.length_unit = 'MILLIMETERS'
        bpy.ops.mesh.primitive_cube_add('EXEC_DEFAULT', True, size=0.04)
        bpy.context.active_object.name = "GUI_Cube"
        props = bpy.context.scene.snapsplit
        props.split_axis = 'Z'
        props.parts_count = 2
        props.split_offset_mm = 0.0


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
    check("two parts", len(parts) == 2, [o.name for o in parts])


def push_settings_change():
    """Two undo steps that differ only in scene.snapsplit (undo re-allocates the group)."""
    with override():
        bpy.ops.ed.undo_push(message="gui: base")
        bpy.context.scene.snapsplit.parts_count = 3
        bpy.ops.ed.undo_push(message="gui: settings")


def invoke_adjust():
    with override():
        ret = bpy.ops.snapsplit.adjust_split_axis('INVOKE_DEFAULT', True)
    check("adjust invoked", ret == {'RUNNING_MODAL'}, ret)


def invoke_connectors():
    with override():
        ret = bpy.ops.snapsplit.place_connectors_click('INVOKE_DEFAULT', True)
    check("connectors invoked", ret == {'RUNNING_MODAL'}, ret)
    check("connector preview created", preview_objects(), preview_objects())


def undo():
    before = bpy.context.scene.snapsplit.as_pointer()
    with override():
        bpy.ops.ed.undo()
    log("undo", "group moved" if bpy.context.scene.snapsplit.as_pointer() != before else "group kept")


def redo():
    with override():
        bpy.ops.ed.redo()


OFFSETS = []


def record_offset():
    OFFSETS.append(bpy.context.scene.snapsplit.split_offset_mm)
    log("offset", OFFSETS[-1], modal_ops())


def check_adjust_running():
    check("adjust still running", 'SNAPSPLIT_OT_adjust_split_axis' in modal_ops(), modal_ops())


def check_connectors_preview_rebuilt():
    check("connectors running", 'SNAPSPLIT_OT_place_connectors_click' in modal_ops(), modal_ops())
    check("preview rebuilt after undo", preview_objects(), preview_objects())


def check_finished_clean(what):
    def step():
        check(f"{what}: modal ended", not modal_ops(), modal_ops())
        check(f"{what}: no preview objects left", not preview_objects(), preview_objects())
        check(f"{what}: X-Ray released", not xray_reasons(), xray_reasons())
    step.__name__ = f"check_finished_clean_{what}"
    return step


def check_offsets_followed_wheel():
    check("live offset followed the wheel", len(set(OFFSETS)) > 1 and any(OFFSETS), OFFSETS)


def load_homefile():
    reasons = xray_reasons()
    with override():
        bpy.ops.wm.read_homefile()
    log("read_homefile; X-Ray reasons before:", reasons)


SCENARIOS = {
    "adjust_undo_wheel": (
        [setup_cube, push_settings_change, invoke_adjust, sim('WHEELUPMOUSE'), wait, record_offset]
        + [undo, sim('WHEELUPMOUSE'), sim('WHEELUPMOUSE'), wait, record_offset,
           redo, sim('WHEELDOWNMOUSE'), wait, record_offset] * 6
        + [check_adjust_running, check_offsets_followed_wheel, sim('ESC'), wait,
           check_finished_clean("adjust")]
    ),
    "conn_undo": (
        [setup_cube, split_into_parts, push_settings_change, invoke_connectors, mousemove(10), wait]
        + [undo, mousemove(20), wait, check_connectors_preview_rebuilt, sim('S'),
           redo, mousemove(-20), wait] * 4
        + [sim('ESC'), wait, check_finished_clean("connectors")]
    ),
    "load_adjust": [setup_cube, invoke_adjust, sim('WHEELUPMOUSE'), wait, load_homefile, wait,
                    check_finished_clean("adjust after file load")],
    "load_conn": [setup_cube, split_into_parts, invoke_connectors, mousemove(10), wait, load_homefile, wait,
                  check_finished_clean("connectors after file load")],
}

STEPS = list(SCENARIOS[ARGS.scenario])
STATE = {"i": 0}


def tick():
    if STATE["i"] >= len(STEPS):
        REPORT["completed"] = True
        write_report()
        bpy.ops.wm.quit_blender()
        return None
    step = STEPS[STATE["i"]]
    STATE["i"] += 1
    try:
        step()
    except Exception:
        check(f"step {step.__name__} raised", False, traceback.format_exc())
    write_report()  # keep a report on disk even if a later step crashes Blender
    return 0.25


bpy.app.timers.register(tick, first_interval=2.0, persistent=True)
