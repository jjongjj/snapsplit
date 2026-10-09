# SPDX-License-Identifier: GPL-3.0-or-later
"""P3-1 (+P3-2, P3-3 basics): every connector type in the new pipeline, planar and curved seams.

For each type (CYL_PIN, RECT_TENON, DOVETAIL, SNAP_PIN, SNAP_TENON, SNAP_DOVETAIL, CUSTOM, DOWEL):

- planar Z cut (gap 0.4) on a 40 mm cube, Distribute: Build gives manifold parts, the pin
  part is larger than the socket part (dowel: both lose volume, plus a dowel part), no part
  reaches outside the cube; the cross-sections show the per-type clearance:
  prisms + 2c, tapered faces c measured normal to the face against the assembled pin
  (shifted by the gap), snap bumps stand out by their height and their dimples by height + c,
  the custom box gets +c on every face (normal offset, not a scale);
- curved S stroke (gap 0.4), Distribute: manifold, pin part gains / socket part loses volume
  against the same Build without connectors, inside the cube;
- fit barriers: a Z cut crossed by a vertical S stroke: Distribute on the Z cut never reaches
  across the ribbon (fit margin >= wall for both pin sides), Build gives 4 parts without
  warnings; a manual connector at the cube edge is skipped by Build with a warning.
"""

import math

import bmesh
import bpy
from mathutils import Vector

import lib

KINDS = ('CYL_PIN', 'RECT_TENON', 'DOVETAIL', 'SNAP_PIN', 'SNAP_TENON', 'SNAP_DOVETAIL', 'CUSTOM', 'DOWEL')
W, H, L, C, GAP = 6.0, 4.0, 10.0, 0.25, 0.4
TAPER, BUMP_D, BUMP_P = 0.5, 2.0, 0.6


