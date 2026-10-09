# 구현 체크리스트 (검증자용)

규칙
- 각 항목은 독립적으로 체크 가능해야 한다. "검증" 줄의 명령을 그대로 실행하고 기대 출력과 비교한다.
- 공통 명령: `BL45="/mnt/c/Program Files/Blender Foundation/Blender 4.5/blender.exe"`, `BL52="/mnt/c/Program Files/Blender Foundation/Blender 5.2/blender.exe"`. 테스트 실행은 `python3 tests/run_tests.py`(기본으로 두 버전 모두 실행, 모두 통과 시 exit 0).
- "GUI" 표시 항목은 headless 불가 → 사람이 Blender를 열어 확인하고 결과를 메모한다.
- 각 Phase는 이전 Phase의 모든 자동 테스트가 계속 통과해야 완료다(회귀 금지).

---

## Phase 0 — 테스트 하니스 + 베이스라인 + 위생

- [x] **P0-1 브랜치 준비**: `develop`을 `upstream/V_0.2.0_freehand`에서 생성.
  검증: `git branch --contains upstream/V_0.2.0_freehand | grep develop` 출력 있음. `git merge-base --is-ancestor master develop && echo ok` → `ok`.
- [x] **P0-2 .gitignore 수정**: `snapsplit/ops_split.py`, `/Tests/` 항목 제거(필요 시 `/Tests/`→`/tests/fixtures/*.blend1` 등으로 교체).
  검증: `git check-ignore -v tests/run_tests.py snapsplit/ops_split.py`의 exit code가 1(무시 안 됨).
- [x] **P0-3 하니스 골격**: `tests/run_tests.py`, `tests/blender_runner.py`, `tests/lib/__init__.py`, `tests/cases/test_register.py`(등록→해제→재등록, `SNAPSPLIT_OT_planar_split`·`SNAPSPLIT_OT_freehand_cut` 존재, `scene.snapsplit` 존재).
  검증: `python3 tests/run_tests.py --case test_register` → 두 버전 모두 `PASS`, exit 0. `python3 tests/run_tests.py --case test_register --blender "$BL52"`로 단일 버전 실행 가능.
- [x] **P0-4 실패가 실패로 보임**: 일부러 `assert False`인 케이스를 추가해 exit 1·트레이스백 출력 확인 후 제거.
  검증: 임시 케이스 실행 시 종료코드 1, JSON 결과에 `"status":"FAIL"`과 `traceback` 키.
- [x] **P0-5 베이스라인 케이스**: `test_legacy_split_cube.py`(Z 2분할, 파트 2, 매니폴드, 원본 존재), `test_legacy_split_monkey.py`(구멍 메운 Suzanne, 캡 포함 매니폴드), `test_legacy_connectors.py`(CYL_PIN 3개 후 매니폴드), `test_units.py`(mm 씬에서 `unit_mm()==1.0`).
  검증: `python3 tests/run_tests.py` → 4.5/5.2 모두 전체 PASS.
- [x] **P0-6 프리뷰 재질 버그 수정**: `build_orange_preview_material`에서 `shadow_method`·`blend_method`를 `hasattr` 가드. 케이스 `test_preview_material.py`(함수 호출 시 예외 없음, 재질 반환).
  검증: 케이스 PASS 4.5/5.2. GUI: "Show split preview" 켜면 주황 평면이 보임(4.5, 5.2 각각 메모).
- [x] **P0-7 로깅**: `snapsplit/core/log.py` 추가, `print("[SnapSplit DEBUG]…")` 전부 `log.debug`로 치환. 프리퍼런스 `debug_log` Bool(기본 False).
  검증: `grep -rn "SnapSplit DEBUG" snapsplit/ | wc -l` → `0`. 기본 설정으로 P0-5 실행 시 stdout에 `DEBUG` 문자열 없음(`python3 tests/run_tests.py --case test_legacy_split_monkey | grep -c DEBUG` → `0`).
- [x] **P0-8 수동 검증 체크리스트 문서**: `docs/MANUAL_QA.md`에 GUI 전용 항목(모달 조정, 클릭 배치, freehand 스트로크) 절차 작성.
  검증: 파일 존재, 각 항목에 "절차/기대 결과" 두 줄 이상.
