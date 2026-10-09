# SPDX-License-Identifier: GPL-3.0-or-later
"""Stroke cuts on moved / rotated / non-uniformly scaled objects.

The stroke is stored in object space (points and direction), so:
- a stroke added on a transformed object cuts where it was drawn (world space): the
  parts equal those of the same stroke on a copy with the transform applied;
- moving / rotating the object afterwards moves the cut with it (the parts follow the
  object, same volumes, same part shapes up to the transform);
- connectors (u, v in mm along the ribbon) land on the world-space ribbon.
"""

import math

import bpy
from mathutils import Euler, Matrix, Vector

import lib

D = Vector((0.3, 1.0, -0.2)).normalized()


def stroke_points():
    return [(-30.0 + 60.0 * i / 29 + 5.0, 2.0, 3.0 + 6.0 * math.sin(2 * math.pi * i / 29)) for i in range(30)]


def add_stroke(points, direction):
    lib.run_op(bpy.ops.splitforge.stack_add_stroke, points=[{"name": "", "co": p} for p in points],
               direction=tuple(direction))


def parts(name):
    return {o.name[len(name) + 1:]: o for o in bpy.data.objects if o.get("splitforge_source") == name}


def world_vertices(obj):
    return sorted(tuple(round(c, 2) for c in obj.matrix_world @ v.co) for v in obj.data.vertices)


def run(ctx):
    build = ctx.module("cuts.build")
    lib.set_scene_mm()
    transform = (Matrix.Translation((5.0, -3.0, 2.0)) @ Euler((0.3, -0.2, 0.7)).to_matrix().to_4x4()
                 @ Matrix.Diagonal((1.5, 1.0, 0.7, 1.0)))

    # Transformed object
    obj = lib.make_cube(40.0)
    obj.name = "Moved"
    obj.matrix_world = transform
    bpy.context.view_layer.update()
    lib.select_only([obj])
    add_stroke(stroke_points(), D)
    cut = obj.splitforge_stack.cuts[0]
    cut.gap_mm = 0.4
    c = cut.connectors.add()
    c.u, c.v = 4.0, 3.0
    local = [tuple(p.co) for p in cut.points]
    assert any(abs(a - b) > 1.0 for p, q in zip(local, stroke_points()) for a, b in zip(p, q)), \
        "points must be stored in object space"
    res = build.build(bpy.context, obj)
    assert not res.warnings, res.warnings
    moved = parts("Moved")

    # Same stroke on a copy with the transform applied
    ref = lib.make_cube(40.0)
    ref.name = "Applied"
    ref.data.transform(transform)
    lib.select_only([ref])
    add_stroke(stroke_points(), D)
    rcut = ref.splitforge_stack.cuts[0]
    rcut.gap_mm = 0.4
    rc = rcut.connectors.add()
    rc.u, rc.v = 4.0, 3.0
    build.build(bpy.context, ref)
    applied = parts("Applied")
    assert sorted(moved) == sorted(applied) == ["A", "B"], (sorted(moved), sorted(applied))
    for side in ("A", "B"):
        assert lib.is_manifold(moved[side])
        lib.assert_close(lib.volume(moved[side]), lib.volume(applied[side]), rel=0.002, msg=f"side {side}")
        a, b = world_vertices(moved[side]), world_vertices(applied[side])
        lib.assert_close(min(p[2] for p in a), min(p[2] for p in b), abs_=0.05)
        lib.assert_close(max(p[0] for p in a), max(p[0] for p in b), abs_=0.05)
    # The pin landed on the world-space ribbon at the same place in both
    s1 = build.connector_specs(obj, [cut], bpy.context.scene, bpy.context.scene.splitforge)[0]
    s2 = build.connector_specs(ref, [rcut], bpy.context.scene, bpy.context.scene.splitforge)[0]
    assert (s1.matrix.translation - s2.matrix.translation).length < 0.05, (s1.matrix.translation,
                                                                          s2.matrix.translation)

    # Moving the object afterwards moves the cut with it
    before = {k: lib.volume(p) for k, p in moved.items()}
    lib.select_only([obj])
    obj.hide_set(False)
    shift = Matrix.Translation((30.0, 10.0, -5.0)) @ Euler((0.0, 0.0, 0.5)).to_matrix().to_4x4()
    obj.matrix_world = shift @ obj.matrix_world
    bpy.context.view_layer.update()
    build.build(bpy.context, obj)
    after = parts("Moved")
    for side in ("A", "B"):
        lib.assert_close(lib.volume(after[side]), before[side], rel=0.002, msg=f"moved side {side}")
        expected = sorted(tuple(round(c, 1) for c in shift @ Vector(v)) for v in world_vertices(applied[side]))
        got = sorted(tuple(round(c, 1) for c in v) for v in world_vertices(after[side]))
        lib.assert_close(min(p[0] for p in got), min(p[0] for p in expected), abs_=0.1)
        lib.assert_close(max(p[2] for p in got), max(p[2] for p in expected), abs_=0.1)
