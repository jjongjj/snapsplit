# SnapSplit 포크 → "Cut & Connect for 3D printing" 애드온 발전 계획

작성일: 2026-10-09 / 기준: `master` (v0.1.9), `upstream/V_0.2.0_freehand` (v0.2.0)
Blender 대상: 4.2 LTS ~ 5.x (검증 환경: 4.5.5 LTS, 5.2.2 LTS, Windows exe를 WSL에서 headless 호출)

---

## 1. 현황 분석 (Gap Analysis)

### 1.1 SnapSplit이 지금 하는 것

| 영역 | 현재 구현 | 핵심 코드 |
|---|---|---|
| 컷 | 월드축(X/Y/Z) 평면으로 N등분. `bmesh.ops.bisect_plane` 기반(불리언 아님). 오프셋 1개(모달 `adjust_split_axis`). 등간격만 가능 | `ops_split.py` `create_cut_data_with_offset`(862), `split_mesh_bmesh_into_two`(1071), `apply_bmesh_split_sequence`(1139) |
| 캡핑 | 컷 단면의 폐루프를 찾아 `triangle_fill`/n-gon으로 채움. 중공(hollow) 링(외곽+구멍) 처리 지원 | `cap_single_object_hollow_style`(1389, ~375줄) |
| 결과물 | 원본 숨김(`hide_set`), 파트는 `SnapSplit_Parts/<src>_<timestamp>` 컬렉션. 이름은 `_A_S1_B_S2` 식 누적 | `_ensure_job_collections`(598) |
| 커넥터 | 7종: CYL_PIN, RECT_TENON, DOVETAIL, SNAP_PIN, SNAP_TENON, SNAP_DOVETAIL, CUSTOM(사용자 메시). 핀=UNION, 소켓=DIFFERENCE, Boolean 모디파이어(EXACT→FAST→FLOAT 순 폴백)를 즉시 적용 | `ops_connectors.py` `place_connectors_between`(2579, ~440줄), `boolean_*`(1184~1494) |
| 커넥터 배치 | 자동(LINE/GRID, 시임당 1~128개, 마진%) 또는 클릭 배치(모달, S키로 핀/소켓 스왑). 재질 프로필별 공차(PLA 0.2 등, 소켓에만 적용) | `distribute_points_*`(642~742), `SNAP_OT_place_connectors_click`(3347) |
| 정렬 | Face A/B 픽 → B를 A에 면 맞춤. 시임 평면을 B의 커스텀 프로퍼티에 기록 | `ops_align.py` |
| Freehand (0.2.0 브랜치) | 뷰포트에 스트로크를 그리면 **PCA로 직선 1개로 환원 → 뷰 정렬 평면 1개**로 bisect. 곡선 컷 아님(README도 명시). 캡핑·검증·롤백이 매우 방어적. 시임 메타데이터(`seam_data.py`, JSON 커스텀 프로퍼티)로 경사 시임에 커넥터 배치 가능 | `ops_freehand.py`(2437줄), `seam_data.py`(771줄) |
| 기타 | 15개 언어 로컬라이즈(`localization.py` 3k줄), extension manifest, 프리뷰(평면 오브젝트 + depsgraph 핸들러) | |

### 1.2 목표 기능 대비 갭

