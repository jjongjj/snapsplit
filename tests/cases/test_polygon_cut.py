# SPDX-License-Identifier: GPL-3.0-or-later
"""P4-2: polygon cut (region removal / cut-out).

A square drawn from above (extruded along -Z) on a 40 mm cube:
- Depth 10: two parts, the plug (20 x 20 x 10 = 4000) and the body with a pocket (60000), both
  manifold, sum = cube (2 % allowed, actual exact); part A is the plug.
- Through (Depth 0) with gap 0.4: a column inside the inner offset (19.6^2 x 40) and the rest outside
  the outer offset (64000 - 20.4^2 x 40), each within 0.5 %; pair check passes (A + B + gap = cube).
- A concave (L-shaped) polygon cuts out an L.
- Connectors on the floor of a cut-out: Distribute puts them inside the polygon with the wall
  margin, pins grow the plug and sockets shrink the body, no warnings, assembled pins stay inside
  the pocket walls; a through polygon refuses Distribute with "set a Depth".
- With a Z plane cut through the plug: four parts, and the plane's connectors keep >= 0.4 mm from the
  polygon walls (the polygon is a fit barrier: RibbonBarrier over its prism).
- Invalid polygons are refused with a reason (2 points, crossing edges, outside the object, too
  narrow for the gap); the panel problem check names it; Easy cut-out builds at once.
- Undo after adding restores the stack; the source mesh is never changed.
"""

import math

import bpy
from mathutils import Vector

import lib

SQUARE = [(-10.0, -10.0, 30.0), (10.0, -10.0, 30.0), (10.0, 10.0, 30.0), (-10.0, 10.0, 30.0)]
DOWN = (0.0, 0.0, -1.0)


def add(points, direction=DOWN, **kw):
    return bpy.ops.splitforge.stack_add_polygon(points=[{"name": "", "co": p} for p in points],
                                                direction=direction, **kw)


def new_cube(name):
    cube = lib.make_cube(40.0)
    cube.name = name
    lib.select_only([cube])
    return cube


def expect_error(fn, text):
    try:
        fn()
    except RuntimeError as ex:
        assert text in str(ex), (text, str(ex))
        return str(ex)
    raise AssertionError(f"expected an error containing {text!r}")


