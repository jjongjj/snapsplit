# SPDX-License-Identifier: GPL-3.0-or-later
"""P1-9: CYL_PIN / RECT_TENON pins (UNION) and sockets (DIFFERENCE), one boolean per part.

Socket size = pin size + 2 x clearance, measured on a section through the socket.
"""

import bmesh
import bpy
from mathutils import Vector

import lib


def _section_loops(meshlib, obj, z):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    try:
        return meshlib.section_loops_2d(bm, Vector((0, 0, z)), Vector((0, 0, 1)),
                                        Vector((1, 0, 0)), Vector((0, 1, 0)))
    finally:
        bm.free()


def _small_loops(loops, limit=20.0):
    """Bounding boxes (w, h, cx, cy) of the loops smaller than ``limit`` (pins/sockets)."""
    out = []
    for loop in loops:
        us, vs = [p[0] for p in loop], [p[1] for p in loop]
        w, h = max(us) - min(us), max(vs) - min(vs)
        if w < limit and h < limit:
            out.append((w, h, (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2))
    return sorted(out, key=lambda b: b[2])


def _build(name, kind, pin_side, clearance, count=3, width=5.0, height=5.0):
    cube = lib.make_cube(40.0)
    cube.name = name
    lib.select_only([cube])
    s = bpy.context.scene.splitforge
    s.new_connector_kind = kind
    s.new_connector_width_mm, s.new_connector_height_mm, s.new_connector_length_mm = width, height, 10.0
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    cut = cube.splitforge_stack.cuts[0]
    cut.connector_count = count
    lib.run_op(bpy.ops.splitforge.connector_add_auto)
    for c in cut.connectors:
        c.pin_side = pin_side
        c.clearance_mm = clearance
    lib.run_op(bpy.ops.splitforge.build)
    parts = {o.name[len(name) + 1:]: o for o in bpy.data.objects if o.get("splitforge_source") == name}
    assert sorted(parts) == ["A", "B"], sorted(parts)
    return parts


def run(ctx):
    meshlib = ctx.module("core.meshlib")
    boolean = ctx.module("core.boolean")
    lib.set_scene_mm()
    half = 40.0 * 40.0 * 20.0

    # Count booleans: one UNION and one DIFFERENCE per part regardless of the 3 connectors
    calls = []
    original = boolean.apply

    def counting(target, operand_bm, operation, preference='AUTO', **kwargs):
        calls.append((target.name, operation))
        return original(target, operand_bm, operation, preference, **kwargs)
    boolean.apply = counting
    try:
        parts = _build("PinA", 'CYL_PIN', 'A', 0.3)
    finally:
        boolean.apply = original
    assert sorted(calls) == [("PinA_A", 'UNION'), ("PinA_B", 'DIFFERENCE')], calls

    a, b = parts["A"], parts["B"]
    assert lib.is_manifold(a) and lib.is_manifold(b)
    va, vb = lib.volume(a), lib.volume(b)
    assert va > half * 1.001 and vb < half * 0.999, (va, vb)
    # Pin cross-section below the seam (z = -2) on the pin part: diameter 5
    pins = _small_loops(_section_loops(meshlib, a, -2.0))
    assert len(pins) == 3, pins
    for w, h, _cx, cy in pins:
        lib.assert_close(w, 5.0, abs_=0.02, msg="pin diameter")
        lib.assert_close(h, 5.0, abs_=0.02, msg="pin diameter")
        assert abs(cy) < 1e-4
    # Socket holes in part B at z = -2: diameter 5 + 2 x 0.3, same centers
    sockets = _small_loops(_section_loops(meshlib, b, -2.0))
    assert len(sockets) == 3, sockets
    for (w, h, cx, _cy), pin in zip(sockets, pins):
        lib.assert_close(w, 5.6, abs_=0.02, msg="socket diameter")
        lib.assert_close(h, 5.6, abs_=0.02, msg="socket diameter")
        lib.assert_close(cx, pin[2], abs_=1e-4, msg="socket under the pin")
    # Socket depth: length/2 + clearance = 5.3 below the seam, closed below that
    assert len(_small_loops(_section_loops(meshlib, b, -5.25))) == 3
    assert not _small_loops(_section_loops(meshlib, b, -5.35))

    # pin_side B: the other part gets the pins
    parts = _build("PinB", 'CYL_PIN', 'B', 0.3)
    va, vb = lib.volume(parts["A"]), lib.volume(parts["B"])
    assert va < half * 0.999 and vb > half * 1.001, (va, vb)
    assert lib.is_manifold(parts["A"]) and lib.is_manifold(parts["B"])

    # Rectangular tenon 6 x 4, clearance 0.25 (scene default when the connector says -1)
    bpy.context.scene.splitforge.clearance_mm = 0.25
    parts = _build("Tenon", 'RECT_TENON', 'A', -1.0, count=2, width=6.0, height=4.0)
    a, b = parts["A"], parts["B"]
    assert lib.is_manifold(a) and lib.is_manifold(b)
    tenons = _small_loops(_section_loops(meshlib, a, -2.0))
    sockets = _small_loops(_section_loops(meshlib, b, -2.0))
    assert len(tenons) == len(sockets) == 2, (tenons, sockets)
    for w, h, _cx, _cy in tenons:
        lib.assert_close(w, 6.0, abs_=0.02)
        lib.assert_close(h, 4.0, abs_=0.02)
    for w, h, _cx, _cy in sockets:
        lib.assert_close(w, 6.5, abs_=0.02)
        lib.assert_close(h, 4.5, abs_=0.02)

    # Gap 1 mm: pin sticks out 5 mm from the pin face (z = +0.5), socket 5.3 deep from z = -0.5
    cube = lib.make_cube(40.0)
    cube.name = "Gap"
    lib.select_only([cube])
    bpy.context.scene.splitforge.new_connector_kind = 'CYL_PIN'
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    cut = cube.splitforge_stack.cuts[0]
    cut.gap_mm = 1.0
    cut.connector_count = 1
    lib.run_op(bpy.ops.splitforge.connector_add_auto)
    cut.connectors[0].clearance_mm = 0.3
    lib.run_op(bpy.ops.splitforge.build)
    a, b = bpy.data.objects["Gap_A"], bpy.data.objects["Gap_B"]
    assert lib.is_manifold(a) and lib.is_manifold(b)
    zmin_a = min(v.co.z for v in a.data.vertices)
    lib.assert_close(zmin_a, 0.5 - 5.0, abs_=1e-4, msg="pin tip")
    assert len(_small_loops(_section_loops(meshlib, b, -0.5 - 5.25))) == 1
    assert not _small_loops(_section_loops(meshlib, b, -0.5 - 5.35))

    # Overlapping connectors (joined operand intersects itself): still manifold, pins merged
    cube = lib.make_cube(40.0)
    cube.name = "Overlap"
    lib.select_only([cube])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    for u in (0.0, 3.0):
        lib.run_op(bpy.ops.splitforge.connector_add, u=u, v=0.0)
    lib.run_op(bpy.ops.splitforge.build)
    a, b = bpy.data.objects["Overlap_A"], bpy.data.objects["Overlap_B"]
    assert lib.is_manifold(a) and lib.is_manifold(b)
    assert len(_small_loops(_section_loops(meshlib, a, -2.0))) == 1  # one merged pin outline
    assert lib.volume(a) > half * 1.001 and lib.volume(b) < half * 0.999
