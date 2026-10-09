# SPDX-License-Identifier: GPL-3.0-or-later
"""P3-6: the legacy SnapSplit baselines, rebuilt with the new pipeline (the legacy code is gone).

Each block is the SplitForge equivalent of a removed legacy case (test_legacy_*):
- split_cube: Z cut of a 40 mm cube -> 2 manifold parts, volume preserved (1 %), source kept;
- split_monkey: Z cut of a filled Suzanne -> capped manifold parts (cut through the eyes:
  the eye loops are islands, not holes - the old cap-nesting regression);
- split_hollow: hollow box -> ring caps, the cavity stays (volume = 40^3 - 36^3);
- parts_count 3 + split offset: two Z cuts -> 3 parts, offset cut at the requested height;
- connectors: 3 CYL_PIN per seam -> manifold, pin part gains, socket part loses volume;
- material profiles: the clearance follows the chosen material (PETG 0.30 mm) in the socket.
Freehand cuts, click placement, snap/dovetail/custom connectors have their own Phase 2/3 tests.
"""

import bpy
from mathutils import Vector

import lib


def parts_of(name):
    return sorted((o for o in bpy.data.objects if o.get("splitforge_source") == name), key=lambda o: o.name)


def build_z(obj, offsets=(0.0,), count=0):
    lib.select_only([obj])
    for off in offsets:
        lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z', offset_mm=off)
        if count:
            obj.splitforge_stack.cuts[-1].connector_count = count
            lib.run_op(bpy.ops.splitforge.connector_add_auto)
    lib.run_op(bpy.ops.splitforge.build)
    return parts_of(obj.name)


def run(ctx):
    meshlib = ctx.module("core.meshlib")
    lib.set_scene_mm()

    cube = lib.make_cube(40.0)
    cube.name = "Cube"
    parts = build_z(cube)
    assert len(parts) == 2 and all(lib.is_manifold(p) for p in parts)
    lib.assert_close(sum(lib.volume(p) for p in parts), 64000.0, rel=0.01)
    assert "Cube" in bpy.data.objects and len(cube.data.vertices) == 8

    monkey = lib.make_monkey_manifold(40.0)
    monkey.name = "Monkey"
    for off in (0.0, 4.0):     # through the head, through the eyes
        monkey.splitforge_stack.cuts.clear()
        parts = build_z(monkey, (off,))
        assert len(parts) == 2 and all(lib.is_manifold(p) for p in parts), (off, [p.name for p in parts])

    box = lib.make_hollow_box(40.0, 2.0)
    box.name = "Hollow"
    parts = build_z(box)
    assert len(parts) == 2 and all(lib.is_manifold(p) for p in parts)
    lib.assert_close(sum(lib.volume(p, signed=True) for p in parts), 40.0 ** 3 - 36.0 ** 3, rel=1e-4)

    bar = lib.make_cube(40.0)
    bar.name = "Three"
    parts = build_z(bar, (-40.0 / 6.0, 40.0 / 6.0 + 2.0))
    assert len(parts) == 3 and all(lib.is_manifold(p) for p in parts), [p.name for p in parts]
    top = max(parts, key=lambda p: min(v.co.z for v in p.data.vertices))
    lib.assert_close(min(v.co.z for v in top.data.vertices), 40.0 / 6.0 + 2.0, abs_=1e-4, msg="offset cut")

    pins = lib.make_cube(40.0)
    pins.name = "Pins"
    bpy.context.scene.splitforge.new_connector.kind = 'CYL_PIN'
    parts = build_z(pins, (0.0,), count=3)
    assert len(pins.splitforge_stack.cuts[0].connectors) == 3
    va, vb = lib.volume(parts[0]), lib.volume(parts[1])
    assert all(lib.is_manifold(p) for p in parts) and va > 32000.0 > vb, (va, vb)

    s = bpy.context.scene.splitforge
    s.material = 'PETG'
    assert abs(s.clearance_mm - 0.30) < 1e-6, s.clearance_mm
    mat = lib.make_cube(40.0)
    mat.name = "Petg"
    parts = build_z(mat, (0.0,), count=1)
    bm = lib.bm_of(parts[1])

    loops = meshlib.section_loops_2d(bm, Vector((0, 0, -2)), Vector((0, 0, 1)), Vector((1, 0, 0)), Vector((0, 1, 0)))
    bm.free()
    hole = [lp for lp in loops if max(p[0] for p in lp) - min(p[0] for p in lp) < 20.0]
    assert len(hole) == 1
    lib.assert_close(max(p[0] for p in hole[0]) - min(p[0] for p in hole[0]), 5.0 + 0.6, abs_=0.02,
                     msg="PETG socket = pin + 2 x 0.30")
