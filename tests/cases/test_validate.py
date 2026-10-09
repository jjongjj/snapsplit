# SPDX-License-Identifier: GPL-3.0-or-later
"""P1-2: core/validate.validate() reports manifold, loose geometry, transforms and units."""

import bmesh
import bpy

import lib


def run(ctx):
    validate = ctx.module("core.validate").validate
    lib.set_scene_mm()

    cube = lib.make_cube(40.0)
    rep = validate(cube)
    assert rep.ok and rep.manifold and rep.transform_applied and rep.unit_is_mm, rep
    assert not rep.loose_geom and not rep.messages, rep

    # One face deleted -> not manifold
    holed = lib.make_cube(40.0)
    bm = bmesh.new()
    bm.from_mesh(holed.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[0]], context='FACES_ONLY')
    bm.to_mesh(holed.data)
    bm.free()
    rep = validate(holed)
    assert rep.manifold is False and not rep.ok, rep
    assert any("non-manifold" in m for m in rep.messages), rep.messages

    # Loose vertex
    loose = lib.make_cube(40.0)
    bm = bmesh.new()
    bm.from_mesh(loose.data)
    bm.verts.new((100.0, 0.0, 0.0))
    bm.to_mesh(loose.data)
    bm.free()
    rep = validate(loose)
    assert rep.loose_geom is True and rep.manifold, rep

    # Unapplied scale (location alone is fine)
    scaled = lib.make_cube(40.0)
    scaled.scale = (2.0, 2.0, 2.0)
    scaled.location = (10.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    rep = validate(scaled)
    assert rep.transform_applied is False and rep.manifold, rep
    moved = lib.make_cube(40.0)
    moved.location = (50.0, 0.0, 0.0)
    assert validate(moved).transform_applied is True

    # Meter scene
    bpy.context.scene.unit_settings.length_unit = 'METERS'
    rep = validate(cube)
    assert rep.unit_is_mm is False and rep.manifold, rep
    assert validate(cube, check_mesh=False).unit_is_mm is False

    # Non-mesh object
    bpy.ops.object.empty_add()
    rep = validate(bpy.context.active_object)
    assert not rep.ok and rep.messages, rep