| 목표 기능 | 현황 | 갭 |
|---|---|---|
| Draft 모드(비파괴 컷 스택: 추가/편집/비활성/삭제 → Build) | 없음. 모든 작업이 즉시 파괴적이고 파라미터가 어디에도 저장되지 않음 | **신규 데이터 모델 전체** |
| Easy 모드(즉시 실행) | 사실상 현재 동작 | 새 파이프라인 위에서 재구현 |
| 직선(평면) 컷 | 월드축 평면만. 임의 방향 불가(Freehand는 뷰 평면 1개) | 임의 origin/normal 평면 지원, 컷별 독립 평면 |
| 곡선 컷(스트로크 → 곡면 커터) | 없음(Freehand는 평면으로 환원) | **스트로크→리본→솔리드 커터, 불리언 파이프라인** |
| Manual(폴리라인) / Polygonal(영역 제거) | 없음 | 커터 생성기 2종 추가 |
| 커넥터 자동 핀/소켓 | 있음(자동/클릭) | 컷별·커넥터별 레코드로 재편, 편집 가능하게 |
| 위치/회전/스케일/폭/높이 편집 | 전역 설정 1벌뿐. 배치 후 수정 불가 | 커넥터별 프로퍼티 + 재빌드 |
| 여러 내장 타입 / 커스텀 메시 | 7종 + CUSTOM 있음 | 지오메트리 빌더는 재사용, 배치 로직은 교체 |
| 핀이 붙는 면 선택 | 전역 스왑 토글 + 모달 S키 | 커넥터별 `pin_side` |
| 클리어런스 & 컷 갭(mm) | 공차 있음(소켓만, 깊이 방향 없음). **컷 갭 없음**(bisect는 갭 0) | 갭은 커터 두께로, 공차는 소켓 반경+깊이 |
| 컷당 N개 커넥터 | 있음(LINE/GRID) | 유지, 레코드화 |
| 양면 도웰(double-sided dowel) | 없음 | 양쪽 소켓 + 별도 도웰 파트 출력 |
| 검증(매니폴드/적용된 변환/단위 mm) | 변환은 자동 적용(파괴적), 매니폴드 검사 없음, 단위는 2값 휴리스틱(`unit_mm()`: mm 아니면 무조건 m로 가정 → cm/imperial 오류) | 검증 패널 + 올바른 단위 변환 |
| Build → 새 컬렉션, 원본 보존 | 원본 숨김만(이미 변환 적용·모디파이어 적용·짝 오브젝트 join 등으로 **원본이 변형됨**) | 원본 복사본에서 빌드 |
| 일괄 내보내기 STL/OBJ/FBX | 없음 | 신규 |
| 견고한 불리언(Exact + voxel remesh 폴백) + 진행률 | 솔버 폴백은 있음. 실패 감지는 CUSTOM 타입만. 진행률은 split에만 `wm.progress` | 통합 파이프라인 |
| Blender 4.2~5.x | manifest min 4.2, README 테스트 4.5/5.x. **버그: `mat.shadow_method`(4.2에서 제거됨) → 프리뷰 재질 생성 시 AttributeError** (아래 2절 실측) | 호환성 가드 + 자동 테스트 |

### 1.3 코드 품질 문제(설계에 영향을 주는 것만)

- 배치 수학이 3곳(배치/클릭/라이브프리뷰)에 중복 → 프리뷰와 결과 불일치 가능. 440줄·375줄·280줄짜리 함수.
- `try/except Exception: pass` 수십 곳, `print("[SnapSplit DEBUG]")`가 운영 경로에 다수 → 실패가 조용히 묻힘.
- 모듈 전역 상태(`_FRAME_X_HINT`, `_last_preview_*`, X-ray 레지스트리), depsgraph 핸들러 안에서 오브젝트 생성/삭제(프리뷰 평면) → undo와 충돌 위험.
- 프리뷰 평면 위치 계산과 실제 컷 위치 계산이 분리된 두 진실(`position_preview_planes_for_object` vs `create_cut_data_with_offset`).
- `.gitignore`에 `snapsplit/ops_split.py`와 `/Tests/`가 들어 있음. Windows(`core.ignorecase=true`)에서는 **`tests/`도 무시됨** → Phase 0에서 수정 필수.
- `bl_info["blender"] = (5,2,0)` vs manifest `4.2.0` 불일치(extension 경로에서는 bl_info 무시되지만 혼란).

## 2. Headless 실측 결과 (2026-10-09)

방법: `snapsplit/`를 임시 디렉터리에 복사 → `preferences.extensions.repos.new(custom_directory=...)` → `addon_enable("bl_ext.probe.snapsplit")` → mm 씬에서 큐브/매니폴드 처리한 Suzanne을 Z축 2분할 → `add_connectors`(CYL_PIN) → 매니폴드 검사. (`blender.exe -b --factory-startup --python probe.py -- <repo_dir>`)

