#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SnapSplit.
"""Host-side test runner.

Copies ``snapsplit/`` into a temporary extension repository, runs
``tests/blender_runner.py`` inside each requested Blender (headless), collects
the JSON reports and prints a summary. Exit code 0 only if every selected case
passed in every Blender version.

Usage:
    python3 tests/run_tests.py [--blender EXE]... [--case PATTERN]... [--slow]

Default Blender executables are BL45 and BL52 below (override with the
environment variables of the same name). Windows executables are supported from
WSL: paths handed to them are converted with ``wslpath -w``.
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
ADDON_DIR = os.path.join(ROOT_DIR, "snapsplit")
OUT_DIR = os.path.join(TESTS_DIR, "_out")


def to_exe_path(path, exe):
    """Return ``path`` in the form the Blender executable expects."""
    if exe.lower().endswith(".exe") and path.startswith("/"):
        return subprocess.check_output(["wslpath", "-w", path], text=True).strip()
    return path


def label_for(exe):
    """Short, file-name safe label for an executable (e.g. 'Blender_5.2')."""
    name = os.path.basename(os.path.dirname(exe)) or os.path.basename(exe)
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in name)


def run_blender(exe, args, timeout):
    """Run the in-Blender runner for one executable. Returns the parsed report."""
    label = label_for(exe)
    repo_dir = os.path.join(OUT_DIR, "repo_" + label)
    json_path = os.path.join(OUT_DIR, "results_" + label + ".json")
    shutil.rmtree(repo_dir, ignore_errors=True)
    shutil.copytree(ADDON_DIR, os.path.join(repo_dir, "snapsplit"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if os.path.exists(json_path):
        os.remove(json_path)

    cmd = [
        exe, "-b", "--factory-startup", "--python-exit-code", "1",
        "--python", to_exe_path(os.path.join(TESTS_DIR, "blender_runner.py"), exe),
        "--",
        "--repo", to_exe_path(repo_dir, exe),
        "--cases", to_exe_path(os.path.join(TESTS_DIR, "cases"), exe),
        "--out", to_exe_path(json_path, exe),
    ]
    for pattern in args.case:
        cmd += ["--case", pattern]
    if args.slow:
        cmd.append("--slow")

    print(f"=== {exe}", flush=True)
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, timeout=timeout)
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
            "elapsed_s": elapsed, "json": json_path, "report": report}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--blender", action="append", default=[],
                    help="Blender executable (repeatable). Default: BL45 and BL52.")
    ap.add_argument("--case", action="append", default=[],
                    help="Case name or glob, e.g. test_register or 'test_legacy_*' (repeatable).")
    ap.add_argument("--slow", action="store_true", help="Also run slow cases (SLOW = True).")
    ap.add_argument("--timeout", type=float, default=3600.0,
                    help="Timeout per Blender run in seconds.")
    args = ap.parse_args()

    exes = args.blender or [BL45, BL52]
    missing = [e for e in exes if not os.path.isfile(e)]
    if missing:
        print("Blender executable not found: " + ", ".join(missing), file=sys.stderr)
        return 2

    os.makedirs(OUT_DIR, exist_ok=True)
    runs = [run_blender(exe, args, args.timeout) for exe in exes]

    ok = True
    print("\n=== Summary")
    for run in runs:
        report = run["report"]
        if report is None:
            ok = False
            print(f"[FAIL] {run['label']}: no JSON report (exit code {run['returncode']})")
            continue
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
    print("RESULT: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
