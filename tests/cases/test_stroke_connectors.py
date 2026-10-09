# SPDX-License-Identifier: GPL-3.0-or-later
"""P2-5: connectors on curved seams, and the fit check generalised to stroke cuts.

- S stroke through a cube + Distribute (CYL_PIN): positions on the unrolled ribbon
  (u = arc length, v = depth), each pin axis parallel to the ribbon's local normal
  (< 2 deg against the actual ribbon face under the pin), centers on the ribbon,
  Build manifold, connectors applied (pin part gains, socket part loses volume).
- Own seam: on a V-shaped stroke a pin at the apex would cross its own seam again;
  Build skips a manual connector there ("bends into"), Distribute does not place one.
- Other cut = stroke: Distribute on a Z plane crossed by a vertical S stroke never puts
  a pin across the ribbon (RibbonBarrier margin >= wall); a manual connector across it
  is skipped by Build ("across another cut"); Distribute on the stroke cut with the Z
  cut present keeps away from the plane; no part reaches into another.
"""

import math

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import lib

D = (0.0, 1.0, 0.0)


def add_stroke(points, direction=D):
    lib.run_op(bpy.ops.splitforge.stack_add_stroke, points=[{"name": "", "co": p} for p in points],
               direction=direction)


def s_points(z_amp=6.0, n=40):
    return [(-26.0 + 52.0 * i / (n - 1), 0.0, z_amp * math.sin(2 * math.pi * i / (n - 1))) for i in range(n)]


def parts_of(name):
    return sorted((o for o in bpy.data.objects if o.get("splitforge_source") == name), key=lambda o: o.name)


def no_interpenetration(fit, parts):
    bvhs = {}
    for p in parts:
        bm = lib.bm_of(p)
        bvhs[p.name] = BVHTree.FromBMesh(bm)
        bm.free()
    for a in parts:
        for b in parts:
            if a is not b:
                bad = [v.co for v in a.data.vertices if fit.depth_inside(bvhs[b.name], a.matrix_world @ v.co) > 1e-3]
                assert not bad, f"{len(bad)} vertices of {a.name} inside {b.name}, e.g. {tuple(bad[0])}"


