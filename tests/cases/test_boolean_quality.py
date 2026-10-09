# SPDX-License-Identifier: GPL-3.0-or-later
"""Boolean quality setting (Scene ``splitforge.boolean_quality``: Auto / Accurate / Fast).

Filled Suzanne (eye shells intersect the head) with a stroke through the eyes and a
pin: Accurate cuts with EXACT_SELF (the eyes are united with the head: parts lose the
overlap volume), Fast with MANIFOLD (shells stay overlapping: parts keep it), Auto
behaves like Accurate below LARGE_FACES and like Fast above (threshold lowered here).
Build's info line names the solvers ("Booleans (Fast): 4x MANIFOLD"). Every result is
still validated (manifold parts).
"""

import math

import bpy

import lib


def run(ctx):
    build = ctx.module("cuts.build")
    boolean = ctx.module("core.boolean")
    lib.set_scene_mm()
    settings = bpy.context.scene.splitforge
    assert settings.boolean_quality == 'AUTO'
    monkey = lib.make_monkey_manifold(40.0)
    monkey.name = "QMonkey"
    v_source = lib.volume(monkey)
    lib.select_only([monkey])
    pts = [(-30.0 + 60.0 * i / 19, 0.0, 6.0 + 1.5 * math.sin(i / 3.0)) for i in range(20)]
    lib.run_op(bpy.ops.splitforge.stack_add_stroke, points=[{"name": "", "co": p} for p in pts],
               direction=(0.0, 1.0, 0.0))
    cut = monkey.splitforge_stack.cuts[0]
    c = cut.connectors.add()
    c.u, c.v = -8.0, 0.0

    results = {}
    for quality in ('ACCURATE', 'FAST', 'AUTO'):
        settings.boolean_quality = quality
        lib.select_only([monkey])
        monkey.hide_set(False)
        res = build.build(bpy.context, monkey)
        parts = [bpy.data.objects[n] for n in res.parts]
        assert len(parts) == 2 and all(lib.is_manifold(p) for p in parts), quality
        solvers = [entry[1] for entry in res.booleans]
        total = sum(lib.volume(p) for p in parts)
        results[quality] = (solvers, total, [i for i in res.infos if i.startswith("Booleans")])
        ctx.metric(quality.lower(), f"{','.join(solvers)} {total:.0f}/{v_source:.0f}")
    acc, fast, auto = results['ACCURATE'], results['FAST'], results['AUTO']
    assert acc[0][:2] == ['EXACT_SELF', 'EXACT_SELF'], acc
    # A fallback (here the pin booleans on the united parts) is named in the info line
    if any(s != 'EXACT_SELF' for s in acc[0]):
        assert "fallbacks:" in acc[2][0], acc[2]
    assert fast[0][:2] == ['MANIFOLD', 'MANIFOLD'], fast
    assert auto[0][:2] == acc[0][:2], ("Auto below the threshold = Accurate", auto, acc)
    assert acc[2] and acc[2][0].startswith("Booleans (Accurate):") and "EXACT_SELF" in acc[2][0], acc[2]
    assert fast[2] and fast[2][0].startswith("Booleans (Fast):") and "MANIFOLD" in fast[2][0], fast[2]
    # Accurate unites the overlapping eyes (less volume), Fast keeps them overlapping
    assert acc[1] < fast[1] - 0.005 * v_source, (acc[1], fast[1])

    # Auto above the threshold = Fast
    threshold = boolean.LARGE_FACES
    boolean.LARGE_FACES = 100
    try:
        settings.boolean_quality = 'AUTO'
        lib.select_only([monkey])
        monkey.hide_set(False)
        res = build.build(bpy.context, monkey)
    finally:
        boolean.LARGE_FACES = threshold
    assert [entry[1] for entry in res.booleans][:2] == ['MANIFOLD', 'MANIFOLD'], res.booleans
    assert any(i.startswith("Booleans (Auto):") for i in res.infos), res.infos

    # The panel shows the setting (Settings sub-panel)
    assert "boolean_quality" in type(settings).bl_rna.properties
    desc = type(settings).bl_rna.properties["boolean_quality"].enum_items["FAST"].description
    assert "overlapping" in desc, desc