- [x] **P0-9 느린 테스트 옵션**: `--slow` 시 51만 면 Suzanne 3분할 + 핀 3개 케이스 실행, 시간 로그.
  검증: `python3 tests/run_tests.py --slow --case test_perf_large --blender "$BL52"` PASS, 출력에 `split_s=`·`connectors_s=` 수치.

## Phase 1 — MVP: 평면 컷 스택 + Build + 핀/소켓 + Export

식별자(2026-10-09 사용자 결정, PLAN 상단): 새 타입·오퍼레이터는 `SPLITFORGE_*` / `splitforge.*`, 스택 `Object.splitforge_stack`,
전역 설정 `Scene.splitforge`, 파트 프로퍼티 `["splitforge_source"]`·`["splitforge_cut_ids"]`, 결과 컬렉션 `SplitForge_Build_<obj>`,
패키지 폴더 `splitforge/`(이름은 `splitforge/core/naming.py`에 중앙화). 레거시 `snapsplit.*`·`Scene.snapsplit`는 유지.

- [x] **P1-1 core/units.py**: `mm_to_scene`/`scene_to_mm`가 Blender 표시 규약을 따른다: **1 BU = `scale_length` m**
  (`length_unit`은 표시만 바꿈). 애드온의 mm 값은 항상 Blender가 mm로 보여 주는 값과 같다(2026-10-09 사용자 결정).
  검증: `test_units.py` — mm 단위 +Unit Scale 0.001 → mm당 1.0 BU(표준 3D 프린트 설정), m+0.001 1.0, m+1.0 0.001,
  mm+1.0 0.001(Blender가 40 BU를 40000 mm로 표시), cm+0.01 0.1, inch+0.0254 1/25.4, ADAPTIVE/NONE 0.001 (허용 1e-9),
  각 설정에서 Blender 자체 변환(`bpy.utils.units.to_value("25 mm") / scale_length`)과 일치. PASS.
  결과(2026-10-09, fix/p1-followups): PASS 4.5/5.2. `scale_length`는 float32라 7자리 유효숫자로 반올림. 모든 테스트 씬은
  표준 설정(Millimeters + Unit Scale 0.001, 40 BU = 40 mm 큐브). (feat/p1-mvp2의 "1 BU = length_unit × scale_length" 규약은 폐기)
- [x] **P1-2 core/validate.py**: `validate(obj) -> ValidationReport(manifold, loose_geom, transform_applied, unit_is_mm, mm_per_unit, messages)`.
  검증: `test_validate.py` — 큐브 OK; 면 하나 삭제한 큐브 `manifold=False`; scale 2 큐브 `transform_applied=False`; m 씬(Unit Scale 1) `unit_is_mm=False`, `mm_per_unit=1000`과 메시지. PASS.
  패널은 항상 실제 "1 unit = … mm"를 표시.
  결과: PASS 4.5/5.2(+ 느슨한 정점 `loose_geom`, 위치만 이동한 큐브는 transform OK, 비메시 오브젝트).
- [x] **P1-3 model/props.py**: `SPLITFORGE_PG_Connector`, `SPLITFORGE_PG_Cut`, `SPLITFORGE_PG_CutStack`(+ `SPLITFORGE_PG_Settings`) 등록, `Object.splitforge_stack`.
  검증: `test_model.py` — 큐브에 컷 2개·커넥터 3개 추가 → `.blend` 저장 → `wm.open_mainfile` 후 값 동일. 등록/해제 반복 3회 예외 없음. PASS.
  결과: PASS 4.5/5.2. 이름은 `SPLITFORGE_PG_*`. P1에서 쓰지 않는 필드(`scale`, `custom_object`, `double_sided`, `points`, `target_part`, `seam_cache`, `kind`의 STROKE 등)는 아직 없음 — 해당 Phase(2·3)에서 추가(빈 필드를 미리 두지 않음).
