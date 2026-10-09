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

곡선 컷 방식(PLAN 7-5, 2026-10-09 사용자 결정): **뷰 투영 리본** — 그린 2D 스트로크를 뷰 방향으로 압출한 곡면(쿠키 커터,
컷 면이 뷰 방향과 평행). 컷 레코드에는 뷰와 무관한 형태(오브젝트 로컬 폴리라인 + 압출 방향)로 저장해 Build가 뷰포트 없이 재현한다.
컷이 지나가지 않는 별도 셸(Suzanne 눈)은 자기 쪽 파트에 통째로 들어가고 정보 메시지를 낸다(평면 컷과 동일, freehand의 거부 없음).

- [x] **P2-1 core/boolean.py**: `apply(target, operand_bm, op, preference)` / `apply_bm(bm, …)` — EXACT → EXACT(자기교차) → MANIFOLD(4.5+) →
  FAST/FLOAT → 복셀 리메시(대각/200) 후 EXACT(자기교차), 결과 검증(면>0, 매니폴드, 연산별 부피 범위: UNION은 증가 ≤ 피연산자 부피,
  DIFFERENCE는 감소 ≤ 피연산자 부피, INTERSECT ≤ 입력, 호출자 `expect` 범위), 전부 실패 시 대상 불변 + 시도별 이유.
  곡선 컷은 추가로 **쌍 검증**(A + B + 갭 부피 = 조각 ± 4 %, 갭 부피 = 갭 × 양쪽 시임 면적/2)이 맞지 않으면 다음 솔버로 둘 다 다시.
  검증: `test_boolean.py` — 큐브−구 EXACT 매니폴드·제거 부피; 열린(비매니폴드) 커터는 어느 솔버가 처리하거나 `ok=False`+메시지·대상 불변;
  `_evaluate` 실패 주입으로 체인 순서(EXACT→EXACT_SELF→MANIFOLD→float→VOXEL), 로그 `fallback=`, 전부 실패 시 메시지·대상 불변,
  부피 손실 결과 거부, bmesh 경로에 임시 데이터 0, Suzanne에서 EXACT 빈 결과 → EXACT_SELF 성공. PASS 4.5/5.2.
  **원인 규명(이전 "큰 Suzanne 중간 파트에서 EXACT 부피 손실 → MANIFOLD 폴백")**: 구멍 메운 Suzanne의 눈 셸 2개가 머리 셸과 교차한다
  (51만 면에서 삼각형 쌍 780개 겹침, 겹친 부피 1.2–1.7 %). EXACT를 `use_self=False`로 쓰면 자기교차 입력에서 빈/잘못된 메시를 낸다
  (실측: 504면·51만 면 모두 DIFFERENCE 결과 면 0). `use_self=True`면 정확하다(눈/머리 겹침을 합친 부피). Build는 소스 셸끼리 교차하면
  체인을 EXACT_SELF부터 시작한다.
- [x] **P2-2 cuts/stroke.py 순수 함수**: `prepare_points`(투영·중복 제거·등간격 리샘플·라플라시안 스무딩), `build_cutter(points, direction, corners, gap)
  -> StrokeCutter`(`remove_for_a/remove_for_b/positive_solid/slab/ribbon`), `Centerline`(시임 프레임), `points_from_view(region, rv3d, …)`.
  (체크리스트 원안의 `build_stroke_cutter(points_2d, region, rv3d, …)` 대신 뷰 의존 부분을 `points_from_view`로 분리 — 저장·재빌드가 뷰와 무관.)
  검증: `test_stroke_cutter.py` — 합성 직교 Front 뷰(`tests/lib FakeView`)에서 S자 30점 → 4개 솔리드 매니폴드·부피>0·깊이 범위가 원본 포함,
  두 제거 솔리드 합집합 bbox ⊇ 원본, 제거 솔리드 부피 합 = 커터 상자 + 슬랩(1e-6), 슬랩 = 갭×길이×깊이(1 %), 점 2개는 평면 리본(1e-5),
  축 스냅, 거부 메시지 5종(짧음, 자기교차, 연장선 교차, 갭보다 급한 굽힘, 갭보다 가까이 되돌아옴). PASS 4.5/5.2.
  "점 2개 = 평면 컷 부피 1 % 이내"는 Build 수준에서 확인(`test_stroke_build`).
