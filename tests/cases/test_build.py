# SPDX-License-Identifier: GPL-3.0-or-later
"""P1-6: splitforge.build copies the source, applies enabled cuts, replaces its result collection."""

import hashlib
import struct

import bpy

import lib


def _mesh_hash(obj):
    h = hashlib.sha256()
    for v in obj.data.vertices:
        h.update(struct.pack("<3d", *v.co))
    for p in obj.data.polygons:
        h.update(struct.pack(f"<{len(p.vertices)}i", *p.vertices))
    return h.hexdigest()


def _parts(source_name):
    return sorted(o.name for o in bpy.data.objects if o.get("splitforge_source") == source_name)


def run(ctx):
    naming = ctx.module("core.naming")
    lib.set_scene_mm()
    cube = lib.make_cube(40.0)
    cube.name = "BuildCube"
    lib.select_only([cube])
    before = (_mesh_hash(cube), tuple(map(tuple, cube.matrix_world)), len(cube.data.vertices))
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='X', offset_mm=5.0)
    n_coll = len(bpy.data.collections)
    lib.run_op(bpy.ops.splitforge.build)

    parts = _parts("BuildCube")
    assert len(parts) == 4, parts
    coll = bpy.data.collections[naming.build_collection_name("BuildCube")]
    assert sorted(o.name for o in coll.objects) == parts
    assert len(bpy.data.collections) == n_coll + 1
    vols = {}
    for name in parts:
        p = bpy.data.objects[name]
        assert lib.is_manifold(p), f"{name} not manifold"
        assert p["splitforge_source"] == "BuildCube"
        assert p["splitforge_cut_ids"] == "C1,C2", p["splitforge_cut_ids"]
        vols[name] = lib.volume(p)
    lib.assert_close(sum(vols.values()), 64000.0, rel=1e-6, msg="volume sum")
    # X cut 5 mm off center: A (x > 5) parts are 15 mm wide, B parts 25 mm
    lib.assert_close(vols["BuildCube_AA"], 20 * 15 * 40, rel=1e-6)
    lib.assert_close(vols["BuildCube_BB"], 20 * 25 * 40, rel=1e-6)

    src = bpy.data.objects["BuildCube"]
    assert (_mesh_hash(src), tuple(map(tuple, src.matrix_world)), len(src.data.vertices)) == before
    assert src.hide_get() and not src.modifiers, "source must only be hidden"

    # Disable one cut and rebuild from a part (the stack owner is resolved from the part)
    lib.select_only([bpy.data.objects[parts[0]]])
    src.splitforge_stack.cuts[1].enabled = False
    lib.run_op(bpy.ops.splitforge.build)
    parts2 = _parts("BuildCube")
    assert parts2 == ["BuildCube_A", "BuildCube_B"], parts2
    assert len(bpy.data.collections) == n_coll + 1, "rebuild must reuse the collection"
    assert sorted(o.name for o in coll.objects) == parts2
    assert not [m.name for m in bpy.data.meshes if m.users == 0], "orphan meshes after rebuild"
    for name in parts2:
        assert bpy.data.objects[name]["splitforge_cut_ids"] == "C1"
    assert _mesh_hash(bpy.data.objects["BuildCube"]) == before[0]

    # Transformed source (rotation + non-uniform scale + modifier): parts are in world space
    obj = lib.make_cube(20.0)
    obj.name = "Rotated"
    obj.rotation_euler = (0.3, 0.2, 0.5)
    obj.scale = (1.0, 2.0, 1.5)
    obj.location = (100.0, 0.0, 0.0)
    obj.modifiers.new("bevel", 'BEVEL').width = 1.0
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    eval_mesh = obj.evaluated_get(deps).to_mesh()
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(eval_mesh)
    bm.transform(obj.matrix_world)
    world_volume = bm.calc_volume()
    bm.free()
    obj.evaluated_get(deps).to_mesh_clear()
    lib.select_only([obj])
    hash_rot = _mesh_hash(obj)
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z', offset_mm=3.0)
    lib.run_op(bpy.ops.splitforge.build)
    rparts = [bpy.data.objects[n] for n in _parts("Rotated")]
    assert len(rparts) == 2
    for p in rparts:
        assert lib.is_manifold(p)
        assert p.matrix_world == p.matrix_world.Identity(4)
    lib.assert_close(sum(lib.volume(p) for p in rparts), world_volume, rel=1e-5, msg="world volume")
    zs = [min((p.matrix_world @ v.co).z for v in p.data.vertices) for p in rparts]
    lib.assert_close(max(zs), 3.0, abs_=1e-4, msg="world Z plane at offset 3 mm")
    assert _mesh_hash(obj) == hash_rot and len(obj.modifiers) == 1

    # Result collection excluded/hidden by the user: rebuild makes it visible again
    layer = bpy.context.view_layer.layer_collection.children[coll.name]
    layer.exclude = True
    bpy.context.view_layer.objects.active = bpy.data.objects["BuildCube"]  # hidden source
    lib.run_op(bpy.ops.splitforge.build)
    layer = bpy.context.view_layer.layer_collection.children[coll.name]
    assert not layer.exclude and _parts("BuildCube") == ["BuildCube_A", "BuildCube_B"]
    assert all(bpy.data.objects[n].visible_get() for n in _parts("BuildCube"))

    # Renamed source: the rebuild replaces the old parts (no stale duplicates) and renames the collection
    src = bpy.data.objects["BuildCube"]
    src.name = "Renamed"
    src.hide_set(False)
    lib.select_only([src])
    lib.run_op(bpy.ops.splitforge.build)
    assert _parts("BuildCube") == [] and _parts("Renamed") == ["Renamed_A", "Renamed_B"], (
        _parts("BuildCube"), _parts("Renamed"))
    coll = bpy.data.collections[naming.build_collection_name("Renamed")]
    assert sorted(o.name for o in coll.objects) == ["Renamed_A", "Renamed_B"]
    assert naming.build_collection_name("BuildCube") not in bpy.data.collections

    # Duplicated source (copies the last_build_collection pointer) builds into its own collection
    src.hide_set(False)
    lib.select_only([src])
    bpy.ops.object.duplicate()
    dup = bpy.context.active_object
    dup.name = "Dup"
    assert dup.splitforge_stack.last_build_collection == coll
    lib.run_op(bpy.ops.splitforge.build)
    assert _parts("Dup") == ["Dup_A", "Dup_B"] and _parts("Renamed") == ["Renamed_A", "Renamed_B"]
    assert naming.build_collection_name("Dup") in bpy.data.collections
    assert sorted(o.name for o in coll.objects) == ["Renamed_A", "Renamed_B"]
    src = bpy.data.objects["Renamed"]
    src.name = "BuildCube"
    lib.select_only([bpy.data.objects["Renamed_A"]])
    lib.run_op(bpy.ops.splitforge.build)
    coll = bpy.data.collections[naming.build_collection_name("BuildCube")]

    # Edit mode: Build is not available
    src.hide_set(False)
    lib.select_only([src])
    bpy.ops.object.mode_set(mode='EDIT')
    assert not bpy.ops.splitforge.build.poll()
    bpy.ops.object.mode_set(mode='OBJECT')

    # No enabled cut: build is not available; clear_build restores the source
    for c in src.splitforge_stack.cuts:
        c.enabled = False
    lib.select_only([bpy.data.objects["BuildCube_A"]])
    assert not bpy.ops.splitforge.build.poll()
    assert bpy.data.objects["BuildCube_A"]["splitforge_source"] == "BuildCube"
    lib.run_op(bpy.ops.splitforge.clear_build)
    assert _parts("BuildCube") == [] and not bpy.data.objects["BuildCube"].hide_get()
    assert naming.build_collection_name("BuildCube") not in bpy.data.collections
