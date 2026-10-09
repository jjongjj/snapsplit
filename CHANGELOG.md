# Changelog

SplitForge is a fork of SnapSplit by Christoph Medicus (Betakontext). Versions before 0.3 are
SnapSplit's (see its repository); SplitForge continues the numbering.

## 0.4.1 (2026-10-10) - fixes after the Phase 4 verification

Fixed
- Sharp polyline corners with a gap (D20): offsets now use exact mitre joins (the old clamped mitre
  narrowed the kerf along both segments next to a corner under ~30 degrees and Build failed with "no
  solver left"); corners under 15 degrees are refused with a gap, at add time and in the panel check.
  Polygons the same.
- Tiny polygon cut-outs (D21, D22): refused at add time and in the panel check instead of failing at
  Build, each with its own reason: narrower than 0.5 mm, shallower than 0.2 mm, or removing less volume
  than the boolean result check can see on an object that large (2 x 1e-6 of its bounding box volume:
  250 mm^3 on a 500 mm cube). (A first version scaled the volume limit 10x too strictly and refused
  normal pockets on large objects; fixed before release.)
- A floor connector of a polygon cut-out too close to its wall is skipped / dropped with a message about
  the cut-out's wall (it said "the curved seam bends into it").
- Placing points after orbiting the view: Ctrl's 15 degree steps and closing a polygon on its first
  corner use where the points are on screen now.
- Apply Rotation & Scale applies delta rotation and scale too (left scale 0.5 / delta 2 before).
- Fill Holes reports faces it turned outward; the stack's schema version is written to the file.

## 0.4.0 (2026-10-10) - first feature-complete release, Blender 5.2

Added
- **Polyline cut**: click points in the viewport; straight segments with sharp corners, extruded
  along the view direction; Ctrl = 15 degree steps, Backspace / Ctrl+Z remove the last point;
  connectors stand square on their segment.
- **Polygon cut (cut-out)**: click a closed polygon; its region becomes its own part, through the
  object or a set Depth deep (a plug in a pocket); gap on the walls; connectors on the cut-out's
  floor; the prism counts as a barrier for other cuts' connectors. Draft, Easy ("Cut Out", Easy
  Depth), redraw, overlay, panel checks.
- **Print checks with one-click fixes**: Check Mesh reports holes, edges with 3+ faces, loose
  geometry, inconsistent / inward normals, duplicate vertices; Fix buttons for rotation & scale
  (the cut stack stays in place), units (Millimeters + 0.001, Keep Units / Keep Size), normals,
  merge by distance, fill holes. One undo step each, every change reported.
- Release packaging: `extension build` zip (44 files), `tests/run_tests.py --zip` installs it with
  `package_install_files` and runs the tests on its contents.
- German and Korean labels, Korean tooltips for all new UI.

Changed
- **Blender 5.2 only** (`blender_version_min = 5.2.0`); tests run on 5.2 by default
  (`--all-versions` adds 4.5, unsupported). 4.x boolean solver-name shims removed.
- Custom connector sockets (defect D19): convex meshes use the exact grown convex hull (17-face
  cone 17.4 s -> 0.01 s per socket), others a Minkowski sum of convex per-face hulls (star 3.4 s
  -> 1.9 s); one computation per shape, size and clearance for both pin sides, any gap and insert
  depth; a wait cursor and status text on the slow path. The new sockets have no degenerate
  triangles, so their DIFFERENCE no longer falls back from the exact solver to MANIFOLD.

Fixed
- Export to a folder that cannot be created, or onto a path that cannot be written, reports a
  clean error naming the path instead of a Python traceback.

## 0.3.0-dev (Phases 0-3, 2026-10-09/10)

- Test harness (headless + GUI with simulated input), non-destructive cut stack with Build, plane
  and stroke (curved) cuts, verified booleans with solver fallback and quality setting, progress,
  connectors of every type (custom meshes, dowels with layouts), click placement, Export, German
  and Korean UI; the original SnapSplit tools were replaced. Details: `docs/CHECKLIST.md`.