def run(ctx):
    build = ctx.module("cuts.build")
    fit = ctx.module("connectors.fit")
    stack_api = ctx.module("model.stack")
    lib.set_scene_mm()

    # --- cut-out with a floor -------------------------------------------------------------------
    cube = new_cube("PG")
    h0 = lib.mesh_hash(cube)
    assert add(SQUARE, depth_mm=10.0) == {'FINISHED'}
    cut = cube.splitforge_stack.cuts[0]
    assert cut.kind == 'POLYGON' and math.isclose(cut.depth_mm, 10.0) and len(cut.points) == 4
    res = build.build(bpy.context, cube)
    a, b = bpy.data.objects["PG_A"], bpy.data.objects["PG_B"]
    assert lib.is_manifold(a) and lib.is_manifold(b)
    lib.assert_close(lib.volume(a), 4000.0, rel=1e-4, msg="plug")
    lib.assert_close(lib.volume(b), 60000.0, rel=1e-4, msg="body")
    lib.assert_close(lib.volume(a) + lib.volume(b), 64000.0, rel=0.02, msg="sum")
    za = [(a.matrix_world @ v.co).z for v in a.data.vertices]
    assert math.isclose(min(za), 10.0, abs_tol=1e-4) and math.isclose(max(za), 20.0, abs_tol=1e-4), (min(za), max(za))
    assert lib.mesh_hash(cube) == h0
    ctx.metric("pocket", f"{lib.volume(a):.1f}/{lib.volume(b):.1f} {res.infos[-1]}")

    # --- connectors on the floor ----------------------------------------------------------------
    lib.select_only([cube])
    cube.hide_set(False)
    assert bpy.ops.splitforge.connector_add_auto() == {'FINISHED'}
    cut = cube.splitforge_stack.cuts[0]
    assert len(cut.connectors) == 2, len(cut.connectors)
    spec = build.cut_spec(cube, cut, bpy.context.scene)
    for c in cut.connectors:
        m = spec.matrix(c.u, c.v, 0.0)
        assert math.isclose(m.translation.z, 10.0, abs_tol=1e-6), m.translation
        assert Vector(m.col[2][:3]).dot(Vector((0, 0, 1))) > 0.999, "pin axis = -d (up into the plug)"
        r = c.width_mm * 0.5 + 0.2
        assert max(abs(m.translation.x), abs(m.translation.y)) + r <= 10.0 - 0.4 + 1e-6, ("too near a wall", m.translation)
    res = build.build(bpy.context, cube)
    assert not res.warnings, res.warnings
    a, b = bpy.data.objects["PG_A"], bpy.data.objects["PG_B"]
    assert lib.is_manifold(a) and lib.is_manifold(b)
    assert lib.volume(a) > 4000.0 and lib.volume(b) < 60000.0, (lib.volume(a), lib.volume(b))
    # the pins (above z = 10 they are the plug, below it they stick into the body) stay inside the walls
    xs = [abs((a.matrix_world @ v.co).x) for v in a.data.vertices if (a.matrix_world @ v.co).z < 9.99]
    assert xs and max(xs) < 10.0 - 0.4, max(xs)
    ctx.metric("floor_pins", f"plug {lib.volume(a):.1f} body {lib.volume(b):.1f}")

    # --- through with a gap ---------------------------------------------------------------------
    col = new_cube("PGT")
    assert add(SQUARE) == {'FINISHED'}
    col.splitforge_stack.cuts[0].gap_mm = 0.4
    res = build.build(bpy.context, col)
    # the pair check (A + B + gap ring = piece) passes on the first, exact attempt
    assert [b[1] for b in res.booleans] == ['EXACT', 'EXACT'] and not res.warnings, (res.booleans, res.warnings)
    a, b = bpy.data.objects["PGT_A"], bpy.data.objects["PGT_B"]
    assert lib.is_manifold(a) and lib.is_manifold(b)
    lib.assert_close(lib.volume(a), 19.6 ** 2 * 40.0, rel=0.005, msg="column")
    lib.assert_close(lib.volume(b), 64000.0 - 20.4 ** 2 * 40.0, rel=0.005, msg="ring")
    lib.select_only([col])
    col.hide_set(False)
    expect_error(lambda: bpy.ops.splitforge.connector_add_auto(), "set a Depth")

    # --- concave L ------------------------------------------------------------------------------
    ell = new_cube("PGL")
    L = [(-15, -15, 30), (15, -15, 30), (15, -5, 30), (-5, -5, 30), (-5, 15, 30), (-15, 15, 30)]
    assert add(L, depth_mm=5.0) == {'FINISHED'}
    build.build(bpy.context, ell)
    a = bpy.data.objects["PGL_A"]
    lib.assert_close(lib.volume(a), (30 * 10 + 10 * 20) * 5.0, rel=1e-4, msg="L plug")
    assert lib.is_manifold(a) and lib.is_manifold(bpy.data.objects["PGL_B"])

    # --- with a plane through the plug: four parts, plane connectors keep off the polygon walls ---
    mix = new_cube("PGM")
    assert add(SQUARE, depth_mm=30.0) == {'FINISHED'}     # floor at z = -10
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z', offset_mm=0.0)
    stack = mix.splitforge_stack
    stack.active_index = 1
    bpy.context.scene.splitforge.new_connector.width_mm = 4.0
    stack.cuts[1].distribution, stack.cuts[1].connector_count, stack.cuts[1].connector_rows = 'GRID', 4, 4
    assert bpy.ops.splitforge.connector_add_auto() == {'FINISHED'}
    plane_cut = stack.cuts[1]
    assert len(plane_cut.connectors) >= 4, len(plane_cut.connectors)
    barrier = build.cut_spec(mix, stack.cuts[0], bpy.context.scene).barrier()
    pspec = build.cut_spec(mix, plane_cut, bpy.context.scene)
    inside = 0
    for i, c in enumerate(plane_cut.connectors):
        cs = build.make_spec(mix, plane_cut, bpy.context.scene, "", c.u, c.v, 0.0, c.kind, c.width_mm, c.height_mm,
                             c.length_mm, 0.2, 'A', pspec)
        margin = min(fit.plane_margin(cs, [barrier], side, 1.0) for side in (True, False))
        assert margin >= 0.4 - 1e-6, (i, margin)
        inside += barrier.positive(cs.matrix.translation)
    assert 0 < inside < len(plane_cut.connectors), ("connectors in both the plug and the ring", inside)
    res = build.build(bpy.context, mix)
    assert len(res.parts) == 4 and not res.warnings, (res.parts, res.warnings)
    assert all(lib.is_manifold(bpy.data.objects[n]) for n in res.parts)
    ctx.metric("mixed", f"{len(plane_cut.connectors)} plane connectors, {inside} in the plug")

    # --- invalid polygons -----------------------------------------------------------------------
    bad = new_cube("PGBad")
    expect_error(lambda: add(SQUARE[:2]), "at least 3 points")
    expect_error(lambda: add([SQUARE[0], SQUARE[2], SQUARE[1], SQUARE[3]]), "crosses itself")
    expect_error(lambda: add([(x + 100.0, y, z) for x, y, z in SQUARE]), "does not cross")
    expect_error(lambda: add([(-60, -60, 30), (60, -60, 30), (60, 60, 30), (-60, 60, 30)]), "does not cross")
    bpy.context.scene.splitforge.easy_gap_mm = 3.0
    expect_error(lambda: add([(-10, -1, 30), (10, -1, 30), (10, 1, 30), (-10, 1, 30)], easy=True),
                 "too narrow or too sharp for its gap")
    assert len(bad.splitforge_stack.cuts) == 0
    # a stored polygon that became too narrow: the panel check names it
    assert add([(-10, -1, 30), (10, -1, 30), (10, 1, 30), (-10, 1, 30)]) == {'FINISHED'}
    narrow = bad.splitforge_stack.cuts[0]
    assert stack_api.stroke_problem_cached(bad, narrow, bpy.context.scene) == ""
    narrow.gap_mm = 3.0
    assert "too narrow" in stack_api.stroke_problem_cached(bad, narrow, bpy.context.scene)
    narrow.gap_mm = 0.0

    # --- D21: too small to cut out (refused at add time and by the panel check); 0.5 mm builds ---------
    tiny = new_cube("PGTiny")
    for side in (0.01, 0.1, 0.4):
        sq = [(0.0, 0.0, 30.0), (side, 0.0, 30.0), (side, side, 30.0), (0.0, side, 30.0)]
        expect_error(lambda: add(sq, depth_mm=5.0), "too small or too narrow")
    expect_error(lambda: add([(-10, 0, 30), (10, 0, 30), (10, 0.2, 30), (-10, 0.2, 30)], depth_mm=5.0),
                 "too small or too narrow")
    assert len(tiny.splitforge_stack.cuts) == 0
    half_mm = [(0.0, 0.0, 30.0), (0.5, 0.0, 30.0), (0.5, 0.5, 30.0), (0.0, 0.5, 30.0)]
    assert add(half_mm, depth_mm=5.0) == {'FINISHED'}
    res = build.build(bpy.context, tiny)
    assert len(res.parts) == 2 and [b[1] for b in res.booleans] == ['EXACT', 'EXACT'], (res.parts, res.booleans)
    stored = tiny.splitforge_stack.cuts[0]
    for p, co in zip(stored.points, [(0, 0, 30), (0.05, 0, 30), (0.05, 0.05, 30), (0, 0.05, 30)]):
        p.co = co
    assert "too small" in stack_api.stroke_problem_cached(tiny, stored, bpy.context.scene)
    lib.select_only([tiny])
    tiny.hide_set(False)
    expect_error(lambda: bpy.ops.splitforge.build(), "too small")

    # --- Easy cut-out ---------------------------------------------------------------------------
    easy = new_cube("PGE")
    s = bpy.context.scene.splitforge
    s.easy_gap_mm, s.easy_depth_mm, s.easy_connector_count = 0.2, 12.0, 2
    assert add(SQUARE, easy=True) == {'FINISHED'}
    cut = easy.splitforge_stack.cuts[0]
    assert math.isclose(cut.depth_mm, 12.0) and len(cut.connectors) == 2
    assert all(lib.is_manifold(bpy.data.objects[n]) for n in ("PGE_A", "PGE_B"))
    # Easy through-polygon: built without connectors (info)
    easy2 = new_cube("PGE2")
    s.easy_depth_mm = 0.0
    assert add(SQUARE, easy=True) == {'FINISHED'}
    assert len(easy2.splitforge_stack.cuts[0].connectors) == 0
    assert "PGE2_A" in bpy.data.objects

    # --- undo -----------------------------------------------------------------------------------
    target = new_cube("PGU")
    bpy.ops.ed.undo_push(message="before")
    assert add(SQUARE, depth_mm=5.0) == {'FINISHED'}
    bpy.ops.ed.undo_push(message="polygon")
    bpy.ops.ed.undo()
    assert len(bpy.data.objects["PGU"].splitforge_stack.cuts) == 0
