# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# ops/ops_fix.py
"""One-click fixes for the print checks (core/validate.py). Each is one undo step and reports
exactly what it changed; none runs on its own.

- ``fix_transforms``: apply rotation and scale of the source object to its mesh. The cut
  stack is stored in object space, so every cut (plane origin/normal/tangent, stroke /
  polyline / polygon points and direction) is moved with the mesh: the cuts stay where they
  were in the world and connector positions (mm on the seam) are unchanged. Children keep
  their world transform. Refused for a mesh shared with other objects.
- ``fix_units``: Metric, Millimeters, Unit Scale 0.001 (1 unit = 1 mm). ``Keep Units`` (the
  usual case after importing an STL in mm) only relabels: a 40 unit object shows as 40 mm.
  ``Keep Size`` also scales every object in the scene so its physical size stays (a 0.04 m
  object stays 40 mm); its scale is then not applied (Fix Transforms).
- ``fix_normals``: recalculate face normals to point outward.
- ``fix_merge``: merge vertices closer than a distance (default 0.001 mm).
- ``fix_holes``: fill holes (open boundary loops) and delete loose vertices/edges. Edges with
  more than two faces are left alone and reported (fix them in Edit Mode).

Mesh fixes act on the source's own mesh (not on modifiers' results); built parts are not
changed until the next Build.
"""

import bmesh
import bpy
from bpy.props import EnumProperty, FloatProperty
from bpy.types import Operator
from mathutils import Matrix, Vector

from ..core import naming, units, validate
from ..model import stack as stack_api


def _owner(context):
    return stack_api.context_owner(context)


class _FixOp:
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and _owner(context) is not None

    def _single_user(self, obj):
        if obj.data.users > 1:
            self.report({'ERROR'}, f"The mesh of {obj.name} is shared by {obj.data.users} objects: make it "
                                   "single user first (Object > Relations > Make Single User)")
            return False
        return True

    def _rebuild_hint(self, obj):
        from ..ops.ops_export import built_parts
        return " (Rebuild to update the parts)" if built_parts(obj) else ""

    def _recheck(self, context, obj):
        """Run Check Mesh again after a mesh fix, so the panel shows the new state (when it was shown)."""
        validate.validate(obj, context.scene)


def transform_cut(cut, m):
    """Move a stack cut's object-space data by the 4x4 matrix ``m`` (new local = m @ old local)."""
    m3 = m.to_3x3()
    normal_m = m3.inverted_safe().transposed()
    cut.origin = m @ Vector(cut.origin)
    n = (normal_m @ Vector(cut.normal)).normalized()
    t = m3 @ Vector(cut.tangent)
    t = (t - n * t.dot(n)).normalized() if (t - n * t.dot(n)).length > 1e-12 else t.normalized()
    cut.normal, cut.tangent = n, t
    cut.direction = (m3 @ Vector(cut.direction)).normalized()
    for p in cut.points:
        p.co = m @ Vector(p.co)


def apply_rotation_scale(obj):
    """Apply rotation and scale of ``obj`` (location kept) to its mesh and cut stack. Returns the matrix
    applied to the object-space data."""
    loc, rot, sca = obj.matrix_basis.decompose()
    m = (rot.to_matrix() @ Matrix.Diagonal(sca)).to_4x4()
    obj.data.transform(m, shape_keys=True)
    if m.determinant() < 0.0:
        obj.data.flip_normals()
    obj.matrix_basis = Matrix.Translation(loc)
    for child in obj.children:
        child.matrix_parent_inverse = m @ child.matrix_parent_inverse
    stack = stack_api.get_stack(obj)
    for cut in (stack.cuts if stack is not None else ()):
        transform_cut(cut, m)
    obj.data.update()
    return m


class SPLITFORGE_OT_fix_transforms(_FixOp, Operator):
    """Apply the object's rotation and scale to its mesh; the cuts move with it, so they stay in place"""
    bl_idname = naming.op("fix_transforms")
    bl_label = "Apply Rotation & Scale"

    def execute(self, context):
        obj = _owner(context)
        if validate.transform_is_applied(obj):
            self.report({'INFO'}, f"{obj.name}: rotation and scale are already applied")
            return {'CANCELLED'}
        if not self._single_user(obj):
            return {'CANCELLED'}
        scale = tuple(round(x, 4) for x in obj.scale)
        n_cuts = len(stack_api.get_stack(obj).cuts)
        apply_rotation_scale(obj)
        self.report({'INFO'}, f"{obj.name}: applied rotation and scale {scale} to the mesh; "
                              f"{n_cuts} cut(s) kept in place{self._rebuild_hint(obj)}")
        return {'FINISHED'}


