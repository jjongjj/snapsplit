# SPDX-License-Identifier: GPL-3.0-or-later
# This file is part of SplitForge (fork of SnapSplit by Christoph Medicus).

# core/validate.py
"""Print-readiness checks for a mesh object (read only, never modifies data).

``validate`` scans the mesh (the source's own mesh data, before modifiers):

- open edges (one face: a hole), edges with more than two faces (not fixable
  automatically), loose vertices/edges;
- inconsistent normals (an edge whose two faces run it the same way) and an
  inside-out mesh (negative enclosed volume);
- duplicate vertices (closer than ``MERGE_MM``);
- unapplied rotation/scale, and the unit setup (1 Blender unit = 1 mm).

Every finding names its one-click fix (ops/ops_fix.py). ``last_report`` keeps
the result of the last Check Mesh per object as plain values (no Blender
data), keyed by a fingerprint of the mesh, so the panel can show it without
rescanning large meshes on every redraw.
"""

from dataclasses import dataclass, field

import bmesh
from mathutils.kdtree import KDTree

from . import units

# Vertices closer than this are duplicates (Merge by Distance), millimeters
MERGE_MM = 0.001


@dataclass
class ValidationReport:
    manifold: bool = True
    loose_geom: bool = False
    transform_applied: bool = True
    unit_is_mm: bool = True
    mm_per_unit: float = 1.0          # effective millimeters per Blender unit (1000 x Unit Scale)
    open_edges: int = 0               # edges with one face (holes)
    multi_edges: int = 0              # edges with more than two faces
    loose_verts: int = 0
    loose_edges: int = 0
    flipped_edges: int = 0            # edges whose two faces disagree on the winding
    inside_out: bool = False          # consistent normals pointing inward (negative volume)
    duplicates: int = 0               # vertices within MERGE_MM of another one
    checked_mesh: bool = False
    messages: list = field(default_factory=list)

    @property
    def normals_ok(self):
        return not self.flipped_edges and not self.inside_out

    @property
    def ok(self):
        return (self.manifold and not self.loose_geom and self.normals_ok and not self.duplicates
                and self.transform_applied and self.unit_is_mm)


def mesh_stats(bm):
    """(non-manifold edges, loose verts, loose edges, faces) of a BMesh."""
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold and e.link_faces)
    loose_verts = sum(1 for v in bm.verts if not v.link_edges)
    loose_edges = sum(1 for e in bm.edges if not e.link_faces)
    return non_manifold, loose_verts, loose_edges, len(bm.faces)


def flipped_edges(bm):
    """Edges between two faces that traverse them in the same direction (inconsistent normals)."""
    count = 0
    for e in bm.edges:
        if len(e.link_loops) != 2:
            continue
        a, b = e.link_loops
        if a.vert == b.vert:
            count += 1
    return count


def duplicate_verts(bm, distance):
    """Number of vertices with another vertex within ``distance`` (what Merge by Distance would remove)."""
    if len(bm.verts) < 2 or distance <= 0.0:
        return 0
    tree = KDTree(len(bm.verts))
    for i, v in enumerate(bm.verts):
        tree.insert(v.co, i)
    tree.balance()
    removed = set()
    for i, v in enumerate(bm.verts):
        if i in removed:
            continue
        for _co, j, _d in tree.find_range(v.co, distance):
            if j != i and j not in removed:
                removed.add(j)
    return len(removed)


def transform_is_applied(obj, tol=1e-6):
    """True when rotation is zero and scale is one (location may be anything)."""
    mat = obj.matrix_basis.to_3x3()
    for i in range(3):
        for j in range(3):
            if abs(mat[i][j] - (1.0 if i == j else 0.0)) > tol:
                return False
    return True


def mesh_key(obj):
    """Cheap fingerprint of an object's mesh data (changes after edits, fixes and undo)."""
    me = obj.data
    n = len(me.vertices)
    probe = tuple(tuple(round(c, 6) for c in me.vertices[i].co) for i in sorted({0, n // 2, n - 1})) if n else ()
    return (obj.name, me.name, n, len(me.edges), len(me.polygons), probe,
            tuple(tuple(p.vertices) for p in me.polygons[:8]))


# object name -> (mesh_key, ValidationReport) of the last Check Mesh (plain values only)
_LAST = {}


def last_report(obj):
    """The last full report of ``obj`` if its mesh did not change since, else None."""
    hit = _LAST.get(obj.name)
    if hit is None or hit[0] != mesh_key(obj):
        return None
    return hit[1]


def validate(obj, scene=None, check_mesh=True):
    """Validate ``obj`` for printing. ``check_mesh=False`` skips the (slow) mesh scan."""
    rep = ValidationReport()
    if obj is None or obj.type != 'MESH' or obj.data is None:
        rep.manifold = False
        rep.messages.append("Not a mesh object")
        return rep

    if scene is None and obj.users_scene:
        scene = obj.users_scene[0]
    if check_mesh:
        rep.checked_mesh = True
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            rep.open_edges = sum(1 for e in bm.edges if len(e.link_faces) == 1)
            rep.multi_edges = sum(1 for e in bm.edges if len(e.link_faces) > 2)
            rep.loose_verts = sum(1 for v in bm.verts if not v.link_edges)
            rep.loose_edges = sum(1 for e in bm.edges if not e.link_faces)
            faces = len(bm.faces)
            rep.flipped_edges = flipped_edges(bm)
            if faces and not rep.open_edges and not rep.multi_edges and not rep.flipped_edges:
                rep.inside_out = bm.calc_volume(signed=True) < 0.0
            rep.duplicates = duplicate_verts(bm, units.mm_to_scene(MERGE_MM, scene))
        finally:
            bm.free()
        if faces == 0:
            rep.manifold = False
            rep.messages.append("Mesh has no faces")
        elif rep.open_edges or rep.multi_edges:
            rep.manifold = False
            rep.messages.append(f"{rep.open_edges + rep.multi_edges} non-manifold edge(s): "
                                f"{rep.open_edges} open (holes), {rep.multi_edges} with more than two faces")
        if rep.loose_verts or rep.loose_edges:
            rep.loose_geom = True
            rep.messages.append(f"Loose geometry: {rep.loose_verts} vertex(es), {rep.loose_edges} edge(s)")
        if rep.flipped_edges:
            rep.messages.append(f"Inconsistent normals at {rep.flipped_edges} edge(s)")
        elif rep.inside_out:
            rep.messages.append("Normals point inward (inside-out mesh)")
        if rep.duplicates:
            rep.messages.append(f"{rep.duplicates} duplicate vertex(es) (closer than {MERGE_MM:g} mm)")

    if not transform_is_applied(obj):
        rep.transform_applied = False
        rep.messages.append("Rotation/scale not applied")

    rep.mm_per_unit = units.bu_to_mm_factor(scene)
    if not units.is_mm_scene(scene):
        rep.unit_is_mm = False
        rep.messages.append(f"1 unit = {rep.mm_per_unit:g} mm (Unit Scale 0.001: 1 mm)")
    if check_mesh:
        if len(_LAST) > 64:
            _LAST.clear()
        _LAST[obj.name] = (mesh_key(obj), rep)
    return rep
