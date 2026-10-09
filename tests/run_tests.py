#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SnapSplit.
"""Host-side test runner.

Copies the add-on package (``splitforge/``) into a temporary extension repository, runs
``tests/blender_runner.py`` inside each requested Blender (headless), collects
the JSON reports and prints a summary. Exit code 0 only if every selected case
passed in every Blender version.

Usage:
    python3 tests/run_tests.py [--blender EXE]... [--all-versions] [--case PATTERN]... [--slow]
                                [--gui [--gui-only] [--gui-scenario NAME]...]

``--gui`` additionally runs the modal-operator scenarios in ``tests/gui/gui_runner.py``
(QA-5..QA-12 mouse/keyboard steps, undo and file-load safety) in GUI Blender instances
with simulated input; screenshots go to ``tests/_out/gui/``. Takes a few minutes;
windows pop up and must not be touched while they run.

SplitForge supports Blender 5.2 only (user decision 2026-10-10): the default
executable is BL52 below. ``--all-versions`` also runs BL45 (Blender 4.5, kept as an
optional regression signal, not a supported version); ``--blender`` picks any
executables (override the defaults with the environment variables of the same name). Windows executables are supported from
WSL: paths handed to them are converted with ``wslpath -w``.

Blender runs with TEMP/TMP/TMPDIR set to ``tests/_out/tmp`` (forwarded through
WSLENV), so a crash writes ``blender.crash.txt`` there, never into the user's %TEMP%.
A run whose ``bpy.app.tempdir`` is not inside that directory counts as FAIL.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

BL45 = os.environ.get("BL45", "/mnt/c/Program Files/Blender Foundation/Blender 4.5/blender.exe")
BL52 = os.environ.get("BL52", "/mnt/c/Program Files/Blender Foundation/Blender 5.2/blender.exe")

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TESTS_DIR)


def _find_addon():
    """(directory, package name): the top-level folder holding blender_manifest.toml.

    The package is installed under its manifest ``id`` (the extension module name),
    so renaming the add-on only touches the manifest and the folder name.
    """
    for entry in sorted(os.listdir(ROOT_DIR)):
        manifest = os.path.join(ROOT_DIR, entry, "blender_manifest.toml")
        if os.path.isfile(manifest):
            with open(manifest, encoding="utf-8") as f:
                for line in f:
                    key, _, value = line.partition("=")
                    if key.strip() == "id":
                        return os.path.join(ROOT_DIR, entry), value.strip().strip('"')
    raise SystemExit("no add-on folder with blender_manifest.toml found in " + ROOT_DIR)


ADDON_DIR, PACKAGE = _find_addon()
OUT_DIR = os.path.join(TESTS_DIR, "_out")
# Private temp directory for the Blender subprocesses: a crash writes blender.crash.txt
# (and other temp files) here instead of overwriting the user's %TEMP%.
TMP_DIR = os.path.join(OUT_DIR, "tmp")


def to_exe_path(path, exe):
    """Return ``path`` in the form the Blender executable expects."""
    if exe.lower().endswith(".exe") and path.startswith("/"):
        return subprocess.check_output(["wslpath", "-w", path], text=True).strip()
    return path


def label_for(exe):
    """Short, file-name safe label for an executable (e.g. 'Blender_5.2')."""
    name = os.path.basename(os.path.dirname(exe)) or os.path.basename(exe)
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in name)


def blender_env(exe):
    """Environment for a Blender subprocess with TEMP/TMP/TMPDIR pointing to TMP_DIR.

    A Windows executable started from WSL only sees variables listed in WSLENV; the
    values are already Windows paths, so they are passed without a conversion flag.
    """
    os.makedirs(TMP_DIR, exist_ok=True)
    tmp = to_exe_path(TMP_DIR, exe)
    env = dict(os.environ, TEMP=tmp, TMP=tmp, TMPDIR=tmp)
    if exe.lower().endswith(".exe"):
        names = [n for n in env.get("WSLENV", "").split(":") if n and n.split("/")[0] not in ("TEMP", "TMP", "TMPDIR")]
        env["WSLENV"] = ":".join(names + ["TEMP", "TMP", "TMPDIR"])
    return env


def tempdir_ok(report, tmp):
    """True if Blender's session temp dir lies inside the private TMP_DIR."""
    tempdir = (report or {}).get("tempdir", "")
    norm = lambda p: p.replace("\\", "/").rstrip("/").lower()
    return norm(tempdir).startswith(norm(tmp) + "/")


