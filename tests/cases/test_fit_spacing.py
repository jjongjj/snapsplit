# SPDX-License-Identifier: GPL-3.0-or-later
"""Build checks connector solids with samples at most 1 mm apart (cuts/build.FIT_STEP_MM).

Without the spacing, the pin surface of a 5 x 10 mm CYL_PIN is sampled on 9 rings
(1.25 mm apart: z = 0, 1.25, 2.5, 3.75, 5 above the seam) and 24 points per ring. A
0.3 mm internal cavity centered on the pin surface at z = 4 mm, between two
circumferential samples (7.5 deg), lies between those rings and between the sample
lines, so neither the depth test nor the segment test sees it. With the 1 mm spacing a
ring runs at z = 4 and its chord through the cavity is caught: Build skips the
connector with a warning. (Mutation check: dropping ``max_step`` from Build's
``assign`` call makes this test fail.)
"""

import math

import bmesh
import bpy

import lib


def add_cavity(obj, center, size):
    """Add an inward-facing closed box (an internal void) to the object's mesh."""
    bm = lib.bm_of(obj, world=False)
    cav = bmesh.new()
    bmesh.ops.create_cube(cav, size=size)
    bmesh.ops.translate(cav, verts=cav.verts, vec=center)
    bmesh.ops.reverse_faces(cav, faces=cav.faces)
    tmp = bpy.data.meshes.new("cavity_tmp")
    cav.to_mesh(tmp)
    bm.from_mesh(tmp)
    bm.to_mesh(obj.data)
    bm.free()
    cav.free()
    bpy.data.meshes.remove(tmp)


def run(ctx):
    build = ctx.module("cuts.build")
    fit = ctx.module("connectors.fit")
    lib.set_scene_mm()
    assert build.FIT_STEP_MM == 1.0
    a = math.radians(7.5)
    cube = lib.make_cube(40.0)
    cube.name = "Spacing"
    add_cavity(cube, (2.5 * math.cos(a), 2.5 * math.sin(a), 4.0), 0.3)
    lib.select_only([cube])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    cut = cube.splitforge_stack.cuts[0]
    c = cut.connectors.add()
    c.u, c.v = 0.0, 0.0
    c.pin_side = 'A'

    # The premise: default sampling misses the cavity, 1 mm sampling finds it
    bm = lib.bm_of(cube)
    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromBMesh(bm)
    bm.free()
    spec = build.connector_specs(cube, [cut], bpy.context.scene, bpy.context.scene.splitforge)[0]
    tol = -1e-4 * spec.length
    assert fit.check(spec, bvh, (), tol).ok(tol), "test premise: default sampling should miss the cavity"
    assert not fit.check(spec, bvh, (), tol, max_step=1.0).ok(tol), "1 mm sampling should find the cavity"

    result = build.build(bpy.context, cube)
    assert any("connector 1" in w and "break through" in w for w in result.warnings), result.warnings
    # Moved away from the cavity it builds without warning
    c.u = -8.0
    lib.select_only([cube])
    cube.hide_set(False)
    result = build.build(bpy.context, cube)
    assert not result.warnings, result.warnings
