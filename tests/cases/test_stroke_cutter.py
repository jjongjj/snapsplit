# SPDX-License-Identifier: GPL-3.0-or-later
"""P2-2: stroke cutter construction (cuts/stroke.py), pure functions, synthetic view.

A front orthographic view (looking along +Y) is built without a window
(tests/lib FakeView); an S-shaped stroke of 30 screen points is projected onto the
plane through the cube center, prepared (resampled + smoothed) and turned into the
ribbon cutters. Checks: manifold closed cutters with volume, the two remover solids
partition the cutter box (overlapping exactly in the gap slab), the depth range
covers the object, a two-point stroke gives a planar ribbon, the seam frame, axis
snapping, and the user-facing rejections (too short, self-crossing, extension
crossing the stroke, too tight for the gap).
"""

import math

import bmesh
from mathutils import Vector

import lib

HALF = 20.0
CORNERS = [Vector((x, y, z)) for x in (-HALF, HALF) for y in (-HALF, HALF) for z in (-HALF, HALF)]


def _is_manifold(bm):
    return (len(bm.faces) > 0 and all(e.is_manifold for e in bm.edges)
            and all(v.link_faces for v in bm.verts))


def _bbox(bm):
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    zs = [v.co.z for v in bm.verts]
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


def s_curve_screen(view, n=30):
    """S curve across the cube (world x -26..26, z = 8 sin) as region coordinates."""
    pts = []
    for i in range(n):
        f = i / (n - 1)
        x = -26.0 + 52.0 * f
        z = 8.0 * math.sin(2.0 * math.pi * f)
        pts.append(tuple(view.to_region((x, 0.0, z))))
    return pts


