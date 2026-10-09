# SPDX-License-Identifier: GPL-3.0-or-later
"""P3-7: the SplitForge UI is translatable (German, Korean) and the translation mechanism works.

- Every UI string of the registered SplitForge types -- operator labels (Operator context),
  property names, enum item names, panel labels -- and every constant label text drawn by
  ui/panel.py has a ko_KR and a de_DE entry.
- No dictionary entry belongs to removed (legacy) UI: each msgid occurs in the add-on source.
- Every locale of the dictionary is known to this Blender (no "locales unknown" message), and
  with the interface language set to Korean, Blender returns the Korean text.
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

    # No leftovers of the legacy UI: every msgid occurs in the add-on source
    root = os.path.dirname(loc.__file__)
    literals = set()
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".py") and f != "localization.py":
                tree = ast.parse(open(os.path.join(dirpath, f), encoding="utf-8").read())
                literals.update(n.value for n in ast.walk(tree)
                                if isinstance(n, ast.Constant) and isinstance(n.value, str))
    stale = sorted({k[1] for table in loc.DICTIONARY.values() for k in table} - literals)
    assert not stale, f"dictionary entries without a UI string: {stale[:10]}"

    # Every locale is known (otherwise register() prints "locales unknown ... skipped")
    unknown = sorted(set(loc.DICTIONARY) - set(bpy.app.translations.locales))
    assert not unknown, unknown

    # Blender actually translates with the registered dictionary
    view = bpy.context.preferences.view
    old = (view.language, view.use_translate_interface)
    try:
        view.language = 'ko_KR'
        view.use_translate_interface = True
        got = bpy.app.translations.pgettext_iface("Build & Export")
        op = bpy.app.translations.pgettext_iface("Place Connectors", "Operator")
    finally:
        view.language, view.use_translate_interface = old
    assert got == "빌드 및 내보내기", got
    assert op == "커넥터 배치", op