| 항목 | 4.5.5 LTS | 5.2.2 LTS |
|---|---|---|
| 등록/해제/재등록 (master) | PASS | PASS |
| 등록 (V_0.2.0_freehand, `SNAPSPLIT_OT_freehand_cut` 포함) | PASS | PASS |
| 큐브 Z 2분할 → 2파트, 매니폴드, 원본 존재 | PASS (0.01s) | PASS |
| Suzanne(구멍 메움) 2분할 → 2파트(414/280면), 캡핑 포함 매니폴드 | PASS | PASS |
| `add_connectors` CYL_PIN 3개 → 양 파트 매니폴드 유지 | PASS (큐브 1.1s, 원숭이 0.09s) | PASS |
| 프리뷰 재질 `build_orange_preview_material()` | **FAIL** `AttributeError: 'Material' object has no attribute 'shadow_method'` | **FAIL** 동일 |
| 51만 면 Suzanne(subsurf 5) 3분할 + 핀 3개 (5.2) | – | split 4.6s, connectors 12.8s(진행 표시 없음) |

관찰:
- 핵심 split/connector 파이프라인은 4.5/5.2 모두 headless에서 동작한다.
- 프리뷰 재질 버그는 depsgraph 핸들러의 `try/except`에 삼켜져 GUI에서 "프리뷰가 그냥 안 보이는" 증상으로 나타날 가능성이 큼(GUI 확인 필요, Phase 0에서 수정).
- 결과 컬렉션이 `Cube.001_20261009_091744`와 `...001`(원본용) 두 개씩 생김 → 네이밍 정리 필요.
- 4.2는 로컬에 설치되어 있지 않아 미검증(설치된 것: 4.4, 4.5, 5.2).

## 3. 브랜치 전략

결정: **`develop`을 `upstream/V_0.2.0_freehand`에서 분기**한다.

근거:
- `master`는 freehand 브랜치의 조상(strict ancestor)이다. 즉 freehand = master + 0.2.0 작업이며 충돌 없이 포함된다.
- `seam_data.py`(시임 메타데이터·검증)와 ops_freehand의 스트로크 모달/gpu 드로잉 코드는 우리 곡선 컷과 커넥터 레코드의 출발점으로 재사용 가치가 있다.
- 업스트림이 0.2.0을 master에 머지하면 `git merge upstream/master`가 사실상 no-op이 된다.

운영 규칙:
- 브랜치: `develop`(통합), `feat/<phase>-<topic>`(작업), `plan/architecture`(이 문서). 릴리스는 `develop` → `master`(포크) 머지 + 태그 `v0.3.0` 등.
- 업스트림 동기화: 주 1회 `git fetch upstream && git merge upstream/master`(또는 freehand 브랜치가 갱신되면 그것). rebase 금지(공유 브랜치).
- 충돌 최소화 원칙(strangler 패턴): 새 기능은 **새 모듈**(`core/`, `cuts/`, `connectors/`, `ops/`)에 작성하고 기존 파일(`ops_split.py`, `ops_connectors.py`, `ops_freehand.py`)은 "레거시 모드"로 두고 최소 수정(버그 가드, 함수 추출)만 한다. 기능 동등성 확보 후 레거시 모듈을 제거한다.
- 업스트림 기여: 범용 버그 수정(`shadow_method` 가드, `.gitignore`)은 별도 작은 브랜치로 upstream PR 가능.

## 4. 아키텍처

### 4.1 모듈 레이아웃

