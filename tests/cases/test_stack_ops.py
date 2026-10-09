# SPDX-License-Identifier: GPL-3.0-or-later
"""P1-4: stack operators add/move/remove/duplicate/clear/cut_adjust_plane, each undoable.

Background mode does not push undo steps for operators called from Python, so each
call is followed by ``ed.undo_push`` (what the window manager does for UNDO operators
in the GUI; the real Ctrl+Z path is covered by tests/gui scenario p1_adjust_plane).
"""

import bpy

import lib


def _names():
    return [c.name for c in bpy.data.objects["StackCube"].splitforge_stack.cuts]


def _step(op, message, **kwargs):
    lib.run_op(op, **kwargs)
    bpy.ops.ed.undo_push(message=message)
    return _names()


def _undo_redo(expected_before, expected_after):
    bpy.ops.ed.undo()
    assert _names() == expected_before, (_names(), expected_before)
    bpy.ops.ed.redo()
    assert _names() == expected_after, (_names(), expected_after)


def run(ctx):
    lib.set_scene_mm()
    cube = lib.make_cube(40.0)
    cube.name = "StackCube"
    lib.select_only([cube])
    ops = bpy.ops.splitforge
    for name in ("stack_add_plane", "stack_remove", "stack_move", "stack_duplicate", "stack_clear",
                 "cut_adjust_plane"):
        cls = getattr(bpy.types, "SPLITFORGE_OT_" + name)
        assert {'REGISTER', 'UNDO'} <= set(cls.bl_options), (name, cls.bl_options)
    bpy.ops.ed.undo_push(message="base")

    history = [[]]
    for axis, offset in (('Z', 0.0), ('X', 5.0), ('Y', -5.0)):
        history.append(_step(ops.stack_add_plane, f"add {axis}", axis=axis, offset_mm=offset))
        _undo_redo(history[-2], history[-1])
    assert history[-1] == ["Cut Z", "Cut X", "Cut Y"], history[-1]
    stack = bpy.data.objects["StackCube"].splitforge_stack
    # World-axis planes through the bbox center + offset (object local == world here)
    lib.assert_close(stack.cuts[1].origin[0], 5.0, abs_=1e-5)
    assert tuple(round(x, 6) for x in stack.cuts[1].normal) == (1.0, 0.0, 0.0)
    assert len({c.uid for c in stack.cuts}) == 3

    moved = _step(ops.stack_move, "move", index=1, direction='UP')
    assert moved == ["Cut X", "Cut Z", "Cut Y"], moved
    assert bpy.data.objects["StackCube"].splitforge_stack.active_index == 0
    _undo_redo(history[-1], moved)

    dup = _step(ops.stack_duplicate, "duplicate", index=0)
    assert dup == ["Cut X", "Cut X copy", "Cut Z", "Cut Y"], dup
    _undo_redo(moved, dup)

    removed = _step(ops.stack_remove, "remove", index=1)
    assert removed == ["Cut X", "Cut Z", "Cut Y"], removed
    removed = _step(ops.stack_remove, "remove", index=2)
    assert len(removed) == 2 and removed == ["Cut X", "Cut Z"], removed
    _undo_redo(["Cut X", "Cut Z", "Cut Y"], removed)

    # cut_adjust_plane, execute path (no viewport): explicit local origin/normal
    adjusted_origin = (0.0, 0.0, 7.5)
    lib.run_op(ops.cut_adjust_plane, index=1, origin=adjusted_origin, normal=(0.0, 0.0, 2.0))
    bpy.ops.ed.undo_push(message="adjust")
    cut = bpy.data.objects["StackCube"].splitforge_stack.cuts[1]
    assert tuple(cut.origin) == adjusted_origin and tuple(round(x, 6) for x in cut.normal) == (0, 0, 1)
    bpy.ops.ed.undo()
    cut = bpy.data.objects["StackCube"].splitforge_stack.cuts[1]
    assert tuple(cut.origin) == (0.0, 0.0, 0.0), tuple(cut.origin)
    bpy.ops.ed.redo()

    cleared = _step(ops.stack_clear, "clear")
    assert cleared == [], cleared
    _undo_redo(removed, cleared)

    # Invalid input: reported as an error (RuntimeError from Python), stack unchanged
    assert ops.stack_remove.poll() is False
    lib.run_op(ops.stack_add_plane, axis='Z')
    for call, message in ((lambda: ops.stack_remove(index=5), "No cut at index 5"),
                          (lambda: ops.stack_add_plane(use_plane=True, normal=(0.0, 0.0, 0.0)),
                           "Normal must not be zero")):
        try:
            call()
        except RuntimeError as ex:
            assert message in str(ex), ex
        else:
            raise AssertionError(f"expected error: {message}")
    assert _names() == ["Cut Z"], _names()
