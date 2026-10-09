# SPDX-License-Identifier: GPL-3.0-or-later
"""P3-7: the SplitForge UI is translatable (German, Korean) and the translation mechanism works.

- Every UI string of the registered SplitForge types -- operator labels (Operator context),
  property names, enum item names, panel labels -- and every constant label text drawn by
  ui/panel.py has a ko_KR and a de_DE entry.
- No dictionary entry belongs to removed (legacy) UI: each msgid occurs in the add-on source.
- Every locale of the dictionary is known to this Blender (no "locales unknown" message), and
  with the interface language set to Korean, Blender returns the Korean text.
- (D18) Operator buttons with their own text (Cut, Distribute, Adjust in Viewport, ...) have
  Operator-context entries; labels with values ("Part of {name}", "Gap {gap} mm, ...") are
  templates: drawn with the Korean interface the panel shows them in Korean.
- Tooltips: every description (properties, enum items, operators) has a Korean entry (German
  keeps English tooltips by the user's choice); Blender returns them for ko_KR.
"""

import ast
import os

import bpy


def _props(rna, out, seen):
    """Names and enum item names of an RNA struct's own properties, following SplitForge groups."""
    if rna.identifier in seen:
        return
    seen.add(rna.identifier)
    for prop in rna.properties:
        if prop.identifier in ("rna_type", "name", "bl_idname") or prop.is_hidden:
            continue
        if prop.name != prop.identifier:      # unnamed: internal storage, never labelled in the UI
            out.add(("*", prop.name))
        if prop.type == 'ENUM':
            out.update(("*", item.name) for item in prop.enum_items)
        if prop.type in ('POINTER', 'COLLECTION') and prop.fixed_type.identifier.startswith("SPLITFORGE_"):
            _props(prop.fixed_type, out, seen)


def descriptions(ctx):
    """Every tooltip text of the SplitForge UI (property, enum item and operator descriptions)."""
    naming = ctx.module("core.naming")
    out = set()

    def walk(rna, seen):
        if rna.identifier in seen:
            return
        seen.add(rna.identifier)
        for prop in rna.properties:
            if prop.identifier in ("rna_type", "name", "bl_idname") or prop.is_hidden:
                continue
            if prop.description:
                out.add(prop.description)
            if prop.type == 'ENUM':
                out.update(item.description for item in prop.enum_items if item.description)
            if prop.type in ('POINTER', 'COLLECTION') and prop.fixed_type.identifier.startswith("SPLITFORGE_"):
                walk(prop.fixed_type, seen)
    seen = set()
    for name in dir(bpy.ops.splitforge):
        rna = getattr(bpy.ops.splitforge, name).get_rna_type()
        if rna.description:
            out.add(rna.description)
        walk(rna, seen)
    walk(bpy.types.Scene.bl_rna.properties[naming.SCENE_SETTINGS].fixed_type, seen)
    walk(bpy.types.Object.bl_rna.properties[naming.OBJECT_STACK].fixed_type, seen)
    walk(bpy.context.preferences.addons[ctx.addon_module].preferences.bl_rna, seen)
    return out


def operator_button_texts(ctx):
    """Texts given to operator buttons in ui/panel.py (shown in the Operator context)."""
    tree = ast.parse(open(ctx.module("ui.panel").__file__, encoding="utf-8").read())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "operator":
            for kw in node.keywords:
                if kw.arg != "text":
                    continue
                values = [kw.value] if isinstance(kw.value, ast.Constant) else (
                    [kw.value.body, kw.value.orelse] if isinstance(kw.value, ast.IfExp) else [])
                out.update(v.value for v in values if isinstance(v, ast.Constant) and len(v.value) > 1)
    return out