```
snapsplit/
  __init__.py                 # 등록 순서: core → model → ops → ui, 레거시 포함
  blender_manifest.toml
  core/
    compat.py                 # bpy.app.version 가드, 재질/모디파이어 API 차이 흡수
    units.py                  # mm↔scene 정확 변환(scale_length·length_unit 전부 반영)
    log.py                    # logging 기반, DEBUG는 프리퍼런스 토글
    validate.py               # manifold/loose/transform/unit 검사 → ValidationReport
    boolean.py                # 불리언 파이프라인(4.4절)
    meshlib.py                # bisect+cap(기존 cap 함수 이관), volume, bbox, remesh
    progress.py               # wm.progress + 상태바 + 모달 타이머 스텝 실행기
    scene.py                  # 컬렉션/이름 규칙, 결과 컬렉션 생성
  model/
    props.py                  # PropertyGroup: CutItem, ConnectorItem, CutStack, 전역 설정
    stack.py                  # 스택 조작 API(add/remove/move/enable), 직렬화
  cuts/
    plane.py                  # 평면 커터(origin/normal) 생성·프리뷰 데이터
    stroke.py                 # 스트로크 → 리본 → 솔리드 커터(곡선 컷)
    polyline.py               # 수동 점 입력 커터
    polygon.py                # 폴리곤 영역 제거 커터
    build.py                  # Build 파이프라인: 원본 복사 → 컷 순차 적용 → 캡 → 커넥터 → 컬렉션
  connectors/
    shapes.py                 # 기존 create_cyl_pin/rect_tenon/dovetail/custom/sphere 이관
    placement.py              # 시임 프레임 + UV 위치 → 월드 변환(단일 진실)
    apply.py                  # 핀 UNION/소켓 DIFFERENCE, 클리어런스, 양면 도웰
  ops/
    ops_stack.py              # 스택 CRUD, Build, Easy 모드
    ops_cut_plane.py          # 평면 컷 추가/조정(모달 gizmo)
    ops_cut_stroke.py         # 스트로크 모달(ops_freehand에서 입력·드로잉 부분 발췌)
    ops_connector.py          # 커넥터 추가/클릭 배치/편집
    ops_export.py             # 일괄 STL/OBJ/FBX
    ops_validate.py
  ui/
    panel.py, lists.py (UIList), overlay.py (gpu 오버레이 프리뷰)
  legacy/ (Phase 3 말까지 유지) ops_split.py, ops_connectors.py, ops_align.py, ops_freehand.py, seam_data.py, profiles.py
  localization.py
tests/
  run_tests.py                # 호스트 파이썬: Blender 버전별 실행, 종료코드 집계
  blender_runner.py           # Blender 안: 확장 등록, cases 발견·실행, JSON 보고
  lib/                        # make_cube/monkey/hollow, is_manifold, volume, assert 헬퍼
  cases/test_*.py             # 각 파일 run(ctx) 함수
  fixtures/*.blend (필요 시)
```

유지/리팩터/추가 요약:
- 유지(이관): 커넥터 지오메트리 빌더, 캡핑 알고리즘, `apply_modifier_data`, `seam_data` 검증 아이디어, 로컬라이즈, 재질 프로필 표.
- 리팩터: 배치 수학 단일화(`connectors/placement.py`), 단위 변환, 로깅, 솔버 선택.
- 신규: 모델/스택/빌드/커터 생성기/내보내기/검증/테스트 하니스.

### 4.2 데이터 모델 (PropertyGroup)

저장 위치: **원본 오브젝트**에 `obj.snapsplit_stack`(PointerProperty → `SNAP_PG_CutStack`). 파일 저장/undo에 자동 포함. 전역 UI 상태는 `scene.snapsplit`(기존)에 유지.

```python
class SNAP_PG_Connector(PropertyGroup):
    enabled: Bool
    kind: Enum[CYL_PIN, RECT_TENON, DOVETAIL, SNAP_PIN, SNAP_TENON, SNAP_DOVETAIL, CUSTOM, DOWEL]
    u, v: Float              # 시임 평면 내 2D 위치(mm, 시임 프레임 기준)
    rotation_deg: Float      # 평면 내 회전
    width_mm, height_mm, length_mm: Float
    scale: FloatVector(3)
    pin_side: Enum[A, B]     # 핀이 붙는 파트
    clearance_mm: Float      # -1 = 프로필 기본값
    custom_object: Pointer(Object)
    double_sided: Bool       # 도웰: 양쪽 소켓 + 별도 도웰 파트

class SNAP_PG_Cut(PropertyGroup):
    name: String; enabled: Bool
    kind: Enum[PLANE, STROKE, POLYLINE, POLYGON]
    origin, normal, tangent: FloatVector(3)   # 원본 로컬 좌표. PLANE/STROKE 시임 프레임
    cutter_object: Pointer(Object)            # STROKE/POLYLINE/POLYGON: 숨김 컬렉션의 편집 가능한 커터 메시
    points: Collection(SNAP_PG_Point)         # 스트로크/폴리라인 원시 점(재생성용)
    gap_mm: Float; cap: Bool
    target_part: String                       # 스택 상 어느 파트에 적용(빈 값=전체 원본)
    connectors: Collection(SNAP_PG_Connector)
    connector_distribution: Enum[LINE, GRID, MANUAL]; count, rows, margin_pct
    seam_cache: String                        # 빌드 후 시임 윤곽 JSON(seam_data 방식), 읽기 전용

class SNAP_PG_CutStack(PropertyGroup):
    cuts: Collection(SNAP_PG_Cut); active_index: Int
    mode: Enum[DRAFT, EASY]
    solver: Enum[AUTO, EXACT, FAST]; voxel_fallback: Bool
    last_build_collection: Pointer(Collection); schema_version: Int
```