- [x] **P2-3 곡선 컷 빌드 통합**: `kind=STROKE` 컷은 조각마다 DIFFERENCE 2회(리본이 닿는 조각만, 아닌 조각은 통째로 자기 쪽), gap 반영, Easy 포함.
  검증: `test_stroke_build.py` — 큐브 S자(gap 0.5) → 매니폴드 2파트, 부피 합 = 64000 − 갭 부피(1 % 이내, 실측 0.02 %), A가 양(+n) 쪽,
  파트끼리 관입 없음 + 최소 거리 ≥ 0.9×갭(체크리스트 원안의 "bbox 겹치지 않음"은 S자 컷에서 성립하지 않아 이것으로 대체), 원본 해시 불변,
  재빌드 누수 0; 점 2개 스트로크 = 같은 평면 컷(파트별 부피 1 %); Suzanne(눈 교차) 주둥이 컷 → 2파트 매니폴드·"2 separate shell(s)" 정보·
  부피 합 = 원본 − 겹침(4 % 이내), 눈을 지나는 컷은 눈도 자름; 평면+스트로크 4파트; 비활성 스트로크로 재빌드; 저장된 자기교차 스트로크는
  Build 오류 메시지·변경 없음; 오브젝트를 비껴가는 스트로크는 추가 거부; 복제가 점·방향 복사; Easy 스트로크(갭+커넥터) 한 번에. PASS 4.5/5.2.
- [x] **P2-4 스트로크 모달 오퍼레이터** `splitforge.stack_add_stroke`(새 코드, freehand의 입력/드로잉 방식만 참고): LMB 그리기, Shift 릴리스 = 축 직선,
  Enter/Space 확정, LMB 다시 그리기, Esc/RMB 취소, 그리기 사이 뷰 이동 통과, gpu 프리뷰(스트로크 + 리본, 평범한 데이터만), `replace_uid`로 다시 그리기,
  `easy`로 Easy. 점은 `Cut.points`(로컬)·`Cut.direction`에 저장. (원안의 "숨김 컬렉션 커터 오브젝트"는 만들지 않는다 — 커터는 Build 때 레코드에서 생성.)
  검증: `test_stroke_modal.py`(헤드리스 스탠드인: 이벤트 사이 bpy 구조체 보관 없음, ed.undo 후 확정, Esc/RMB 흔적 없음·핸들러 제거, Shift 스냅,
  잘못된 스트로크 Enter 거부+이유, 다시 그리기 uid·커넥터 유지, 오브젝트 사라짐/`cancel()` 정리) PASS; GUI `p2_stroke` — 아래 MANUAL_QA QA-7.
- [x] **P2-5 곡선 시임 위 커넥터**: (u, v) = 리본 펼침 좌표(u 호 길이, 스트로크 중앙 0; v 압출 방향 깊이), 핀 축 = 리본 국소 법선(t × d).
  Distribute는 펼친 리본을 래스터 샘플링(소스 안, 다른 컷 갭 밖, 다른 컷 쪽별로 영역)해 루프를 만들고 기존 분배·3D 검사를 쓴다.
  fit 일반화: 다른 컷 = 장벽(`PlaneBarrier` 무한 평면 / `RibbonBarrier` 실제 연장 리본: 양쪽 솔리드 BVH로 쪽, 리본 BVH로 거리);
  곡선 시임은 자기 리본 재교차(`own_margin`)도 검사, Build는 경고와 함께 건너뜀.
  검증: `test_stroke_connectors.py` — S자 + Distribute → 중심이 리본 위(2D 1e-5), 핀 축 vs 실제 리본 면 법선 최대 0.54°(< 2°), v는 d 방향 이동,
  핀 쪽 부피 +·소켓 쪽 −, 관입 없음; V자 꼭짓점 수동 커넥터 "bends into" 건너뜀, Distribute는 꼭짓점 회피; Z 평면 + 세로 S자: 각 컷 시임이
  두 영역, 모든 커넥터 다른 컷까지 여유 ≥ 0.4 mm(장벽 종류 확인), 4파트 관입 없음, 리본을 걸친 수동 커넥터 "across another cut". PASS 4.5/5.2.