def run(ctx):
    stroke = ctx.module("cuts.stroke")
    view = lib.front_view()

    # --- projection from a synthetic view --------------------------------------------
    screen = s_curve_screen(view)
    pts, d = stroke.points_from_view(view.region, view, screen, (0.0, 0.0, 0.0))
    assert len(pts) == 30
    assert (d - Vector((0.0, 1.0, 0.0))).length < 1e-6, d
    for p in pts:
        assert abs(p.y) < 1e-6, p           # on the plane through the center facing the view
    lib.assert_close(pts[0].x, -26.0, abs_=1e-3)
    lib.assert_close(pts[7].z, 8.0 * math.sin(2 * math.pi * 7 / 29), abs_=1e-3)

    # --- preparation: resample + smooth ------------------------------------------------
    prepared = stroke.prepare_points(pts, d, 0.5)
    ctx.metric("prepared_points", len(prepared))
    assert 100 <= len(prepared) <= stroke.MAX_POINTS
    assert (prepared[0] - pts[0]).length < 1e-6 and (prepared[-1] - pts[-1]).length < 1e-6, "ends kept"
    gaps = [(a - b).length for a, b in zip(prepared, prepared[1:])]
    assert max(gaps) / min(gaps) < 1.05, (min(gaps), max(gaps))
    noisy = [Vector((x * 0.5, 0.0, 0.3 * (-1) ** x)) for x in range(-40, 41)]
    smooth = stroke.prepare_points(noisy, d, 0.5)
    assert max(abs(p.z) for p in smooth[3:-3]) < 0.15, "jitter not smoothed"

    # --- S curve cutters with a 0.5 gap --------------------------------------------------
    cutter = stroke.build_cutter(prepared, d, CORNERS, 0.5)
    solids = {"remove_a": cutter.remove_for_a(), "remove_b": cutter.remove_for_b(),
              "positive": cutter.positive_solid(), "slab": cutter.slab()}
    try:
        for name, bm in solids.items():
            assert _is_manifold(bm), f"{name} not manifold"
            assert bm.calc_volume(signed=True) > 0.0, f"{name}: no volume or inward normals"
            (_x0, _x1), (y0, y1), (_z0, _z1) = _bbox(bm)
            assert y0 < -HALF and y1 > HALF, f"{name} does not cover the object's depth"
        # Together the removers cover the whole object bbox
        boxes = [_bbox(solids[k]) for k in ("remove_a", "remove_b")]
        for axis in range(3):
            assert min(b[axis][0] for b in boxes) < -HALF and max(b[axis][1] for b in boxes) > HALF, axis
        # They partition the cutter box and overlap exactly in the gap slab
        x0, y0, x1, y1 = cutter.box
        box_volume = (x1 - x0) * (y1 - y0) * (cutter.z1 - cutter.z0)
        va, vb = (solids[k].calc_volume() for k in ("remove_a", "remove_b"))
        vslab = solids["slab"].calc_volume()
        lib.assert_close(va + vb, box_volume + vslab, rel=1e-6, msg="removers = box + slab")
        # The slab is gap x ribbon length (inside the box) x depth
        length = stroke.polyline_length(cutter.extended)
        lib.assert_close(vslab, 0.5 * length * (cutter.z1 - cutter.z0), rel=0.01, msg="slab volume")
        ctx.metric("slab_volume", round(vslab, 1))
    finally:
        for bm in solids.values():
            bm.free()

    # Sides: points above / below the S
    assert cutter.side(Vector((0.0, 5.0, 15.0))) == 1 and cutter.side(Vector((0.0, -5.0, -15.0))) == -1
    lib.assert_close(cutter.distance(Vector((-26.0 + 13.0, 3.0, 8.0))), 0.0, abs_=0.15)

    # --- seam frame along the curve ------------------------------------------------------
    cl = stroke.centerline(cutter)
    lib.assert_close(cl.total, stroke.polyline_length(cutter.curve), rel=1e-9)
    co, n, t = cl.frame_at(0.0, 3.0)
    assert abs(n.dot(d)) < 1e-9 and abs(t.dot(d)) < 1e-9 and abs(n.dot(t)) < 1e-9
    lib.assert_close(co.y - prepared[0].y, 3.0, abs_=1e-6, msg="v is the depth along d")
    m = cl.matrix(5.0, -2.0, 30.0)
    z_axis = Vector(m.col[2][:3])
    _co, n5, _t5 = cl.frame_at(5.0)
    assert z_axis.angle(n5) < 1e-6
    a = cl.frame_at(-cl.total / 2)[0]
    assert (a - prepared[0]).length < 1e-6, "u = -total/2 is the stroke start"
    # Drawn left to right: the positive side (normal) points up at the start of the S
    assert cl.frame_at(-cl.total / 2 + 0.1)[1].z > 0.5

    # --- a two-point stroke is a plane ---------------------------------------------------
    line = [Vector((-30.0, 0.0, 2.0)), Vector((30.0, 0.0, 6.0))]
    flat = stroke.build_cutter(line, d, CORNERS, 0.0)
    n_line = (line[1] - line[0]).normalized().cross(d)
    rib = flat.ribbon()
    try:
        worst = max(abs((v.co - line[0]).dot(n_line)) for v in rib.verts)
        assert worst < 1e-5, worst  # bmesh coordinates are float32
    finally:
        rib.free()
    pos = flat.positive_solid()
    try:
        assert all((v.co - line[0]).dot(n_line) >= -1e-6 for v in pos.verts), "positive side is +normal"
    finally:
        pos.free()

    # --- axis snap ------------------------------------------------------------------------
    snapped = stroke.snap_to_axis([Vector((-20, 0, -3)), Vector((0, 0, 1)), Vector((20, 0, 4))], d)
    direction = (snapped[1] - snapped[0]).normalized()
    assert abs(abs(direction.x) - 1.0) < 1e-9, direction
    steep = stroke.snap_to_axis([Vector((1, 0, -20)), Vector((-2, 0, 20))], d)
    assert abs(abs((steep[1] - steep[0]).normalized().z) - 1.0) < 1e-9

    # --- rejections with a message for the user -----------------------------------------
    def rejected(points, gap=0.0, text=""):
        try:
            stroke.build_cutter(points, d, CORNERS, gap)
        except stroke.StrokeError as ex:
            assert text in str(ex), (text, str(ex))
            return str(ex)
        raise AssertionError(f"accepted: {text}")

    ctx.metric("msg_short", rejected([Vector((0, 0, 0)), Vector((1e-9, 0, 0))], text="too short"))
    loop = [Vector((10 * math.cos(a), 0, 10 * math.sin(a))) for a in [i * 0.3 for i in range(25)]]
    ctx.metric("msg_loop", rejected(loop, text="crosses itself"))
    hook = [Vector((-25, 0, 0)), Vector((5, 0, 0)), Vector((5, 0, 8)), Vector((-2, 0, 8)), Vector((-2, 0, 4))]
    ctx.metric("msg_hook", rejected(hook, text="extension"))
    # U-turn of radius 0.8: a gap of 2 (offset 1 > radius) folds the inner offset curve
    u_turn = ([Vector((-25 + i, 0, 3.0)) for i in range(31)]
              + [Vector((5 + 0.8 * math.sin(a), 0, 2.2 + 0.8 * math.cos(a)))
                 for a in [math.pi * k / 12 for k in range(1, 12)]]
              + [Vector((5 - i, 0, 1.4)) for i in range(31)])
    ctx.metric("msg_tight", rejected(u_turn, gap=2.0, text="gap"))
    stroke.build_cutter(u_turn, d, CORNERS, 0.2)  # fine with a small gap
    # Wide bend (radius 3 > offset 1) but the legs come back 1.5 apart: the offset curves do
    # not fold or cross, yet part A would overlap part B (plus not left of minus)
    bulb = ([Vector((-25 + i, 0, 3.0)) for i in range(26)]
            + [Vector((3 * math.sin(a), 0, 3 * math.cos(a))) for a in [math.pi * k / 16 for k in range(1, 16)]]
            + [Vector((0, 0, -3.0)), Vector((-20, 0, 1.5)), Vector((-25, 0, 1.5))])
    ctx.metric("msg_close", rejected(bulb, gap=2.0, text="too close"))
    stroke.build_cutter(bulb, d, CORNERS, 1.0)
    zigzag = [Vector((-25 + 1.0 * i, 0, 1.0 * (i % 2))) for i in range(51)]
    stroke.build_cutter(zigzag, d, CORNERS, 0.0)  # sharp but simple
    try:
        stroke.prepare_points([Vector((0, 0, 0))], d, 0.5)
        raise AssertionError("one point accepted")
    except stroke.StrokeError:
        pass

    # --- rectangle walk helpers ----------------------------------------------------------
    box = (0.0, 0.0, 10.0, 10.0)
    assert stroke.walk_ccw((10.0, 5.0), (0.0, 5.0), box) == [(10.0, 10.0), (0.0, 10.0)]
    assert stroke.walk_ccw((0.0, 5.0), (10.0, 5.0), box) == [(0.0, 0.0), (10.0, 0.0)]
    left = stroke.left_polygon([(0.0, 5.0), (10.0, 5.0)], box)
    assert stroke.point_in_polygon((5.0, 8.0), left) and not stroke.point_in_polygon((5.0, 2.0), left)