- [x] **P1-4 스택 오퍼레이터**: `stack_add_plane`, `stack_remove`, `stack_move`, `stack_duplicate`, `stack_clear`, `cut_adjust_plane`(모달, headless는 execute 경로로 origin/normal 직접 지정).
  검증: `test_stack_ops.py` — add 3회 → len 3; move(1→0) 순서 반영; remove → 2; clear → 0. 각 호출 후 `bpy.ops.ed.undo()`로 되돌리면 직전 상태(undo 스택 동작, headless에서 `undo_push` 사용). PASS.
  결과: PASS 4.5/5.2(`test_stack_ops`: add 3·move·duplicate·remove·clear 각각 undo/redo, `cut_adjust_plane` execute 경로; `test_cut_adjust_modal`: 모달 휠/X/Esc/확정, undo 후 live 데이터 기록, 구조체 캐시 없음). 실제 Ctrl+Z는 GUI `p1_adjust_plane`·`p1_panel` PASS.
- [x] **P1-5 cuts/plane.py + core/meshlib.py**: 임의 origin/normal 평면 bisect(±gap/2) + 캡(기존 `cap_single_object_hollow_style` 이관, 축 의존 제거 → 컷 법선 사용).
  검증: `test_plane_cut.py` — 큐브 40mm, 법선 (1,1,0) 정규화 평면, gap 0.4mm → 두 파트 매니폴드, 부피 합 = 원본 − 갭 부피(허용 2%); 중공 박스(벽 2mm)도 두 파트 매니폴드, 캡이 링 형태(면 수 > 단순 n-gon 2개). PASS.
  결과: PASS 4.5/5.2. 기존 레거시 캡 함수를 옮기는 대신 WIP의 bmesh 전용 `cap_plane`을 검토 후 사용 + 면 winding으로 외곽/구멍 판정(겹친 별도 셸 Suzanne 눈이 구멍으로 처리돼 부피 4% 손실하던 버그를 `test_build_monkey`가 잡음).
- [x] **P1-6 cuts/build.py + `splitforge.build`**: 원본 복사 → 활성 컷 순차 적용 → 결과 컬렉션 `SplitForge_Build_<obj>`(재빌드 시 교체) → 원본 `hide_set(True)`만, 데이터 불변.
  검증: `test_build.py` — 컷 2개(Z, X) 빌드 → 파트 4개, 전부 매니폴드; 원본 메시 해시(정점 좌표 sha256) 빌드 전후 동일; 컷 1개 `enabled=False` 후 재빌드 → 파트 2개, 컬렉션 수 증가 없음; 각 파트 `["splitforge_source"]==원본 이름`. PASS.
  결과: PASS 4.5/5.2(+ 회전·비균일 스케일·모디파이어 원본, 결과 컬렉션 제외 후 재빌드, 원본 이름 변경, 원본 복제, Edit 모드 poll, clear_build).
- [x] **P1-7 Easy 모드**: `splitforge.easy_cut(axis, offset_mm)` → 스택 1개 + 즉시 빌드.
  검증: `test_easy.py` — 큐브에 호출 → 파트 2개, `obj.snapsplit_stack.cuts` len 1. PASS.
  결과: PASS 4.5/5.2(기본 커넥터 2개, 커넥터 0개, 오브젝트 밖 컷은 흔적 없이 실패, 패널 invoke는 Easy 설정 사용). Easy 컷을 반복하면 스택에 누적되어 전체가 다시 빌드됨(의도된 동작으로 둠).