class SPLITFORGE_OT_fix_units(_FixOp, Operator):
    """Set the scene to Metric, Millimeters and Unit Scale 0.001 (1 unit = 1 mm, what slicers expect)"""
    bl_idname = naming.op("fix_units")
    bl_label = "Set Units to Millimeters"

    mode: EnumProperty(name="Objects", default='RELABEL', items=[
        ('RELABEL', "Keep Units", "Keep the objects as they are: 1 unit becomes 1 mm (right after importing "
         "an STL in millimeters into a meter scene)"),
        ('KEEP_SIZE', "Keep Size", "Scale every object in the scene so its physical size stays the same "
         "(a model built in meters keeps its millimeter size); apply the scale afterwards"),
    ])

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def invoke(self, context, event):
        if units.is_mm_scene(context.scene):
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.label(text=f"Now 1 unit = {units.bu_to_mm_factor(context.scene):g} mm", translate=False)
        layout.prop(self, "mode", expand=True)

    def execute(self, context):
        scene = context.scene
        us = scene.unit_settings
        before = units.bu_to_mm_factor(scene)
        if units.is_mm_scene(scene) and us.length_unit == 'MILLIMETERS' and us.system == 'METRIC':
            self.report({'INFO'}, "Units are already Millimeters with Unit Scale 0.001")
            return {'CANCELLED'}
        us.system = 'METRIC'
        us.length_unit = 'MILLIMETERS'
        us.scale_length = 0.001
        if self.mode == 'KEEP_SIZE' and abs(before - 1.0) > 1e-12:
            s = Matrix.Scale(before, 4)
            roots = [o for o in scene.objects if o.parent is None]
            for o in roots:
                o.matrix_world = s @ o.matrix_world
            self.report({'INFO'}, f"1 unit = 1 mm now (was {before:g} mm); {len(roots)} object(s) scaled by "
                                  f"{before:g} to keep their size (apply the scale before cutting)")
        else:
            self.report({'INFO'}, f"1 unit = 1 mm now (was {before:g} mm); objects unchanged, so a 1 unit "
                                  "object now reads 1 mm")
        return {'FINISHED'}


class SPLITFORGE_OT_fix_normals(_FixOp, Operator):
    """Recalculate the source mesh's face normals to point outward"""
    bl_idname = naming.op("fix_normals")
    bl_label = "Recalculate Normals"

    def execute(self, context):
        obj = _owner(context)
        if not self._single_user(obj):
            return {'CANCELLED'}
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            before = [f.normal.copy() for f in bm.faces]
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
            bm.normal_update()
            flipped = sum(1 for f, n in zip(bm.faces, before) if f.normal.dot(n) < 0.0)
            if flipped:
                bm.to_mesh(obj.data)
        finally:
            bm.free()
        if not flipped:
            self.report({'INFO'}, f"{obj.name}: normals already point outward")
            return {'CANCELLED'}
        obj.data.update()
        self._recheck(context, obj)
        self.report({'INFO'}, f"{obj.name}: flipped {flipped} face(s) to point outward{self._rebuild_hint(obj)}")
        return {'FINISHED'}


class SPLITFORGE_OT_fix_merge(_FixOp, Operator):
    """Merge vertices of the source mesh closer than the distance (Merge by Distance)"""
    bl_idname = naming.op("fix_merge")
    bl_label = "Merge by Distance"

    distance_mm: FloatProperty(name="Distance (mm)", default=validate.MERGE_MM, min=0.0, soft_max=0.1,
                               precision=4, description="Vertices closer than this are merged")

    def execute(self, context):
        obj = _owner(context)
        if not self._single_user(obj):
            return {'CANCELLED'}
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            n = len(bm.verts)
            bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=units.mm_to_scene(self.distance_mm, context.scene))
            removed = n - len(bm.verts)
            if removed:
                bm.to_mesh(obj.data)
        finally:
            bm.free()
        if not removed:
            self.report({'INFO'}, f"{obj.name}: no vertices closer than {self.distance_mm:g} mm")
            return {'CANCELLED'}
        obj.data.update()
        self._recheck(context, obj)
        self.report({'INFO'}, f"{obj.name}: merged {removed} vertex(es){self._rebuild_hint(obj)}")
        return {'FINISHED'}


class SPLITFORGE_OT_fix_holes(_FixOp, Operator):
    """Fill the holes of the source mesh and delete loose vertices and edges (edges with more than two faces are left for Edit Mode)"""
    bl_idname = naming.op("fix_holes")
    bl_label = "Fill Holes"

    def execute(self, context):
        obj = _owner(context)
        if not self._single_user(obj):
            return {'CANCELLED'}
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            loose_e = [e for e in bm.edges if not e.link_faces]
            n_loose_e = len(loose_e)
            if loose_e:
                bmesh.ops.delete(bm, geom=loose_e, context='EDGES')
            loose_v = [v for v in bm.verts if not v.link_faces]
            n_loose_v = len(loose_v)
            if loose_v:
                bmesh.ops.delete(bm, geom=loose_v, context='VERTS')
            open_edges = [e for e in bm.edges if len(e.link_faces) == 1]
            faces_before = len(bm.faces)
            if open_edges:
                bmesh.ops.holes_fill(bm, edges=open_edges, sides=0)
            new_faces = len(bm.faces) - faces_before
            if new_faces:
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
            remaining_open = sum(1 for e in bm.edges if len(e.link_faces) == 1)
            multi = sum(1 for e in bm.edges if len(e.link_faces) > 2)
            changed = bool(n_loose_e or n_loose_v or new_faces)
            if changed:
                bm.to_mesh(obj.data)
        finally:
            bm.free()
        left = ""
        if remaining_open or multi:
            left = (f"; still {remaining_open} open edge(s) and {multi} edge(s) with more than two faces: fix them "
                    "in Edit Mode")
        if not changed:
            self.report({'WARNING'} if left else {'INFO'}, f"{obj.name}: no holes or loose geometry{left}")
            return {'CANCELLED'}
        obj.data.update()
        self._recheck(context, obj)
        self.report({'WARNING'} if left else {'INFO'},
                    f"{obj.name}: filled holes with {new_faces} face(s), deleted {n_loose_v} loose vertex(es) and "
                    f"{n_loose_e} loose edge(s){left}{self._rebuild_hint(obj)}")
        return {'FINISHED'}


classes = (
    SPLITFORGE_OT_fix_transforms,
    SPLITFORGE_OT_fix_units,
    SPLITFORGE_OT_fix_normals,
    SPLITFORGE_OT_fix_merge,
    SPLITFORGE_OT_fix_holes,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
