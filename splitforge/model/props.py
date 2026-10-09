# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# model/props.py
"""Cut stack data model (PropertyGroups).

The stack lives on the source object (``Object.<naming.OBJECT_STACK>``), so it
is saved with the file and restored by undo. Global UI/build settings live on
the scene (``Scene.<naming.SCENE_SETTINGS>``).

Coordinates: a cut's ``origin``/``normal``/``tangent`` are in the source
object's LOCAL space (Blender units), so moving the object moves its cuts.
Lengths a user types (gap, connector sizes, u/v) are millimeters and are
converted with core/units.py when the build runs.

Nothing here keeps references to Blender data between calls; operators and
draw code resolve ``obj.<stack>`` again every time.
"""

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       FloatVectorProperty, IntProperty, PointerProperty, StringProperty)
from bpy.types import PropertyGroup

from ..core import naming

SCHEMA_VERSION = 3   # 2: STROKE cuts (points, direction); 3: all connector types

CONNECTOR_KINDS = [
    ('CYL_PIN', "Cylinder pin", "Round pin; width is the diameter", 'MESH_CYLINDER', 0),
    ('RECT_TENON', "Rectangular tenon", "Box tenon of width x height (cannot rotate)", 'MESH_CUBE', 1),
    ('DOVETAIL', "Dovetail", "Tapered tenon: narrower towards the tip, self-centering", 'MESH_CONE', 2),
    ('SNAP_PIN', "Snap pin", "Cylinder pin with snap bumps that click into dimples in the socket",
     'MESH_UVSPHERE', 3),
    ('SNAP_TENON', "Snap tenon", "Rectangular tenon with snap bumps", 'MESH_ICOSPHERE', 4),
    ('SNAP_DOVETAIL', "Snap dovetail", "Tapered tenon with snap bumps", 'MESH_CAPSULE', 5),
    ('CUSTOM', "Custom mesh", "Any closed mesh object as the pin, scaled into width x height x length; "
     "the socket is its outline offset by the clearance", 'MESH_MONKEY', 6),
    ('DOWEL', "Dowel (separate part)", "Sockets in both parts and a separate printable dowel part",
     'MESH_CYLINDER', 7),
]

PIN_SIDES = [
    ('A', "A (+N)", "The pin sits on the part on the positive side of the cut normal"),
    ('B', "B (-N)", "The pin sits on the part on the negative side of the cut normal"),
]

DISTRIBUTIONS = [
    ('LINE', "Line", "Evenly spaced along the longer extent of the seam"),
    ('GRID', "Grid", "Columns x rows over the seam, points outside the section are dropped"),
]

# Material -> default socket clearance per side (mm)
MATERIAL_PROFILES = {
    "PLA": 0.20,
    "PETG": 0.30,
    "ABS": 0.25,
    "ASA": 0.25,
    "TPU": 0.35,
    "SLA": 0.10,
}
MATERIALS = [(key, key, f"Clearance {value:.2f} mm") for key, value in MATERIAL_PROFILES.items()]

def _redraw(_self, context):
    """Viewport overlay shows cuts/connectors: redraw 3D views after edits."""
    screen = getattr(context, "screen", None)
    for area in (screen.areas if screen else ()):
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def _custom_poll(self, obj):
    """Custom connector meshes: any mesh object except the stack owner itself."""
    return obj.type == 'MESH' and obj != self.id_data


def _material_changed(self, context):
    self.clearance_mm = MATERIAL_PROFILES.get(self.material, self.clearance_mm)


