# SPDX-License-Identifier: GPL-3.0-or-later
"""D17: the socket of a custom connector keeps the clearance everywhere.

The vertex-normal offset folds where a slot is narrower than 2 x clearance and loses clearance at
sharp or concave corners. Now the offset is checked (clean union, >= 0.9 x clearance from every
pin surface sample) and replaced by a Minkowski sum (pin + face prisms + edge cylinders + corner
balls) when it fails.

For a 0.3 mm slot, a 5-pointed star, a cone with a sharp tip, an L and a plain box (offset stays):
Build has no warnings, both parts are manifold, and with the gap closed every point of the pin
that enters the socket part is at least 0.9 x clearance away from its material. For the slot,
star and cone the plain offset alone would not reach 0.9 x clearance (why the fallback exists).
A mesh too detailed for the Minkowski fallback (> MINKOWSKI_MAX_TRIS) with a fine slot builds
with a warning naming the clearance share it keeps (and asking to simplify the mesh).
"""

import importlib
import math

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import lib

C, GAP, W, L = 0.25, 0.4, 6.0, 10.0


def mesh_object(name, bm):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.location = (300.0, 0.0, 0.0)
    return o


def prism(outline, depth=6.0):
    """Outline (x, z), extruded along y."""
    bm = bmesh.new()
    face = bm.faces.new([bm.verts.new((x, -depth / 2, z)) for x, z in outline])
    r = bmesh.ops.extrude_face_region(bm, geom=[face])
    bmesh.ops.translate(bm, verts=[e for e in r["geom"] if isinstance(e, bmesh.types.BMVert)], vec=(0, depth, 0))
    return bm


def shapes():
    out = {}
    # slot open at the tip (top), 0.3 wide, 4 deep
    out["slot"] = prism([(-3, 0), (3, 0), (3, 10), (0.15, 10), (0.15, 6), (-0.15, 6), (-0.15, 10), (-3, 10)])
    star = [((3.0 if i % 2 == 0 else 1.0) * math.cos(math.pi * i / 5), (3.0 if i % 2 == 0 else 1.0) * math.sin(math.pi * i / 5))
            for i in range(10)]
    bm = bmesh.new()
    face = bm.faces.new([bm.verts.new((x, y, 0.0)) for x, y in star])
    r = bmesh.ops.extrude_face_region(bm, geom=[face])
    bmesh.ops.translate(bm, verts=[e for e in r["geom"] if isinstance(e, bmesh.types.BMVert)], vec=(0, 0, 10))
    out["star"] = bm
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=3.0, radius2=0.0, depth=10.0)
    out["cone"] = bm
    out["L"] = prism([(-3, 0), (3, 0), (3, 4), (0, 4), (0, 10), (-3, 10)])
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    out["box"] = bm
    return {k: mesh_object(f"K_{k}", v) for k, v in out.items()}


def build_with(build, name, knob):
    cube = lib.make_cube(40.0)
    cube.name = name
    lib.select_only([cube])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    cube.splitforge_stack.cuts[0].gap_mm = GAP
    t = bpy.context.scene.splitforge.new_connector
    t.kind, t.width_mm, t.height_mm, t.length_mm, t.custom_object, t.clearance_mm = 'CUSTOM', W, W, L, knob, C
    lib.run_op(bpy.ops.splitforge.connector_add, u=0.0, v=0.0)
    return cube, build.build(bpy.context, cube)


def assembled_clearance(ctx, build, cube):
    """Smallest distance from the socket part's material to the pin, gap closed (pin part moved down)."""
    shapes_mod = ctx.module("connectors.shapes")
    fit = ctx.module("connectors.fit")
    cut = cube.splitforge_stack.cuts[0]
    c = cut.connectors[0]
    values = build.connector_values(c)
    spec = build.make_spec(cube, cut, bpy.context.scene, "", c.u, c.v, 0.0, values.pop("kind"), values.pop("width_mm"),
                           values.pop("height_mm"), values.pop("length_mm"), C, c.pin_side,
                           custom=build.custom_shape_of(c.custom_object)[0], **values)
    pin = shapes_mod.connector_solids(spec).pin[0]
    b = bpy.data.objects[f"{cube.name}_B"]
    bm = lib.bm_of(b)
    bvh = BVHTree.FromBMesh(bm)
    bm.free()
    worst = math.inf
    for p in pin.samples(0.1):
        q = p - Vector((0.0, 0.0, GAP))          # assembled: the pin part moved down by the gap
        if q.z < -GAP / 2:
            worst = min(worst, -fit.depth_inside(bvh, q))
    return worst


def run(ctx):
    build = ctx.module("cuts.build")
    custom_socket = importlib.import_module(ctx.addon_module + ".connectors.custom_socket")
    shapes_mod = ctx.module("connectors.shapes")
    lib.set_scene_mm()
    for key, knob in shapes().items():
        cube, res = build_with(build, f"Sk_{key}", knob)
        assert not res.warnings, (key, res.warnings)
        # The pin (a clean user mesh) unites with plain EXACT; the socket boolean may need a fallback
        # solver for the Minkowski socket (star), but never the voxel remesh
        assert all(b[1] == 'EXACT' for b in res.booleans if "union" in b[0]), (key, res.booleans)
        assert all(b[1] and b[1] != 'VOXEL' for b in res.booleans), (key, res.booleans)
        ctx.metric(f"{key}_solvers", ",".join(b[1] for b in res.booleans))
        for part in (f"Sk_{key}_A", f"Sk_{key}_B"):
            assert lib.is_manifold(bpy.data.objects[part]), (key, part)
        got = assembled_clearance(ctx, build, cube)
        assert got >= 0.9 * C, (key, got)
        # What the plain vertex-normal offset alone would keep
        bm = bmesh.new()
        bm.from_mesh(knob.data)
        shape = shapes_mod.custom_shape(bm, knob.name)[0]
        bm.free()
        verts = shapes_mod._custom_local(shape, W, W, L, 5.0, 1.0)
        pin = custom_socket._bm(verts, shape.faces)
        off = custom_socket._bm(custom_socket._offset(pin, C), shape.faces)
        plain = custom_socket.clearance(off, custom_socket.pin_samples(pin, 0.4))
        pin.free()
        off.free()
        if key in ("slot", "star", "cone"):
            assert plain < 0.9 * C, (key, "the plain offset was enough; test not meaningful", plain)
        ctx.metric(key, f"assembled {got:.3f} (plain offset {plain:.3f})")

    # Too detailed for the Minkowski fallback: built, with a warning about the clearance it keeps
    dense = prism([(-3, 0), (3, 0), (3, 10), (0.15, 10), (0.15, 6), (-0.15, 6), (-0.15, 10), (-3, 10)])
    bmesh.ops.subdivide_edges(dense, edges=dense.edges[:], cuts=16, use_grid_fill=True)
    bmesh.ops.triangulate(dense, faces=dense.faces[:])
    assert len(dense.faces) > custom_socket.MINKOWSKI_MAX_TRIS, len(dense.faces)
    knob = mesh_object("K_dense", dense)
    cube, res = build_with(build, "Sk_dense", knob)
    assert any("custom socket" in w and "of the clearance" in w and "simplify" in w for w in res.warnings), res.warnings
    ctx.metric("dense_warning", res.warnings[0])