- [x] **P2-6 진행률**: `core/progress.py`(`wm.progress_*` + 작업공간 상태바 텍스트 + 리스너). Build는 단계 생성기: 조각×컷마다 2단계(A쪽/B쪽) +
  커넥터 불리언당 1단계; UI의 Build는 모달 타이머로 한 단계씩 실행(Esc 취소 = 이전 결과 유지), 스크립트(`execute`)는 즉시 실행.
  검증: `test_progress.py` — 큐브 Z+X 컷 + 커넥터: 단계 수 = 2·1 + 2·2 + 커넥터 불리언 수, 마지막 단계 = 합계; 스트로크 추가 시 +2×조각;
  모달 Build(스탠드인 TIMER): 끝까지 = execute와 같은 파트, Esc 중간 = 이전 파트·메시 그대로, `cancel()` 동일, 첫 빌드 취소 시 빈 컬렉션 없음. PASS.
  GUI `p2_build_progress`(13만 면 Suzanne, 스트로크 + 평면 + 커넥터): 빌드 중 창 스크린샷 하단 상태바 "SplitForge Build: Stroke 1: side A (1/4)",
  Esc 중간 취소 시 이전 파트 유지 — MANUAL_QA QA-8.
- [x] **P2-7 대형 메시 성능**: `--slow` `test_perf_large`에 51만 면 S자 컷(gap 0.3, 커넥터 2) 추가, 상한 120 s(5.2).
  결과는 아래 "Phase 2 결과" 참고.
- [x] **P2-8 (P1 검증 후속)** D8 중공 벽: Distribute가 맞지 않는 목표점을 옆으로(LINE은 선 방향, GRID는 행/열) 이웃 간격의 절반 안에서 찾아
  재료 쪽(벽 가운데)에 둔다; 2D에서 탈락한 위치도 dropped에 셈; Distribute 경고에 실제 이유(표면 관통 / 다른 컷 / 곡선 시임 / 시임 가장자리
  공간 없음 / 다른 커넥터와 너무 가까움). Build의 1 mm 샘플 간격을 지우면 실패하는 테스트.
  검증: `test_connectors_hollow.py`(벽 8 mm: LINE 2개 모두 벽 가운데 u ≈ ±16, GRID 16개, 빌드 매니폴드·부피 변화; 벽 3 mm에 8개 요청 →
  dropped 8 "no room"; 가파른 D7 재현에서 "would reach across another cut" 경고), `test_fit_spacing.py`(1.25 mm 링 사이 0.3 mm 공동). PASS.

### Phase 2 결과 (feat/p2-curved)

- 헤드리스 34/34 PASS ×2(4.5.5 / 5.2.2), `--gui` 12개 시나리오 ×2 PASS(새 `p2_stroke` 43–48 s, `p2_build_progress` 52–57 s).
  스크린샷: 리본 오버레이 [4.5](qa/p2_stroke_4.5.png) [5.2](qa/p2_stroke_5.2.png), 분리한 파트 [4.5](qa/p2_stroke_built_4.5.png)
  [5.2](qa/p2_stroke_built_5.2.png), 빌드 중 상태바 [4.5](qa/p2_build_progress_4.5.png) [5.2](qa/p2_build_progress_5.2.png).
- `--slow test_perf_large`(5.2, 514 560면): 레거시 split 4.89 s, connectors 12.92 s, 평면 Build 59.53 s, **S자 스트로크 추가 0.19 s,
  Distribute 0.81 s, Build 85.35 s(상한 120 s)** — 양쪽 DIFFERENCE 각 EXACT_SELF ~28.5 s, 커넥터 UNION 13.4 s / DIFFERENCE 11.5 s.
  평면 Build는 Phase 1의 ~9–10 s에서 59.5 s로 늘었다: 커넥터 불리언이 자기교차 Suzanne에서 이제 정확한 EXACT_SELF로 성공
  (이전에는 EXACT가 부피를 잃고 MANIFOLD로 폴백). PLAN 7-7 열린 결정.
