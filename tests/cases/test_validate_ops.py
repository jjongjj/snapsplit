# SPDX-License-Identifier: GPL-3.0-or-later
"""P4-3: print checks + one-click Fix actions (ops/ops_fix.py), each one undo step, never silent.

- fix_transforms: a cube scaled 2 (and rotated) with a Z plane cut, a stroke and a connector:
  scale/rotation become identity, the world size stays (80 mm), the cuts stay in the world (same
  world plane / stroke points), the Build gives the same part volumes as before; negative scale
  keeps outward normals; a child keeps its world matrix; a shared mesh is refused; undo restores.
- fix_units: from a meter scene, Keep Units relabels (Millimeters, Unit Scale 0.001, objects
  unchanged), Keep Size scales the objects so the physical size stays; undo restores.
- fix_normals: some faces flipped / an inside-out cube -> detected, fixed (normals outward), undo.
- fix_merge: an edge-split cube (24 vertices) -> 16 duplicates detected, merged to 8.
- fix_holes: a missing face + a loose vertex -> filled, closed, loose gone; an edge with three
  faces stays (left for Edit Mode, named in the report).
- The panel shows the check rows with a Fix button only for failing checks; the mesh rows come
  from the last Check Mesh while the mesh is unchanged.
"""

import math

import bmesh
import bpy
from mathutils import Vector

import lib


def world_verts(obj):
    return [obj.matrix_world @ v.co for v in obj.data.vertices]


def run_fix(op, **kw):
    """Run a fix; push the undo step its UNDO flag gives it in the UI (scripted calls in background
    mode push none), so ed.undo below steps back over exactly this fix."""
    result = op(**kw)
    assert result == {'FINISHED'}, (op.idname_py(), result)
    bpy.ops.ed.undo_push(message=op.idname_py())


def expect_error(fn, text):
    try:
        fn()
    except RuntimeError as ex:
        assert text in str(ex), (text, str(ex))
        return
    raise AssertionError(f"expected an error containing {text!r}")