class SPLITFORGE_PG_Connector(PropertyGroup):
    """One pin/socket pair on a cut seam."""
    enabled: BoolProperty(name="Enabled", default=True, update=_redraw)
    kind: EnumProperty(name="Type", items=CONNECTOR_KINDS, default='CYL_PIN', update=_redraw)
    u: FloatProperty(name="U (mm)", default=0.0, precision=2, update=_redraw,
                     description="Position along the seam tangent, millimeters from the cut origin")
    v: FloatProperty(name="V (mm)", default=0.0, precision=2, update=_redraw,
                     description="Position along normal x tangent, millimeters from the cut origin")
    rotation_deg: FloatProperty(name="Rotation", default=0.0, min=-360.0, max=360.0, update=_redraw,
                                description="Rotation around the cut normal, degrees")
    width_mm: FloatProperty(name="Width (mm)", default=5.0, min=0.5, soft_max=50.0, update=_redraw,
                            description="Pin diameter (cylinder) or tenon width")
    height_mm: FloatProperty(name="Height (mm)", default=5.0, min=0.5, soft_max=50.0, update=_redraw,
                             description="Tenon height (rectangular tenon only)")
    length_mm: FloatProperty(name="Length (mm)", default=10.0, min=1.0, soft_max=100.0, update=_redraw,
                             description="Total pin (or dowel) length; Insert depth % of it sits in the pin part")
    pin_side: EnumProperty(name="Pin side", items=PIN_SIDES, default='A', update=_redraw)
    clearance_mm: FloatProperty(name="Clearance (mm)", default=-1.0, min=-1.0, max=2.0, precision=2,
                                description="Socket clearance per side; -1 uses the scene default")
    embed_pct: FloatProperty(name="Insert depth %", default=50.0, min=20.0, max=80.0, update=_redraw,
                             description="Share of the length that sits inside the pin part (the rest "
                                         "sticks out into the socket); dowels always use 50 %")
    taper_pct: FloatProperty(name="Taper %", default=20.0, min=0.0, max=60.0, update=_redraw,
                             description="Dovetail: how much narrower the tip is than the base, percent")
    chamfer_mm: FloatProperty(name="Chamfer (mm)", default=0.0, min=0.0, soft_max=2.0, precision=2,
                              update=_redraw,
                              description="Bevel of the pin tip (dowel: both ends), eases insertion")
    snap_count: IntProperty(name="Bumps", default=2, min=1, max=8, update=_redraw,
                            description="Snap bumps evenly around the pin")
    snap_diameter_mm: FloatProperty(name="Bump diameter (mm)", default=2.0, min=0.4, soft_max=6.0,
                                    precision=2, update=_redraw, description="Diameter of a snap bump")
    snap_protrusion_mm: FloatProperty(name="Bump height (mm)", default=0.6, min=0.1, soft_max=3.0,
                                      precision=2, update=_redraw,
                                      description="How far a snap bump stands out of the pin surface")
    custom_object: PointerProperty(name="Mesh", type=bpy.types.Object, poll=_custom_poll, update=_redraw,
                                   description="Closed mesh used as the pin (custom connectors); its local "
                                               "Z is the insertion direction, lowest Z the embedded end")


class SPLITFORGE_PG_Point(PropertyGroup):
    """One point of a stroke polyline (object local space)."""
    co: FloatVectorProperty(name="Point", size=3, subtype='TRANSLATION')


CUT_KINDS = [
    ('PLANE', "Plane", "Planar cut", 'MESH_PLANE', 0),
    ('STROKE', "Stroke", "Curved cut: a drawn stroke extruded along the view direction", 'CURVE_BEZCURVE', 1),
]


class SPLITFORGE_PG_Cut(PropertyGroup):
    """One cut of the stack: a plane, or a stroke ribbon (points + direction).

    For a STROKE cut ``origin``/``normal``/``tangent`` hold the seam frame at
    the middle of the stroke (display only); the cut itself is ``points``
    swept along ``direction``.
    """
    uid: StringProperty(name="ID", description="Stable identifier written onto built parts")
    enabled: BoolProperty(name="Enabled", default=True, update=_redraw)
    kind: EnumProperty(name="Kind", items=CUT_KINDS, default='PLANE', update=_redraw)
    points: CollectionProperty(type=SPLITFORGE_PG_Point,
                               description="Stroke polyline (object local space), STROKE cuts only")
    direction: FloatVectorProperty(name="Direction", size=3, default=(0.0, 1.0, 0.0), subtype='XYZ',
                                   update=_redraw,
                                   description="Extrusion direction of the stroke (object local space)")
    origin: FloatVectorProperty(name="Origin", size=3, subtype='TRANSLATION', update=_redraw,
                                description="A point on the cut plane (object local space)")
    normal: FloatVectorProperty(name="Normal", size=3, default=(0.0, 0.0, 1.0), subtype='XYZ',
                                update=_redraw, description="Cut plane normal (object local space)")
    tangent: FloatVectorProperty(name="Tangent", size=3, default=(1.0, 0.0, 0.0), subtype='XYZ',
                                 update=_redraw,
                                 description="Seam frame U axis (projected into the plane)")
    gap_mm: FloatProperty(name="Gap (mm)", default=0.0, min=0.0, soft_max=5.0, precision=2,
                          update=_redraw, description="Material removed along the cut (kerf)")
    cap: BoolProperty(name="Cap", default=True, description="Close the cut faces")
    connectors: CollectionProperty(type=SPLITFORGE_PG_Connector)
    active_connector: IntProperty(name="Active connector", default=0, min=0)
    distribution: EnumProperty(name="Distribution", items=DISTRIBUTIONS, default='LINE')
    connector_count: IntProperty(name="Count", default=2, min=1, max=64,
                                 description="Connectors along the line, or grid columns")
    connector_rows: IntProperty(name="Rows", default=2, min=1, max=64, description="Grid rows")
    margin_pct: FloatProperty(name="Margin %", default=15.0, min=0.0, max=45.0,
                              description="Distance kept from the seam edges, percent of its extent")


