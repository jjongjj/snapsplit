# SPDX-License-Identifier: GPL-3.0-or-later
"""D1: connectors on an oblique cut never break through the outer surface.

Repro of the verifier's live case (qa4/probe_protrude.py): 40 mm cube, Z cut at -5 mm
and an oblique gapped cut (origin (3,0,0), normal (1,0.6,0.35), gap 0.5). Before the
fix 4 of 8 auto connectors stuck 0.4-1.65 mm out of the cube and one socket cut
through the wall. Now Distribute insets each seam region by the connector reach,
checks pin and socket in 3D (both pin sides), moves misfits inward or drops them;
Build skips (with a warning) any connector that would break through.
"""

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import lib

HALF = 20.0


def _outside(obj):
    """Largest distance of a vertex outside the 40 mm cube (<= 0: inside)."""
    return max(max(abs(c) for c in (obj.matrix_world @ v.co)) - HALF for v in obj.data.vertices)


def _source_bvh(obj):
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    try:
        return BVHTree.FromBMesh(bm)
    finally:
        bm.free()


def run(ctx):
    build = ctx.module("cuts.build")
    fit = ctx.module("connectors.fit")
    auto = ctx.module("connectors.auto")
    lib.set_scene_mm()
    cube = lib.make_cube(40.0)
    cube.name = "FitCube"
    lib.select_only([cube])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z', offset_mm=-5.0)
    lib.run_op(bpy.ops.splitforge.stack_add_plane, use_plane=True, origin=(3.0, 0.0, 0.0),
               normal=(1.0, 0.6, 0.35))
    stack = cube.splitforge_stack
    stack.cuts[1].gap_mm = 0.5
    results = []
    for i in range(2):
        cut = stack.cuts[i]
        results.append(auto.add_auto(bpy.context, cube, cut, 'CYL_PIN', 5.0, 5.0, 10.0))
    oblique = results[1]
    ctx.metric("oblique_added", oblique.added)
    ctx.metric("oblique_moved", oblique.moved)
    ctx.metric("oblique_dropped", oblique.dropped)
    assert oblique.added >= 2, oblique
    assert oblique.moved + oblique.dropped > 0, f"the repro positions should not all fit as distributed: {oblique}"

    # Every connector (both pin sides) keeps >= MIN_WALL_MM of material
    bvh = _source_bvh(cube)
    specs = build.connector_specs(cube, list(stack.cuts), bpy.context.scene, bpy.context.scene.splitforge)
    assert len(specs) == sum(r.added for r in results)
    for spec in specs:
        depth = fit.worst_depth(bvh, spec, both_sides=True)
        assert depth >= auto.MIN_WALL_MM - 1e-6, (spec.label, depth)

    # Build: no warnings, outer surface unchanged (no vertex outside the cube)
    result = build.build(bpy.context, cube)
    assert not result.warnings, result.warnings
    parts = [bpy.data.objects[n] for n in result.parts]
    assert len(parts) == 4
    for p in parts:
        assert lib.is_manifold(p), p.name
        out = _outside(p)
        assert out <= 1e-4, f"{p.name}: {out:.3f} mm outside the original surface"
    # The connectors really are applied: compare with a build without them
    with_conn = {p.name: lib.volume(p) for p in parts}
    for cut in stack.cuts:
        for c in cut.connectors:
            c.enabled = False
    plain = build.build(bpy.context, cube)
    without = {n: lib.volume(bpy.data.objects[n]) for n in plain.parts}
    changed = [n for n in with_conn if abs(with_conn[n] - without[n]) > 1.0]
    assert len(changed) == 4, (with_conn, without)
    for cut in stack.cuts:
        for c in cut.connectors:
            c.enabled = True

    # A manually placed connector at the edge is skipped by Build with a warning
    cut0 = stack.cuts[0]
    c = cut0.connectors.add()
    c.u, c.v = 18.5, 0.0
    lib.select_only([cube])
    cube.hide_set(False)
    result = build.build(bpy.context, cube)
    assert any("break through" in w for w in result.warnings), result.warnings
    for name in result.parts:
        assert _outside(bpy.data.objects[name]) <= 1e-4, name

    # The fit check itself: centered pin fits, the edge pin does not
    spec_edge = build.make_spec(cube, cut0, bpy.context.scene, "edge", 18.5, 0.0, 0.0, 'CYL_PIN',
                                5.0, 5.0, 10.0, 0.2, 'A')
    spec_mid = build.make_spec(cube, cut0, bpy.context.scene, "mid", 0.0, 0.0, 0.0, 'CYL_PIN',
                               5.0, 5.0, 10.0, 0.2, 'A')
    assert fit.worst_depth(bvh, spec_edge) < 0.0 < fit.worst_depth(bvh, spec_mid)

    # Seam too small for the connector: nothing added, nothing changed
    thin = lib.make_cube(4.0)
    thin.name = "Thin"
    lib.select_only([thin])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    res = auto.add_auto(bpy.context, thin, thin.splitforge_stack.cuts[0], 'CYL_PIN', 5.0, 5.0, 10.0)
    assert res.added == 0 and len(thin.splitforge_stack.cuts[0].connectors) == 0, res

    # Moving misfits inward never stacks connectors on top of each other
    monkey = lib.make_monkey_manifold(80.0)
    lib.select_only([monkey])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z', offset_mm=-10.0)
    mcut = monkey.splitforge_stack.cuts[0]
    mcut.connector_count = 3
    res = auto.add_auto(bpy.context, monkey, mcut, 'CYL_PIN', 5.0, 5.0, 10.0)
    assert res.added >= 1, res
    spacing = 2 * (2.5 + bpy.context.scene.splitforge.clearance_mm) + auto.MIN_WALL_MM
    pts = [(c.u, c.v) for c in mcut.connectors]
    for i, p in enumerate(pts):
        for q in pts[i + 1:]:
            assert ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5 >= spacing - 1e-9, pts
