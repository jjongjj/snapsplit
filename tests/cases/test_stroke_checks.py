# SPDX-License-Identifier: GPL-3.0-or-later
"""Curved-cut checks from the Phase 2 verification (D9, D10, D11) and the gap problem in the panel.

- D9: with no intersecting shells the pair check is tight (0.1 %): a side result that
  lost 3 % (still manifold and smaller, so the single-boolean check passes) is
  rejected and both sides are redone with the next solver. A real cut on a
  non-intersecting organic mesh (Suzanne head only, gap 0.4) passes the tight check.
- D10: a curved cut that only succeeds through the voxel fallback is reported as a
  Build warning.
- D11: amplitude-14 S cut on a 40 mm cube with gap 0.5: every connector Distribute
  places builds without the "bends into" warning (same exact side test in both, and
  Distribute keeps a safety margin on the own-seam check, whose measure is continuous); the ribbon side test
  agrees with the exact 2D test on all connector samples.
- Raising the gap of a stroke cut until it cannot be built sets ``cut.problem`` (shown
  in the panel); lowering it clears it.
"""

import math

import bmesh
import bpy
from mathutils import Matrix

import lib

D = (0.0, 1.0, 0.0)


def add_stroke(points):
    lib.run_op(bpy.ops.splitforge.stack_add_stroke, points=[{"name": "", "co": p} for p in points], direction=D)


def s_points(amp, n=40):
    return [(-26.0 + 52.0 * i / (n - 1), 0.0, amp * math.sin(2 * math.pi * i / (n - 1))) for i in range(n)]


def head_only_monkey():
    """Filled Suzanne without the eye shells (no intersecting shells)."""
    monkey = lib.make_monkey_manifold(40.0)
    bm = lib.bm_of(monkey, world=False)
    shells = sorted(ctx_meshlib.shells(bm), key=len)
    bmesh.ops.delete(bm, geom=[v for s in shells[:-1] for v in s], context='VERTS')
    bm.to_mesh(monkey.data)
    bm.free()
    return monkey


