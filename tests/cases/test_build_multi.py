# SPDX-License-Identifier: GPL-3.0-or-later
"""P1-10: two cuts with connectors; every connector is applied; rebuilding leaks nothing.

Auto distribution works per seam region: the X seam is split by the Z cut into two
regions, so "2 per seam" gives 4 connectors on each cut and none on another cut plane.
"""

import math

import bpy

import lib


def _state():
    return (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.collections),
            sorted(m.name for m in bpy.data.meshes if m.users == 0))


def run(ctx):
    lib.set_scene_mm()
    cube = lib.make_cube(40.0)
    cube.name = "Multi"
    lib.select_only([cube])
    for axis in ('Z', 'X'):
        lib.run_op(bpy.ops.splitforge.stack_add_plane, axis=axis)
        cut = cube.splitforge_stack.cuts[-1]
        cut.connector_count = 2
    for i in range(2):
        cube.splitforge_stack.active_index = i
        lib.run_op(bpy.ops.splitforge.connector_add_auto)
    for cut in cube.splitforge_stack.cuts:
        assert len(cut.connectors) == 4, (cut.name, len(cut.connectors))
        # Seam frame v axis of both cuts crosses the other cut plane at v = 0
        for c in cut.connectors:
            assert abs(c.u) > 3.0 and abs(c.v) > 3.0, (cut.name, c.u, c.v)
    lib.run_op(bpy.ops.splitforge.build)

    parts = [o for o in bpy.data.objects if o.get("splitforge_source") == "Multi"]
    assert len(parts) == 4, [o.name for o in parts]
    for p in parts:
        assert lib.is_manifold(p), p.name
    # All 8 connectors were applied: total = cube + 8 x (pin protrusion - socket)
    def ngon(r, n=32):
        return 0.5 * n * r * r * math.sin(2 * math.pi / n)
    clearance = bpy.context.scene.splitforge.clearance_mm
    pin = ngon(2.5) * 5.0
    socket = ngon(2.5 + clearance) * (5.0 + clearance)
    vols = [lib.volume(p) for p in parts]
    lib.assert_close(sum(vols), 64000.0 + 8 * (pin - socket), rel=1e-4, msg="all connectors applied")
    for v in vols:
        assert abs(v - 16000.0) > 1.0, vols

    first = _state()
    assert first[3] == [], f"orphan meshes: {first[3]}"
    for _ in range(2):
        lib.run_op(bpy.ops.splitforge.build)
        assert _state() == first, (first, _state())
    assert not [o.name for o in bpy.data.objects if o.name.startswith("_SplitForge")]