def run_blender(exe, args, timeout):
    """Run the in-Blender runner for one executable. Returns the parsed report."""
    label = label_for(exe)
    repo_dir = os.path.join(OUT_DIR, "repo_" + label)
    json_path = os.path.join(OUT_DIR, "results_" + label + ".json")
    shutil.rmtree(repo_dir, ignore_errors=True)
    shutil.copytree(ADDON_DIR, os.path.join(repo_dir, PACKAGE),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if os.path.exists(json_path):
        os.remove(json_path)

    cmd = [
        exe, "-b", "--factory-startup", "--python-exit-code", "1",
        "--python", to_exe_path(os.path.join(TESTS_DIR, "blender_runner.py"), exe),
        "--",
        "--repo", to_exe_path(repo_dir, exe),
        "--package", PACKAGE,
        "--cases", to_exe_path(os.path.join(TESTS_DIR, "cases"), exe),
        "--out", to_exe_path(json_path, exe),
    ]
    for pattern in args.case:
        cmd += ["--case", pattern]
    if args.slow:
        cmd.append("--slow")

    print(f"=== {exe}", flush=True)
    t0 = time.time()
    env = blender_env(exe)
    try:
        proc = subprocess.run(cmd, timeout=timeout, env=env)
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        returncode = "timeout"
    elapsed = time.time() - t0
    shutil.rmtree(repo_dir, ignore_errors=True)

    report = None
    if os.path.exists(json_path):
        with open(json_path, encoding="utf-8") as f:
            report = json.load(f)
    return {"exe": exe, "label": label, "returncode": returncode,
            "elapsed_s": elapsed, "json": json_path, "report": report,
            "tmp": to_exe_path(TMP_DIR, exe)}


GUI_SCENARIOS = ("p1_adjust_plane", "p1_panel", "p2_stroke", "p2_build_progress", "p3_connector_click",
                 "p3_connector_types", "p4_points", "p4_fix")
GUI_SHOTS_DIR = os.path.join(OUT_DIR, "gui")


def run_gui(exe, scenario, timeout):
    """Run one tests/gui scenario in a GUI Blender with simulated input. Returns (ok, lines)."""
    label = label_for(exe)
    repo_dir = os.path.join(OUT_DIR, "repo_gui_" + label)
    json_path = os.path.join(OUT_DIR, f"gui_{scenario}_{label}.json")
    log_path = os.path.join(OUT_DIR, f"gui_{scenario}_{label}.log")
    crash_path = os.path.join(TMP_DIR, "blender.crash.txt")
    shutil.rmtree(repo_dir, ignore_errors=True)
    shutil.copytree(ADDON_DIR, os.path.join(repo_dir, PACKAGE),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for path in (json_path, crash_path):
        if os.path.exists(path):
            os.remove(path)
    cmd = [
        exe, "--factory-startup", "--enable-event-simulate",
        "--python", to_exe_path(os.path.join(TESTS_DIR, "gui", "gui_runner.py"), exe),
        "--",
        "--repo", to_exe_path(repo_dir, exe),
        "--package", PACKAGE,
        "--scenario", scenario,
        "--out", to_exe_path(json_path, exe),
        "--shots", to_exe_path(GUI_SHOTS_DIR, exe),
        "--label", label,
    ]
    os.makedirs(GUI_SHOTS_DIR, exist_ok=True)
    env = blender_env(exe)
    t0 = time.time()
    with open(log_path, "w", encoding="utf-8") as log:
        try:
            returncode = subprocess.run(cmd, timeout=timeout, env=env, stdout=log,
                                        stderr=subprocess.STDOUT).returncode
        except subprocess.TimeoutExpired:
            returncode = "timeout"
    elapsed = time.time() - t0
    shutil.rmtree(repo_dir, ignore_errors=True)

    report = None
    if os.path.exists(json_path):
        with open(json_path, encoding="utf-8") as f:
            report = json.load(f)
    with open(log_path, encoding="utf-8", errors="replace") as f:
        python_errors = f.read().count("Traceback")
    crashed = os.path.exists(crash_path)
    if crashed:
        os.replace(crash_path, os.path.join(OUT_DIR, f"gui_{scenario}_{label}.crash.txt"))

    ok = (report is not None and report.get("ok") and report.get("completed")
          and returncode == 0 and not crashed and not python_errors
          and tempdir_ok(report, to_exe_path(TMP_DIR, exe)))
    lines = [f"  {'PASS' if ok else 'FAIL'} gui:{scenario:28} {elapsed:8.2f}s "
             f"exit={returncode} crash={crashed} tracebacks={python_errors} log={log_path}"]
    if report and report.get("screenshots"):
        lines.append("       screenshots: " + ", ".join(os.path.basename(p) for p in report["screenshots"]))
    for c in (report or {}).get("checks", []):
        if not c["ok"]:
            lines.append(f"       check failed: {c['name']}: {c['detail'][:300]}")
    return bool(ok), lines


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--blender", action="append", default=[],
                    help="Blender executable (repeatable). Default: BL52 (Blender 5.2, the supported version).")
    ap.add_argument("--all-versions", action="store_true",
                    help="Also run BL45 (Blender 4.5; optional, unsupported).")
    ap.add_argument("--case", action="append", default=[],
                    help="Case name or glob, e.g. test_register or 'test_legacy_*' (repeatable).")
    ap.add_argument("--slow", action="store_true", help="Also run slow cases (SLOW = True).")
    ap.add_argument("--timeout", type=float, default=3600.0,
                    help="Timeout per Blender run in seconds.")
    ap.add_argument("--gui", action="store_true",
                    help="Also run the tests/gui scenarios (opens Blender windows with simulated "
                         "input; do not touch them while they run).")
    ap.add_argument("--gui-scenario", action="append", default=[], metavar="NAME",
                    help="With --gui: run only these scenarios (repeatable; default: all).")
    ap.add_argument("--gui-only", action="store_true",
                    help="With --gui: skip the headless cases.")
    args = ap.parse_args()

    exes = list(args.blender) or [BL52]
    if args.all_versions and BL45 not in exes:
        exes.insert(0, BL45)
    missing = [e for e in exes if not os.path.isfile(e)]
    if missing:
        print("Blender executable not found: " + ", ".join(missing), file=sys.stderr)
        return 2

    os.makedirs(OUT_DIR, exist_ok=True)
    runs = [] if (args.gui and args.gui_only) else [run_blender(exe, args, args.timeout) for exe in exes]

    ok = True
    print("\n=== Summary")
    for run in runs:
        report = run["report"]
        if report is None:
            ok = False
            print(f"[FAIL] {run['label']}: no JSON report (exit code {run['returncode']})")
            continue
        if not tempdir_ok(report, run["tmp"]):
            ok = False
            print(f"[FAIL] {run['label']}: Blender temp dir {report.get('tempdir')!r} "
                  f"is not inside {run['tmp']!r}")
        cases = report.get("cases", [])
        n_fail = sum(1 for c in cases if c["status"] != "PASS")
        if run["returncode"] != 0 or n_fail or not cases:
            ok = False
        print(f"{run['label']} (Blender {report.get('blender')}): "
              f"{len(cases) - n_fail} passed, {n_fail} failed, "
              f"exit code {run['returncode']}, {run['elapsed_s']:.1f}s, report {run['json']}")
        for c in cases:
            metrics = " ".join(f"{k}={v}" for k, v in c.get("metrics", {}).items())
            print(f"  {c['status']:4} {c['name']:32} {c['time_s']:8.2f}s {metrics}".rstrip())
        if not cases:
            print("  no cases selected")
        for note in report.get("notes", []):
            print(f"  note: {note}")
    if args.gui:
        print("\n=== GUI scenarios (tests/gui/gui_runner.py)")
        for exe in exes:
            print(label_for(exe))
            for scenario in (args.gui_scenario or GUI_SCENARIOS):
                gui_ok, lines = run_gui(exe, scenario, min(args.timeout, 400.0))
                ok = ok and gui_ok
                print("\n".join(lines), flush=True)
    print("RESULT: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