def run(ctx):
    global ctx_meshlib
    ctx_meshlib = ctx.module("core.meshlib")
    build = ctx.module("cuts.build")
    boolean = ctx.module("core.boolean")
    auto = ctx.module("connectors.auto")
    fit = ctx.module("connectors.fit")
    lib.set_scene_mm()
    scene = bpy.context.scene

    # --- D9: tight pair check without intersecting shells ---------------------------------
    cube = lib.make_cube(40.0)
    cube.name = "Tight"
    lib.select_only([cube])
    add_stroke(s_points(8.0))
    cube.splitforge_stack.cuts[0].gap_mm = 0.5
    original = boolean._evaluate
    factor = 0.97 ** (1.0 / 3.0)

    def lossy(target, operand, operation, attempt):
        mesh = original(target, operand, operation, attempt)
        if attempt == 'EXACT' and target.name.startswith("_SplitForge_Target") and not lossy.done:
            lossy.done = True
            mesh.transform(Matrix.Scale(factor, 4))    # 3 % less volume, still manifold
        return mesh
    lossy.done = False
    boolean._evaluate = lossy
    try:
        res = build.build(bpy.context, cube)
    finally:
        boolean._evaluate = original
    side = [(label, solver) for label, solver, _a in res.booleans if label.startswith("Stroke")]
    ctx.metric("d9_retry", side)
    assert lossy.done and len(side) == 4 and side[2][1] != 'EXACT', side
    total = sum(lib.volume(bpy.data.objects[n]) for n in res.parts)
    assert abs(total - (64000.0 - 0.5 * 40.0 * build.stroke.polyline_length(
        [p for p in build.cut_spec(cube, cube.splitforge_stack.cuts[0], scene).cutter.curve if abs(p[0]) <= 20.0])))\
        < 0.002 * 64000.0, total

    # A correct cut on an organic mesh without intersecting shells passes the tight check
    head = head_only_monkey()
    head.name = "Head"
    lib.select_only([head])
    add_stroke([(x, 0.0, z * 0.4) for x, _y, z in s_points(8.0)])
    head.splitforge_stack.cuts[0].gap_mm = 0.4
    res = build.build(bpy.context, head)
    assert len(res.parts) == 2 and len(res.booleans) == 2 and all(len(e[2]) == 1 for e in res.booleans), res.booleans
    ctx.metric("head", ",".join(entry[1] for entry in res.booleans))

    # --- D10: voxel-only success is reported -------------------------------------------------
    vox = lib.make_cube(40.0)
    vox.name = "Vox"
    lib.select_only([vox])
    add_stroke(s_points(6.0))

    def voxel_only(target, operand, operation, attempt):
        mesh = original(target, operand, operation, attempt)
        if attempt != 'VOXEL' and target.name.startswith("_SplitForge_Target"):
            empty = bmesh.new()
            empty.to_mesh(mesh)
            empty.free()
        return mesh
    divisions = boolean.VOXEL_DIVISIONS
    boolean.VOXEL_DIVISIONS = 60
    boolean._evaluate = voxel_only
    try:
        res = build.build(bpy.context, vox)
    finally:
        boolean._evaluate = original
        boolean.VOXEL_DIVISIONS = divisions
    assert [entry[1] for entry in res.booleans] == ['VOXEL', 'VOXEL'], res.booleans
    assert sum("voxel remesh" in w for w in res.warnings) == 2, res.warnings
    assert any("fallbacks:" in i for i in res.infos), res.infos

    # --- D11: Distribute and Build agree on the own-seam check ------------------------------
    disagree, checked = 0, 0
    for count in (2, 3, 4, 6):
        s14 = lib.make_cube(40.0)
        s14.name = f"S14_{count}"
        lib.select_only([s14])
        add_stroke(s_points(14.0))
        cut = s14.splitforge_stack.cuts[0]
        cut.gap_mm, cut.connector_count, cut.margin_pct = 0.5, count, 15.0
        auto.add_auto(bpy.context, s14, cut, 'CYL_PIN', 5.0, 5.0, 10.0)
        res = build.build(bpy.context, s14)
        assert not [w for w in res.warnings if "bends into" in w], (count, res.warnings)
        spec = build.cut_spec(s14, cut, scene)
        barrier = spec.barrier()
        for c in cut.connectors:
            cs = build.make_spec(s14, cut, scene, "", c.u, c.v, 0.0, 'CYL_PIN', 5, 5, 10, 0.2, c.pin_side, spec)
            for side in (True, False):
                m = fit.own_margin(cs, barrier, side, 1.0)
                assert m >= fit.OWN_SAFETY * auto.MIN_WALL_MM - 1e-4, (count, c.u, c.v, side, m)
                for p in fit.spec_samples(cs, side, 1.0):
                    checked += 1
                    disagree += barrier.positive(p) != spec.cutter.is_positive(p)
    ctx.metric("d11_side_samples", f"{disagree}/{checked}")
    # The rule itself: Distribute (wall 0.4) wants 0.1 mm own-seam clearance, Build (tolerance < 0) only >= 0
    assert not fit.FitResult(own_margin=0.05).ok(0.4) and fit.FitResult(own_margin=0.05).ok(-1e-3)
    assert fit.FitResult(own_margin=0.05).reason(0.4) == "own seam"
    assert checked > 1000 and disagree == 0

    # --- gap problem shown in the panel -----------------------------------------------------
    ui = lib.make_cube(40.0)
    ui.name = "GapUI"
    lib.select_only([ui])
    add_stroke([(-26.0 + 52.0 * i / 39, 0.0, 6.0 * math.sin(4 * math.pi * i / 39)) for i in range(40)])
    cut = ui.splitforge_stack.cuts[0]
    assert cut.problem == "", cut.problem
    cut.gap_mm = 0.5
    assert cut.problem == "", cut.problem
    cut.gap_mm = 12.0
    ctx.metric("gap_problem", cut.problem)
    assert "gap" in cut.problem, cut.problem
    labels = []

    class Layout:
        alert = False
        operator_context = 'INVOKE_DEFAULT'

        def __getattr__(self, name):
            return lambda *a, **k: Layout()

        def label(self, text="", icon='NONE', **k):
            labels.append((text, icon))

        def operator(self, *a, **k):
            return type("P", (), {})()

    bpy.types.SPLITFORGE_PT_main.draw(type("S", (), {"layout": Layout()})(), bpy.context)
    assert ("Cannot build this cut:", 'ERROR') in labels, labels
    with_icon = []
    bpy.types.SPLITFORGE_UL_cuts.draw_item(None, bpy.context, type("L", (), {
        "row": lambda self, **k: self, "prop": lambda self, *a, **k: None,
        "label": lambda self, text="", icon='NONE': with_icon.append(icon)})(), None, cut, 0, None, "", 0)
    assert 'ERROR' in with_icon, with_icon
    cut.gap_mm = 0.5
    assert cut.problem == "", cut.problem
    try:
        bpy.ops.splitforge.build()
    except RuntimeError as ex:
        raise AssertionError(f"build failed after lowering the gap: {ex}")
