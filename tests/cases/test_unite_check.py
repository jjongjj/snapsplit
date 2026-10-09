# SPDX-License-Identifier: GPL-3.0-or-later
"""D16: uniting intersecting shells (Accurate Build start) must not lose volume.

``boolean.unite_bm`` checked only manifold / faces / "not larger". A union that
shrank by 3 % (or dropped a shell) was accepted and became the baseline of every
later volume check. Now the result must enclose the same volume as the input's
winding-number ray integral (overlaps counted once, independent of the solver).

Checks: real unions pass on several meshes (Suzanne with eyes at 3 densities,
hollow box with a peg through the wall, nested shell, crossing solids); injected
losses (3 % shrink, a dropped eye, 1 % shrink) are rejected with a reason; an
Accurate Build with the injected loss warns and keeps the shells overlapping
(manifold parts, no "united" info); the ray integral itself matches exact volumes.
"""


import bmesh
import bpy
from mathutils import Matrix

import lib


def _bm_from_parts(*builders):
    bm = bmesh.new()
    for build in builders:
        part = bmesh.new()
        build(part)
        mesh = bpy.data.meshes.new("_tmp")
        part.to_mesh(mesh)
        part.free()
        bm.from_mesh(mesh)
        bpy.data.meshes.remove(mesh)
    return bm


def _cube(size, offset=(0, 0, 0), inward=False):
    def build(bm):
        bmesh.ops.create_cube(bm, size=size, matrix=Matrix.Translation(offset))
        if inward:
            bmesh.ops.reverse_faces(bm, faces=bm.faces)
    return build


def _cyl(r, depth, offset, segments=48):
    def build(bm):
        bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=r, radius2=r, depth=depth,
                              matrix=Matrix.Translation(offset))
    return build


def _monkey_bm(levels):
    monkey = lib.make_monkey_manifold(40.0)
    if levels:
        mod = monkey.modifiers.new("s", 'SUBSURF')
        mod.levels = levels
        lib.select_only([monkey])
        bpy.ops.object.modifier_apply(modifier=mod.name)
    bm = lib.bm_of(monkey)
    bpy.data.objects.remove(monkey)
    return bm


def run(ctx):
    lib.set_scene_mm()
    boolean = ctx.module("core.boolean")
    meshlib = ctx.module("core.meshlib")

    # The ray integral (a sampled estimate) matches exact volumes (single shells, a cavity) and counts
    # overlaps once
    cube = _bm_from_parts(_cube(40.0))
    lib.assert_close(meshlib.winding_volume(cube), 64000.0, rel=1e-6, msg="cube")
    hollow = _bm_from_parts(_cube(40.0), _cube(34.0, inward=True))
    lib.assert_close(meshlib.winding_volume(hollow), 64000.0 - 34.0 ** 3, rel=0.03, msg="hollow")
    pair = _bm_from_parts(_cube(20.0), _cube(20.0, offset=(10, 10, 10)))
    lib.assert_close(meshlib.winding_volume(pair), 2 * 8000.0 - 1000.0, rel=0.03, msg="overlapping cubes")
    for bm in (cube, hollow, pair):
        bm.free()

    # Real unions pass (and agree with the exact volume of the result)
    cases = {
        "suzanne": lambda: _monkey_bm(0),
        "suzanne_s1": lambda: _monkey_bm(1),
        "suzanne_s2": lambda: _monkey_bm(2),
        "hollow_peg": lambda: _bm_from_parts(_cube(40.0), _cube(34.0, inward=True), _cyl(6.0, 10.0, (8, 0, 20.5))),
        "nested": lambda: _bm_from_parts(_cube(40.0), _cube(10.0, offset=(5, 5, 5))),
        "crossing": lambda: _bm_from_parts(_cyl(8.0, 50.0, (0, 0, 0)), _cube(30.0)),
    }
    for name, make in cases.items():
        bm = make()
        before = meshlib.bm_volume(bm)
        united, why = boolean.unite_bm(bm)
        assert united is not None, f"{name}: {why}"
        after = meshlib.bm_volume(united)
        tri = bm.copy()
        bmesh.ops.triangulate(tri, faces=tri.faces[:])   # unite_bm works on triangles (n-gon volumes)
        bounds = meshlib.bm_bounds(tri)
        ray_in = meshlib.winding_volume(tri, bounds=bounds)
        ray_out = meshlib.winding_volume(united, bounds=bounds)
        tri.free()
        ctx.metric(name, f"{before:.1f}->{after:.1f} ray {ray_in:.1f}/{ray_out:.1f} "
                         f"({100.0 * (ray_out - ray_in) / ray_in:+.4f} %, exact {100.0 * (ray_out - after) / after:+.3f} %)")
        assert after <= before * (1 + 1e-3)
        lib.assert_close(ray_out, ray_in, rel=2e-4, msg=f"{name}: ray integral, result vs input")
        # sampled estimate: box-aligned shells (cavity) are off by the grid quantization
        lib.assert_close(ray_out, after, rel=0.03, msg=f"{name}: ray integral vs exact union volume")
        united.free()
        bm.free()

    # Injected losses are rejected
    original = boolean._united

    def shrunk(factor):
        def fake(target):
            mesh = original(target)
            c = sum((v.co for v in mesh.vertices), mesh.vertices[0].co * 0.0) / len(mesh.vertices)
            mesh.transform(Matrix.Translation(c) @ Matrix.Scale(factor, 4) @ Matrix.Translation(-c))
            return mesh
        return fake

    def drop_smallest_shell(target):
        mesh = original(target)
        bm = bmesh.new()
        bm.from_mesh(mesh)
        smallest = min(meshlib.shells(bm), key=len)
        bmesh.ops.delete(bm, geom=smallest, context='VERTS')
        bm.to_mesh(mesh)
        bm.free()
        return mesh

    def two_groups():
        """Crossing cylinder + box (united into one shell) and a separate cube (stays its own shell)."""
        return _bm_from_parts(_cyl(8.0, 50.0, (0, 0, 0)), _cube(30.0), _cube(12.0, offset=(60, 0, 0)))

    injections = {
        "shrink_3pct": (shrunk(0.99), lambda: _monkey_bm(1)),
        "shrink_1pct": (shrunk(0.9967), lambda: _monkey_bm(1)),
        "dropped_shell": (drop_smallest_shell, two_groups),
    }
    try:
        for name, (fake, make) in injections.items():
            boolean._united = fake
            bm = make()
            united, why = boolean.unite_bm(bm)
            bm.free()
            assert united is None, f"{name}: lossy union accepted"
            assert "changed the enclosed volume" in why, why
            ctx.metric(name, why)

        # Accurate Build with the 3 % loss: warning, shells stay overlapping, parts still valid
        boolean._united = shrunk(0.99)
        monkey = lib.make_monkey_manifold(40.0)
        lib.select_only([monkey])
        bpy.context.scene.splitforge.boolean_quality = 'ACCURATE'
        lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z', offset_mm=-6.0)
        result = ctx.module("cuts.build").build(bpy.context, monkey)
    finally:
        boolean._united = original
    assert any("could not be united" in w for w in result.warnings), result.warnings
    assert not any("united into one solid" in i for i in result.infos), result.infos
    parts = [bpy.data.objects[n] for n in result.parts]
    assert len(parts) == 2 and all(lib.is_manifold(p) for p in parts)
    ctx.metric("build_warning", next(w for w in result.warnings if "could not be united" in w))
    # Without the injection the same Build unites the shells
    result = ctx.module("cuts.build").build(bpy.context, monkey)
    assert any("united into one solid" in i for i in result.infos), result.infos
    assert not result.warnings, result.warnings
