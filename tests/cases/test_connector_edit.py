# SPDX-License-Identifier: GPL-3.0-or-later
"""P3-4: per-connector editing (position, rotation, size, pin side, clearance, type) is
reflected by Rebuild, and edits are undoable.

Z cut (gap 0) + one RECT_TENON 8 x 4 x 10 at (0, 0):
- U += 10 mm -> the tenon's section center moves 10 mm along the seam tangent (0.1 mm);
- rotation 90 deg -> the section bbox swaps width and height;
- width / height / length / clearance edits -> section sizes and depths follow;
- pin side B -> the other part carries the tenon;
- type -> DOVETAIL: tapered section; insert depth -> pin protrudes (1 - e) x L;
- tip chamfer: 45-degree bevel over the chamfer length, tip height kept, socket not chamfered;
- an edit followed by ed.undo restores the previous value and Rebuild geometry.
"""

import bmesh
import bpy
from mathutils import Vector

import lib


def parts():
    return {o.name.split("_")[-1]: o for o in bpy.data.objects if o.get("splitforge_source") == "Ed"}


def boxes(meshlib, obj, z):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    try:
        loops = meshlib.section_loops_2d(bm, Vector((0, 0, z)), Vector((0, 0, 1)), Vector((1, 0, 0)),
                                         Vector((0, 1, 0)))
    finally:
        bm.free()
    out = []
    for lp in loops:
        xs, ys = [p[0] for p in lp], [p[1] for p in lp]
        if max(xs) - min(xs) < 20 and max(ys) - min(ys) < 20:
            out.append((max(xs) - min(xs), max(ys) - min(ys), (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2))
    return out


def rebuild():
    lib.select_only([bpy.data.objects["Ed"]])
    lib.run_op(bpy.ops.splitforge.build)
    return parts()


def run(ctx):
    meshlib = ctx.module("core.meshlib")
    lib.set_scene_mm()
    bpy.context.preferences.edit.undo_steps = 64
    cube = lib.make_cube(40.0)
    cube.name = "Ed"
    lib.select_only([cube])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    t = bpy.context.scene.splitforge.new_connector
    t.kind, t.width_mm, t.height_mm, t.length_mm, t.clearance_mm = 'RECT_TENON', 8.0, 4.0, 10.0, 0.2
    lib.run_op(bpy.ops.splitforge.connector_add, u=0.0, v=0.0)

    def conn():
        return bpy.data.objects["Ed"].splitforge_stack.cuts[0].connectors[0]

    p = rebuild()
    (w, h, cx, cy), = boxes(meshlib, p["A"], -2.0)
    lib.assert_close(w, 8.0, abs_=0.02)
    lib.assert_close(h, 4.0, abs_=0.02)
    x0 = cx

    conn().u += 10.0
    (w, h, cx, cy), = boxes(meshlib, rebuild()["A"], -2.0)
    lib.assert_close(cx - x0, 10.0, abs_=0.1, msg="U moved the tenon")
    lib.assert_close(cy, 0.0, abs_=0.1)

    conn().rotation_deg = 90.0
    (w, h, cx, _cy), = boxes(meshlib, rebuild()["A"], -2.0)
    lib.assert_close(w, 4.0, abs_=0.02, msg="rotation swaps the bbox")
    lib.assert_close(h, 8.0, abs_=0.02, msg="rotation swaps the bbox")
    lib.assert_close(cx - x0, 10.0, abs_=0.1)

    c = conn()
    c.rotation_deg, c.width_mm, c.height_mm, c.length_mm, c.clearance_mm = 0.0, 6.0, 5.0, 14.0, 0.3
    p = rebuild()
    (w, h, _cx, _cy), = boxes(meshlib, p["A"], -2.0)
    lib.assert_close(w, 6.0, abs_=0.02)
    lib.assert_close(h, 5.0, abs_=0.02)
    (w, h, _cx, _cy), = boxes(meshlib, p["B"], -2.0)
    lib.assert_close(w, 6.6, abs_=0.02, msg="clearance edit")
    lib.assert_close(h, 5.6, abs_=0.02, msg="clearance edit")
    assert boxes(meshlib, p["A"], -6.9) and not boxes(meshlib, p["A"], -7.1), "length 14: tip at -7"
    assert boxes(meshlib, p["B"], -7.25) and not boxes(meshlib, p["B"], -7.35), "socket 7 + 0.3 deep"

    conn().embed_pct = 30.0     # 70 % of 14 sticks out
    p = rebuild()
    assert boxes(meshlib, p["A"], -9.7) and not boxes(meshlib, p["A"], -9.9), "insert depth 30 %"
    conn().embed_pct = 50.0

    conn().pin_side = 'B'
    p = rebuild()
    assert boxes(meshlib, p["B"], 2.0) and len(boxes(meshlib, p["A"], 2.0)) == 1
    assert lib.volume(p["B"]) > lib.volume(p["A"]), "pin side B: B carries the tenon"
    conn().pin_side = 'A'

    conn().kind = 'DOVETAIL'
    conn().taper_pct = 40.0
    p = rebuild()
    (w_hi, _h, _x, _y), = boxes(meshlib, p["A"], -1.0)
    (w_lo, _h, _x, _y), = boxes(meshlib, p["A"], -6.0)
    assert w_lo < w_hi - 0.5, ("dovetail narrows towards the tip", w_hi, w_lo)

    # Tip chamfer (cylinder pin 6 x 10, tip at z = -5): 45 degrees over 1 mm, full width above it;
    # the socket stays a full cylinder
    c = conn()
    c.kind, c.width_mm, c.length_mm, c.chamfer_mm, c.clearance_mm = 'CYL_PIN', 6.0, 10.0, 1.0, 0.2
    p = rebuild()
    for z, width in ((-4.5, 5.0), (-4.01, 2 * (2.0 + 0.99)), (-3.5, 6.0), (-1.0, 6.0)):
        (w, _h, _x, _y), = boxes(meshlib, p["A"], z)
        lib.assert_close(w, width, abs_=0.02, msg=f"chamfered pin width at z={z}")
    (w, _h, _x, _y), = boxes(meshlib, p["B"], -4.5)
    lib.assert_close(w, 6.4, abs_=0.02, msg="socket not chamfered")
    assert boxes(meshlib, p["A"], -4.99) and not boxes(meshlib, p["A"], -5.01), "tip still at -5"
    c = conn()
    c.kind, c.width_mm, c.chamfer_mm = 'DOVETAIL', 6.0, 0.0

    # Undo restores an edit (and the rebuilt geometry follows the restored value)
    bpy.ops.ed.undo_push(message="before width")
    conn().width_mm = 9.0
    bpy.ops.ed.undo_push(message="width 9")
    bpy.ops.ed.undo()
    assert abs(conn().width_mm - 6.0) < 1e-6, conn().width_mm
    p = rebuild()
    (w, _h, _x, _y), = boxes(meshlib, p["A"], -1.0)
    assert w < 6.0 + 1e-3, w
    bpy.ops.ed.redo()
    assert abs(conn().width_mm - 9.0) < 1e-6, conn().width_mm