- 뮤테이션 15건 중 14건 검출(불리언 검증 끔, 굽힘(fold) 검사 끔, 쌍 부피 검사 끔, Build 자기 시임 검사 끔, Distribute가 리본 장벽 무시,
  D8 옆 탐색 끔, 2D 탈락 미집계, Build `max_step` 제거, `is_inside` 모서리 수정 되돌림, 모달이 region 보관, 취소 시 새 파트 남김,
  커넥터 진행 단계 누락, 리본 깊이 분할 끔, 셸 정보 누락). 미검출 1건: "+오프셋이 −오프셋의 왼쪽" 포함 검사 — 만들어 본 모든 사례가
  오프셋 교차 검사에 먼저 걸리는 중복 방어선(남겨 둠).
- 독립 검증(2026-10-09, verifier, develop 29cd845): 헤드리스 34/34 ×2회 PASS(4.5.5/5.2.2), `--gui` 12시나리오 ×2버전 PASS(p2_stroke 43/48 s, p2_build_progress 56/55 s), `--slow test_perf_large`(5.2) PASS: 평면 Build 58.69 s, S자 Build 93.12 s(< 120 s; 구현자 85.35 s), 스트로크 추가 0.19 s, Distribute 0.82 s. 뮤테이션 8건 중 6건 검출(쌍 검사 끔·매니폴드 검사 끔·셸 교차 감지 끔·굽힘 검사 끔·자기 시임 검사 끔·리본 교차 판정 끔); 미검출 2건: Esc 시 `gen.close()` 제거(참조 해제로 CPython이 같은 정리를 함 — 등가 뮤턴트), 스트로크를 로컬 대신 월드로 저장(변환된 오브젝트 테스트 없음, 코드는 정확). 적대 스트로크(지그재그·헤어핀·짧음·부분·물체 밖·고리·나선·회전/스케일) 모두 올바르게 빌드 또는 이유와 함께 거부. Suzanne EXACT 빈 결과 원인 재현. 라이브 5.2 PASS(MANUAL_QA "P2 곡선 컷 라이브 검증"). 열린 결함: D9 쌍 검증 허용치 4 %가 셸 교차 없는 조각에도 적용(5 % 손실 통과, 중간~낮음), D10 곡선 컷 VOXEL 폴백 경고 누락(낮음~중간), D11 Distribute/Build 자기 시임 경계 불일치(낮음).

### Phase 2 후속 (fix/p2-followups, 검증자 결함 D9–D11 + 사용자 결정 7)

- [x] **P2F-1 불리언 품질 설정**: `Scene.splitforge.boolean_quality` Auto/Accurate/Fast(Settings 패널, 툴팁에 트레이드오프), 객체별 `solver` 속성 제거.
  Build 정보 줄에 솔버·폴백. 검증: `test_boolean_quality.py`(Suzanne: Accurate는 곡선 컷 EXACT_SELF·눈 겹침 부피 합침, Fast는 MANIFOLD·겹침 유지,
  Auto는 임계값 아래 Accurate·위 Fast, 정보 줄 "Booleans (…)"), `test_boolean.py`(품질별 순서). 성능은 아래.
- [x] **P2F-2 D9 쌍 검사 엄격화**: 셸 교차가 없으면 허용 0.1 % + 1e-7×대각³ + 리본이 지나는 면의 삼각분할 여유(`meshlib.triangulation_slack`,
  평면 면 0); 4 %는 셸 교차·voxel일 때만. 발견: 머리만 남긴 Suzanne도 비평면 사각형 때문에 모든 솔버가 0.12 % "잃음"(조각 부피는
  사각형의 한 삼각분할 기준) — 여유 없이 0.1 %면 정상 컷이 거부됨. 검증: `test_stroke_checks.py`(한쪽 3 % 손실 주입 → 다음 솔버로 둘 다 재시도,
  머리만 Suzanne S자(gap 0.4) 첫 시도 통과).