- Easy 모드 = 스택에 항목 1개 추가 후 즉시 Build하는 래퍼. 데이터 경로가 하나이므로 두 모드가 같은 코드를 탄다.
- 커넥터 위치는 시임 프레임(u,v)로 저장하므로 컷 평면을 움직여도 상대 위치가 유지된다.
- Build 결과 파트에는 `["snapsplit_source"]`, `["snapsplit_cut_ids"]` 커스텀 프로퍼티를 기록해 재빌드 시 교체·정리한다.

### 4.3 오퍼레이터 목록 (bl_idname)

| 그룹 | bl_idname | 설명 |
|---|---|---|
| 스택 | `snapsplit.stack_add_plane`, `stack_add_stroke`, `stack_add_polyline`, `stack_add_polygon` | 컷 추가(모달 입력 포함) |
| | `snapsplit.stack_remove`, `stack_move`, `stack_duplicate`, `stack_clear` | CRUD |
| | `snapsplit.cut_adjust_plane` | 평면 origin/normal 모달 조정(마우스/휠, X/Y/Z 스냅, Shift로 축 정렬) |
| | `snapsplit.build` | Draft 빌드(Build 파이프라인). `rebuild=True`면 기존 결과 교체 |
| | `snapsplit.easy_cut` | Easy 모드: 컷 1개 + 기본 커넥터 → 즉시 빌드 |
| 커넥터 | `snapsplit.connector_add_auto` (LINE/GRID), `connector_add_click`(모달, 클릭마다 `undo_push`), `connector_remove`, `connector_mirror_side` | |
| 검증/출력 | `snapsplit.validate`, `snapsplit.fix_transforms`, `snapsplit.fix_units`, `snapsplit.export_parts` (STL/OBJ/FBX, 파트별 파일) | |
| 레거시 | 기존 `planar_split`, `add_connectors`, `place_connectors_click`, `freehand_cut`, `align_faces`… | Phase 3까지 "Legacy" 서브패널에 유지 |

### 4.4 불리언 파이프라인 (`core/boolean.py`)

```
run_cut(part_mesh_obj, cutter_solid, side) -> Result(obj, ok, method, stats)
  1. 입력 전처리: 스케일/회전 적용(복사본), remove_doubles(1e-5 mm), normals outside
  2. PLANE 컷: bmesh.bisect_plane 2회(±gap/2) + cap  ← 불리언 없이 가장 견고·빠름
  3. 그 외: Boolean 모디파이어(DIFFERENCE, solver=EXACT, use_self=False) → apply_modifier_data
  4. 결과 검증: 면 수>0, 매니폴드, 부피 > 0, 부피 합 ≈ 원본 부피 − 갭 부피 (허용 5%)
  5. 실패 시 폴백 순서: EXACT(use_hole_tolerant) → FAST → 입력 voxel remesh(복셀 = bbox 대각/400, 사용자 조정) 후 EXACT → 오류 보고(파트 미생성, 원본 무손상)
  6. 각 단계는 progress.step()을 호출(대형 메시 피드백)
```

