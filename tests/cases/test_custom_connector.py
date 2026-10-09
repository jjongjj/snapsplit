# SPDX-License-Identifier: GPL-3.0-or-later
"""P3-2: custom mesh connectors.

- A user cylinder mesh (any size, location, rotation; its local mesh is used) scaled to
  6 x 6 x 10 builds manifold parts and matches a CYL_PIN of the same size (volume, 1 %).
- Validation: an open mesh, a flat mesh, a mesh with too many faces, an object without
  faces are rejected with a reason: Build warns and skips the connector (the parts are
  still built), Distribute and click placement refuse with the message (operator reports),
  the panel shows it. The stack owner cannot be its own custom mesh (poll).
- The socket is the pin offset along the normals (not a scale): on a tapered custom
  frustum the clearance measured normal to the slanted faces is c at two heights, and the
  box faces of a W != H box both get +c (a uniform scale could not do both).
- "Use Object Size" copies the object's dimensions (mm) into W/H/L.
"""

import math

import bmesh
import bpy
from mathutils import Euler, Vector

import lib

C, GAP = 0.25, 0.4


def mesh_object(name, build):
    bm = bmesh.new()
    build(bm)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def frustum(bm):
    """Square frustum: base 2 x 2 at z = 0, top 1 x 1 at z = 2 (tip narrower)."""
    base = [bm.verts.new((x, y, 0.0)) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    top = [bm.verts.new((x * 0.5, y * 0.5, 2.0)) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    bm.faces.new(list(reversed(base)))
    bm.faces.new(top)
    for k in range(4):
        bm.faces.new((base[k], base[(k + 1) % 4], top[(k + 1) % 4], top[k]))


def parts_of(name):
    return {o.name[len(name) + 1:]: o for o in bpy.data.objects if o.get("splitforge_source") == name}


def section_half_x(meshlib, obj, z):
    """Half width along x of the small section loops of ``obj`` at height z."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    try:
        loops = meshlib.section_loops_2d(bm, Vector((0, 0, z)), Vector((0, 0, 1)), Vector((1, 0, 0)),
                                         Vector((0, 1, 0)))
    finally:
        bm.free()
    small = [lp for lp in loops if max(p[0] for p in lp) - min(p[0] for p in lp) < 20.0]
    assert len(small) == 1, (obj.name, z, len(small))
    xs = [p[0] for p in small[0]]
    ys = [p[1] for p in small[0]]
    return (max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2


def cube_with_connector(name, kind, obj=None, w=6.0, h=6.0, length=10.0, u=0.0):
    cube = lib.make_cube(40.0)
    cube.name = name
    lib.select_only([cube])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    cut = cube.splitforge_stack.cuts[0]
    cut.gap_mm = GAP
    t = bpy.context.scene.splitforge.new_connector
    t.kind, t.width_mm, t.height_mm, t.length_mm, t.custom_object, t.clearance_mm = kind, w, h, length, obj, C
    lib.run_op(bpy.ops.splitforge.connector_add, u=u, v=0.0)
    return cube


def run(ctx):
    build = ctx.module("cuts.build")
    meshlib = ctx.module("core.meshlib")
    panel = ctx.module("ui.panel")
    ops = ctx.module("ops.ops_connector")
    lib.set_scene_mm()

    # --- a user cylinder == the built-in pin --------------------------------------------
    cyl = mesh_object("UserCyl", lambda bm: bmesh.ops.create_cone(
        bm, cap_ends=True, segments=32, radius1=7.0, radius2=7.0, depth=3.0))
    cyl.location, cyl.rotation_euler, cyl.scale = (60, 5, 3), Euler((0.4, 0.2, 1.0)), (2.0, 2.0, 2.0)
    cube = cube_with_connector("Cu", 'CUSTOM', cyl)
    res = build.build(bpy.context, cube)
    assert not res.warnings, res.warnings
    cu = parts_of("Cu")
    ref = cube_with_connector("Ref", 'CYL_PIN')
    build.build(bpy.context, ref)
    rp = parts_of("Ref")
    for k in ("A", "B"):
        assert lib.is_manifold(cu[k]), k
        lib.assert_close(lib.volume(cu[k]), lib.volume(rp[k]), rel=0.002, msg=f"custom cylinder {k}")
    lib.assert_close(section_half_x(meshlib, cu["B"], -2.0)[0], 3.0 + C, abs_=0.02, msg="custom socket radius")
    ctx.metric("cylinder", f"{lib.volume(cu['A']):.1f}/{lib.volume(rp['A']):.1f}")

    # --- validation ------------------------------------------------------------------------
    def open_box(bm):
        bmesh.ops.create_cube(bm, size=2.0)
        bmesh.ops.delete(bm, geom=list(bm.faces)[:1], context='FACES_ONLY')

    def flat(bm):
        bmesh.ops.create_cube(bm, size=2.0)
        bmesh.ops.scale(bm, vec=(1.0, 1.0, 0.001), verts=bm.verts)

    def dense(bm):
        bmesh.ops.create_uvsphere(bm, u_segments=200, v_segments=120, radius=1.0)

    bad = {
        "Open": (mesh_object("OpenBox", open_box), "not a closed manifold"),
        "Flat": (mesh_object("FlatBox", flat), "is flat"),
        "Dense": (mesh_object("DenseBall", dense), "faces (at most"),
        "Empty": (mesh_object("NoFaces", lambda bm: None), "has no faces"),
    }
    for key, (obj, why) in bad.items():
        cube = cube_with_connector(f"Bad{key}", 'CUSTOM', obj)
        lib.run_op(bpy.ops.splitforge.connector_add, u=-8.0, v=0.0)
        cube.splitforge_stack.cuts[0].connectors[1].kind = 'CYL_PIN'
        res = build.build(bpy.context, cube)
        assert any("connector 1" in w and why in w and "skipped" in w for w in res.warnings), (key, res.warnings)
        parts = parts_of(f"Bad{key}")
        assert sorted(parts) == ["A", "B"] and all(lib.is_manifold(p) for p in parts.values())
        assert lib.volume(parts["A"]) > 40 * 40 * 19.8 + 50.0, "the other (pin) connector was built"
        assert why in panel.custom_problem(obj), (key, panel.custom_problem(obj))
        # Distribute refuses with the reason (operator report)
        lib.select_only([cube])
        op, reports = lib.stand_in(ops.SPLITFORGE_OT_connector_add_auto)
        op.cut_index, op.replace = -1, True
        result = ops.SPLITFORGE_OT_connector_add_auto.execute(op, bpy.context)
        assert result == {'CANCELLED'} and any(why in msg for _lvl, msg in reports), (key, result, reports)
        ctx.metric(key, reports[-1][1])
    assert panel.custom_problem(None) == "no custom mesh object chosen"

    # The stack owner is not offered as its own custom mesh
    c0 = bpy.data.objects["Cu"].splitforge_stack.cuts[0].connectors[0]
    assert not ctx.module("model.props")._custom_poll(c0, bpy.data.objects["Cu"])
    assert ctx.module("model.props")._custom_poll(c0, cyl)

    # --- normal offset, not a scale ----------------------------------------------------
    knob = mesh_object("Frustum", frustum)
    cube = cube_with_connector("Fr", 'CUSTOM', knob, w=8.0, h=8.0, length=10.0)
    res = build.build(bpy.context, cube)
    assert not res.warnings, res.warnings
    fr = parts_of("Fr")
    assert all(lib.is_manifold(p) for p in fr.values())
    # Pin (part A, side A): base 8 wide at z = hg + 5, tip 4 wide at z = hg - 5; slope 2 mm per 10 mm
    hg = GAP / 2
    cos_t = 1.0 / math.sqrt(1.0 + (2.0 / 10.0) ** 2)
    for z in (-1.0, -4.0):
        pin_assembled = 4.0 - 2.0 * ((hg + 5.0) - (z + GAP)) / 10.0   # pin half width where it sits after assembly
        sock = section_half_x(meshlib, fr["B"], z)
        for half in sock:
            normal_gap = (half - pin_assembled) * cos_t
            lib.assert_close(normal_gap, C, abs_=0.01, msg=f"clearance normal to the slanted face at z={z}")
        ctx.metric(f"frustum_z{z}", f"{(sock[0] - pin_assembled) * cos_t:.4f}")
    # A W != H box: +c on both sides (a uniform scale gives different gaps)
    box = mesh_object("Slab", lambda bm: bmesh.ops.create_cube(bm, size=1.0))
    cube = cube_with_connector("Bx", 'CUSTOM', box, w=8.0, h=3.0)
    build.build(bpy.context, cube)
    hx, hy = section_half_x(meshlib, parts_of("Bx")["B"], -2.0)
    lib.assert_close(hx, 4.0 + C, abs_=0.02)
    lib.assert_close(hy, 1.5 + C, abs_=0.02)

    # --- Use Object Size -----------------------------------------------------------------------
    cyl.scale = (1.0, 1.0, 1.0)
    bpy.context.view_layer.update()
    lib.select_only([bpy.data.objects["Cu"]])
    lib.run_op(bpy.ops.splitforge.connector_custom_size, target='ACTIVE')
    c0 = bpy.data.objects["Cu"].splitforge_stack.cuts[0].connectors[0]
    dims = tuple(round(d, 4) for d in cyl.dimensions)
    assert (round(c0.width_mm, 4), round(c0.height_mm, 4), round(c0.length_mm, 4)) == dims, (dims, c0.width_mm)
