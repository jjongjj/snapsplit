# SPDX-License-Identifier: GPL-3.0-or-later
"""P1-3: the cut stack PropertyGroups survive save/load and add-on disable/enable."""

import os

import bpy

import lib


def _fill(obj):
    stack = obj.splitforge_stack
    for i, (origin, normal) in enumerate((((0, 0, 3.5), (0, 0, 1)), ((-2, 0, 0), (1, 1, 0)))):
        cut = stack.cuts.add()
        cut.name = f"Cut {i}"
        cut.uid = f"C{i + 1}"
        cut.origin = origin
        cut.normal = normal
        cut.gap_mm = 0.25 * (i + 1)
        cut.cap = bool(i)
        cut.distribution = 'GRID'
        cut.connector_rows = 3 + i
    stroke = stack.cuts.add()
    stroke.name = "Stroke 3"
    stroke.uid = "C3"
    stroke.kind = 'STROKE'
    stroke.direction = (0.0, 0.6, 0.8)
    for k in range(5):
        stroke.points.add().co = (k * 3.0 - 6.0, 0.5 * k, -0.25 * k * k)
    stack.active_index = 1
    stack.mode = 'EASY'
    for j in range(3):
        c = stack.cuts[j % 2].connectors.add()
        c.kind = 'RECT_TENON' if j == 1 else 'CYL_PIN'
        c.u, c.v = 1.5 * j, -2.0 * j
        c.rotation_deg = 15.0 * j
        c.width_mm, c.height_mm, c.length_mm = 4.0 + j, 6.0, 12.0 + j
        c.pin_side = 'B' if j == 2 else 'A'
        c.clearance_mm = 0.3


def _snapshot(obj):
    stack = obj.splitforge_stack
    cuts = []
    for cut in stack.cuts:
        conns = [(c.enabled, c.kind, round(c.u, 5), round(c.v, 5), round(c.rotation_deg, 5),
                  round(c.width_mm, 5), round(c.height_mm, 5), round(c.length_mm, 5), c.pin_side,
                  round(c.clearance_mm, 5)) for c in cut.connectors]
        cuts.append((cut.name, cut.uid, cut.enabled, cut.kind, tuple(round(x, 5) for x in cut.origin),
                     tuple(round(x, 5) for x in cut.normal), round(cut.gap_mm, 5), cut.cap,
                     cut.distribution, cut.connector_rows, conns, tuple(round(x, 5) for x in cut.direction),
                     [tuple(round(x, 5) for x in p.co) for p in cut.points]))
    return (stack.active_index, stack.mode, stack.schema_version, cuts, bpy.context.scene.splitforge.boolean_quality)


def run(ctx):
    lib.set_scene_mm()
    cube = lib.make_cube(40.0)
    cube.name = "ModelCube"
    _fill(cube)
    bpy.context.scene.splitforge.boolean_quality = 'FAST'
    before = _snapshot(cube)
    assert len(before[3]) == 3 and sum(len(c[10]) for c in before[3]) == 3, before
    assert before[3][2][3] == 'STROKE' and len(before[3][2][12]) == 5 and before[2] == 2 and before[4] == 'FAST', before

    path = os.path.join(bpy.app.tempdir, "test_model.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, check_existing=False)
    bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
    assert "ModelCube" not in bpy.data.objects
    bpy.ops.wm.open_mainfile(filepath=path)
    after = _snapshot(bpy.data.objects["ModelCube"])
    assert after == before, (before, after)

    # Disable/enable three times: the stored values come back each time
    for _ in range(3):
        bpy.ops.preferences.addon_disable(module=ctx.addon_module)
        assert not hasattr(bpy.data.objects["ModelCube"], "splitforge_stack")
        bpy.ops.preferences.addon_enable(module=ctx.addon_module)
        assert _snapshot(bpy.data.objects["ModelCube"]) == before
