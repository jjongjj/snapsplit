# SPDX-License-Identifier: GPL-3.0-or-later
"""P1-7: splitforge.easy_cut adds one cut (with default connectors) and builds at once."""

import bpy

import lib


def run(ctx):
    lib.set_scene_mm()
    cube = lib.make_cube(40.0)
    cube.name = "EasyCube"
    lib.select_only([cube])
    lib.run_op(bpy.ops.splitforge.easy_cut, axis='Z', offset_mm=4.0)

    src = bpy.data.objects["EasyCube"]
    stack = src.splitforge_stack
    assert len(stack.cuts) == 1, len(stack.cuts)
    settings = bpy.context.scene.splitforge
    assert len(stack.cuts[0].connectors) == settings.easy_connector_count == 2
    parts = sorted((o for o in bpy.data.objects if o.get("splitforge_source") == "EasyCube"), key=lambda o: o.name)
    assert len(parts) == 2, [o.name for o in parts]
    for p in parts:
        assert lib.is_manifold(p), p.name
    # Plane at z = 4: A is 16 mm tall plus 2 pins, B is 24 mm minus 2 sockets
    a, b = (lib.volume(p) for p in parts)
    assert a > 40 * 40 * 16 and b < 40 * 40 * 24, (a, b)

    # Without connectors: exact halves
    cube2 = lib.make_cube(40.0)
    cube2.name = "EasyPlain"
    lib.select_only([cube2])
    lib.run_op(bpy.ops.splitforge.easy_cut, axis='X', offset_mm=0.0, connector_count=0)
    plain = [o for o in bpy.data.objects if o.get("splitforge_source") == "EasyPlain"]
    assert len(plain) == 2 and len(bpy.data.objects["EasyPlain"].splitforge_stack.cuts) == 1
    for p in plain:
        lib.assert_close(lib.volume(p), 32000.0, rel=1e-6)

    # A cut that misses the object fails cleanly and leaves no stack entry
    cube3 = lib.make_cube(10.0)
    cube3.name = "EasyMiss"
    lib.select_only([cube3])
    try:
        bpy.ops.splitforge.easy_cut(axis='Z', offset_mm=50.0, connector_count=0)
    except RuntimeError as ex:
        assert "do not intersect" in str(ex), ex
    else:
        raise AssertionError("easy_cut outside the object must fail")
    stack = bpy.data.objects["EasyMiss"].splitforge_stack
    assert len(stack.cuts) == 0 and stack.next_uid == 1, (len(stack.cuts), stack.next_uid)

    # invoke() (panel button) uses the Easy settings unless the caller set the values.
    # Background mode never calls invoke(), so it runs on a stand-in (tests/lib).
    s = bpy.context.scene.splitforge
    s.easy_axis, s.easy_offset_mm, s.easy_connector_count = 'Y', 2.0, 0
    cls = bpy.types.SPLITFORGE_OT_easy_cut
    rna = bpy.ops.splitforge.easy_cut.get_rna_type()
    assert rna.properties["axis"].is_skip_save and rna.properties["offset_mm"].is_skip_save
    for name, explicit, normal in (("EasyInvoke", {}, (0, 1, 0)), ("EasyExplicit", {"axis": 'X'}, (1, 0, 0))):
        cube = lib.make_cube(20.0)
        cube.name = name
        lib.select_only([cube])
        op, _reports = lib.stand_in(cls)
        op.axis, op.offset_mm, op.connector_count = explicit.get("axis", 'Z'), 0.0, -1
        op.properties = type("Props", (), {"is_property_set": lambda self, key: key in explicit})()
        assert cls.invoke(op, bpy.context, None) == {'FINISHED'}
        cut = bpy.data.objects[name].splitforge_stack.cuts[0]
        assert tuple(round(x, 6) for x in cut.normal) == normal, (name, tuple(cut.normal))
