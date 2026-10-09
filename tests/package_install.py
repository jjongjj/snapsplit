# SPDX-License-Identifier: GPL-3.0-or-later
"""Install the release zip the way a user does (started by ``tests/run_tests.py --zip``).

blender -b --factory-startup --python package_install.py -- --zip <file> --repo-dir <empty dir> --out <json>

A local extension repository in ``--repo-dir`` receives the zip through
``extensions.package_install_files`` (enable on install); the add-on must then be enabled, its
operators and panels registered, a Z cut + Build on a cube must give two manifold parts, and
disable / enable must work. Writes a JSON report (ok, checks).
"""

import argparse
import json
import sys
import traceback

import bmesh
import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--zip", required=True)
ap.add_argument("--repo-dir", required=True)
ap.add_argument("--out", required=True)
args = ap.parse_args(argv)
REPO = "splitforge_zip_test"
report = {"checks": [], "ok": False, "blender": bpy.app.version_string, "tempdir": bpy.app.tempdir}


def check(name, cond, detail=""):
    report["checks"].append({"name": name, "ok": bool(cond), "detail": str(detail)})


try:
    repos = bpy.context.preferences.extensions.repos
    repo = repos.new(name=REPO, module=REPO, custom_directory=args.repo_dir)
    repo.use_custom_directory = True
    ret = bpy.ops.extensions.package_install_files(filepath=args.zip, repo=REPO, enable_on_install=True)
    module = f"bl_ext.{REPO}.splitforge"
    check("package_install_files finished", ret == {'FINISHED'}, ret)
    check("add-on enabled after install", module in bpy.context.preferences.addons,
          list(bpy.context.preferences.addons.keys()))
    for name in ("SPLITFORGE_OT_build", "SPLITFORGE_OT_stack_add_polygon", "SPLITFORGE_OT_fix_transforms",
                 "SPLITFORGE_PT_main"):
        check(f"{name} registered", hasattr(bpy.types, name))
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'MILLIMETERS', 0.001
    bpy.ops.mesh.primitive_cube_add(size=40.0)
    cube = bpy.context.active_object
    bpy.ops.splitforge.stack_add_plane(axis='Z')
    bpy.ops.splitforge.connector_add_auto()
    ret = bpy.ops.splitforge.build()
    parts = [o for o in bpy.data.objects if o.get("splitforge_source") == cube.name]

    def manifold(o):
        bm = bmesh.new()
        bm.from_mesh(o.data)
        ok = len(bm.faces) > 0 and all(e.is_manifold for e in bm.edges)
        bm.free()
        return ok
    check("Build with the installed add-on: 2 manifold parts", ret == {'FINISHED'} and len(parts) == 2
          and all(manifold(o) for o in parts), [o.name for o in parts])
    bpy.ops.preferences.addon_disable(module=module)
    check("disable", not hasattr(bpy.types, "SPLITFORGE_OT_build"))
    bpy.ops.preferences.addon_enable(module=module)
    check("enable again", hasattr(bpy.types, "SPLITFORGE_OT_build"))
except Exception:
    check("no exception", False, traceback.format_exc())
report["ok"] = bool(report["checks"]) and all(c["ok"] for c in report["checks"])
with open(args.out, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=1)
