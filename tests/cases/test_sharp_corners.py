# SPDX-License-Identifier: GPL-3.0-or-later
"""D20: sharp polyline / polygon corners with a gap.

The offset ribbons used clamped mitres (at most 4 x the offset at a corner): on a sparse polyline the
clamped corner tilted the whole neighbouring segments, so the kerf shrank along them and the Build pair
check (A + B + gap x seam area = piece) failed with every solver ("no solver left"). Now the mitres are
exact and corners under 15 degrees are refused when there is a gap, at add time and by the panel check.

For V-shaped polylines (corner 10/15/20/25/40 degrees) x gap 0 / 0.3 / 1 mm on a 40 mm cube:
- gap 0: always builds (no offsets);
- corner >= 15 degrees: builds on the first exact attempt (EXACT x 2, no retry, no warning), A + B = cube
  minus the slab, and the parts stay a full gap apart everywhere (kerf uniform, >= 0.99 x gap);
- corner 10 degrees with a gap: refused at add time and by the panel check with the corner angle.
A polygon with a 20 degree spike and gap 1 builds the same way; a 10 degree spike with a gap is refused.
"""

import math

import bpy
from mathutils.bvhtree import BVHTree

import lib


def vee(angle, apex_z=-8.0, arm=45.0):
    h = math.radians(angle) * 0.5
    return [(-arm * math.sin(h), 0.0, apex_z + arm * math.cos(h)), (0.0, 0.0, apex_z),
            (arm * math.sin(h), 0.0, apex_z + arm * math.cos(h))]


def min_gap(a, b):
    bm_a, bm_b = lib.bm_of(a), lib.bm_of(b)
    try:
        tree = BVHTree.FromBMesh(bm_b)
        return min(tree.find_nearest(v.co)[3] for v in bm_a.verts)
    finally:
        bm_a.free()
        bm_b.free()


def expect_error(fn, text):
    try:
        fn()
    except RuntimeError as ex:
        assert text in str(ex), (text, str(ex))
        return str(ex)
    raise AssertionError(f"expected an error containing {text!r}")


def run(ctx):
    build = ctx.module("cuts.build")
    stack_api = ctx.module("model.stack")
    lib.set_scene_mm()
    for angle in (10, 15, 20, 25, 40):
        for gap in (0.0, 0.3, 1.0):
            name = f"V{angle}_{gap:g}"
            cube = lib.make_cube(40.0)
            cube.name = name
            lib.select_only([cube])
            bpy.context.scene.splitforge.easy_gap_mm = gap

            def add():
                return bpy.ops.splitforge.stack_add_polyline(points=[{"name": "", "co": p} for p in vee(angle)],
                                                             direction=(0.0, 1.0, 0.0), easy=gap > 0.0)
            if angle < 15 and gap > 0.0:
                msg = expect_error(add, "too sharp for a gap")
                assert f"{angle:.1f} degrees" in msg and "at least 15" in msg, msg
                assert len(cube.splitforge_stack.cuts) == 0
                # a stored cut whose gap is raised later: the panel check names it
                bpy.ops.splitforge.stack_add_polyline(points=[{"name": "", "co": p} for p in vee(angle)],
                                                      direction=(0.0, 1.0, 0.0))
                cut = cube.splitforge_stack.cuts[0]
                cut.gap_mm = gap
                assert "too sharp for a gap" in stack_api.stroke_problem_cached(cube, cut, bpy.context.scene)
                ctx.metric(name, "refused")
                continue
            bpy.context.scene.splitforge.easy_connector_count = 0
            if gap == 0.0:
                assert add() == {'FINISHED'}
                res = build.build(bpy.context, cube)
            else:
                assert add() == {'FINISHED'}, name          # Easy: add + build in one step
                cube.hide_set(False)
                lib.select_only([cube])
                res = build.build(bpy.context, cube)
            assert [b[1] for b in res.booleans] == ['EXACT', 'EXACT'] and not res.warnings, \
                (name, res.booleans, res.warnings)
            a, b = bpy.data.objects[f"{name}_A"], bpy.data.objects[f"{name}_B"]
            assert lib.is_manifold(a) and lib.is_manifold(b), name
            if gap > 0.0:
                got = min_gap(a, b)
                assert got >= 0.99 * gap, (name, "kerf narrower than the gap", got)
                ctx.metric(name, f"min kerf {got:.4f}")
    # polygons: a 20 degree spike with gap 1 builds exactly; a 10 degree spike with a gap is refused
    for angle, ok in ((20, True), (10, False)):
        cube = lib.make_cube(40.0)
        cube.name = f"P{angle}"
        lib.select_only([cube])
        h = math.radians(angle) * 0.5
        tri = [(0.0, -12.0, 30.0), (30.0 * math.sin(h), -12.0 + 30.0 * math.cos(h), 30.0),
               (-30.0 * math.sin(h), -12.0 + 30.0 * math.cos(h), 30.0)]
        bpy.context.scene.splitforge.easy_gap_mm = 1.0

        def add_poly():
            return bpy.ops.splitforge.stack_add_polygon(points=[{"name": "", "co": p} for p in tri],
                                                        direction=(0.0, 0.0, -1.0), easy=True, depth_mm=0.0)
        if not ok:
            expect_error(add_poly, "too sharp for a gap")
            continue
        assert add_poly() == {'FINISHED'}
        a, b = bpy.data.objects[f"P{angle}_A"], bpy.data.objects[f"P{angle}_B"]
        assert lib.is_manifold(a) and lib.is_manifold(b)
        assert min_gap(a, b) >= 0.99 * 1.0, min_gap(a, b)     # inner and outer walls a full gap apart
