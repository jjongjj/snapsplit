# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# core/validate.py
"""Print-readiness checks for a mesh object (read only, never modifies data)."""

from dataclasses import dataclass, field

import bmesh

from . import units


@dataclass
class ValidationReport:
    manifold: bool = True
    loose_geom: bool = False
    transform_applied: bool = True
    unit_is_mm: bool = True
    mm_per_unit: float = 1.0          # effective millimeters per Blender unit (1000 x Unit Scale)
    messages: list = field(default_factory=list)

    @property
    def ok(self):
        return (self.manifold and not self.loose_geom
                and self.transform_applied and self.unit_is_mm)


def mesh_stats(bm):
    """(non-manifold edges, loose verts, loose edges, faces) of a BMesh."""
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold and e.link_faces)
    loose_verts = sum(1 for v in bm.verts if not v.link_edges)
    loose_edges = sum(1 for e in bm.edges if not e.link_faces)
    return non_manifold, loose_verts, loose_edges, len(bm.faces)


def transform_is_applied(obj, tol=1e-6):
    """True when rotation is zero and scale is one (location may be anything)."""
    mat = obj.matrix_basis.to_3x3()
    for i in range(3):
        for j in range(3):
            if abs(mat[i][j] - (1.0 if i == j else 0.0)) > tol:
                return False
    return True


def validate(obj, scene=None, check_mesh=True):
    """Validate ``obj`` for printing. ``check_mesh=False`` skips the (slow) mesh scan."""
    rep = ValidationReport()
    if obj is None or obj.type != 'MESH' or obj.data is None:
        rep.manifold = False
        rep.messages.append("Not a mesh object")
        return rep

    if check_mesh:
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            non_manifold, loose_v, loose_e, faces = mesh_stats(bm)
        finally:
            bm.free()
        if faces == 0:
            rep.manifold = False
            rep.messages.append("Mesh has no faces")
        elif non_manifold:
            rep.manifold = False
            rep.messages.append(f"{non_manifold} non-manifold edge(s)")
        if loose_v or loose_e:
            rep.loose_geom = True
            rep.messages.append(f"Loose geometry: {loose_v} vertex(es), {loose_e} edge(s)")

    if not transform_is_applied(obj):
        rep.transform_applied = False
        rep.messages.append("Rotation/scale not applied")

    if scene is None and obj.users_scene:
        scene = obj.users_scene[0]
    rep.mm_per_unit = units.bu_to_mm_factor(scene)
    if not units.is_mm_scene(scene):
        rep.unit_is_mm = False
        rep.messages.append(f"1 unit = {rep.mm_per_unit:g} mm (Unit Scale 0.001: 1 mm)")
    return rep