def custom_box():
    """A user mesh (2 x 3 x 5 box, rotated data, flipped normals) used as the custom pin shape."""
    obj = bpy.data.objects.get("KnobBox")
    if obj is None:
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=(2.0, 3.0, 5.0), verts=bm.verts)
        bmesh.ops.reverse_faces(bm, faces=bm.faces)   # flipped normals must not invert the socket
        mesh = bpy.data.meshes.new("KnobBox")
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new("KnobBox", mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj.location = (80.0, 0.0, 0.0)
    return obj


def set_template(kind):
    t = bpy.context.scene.splitforge.new_connector
    t.kind = kind
    t.width_mm, t.height_mm, t.length_mm = W, H, L
    t.taper_pct = TAPER * 100.0
    t.snap_count, t.snap_diameter_mm, t.snap_protrusion_mm = 2, BUMP_D, BUMP_P
    t.embed_pct, t.chamfer_mm, t.clearance_mm, t.pin_side = 50.0, 0.0, -1.0, 'A'
    t.custom_object = custom_box() if kind == 'CUSTOM' else None
    return t


def parts_of(name):
    return {o.name[len(name) + 1:]: o for o in bpy.data.objects if o.get("splitforge_source") == name}


def section_boxes(meshlib, obj, z, limit=20.0):
    """(width x, width y, center x, center y) of the small section loops of ``obj`` at height z."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    try:
        loops = meshlib.section_loops_2d(bm, Vector((0, 0, z)), Vector((0, 0, 1)), Vector((1, 0, 0)),
                                         Vector((0, 1, 0)))
    finally:
        bm.free()
    out = []
    for loop in loops:
        xs, ys = [p[0] for p in loop], [p[1] for p in loop]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if w < limit and h < limit:
            out.append((w, h, (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2))
    return sorted(out, key=lambda b: b[2])


def inside_cube(obj, half=20.0, tol=1e-3):
    return all(abs(c) <= half + tol for v in obj.data.vertices for c in (obj.matrix_world @ v.co))


def new_cube(name):
    cube = lib.make_cube(40.0)
    cube.name = name
    lib.select_only([cube])
    return cube


def add_stroke(points, direction=(0.0, 1.0, 0.0)):
    lib.run_op(bpy.ops.splitforge.stack_add_stroke, points=[{"name": "", "co": p} for p in points],
               direction=direction)


def s_points(amp=5.0, n=40, vertical=False, offset=0.0):
    pts = []
    for i in range(n):
        a = -26.0 + 52.0 * i / (n - 1)
        b = offset + amp * math.sin(2 * math.pi * i / (n - 1))
        pts.append((b, 0.0, a) if vertical else (a, 0.0, b))
    return pts


def check_planar_sections(ctx, kind, parts):
    """Cross-sections of the planar Z cut (pin side A above, pins point down into B)."""
    meshlib = ctx.module("core.meshlib")
    a, b = parts["A"], parts["B"]
    hg = GAP / 2.0
    if kind == 'DOWEL':
        for part, z in ((a, 2.0), (b, -2.0)):
            holes = section_boxes(meshlib, part, z)
            assert len(holes) == 2, (kind, part.name, holes)
            for w, h, _x, _y in holes:
                lib.assert_close(w, W + 2 * C, abs_=0.02, msg=f"{part.name} dowel socket")
                lib.assert_close(h, W + 2 * C, abs_=0.02, msg=f"{part.name} dowel socket")
        # socket depth L/2 + c beyond each face, closed behind it
        assert len(section_boxes(meshlib, a, hg + L / 2 + C - 0.05)) == 2
        assert not section_boxes(meshlib, a, hg + L / 2 + C + 0.05)
        assert len(section_boxes(meshlib, b, -(hg + L / 2 + C - 0.05))) == 2
        assert not section_boxes(meshlib, b, -(hg + L / 2 + C + 0.05))
        return
    z = -2.0
    pins, holes = section_boxes(meshlib, a, z), section_boxes(meshlib, b, z)
    assert len(pins) == len(holes) == 2, (kind, pins, holes)
    if kind in ('CYL_PIN', 'SNAP_PIN'):
        expect_pin, expect_hole = (W, W), (W + 2 * C, W + 2 * C)
    elif kind in ('RECT_TENON', 'SNAP_TENON', 'CUSTOM'):
        expect_pin, expect_hole = (W, H), (W + 2 * C, H + 2 * C)
    else:
        # Dovetail: half widths linear from the base (z = hg + L/2) to the tip (z = hg - L/2, x (1 - taper))
        def half(z_, full):
            f = (z_ - (hg + L / 2)) / -L
            return full / 2 * (1.0 - TAPER * f)
        sec_u = math.sqrt(1 + (W / 2 * TAPER / L) ** 2)
        sec_v = math.sqrt(1 + (H / 2 * TAPER / L) ** 2)
        expect_pin = (2 * half(z, W), 2 * half(z, H))
        # Socket at z holds the assembled pin (moved down by the gap): its section at z + gap, + c normal
        expect_hole = (2 * (half(z + GAP, W) + C * sec_u), 2 * (half(z + GAP, H) + C * sec_v))
        # The clearance normal to the slanted face is c
        lib.assert_close((expect_hole[0] / 2 - half(z + GAP, W)) / sec_u, C, abs_=1e-9)
    if kind in ('SNAP_PIN', 'SNAP_TENON', 'SNAP_DOVETAIL'):
        pass  # bump sections are checked below; at z = -2 the bumps (centre -2.3) widen the outline
    else:
        for w, h, _x, _y in pins:
            lib.assert_close(w, expect_pin[0], abs_=0.02, msg=f"{kind} pin width")
            lib.assert_close(h, expect_pin[1], abs_=0.02, msg=f"{kind} pin height")
        # Sections of exact planar geometry: tight enough to see the 1/cos of a tapered face
        tol = 0.002 if kind == 'DOVETAIL' else 0.02
        for w, h, _x, _y in holes:
            lib.assert_close(w, expect_hole[0], abs_=tol, msg=f"{kind} socket width")
            lib.assert_close(h, expect_hole[1], abs_=tol, msg=f"{kind} socket height")
    if kind in ('SNAP_PIN', 'SNAP_TENON', 'SNAP_DOVETAIL'):
        z_bump = hg - L / 4                    # middle of the protruding half
        base_half = W / 2
        if kind == 'SNAP_DOVETAIL':
            base_half = W / 2 * (1.0 - TAPER * ((z_bump - (hg + L / 2)) / -L))
        bumps = section_boxes(meshlib, a, z_bump)
        for w, _h, _x, _y in bumps:            # bumps at 0 and 180 degrees: along x
            lib.assert_close(w, 2 * (base_half + BUMP_P), abs_=0.03, msg=f"{kind} bump height")
        dimples = section_boxes(meshlib, b, z_bump - GAP)
        for w, _h, _x, _y in dimples:
            lib.assert_close(w, 2 * (base_half + BUMP_P + C), abs_=0.03, msg=f"{kind} dimple = bump + c")
        ctx.metric(f"{kind}_bump", f"{bumps[0][0]:.3f}/{dimples[0][0]:.3f}")


def run(ctx):
    build = ctx.module("cuts.build")
    fit = ctx.module("connectors.fit")
    auto = ctx.module("connectors.auto")
    lib.set_scene_mm()
    scene = bpy.context.scene
    scene.splitforge.clearance_mm = C
    half = 40.0 ** 3 / 2.0
    for kind in KINDS:
        set_template(kind)

        # --- planar seam --------------------------------------------------------
        name = f"P_{kind}"
        cube = new_cube(name)
        lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
        cut = cube.splitforge_stack.cuts[0]
        cut.gap_mm = GAP
        lib.run_op(bpy.ops.splitforge.connector_add_auto)
        assert len(cut.connectors) == 2 and all(c.kind == kind for c in cut.connectors), [
            (c.kind, c.u) for c in cut.connectors]
        result = build.build(bpy.context, cube)
        assert not result.warnings, (kind, result.warnings)
        # A connector's own overlapping solids (snap bumps, custom offset) are united first, so the
        # part booleans need no self-intersection handling
        assert all(b[1] == 'EXACT' for b in result.booleans), (kind, result.booleans)
        parts = parts_of(name)
        expect = {"A", "B"} | ({"Dowel_1", "Dowel_2"} if kind == 'DOWEL' else set())
        assert set(parts) == expect, (kind, sorted(parts))
        for p in parts.values():
            assert lib.is_manifold(p), f"{kind}: {p.name} not manifold"
        va, vb = lib.volume(parts["A"]), lib.volume(parts["B"])
        if kind == 'DOWEL':
            assert va < half - 0.2 * 40 * 40 and vb < half - 0.2 * 40 * 40, (va, vb)
        else:
            assert va > vb, (kind, va, vb)
            assert va > half - 0.2 * 1600 and vb < half - 0.2 * 1600 - 1.0, (kind, va, vb)
        for key in ("A", "B"):
            assert inside_cube(parts[key]), f"{kind}: {key} leaves the cube"
        check_planar_sections(ctx, kind, parts)
        ctx.metric(f"{kind}_planar", f"{va:.0f}/{vb:.0f} {result.infos[-1] if result.infos else ''}")

        # Edge connector: skipped by Build with a reason
        lib.run_op(bpy.ops.splitforge.connector_add, u=18.5, v=0.0)
        result = build.build(bpy.context, cube)
        assert any("connector 3" in w and "break through" in w for w in result.warnings), (kind, result.warnings)
        if kind in ('CYL_PIN', 'SNAP_PIN'):
            # Socket wall 0.2 mm from the surface: a plain pin fits, a snap pin's dimples break through
            cut.connectors[2].u = 20.0 - (W / 2 + C) - 0.2
            cut.connectors[2].v = 0.0
            result = build.build(bpy.context, cube)
            skipped = any("connector 3" in w for w in result.warnings)
            assert skipped == (kind == 'SNAP_PIN'), (kind, result.warnings)

        # --- curved seam --------------------------------------------------------
        name = f"S_{kind}"
        cube = new_cube(name)
        add_stroke(s_points())
        cut = cube.splitforge_stack.cuts[0]
        cut.gap_mm = GAP
        result = build.build(bpy.context, cube)
        base = {k: lib.volume(p) for k, p in parts_of(name).items()}
        lib.run_op(bpy.ops.splitforge.connector_add_auto)
        assert cut.connectors, kind
        result = build.build(bpy.context, cube)
        assert not result.warnings, (kind, result.warnings)
        parts = parts_of(name)
        for p in parts.values():
            assert lib.is_manifold(p), f"{kind} curved: {p.name} not manifold"
        for key in ("A", "B"):
            assert inside_cube(parts[key]), f"{kind} curved: {key} leaves the cube"
        va, vb = lib.volume(parts["A"]), lib.volume(parts["B"])
        if kind == 'DOWEL':
            assert va < base["A"] - 1.0 and vb < base["B"] - 1.0 and "Dowel_1" in parts, (kind, va, vb, base)
        else:
            assert va > base["A"] + 1.0 and vb < base["B"] - 1.0, (kind, va, vb, base)
        ctx.metric(f"{kind}_curved", f"{len(cut.connectors)} conn {va - base['A']:+.0f}/{vb - base['B']:+.0f}")

        # --- fit barriers: the Z cut's connectors stay off the vertical stroke ribbon ----
        name = f"X_{kind}"
        cube = new_cube(name)
        lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
        add_stroke(s_points(amp=4.0, vertical=True, offset=6.0))
        stack = cube.splitforge_stack
        stack.cuts[1].gap_mm = GAP
        stack.active_index = 0
        stack.cuts[0].connector_count = 3
        lib.run_op(bpy.ops.splitforge.connector_add_auto)
        zcut = stack.cuts[0]
        assert zcut.connectors, kind
        ribbon = build.cut_spec(cube, stack.cuts[1], scene).barrier()
        spec_z = build.cut_spec(cube, zcut, scene)
        wall = auto.MIN_WALL_MM
        for c in zcut.connectors:
            values = build.connector_values(c)
            custom = build.custom_shape_of(c.custom_object)[0] if kind == 'CUSTOM' else None
            cs = build.make_spec(cube, zcut, scene, "", c.u, c.v, c.rotation_deg, values.pop("kind"),
                                 values.pop("width_mm"), values.pop("height_mm"), values.pop("length_mm"), C,
                                 c.pin_side, spec_z, custom=custom, **values)
            for side in (True, False):
                margin = fit.plane_margin(cs, [ribbon], side, 1.0)
                assert margin >= wall - 1e-6, (kind, c.u, c.v, side, margin)
        result = build.build(bpy.context, cube)
        assert not result.warnings, (kind, result.warnings)
        parts = parts_of(name)
        assert len([k for k in parts if "Dowel" not in k]) == 4, (kind, sorted(parts))
        for p in parts.values():
            assert lib.is_manifold(p), f"{kind} barrier: {p.name} not manifold"
        ctx.metric(f"{kind}_barrier", len(zcut.connectors))
