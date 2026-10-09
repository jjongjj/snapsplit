# SPDX-License-Identifier: GPL-3.0-or-later
"""P2-1: core/boolean.py - solver fallback chain, result validation, source never damaged.

Cube - sphere DIFFERENCE is exact and manifold. A non-manifold (open) cutter is
either handled by a solver that copes or refused with a message, the target
unchanged. Solver failures are simulated (``_evaluate`` returning an empty or a
volume-losing mesh) to walk the chain EXACT -> EXACT_SELF -> MANIFOLD -> float ->
VOXEL: the first plausible result wins, the log says ``fallback=``, and when all fail
the target keeps its mesh. A filled Suzanne (eye shells intersect the head) shows
the documented cause of the old "EXACT lost volume" fallback: plain EXACT returns an
empty mesh, EXACT with self-intersection succeeds. No temporary data is left behind.
"""

import io

import bmesh
import bpy

import lib


def sphere_bm(radius, center=(0.0, 0.0, 0.0), open_mesh=False):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=radius)
    bmesh.ops.translate(bm, verts=bm.verts, vec=center)
    if open_mesh:
        bmesh.ops.delete(bm, geom=[bm.faces[:][0]], context='FACES_ONLY')
    return bm


def box_bm(size, center=(0.0, 0.0, 0.0)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bmesh.ops.translate(bm, verts=bm.verts, vec=center)
    return bm


def capture_log(log):
    """Swap the add-on log stream for a StringIO; returns (buffer, restore)."""
    handler = log._logger.handlers[0]
    buf = io.StringIO()
    old = handler.setStream(buf)
    return buf, lambda: handler.setStream(old)


def run(ctx):
    # Voxel attempts: a coarse remesh keeps the test fast (the default is diagonal / 200)
    boolean = ctx.module("core.boolean")
    divisions = boolean.VOXEL_DIVISIONS
    boolean.VOXEL_DIVISIONS = 50
    try:
        _run(ctx)
    finally:
        boolean.VOXEL_DIVISIONS = divisions


def _run(ctx):
    boolean = ctx.module("core.boolean")
    log = ctx.module("core.log")
    lib.set_scene_mm()
    fast = 'FLOAT'
    has_manifold = True
    solvers = [i.identifier for i in bpy.types.BooleanModifier.bl_rna.properties['solver'].enum_items]
    assert {'EXACT', 'MANIFOLD', 'FLOAT'} <= set(solvers), solvers

    # --- attempt order by quality ------------------------------------------------------
    accurate = ['EXACT', 'EXACT_SELF'] + (['MANIFOLD'] if has_manifold else []) + [fast, 'VOXEL']
    assert boolean.attempt_order('ACCURATE') == accurate, boolean.attempt_order('ACCURATE')
    assert boolean.attempt_order('EXACT') == accurate          # old name
    assert boolean.attempt_order('AUTO', faces=1000) == accurate
    big = boolean.LARGE_FACES + 1
    fast_order = (['MANIFOLD'] if has_manifold else []) + ['EXACT', 'EXACT_SELF', fast, 'VOXEL']
    assert boolean.attempt_order('AUTO', faces=big) == fast_order, boolean.attempt_order('AUTO', faces=big)
    assert boolean.attempt_order('FAST', faces=10) == fast_order
    assert boolean.attempt_order('ACCURATE', self_intersect=True)[0] == 'EXACT_SELF'
    assert boolean.attempt_order('FAST', self_intersect=True) == fast_order[:1] + ['EXACT_SELF', fast, 'VOXEL'] \
        if has_manifold else True
    assert 'VOXEL' not in boolean.attempt_order('AUTO', voxel=False)

    # --- result checks -------------------------------------------------------------------
    chk = boolean.check_result
    assert chk('DIFFERENCE', 100.0, 30.0, 80.0, True, 10) == ""
    assert "empty" in chk('DIFFERENCE', 100.0, 30.0, 0.0, True, 0)
    assert "manifold" in chk('DIFFERENCE', 100.0, 30.0, 80.0, False, 10)
    assert "did not shrink" in chk('DIFFERENCE', 100.0, 30.0, 100.0, True, 10)
    assert "more volume" in chk('DIFFERENCE', 100.0, 30.0, 50.0, True, 10)
    assert "did not grow" in chk('UNION', 100.0, 30.0, 99.0, True, 10)
    assert "more than the operand" in chk('UNION', 100.0, 30.0, 140.0, True, 10)
    assert "larger" in chk('INTERSECT', 100.0, 30.0, 40.0, True, 10)
    assert "expected" in chk('DIFFERENCE', 100.0, 30.0, 80.0, True, 10, expect=(85.0, 95.0))

    # --- cube - sphere ----------------------------------------------------------------------
    cube = lib.make_cube(40.0)
    cube.name = "BoolCube"
    op = sphere_bm(10.0, (20.0, 20.0, 20.0))
    try:
        res = boolean.apply(cube, op, 'DIFFERENCE')
    finally:
        op.free()
    assert res.ok and res.solver == 'EXACT' and not res.fallback, res
    assert lib.is_manifold(cube)
    # An eighth of the sphere is removed (UV sphere volume slightly below 4/3 pi r^3)
    removed = 64000.0 - lib.volume(cube)
    lib.assert_close(removed, 4.0 / 3.0 * 3.14159265 * 1000.0 / 8.0, rel=0.03, msg="removed volume")

    # --- non-manifold cutter: handled by some solver, or refused with the target unchanged
    plain = lib.make_cube(40.0)
    plain.name = "OpenCutter"
    v0, mesh0 = lib.volume(plain), plain.data.name
    op = sphere_bm(10.0, (0.0, 0.0, 20.0), open_mesh=True)
    buf, restore = capture_log(log)
    try:
        res = boolean.apply(plain, op, 'DIFFERENCE')
    finally:
        restore()
        op.free()
    ctx.metric("open_cutter", f"{res.ok}/{res.solver}/" + ",".join(a for a, _r, _s in res.attempts))
    if res.ok:
        assert lib.is_manifold(plain) and lib.volume(plain) < v0
        if res.fallback:
            assert "fallback=" in buf.getvalue(), buf.getvalue()
    else:
        assert res.message and lib.volume(plain) == v0 and plain.data.name == mesh0
        assert all(a in res.message for a, _r, _s in res.attempts), res.message

    # --- simulated solver failures walk the chain ---------------------------------------
    original = boolean._evaluate
    failing = set()

    def flaky(target, operand, operation, attempt):
        mesh = original(target, operand, operation, attempt)
        if attempt in failing:
            bm = bmesh.new()   # an empty result (what EXACT returns on self-intersecting input)
            bm.to_mesh(mesh)
            bm.free()
        return mesh

    def run_with(fail, name):
        failing.clear()
        failing.update(fail)
        obj = lib.make_cube(40.0)
        obj.name = name
        op = box_bm(10.0, (20.0, 0.0, 0.0))
        buf, restore = capture_log(log)
        boolean._evaluate = flaky
        try:
            return obj, boolean.apply(obj, op, 'DIFFERENCE'), buf.getvalue()
        finally:
            boolean._evaluate = original
            restore()
            op.free()

    obj, res, text = run_with({'EXACT'}, "FailExact")
    assert res.ok and res.solver == 'EXACT_SELF' and res.fallback, res
    assert "fallback=EXACT_SELF" in text and "EXACT: empty result" in text, text
    lib.assert_close(lib.volume(obj), 64000.0 - 500.0, rel=1e-6)

    chain = ['EXACT', 'EXACT_SELF'] + (['MANIFOLD'] if has_manifold else [])
    obj, res, text = run_with(set(chain), "FailToFloat")
    assert res.ok and res.solver == fast, res
    assert [a for a, _r, _s in res.attempts] == chain + [fast], res.attempts

    obj, res, text = run_with(set(chain + [fast]), "FailToVoxel")
    assert res.ok and res.solver == 'VOXEL' and "voxel" in res.message, res
    ctx.metric("voxel_s", res.attempts[-1][2])
    assert lib.is_manifold(obj)
    lib.assert_close(lib.volume(obj), 63500.0, rel=0.05, msg="voxel fallback volume")

    obj, res, text = run_with(set(chain + [fast, 'VOXEL']), "FailAll")
    assert not res.ok and len(res.attempts) == len(chain) + 2, res
    assert "failed with every solver" in res.message and "VOXEL: empty result" in res.message, res.message
    assert len(obj.data.vertices) == 8, ("target changed after total failure", len(obj.data.vertices))
    lib.assert_close(lib.volume(obj), 64000.0, rel=1e-9, msg="target volume after total failure")

    # Volume loss is caught too (a result that removed far more than the operand)
    def lossy(target, operand, operation, attempt):
        mesh = original(target, operand, operation, attempt)
        if attempt == 'EXACT':
            bm = box_bm(10.0)
            bm.to_mesh(mesh)
            bm.free()
        return mesh
    obj = lib.make_cube(40.0)
    op = box_bm(10.0, (20.0, 0.0, 0.0))
    boolean._evaluate = lossy
    try:
        res = boolean.apply(obj, op, 'DIFFERENCE')
    finally:
        boolean._evaluate = original
        op.free()
    assert res.ok and res.solver == 'EXACT_SELF' and "more volume" in res.attempts[0][1], res.attempts

    # --- bmesh targets: no temporary data left, input untouched --------------------------
    n_obj, n_mesh = len(bpy.data.objects), len(bpy.data.meshes)
    target = box_bm(40.0)
    op = box_bm(10.0, (20.0, 0.0, 0.0))
    res, out = boolean.apply_bm(target, op, 'DIFFERENCE')
    assert res.ok and out is not None and len(target.verts) == 8
    lib.assert_close(out.calc_volume(), 63500.0, rel=1e-6)
    out.free()
    far = box_bm(1.0, (500.0, 0.0, 0.0))
    res, out = boolean.apply_bm(target, far, 'DIFFERENCE', order=['EXACT', 'EXACT_SELF'])  # nothing removed
    assert not res.ok and out is None and "did not shrink" in res.message
    for bm in (target, op, far):
        bm.free()
    assert (len(bpy.data.objects), len(bpy.data.meshes)) == (n_obj, n_mesh), "temporary data left"
    assert not [o.name for o in bpy.data.objects if o.name.startswith("_SplitForge")]

    # --- filled Suzanne: why plain EXACT fails (intersecting eye shells) -------------------
    monkey = lib.make_monkey_manifold(40.0)
    op = box_bm(100.0, (0.0, 0.0, 52.0))      # removes everything above z = 2
    try:
        res = boolean.apply(monkey, op, 'DIFFERENCE')
    finally:
        op.free()
    assert res.ok and res.solver == 'EXACT_SELF', res.attempts
    assert res.attempts[0][0] == 'EXACT' and res.attempts[0][1] == "empty result", res.attempts
    ctx.metric("suzanne", "; ".join(f"{a}: {r}" for a, r, _s in res.attempts))