class SPLITFORGE_PG_CutStack(PropertyGroup):
    """Cut stack of one source object."""
    cuts: CollectionProperty(type=SPLITFORGE_PG_Cut)
    active_index: IntProperty(name="Active cut", default=0, min=0, update=_redraw)
    mode: EnumProperty(name="Mode", default='DRAFT', items=[
        ('DRAFT', "Draft", "Edit a stack of cuts, then Build"),
        ('EASY', "Easy", "One click: add an axis cut and build immediately"),
    ])
    last_build_collection: PointerProperty(type=bpy.types.Collection, name="Result")
    schema_version: IntProperty(default=SCHEMA_VERSION)
    next_uid: IntProperty(default=1, min=1)


class SPLITFORGE_PG_Settings(PropertyGroup):
    """Scene-wide settings of the new workflow."""
    show_overlay: BoolProperty(name="Show cuts in viewport", default=True, update=_redraw)
    boolean_quality: EnumProperty(name="Booleans", default='AUTO', items=[
        ('AUTO', "Auto", "Fast on meshes over 200,000 faces, Accurate below"),
        ('ACCURATE', "Accurate",
         "Exact solver first (with self-intersection handling when shells intersect): intersecting "
         "shells, e.g. eyes set into a head, are united into one solid. Slow on large meshes"),
        ('FAST', "Fast",
         "Manifold solver first, much faster on large meshes, but intersecting shells stay "
         "overlapping (each is cut on its own; slicers unite them). Falls back to Accurate on failure"),
    ], description="Boolean solver order for curved cuts and connectors; every result is validated")
    material: EnumProperty(name="Material", items=MATERIALS, default='PLA', update=_material_changed)
    clearance_mm: FloatProperty(name="Clearance (mm)", default=0.20, min=0.0, max=2.0, precision=2,
                                description="Default socket clearance per side")
    new_connector: PointerProperty(type=SPLITFORGE_PG_Connector, name="New connector",
                                   description="Type and size of connectors added by Distribute or clicking")
    easy_axis: EnumProperty(name="Axis", default='Z', items=[
        ('X', "X", "World X"), ('Y', "Y", "World Y"), ('Z', "Z", "World Z")])
    easy_offset_mm: FloatProperty(name="Offset (mm)", default=0.0, precision=2,
                                  description="Distance of the cut from the object's bounding box center")
    easy_gap_mm: FloatProperty(name="Gap (mm)", default=0.0, min=0.0, soft_max=5.0, precision=2,
                               description="Material removed along an Easy cut (kerf)")
    easy_connector_count: IntProperty(name="Connectors", default=2, min=0, max=16,
                                      description="Pins added along the seam (0 = none)")
    export_directory: StringProperty(name="Folder", subtype='DIR_PATH', default="//parts/")
    export_formats: EnumProperty(name="Formats", options={'ENUM_FLAG'}, default={'STL'}, items=[
        ('STL', "STL", "Binary STL"), ('OBJ', "OBJ", "Wavefront OBJ"), ('FBX', "FBX", "Autodesk FBX")])


classes = (
    SPLITFORGE_PG_Point,
    SPLITFORGE_PG_Connector,
    SPLITFORGE_PG_Cut,
    SPLITFORGE_PG_CutStack,
    SPLITFORGE_PG_Settings,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    setattr(bpy.types.Object, naming.OBJECT_STACK, PointerProperty(type=SPLITFORGE_PG_CutStack))
    setattr(bpy.types.Scene, naming.SCENE_SETTINGS, PointerProperty(type=SPLITFORGE_PG_Settings))


def unregister():
    for owner, name in ((bpy.types.Scene, naming.SCENE_SETTINGS), (bpy.types.Object, naming.OBJECT_STACK)):
        if hasattr(owner, name):
            delattr(owner, name)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