def ui_strings(ctx):
    """{(context, msgid)} the user sees."""
    naming = ctx.module("core.naming")
    out, seen = set(), set()
    for name in dir(bpy.ops.splitforge):
        rna = getattr(bpy.ops.splitforge, name).get_rna_type()
        out.add(("Operator", rna.name))
        _props(rna, out, seen)
    _props(bpy.types.Scene.bl_rna.properties[naming.SCENE_SETTINGS].fixed_type, out, seen)
    _props(bpy.types.Object.bl_rna.properties[naming.OBJECT_STACK].fixed_type, out, seen)
    _props(bpy.context.preferences.addons[ctx.addon_module].preferences.bl_rna, out, seen)
    for name in dir(bpy.types):
        if name.startswith("SPLITFORGE_PT_"):
            out.add(("*", getattr(bpy.types, name).bl_label))
    panel = ctx.module("ui.panel")
    tree = ast.parse(open(panel.__file__, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("label", "operator", "prop"):
            for kw in node.keywords:
                if kw.arg == "text" and isinstance(kw.value, ast.Constant) and len(kw.value.value) > 1:
                    out.add(("*", kw.value.value))
    out.update(("*", s) for s in panel.KIND_SHORT.values())
    out.update({("*", "pin"), ("*", "both sides")})
    # Untranslatable on purpose: single letters / units shown as they are
    return {k for k in out if k[1] and k[1] not in ("W", "H", "L", "X", "Y", "Z", "U (mm)", "V (mm)")
            and not k[1].startswith(("A (", "B ("))}


def run(ctx):
    loc = ctx.module("localization")
    strings = ui_strings(ctx)
    assert len(strings) > 80, len(strings)
    for locale in ("ko_KR", "de_DE"):
        table = loc.DICTIONARY[locale]
        missing = sorted(k for k in strings if k not in table and not k[1].isupper() and k[1] != "SplitForge")
        assert not missing, f"{locale}: {len(missing)} untranslated UI strings, e.g. {missing[:10]}"
    ctx.metric("ui_strings", len(strings))

    # Operator buttons with their own text: Operator context in both languages
    buttons = operator_button_texts(ctx)
    assert {"Cut", "Distribute", "Adjust in Viewport", "Draw Cut", "Redraw in Viewport"} <= buttons, buttons
    for locale in ("ko_KR", "de_DE"):
        missing = sorted(t for t in buttons if ("Operator", t) not in loc.DICTIONARY[locale])
        assert not missing, (locale, missing)

    # Tooltips: Korean for all
    tips = descriptions(ctx)
    assert len(tips) > 80, len(tips)
    missing = sorted(t for t in tips if ("*", t) not in loc.DICTIONARY["ko_KR"] and not t.isupper())
    assert not missing, f"ko_KR: {len(missing)} untranslated tooltips, e.g. {missing[:5]}"
    ctx.metric("tooltips", len(tips))

    # No leftovers of the legacy UI: every msgid occurs in the add-on source (or is a generated tooltip)
    root = os.path.dirname(loc.__file__)
    literals = set()
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".py") and f != "localization.py":
                tree = ast.parse(open(os.path.join(dirpath, f), encoding="utf-8").read())
                literals.update(n.value for n in ast.walk(tree)
                                if isinstance(n, ast.Constant) and isinstance(n.value, str))
    stale = sorted({k[1] for table in loc.DICTIONARY.values() for k in table} - literals - tips)
    assert not stale, f"dictionary entries without a UI string: {stale[:10]}"

    # Every locale is known (otherwise register() prints "locales unknown ... skipped")
    unknown = sorted(set(loc.DICTIONARY) - set(bpy.app.translations.locales))
    assert not unknown, unknown

    # Blender actually translates with the registered dictionary; the panel draws value labels in Korean
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    import lib
    import test_ui_draw
    lib.set_scene_mm()
    cube = lib.make_cube(40.0)
    cube.name = "KoCube"
    lib.select_only([cube])
    bpy.ops.splitforge.stack_add_plane(axis='Z')
    bpy.ops.splitforge.connector_add_auto()
    bpy.ops.splitforge.stack_add_stroke(points=[{"name": "", "co": (x, 0.0, 6.0)} for x in (-30.0, 30.0)],
                                        direction=(0.0, 1.0, 0.0))
    view = bpy.context.preferences.view
    old = (view.language, view.use_translate_interface, view.use_translate_tooltips)
    try:
        view.language = 'ko_KR'
        view.use_translate_interface = True
        view.use_translate_tooltips = True
        got = bpy.app.translations.pgettext_iface("Build & Export")
        op = bpy.app.translations.pgettext_iface("Place Connectors", "Operator")
        button = bpy.app.translations.pgettext_iface("Distribute", "Operator")
        tip = bpy.app.translations.pgettext_tip("Where Build puts the separate dowel parts")
        drawn = [e[1] for e in test_ui_draw._draw_all("ko") if e[0] == "label"]
        bpy.ops.splitforge.build()
        drawn += [e[1] for e in test_ui_draw._draw_all("ko built") if e[0] == "label"]
    finally:
        view.language, view.use_translate_interface, view.use_translate_tooltips = old
    assert got == "빌드 및 내보내기", got
    assert op == "커넥터 배치", op
    assert button == "자동 배치", button
    assert tip == "빌드가 별도 도웰 파트를 놓을 위치", tip
    for text in ("틈 0 mm, 커넥터 0개", "Stroke 2에 배치", "1 단위 = 1 mm", "KoCube의 파트",
                 "스트로크: 점 2개", "SplitForge_Build_KoCube에 파트 3개"):
        assert text in drawn, (text, drawn)
    ctx.metric("ko_labels", [t for t in drawn if "KoCube" in t or "mm" in t][:4])