- [x] **P2F-3 D10**: voxel 폴백으로만 성공한 곡선 컷은 Build 경고(+ 정보 줄 fallbacks). 검증: 같은 테스트(voxel 외 전부 실패 주입 → 경고 2건).
- [x] **P2F-4 D11 Distribute/Build 불일치**: 원인 둘 — (1) 리본 쪽 판정이 커터 프리즘(가는 삼각형)의 광선 홀짝이라 샘플 하나를 반대쪽으로 판정 →
  최근접 리본 면 법선(애매하면 정확한 2D 다각형 판정)으로 교체, (2) 자기 시임 검사의 "건너뛰는 구역" 경계에 샘플 링이 정확히 놓여(z = 0.75)
  저장된 u의 float32 반올림으로 포함/제외가 바뀜 → 구역 안 샘플에 점점 줄어드는 보너스를 줘 연속 측도로. Distribute는 자기 시임 여유 0.1 mm
  (= 0.25×벽, Build는 0) 요구. 검증: `test_stroke_checks.py`(진폭 14 S자 큐브, gap 0.5, 개수 2/3/4/6: Build "bends into" 0건, 모든 커넥터 양쪽
  여유 ≥ 0.1 mm, 쪽 판정 13552 샘플 불일치 0, 규칙 단위 검사).
- [x] **P2F-5 변환된 오브젝트**: `test_stroke_transform.py` — 이동·회전·비균일 스케일 오브젝트의 스트로크 = 변환 적용 사본의 같은 스트로크(부피 0.2 %,
  커넥터 위치 0.05 mm), 이후 오브젝트를 옮기면 컷이 따라감. (월드 공간 저장 뮤턴트 검출)
- [x] **P2F-6 갭 UX**: 스트로크 컷의 갭을 바꾸면 즉시 검사해 `cut.problem`에 이유 저장, 패널(컷 상자 경고 + 목록 아이콘)에 표시, 줄이면 사라짐.
  검증: `test_stroke_checks.py`(gap 12 → "bends too sharply for its gap", 패널 라벨·목록 ERROR 아이콘, 0.5로 되돌리면 빈 문자열·Build 성공).
- [x] **P2F-7 성능(5.2, 514 560면, `--slow`)**: 평면 Build Auto 14.43 s / Accurate 60.45 s, S자 Build Auto 6.24 s(MANIFOLD 4회) / Accurate 86.71 s
  (EXACT_SELF 29.2/28.0/13.8/12.2 s). 상한 120 s 둘 다 통과. Accurate 평면 Build에서는 커넥터 불리언 3건이 EXACT_SELF 검증 실패 후 MANIFOLD로 폴백.
- 뮤테이션(새 테스트) 11/11 검출: 월드 공간 저장, 변환 무시, D9 항상 느슨, 삼각분할 여유 제거, D10 경고 누락, D11 하드 경계 복원, Distribute 여유 제거,
  Auto가 크기 무시, Build가 설정 무시, 솔버 요약 누락, 갭 재검사 누락.

결과(2026-10-09, fix/p2-followups): 헤드리스 37/37 PASS ×2(4.5.5/5.2.2), `--gui` 12개 시나리오 ×2 PASS, `--slow test_perf_large`(5.2) PASS
(위 P2F-7 수치).
- 독립 검증(2026-10-09, verifier, develop 398154a): 헤드리스 37/37 ×2 PASS(4.5.5/5.2.2), `--gui` 12시나리오 ×2 PASS, `--slow`(5.2) PASS: 평면 Auto 14.31 s / Accurate 61.43 s, S자 Auto 6.35 s(MANIFOLD×4) / Accurate 88.53 s(EXACT_SELF×4). 뮤테이션 6건 중 5건 검출(여유 0, D10 경고 제거, Distribute 여유 0, Auto 크기 무시, 항상 느슨); 리본 쪽 판정에서 2D 폴백 제거는 미검출. 3 % 손실 주입은 촘촘한 메시에서 모두 거부, 단 거친 비평면 메시(비평면 n각형 여유 최대 15 %)에서는 통과(D13). Accurate 평면 Build 커넥터 폴백 3건은 EXACT_SELF가 틀린 것이 아니라 겹친 셸을 두 번 센 before 부피 때문(D14). 원시 140° 꺾임 스트로크에서 쪽 판정 불일치(D15, 낮음). 라이브 5.2 PASS(MANUAL_QA "P2 후속 수정 라이브 검증").

### Phase 2 검증 3차 후속 (fix/p2-d13-d15)

