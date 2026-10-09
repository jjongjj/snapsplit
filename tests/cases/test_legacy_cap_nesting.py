# SPDX-License-Identifier: GPL-3.0-or-later
"""Legacy auto-cap: loop nesting (hole vs. separate outline) must not depend on loop start vertex.

Regression for a flaky test_perf_large: the cut through Suzanne's eyes gives eye
loops that partly stick out of the head loop. Nesting used to be decided by the
loop's first vertex, which comes from set iteration order (varies per run), so
the eyes were sometimes treated as holes -> uncapped eye loops, ~243
non-manifold edges.
"""

import bpy

import lib


def _rotations(pts):
    return [pts[i:] + pts[:i] for i in range(len(pts))]


def run(ctx):
    ops_split = ctx.module("ops_split")
    outer = [(-20.0, -20.0), (20.0, -20.0), (20.0, 20.0), (-20.0, 20.0)]
    nested = [(-5.0, -5.0), (5.0, -5.0), (5.0, 5.0), (-5.0, 5.0)]
    straddling = [(15.0, -5.0), (25.0, -5.0), (25.0, 5.0), (15.0, 5.0)]
    for pts in _rotations(nested):
        assert ops_split._loop_inside_loop_2d(pts, outer), pts
    for pts in _rotations(straddling):
        assert not ops_split._loop_inside_loop_2d(pts, outer), pts

    # End to end: a small cube straddling the side wall of a big cube (two
    # intersecting closed shells in one mesh), split through both, repeated so
    # a start-vertex dependent result shows up (old code: random per run).
    results = []
    for _ in range(12):
        bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
        lib.set_scene_mm()
        big = lib.make_cube(40.0)
        bpy.ops.mesh.primitive_cube_add(size=10.0, location=(20.0, 0.0, 0.0))
        small = bpy.context.active_object
        lib.select_only([big, small], active=big)
        bpy.ops.object.join()
        props = bpy.context.scene.snapsplit
        props.split_axis = 'Z'
        props.parts_count = 2
        lib.run_op(bpy.ops.snapsplit.planar_split)
        parts = sorted((o for o in bpy.context.selected_objects if o.type == 'MESH'),
                       key=lambda o: o.name)
        assert len(parts) == 2, [o.name for o in parts]
        for p in parts:
            assert lib.is_manifold(p), f"{p.name} not manifold"
        # Each shell capped on its own: signed volumes add up to 40^3 + 10^3
        lib.assert_close(sum(lib.volume(p, signed=True) for p in parts), 65000.0,
                         rel=0.001, msg="part volume sum")
        results.append([len(p.data.polygons) for p in parts])
    assert all(r == results[0] for r in results), f"non-deterministic caps: {results}"
