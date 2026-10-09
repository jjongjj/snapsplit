# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SnapSplit.
"""Helpers for test cases (run inside Blender)."""

import bmesh
import bpy


def set_scene_mm(scene=None):
    """Standard 3D-print setup: Metric, Millimeters, Unit Scale 0.001 (1 BU = 1 mm)."""
    us = (scene or bpy.context.scene).unit_settings
    us.system = 'METRIC'
    us.length_unit = 'MILLIMETERS'
    us.scale_length = 0.001


def select_only(objs, active=None):
    """Select exactly ``objs`` and make ``active`` (default: first) active."""
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or (objs[0] if objs else None)


def make_cube(size_mm=40.0):
    bpy.ops.mesh.primitive_cube_add(size=size_mm)
    return bpy.context.active_object


def make_monkey_manifold(size_mm=40.0):
    """Suzanne with filled eye holes and consistent outward normals."""
    bpy.ops.mesh.primitive_monkey_add(size=size_mm)
    obj = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.fill_holes(sides=0)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    return obj


def make_hollow_box(size_mm=40.0, wall_mm=2.0):
    """Closed box with an inner cavity: outer cube plus inward-facing inner cube, one mesh."""
    outer = make_cube(size_mm)
    inner = make_cube(size_mm - 2.0 * wall_mm)
    bm = bmesh.new()
    bm.from_mesh(inner.data)
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.to_mesh(inner.data)
    bm.free()
    select_only([outer, inner], active=outer)
    bpy.ops.object.join()
    return outer


def is_manifold(obj):
    """True if every edge is manifold and there are no wire/loose vertices."""
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        return (len(bm.faces) > 0
                and all(e.is_manifold for e in bm.edges)
                and all(not v.is_wire and v.link_faces for v in bm.verts))
    finally:
        bm.free()


def volume(obj, signed=False):
    """Volume of a closed mesh in object space (unsigned unless signed=True)."""
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        return bm.calc_volume(signed=signed)
    finally:
        bm.free()


def assert_close(actual, expected, rel=0.0, abs_=0.0, msg=""):
    tol = max(abs_, rel * abs(expected))
    assert abs(actual - expected) <= tol, (
        f"{msg} {actual!r} != {expected!r} (tolerance {tol!r})".strip())


def run_op(op, **kwargs):
    """Call an operator and assert it returned {'FINISHED'}."""
    result = op(**kwargs)
    assert result == {'FINISHED'}, f"{op.idname_py()} returned {result}"
    return result


# ---------------------------------------------------------------------------
# Calling modal operators in background mode
# ---------------------------------------------------------------------------

class _WindowManager:
    """Accepts modal_handler_add(); everything else comes from the real one."""

    def modal_handler_add(self, _op):
        return True

    def __getattr__(self, name):
        return getattr(bpy.context.window_manager, name)


class _Context:
    """bpy.context with overrides (no window/area in background mode)."""

    def __init__(self, **overrides):
        self._overrides = overrides

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(bpy.context, name)


class ModalEvent:
    """Minimal stand-in for bpy.types.Event passed to modal()."""

    def __init__(self, type, value='PRESS', mouse_y=0, mouse_prev_y=0):
        self.type = type
        self.value = value
        self.mouse_y = mouse_y
        self.mouse_prev_y = mouse_prev_y
        self.mouse_x = self.mouse_prev_x = 0
        self.mouse_region_x = self.mouse_region_y = 0
        self.shift = self.ctrl = self.alt = self.oskey = self.is_repeat = False


def modal_context():
    """Context for calling invoke()/modal() in background mode (no window/area)."""
    return _Context(window_manager=_WindowManager(), area=None, region=None,
                    region_data=None, space_data=None)


def stand_in(op_cls):
    """Instance of a plain class with the operator's methods and Python properties.

    Modal operators cannot be invoked in background mode; tests call
    ``op_cls.invoke(op, ctx, event)`` / ``op_cls.modal(...)`` on this instead.
    Returns ``(op, reports)``.
    """
    reports = []
    ns = {k: v for k, v in vars(op_cls).items()
          if callable(v) or isinstance(v, property)}
    ns["report"] = lambda self, level, msg: reports.append((set(level), msg))
    op = type("StandIn_" + op_cls.__name__, (), ns)()
    return op, reports
