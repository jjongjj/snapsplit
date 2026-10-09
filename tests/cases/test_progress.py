# SPDX-License-Identifier: GPL-3.0-or-later
"""P2-6: Build progress steps and the modal Build.

Progress listeners (core/progress.py) count the steps: two per piece and cut (side A,
side B) plus one per connector boolean. Cube with a Z cut (1 piece), an X cut (2
pieces) and connectors on both: 2 + 4 + connector booleans; the last step equals the
total and the totals never decrease below the steps done. A stroke cut adds 2 steps.

The modal Build (``invoke`` in the UI) is driven here through a stand-in: TIMER events
advance one step each and it finishes with the same parts as ``execute``; Esc in the
middle leaves the previous result untouched (same parts, no new objects, no empty new
collection); ``cancel()`` (file load) does the same; nothing is kept but the step
generator and the timer.
"""

import bpy

import lib


class FakeWM:
    def __init__(self):
        self.timers = []

    def event_timer_add(self, interval, window=None):
        self.timers.append(object())
        return self.timers[-1]

    def event_timer_remove(self, timer):
        self.timers.remove(timer)

    def modal_handler_add(self, op):
        return True


class FakeContext:
    def __init__(self, wm):
        self.window_manager = wm
        self.window = object()

    def __getattr__(self, name):
        return getattr(bpy.context, name)


def listen(progress):
    steps = []

    def fn(done, total, text):
        steps.append((done, total, text))
    progress.listeners.append(fn)
    return steps, lambda: progress.listeners.remove(fn)


def parts_of(name):
    return sorted(o.name for o in bpy.data.objects if o.get("splitforge_source") == name)


def run(ctx):
    build = ctx.module("cuts.build")
    progress = ctx.module("core.progress")
    ops = ctx.module("ops.ops_build")
    lib.set_scene_mm()

    cube = lib.make_cube(40.0)
    cube.name = "Prog"
    lib.select_only([cube])
    for axis in ('Z', 'X'):
        lib.run_op(bpy.ops.splitforge.stack_add_plane, axis=axis)
        lib.run_op(bpy.ops.splitforge.connector_add_auto)
    steps, stop = listen(progress)
    try:
        result = build.build(bpy.context, cube)
    finally:
        stop()
    connector_ops = sum(1 for label, _s, _a in result.booleans if label.startswith("connectors"))
    calls = [s for s in steps if s[2]]          # step() calls carry a text; begin() does not
    expected = 2 * 1 + 2 * 2 + connector_ops
    ctx.metric("steps", f"{len(calls)}={expected} (connector booleans {connector_ops})")
    assert connector_ops >= 4, result.booleans
    assert len(calls) == expected, [s[2] for s in calls]
    assert [d for d, _t, _x in calls] == list(range(1, expected + 1))
    assert calls[-1][1] == expected, calls[-1]
    assert all(d <= t for d, t, _x in calls)
    assert calls[0][2].startswith("Cut Z: side A") and "connectors" in calls[-1][2], (calls[0], calls[-1])

    # A stroke cut on top: 2 more steps per piece it meets (4 pieces)
    lib.select_only([cube])
    cube.hide_set(False)
    lib.run_op(bpy.ops.splitforge.stack_add_stroke, direction=(0.0, 1.0, 0.0),
               points=[{"name": "", "co": (-26.0 + 52.0 * i / 19, 0.0, 9.0 + 3.0 * (i % 2))} for i in range(20)])
    for c in cube.splitforge_stack.cuts:
        c.connectors.clear()
    steps, stop = listen(progress)
    try:
        result = build.build(bpy.context, cube)
    finally:
        stop()
    calls = [s for s in steps if s[2]]
    assert len(calls) == 2 + 4 + 2 * 4 and calls[-1][1] == len(calls), (len(calls), calls[-1])
    assert len(result.parts) == 6, result.parts   # the stroke at z ~ 9..12 only splits the upper pieces

    # --- modal Build: timer steps, Esc, cancel() -----------------------------------------
    cube.splitforge_stack.cuts[2].enabled = False
    lib.select_only([cube])
    cube.hide_set(False)
    reference = build.build(bpy.context, cube)
    names = parts_of("Prog")
    assert len(names) == 4
    meshes = {n: bpy.data.objects[n].data.name for n in names}
    n_objects = len(bpy.data.objects)

    def modal_op():
        wm = FakeWM()
        mctx = FakeContext(wm)
        op, reports = lib.stand_in(ops.SPLITFORGE_OT_build)
        op._gen = build.build_steps(cube)
        op._timer = wm.event_timer_add(0.01)
        bad = [k for k, v in vars(op).items()
               if isinstance(v, bpy.types.bpy_struct) and not isinstance(v, bpy.types.ID)]
        assert not bad, bad
        return op, reports, mctx, wm

    cls = ops.SPLITFORGE_OT_build
    # Esc after a few steps: previous parts untouched, nothing new left behind
    cube.splitforge_stack.cuts[0].gap_mm = 1.0
    op, reports, mctx, wm = modal_op()
    for _ in range(5):
        assert cls.modal(op, mctx, lib.ModalEvent('TIMER')) == {'RUNNING_MODAL'}
    assert cls.modal(op, mctx, lib.ModalEvent('MOUSEMOVE')) == {'RUNNING_MODAL'}   # swallowed
    assert cls.modal(op, mctx, lib.ModalEvent('ESC')) == {'CANCELLED'}
    assert not wm.timers and op._gen is None
    assert parts_of("Prog") == names and len(bpy.data.objects) == n_objects
    assert {n: bpy.data.objects[n].data.name for n in names} == meshes, "previous parts changed"
    assert any("cancelled" in m for _l, m in reports), reports
    # Run to the end with timer events: same result as execute, one FINISHED
    op, reports, mctx, wm = modal_op()
    results = [cls.modal(op, mctx, lib.ModalEvent('TIMER')) for _ in range(200)]
    assert results.count({'FINISHED'}) == 1, results
    done_at = results.index({'FINISHED'})
    assert all(r == {'RUNNING_MODAL'} for r in results[:done_at]) and done_at >= 6, done_at
    assert parts_of("Prog") == names and not wm.timers
    assert any("Built 4 part(s)" in m for _l, m in reports), reports
    # cancel() (file load / window close) mid-build cleans up the same way
    op, reports, mctx, wm = modal_op()
    for _ in range(3):
        cls.modal(op, mctx, lib.ModalEvent('TIMER'))
    cls.cancel(op, mctx)
    assert not wm.timers and parts_of("Prog") == names and len(bpy.data.objects) == n_objects

    # A first build cancelled after its collection was created leaves no empty collection
    fresh = lib.make_cube(20.0)
    fresh.name = "Fresh"
    lib.select_only([fresh])
    lib.run_op(bpy.ops.splitforge.stack_add_plane, axis='Z')
    lib.run_op(bpy.ops.splitforge.connector_add_auto)
    gen = build.build_steps(fresh)
    texts = []
    try:
        while True:
            next(gen)
            texts.append(bpy.data.collections.get("SplitForge_Build_Fresh") is not None)
            if texts[-1]:
                break
    finally:
        gen.close()
    assert texts and texts[-1], "the build collection should exist during the connector steps"
    assert bpy.data.collections.get("SplitForge_Build_Fresh") is None, "empty collection left after cancel"
    assert not parts_of("Fresh") and fresh.splitforge_stack.last_build_collection is None
