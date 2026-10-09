# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SnapSplit.
"""In-Blender test runner (started by tests/run_tests.py).

blender -b --factory-startup --python blender_runner.py -- \
    --repo <dir containing snapsplit/> --cases <dir> --out <json> [--case PATTERN]... [--slow]

Registers <repo> as a local extension repository, enables the add-on, runs every
selected ``tests/cases/test_*.py`` (each defines ``run(ctx)``) in a fresh empty
scene and writes a JSON report. An exception in ``run`` is a FAIL.
"""

import argparse
import fnmatch
import glob
import importlib.util
import json
import os
import sys
import time
import traceback

import bpy

REPO_NAME = "snapsplit_test"
ADDON_MODULE = f"bl_ext.{REPO_NAME}.snapsplit"

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)


class Context:
    """Passed to each case's run(ctx)."""

    def __init__(self, name, slow):
        self.name = name
        self.slow = slow
        self.addon_module = ADDON_MODULE
        self.blender_version = bpy.app.version
        self.metrics = {}

    def module(self, name):
        """Return an add-on submodule, e.g. ctx.module("ops_split")."""
        return sys.modules[f"{ADDON_MODULE}.{name}"]

    def metric(self, key, value):
        """Record a metric (also printed as key=value)."""
        self.metrics[key] = value
        print(f"[{self.name}] {key}={value}", flush=True)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="blender_runner.py")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--case", action="append", default=[])
    ap.add_argument("--slow", action="store_true")
    return ap.parse_args(argv)


def enable_addon(repo_dir):
    repos = bpy.context.preferences.extensions.repos
    repo = repos.get(REPO_NAME) or repos.new(name=REPO_NAME, module=REPO_NAME,
                                             custom_directory=repo_dir)
    repo.use_custom_directory = True
    repo.enabled = True
    bpy.ops.extensions.repo_refresh_all()
    bpy.ops.preferences.addon_enable(module=ADDON_MODULE)
    if ADDON_MODULE not in bpy.context.preferences.addons:
        raise RuntimeError(f"add-on {ADDON_MODULE} not enabled")


def reset_scene():
    """Empty factory scene; preferences (and the enabled add-on) are kept."""
    bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
    if ADDON_MODULE not in bpy.context.preferences.addons:
        bpy.ops.preferences.addon_enable(module=ADDON_MODULE)


def load_case(path):
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(f"snapsplit_case_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def select_cases(cases_dir, patterns):
    paths = sorted(glob.glob(os.path.join(cases_dir, "test_*.py")))
    if not patterns:
        return paths
    return [p for p in paths
            if any(fnmatch.fnmatch(os.path.splitext(os.path.basename(p))[0], pat)
                   for pat in patterns)]


def main():
    args = parse_args()
    report = {"blender": bpy.app.version_string, "cases": [], "notes": []}

    def write_report():
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1, separators=(",", ":"))

    print(f"Blender {bpy.app.version_string}", flush=True)
    try:
        enable_addon(args.repo)
    except Exception:
        tb = traceback.format_exc()
        print(tb, flush=True)
        report["cases"].append({"name": "addon_enable", "status": "FAIL",
                                "time_s": 0.0, "traceback": tb, "metrics": {}})
        write_report()
        return 1

    for path in select_cases(args.cases, args.case):
        name = os.path.splitext(os.path.basename(path))[0]
        entry = {"name": name, "status": "PASS", "time_s": 0.0, "metrics": {}}
        t0 = time.perf_counter()
        try:
            mod = load_case(path)
            if getattr(mod, "SLOW", False) and not args.slow:
                report["notes"].append(f"{name} is a slow case, run with --slow")
                continue
            reset_scene()
            ctx = Context(name, args.slow)
            entry["metrics"] = ctx.metrics
            mod.run(ctx)
        except BaseException:
            entry["status"] = "FAIL"
            entry["traceback"] = traceback.format_exc()
        entry["time_s"] = round(time.perf_counter() - t0, 3)
        report["cases"].append(entry)
        print(f"[{entry['status']}] {name} ({entry['time_s']:.2f}s)", flush=True)
        if entry["status"] == "FAIL":
            print(entry["traceback"], flush=True)
        write_report()

    write_report()
    failed = [c for c in report["cases"] if c["status"] != "PASS"]
    return 1 if failed or not report["cases"] else 0


if __name__ == "__main__":
    sys.exit(main())
