# SPDX-License-Identifier: GPL-3.0-or-later
"""P3-3: double-sided dowel = sockets in both parts + a separate printable dowel part.

- Z cut (gap 0.4) + one DOWEL (6 x 12 mm, clearance 0.2, chamfer 0.5): parts A, B and
  ``<source>_Dowel_1``; both halves lose volume (a socket each, L/2 + c deep), the dowel
  is length x diameter (bbox, 0.05 mm), lies flat along X next to the source (min x beyond
  the source's +X side, resting on its lowest Z), chamfered ends narrower, manifold;
  the dowel volume fits the two sockets with clearance on every side (assembled check:
  the dowel moved to the connector position sits inside both sockets, nowhere in a part).
- Export writes the dowel file too; Rebuild replaces it (no leak), switching the type to a
  pin removes it, Clear Build removes it; dowel parts are numbered per dowel.
"""

import os
import shutil

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

import lib

D, LEN, C, GAP, CH = 6.0, 12.0, 0.2, 0.4, 0.5


def parts_of(name):
    return {o.name[len(name) + 1:]: o for o in bpy.data.objects if o.get("splitforge_source") == name}


def run(ctx):
    fit = ctx.module("connectors.fit")
    lib.set_scene_mm()
    cube = lib.make_cube(40.0)
    cube.name = "Dw"
    lib.select_only([cube])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    cut = cube.splitforge_stack.cuts[0]
    cut.gap_mm = GAP
    t = bpy.context.scene.splitforge.new_connector
    t.kind, t.width_mm, t.length_mm, t.clearance_mm, t.chamfer_mm = 'DOWEL', D, LEN, C, CH
    lib.run_op(bpy.ops.splitforge.connector_add, u=4.0, v=-3.0)
    lib.run_op(bpy.ops.splitforge.build)
    parts = parts_of("Dw")
    assert sorted(parts) == ["A", "B", "Dowel_1"], sorted(parts)
    a, b, dowel = parts["A"], parts["B"], parts["Dowel_1"]
    for p in (a, b, dowel):
        assert lib.is_manifold(p), p.name
    half_after_gap = 40 * 40 * (20 - GAP / 2)
    socket = 3.14159 * (D / 2 + C) ** 2 * (LEN / 2 + C)
    for p in (a, b):
        lib.assert_close(lib.volume(p), half_after_gap - socket, rel=0.002, msg=f"{p.name} volume")
    assert dowel.get("splitforge_dowel") == "Cut Z connector 1", dowel.get("splitforge_dowel")

    # Dimensions and placement: flat along X, next to the cube, on its floor
    xs = [v.co.x for v in dowel.data.vertices]
    ys = [v.co.y for v in dowel.data.vertices]
    zs = [v.co.z for v in dowel.data.vertices]
    lib.assert_close(max(xs) - min(xs), LEN, abs_=0.05, msg="dowel length")
    lib.assert_close(max(ys) - min(ys), D, abs_=0.05, msg="dowel diameter")
    lib.assert_close(max(zs) - min(zs), D, abs_=0.05, msg="dowel diameter")
    assert min(xs) > 20.0 + 4.9, min(xs)
    lib.assert_close(min(zs), -20.0, abs_=1e-4, msg="resting on the source's lowest Z")
    end = [v.co for v in dowel.data.vertices if abs(v.co.x - min(xs)) < 1e-6]
    end_r = max((Vector((0, co.y, co.z)) - Vector((0, sum(ys) / len(ys), sum(zs) / len(zs)))).length for co in end)
    lib.assert_close(end_r, D / 2 - CH, abs_=0.02, msg="chamfered end")
    lib.assert_close(lib.volume(dowel), 3.14159 * (D / 2) ** 2 * LEN, rel=0.05, msg="dowel volume")

    # Assembled: the dowel moved onto its connector axis sits inside the two sockets with clearance
    center = Vector((4.0, -3.0, 0.0))
    dowel_center = Vector(((max(xs) + min(xs)) / 2, sum(ys) / len(ys), sum(zs) / len(zs)))
    to_place = Matrix.Translation(center) @ Matrix.Rotation(-1.5707963, 4, 'Y') @ Matrix.Translation(-dowel_center)
    bvh = {}
    for p in (a, b):
        bm = lib.bm_of(p)
        bvh[p.name] = BVHTree.FromBMesh(bm)
        bm.free()
    # Close the gap as on assembly: A moves down by the gap; the dowel's lower half is in B, upper in A
    worst = []
    for v in dowel.data.vertices:
        q = to_place @ v.co
        if q.z >= 0.0:
            target, q2 = a, q + Vector((0, 0, GAP / 2))
        else:
            target, q2 = b, q - Vector((0, 0, GAP / 2))
        worst.append(fit.depth_inside(bvh[target.name], q2))
    assert max(worst) < -C * 0.5, f"dowel reaches into a part: {max(worst)}"
    ctx.metric("assembled_gap", f"{-max(worst):.3f}")

    # Export includes the dowel
    out = os.path.join(bpy.app.tempdir, "dowel_export")
    shutil.rmtree(out, ignore_errors=True)
    lib.run_op(bpy.ops.splitforge.export_parts, directory=out, formats={'STL'})
    assert sorted(os.listdir(out)) == ["Dw_A.stl", "Dw_B.stl", "Dw_Dowel_1.stl"], os.listdir(out)

    # Second dowel -> Dowel_2; rebuild replaces, no leaks
    lib.select_only([bpy.data.objects["Dw"]])
    lib.run_op(bpy.ops.splitforge.connector_add, u=-6.0, v=5.0)
    n_objects, n_meshes = len(bpy.data.objects), len(bpy.data.meshes)
    lib.run_op(bpy.ops.splitforge.build)
    assert sorted(parts_of("Dw")) == ["A", "B", "Dowel_1", "Dowel_2"], sorted(parts_of("Dw"))
    lib.run_op(bpy.ops.splitforge.build)
    assert len(bpy.data.objects) == n_objects + 1 and len(bpy.data.meshes) == n_meshes + 1
    assert not [m for m in bpy.data.meshes if m.users == 0]
    d1, d2 = parts_of("Dw")["Dowel_1"], parts_of("Dw")["Dowel_2"]
    y1 = [v.co.y for v in d1.data.vertices]
    y2 = [v.co.y for v in d2.data.vertices]
    assert min(y2) > max(y1), "dowels side by side"

    # A pin instead: the dowel parts go away on rebuild; Clear Build removes everything
    for c in bpy.data.objects["Dw"].splitforge_stack.cuts[0].connectors:
        c.kind = 'CYL_PIN'
    lib.select_only([bpy.data.objects["Dw"]])
    lib.run_op(bpy.ops.splitforge.build)
    assert sorted(parts_of("Dw")) == ["A", "B"], sorted(parts_of("Dw"))
    for c in bpy.data.objects["Dw"].splitforge_stack.cuts[0].connectors:
        c.kind = 'DOWEL'
    lib.run_op(bpy.ops.splitforge.build)
    lib.run_op(bpy.ops.splitforge.clear_build)
    assert not parts_of("Dw") and not [o for o in bpy.data.objects if "Dowel" in o.name]