- [x] **P1-8 connectors/placement.py**: 시임 프레임(origin, normal, tangent) + (u,v,rot) → 월드 행렬. 단일 함수가 자동/클릭/프리뷰 모두에 쓰임.
  검증: `test_placement.py` — 단위 프레임에서 (u=5,v=0) → 월드 x=5; 프레임 회전 90° → 대응 좌표. 자동 LINE 3개·margin 10% 위치가 시임 폭 내부. PASS. `grep -rn "def distribute_points" splitforge/connectors | wc -l` → `1`.
  결과: PASS 4.5/5.2. 자동 배치는 **시임 영역별**: 다른 컷이 시임을 나누면 영역마다 count개(다른 컷 평면 위에 커넥터가 놓이던 문제를 GUI에서 발견해 수정).
  추가(fix/p1-followups, 결함 D1): 자동 배치는 시임 영역을 커넥터 도달 거리(반경+클리어런스+벽 0.4 mm)만큼 줄이고, 핀·소켓 전체(컷 법선 방향 깊이 포함, 핀 쪽 A/B 모두)를 원본 안에서 3D 검사해 안쪽으로 옮기거나 버리며 경고한다; Build는 표면을 뚫는 커넥터를 경고와 함께 건너뛴다. 검증: `test_connectors_fit.py` — 경사 컷(원점 (3,0,0), 법선 (1,0.6,0.35), gap 0.5) 커넥터 전부 벽 0.4 mm 이상, 빌드 경고 0, 파트 정점이 원본 큐브 밖 0, 가장자리 수동 커넥터는 건너뜀+경고, 옮긴 커넥터끼리 간격 유지. PASS 4.5/5.2.
  추가(fix/d7-crosscut, 결함 D7): 핀·소켓 전체가 다른 모든 활성 컷 평면의 자기 쪽(그 컷의 갭/2 + 벽 0.4 mm 너머)에 남아야 한다 — 세 번째 파트로 넘어가 조립 시 충돌하던 문제. Distribute는 옮기거나 버리고 보고, Build는 경고와 함께 건너뜀. 내부 판정은 최근접 면 법선 + 광선 홀짝(불일치 시 3방향 다수결), 샘플 간 선분이 표면을 지나면 관통(샘플 간격보다 얇은 특징). 검증: `test_connectors_crosscut.py`(가파른 경사 컷 재현: 커넥터 전부 다른 컷까지 여유 ≥ 0.4 mm, 빌드 경고 0, 어떤 파트의 정점도 다른 파트 안에 없음, 다른 컷을 넘는 수동 커넥터는 건너뜀+경고, 간격 규칙: 8개 요청 시 소켓 간 ≥ 0.4 mm), `test_connectors_fit.py`(0.3 mm 내부 공동 관통 금지, 칼날 모서리 바깥 점 판정), `test_plane_cut.py`(건드리지 않은 내부 공동의 법선 유지 — 캡 후 전체 법선 재계산이 공동을 부피로 뒤집던 버그). 뮤테이션 6건 모두 검출. PASS 4.5/5.2.
  독립 검증(2026-10-09, verifier, develop fafaed4): `--gui` 10시나리오 ×2 PASS, 헤드리스 25/25 ×2 PASS, `--slow` PASS(5.2: split 5.03 s, connectors 14.33 s, build 9.56 s), 뮤테이션(fit 무력화·Build 건너뛰기 제거·3D fit 제거·단위 스케일·float32 반올림·옛 규약·export/FBX 스케일) 검출, inset 제거·간격 규칙 제거는 미검출(3D fit이 대신 잡음/간격 테스트 약함). 라이브 5.2 PASS. 열린 결함 D7: 다른 컷을 넘어 세 번째 파트로 핀 관입(가파른 경사 컷), MANUAL_QA 참고.
  D7 독립 검증(2026-10-09, verifier, develop ff7ecdb): `--gui` 10시나리오 ×2 PASS, 헤드리스 26/26 ×2 PASS, `--slow` PASS(5.2: split 4.64 s, connectors 13.48 s, build 10.31 s). 뮤테이션 7건 중 6건 검출(평면 검사 끔·Build에 평면 미전달·inside 판정 단순화·관통 세그먼트 검사 끔·법선 전체 재계산·간격 규칙 제거), Build `max_step` 미전달은 미검출. 적대 케이스(컷 3개·중공·L자·슬롯) 관입 0. 라이브 5.2 PASS. D7 해결. 열린 항목 D8(중공 벽 자동 배치 0개, 중간~낮음).
- [x] **P1-9 connectors/apply.py (핀/소켓)**: CYL_PIN·RECT_TENON에 대해 핀 UNION(pin_side 파트), 소켓 DIFFERENCE(반대 파트, 반경+클리어런스, 깊이+클리어런스). 컷당 커넥터 N개를 커터 join 후 **파트당 불리언 1회**.
  검증: `test_connectors_build.py` — 큐브 Z컷 + CYL_PIN 3개 빌드 → 양 파트 매니폴드, 핀 파트 부피 > 반쪽 부피, 소켓 파트 부피 < 반쪽 부피; `pin_side` 바꾸면 반대. 클리어런스 0.3mm 시 소켓 지름 = 핀 지름+0.6 (단면 bbox로 측정, 허용 0.02mm). PASS.
  결과: PASS 4.5/5.2(소켓 지름 5.6±0.02, 깊이 5.3, RECT_TENON 6.5×4.5, gap 1 mm, 겹친 커넥터, 불리언 호출 수 = 파트당 UNION 1·DIFFERENCE 1).
