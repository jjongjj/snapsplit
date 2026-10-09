# SPDX-License-Identifier: GPL-3.0-or-later
"""D7: a connector never reaches across ANOTHER cut into a third part.

Verifier's repro: 40 mm cube, Z cut at -6 mm + oblique cut (origin (0,0,2), normal
(1, 0.2, 1.2), gap 0.5). Before the fix the Z-cut connector near (16.4, -14, -6) on
part AA reached 2.64 mm into part BB beyond the oblique cut (no socket there: the
parts collide on assembly, no warning). Now Distribute and Build test every pin and
socket against all other enabled cut planes (beyond their half gap + wall).

Also: the connector spacing rule (sockets at least MIN_WALL_MM apart) is checked on
a seam asked for more connectors than fit; without the rule they overlap.
"""

import math

import bmesh
import bpy
from mathutils.bvhtree import BVHTree

import lib


def _bvh(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    try:
        return BVHTree.FromBMesh(bm)
    finally:
        bm.free()


def _setup(name):
    cube = lib.make_cube(40.0)
    cube.name = name
    lib.select_only([cube])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z', offset_mm=-6.0)
    lib.run_op(bpy.ops.splitforge.stack_add_plane, use_plane=True, origin=(0.0, 0.0, 2.0),
               normal=(1.0, 0.2, 1.2))
    cube.splitforge_stack.cuts[1].gap_mm = 0.5
    return cube


def run(ctx):
    build = ctx.module("cuts.build")
    fit = ctx.module("connectors.fit")
    auto = ctx.module("connectors.auto")
    lib.set_scene_mm()
    scene = bpy.context.scene

    # The scenario is meaningful: the old placement (2D distribution of the Z seam,
    # no 3D checks) put a connector across the oblique cut
    cube = _setup("Steep")
    stack = cube.splitforge_stack
    planes = build.fit_planes(cube, list(stack.cuts), scene)
    old = build.make_spec(cube, stack.cuts[0], scene, "old", 16.4, -14.0, 0.0, 'CYL_PIN', 5.0, 5.0, 10.0,
                          0.2, 'A')
    assert fit.plane_margin(old, [planes[stack.cuts[1].uid]]) < -1.0, "repro position should cross the cut"

    for i in range(2):
        res = auto.add_auto(bpy.context, cube, stack.cuts[i], 'CYL_PIN', 5.0, 5.0, 10.0)
        ctx.metric(f"cut{i}", f"{res.added}/{res.moved}/{res.dropped}")
        assert res.added >= 1, (i, res)
    wall = auto.MIN_WALL_MM
    for spec in build.connector_specs(cube, list(stack.cuts), scene, scene.splitforge):
        others = [pl for uid, pl in planes.items() if uid != spec.cut_uid]
        margin = min(fit.plane_margin(spec, others, side) for side in (True, False))
        assert margin >= wall - 1e-6, (spec.label, margin)

    # Build: no warning, and no part reaches into another part
    result = build.build(bpy.context, cube)
    assert not result.warnings, result.warnings
    parts = [bpy.data.objects[n] for n in result.parts]
    assert len(parts) == 4
    bvhs = {p.name: _bvh(p) for p in parts}
    for a in parts:
        for b in parts:
            if a is b:
                continue
            inside = [v.co for v in a.data.vertices
                      if fit.depth_inside(bvhs[b.name], a.matrix_world @ v.co) > 1e-3]
            assert not inside, f"{len(inside)} vertices of {a.name} inside {b.name}, e.g. {tuple(inside[0])}"

    # Build skips (with a warning) a manually placed connector that crosses the other cut
    c = stack.cuts[0].connectors.add()
    c.u, c.v = 16.4, -14.0
    result = build.build(bpy.context, cube)
    assert any("across another cut" in w for w in result.warnings), result.warnings
    parts = [bpy.data.objects[n] for n in result.parts]
    bvhs = {p.name: _bvh(p) for p in parts}
    for a in parts:
        for b in parts:
            if a is not b:
                assert not any(fit.depth_inside(bvhs[b.name], a.matrix_world @ v.co) > 1e-3
                               for v in a.data.vertices), (a.name, b.name)

    # Spacing rule: 8 pins asked on a 40 mm seam (4.8 mm apart, sockets 5.4 mm wide)
    dense = lib.make_cube(40.0)
    dense.name = "Dense"
    lib.select_only([dense])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    cut = dense.splitforge_stack.cuts[0]
    cut.connector_count, cut.margin_pct = 8, 0.0
    res = auto.add_auto(bpy.context, dense, cut, 'CYL_PIN', 5.0, 5.0, 10.0)
    pts = [(c.u, c.v) for c in cut.connectors]
    spacing = 2 * (2.5 + scene.splitforge.clearance_mm) + auto.MIN_WALL_MM
    gaps = [math.dist(p, q) for i, p in enumerate(pts) for q in pts[i + 1:]]
    assert len(pts) >= 2 and min(gaps) >= spacing - 1e-9, (pts, spacing)
    assert res.dropped + res.moved > 0, res