곡선 컷 커터(`cuts/stroke.py`): 스트로크 2D 점 → 뷰 레이를 따라 원본 bbox를 넘어 앞·뒤로 연장한 **리본(ruled surface)** → 리본을 법선 방향으로 `gap_mm`만큼 두께 부여 + 측면으로 bbox 밖까지 연장한 폐솔리드 `H_gap` → `H+` = 리본 한쪽 반공간 솔리드. A = 원본 − H+, B = 원본 − (H+ 의 여집합 + H_gap) 로 두 파트를 각각 **한 번의 DIFFERENCE**로 생성한다. 폴리라인/폴리곤 커터도 같은 "솔리드 커터 → 2회 DIFFERENCE" 규약을 따르므로 파이프라인은 하나다.

양면 도웰: 두 파트 모두 소켓 DIFFERENCE, 도웰 본체는 별도 파트 오브젝트(공차는 소켓에 적용)로 결과 컬렉션에 포함.

### 4.5 Undo 안전 전략

- 모든 오퍼레이터 `{'REGISTER','UNDO'}`. 모달 클릭 배치는 클릭마다 `bpy.ops.ed.undo_push(message=...)`.
- Build는 **원본을 절대 변경하지 않는다**(복사본에서 작업). 변환 적용도 복사본에만. 사용자가 원하면 `fix_transforms`를 명시 실행.
- depsgraph/draw 핸들러에서 데이터블록 생성·삭제 금지. 프리뷰는 gpu 오버레이(`SpaceView3D.draw_handler_add`)로만 그린다(평면 오브젝트 프리뷰 제거). 모달 중 데이터는 파이썬 객체에만 보관.
- 핸들러·드로우 핸들러는 `unregister`에서 반드시 제거(ops_freehand의 `_ACTIVE_OPERATORS` 패턴 유지).
- 재빌드 시 이전 결과 컬렉션을 통째로 교체(이름 재사용), 중간 오브젝트는 생성하지 않거나 즉시 제거.

### 4.6 UI 레이아웃 (N 패널 "SnapSplit")

1. **Validate** 박스: 매니폴드/변환/단위 상태 아이콘 + Fix 버튼.
2. **Mode**: Draft | Easy 토글.
3. **Cuts** (Draft): `UIList`(이름, 종류 아이콘, 활성 체크, 이동 ▲▼) + 추가 버튼 행(Plane/Stroke/Polyline/Polygon) + 선택 항목 속성(평면 조정, gap, cap).
4. **Connectors**(선택된 컷): `UIList` + 자동 배치(분포/개수/마진) + 클릭 배치 + 선택 커넥터 속성(타입, 크기, 회전, 핀 측, 클리어런스, 커스텀 메시, 양면).
5. **Build / Export**: Build, Rebuild, 결과 컬렉션 표시, Export(포맷·폴더).
6. **Settings**(접힘): 재질 프로필/공차, 솔버, voxel 폴백, 디버그 로그.
7. **Legacy**(접힘, Phase 3까지): 기존 패널 그대로.

### 4.7 테스트 하니스

- `tests/run_tests.py`(호스트, WSL/Windows 파이썬 3): 인자 `--blender <exe>…`(기본: 설치된 4.5·5.2 자동 탐색), `--case <glob>`. `snapsplit/`를 임시 extension repo로 복사 → `blender.exe -b --factory-startup --python tests/blender_runner.py -- --repo <winpath> --out <json>` 실행 → JSON 집계 → 요약 표 출력, 실패 시 exit 1.
- `tests/blender_runner.py`(Blender 내부): 확장 repo 등록(`preferences.extensions.repos.new` + `use_custom_directory=True` → `addon_enable("bl_ext.<repo>.snapsplit")`), `tests/cases/test_*.py` 동적 import, 각 `run(ctx)` 실행, 예외=FAIL, 케이스 간 `bpy.ops.wm.read_factory_settings(use_empty=True)`로 격리, 결과·시간·트레이스백을 JSON으로 기록.
- `tests/lib/`: `make_cube(size_mm)`, `make_monkey_manifold()`, `make_hollow_box()`, `is_manifold(obj)`, `volume(obj)`, `count_parts(collection)`, `assert_close`.
- 모달·마우스 입력은 headless 불가 → 스트로크 커터 생성은 **점 리스트를 받는 순수 함수**로 분리해 테스트하고, 모달 오퍼레이터는 GUI 수동 체크리스트로 검증.
- 성능 테스트: 50만 면 메시 케이스는 `--slow` 옵션으로만 실행, 시간 상한 기록.