- [x] **P1-10 연속 컷 + 커넥터**: 컷 2개 모두 커넥터 2개씩 → 빌드.
  검증: `test_build_multi.py` — 파트 4개 전부 매니폴드, 재빌드 2회 반복 후 `bpy.data.objects` 수 동일(누수 없음), `bpy.data.meshes` 중 고아(users==0) 0개. PASS.
  결과: PASS 4.5/5.2. 커넥터 8개 모두 적용됐는지 부피 합으로 검증(이전 버전은 건너뛴 커넥터를 놓쳤음).
- [x] **P1-11 Export**: `splitforge.export_parts(directory, formats={STL,OBJ,FBX}, apply_scale_mm=True)`.
  검증: `test_export.py` — 파트 2개 빌드 후 임시 폴더로 STL+OBJ 내보내기 → 파일 4개 존재, 각 >1KB; STL 재임포트 시 면 수 동일. PASS (4.5/5.2 모두; 5.x에서 OBJ/STL 오퍼레이터 ID 차이 `compat.py`로 흡수).
  결과: PASS 4.5/5.2(+ FBX를 미터 씬에 임포트해 실제 단위 확인, cm 씬→mm STL, 숨긴 파트 제외, 저장 안 된 파일의 상대 경로 거부).
- [x] **P1-12 UI 패널(Draft/Easy, Cuts UIList, Connectors UIList, Build/Export)**.
  검증: `test_ui_draw.py` — `bpy.types.SPLITFORGE_PT_main.draw`(+ 서브패널, 레거시 `SNAP_PT_panel`)를 `temp_override`로 호출(dummy layout) 예외 없음. GUI: 패널에 컷 추가/삭제/활성 토글/Build/Export 조작 가능, 스크린샷 `docs/qa/p1_panel_<ver>.png`.
  결과: `test_ui_draw` PASS 4.5/5.2. GUI: `python3 tests/run_tests.py --gui`의 `p1_panel`(실제 버튼 클릭)·`p1_adjust_plane` PASS 4.5/5.2. 스크린샷 [4.5](qa/p1_panel_4.5.png) [5.2](qa/p1_panel_5.2.png), 모달 [4.5](qa/p1_adjust_plane_4.5.png) [5.2](qa/p1_adjust_plane_5.2.png).
- [x] **P1-13 회귀**: 레거시 케이스(P0-5) 포함 전체 PASS, 두 버전.
  검증: `python3 tests/run_tests.py` exit 0.
  독립 검증(2026-10-09, verifier, develop e148026): 헤드리스 24/24 ×2회 PASS(4.5.5/5.2.2), `--gui` 10시나리오 ×2버전 PASS, `--slow test_perf_large` PASS(5.2: split 4.54 s, connectors 12.97 s, build 9.16 s), 뮤테이션 13건 전부 테스트가 검출, `extension validate` 성공, 라이브 5.2 MCP PASS(MANUAL_QA "P1 라이브 검증"). 열린 결함: 경사 컷 자동 커넥터가 외곽 관통(P1-8 범위 밖, 중간) → fix/p1-followups에서 수정(아래 P1-8 추가 기준).
  결과: 헤드리스 24/24 PASS ×2회(4.5/5.2), `--gui` 10개 시나리오 PASS(4.5/5.2), `--slow --case test_perf_large` PASS(5.2: split 4.87 s, connectors 14.11 s, 새 Build 9.27 s).

## Phase 2 — 곡선 컷 + 불리언 폴백 + 진행률

- [ ] **P2-1 core/boolean.py**: `run_boolean(target, cutter, op, solver='AUTO')` — EXACT→FAST→voxel remesh→실패 보고, 결과 검증(면>0, 매니폴드, 부피 양수).
  검증: `test_boolean.py` — 큐브−구 DIFFERENCE 매니폴드; 의도적 비매니폴드 커터(면 하나 제거) → `result.method in {FAST, VOXEL}` 또는 `ok=False`와 메시지, 원본 불변; 폴백 시 로그에 `fallback=` 기록. PASS.