def run(ctx):
    build = ctx.module("cuts.build")
    stroke = ctx.module("cuts.stroke")
    fit = ctx.module("connectors.fit")
    auto = ctx.module("connectors.auto")
    lib.set_scene_mm()
    scene = bpy.context.scene
    wall = auto.MIN_WALL_MM

    # --- S seam: distribute, frame, build ------------------------------------------------
    cube = lib.make_cube(40.0)
    cube.name = "SConn"
    lib.select_only([cube])
    add_stroke(s_points())
    cut = cube.splitforge_stack.cuts[0]
    cut.gap_mm = 0.3
    cut.connector_count = 2
    lib.run_op(bpy.ops.splitforge.connector_add_auto)
    assert len(cut.connectors) >= 2, len(cut.connectors)
    ctx.metric("s_connectors", ";".join(f"{c.u:.1f},{c.v:.1f}" for c in cut.connectors))
    spec = build.cut_spec(cube, cut, scene)
    rib = spec.cutter.ribbon()
    ribbon_bvh = BVHTree.FromBMesh(rib)
    rib.free()
    worst = 0.0
    for cspec in build.connector_specs(cube, [cut], scene, scene.splitforge):
        center = cspec.matrix.translation
        axis = Vector(cspec.matrix.col[2][:3]).normalized()
        hit, normal, _i, dist = ribbon_bvh.find_nearest(center)
        off = stroke.distance_to_polyline(spec.cutter.frame.to2d(center), spec.cutter.curve)
        assert off < 1e-5 and dist < 1e-3, f"{cspec.label}: center {off:.6f} / {dist:.4f} off the ribbon"
        angle = math.degrees(axis.angle(normal))
        angle = min(angle, 180.0 - angle)
        worst = max(worst, angle)
        # Pin axis = local ribbon normal = tangent x d: perpendicular to the extrusion direction
        assert abs(axis.dot(Vector(D))) < 1e-9
    ctx.metric("worst_axis_deg", round(worst, 3))
    assert worst < 2.0, worst
    # A record's (u, v) maps to arc length / depth: v moves the pin along d only
    c0 = cut.connectors[0]
    m0 = build.make_spec(cube, cut, scene, "", c0.u, c0.v, 0.0, 'CYL_PIN', 5, 5, 10, 0.2, 'A', spec).matrix
    m1 = build.make_spec(cube, cut, scene, "", c0.u, c0.v + 3.0, 0.0, 'CYL_PIN', 5, 5, 10, 0.2, 'A', spec).matrix
    assert (m1.translation - m0.translation - Vector(D) * 3.0).length < 1e-6

    plain_volumes = None
    for enabled in (False, True):
        for c in cut.connectors:
            c.enabled = enabled
        lib.select_only([cube])
        cube.hide_set(False)
        result = build.build(bpy.context, cube)
        assert not result.warnings, result.warnings
        parts = parts_of("SConn")
        assert len(parts) == 2 and all(lib.is_manifold(p) for p in parts)
        volumes = {p.name: lib.volume(p) for p in parts}
        if not enabled:
            plain_volumes = volumes
    pin_part = "SConn_A" if c0.pin_side == 'A' else "SConn_B"
    sock_part = "SConn_B" if pin_part == "SConn_A" else "SConn_A"
    assert volumes[pin_part] > plain_volumes[pin_part] + 10.0, (volumes, plain_volumes)
    assert volumes[sock_part] < plain_volumes[sock_part] - 10.0, (volumes, plain_volumes)
    no_interpenetration(fit, parts_of("SConn"))

    # --- own seam: V stroke, pin at the apex ---------------------------------------------
    vcube = lib.make_cube(40.0)
    vcube.name = "VConn"
    lib.select_only([vcube])
    add_stroke([(-26.0, 0.0, 22.0), (0.0, 0.0, -4.0), (26.0, 0.0, 22.0)])
    vcut = vcube.splitforge_stack.cuts[0]
    apex = vcut.connectors.add()
    apex.u, apex.v = 0.0, 0.0
    leg = vcut.connectors.add()
    leg.u, leg.v = -14.0, 0.0
    result = build.build(bpy.context, vcube)
    bends = [w for w in result.warnings if "bends into" in w]
    assert len(bends) == 1 and "connector 1" in bends[0], result.warnings
    vspec = build.cut_spec(vcube, vcut, scene)
    apex_spec = build.make_spec(vcube, vcut, scene, "", 0.0, 0.0, 0.0, 'CYL_PIN', 5, 5, 10, 0.2, 'A', vspec)
    assert fit.own_margin(apex_spec, vspec.barrier()) < 0.0
    leg_spec = build.make_spec(vcube, vcut, scene, "", -14.0, 0.0, 0.0, 'CYL_PIN', 5, 5, 10, 0.2, 'A', vspec)
    assert fit.own_margin(leg_spec, vspec.barrier()) > 0.0
    vcut.connectors.clear()
    vcut.connector_count = 3
    vcut.margin_pct = 0.0
    lib.select_only([vcube])
    vcube.hide_set(False)
    res = auto.add_auto(bpy.context, vcube, vcut, 'CYL_PIN', 5.0, 5.0, 10.0)
    for c in vcut.connectors:
        cs = build.make_spec(vcube, vcut, scene, "", c.u, c.v, 0.0, 'CYL_PIN', 5, 5, 10, 0.2, 'A', vspec)
        for side in (True, False):
            assert fit.own_margin(cs, vspec.barrier(), side) >= 0.0, (c.u, c.v)
    ctx.metric("v_auto", f"{res.added}/{res.moved}/{res.dropped} {res.describe()}")

    # --- other cut is a stroke: Z plane + vertical S ----------------------------------------
    combo = lib.make_cube(40.0)
    combo.name = "Combo"
    lib.select_only([combo])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z', offset_mm=-4.0)
    add_stroke([(4.0 * math.sin(2 * math.pi * i / 39), 0.0, -26.0 + 52.0 * i / 39) for i in range(40)])
    stack = combo.splitforge_stack
    zcut, scut = stack.cuts[0], stack.cuts[1]
    scut.gap_mm = 0.3
    zcut.connector_count = 2
    scut.connector_count = 2
    for c in (zcut, scut):
        res = auto.add_auto(bpy.context, combo, c, 'CYL_PIN', 5.0, 5.0, 10.0)
        ctx.metric(f"combo_{c.name.replace(' ', '_')}", f"{res.added}/{res.moved}/{res.dropped}")
        assert res.added >= 2, (c.name, res)
    # Two seam regions on each cut (the other cut splits it): connectors on both sides
    zspec, sspec = build.cut_specs(combo, [zcut, scut], scene)
    sides = {sspec.side(build.make_spec(combo, zcut, scene, "", c.u, c.v, 0.0, 'CYL_PIN', 5, 5, 10, 0.2, 'A',
                                        zspec).matrix.translation) for c in zcut.connectors}
    assert sides == {1, -1}, sides
    barriers = build.fit_planes(combo, [zcut, scut], scene)
    assert isinstance(barriers[scut.uid], fit.RibbonBarrier) and isinstance(barriers[zcut.uid], fit.PlaneBarrier)
    for cs in build.connector_specs(combo, [zcut, scut], scene, scene.splitforge):
        others = [b for uid, b in barriers.items() if uid != cs.cut_uid]
        margin = min(fit.plane_margin(cs, others, side) for side in (True, False))
        assert margin >= wall - 1e-6, (cs.label, margin)
    result = build.build(bpy.context, combo)
    assert not result.warnings, result.warnings
    parts = parts_of("Combo")
    assert len(parts) == 4 and all(lib.is_manifold(p) for p in parts)
    no_interpenetration(fit, parts)

    # Slanted ribbon (drawn looking along (0.8, 0, -0.6)): the Z-cut pins run along Z, so a
    # position inset in 2D from where the ribbon meets the seam can still reach across the
    # ribbon higher up; only the 3D barrier check of Distribute catches that
    tilt = lib.make_cube(40.0)
    tilt.name = "Tilt"
    lib.select_only([tilt])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    d = Vector((0.8, 0.0, -0.6))
    lib.run_op(bpy.ops.splitforge.stack_add_stroke, direction=d,
               points=[{"name": "", "co": tuple(Vector((0.0, -26.0 + 52.0 * i / 19, 0.0)) + d * 0.0
                                                + Vector((0.6, 0.0, 0.8)) * (1.5 * math.sin(i / 3.0)))}
                       for i in range(20)])
    tz = tilt.splitforge_stack.cuts[0]
    tz.connector_count, tz.margin_pct = 3, 0.0
    res = auto.add_auto(bpy.context, tilt, tz, 'CYL_PIN', 5.0, 5.0, 10.0)
    ctx.metric("tilt", f"{res.added}/{res.moved}/{res.dropped} {res.describe()}")
    tbar = build.fit_planes(tilt, list(tilt.splitforge_stack.cuts), scene)
    tspec = build.cut_specs(tilt, [tz], scene)[0]
    for c in tz.connectors:
        cs = build.make_spec(tilt, tz, scene, "", c.u, c.v, 0.0, 'CYL_PIN', 5, 5, 10, 0.2, 'A', tspec)
        margin = min(fit.plane_margin(cs, [tbar[tilt.splitforge_stack.cuts[1].uid]], side) for side in (True, False))
        assert margin >= wall - 1e-6, (c.u, c.v, margin)
    assert res.added >= 2 and res.moved + res.dropped > 0, res

    # A manual Z-cut connector straddling the stroke ribbon is skipped by Build
    m = zcut.connectors.add()
    m.u, m.v = 0.0, 0.0
    lib.select_only([combo])
    combo.hide_set(False)
    result = build.build(bpy.context, combo)
    assert any("across another cut" in w for w in result.warnings), result.warnings
    no_interpenetration(fit, parts_of("Combo"))