## 5. 단계별 로드맵

| Phase | 목표 | 산출물 |
|---|---|---|
| 0 | 하니스 + 베이스라인 + 위생 | `tests/`, `.gitignore` 수정, `shadow_method` 가드, 디버그 print → logging, `develop` 브랜치 |
| 1 (MVP) | 평면 컷 스택 + Build + 핀/소켓 레코드 + Export | `core/`, `model/`, `cuts/plane.py`, `cuts/build.py`, `connectors/*`, `ops/`, 새 패널 |
| 2 | 곡선 컷(스트로크) + 불리언 폴백/진행률 | `cuts/stroke.py`, `core/boolean.py` 완성, `core/progress.py` |
| 3 | 커넥터 고도화(전 타입, 커스텀, 양면 도웰, 편집 gizmo) + 레거시 제거 | `connectors/*` 완성, legacy 삭제, 로컬라이즈 |
| 4 | Manual/Polygonal 컷, 검증 강화, 패키징·배포 | `cuts/polyline.py`, `cuts/polygon.py`, 4.2 호환 검증, 확장 zip |

세부 태스크·수락 기준은 `docs/CHECKLIST.md`.

## 6. 리스크

| 리스크 | 영향 | 대응 |
|---|---|---|
| EXACT 불리언이 얇은 벽/자기교차 메시에서 실패·느림 | 곡선 컷 실패 | voxel remesh 폴백, 부피 검증, 평면 컷은 bisect 유지 |
| 스트로크 리본 커터가 자기교차(급한 곡선·뷰 방향) | 비매니폴드 커터 | 스트로크 리샘플·스무딩, 커터 자체 매니폴드 검사 후 거부 메시지 |
| Blender 5.x API 변화(재질, `use_nodes`, 모디파이어 apply, gpu 셰이더) | 로드 실패 | `core/compat.py` 집중, 4.5+5.2 자동 테스트 상시 실행, 4.2는 CI 없이 수동 |
| 업스트림 freehand 브랜치 리베이스/변경 | 머지 충돌 | 새 모듈 격리(strangler), 동기화 주기 짧게 |
| 커넥터별 불리언이 O(N)으로 느림(51만 면·핀 3개 12.8s) | 대형 메시 UX | 핀/소켓을 한 컷당 1회 UNION/DIFFERENCE로 묶기(커터 join), 진행률 표시 |
| 모달 클릭 배치의 undo 불명확 | 사용자 혼란 | 클릭마다 `undo_push`, 테스트로 undo 횟수 검증(GUI 수동) |
| 단위: cm/imperial/scale_length≠1 씬에서 치수 오류 | 출력물 치수 불량 | `core/units.py` + 검증 패널에서 mm 권장 및 자동 전환 |
| 한 번에 레거시를 대체하려다 회귀 | 기능 손실 | 레거시 패널 유지, 동등성 테스트 통과 후 삭제 |

## 7. 사용자 결정 필요 사항

1. 베이스 브랜치: 제안대로 `upstream/V_0.2.0_freehand`에서 `develop` 분기 승인 여부(대안: master + 필요 시 cherry-pick).
2. 제품 식별자: `id="snapsplit"` 유지(업스트림과 extension ID 충돌 가능) vs 포크용 새 id/이름. 바꾸면 `bl_idname` 접두어·번역 사전 키도 영향.
3. 최소 지원 버전: manifest 4.2 유지하되 자동 검증은 4.4/4.5/5.2만 할지, 4.2 LTS를 설치해 검증 대상에 넣을지.
4. 레거시 오퍼레이터 공개 유지 기간(Phase 3까지 vs MVP 이후 즉시 숨김).
5. 곡선 컷 방식: 뷰 투영 리본(제안, 스트로크 1회) vs 표면 투영 경로 + 법선 오프셋(표면을 따라가지만 구현 난도↑). Phase 2 착수 전 확정.
6. 양면 도웰의 도웰 본체를 결과 컬렉션에 "출력용 파트"로 포함할지, 규격 시판 도웰(예: Ø3mm 핀) 가정으로 소켓만 만들지.