- [ ] **P2-2 cuts/stroke.py 순수 함수**: `build_stroke_cutter(points_2d, region, rv3d, bbox, gap_mm) -> (H_plus_mesh, H_gap_mesh)`; headless는 합성 `region_data`(view matrix, 직교) 로 호출.
  검증: `test_stroke_cutter.py` — 직교 Front 뷰에서 S자 점 30개 → 두 커터 메시 매니폴드, 부피 > 0, 커터 bbox가 원본 bbox 포함. 점 2개(직선) 입력은 평면 컷 결과와 부피 오차 1% 이내. PASS.
- [ ] **P2-3 곡선 컷 빌드 통합**: `kind=STROKE` 컷이 build에서 2회 DIFFERENCE로 파트 2개 생성, gap 반영.
  검증: `test_stroke_build.py` — 큐브에 S자 컷 → 파트 2개 매니폴드, 부피 합 = 원본 − 갭(허용 5%), 두 파트 bbox가 서로 겹치지 않음(갭 축 기준). Suzanne(매니폴드)도 PASS.
- [ ] **P2-4 스트로크 모달 오퍼레이터** `stack_add_stroke`(ops_freehand의 입력·gpu 드로잉 발췌, 점은 `SNAP_PG_Cut.points`에 저장, 커터는 숨김 컬렉션 오브젝트로 생성).
  검증: GUI(4.5, 5.2) — 그리기→Enter → 스택에 STROKE 항목, 커터 오브젝트 `_SnapSplit_Cutters`에 존재, Build 시 두 파트. Esc 취소 시 오브젝트·핸들러 잔존 없음(`bpy.data.objects` 수 동일). `docs/qa/p2_stroke_<ver>.png`.
- [ ] **P2-5 곡선 시임 위 커넥터**: 스트로크 컷의 시임 프레임을 커터 리본의 중앙 점·법선으로 정의, 커넥터 (u,v)는 리본 파라미터(길이 방향 u, 깊이 방향 v).
  검증: `test_stroke_connectors.py` — S자 컷 + CYL_PIN 2개 → 매니폴드, 핀 파트 부피 증가, 핀 축이 리본 로컬 법선과 평행(각도 < 2°). PASS.
- [ ] **P2-6 진행률**: `core/progress.py` — `wm.progress_*` + 상태바 텍스트; Build는 단계 수를 미리 계산해 `step()`.
  검증: `test_progress.py` — 빌드 중 progress 콜백 호출 횟수 == 예상 단계 수(컷 수×2 + 커넥터 그룹 수). GUI: 51만 면 메시 빌드 시 커서 진행률·상태바 텍스트 보임.
- [ ] **P2-7 대형 메시 성능**: `--slow` 케이스에 51만 면 S자 컷 추가, 상한 120s(5.2).
  검증: `python3 tests/run_tests.py --slow --blender "$BL52"` PASS, 시간 기록.

## Phase 3 — 커넥터 고도화 + 레거시 제거

- [ ] **P3-1 전 타입 지원**: DOVETAIL, SNAP_PIN, SNAP_TENON, SNAP_DOVETAIL, CUSTOM을 `connectors/shapes.py`로 이관, 새 apply 경로에서 생성.
  검증: `test_connector_types.py` — 타입별 1개씩 큐브 Z컷 빌드 → 매니폴드, 타입별 핀 파트 부피 > 소켓 파트 부피. PASS.
- [ ] **P3-2 커스텀 메시 커넥터**: `custom_object` 지정, 폭/길이/깊이 스케일.
  검증: 같은 케이스에 사용자 원기둥 메시 → 매니폴드. 비매니폴드 커스텀 메시는 `ok=False` + 경고 메시지(`report` 캡처). PASS.
- [ ] **P3-3 양면 도웰**: `kind=DOWEL`, `double_sided=True` → 두 파트 소켓 + 도웰 파트 오브젝트.
  검증: `test_dowel.py` — 파트 3개(A, B, Dowel_1), 두 파트 부피 모두 반쪽보다 작음, 도웰 길이 = 2×length_mm (bbox 허용 0.05mm). PASS.
