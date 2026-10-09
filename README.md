# SplitForge (fork of SnapSplit)

**SplitForge** (temporary working name) is a Blender add-on that cuts a model into printable
parts and joins them with pins, tenons, dovetails, snap connectors, custom connectors or separate
dowels. It is a GPL-3.0-or-later fork of [SnapSplit](https://github.com/Betakontext/snapsplit) by
Christoph Medicus (Betakontext), rebuilt around a non-destructive workflow.

- Version **0.4.0**, for **Blender 5.2** (the only version it is tested on; see "Blender version").
- N-panel (sidebar) tab: **SplitForge**. German and Korean UI, Korean tooltips.
- Changes: [CHANGELOG.md](CHANGELOG.md). Development plan and verification records: `docs/`.

한국어 요약은 아래 [한국어 빠른 안내](#한국어-빠른-안내)에 있습니다.

## Installation

1. Download `splitforge-0.4.0.zip` (or build it, see "Building the release zip").
2. Blender 5.2: *Edit > Preferences > Get Extensions*, the drop-down at the top right,
   **Install from Disk...**, pick the zip. (Or drag the zip into the Blender window.)
3. Open a 3D Viewport, press **N**, choose the **SplitForge** tab.

The add-on needs no network access and stores everything in the .blend file.

## Unit setup (do this first)

Slicers read STL/OBJ numbers as millimeters. Set the scene so that one Blender unit is one
millimeter: *Scene Properties > Units*: **Metric**, Length **Millimeters**, **Unit Scale 0.001**.
The **Print checks** box at the top of the panel shows `1 unit = … mm` and offers **Fix**:

- **Keep Units** (default): only the unit settings change; an object that is 40 units long now
  reads 40 mm. Right for an STL in millimeters imported into Blender's default (meter) scene.
- **Keep Size**: every object in the scene is scaled so its physical size stays (a 0.04 m cube
  becomes 40 units = 40 mm); apply the scale afterwards (**Fix** on the rotation & scale row).

Every millimeter value in SplitForge (gaps, connector sizes, positions) is what Blender shows in
millimeters, whatever the unit setup; Export always writes millimeters.

## Print checks and one-click fixes

**Check Mesh** scans the selected object (its own mesh, before modifiers) and the panel lists:

| Check | Fix button | What the fix does |
|---|---|---|
| Rotation & scale applied | Apply Rotation & Scale | applies them to the mesh; the cut stack moves with the mesh, so every cut stays where it was in the world; children keep their place |
| 1 unit = 1 mm | Set Units to Millimeters | see "Unit setup" |
| Closed (no holes), no loose geometry | Fill Holes | fills open boundary loops, deletes loose vertices/edges |
| Normals point outward | Recalculate Normals | makes face normals consistent and outward |
| No duplicate vertices | Merge by Distance | merges vertices closer than 0.001 mm (adjustable) |
| Edges with 3+ faces | (none) | reported only: fix them in Edit Mode |

Each fix is a single undo step and reports exactly what it changed. Fixes refuse a mesh shared by
several objects. Built parts are not touched until the next Build. The mesh rows show the last
Check Mesh as long as the mesh is unchanged (no rescan on every redraw).

## Workflow

### Draft mode (cut stack)

Each object has its own **cut stack**. Add cuts with the buttons next to the list:

| Button | Cut | How |
|---|---|---|
| X / Y / Z | **Plane** | through the bounding box center; edit Origin / Normal / Gap, or **Adjust in Viewport** (mouse = move along the normal, wheel = 1 mm, X/Y/Z = axis, LMB confirm, Esc cancel) |
| curve icon | **Stroke** | drag a curve with LMB across the object; it is extruded along the view direction through the whole object; Shift at release = straight axis-aligned line; Enter confirms |
| line icon | **Polyline** | click points (straight segments, corners stay sharp); Ctrl = 15° steps on screen; Backspace or Ctrl+Z removes the last point; Enter confirms |
| circle icon | **Polygon** (cut-out) | click the corners of a region; click the first corner (or Enter) to close; the region becomes its own part, through the object or only **Depth** mm deep from the object's front (seen from the view) |

All point cuts keep the view direction of the first click (orbit freely between clicks; later
clicks land on the same plane), Esc / right click cancel without a trace, and **Redraw in
Viewport** replaces the points of an existing cut (its connectors and settings stay). Invalid input
is refused with the reason (crossing itself, too sharp for the gap, not crossing the object, a
polygon too narrow for its gap).

Cuts are applied top to bottom to every piece; disable one with its checkbox, reorder with the
arrows, duplicate it, remove it. **Gap (mm)** removes material along the cut (kerf); for a polygon
the gap is on its walls (the plug sits on the pocket floor).

Parts are named after the sides of every cut they lie on: `Object_A` (positive side of a plane /
left of a stroke drawn left to right / inside a polygon) and `Object_B`; with several cuts
`Object_AB`, `Object_BA`, …

### Easy mode

One step: choose the axis, offset, gap, connector count and press **Cut** (plane), or
**Draw Cut** (stroke), **Polyline** or **Cut Out** (polygon, with the Easy **Depth**). The cut is
added, connectors are distributed and the object is built at once; Ctrl+Z undoes all of it.
A polygon through the whole object gets no connectors.

### Build

**Build** never modifies the source object: it copies the evaluated mesh (modifiers applied),
cuts it and puts the parts into the collection `SplitForge_Build_<object>`, hides the source and
replaces the previous parts on every rebuild. The status bar shows the progress; Esc cancels and
keeps the previous result. **X** (Clear Build) deletes the parts and shows the source again.

**Settings > Booleans** (quality): *Auto* (default; Fast above 200,000 faces, Accurate below),
*Accurate* (exact solver; overlapping shells such as eyes set into a head are united into one
solid), *Fast* (manifold solver first; much faster on large meshes, but overlapping shells stay
overlapping, slicers unite them). Every boolean result is checked (manifold, plausible volume) and
retried with the next solver if it fails; the info line names the solvers used.

## Connectors

Connectors belong to a cut. **New connectors** sets the type and size of connectors added by:

- **Distribute**: Line (count along the seam) or Grid (columns x rows), with a margin. Every
  position is checked in 3D (pin and socket stay inside the object with 0.4 mm of material, do
  not reach across another cut or into a curved seam, keep away from other connectors); a
  position that does not fit is moved inward or dropped with the reason.
- **Click**: click on the seam in the viewport; the preview follows the cursor (green inside the
  object). S flips the pin side, every click is its own undo step, Enter/Esc ends.
- **+**: one connector at U/V 0, edit it in the box below.

Each connector has its own type, size, U/V position on the seam (mm), rotation, pin side (A or
B), clearance (-1 = scene default from the material profile: PLA 0.20, PETG 0.30, ABS/ASA 0.25,
TPU 0.35, SLA 0.10 mm per side) and insert depth.

| Type | Pin part | Socket part | Values |
|---|---|---|---|
| Cylinder pin | round pin | hole + clearance all round | diameter, length, insert depth, tip chamfer |
| Rectangular tenon | box tenon | box hole + clearance | width, height |
| Dovetail | tapered tenon (narrower tip, self-centering) | tapered hole, clearance normal to the slanted faces | taper % |
| Snap pin / tenon / dovetail | the above + snap bumps | dimples where the bumps sit after assembly | bumps, bump diameter, bump height |
| Custom mesh | any closed mesh object scaled into width x height x length (local Z = insertion direction, lowest Z = embedded end) | the mesh grown by the clearance in every direction | mesh, "Use Object Size" |
| Dowel (separate part) | a socket too | a socket | diameter, length, end chamfer |

Where connectors sit on each cut type: a **plane** on its plane; a **stroke** or **polyline** on
its ribbon (U = distance along the curve from its middle, V = depth along the view direction; on a
polyline the pin stands square on its straight segment and connectors keep off the corners); a
**polygon with a Depth** on the floor of the cut-out (pins point into the plug); a polygon through
the whole object has no floor and takes no connectors.

**Custom connectors** must be closed manifold solids (not flat, at most 20,000 faces). Their
socket keeps the full clearance everywhere: convex meshes get the exact grown hull at once;
others are grown along their normals, or, where that folds or loses clearance (slots narrower
than twice the clearance, sharp corners), built as a Minkowski sum of convex pieces (a second or
two, with a wait cursor; computed once per shape, size and clearance per session). A mesh too
detailed for that (over 4,000 triangles) is built with a warning naming the clearance it keeps.

**Dowels** are printed separately: both parts get a socket of half the dowel length plus the
clearance and Build adds a part `<object>_Dowel_<n>`. **Settings > Dowel layout**: *Flat*
(default; lying along X next to the object, layers run along the dowel), *Upright* (standing),
*At assembly position* (in the sockets, preview). Changing it moves existing dowels; Export writes
them in a print pose (upright when Upright is chosen, otherwise flat).

## Export

**Build & Export**: choose a folder (`//parts/` = next to the saved .blend) and formats
(STL, OBJ, FBX), then **Export Parts**: one file per visible part and format, in millimeters, axes
unchanged (Z up). A folder that cannot be created or a file that cannot be written is reported as
an error naming the path.

## Known limits

- Blender 5.2 only (see below).
- Stroke, polyline and polygon cuts are extruded straight along one view direction (a cookie
  cutter); they cannot follow a curved surface in depth. Perspective views use the view direction,
  not the diverging rays.
- Polygon cuts take connectors only on the floor of a cut-out with a Depth, not on their walls.
- One boolean step on a very large mesh (500k faces) blocks the UI for its duration; the status
  bar updates between steps. Accurate is much slower than Fast on such meshes (see `docs/CHECKLIST.md`).
- Sliding dovetail rails (pushed in sideways along the seam) are not supported yet (backlog B-1).
- Report messages (warnings/errors) are in English; the UI is translated.
- Fit (clearance, snap bump height) depends on the printer, material and orientation: print a test
  pair first.

## Blender version

SplitForge 0.4.0 supports **Blender 5.2** only (user decision, 2026-10-10): the manifest's
`blender_version_min` is 5.2.0 and every automated test runs on 5.2.2 LTS. It used Blender 4.5
as a second test target until Phase 3 (`python3 tests/run_tests.py --all-versions` still runs it,
as an unsupported signal); the 4.x solver-name shims were removed.

## Building the release zip

```sh
BL52="/path/to/blender"     # Blender 5.2
"$BL52" --command extension validate splitforge
"$BL52" --command extension build --source-dir splitforge --output-dir dist
# -> dist/splitforge-0.4.0.zip
```

The manifest excludes caches and tests (`paths_exclude_pattern`). Tests (Blender 5.2 headless,
GUI scenarios with simulated input, slow large-mesh cases): `python3 tests/run_tests.py
[--gui] [--slow]`.

## Package structure

```text
splitforge/
├── blender_manifest.toml, __init__.py, prefs.py, localization.py, LICENCE.txt
├── core/        units, validation, booleans (verified, solver fallback), mesh helpers, progress, naming
├── model/       cut stack PropertyGroups and stack operations
├── cuts/        plane, stroke, polyline and polygon cutters, Build
├── connectors/  solids (all types), custom sockets, placement, distribution, 3D fit checks, apply
├── ops/         stack, plane adjust, stroke, polyline/polygon, connectors, Build, Export, fixes
└── ui/          panel, viewport overlay
```

## 한국어 빠른 안내

1. 설치: Blender 5.2 *편집 > 환경 설정 > 확장 기능 받기* 오른쪽 위 메뉴의 **디스크에서 설치**로 zip 선택.
   3D 뷰포트에서 N → **SplitForge** 탭.
2. 단위: 패널 맨 위 **출력 검사**에서 `1 단위 = 1 mm`가 아니면 **수정** → *단위 유지*(mm STL을 가져온
   경우) 또는 *크기 유지*. **메시 검사**로 구멍·법선·중복 정점을 확인하고 각 줄의 **수정** 버튼으로 고칩니다
   (각각 실행 취소 한 번으로 되돌릴 수 있음).
3. Draft: 목록 옆 버튼으로 컷 추가 — X/Y/Z 평면, 스트로크(LMB로 그리기), 폴리라인(점 클릭, Ctrl 15° 단위,
   Backspace로 마지막 점 삭제), 폴리곤(영역 꼭짓점 클릭, 첫 점 클릭으로 닫기, **깊이**만큼 도려내기).
   커넥터 패널에서 종류·크기를 정하고 **자동 배치** 또는 **클릭**. **빌드** → 원본은 그대로, 파트는
   `SplitForge_Build_<오브젝트>` 컬렉션에.
4. Easy: 축·오프셋·틈·커넥터 수를 정하고 **자르기**(또는 그리기/폴리라인/도려내기) 한 번으로 빌드까지.
5. 내보내기: 폴더와 형식(STL/OBJ/FBX)을 고르고 **파트 내보내기** — 항상 mm.
6. 제한: Blender 5.2 전용, 곡선·폴리곤 컷은 한 방향 압출, 폴리곤 커넥터는 깊이가 있는 도려내기의
   바닥에만, 보고 메시지는 영어.

## Credits and license

SplitForge is a fork of **SnapSplit** by Christoph Medicus (Betakontext,
<https://dev.betakontext.de>, <https://github.com/Betakontext/snapsplit>); the original
segmentation, capping and connector ideas are his. SplitForge contributors rewrote the add-on
around the cut stack (the original SnapSplit tools were removed in Phase 3 after a parity test).
Both are distributed under the **GNU General Public License, version 3 or later**: see
`splitforge/LICENCE.txt`.
