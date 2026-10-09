# SPDX-License-Identifier: GPL-3.0-or-later
"""P1-11: splitforge.export_parts writes one file per part and format, in millimeters."""

import os
import shutil

import bpy

import lib


def _triangles(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def _build(name, size):
    cube = lib.make_cube(size)
    cube.name = name
    lib.select_only([cube])
    lib.run_op(bpy.ops.splitforge.easy_cut, axis='Z', offset_mm=0.0, connector_count=1)
    return sorted((o for o in bpy.data.objects if o.get("splitforge_source") == name), key=lambda o: o.name)


def run(ctx):
    compat = ctx.module("core.compat")
    assert set(compat.export_formats()) == {'STL', 'OBJ', 'FBX'}, compat.export_formats()
    lib.set_scene_mm()
    out = os.path.join(bpy.app.tempdir, "export_parts")
    shutil.rmtree(out, ignore_errors=True)

    parts = _build("Exp", 40.0)
    assert len(parts) == 2
    tris = {p.name: _triangles(p) for p in parts}
    dims = {p.name: tuple(p.dimensions) for p in parts}
    lib.run_op(bpy.ops.splitforge.export_parts, directory=out, formats={'STL', 'OBJ'})
    files = sorted(os.listdir(out))
    assert files == ["Exp_A.obj", "Exp_A.stl", "Exp_B.obj", "Exp_B.stl"], files
    for f in files:
        size = os.path.getsize(os.path.join(out, f))
        assert size > 1024, (f, size)
    # The selection is restored
    assert sorted(o.name for o in bpy.context.selected_objects) == sorted(tris)

    # STL round trip: same triangle count and size (mm scene: 1 unit = 1 mm)
    for name, n_tris in tris.items():
        before = set(bpy.data.objects.keys())
        compat.import_stl(os.path.join(out, name + ".stl"))
        imported = [bpy.data.objects[k] for k in set(bpy.data.objects.keys()) - before]
        assert len(imported) == 1, imported
        assert len(imported[0].data.polygons) == n_tris, (name, len(imported[0].data.polygons), n_tris)
        for got, want in zip(imported[0].dimensions, dims[name]):
            lib.assert_close(got, want, abs_=1e-3, msg=f"{name} STL size")
        bpy.data.objects.remove(imported[0])

    # FBX works in both Blender versions and is written in real units: importing the
    # 40 mm wide part into a meter scene gives 0.04 m (was 40 m before the unit fix)
    fbx_dir = os.path.join(out, "fbx")
    lib.select_only([parts[0]])
    lib.run_op(bpy.ops.splitforge.export_parts, directory=fbx_dir, formats={'FBX'})
    assert sorted(os.listdir(fbx_dir)) == ["Exp_A.fbx", "Exp_B.fbx"]
    width_mm = bpy.data.objects["Exp_B"].dimensions.x
    bpy.context.scene.unit_settings.length_unit = 'METERS'
    before = set(bpy.data.objects.keys())
    bpy.ops.import_scene.fbx(filepath=os.path.join(fbx_dir, "Exp_B.fbx"))
    imported = bpy.data.objects[(set(bpy.data.objects.keys()) - before).pop()]
    bpy.context.view_layer.update()
    lib.assert_close(imported.dimensions.x, width_mm / 1000.0, rel=1e-3, msg="FBX in real units")
    bpy.data.objects.remove(imported)
    lib.set_scene_mm()

    # Hidden parts are skipped with a warning
    hidden_dir = os.path.join(out, "hidden")
    bpy.data.objects["Exp_A"].hide_set(True)
    lib.select_only([bpy.data.objects["Exp_B"]])
    lib.run_op(bpy.ops.splitforge.export_parts, directory=hidden_dir, formats={'STL'})
    assert os.listdir(hidden_dir) == ["Exp_B.stl"], os.listdir(hidden_dir)
    bpy.data.objects["Exp_A"].hide_set(False)

    # The default folder "//parts/" needs a saved file (it would land in Blender's cwd)
    assert not bpy.data.filepath
    try:
        bpy.ops.splitforge.export_parts(formats={'STL'})
    except RuntimeError as ex:
        assert "Save the file first" in str(ex), ex
    else:
        raise AssertionError("relative export folder in an unsaved file must fail")

    # Centimeter scene: a 4-unit cube is 40 mm; the STL is written in millimeters
    bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
    us = bpy.context.scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'CENTIMETERS', 1.0
    parts = _build("ExpCm", 4.0)
    cm_dir = os.path.join(out, "cm")
    lib.run_op(bpy.ops.splitforge.export_parts, directory=cm_dir, formats={'STL'}, apply_scale_mm=True)
    lib.set_scene_mm()
    before = set(bpy.data.objects.keys())
    compat.import_stl(os.path.join(cm_dir, "ExpCm_A.stl"))
    imported = bpy.data.objects[(set(bpy.data.objects.keys()) - before).pop()]
    lib.assert_close(imported.dimensions.x, 40.0, abs_=1e-3, msg="cm scene exported in mm")

    # Without a build there is nothing to export
    lib.select_only([lib.make_cube(10.0)])
    assert not bpy.ops.splitforge.export_parts.poll()
    shutil.rmtree(out, ignore_errors=True)
