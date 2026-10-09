# SPDX-License-Identifier: GPL-3.0-or-later
"""P1-3 / P3 / P4: the cut stack PropertyGroups survive save/load and add-on disable/enable.

Includes every connector type and its per-type values (taper, insert depth, chamfer, snap
bumps, custom mesh object pointer), the scene's new-connector template, and (schema 4) the
polyline and polygon cut kinds with a polygon depth.
"""

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
    for kind, depth in (('POLYLINE', 0.0), ('POLYGON', 7.5)):
        extra = stack.cuts.add()
        extra.name, extra.uid, extra.kind, extra.depth_mm = kind.title(), f"C{len(stack.cuts)}", kind, depth
        extra.direction = (0.0, 0.0, -1.0)
        for co in ((-5.0, -5.0, 9.0), (5.0, -5.0, 9.0), (0.0, 6.0, 9.0)):
            extra.points.add().co = co
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
    # Phase 3 connector types with their own values
    knob = bpy.data.objects.new("ModelKnob", bpy.data.meshes.new("ModelKnob"))
    bpy.context.scene.collection.objects.link(knob)
    for j, kind in enumerate(('DOVETAIL', 'SNAP_PIN', 'SNAP_DOVETAIL', 'CUSTOM', 'DOWEL')):
        c = stack.cuts[0].connectors.add()
        c.kind = kind
        c.u = 3.0 * j
        c.taper_pct = 10.0 + j
        c.embed_pct = 40.0 + j
        c.chamfer_mm = 0.1 * j
        c.snap_count = 1 + j
        c.snap_diameter_mm = 1.5 + 0.1 * j
        c.snap_protrusion_mm = 0.3 + 0.1 * j
        if kind == 'CUSTOM':
            c.custom_object = knob
    t = bpy.context.scene.splitforge.new_connector
    t.kind, t.width_mm, t.taper_pct, t.custom_object = 'SNAP_TENON', 7.5, 33.0, knob


def _snapshot(obj):
    stack = obj.splitforge_stack
    cuts = []
    for cut in stack.cuts:
        conns = [(c.enabled, c.kind, round(c.u, 5), round(c.v, 5), round(c.rotation_deg, 5),
                  round(c.width_mm, 5), round(c.height_mm, 5), round(c.length_mm, 5), c.pin_side,
                  round(c.clearance_mm, 5), round(c.taper_pct, 5), round(c.embed_pct, 5), round(c.chamfer_mm, 5),
                  c.snap_count, round(c.snap_diameter_mm, 5), round(c.snap_protrusion_mm, 5),
                  c.custom_object.name if c.custom_object else None) for c in cut.connectors]
        cuts.append((cut.name, cut.uid, cut.enabled, cut.kind, tuple(round(x, 5) for x in cut.origin),
                     tuple(round(x, 5) for x in cut.normal), round(cut.gap_mm, 5), cut.cap,
                     cut.distribution, cut.connector_rows, conns, tuple(round(x, 5) for x in cut.direction),
                     [tuple(round(x, 5) for x in p.co) for p in cut.points], round(cut.depth_mm, 5)))
    t = bpy.context.scene.splitforge.new_connector
    template = (t.kind, round(t.width_mm, 5), round(t.taper_pct, 5), t.custom_object.name if t.custom_object else None)
    return (stack.active_index, stack.mode, stack.schema_version, cuts, bpy.context.scene.splitforge.boolean_quality,
            template)


def run(ctx):
    lib.set_scene_mm()
    cube = lib.make_cube(40.0)
    cube.name = "ModelCube"
    _fill(cube)
    bpy.context.scene.splitforge.boolean_quality = 'FAST'
    before = _snapshot(cube)
    assert len(before[3]) == 5 and sum(len(c[10]) for c in before[3]) == 8, before
    assert before[3][2][3] == 'STROKE' and len(before[3][2][12]) == 5 and before[2] == 4 and before[4] == 'FAST', before
    assert [(c[3], c[13]) for c in before[3][3:]] == [('POLYLINE', 0.0), ('POLYGON', 7.5)], before[3][3:]
    assert [c[1] for c in before[3][0][10]][2:] == ['DOVETAIL', 'SNAP_PIN', 'SNAP_DOVETAIL', 'CUSTOM', 'DOWEL']
    assert before[3][0][10][5][16] == "ModelKnob" and before[5] == ('SNAP_TENON', 7.5, 33.0, "ModelKnob"), before

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