- [ ] **P3-4 커넥터별 편집**: 위치(u,v)/회전/스케일/폭/높이/pin_side/clearance 변경 후 Rebuild 반영.
  검증: `test_connector_edit.py` — u를 +10mm 이동 후 재빌드 → 핀 중심 bbox가 10mm 이동(허용 0.1mm); rotation 90° → 사각 테논 bbox 가로세로 교환. PASS.
- [ ] **P3-5 클릭 배치 모달** `connector_add_click`(클릭마다 `undo_push`, S키 pin_side 토글, 프리뷰는 gpu 오버레이).
  검증: GUI — 3회 클릭 후 Ctrl+Z 3회로 하나씩 제거됨. 프리뷰 오브젝트 생성 없음(`_SnapSplit_Preview` 컬렉션 없음).
- [ ] **P3-6 레거시 제거**: `ops_split.py`, `ops_connectors.py`, `ops_freehand.py`, `seam_data.py` 삭제(또는 `legacy/`로 이동 후 미등록), 캡핑·지오메트리 함수는 새 모듈에 남김.
  검증: `grep -rn "from . import ops_split\|ops_connectors\|ops_freehand" snapsplit/__init__.py | wc -l` → `0`. 전체 테스트 PASS(레거시 케이스는 새 오퍼레이터 대응 버전으로 교체). `wc -l snapsplit/**/*.py` 합계가 Phase 1 시작 시점보다 작음.
- [ ] **P3-7 로컬라이즈**: 새 UI 문자열을 `localization.py`에 최소 en/de/ko 추가.
  검증: `test_i18n.py` — 새 패널 라벨 키가 사전 `ko_KR`에 존재, 등록 시 "locales unknown" 경고 없음.

## Phase 4 — Manual/Polygonal 컷, 검증 강화, 패키징

- [ ] **P4-1 폴리라인 컷** `cuts/polyline.py` + `stack_add_polyline`(뷰포트 클릭 점 → 리본 커터, 2-2와 동일 규약).
  검증: `test_polyline_cutter.py` — 점 4개 → 커터 매니폴드, 빌드 파트 2개 매니폴드. PASS. GUI 절차 `docs/MANUAL_QA.md` 갱신.
- [ ] **P4-2 폴리곤 영역 제거** `cuts/polygon.py`(폐다각형 → 프리즘 커터, 영역 안을 별도 파트로 분리).
  검증: `test_polygon_cut.py` — 큐브 윗면에 사각형 영역 → 파트 2개(본체, 영역 조각), 부피 합 = 원본(허용 2%), 매니폴드. PASS.
- [ ] **P4-3 검증 패널 + Fix**: `validate`/`fix_transforms`/`fix_units` 오퍼레이터, 패널 상단 상태 아이콘.
  검증: `test_validate_ops.py` — scale 2 큐브에 `fix_transforms` → scale (1,1,1), 치수 동일; m 씬에 `fix_units` → `length_unit=='MILLIMETERS'`, `scale_length==0.001`. PASS.
- [ ] **P4-4 compat 검증 매트릭스**: 4.4·4.5·5.2에서 전체 테스트, (가능하면) 4.2 LTS 설치 후 실행.
  검증: `python3 tests/run_tests.py --blender "$BL44" --blender "$BL45" --blender "$BL52"` exit 0. 결과 표를 `docs/COMPAT.md`에 기록.
- [ ] **P4-5 패키징**: `blender_manifest.toml` 버전 0.3.0, `blender --command extension build` 성공, zip 설치 테스트.
  검증: `"$BL52" --command extension build --source-dir snapsplit --output-dir dist` → `dist/snapsplit-0.3.0.zip` 생성; `"$BL52" --command extension validate snapsplit` 경고 0. headless에서 zip을 `package_install_files`로 설치 후 `test_register` PASS.
- [ ] **P4-6 문서**: README(한/영) 사용법·스크린샷·제한사항, CHANGELOG.
  검증: README에 Draft/Easy, 컷 4종, 커넥터, Export, 검증 섹션 존재(`grep -c "^## " README.md` ≥ 6).