def run(ctx):
    validate = ctx.module("core.validate")
    build = ctx.module("cuts.build")
    lib.set_scene_mm()
    bpy.context.preferences.edit.undo_steps = 64

    # --- transforms ------------------------------------------------------------------------------
    cube = lib.make_cube(40.0)
    cube.name = "VScaled"
    cube.scale = (2.0, 2.0, 2.0)
    cube.rotation_euler = (0.0, 0.0, math.radians(30.0))
    bpy.context.view_layer.update()
    lib.select_only([cube])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z', offset_mm=5.0)
    lib.run_op(bpy.ops.splitforge.connector_add_auto)
    lib.run_op(bpy.ops.splitforge.stack_add_stroke, direction=(0.0, 1.0, 0.0),
               points=[{"name": "", "co": (x, 0.0, -20.0 + 0.1 * x * x / 10)} for x in range(-60, 61, 10)])
    stack = cube.splitforge_stack
    w_plane = [(cube.matrix_world @ Vector(c.origin)).copy() for c in stack.cuts]
    w_points = [cube.matrix_world @ Vector(p.co) for p in stack.cuts[1].points]
    res0 = build.build(bpy.context, cube)
    vols0 = sorted(round(lib.volume(bpy.data.objects[n]), 1) for n in res0.parts)
    lib.select_only([cube])
    cube.hide_set(False)
    child = lib.make_cube(5.0)
    child.name = "VChild"
    child.parent = cube
    child.location = (30.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    child_world = child.matrix_world.copy()
    lib.select_only([cube])
    assert not validate.validate(cube).transform_applied
    bpy.ops.ed.undo_push(message="before fix")
    run_fix(bpy.ops.splitforge.fix_transforms)
    cube = bpy.data.objects["VScaled"]
    assert validate.last_report(cube) is not None, "the panel keeps showing the (re-run) mesh check"
    assert validate.transform_is_applied(cube)
    assert tuple(round(x, 6) for x in cube.scale) == (1.0, 1.0, 1.0)
    xs = [v.co.x for v in cube.data.vertices]
    assert math.isclose(max(xs) - min(xs), 80.0 * math.cos(math.radians(30)) + 80.0 * math.sin(math.radians(30)),
                        rel_tol=1e-5), (max(xs) - min(xs))
    lib.assert_close(lib.volume(cube), 80.0 ** 3, rel=1e-6, msg="world size kept")
    stack = cube.splitforge_stack
    for c, w in zip(stack.cuts, w_plane):
        assert ((cube.matrix_world @ Vector(c.origin)) - w).length < 1e-4
    assert all(((cube.matrix_world @ Vector(p.co)) - q).length < 1e-4 for p, q in zip(stack.cuts[1].points, w_points))
    assert (bpy.data.objects["VChild"].matrix_world.translation - child_world.translation).length < 1e-4
    res1 = build.build(bpy.context, cube)
    vols1 = sorted(round(lib.volume(bpy.data.objects[n]), 1) for n in res1.parts)
    assert all(math.isclose(a, b, rel_tol=1e-4) for a, b in zip(vols0, vols1)), (vols0, vols1)
    ctx.metric("transform_parts", f"{vols0} -> {vols1}")
    bpy.ops.ed.undo()
    cube = bpy.data.objects["VScaled"]
    assert tuple(round(x, 6) for x in cube.scale) == (2.0, 2.0, 2.0), "undo restores the scale"
    # already applied: nothing happens
    plain = lib.make_cube(10.0)
    lib.select_only([plain])
    assert bpy.ops.splitforge.fix_transforms() == {'CANCELLED'}
    # negative scale: normals stay outward
    neg = lib.make_cube(10.0)
    neg.scale = (-1.0, 1.0, 1.0)
    lib.select_only([neg])
    run_fix(bpy.ops.splitforge.fix_transforms)
    assert lib.volume(neg, signed=True) > 0.0 and validate.validate(neg).normals_ok
    # shared mesh
    shared = lib.make_cube(10.0)
    shared.scale = (2.0, 2.0, 2.0)
    twin = shared.copy()
    bpy.context.scene.collection.objects.link(twin)
    lib.select_only([shared])
    expect_error(lambda: bpy.ops.splitforge.fix_transforms(), "shared by 2 objects")

    # --- units -----------------------------------------------------------------------------------
    us = bpy.context.scene.unit_settings
    us.length_unit, us.scale_length = 'METERS', 1.0
    small = lib.make_cube(0.04)
    small.name = "VSmall"
    lib.select_only([small])
    bpy.ops.ed.undo_push(message="meter scene")
    assert not validate.validate(small).unit_is_mm
    run_fix(bpy.ops.splitforge.fix_units, mode='RELABEL')
    us = bpy.context.scene.unit_settings
    assert us.length_unit == 'MILLIMETERS' and math.isclose(us.scale_length, 0.001, rel_tol=1e-6)
    assert math.isclose(bpy.data.objects["VSmall"].dimensions.x, 0.04, rel_tol=1e-6), "relabel keeps units"
    bpy.ops.ed.undo()
    us = bpy.context.scene.unit_settings
    assert us.length_unit == 'METERS' and us.scale_length == 1.0, "undo restores the units"
    run_fix(bpy.ops.splitforge.fix_units, mode='KEEP_SIZE')
    small = bpy.data.objects["VSmall"]
    bpy.context.view_layer.update()
    assert math.isclose(small.dimensions.x, 40.0, rel_tol=1e-5), small.dimensions.x
    assert validate.validate(small).unit_is_mm
    assert bpy.ops.splitforge.fix_units() == {'CANCELLED'}, "already millimeters"
    for o in list(bpy.context.scene.objects):
        bpy.data.objects.remove(o)
    lib.set_scene_mm()

    # --- normals ---------------------------------------------------------------------------------
    flip = lib.make_cube(20.0)
    flip.name = "VFlip"
    bm = bmesh.new()
    bm.from_mesh(flip.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:2])
    bm.to_mesh(flip.data)
    bm.free()
    lib.select_only([flip])
    rep = validate.validate(flip)
    assert rep.flipped_edges > 0 and not rep.normals_ok and not rep.ok, rep
    h = lib.mesh_hash(flip)
    bpy.ops.ed.undo_push(message="flipped")
    run_fix(bpy.ops.splitforge.fix_normals)
    rep = validate.last_report(bpy.data.objects["VFlip"])
    assert rep is not None and rep.normals_ok and lib.volume(bpy.data.objects["VFlip"], signed=True) > 0.0
    bpy.ops.ed.undo()
    assert validate.validate(bpy.data.objects["VFlip"]).flipped_edges > 0, "undo restores the flipped faces"
    inside = lib.make_cube(20.0)
    bm = bmesh.new()
    bm.from_mesh(inside.data)
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    bm.to_mesh(inside.data)
    bm.free()
    lib.select_only([inside])
    rep = validate.validate(inside)
    assert rep.inside_out and rep.flipped_edges == 0, rep
    run_fix(bpy.ops.splitforge.fix_normals)
    assert validate.validate(inside).normals_ok
    assert bpy.ops.splitforge.fix_normals() == {'CANCELLED'}, "nothing left to flip"
    del h

    # --- merge by distance -----------------------------------------------------------------------
    split = lib.make_cube(20.0)
    bm = bmesh.new()
    bm.from_mesh(split.data)
    bmesh.ops.split_edges(bm, edges=bm.edges[:])
    bm.to_mesh(split.data)
    bm.free()
    lib.select_only([split])
    rep = validate.validate(split)
    assert rep.duplicates == 16 and len(split.data.vertices) == 24, (rep.duplicates, len(split.data.vertices))
    run_fix(bpy.ops.splitforge.fix_merge)
    assert len(split.data.vertices) == 8 and validate.validate(split).ok

    # --- holes and loose geometry ----------------------------------------------------------------
    holed = lib.make_cube(20.0)
    holed.name = "VHoled"
    bm = bmesh.new()
    bm.from_mesh(holed.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[0]], context='FACES_ONLY')
    bm.verts.new((50.0, 0.0, 0.0))
    bm.to_mesh(holed.data)
    bm.free()
    lib.select_only([holed])
    rep = validate.validate(holed)
    assert rep.open_edges == 4 and rep.loose_verts == 1 and not rep.manifold, rep
    run_fix(bpy.ops.splitforge.fix_holes)
    rep = validate.validate(holed)
    assert rep.manifold and not rep.loose_geom and rep.normals_ok and lib.is_manifold(holed), rep
    lib.assert_close(lib.volume(holed), 8000.0, rel=1e-6)
    # three faces on one edge: not fixed automatically, mesh untouched, reported
    fin = lib.make_cube(20.0)
    bm = bmesh.new()
    bm.from_mesh(fin.data)
    bm.edges.ensure_lookup_table()
    e = bm.edges[0]
    a, b = e.verts
    out = Vector((50.0, 50.0, 50.0))
    bm.faces.new((a, b, bm.verts.new(out)))
    bm.to_mesh(fin.data)
    bm.free()
    lib.select_only([fin])
    rep = validate.validate(fin)
    assert rep.multi_edges == 1, rep
    bpy.ops.splitforge.fix_holes()
    assert validate.validate(fin).multi_edges == 1, "edges with three faces are left for Edit Mode"

    # --- panel rows ------------------------------------------------------------------------------
    import importlib
    ui = importlib.import_module(ctx.addon_module + ".ui.panel")
    log = []

    class L:
        def __init__(self):
            pass

        def __getattr__(self, name):
            if name in ("row", "column", "box", "split"):
                return lambda *a, **k: L()
            if name == "label":
                return lambda text="", **k: log.append(("label", text))
            if name == "operator":
                return lambda idname, **k: log.append(("operator", idname)) or type("P", (), {})()
            return lambda *a, **k: None

    bad = lib.make_cube(20.0)
    bad.scale = (1.0, 2.0, 1.0)
    lib.select_only([bad])
    ui.draw_checks(bpy.context, L(), bad)
    assert ("operator", "splitforge.fix_transforms") in log and ("label", "Mesh not checked yet") in log, log
    assert ("operator", "splitforge.fix_units") not in log
    log.clear()
    validate.validate(bad)
    ui.draw_checks(bpy.context, L(), bad)
    assert ("label", "Closed (no holes)") in log and ("operator", "splitforge.fix_holes") not in log, log
    log.clear()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.delete(type='ONLY_FACE')
    bpy.ops.object.mode_set(mode='OBJECT')
    ui.draw_checks(bpy.context, L(), bad)
    assert ("label", "Mesh not checked yet") in log, "a changed mesh is not shown with an old report"