- [x] **D14 Accurate가 올바른 EXACT_SELF 결과를 거부**: 교차 셸(눈↔머리) 파트의 "이전 부피"가 겹침을 두 번 셈. (1) EXACT_SELF/VOXEL 결과가 부피
  사유로 거부되면 대상의 *합친* 부피(EXACT_SELF 자기 합집합, 1회)로 다시 검사 — 비매니폴드는 그대로 거부; (2) Accurate(또는 Auto ≤ 200k 면)는
  Build 시작 시 소스 사본의 교차 셸을 한 번 합치고(정보 "Intersecting shells were united into one solid"), 이후 모든 불리언은 깨끗한 입력에서
  EXACT. Fast/큰 Auto는 정보 "Intersecting shells stay overlapping … Accurate unites them here".
  검증: `test_stroke_robust.py`(겹친 Suzanne에 핀 UNION → EXACT_SELF 폴백 없음; 비매니폴드 주입 → 거부; Accurate 평면 Build 커넥터 전부 EXACT·
  폴백 0), `test_boolean_quality.py`(Accurate 전부 EXACT + 합침 정보, Fast 겹침 정보), `test_build_monkey`(부피 합 = 합친 부피, 겹침 1.66 %).
- [x] **D13 삼각분할 여유가 실제 손실을 숨김**: 곡선 컷 전에 조각을 삼각분할 → 어느 솔버도 비평면 면 재분할로 부피를 바꾸지 못함, 여유 제거, 쌍 검사
  0.1 %. 검증: `test_stroke_robust.py` — 날 Suzanne 머리·지터 큐브(±4 mm)·비평면 64각 캡 원기둥: 정상 컷 첫 시도 통과, 한쪽 0.5 %/3 % 손실 주입 → 거부·재시도.
- [x] **D15 날카로운 날(raw) 모서리에서 쪽 판정 오류**: 최근접점이 면 *내부*일 때만 리본 법선, 모서리/꼭짓점이면 정확한 2D 판정. 검증: 날 지그재그·V
  각 20 000 샘플 불일치 0, 2D 폴백 9702/1254회 실행.
- [x] **낮음**: Fast/Auto가 교차 셸을 겹친 채 둘 때 Build 정보; 스트로크 컷 문제는 그리기 때 입력(변환·bbox·단위 스케일·갭·점)에 키를 둔 캐시로
  계산(저장 속성 제거) — 단위 스케일·오브젝트 스케일 변경 시 바로 갱신(`test_stroke_checks.py`).
- 뮤테이션 7/7 검출(합친 부피 재검사 제거, Build 셸 합침 제거, 삼각분할 제거, 모서리에서도 법선 신뢰, 2D 폴백 제거, 겹침 정보 제거, 캐시 미갱신).

결과(2026-10-09): 헤드리스 38/38 PASS ×2(4.5.5/5.2.2), `--gui` 12개 시나리오 ×2 PASS, `--slow test_perf_large`(5.2, 514 560면) PASS:
평면 Build Auto 13.81 s / **Accurate 38.16 s**(이전 60.45 s; 셸 합침 1회 후 커넥터 EXACT 4회, 폴백 0), S자 Build Auto 8.88 s(MANIFOLD) /
**Accurate 38.81 s**(이전 86.71 s; 합침 ~30 s + EXACT 1.7/1.7/1.0/0.9 s).
- 독립 검증(2026-10-09, verifier, develop 3d90da6, D13–D15): 헤드리스 38/38 ×2 PASS, `--gui` 12시나리오 ×2 PASS, `--slow`(5.2) PASS: 평면 Auto 14.75 s / Accurate 46.49 s(4x EXACT), S자 Auto 9.49 s / Accurate 41.89 s(4x EXACT; 구현자 38.2/38.8 s보다 ~20 % 김). 뮤테이션 5/5 검출(합치기 끔·면 내부 판정 항상 참·삼각분할 끔·합친 부피 재검사 끔·캐시 갱신 안 함). 적대: 손실 주입 36건 모두 거부(D13 해결), 원시 140° 지그재그 쪽 판정 불일치 0(D15 해결), 공동+겹친 셸 Accurate에서 공동 유지. 라이브 5.2: Accurate 6x EXACT·폴백 0(D14 해결). 새 결함 D16(셸 합치기 결과에 부피 하한 없음 — 3 % 축소 주입 통과, 중간~낮음). MANUAL_QA "D13–D15 수정 라이브 검증".

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
