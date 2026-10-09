# 구현 체크리스트 (검증자용)

규칙
- 각 항목은 독립적으로 체크 가능해야 한다. "검증" 줄의 명령을 그대로 실행하고 기대 출력과 비교한다.
- 공통 명령: `BL45="/mnt/c/Program Files/Blender Foundation/Blender 4.5/blender.exe"`, `BL52="/mnt/c/Program Files/Blender Foundation/Blender 5.2/blender.exe"`. 테스트 실행은 `python3 tests/run_tests.py`.
  **Phase 4부터 Blender 5.2 전용(사용자 결정 2026-10-10)**: 기본 실행은 5.2만, `--all-versions`로 4.5도 돌릴 수 있지만 지원 대상이 아니다.
  Phase 0–3 항목의 "PASS 4.5/5.2" 기록은 당시 기준 그대로 둔다.
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

- [x] **P3-0 (P2 검증 후속) D16 셸 합치기 부피 하한**: `boolean.unite_bm`은 입력을 먼저 삼각분할(비평면 n각형은 부피가 정의되지 않음)하고,
  결과가 입력 셸들이 함께 감싸는 부피(와인딩 수 광선 적분 96×96, 겹침 1회, 솔버와 무관)와 0.2 % 안에서 같아야 한다. 거부되면 Build 경고
  "Intersecting shells could not be united (…)" 후 겹친 채 진행. (검증자 제안의 "가장 큰 셸 ≥" 하한은 3 % 축소 Suzanne을 못 잡아 대신 이것.)
  검증: `test_unite_check.py` — 실제 합집합 6종(Suzanne 0/1/2단계, 공동+기둥, 중첩 셸, 교차 솔리드) 입력/결과 차 0.0000 %, 3 %·1 % 축소와
  셸 하나 누락 주입 거부, 주입한 Accurate Build는 경고 + 매니폴드 파트, 주입 없이 "united" 정보. 뮤테이션(하한 끔, 삼각분할 끔) 검출.
- [x] **P3-1 전 타입 지원**: `connectors/shapes.py` — 커넥터 = 솔리드 목록(Loft: ROUND/RECT 단면 스윕, Ball, MeshSolid)으로 Build가 추가하고
  `fit.py`가 **같은 솔리드**를 샘플링(표면·다른 컷 평면/리본·자기 곡선 시임·관통). 타입: CYL_PIN, RECT_TENON, DOVETAIL(끝이 좁은 테이퍼 테논),
  SNAP_PIN/TENON/DOVETAIL(돌기 + 딤플), CUSTOM, DOWEL. 커넥터별 값: 삽입 깊이 %, 테이퍼 %, 끝 모따기, 스냅 돌기 수/지름/높이, 커스텀 메시.
  공차: 각 면에 수직(프리즘 +c, 테이퍼 면 c/cos, 딤플 반지름 +c, 커스텀 법선 오프셋), 소켓은 조립 후(갭만큼 이동한) 핀 위치를 따름.
  한 커넥터의 겹치는 솔리드(돌기+핀, 커스텀)는 먼저 작게 합쳐 파트 불리언은 평범한 EXACT.
  검증: `test_connector_types.py` — 8종 × (평면 Z 컷 gap 0.4 / S자 곡선 컷 / Z 컷 + 세로 S 리본 장벽): 매니폴드, 핀 파트 > 소켓 파트(도웰은 둘 다 감소),
  파트가 큐브 밖으로 안 나감, 단면 치수(프리즘 +2c, 도브테일 면 수직 공차 c — 허용 0.002 mm, 스냅 돌기 = 핀 + 높이, 딤플 = 돌기 + c, 커스텀 상자 W≠H 양쪽 +c),
  곡선 시임에서 핀 파트 + / 소켓 파트 −, 리본 장벽 여유 ≥ 0.4 mm(양쪽 핀 방향), 가장자리 수동 커넥터는 Build가 "break through"로 건너뜀,
  벽 0.2 mm 위치에서 원기둥 핀은 통과·스냅 핀(딤플)은 건너뜀, 모든 파트 불리언 EXACT. PASS 4.5/5.2.
- [x] **P3-2 커스텀 메시 커넥터**: `custom_object`(소유 오브젝트 자신은 poll로 제외), 폭/높이/길이로 bbox 정규화(로컬 Z = 삽입 방향, 최저 Z = 박히는 끝),
  "Use Object Size". 검증(`custom_shape`): 닫힌 매니폴드, 평평하지 않음(최소 변 > 1 % 최대 변), 면 ≤ 20 000, 부피 있음, 법선 바깥으로 재계산.
  검증: `test_custom_connector.py` — 사용자 원기둥(크기·위치·회전 무관) = 같은 크기 CYL_PIN(부피 0.2 %), 열린/평평/고밀도/면 없는 메시 → Build 경고
  "… skipped"(다른 커넥터는 적용), Distribute 오퍼레이터 ERROR 보고(`report` 캡처), 패널 문제 표시; 테이퍼 뿔대의 경사면 수직 공차 0.251/0.2475(c 0.25),
  W≠H 상자 양쪽 +c; Use Object Size. 곡선 시임은 `test_connector_types`. PASS 4.5/5.2.
- [x] **P3-3 양면 도웰**: `kind=DOWEL`(원안의 `double_sided` 대신 종류 자체가 양면) → 두 파트 소켓(깊이 L/2 + c) + 도웰 파트 `<원본>_Dowel_<n>`
  (원안 "도웰 길이 = 2×length_mm"을 다른 커넥터와 같은 의미로 바꿈: length_mm = 도웰 전체 길이). 눕혀서(축 = X) 원본 +X 쪽 5 mm 밖, 최저 Z에.
  검증: `test_dowel.py` — 파트 A, B, Dowel_1 매니폴드, A/B 부피 = 반쪽 − 소켓(0.2 %), 도웰 길이·지름(0.05 mm), 모따기 끝 반지름, 배치·바닥,
  조립(도웰을 커넥터 축에 옮기고 갭을 닫음) 시 양쪽 소켓 안에 여유 0.199 mm(c 0.2), Export에 Dw_Dowel_1.stl, 두 번째 도웰 Dowel_2(옆에),
  재빌드 누수 0, 핀으로 바꾸면 도웰 파트 사라짐, Clear Build로 제거. PASS 4.5/5.2.
- [x] **P3-4 커넥터별 편집**: 패널의 활성 커넥터 상자(종류별 필드 + U/V·회전·핀 쪽·공차), 새 커넥터 템플릿(`Scene.splitforge.new_connector`).
  검증: `test_connector_edit.py` — U +10 → 테논 단면 중심 10 mm 이동(0.1), 회전 90° → bbox 가로세로 교환, 폭/높이/길이/공차/삽입 깊이/핀 쪽/종류(도브테일)
  변경이 재빌드에 반영, 편집 후 `ed.undo`/`redo`로 값과 재빌드 결과가 따라감; `test_ui_draw.py` — 8종마다 보이는/숨는 필드. PASS 4.5/5.2.
- [x] **P3-5 클릭 배치 모달** `connector_add_click`(평면은 광선∩평면, 곡선은 광선∩리본 BVH → 펼친 (u, v); 프리뷰는 gpu 오버레이(초록/빨강);
  3D fit 통과 시에만 추가; S = 핀 쪽; 클릭마다 `undo_push`; UNDO 플래그 없음 — PLAN 4.5).
  검증: `test_connector_click.py`(헤드리스 스탠드인 + 합성 위 뷰: 프리뷰 이동, 클릭 위치 ±0.05 mm, S, 물체 밖/가장자리 거부와 이유, ed.undo/redo가 클릭 하나씩,
  모달 중 undo 안전·구조체 보관 없음, 오브젝트 사라짐/`cancel()`, 곡선 리본 위 위치, 도웰, 잘못된 커스텀 메시는 시작 거부) PASS;
  GUI `p3_connector_click` — 실제 클릭 3회 후 **실제 Ctrl+Z 3회로 하나씩 제거**, Ctrl+Shift+Z 3회 복원(모달 중, 끝난 뒤에도 클릭당 1단계),
  프리뷰 오브젝트·컬렉션 생성 없음, Build 매니폴드, 파일 로드 → `cancel()`. 스크린샷 [프리뷰](qa/p3_click_preview_5.2.png) [배치](qa/p3_click_placed_5.2.png)
  [빌드](qa/p3_click_built_5.2.png).
- [x] **P3-6 레거시 제거**: `ops_split.py`, `ops_connectors.py`, `ops_freehand.py`, `ops_align.py`, `seam_data.py`, `profiles.py`, `utils.py`, `ui/legacy.py`
  삭제(legacy/ 보관 없음, 미등록 코드도 남기지 않음). 옛 파일용 코드 없음(결정: Blender가 미등록 `Scene.snapsplit` 값을 ID 프로퍼티로 보존하고 옛 파트는 일반 메시).
  재질 프로필 → `model/props.py`, 프리퍼런스는 debug_log만. Align Faces(면 맞춤)도 제거 — 새 워크플로는 파트를 제자리에 만들므로 필요 없음(열린 결정으로 보고).
  검증: `grep -rn "from . import ops_split\|ops_connectors\|ops_freehand" splitforge/__init__.py | wc -l` → 0; 패키지 .py 합계 7 600줄(Phase 1 시작 15 564줄);
  `test_legacy_parity.py`(레거시 기준 케이스 6종을 새 파이프라인으로: 큐브/Suzanne(눈 관통)/중공/3파트+오프셋/핀 3개/PETG 공차), `test_register`(레거시 타입·
  `Scene.snapsplit`·`snapsplit.*` 미등록). 레거시 GUI 시나리오(qa1–4, 레거시 undo/load) 삭제 → p1/p2/p3 시나리오가 대체. PASS 4.5/5.2.
- [x] **P3-7 로컬라이즈**: `localization.py`를 남은 UI 문자열만으로 정리(레거시 항목 삭제) + de_DE·ko_KR에 오퍼레이터 라벨(Operator 컨텍스트 포함)·속성/열거 이름·
  패널 라벨·패널 고정 문구 전부(설명 툴팁은 아직 번역 안 함). 검증: `test_i18n.py` — 등록된 RNA와 패널 소스에서 모은 UI 문자열 116개 전부 ko_KR·de_DE에 있음,
  소스에 없는 항목 0, 모든 로캘이 Blender에 알려짐(“locales unknown” 없음), 인터페이스 언어 ko_KR에서 `pgettext_iface("Build & Export")` = "빌드 및 내보내기". PASS 4.5/5.2.

### Phase 3 결과 (feat/p3-connectors)

결과(2026-10-09, feat/p3-connectors): 헤드리스 38/38 PASS ×2(4.5.5/5.2.2; 레거시 케이스 9개 삭제·새 케이스 9개), `--gui` 6개 시나리오 ×2 PASS
(p1_adjust_plane, p1_panel, p2_stroke, p2_build_progress, **p3_connector_click** 18/22 s, **p3_connector_types** 7 s). 스크린샷: 클릭 프리뷰
[4.5](qa/p3_click_preview_4.5.png) [5.2](qa/p3_click_preview_5.2.png), 배치 [5.2](qa/p3_click_placed_5.2.png), 빌드한 핀 [5.2](qa/p3_click_built_5.2.png),
8종 [소켓](qa/p3_types_built_5.2.png) [핀](qa/p3_types_pins_5.2.png) (4.5도 같은 이름).
- `--slow test_perf_large`(5.2, 514 560면): 평면 Build(Z 2개 + 핀) **Auto 14.66 s / Accurate 49.62 s**(커넥터 EXACT 4회 각 0.4–1.1 s, 나머지는 셸 합치기 ~31–35 s;
  P2 후 38–46 s 대비 삼각분할 + 부피 하한 검사로 ~4–5 s 증가), Phase 3 타입 Build(도브테일·스냅 핀·커스텀·도웰) **Auto 14.29 s / Accurate 47.42 s**
  (EXACT 3회, 폴백 0, 파트 A·B·Dowel_1), S자 Build **Auto 11.66 s / Accurate 48.46 s**. 상한 120 s 모두 통과.
- 뮤테이션 17건 중 16건 검출(테이퍼 1/cos 제거, 소켓 갭 이동 제거, 커스텀 소켓 = 스케일, 딤플 갭 이동 제거, fit이 돌기 무시, 클릭 undo_push 제거, 커스텀 법선 미수정,
  도웰 소켓 깊이 −c, 클릭이 fit 무시, 잘못된 커스텀 허용, 스냅 솔리드 사전 합집합 제거, ko 오퍼레이터 라벨 삭제, ko 속성 이름 삭제, 레거시식 오퍼레이터 등록,
  D16 하한 끔, 도웰 파트 미생성). 미검출 1건: ko의 `("*", 오퍼레이터 라벨)` 항목 삭제 — 오퍼레이터 라벨은 Operator 컨텍스트로만 표시되므로 등가 뮤턴트.
- 결정·편차: 도브테일은 밀어 넣는 테이퍼 테논만(레거시 음수 테이퍼·Span Axis/Hard-side Cut 레일 미이관), 스냅 변형은 커스텀에 없음, Align Faces 제거,
  도웰 길이 = length_mm(체크리스트 원안 2×length_mm), `double_sided` 대신 DOWEL 종류, 클릭 모달은 UNDO 플래그 없이 클릭마다 undo_push, 툴팁 미번역.
- 독립 검증(2026-10-10, verifier, develop f2a2f46): 헤드리스 38/38 ×2회 PASS(4.5.5/5.2.2), `--gui` 6시나리오 ×2 PASS(p3_connector_click 18/22 s, p3_connector_types 7 s),
  `--slow test_perf_large`(5.2) PASS: 평면 Auto 15.89 s / Accurate 59.56 s, 타입 Build Auto 15.45 s / Accurate 48.43 s, S자 Auto 9.43 s / Accurate 44.90 s(< 120 s).
  `extension validate` 성공, `extension build` → splitforge-0.3.0-dev.zip(39파일, 레거시·pycache 없음). 뮤테이션 7/7 검출(소켓 끝 +c 제거, 딤플 반지름 +c 제거,
  셸 팩터 제거, 클릭 핀 쪽 미적용, 모따기 값 미전달, D16 허용치 0.2→1.2 %, 도웰 크기 = 소켓 크기). 적대: 8종 × 6장면 매트릭스(벽·판·다른 컷·리본·곡선 시임) 관통 0·조립 관입 0·
  여유 ≥ 0.234(c 0.25), 커스텀 14종, 도웰 곡선 시임 여유 0.249, 레거시 .blend 열기 오류 0. 라이브 5.2 PASS(MANUAL_QA "Phase 3 커넥터 라이브 검증").
  열린 결함: D17 좁은 오목 특징(< 2c) 커스텀 소켓 접힘 → MANIFOLD 폴백 0.05 mm 간섭·경고 없음, 날카로운 모서리 여유 감소(낮음~중간); D18 오퍼레이터 버튼 텍스트 5개
  Operator 컨텍스트 번역 없음(ko/de에서 영어, 낮음).

### Phase 3 검증 후속 (fix/p3-followups, 검증자 결함 D17·D18 + 사용자 결정)

- [x] **P3F-1 D17 커스텀 소켓 공차**: `connectors/custom_socket.py` — 정점 법선 오프셋이 깨끗이 합쳐지고 핀 표면 샘플(정점·모서리 점·면 중심)에서
  ≥ 0.9 × 공차면 사용, 아니면 민코프스키 합(핀 ∪ 다각형 프리즘 ∪ 모서리 원기둥(8각, 내접 = c) ∪ 꼭짓점 이코스피어(내접 ≥ c)) 한 번 합집합(삼각형 ≤ 4000),
  형상·크기·공차별 캐시. 모자라거나 너무 촘촘하면 Build 경고("keeps only N % of the clearance … simplify"). 함께 수정: bmesh에 바로 만든 솔리드는
  법선이 없어 오목 n각형 캡(L·슬롯·별)이 홈을 가로질러 삼각분할됨 → 셸 합치기 실패·자기교차 처리로 폴백 → 삼각분할 전 `normal_update()`;
  커스텀 핀은 자기교차할 때만 합침. 검증: `test_custom_socket.py` — 0.3 mm 슬롯·별·뾰족한 원뿔·L·상자: 경고 0, 매니폴드, 조립(갭 닫음) 공차
  0.250 / 0.240 / 0.240 / 0.250 / 0.250(c 0.25; 평범한 오프셋만이면 −0.100 / 0.177 / 0.215), 핀 UNION 평범한 EXACT; 촘촘한 슬롯·별(삼각형 > 4000) 경고;
  법선 없는 L은 자기교차 아님·합치기 성공. 검증자 적대 세트(L, 별, 슬롯, 원뿔 2, 토러스, 뒤집힌 L, 고밀도 UV, 미세, 두 셸, 분리) 관입 0·공차 ≥ 0.237.
- [x] **P3F-2 D18 번역**: 자기 문구가 있는 오퍼레이터 버튼(Cut, Draw Cut, Redraw/Adjust in Viewport, Distribute, Click, Build, Rebuild)에
  Operator 컨텍스트 항목(de/ko), 값이 든 라벨은 템플릿(`ui/panel.py tr()`: "Part of {name}", "Gap {gap} mm, {n} connector(s)", "On {name}",
  "Stroke: {n} points", "1 unit = {mm} mm", "{n} part(s) in {collection}"). **툴팁은 한국어만**(사용자 결정, 104개). 검증: `test_i18n.py` — 버튼 문구
  Operator 컨텍스트, 툴팁 104개 ko, `pgettext_tip`, 한국어 인터페이스로 패널을 그리면 값 라벨이 한국어("KoCube의 파트", "틈 0 mm, 커넥터 0개" 등).
- [x] **P3F-3 도웰 배치 옵션**(사용자 결정): Settings > Dowel layout — Flat(기본)/Upright/At assembly position, 세 자세를 파트에 저장해
  설정 변경 시 즉시 이동, Export는 출력 자세(Upright 선택 시 세움, 아니면 눕힘). 검증: `test_dowel.py`(세 자세 위치·크기·바닥, 조립 자세가 양 파트에서
  공차만큼 떨어짐, 재빌드가 선택한 자세 사용, 자세별 STL 재임포트: 눕힘/세움/눕힘, 바닥 높이), GUI `p3_connector_types`(조립·세움·눕힘 이동, 스크린샷
  [조립](qa/p3f_dowel_assembled_5.2.png) [세움](qa/p3f_dowel_upright_5.2.png)).
- [x] **P3F-4 낮음 항목**: 클릭 모달은 수정키 없는 S/LMB만 처리(Ctrl/Cmd+S, Alt/Shift+LMB, Ctrl+Z는 통과; `test_connector_click`); 패널 커스텀 메시
  검사가 Build처럼 평가된 메시(모디파이어) 사용, 키는 평가 메시 지문(`test_custom_connector`: Solidify 켜고/끄기); 핀 끝 모따기 전용 테스트
  (`test_connector_edit`: 45° 단면 4점, 끝 높이 유지, 소켓은 모따기 없음); D16 얇은 셸 — 와인딩 적분을 X/Y/Z 세 방향(`test_unite_check`:
  0.3 mm 판 누락은 Y·Z 광선 0.0 %, X 광선 0.87 %로 거부). 와인딩 적분 견고화: 살짝 기울인 광선, 모든 광선의 교차를 한 번에(광선 띠 BVH ∩ 메시 BVH →
  정확한 광선-삼각형 교차; 겹친 조각의 일치하는 면도 각각 셈), 같은 교차의 중복은 꼭짓점을 공유하는 면일 때만.
- [x] **P3F-5 결정 반영**: Align Faces 제거 유지, 슬라이딩 도브테일 레일 → 아래 백로그 B-1.

결과(2026-10-10, fix/p3-followups): 헤드리스 39/39 PASS ×2(4.5.5/5.2.2), `--gui` 6시나리오 ×2 PASS(p3_connector_types에 도웰 배치 단계 추가; 마지막
meshlib 미세 변경 후 p2_stroke·p2_build_progress·p3_connector_types ×2 재실행 PASS), `--slow test_perf_large`(5.2, 514 560면) PASS:
평면 **Auto 14.54 s / Accurate 53.04 s**, 타입 **Auto 15.16 s / Accurate 49.88 s**, S자 **Auto 9.64 s / Accurate 46.02 s**(셸 합치기 검사가 3축이 되어
Accurate +3–4 s; 삼각형 메시는 복사 없이 사용). 뮤테이션 15/15 검출(민코프스키 폴백 없음, 공차 검사 없음, 공차 경고 없음, 자기교차 검사·unite_bm의
법선 갱신 제거(각각), Z축만, 중복 규칙에서 꼭짓점 공유 무시, Export가 조립 자세 유지, 설정이 도웰을 안 옮김, 패널이 평가 전 메시, 모따기 무시,
Ctrl+S가 핀 쪽 전환, 값 라벨 미번역, ko 버튼 항목·툴팁 삭제).
알려진 제한: 민코프스키 폴백은 느릴 수 있음(16각 원뿔 20–40 s, 형상·크기별 1회 캐시); 별·원뿔 소켓의 DIFFERENCE는 EXACT_SELF가 비매니폴드라
MANIFOLD로 폴백(검증 통과, 조립 공차 0.24); 오류/경고 메시지 본문(보고)은 영어.
- 독립 검증(2026-10-10, verifier, develop d9f7225): `--gui` **전체** 6시나리오 ×2 PASS(p1_adjust_plane·p1_panel·p3_connector_click 포함, meshlib 변경 후),
  헤드리스 39/39 ×2 PASS, `--slow`(5.2) PASS: 평면 Auto 14.15 s / Accurate 54.56 s, 타입 Auto 14.62 s / Accurate 47.45 s, S자 Auto 11.81 s / Accurate 45.67 s.
  `extension validate` 성공, `extension build` 40파일(custom_socket 포함). 뮤테이션 4/4 검출(공차 비율 0 → 민코프스키 안 씀, 와인딩 Z축만, Export 자세 복원 제거,
  ko `("Operator", "Distribute")` 삭제). 적대: 매트릭스 48빌드 관입 0·최소 여유 0.93c, 커스텀 14종 관입 0·여유 ≥ 0.96c(슬롯 0.250), 0.3 mm 판 누락 8/8 검출.
  라이브 5.2 PASS(MANUAL_QA "Phase 3 후속 수정 라이브 검증"). 새 결함 D19(민코프스키 폴백 느림: 17면 원뿔 ~44 s, 진행 표시 없음, 중간~낮음); 낮음: Export 폴더
  생성 예외 미처리(기존), 폴백 소켓 DIFFERENCE MANIFOLD 폴백.

### 백로그 (나중에, 사용자 결정 2026-10-10)

- [ ] **B-1 슬라이딩 도브테일 레일**: 시임 평면 안에서 옆으로 밀어 넣는 도브테일(레거시 음수 테이퍼 + Span Axis/Hard-side Cut).
  끝이 넓은 사다리꼴 단면 레일이 시임을 따라 한쪽(또는 양쪽) 외곽까지 열려 있고, 파트를 그 방향으로 밀어 조립. 필요한 것: 조립 방향
  (시임 위 u 또는 v), 레일이 외곽을 지나도록 하는 fit 검사 예외(레일 축 방향만 외곽 통과 허용, 나머지 방향은 벽 0.4 mm), 레일과 다른 커넥터의
  간섭(밀어 넣는 경로 위) 검사, 소켓은 경로 전체 + 공차. 검증 아이디어: 큐브 Z 컷 + X 방향 레일 → 매니폴드, 단면이 사다리꼴(끝 넓음),
  B를 +X로 빼낼 수 있음(경로 위 관입 0), 경로를 막는 핀이 있으면 경고.

## Phase 4 — Manual/Polygonal 컷, 검증 강화, 패키징 (feat/p4-final, 5.2 전용)

- [x] **P4-0 (P3 검증 후속) D19 커스텀 소켓 속도**: 볼록한 핀 = 정점 ⊕ 공 꼭짓점의 볼록 껍질(정확한 민코프스키 합, 불리언 없음);
  오목 핀은 정점 법선 오프셋 → 안 되면 면별 볼록 껍질(면 정점 ⊕ 공)을 핀과 한 번 합집합(이전: 면 프리즘 + 모서리 원기둥 + 꼭짓점 구).
  캐시는 표준 프레임(핀 쪽·갭·삽입 깊이와 무관, 강체 이동)이라 양쪽 핀 쪽·Distribute·재빌드가 한 번 계산을 공유. 느린 경로는
  대기 커서 + 상태 텍스트(`progress.busy`, 모달 Build 중에는 Build 진행 표시 유지). 오브젝트/파일 저장 캐시는 만들지 않음(PLAN 9).
  측정(5.2, 6×6×10 mm, c 0.25): 소켓 1개 — 17면 원뿔 17.4 s → 0.01 s, 뒤집은 원뿔 18.0 s → 0.01 s(이전엔 민코프스키 합치기 실패로 86 %
  공차 경고), 별 3.4 s → 1.9 s; Z 컷 큐브에서 Distribute(2개) + 첫 Build — 원뿔 41.7 + 0.57 s → 0.04 + 0.04 s, 뒤집은 원뿔 40.3 + 0.53 s →
  0.05 + 0.04 s, 별 7.0 + 0.52 s → 1.90 + 0.04 s. 조립 여유 0.240 → 0.250(c).
  **낮음(EXACT_SELF→MANIFOLD 폴백) 원인**: 이전 합 소켓에 면적 0 삼각형·길이 0 모서리가 수백 개(원뿔 559/371, 별 562/445: 접하는 구·원기둥의
  합집합 찌꺼기) → 파트 DIFFERENCE에서 EXACT_SELF 결과가 비매니폴드. 새 소켓은 원뿔 0개, 별 11개(1e-6 미만) → 별·원뿔 모두 평범한 EXACT.
  검증: `test_custom_socket.py`(모든 불리언 EXACT, 원뿔 < 1 s·별 < 6 s, 세 가지 핀 쪽/갭/깊이에 캐시 1개, 원뿔은 busy 없음·별은 1번,
  옮긴 소켓이 옮긴 핀을 ≥ 0.9c로 감쌈). 뮤테이션: 볼록 경로 끔, 비표준 캐시 키 → 검출.
- [x] **P4-0b (P1부터) Export 폴더 예외**: `os.makedirs` 실패와 파일 쓰기 실패를 경로를 밝힌 ERROR 보고로(트레이스백 없음, CANCELLED).
  검증: `test_export.py`(파일 아래 폴더 → "Cannot create the export folder …", 같은 이름 폴더가 막은 STL → "Could not write …"). 뮤테이션 검출.
- [x] **P4-1 폴리라인 컷** `cuts/polyline.py` + `splitforge.stack_add_polyline`: 클릭한 점 그대로(스무딩·리샘플 없음)의 리본 컷(스트로크와
  같은 커터·갭·거부 규칙, 메시지는 "polyline"), 커넥터 프레임은 구간 방향(`Centerline(sharp=True)`, 핀이 구간 면에 수직), 꼭짓점 위 커넥터는
  Build가 "bends into"로 건너뜀. 모달: LMB 점 추가(첫 클릭의 뷰 방향 고정, 뷰를 돌려도 같은 평면), Ctrl = 화면 15° 단위,
  Backspace/Delete/Ctrl+Z 마지막 점 삭제, Enter/Space 확정, Esc/RMB 취소, 고무줄 선 + 커터 윤곽 프리뷰(평범한 데이터), `replace_uid`, `easy`.
  검증: `test_polyline_cutter.py`(점 4개 그대로 저장, 두 제거 솔리드 매니폴드, 리본이 구간 위, 2파트 매니폴드·A+B = 큐브 − 갭 슬랩 0.5 %,
  Distribute 2개 축 ⟂ 구간, 경고 0·핀 +/소켓 −, 꼭짓점 커넥터 건너뜀, 점 2개 = 평면 컷(1e-4), 거부 3종, 오브젝트 이동 시 따라감,
  다시 그리기 uid·커넥터 유지, Easy 한 번에, undo), `test_points_modal.py`(스탠드인: 클릭 위치·고무줄·Backspace/Ctrl+Z·undo 중 안전·Enter·
  15° 스냅·궤도 회전 후에도 첫 평면·거부 이유·Esc/RMB 흔적 없음·두 번째 모달 거부·redraw·오브젝트 사라짐·`cancel()`), GUI `p4_points`.
- [x] **P4-2 폴리곤 컷(영역 도려내기)** `cuts/polygon.py` + `splitforge.stack_add_polygon`: 닫힌 다각형(반시계 정규화, 자기 교차·면적 0·
  갭에 비해 좁음 거부) → A = 조각 ∩ 안쪽 오프셋 프리즘(INTERSECT), B = 조각 − 바깥 오프셋 프리즘, 같은 쌍 부피 검사(A + B + 벽 갭 = 조각).
  프리즘은 물체 앞(뷰 쪽)에서 시작해 **Depth**(mm, 물체 bbox 앞면 기준)의 바닥 또는 관통(0). 커넥터는 바닥 평면(법선 −d = 플러그 쪽)에만,
  Distribute는 바닥 ∩ 안쪽 다각형을 래스터, fit은 폴리곤 프리즘을 RibbonBarrier(정확한 안/밖 판정)로 — 자기 시임(own)과 다른 컷의 장벽 모두.
  관통 폴리곤은 Distribute/Click이 "set a Depth" 오류, Easy는 커넥터 없이 빌드. 클릭 모달은 첫 점 클릭(12 px)으로 닫힘.
  검증: `test_polygon_cut.py` — 깊이 10 사각형: 플러그 4000 / 몸체 60000(1e-4, 합 = 64000), 플러그 z 10..20, 원본 해시 불변; 바닥 커넥터 2개
  (z = 10, 축 +Z, 벽에서 ≥ 0.4 mm), 경고 0, 핀 +/소켓 −, 핀이 벽 안; 관통 + 갭 0.4: 기둥 19.6²×40·링 64000 − 20.4²×40(0.5 %), 쌍 검사 첫
  EXACT 통과; L자 오목 플러그; Z 평면 + 깊이 30 폴리곤: 평면 커넥터 21개 모두 폴리곤 벽에서 ≥ 0.4 mm(플러그 안 9개), 4파트; 거부 5종
  (점 2개, 교차, 물체 밖, 물체 전체 둘러쌈, 갭에 비해 좁음), 패널 문제 표시, Easy 도려내기(깊이 12 + 커넥터 2), Easy 관통(커넥터 0), undo.
  (원안의 "큐브 윗면 사각형 → 파트 2개, 부피 합 = 원본 2 %"를 포함.) 눈 있는 Suzanne(Accurate/Fast) 폴리곤 + 폴리라인 프로브: 매니폴드, 폴백 0.
- [x] **P4-3 검증 패널 + Fix**: `core/validate.py`가 열린 모서리(구멍)·3면 이상 모서리·떨어진 요소·뒤집힌 법선(같은 방향으로 지나는 모서리)·
  안팎 뒤집힘(음의 부피)·중복 정점(0.001 mm, KDTree)·변환·단위를 보고, 마지막 Check Mesh 결과를 메시 지문별로 보관(패널이 재스캔하지 않음).
  패널 맨 위 "Print checks": 실패한 행에만 Fix. `ops/ops_fix.py` — `fix_transforms`(회전·스케일을 메시에 적용, 컷 스택(원점·법선·접선·점·방향)을
  같은 행렬로 변환해 월드 위치 유지, 음수 스케일은 법선 뒤집기, 자식은 월드 유지, 공유 메시는 거부), `fix_units`(Metric·Millimeters·0.001;
  Keep Units 기본 / Keep Size = 씬 오브젝트 스케일, 대화상자), `fix_normals`, `fix_merge`(거리 mm), `fix_holes`(구멍 채움 + 떨어진 요소 삭제,
  3면 모서리는 남기고 보고). 모두 REGISTER|UNDO, 바꾼 내용 보고, 할 일이 없으면 CANCELLED, 메시 Fix 뒤 Check Mesh 다시 실행.
  검증: `test_validate_ops.py`(스케일 2·회전 30° 큐브 + Z 컷 + 스트로크 + 커넥터: 적용 후 크기·부피 그대로, 컷 월드 위치·스트로크 점 1e-4,
  자식 월드 유지, Build 파트 부피 동일, undo 복원; 음수 스케일 법선; 공유 메시 오류; 미터 씬 Keep Units/Keep Size/undo/이미 mm;
  면 2개 뒤집힘·안팎 뒤집힘 → 수정·undo; 모서리 분리 큐브 24 → 8 정점; 면 없음 + 떨어진 정점 → 닫힘·부피 8000; 3면 모서리 남음;
  패널 행: Fix는 실패 행에만, 메시 바뀌면 "Mesh not checked yet"), GUI `p4_fix`. 뮤테이션: 컷 미변환·법선 뒤집기 없음·Keep Size 끔·
  뒤집힌 법선 미검출·오래된 보고 표시 → 검출.
- [x] **P4-4 (변경) 호환 매트릭스 → Blender 5.2 전용**(사용자 결정 2026-10-10): 원안의 4.2/4.4/4.5/5.2 매트릭스와 `docs/COMPAT.md` 대신
  manifest·bl_info 최소 5.2.0, `run_tests.py` 기본 5.2(`--all-versions`로 4.5 선택 실행, 지원 주장 안 함), 4.x 전용 호환 코드(FAST/FLOAT 솔버
  이름 분기, MANIFOLD 유무 검사, 미사용 `boolean_solver_order`) 삭제 — 헤드리스 전체·GUI 전체 PASS로 확인. README "Blender version".
- [x] **P4-5 패키징**: 버전 **0.4.0**(PLAN 9), manifest `[build] paths_exclude_pattern`(pycache·pyc·.git·blend1·OS 파일), 패키지 README 새로 씀,
  `.gitignore`에 `/dist/`. 검증: `"$BL52" --command extension validate splitforge` 성공, `extension build --source-dir splitforge --output-dir dist` →
  `dist/splitforge-0.4.0.zip`(44파일, tests·pycache 없음, LICENCE.txt·README.md 포함, ~154 KB); `python3 tests/run_tests.py --zip
  dist/splitforge-0.4.0.zip`가 zip을 `package_install_files`(enable on install)로 설치해 연산자·패널 등록, Build 2파트 매니폴드,
  disable/enable 확인 + 헤드리스 케이스를 zip 내용으로 실행.
- [x] **P4-6 문서**: README(사용자 가이드: 설치, 단위, 검사·Fix, Draft/Easy, 컷 4종, 커넥터(커스텀·도웰 배치), 품질 설정, Export, 제한, 버전,
  빌드, 한국어 빠른 안내, 크레딧), CHANGELOG.md, PLAN(5.2 결정·모듈·결정 9), MANUAL_QA(QA-11·QA-12·자동화 표). 새 UI 문자열 de/ko 라벨 +
  한국어 툴팁(`test_i18n`: 문자열 154·툴팁 121, `tr()` 템플릿과 검사 행도 스캔, 한국어 그리기 "폴리라인: 점 3개").
- 백로그 B-1(슬라이딩 도브테일 레일)은 그대로 보류.

### Phase 4 결과 (feat/p4-final)

결과(2026-10-10, feat/p4-final, Blender 5.2.2 LTS만): 헤드리스 **43/43 PASS**(새 케이스 5개: test_polyline_cutter, test_polygon_cut,
test_points_modal, test_validate_ops + 확장된 기존 케이스), `--zip dist/splitforge-0.4.0.zip`로 zip 내용에서 43/43 + 설치 검사 PASS,
`--gui` **8개 시나리오 전체 PASS**(p1_adjust_plane 26.5 s, p1_panel 187.1 s, p2_stroke 47.7 s, p2_build_progress 49.0 s,
p3_connector_click 21.7 s, p3_connector_types 10.0 s, **p4_points 36.1 s**(40 검사), **p4_fix 128.0 s**(11 검사)).
스크린샷: 폴리라인 프리뷰 [비스듬히](qa/p4_polyline_oblique_5.2.png), 폴리곤 [위에서](qa/p4_polygon_preview_5.2.png),
[빌드 분리](qa/p4_built_apart_5.2.png)(플러그 들어 올림, 아래 폴리라인 시임), 검사 [발견](qa/p4_fix_checks_found_5.2.png)
[수정 후](qa/p4_fix_checks_fixed_5.2.png).
- `--slow test_perf_large`(514 560면): 평면 **Auto 13.68 s / Accurate 50.01 s**, 타입 Auto 14.02 s / Accurate 44.99 s, S자 Auto 9.07 s /
  Accurate 46.30 s, **새 폴리라인 + 폴리곤(깊이 15, 갭 0.3) Auto 11.61 s(MANIFOLD×4) / Accurate 50.01 s(EXACT×4, 각 1.1–2.2 s + 셸 합치기)**,
  폴리곤 추가 0.19 s. 상한 120 s 모두 통과. (같은 날 첫 실행의 평면 Accurate는 64.35 s — 불리언 4개 합 3.4 s, 나머지는 셸 합치기의
  실행 간 편차; 코드 경로 불변.)
- 뮤테이션 21건 중 처음 19건에서 17건 검출, 미검출 2건(폴리곤 갭 부피 무시 — VOXEL의 느슨한 허용치로 통과; 첫 클릭 뷰 방향 고정 해제 —
  궤도 회전 시나리오 없음)은 테스트 보강 후 검출 → 21/21.
- 편차·결정: P4-4 매트릭스 → 5.2 전용(사용자 결정); 버전 0.4.0; 폴리곤 커넥터는 바닥에만; 소켓 캐시 영속화 안 함(PLAN 9);
  원안의 `cuts/polyline.py` 커터는 스트로크 커터 재사용(파일은 규칙·화면 헬퍼); 원안의 `fix_transforms`/`fix_units` 외에 법선·병합·구멍 Fix 추가.
- 독립 검증(2026-10-10, verifier, develop bdd59e3, 5.2 전용): 헤드리스 **43/43 ×2 PASS**, `--gui` **8시나리오 전체 PASS**(p4_points 36.1 s, p4_fix 124.4 s), `--slow test_perf_large` PASS(평면 Auto 13.93 / Accurate 50.62 s, 폴리라인+폴리곤 Auto 11.29 / Accurate 46.75 s), `extension validate` 성공·develop에서 다시 build한 zip 44파일(p4 zip·git HEAD와 내용 동일, tests·pycache 없음), `--zip` 설치 검사 + 43/43 PASS. D19 볼록 소켓 수치 검사 최소 여유 0.2500(UV 구 0.2496), 원뿔 0.006 s·별 2.0 s. 뮤테이션 5건 중 4건 검출(볼록 경로 끔, 폴리곤 항상 관통, Fill Holes 떨어진 정점 남김, Ctrl 스냅 끔); 미검출 1건: 소켓 캐시 키에서 공차 제거(테스트가 같은 형상의 공차를 바꾸지 않음, 코드는 정확). 적대 폴리곤·폴리라인·Fix·옛 .blend 모두 정상 또는 이유와 함께 거부. 라이브 5.2: 릴리스 zip을 User Default에 설치해 Check Mesh + Fix 5종, 폴리라인 + 깊이 폴리곤 + 커넥터 Build, STL, 한국어 UI (MANUAL_QA "Phase 4 라이브 검증 — 릴리스 zip"). 새 결함 D20(뾰족한 폴리라인 + 갭 Build 실패, 중간~낮음), D21(아주 작은 폴리곤, 낮음).
- 독립 검증(2026-10-10, verifier, 0.4.1 후속 946a7a7 + D22 수정 0fd12d3, 5.2 전용): 946a7a7에서 헤드리스 44/44 ×2, `--gui` 8/8, `--slow` PASS(평면 Auto 13.55 / Accurate 47.89 s, 폴리라인+폴리곤 11.08 / 48.08 s), `--zip` PASS, 뮤테이션 4/4(클램프 마이터 복원, 폴리곤 날카로운 꼭짓점 거부 끔, 최소 크기 끔, 델타 초기화 끔); D20 수정 확인(10–40° × 갭 0/0.3/1, 틈 정확), 단 D21 규칙이 큰 물체의 정상 포켓을 거부(D22, 500 mm 큐브 10×10×5) → 반려. 0fd12d3에서 헤드리스 44/44 ×2, `--gui` 8/8, validate·다시 빌드한 zip(44파일, p4d zip·git HEAD와 내용 동일) `--zip` PASS, 뮤테이션 3/3(부피 여유 ×10, 깊이 검사 끔, 부피 검사 끔); D22 케이스 모두 빌드, 경계 249 거부/251 빌드, 거부를 끈 사본에서 124 mm³ 이하 Build 실패·126 이상 성공(불리언 허용치 125 mm³와 일관). 라이브 5.2: 0.4.1 수정본 zip 교체 설치, 500 mm 포켓 빌드, 2 m 큐브 1×1×1 부피 메시지로 거부(MANUAL_QA "Phase 4 후속(0.4.1) + D22 라이브 검증"). 남은 낮음: bbox 기준 부피 규칙이 bbox가 큰 성긴 물체에서 보수적, 폴리곤 면적을 물체와 겹친 부분으로 자르지 않음(모서리 걸침 → VOXEL 폴백 경고).
- 남은 것(사람 확인): 실제 장치에서 점 찍기 감각, 프리뷰 가독성, Fix 대화상자 문구, 실제 출력 끼움(커스텀 소켓 0.25 mm), 한국어 툴팁 문구.

### Phase 4 검증 후속 (fix/p4-followups, 검증자 결함 D20·D21 + 낮음/정보, 0.4.1)

- [x] **D20 날카로운 꼭짓점 + 갭**: 원인 — 오프셋 마이터를 4×오프셋으로 자르면(cos_half ≥ 0.25) 점이 적은 폴리라인에서 꼭짓점 양옆
  **구간 전체**가 기울어져(꼭짓점 쪽에서 0.69h까지) 갭이 구간을 따라 좁아짐 → 쌍 검사(A + B + 갭 × 시임 면적/2 = 조각)가 모든 솔버에서
  실패("no solver left"). 꼭짓점 < 약 29°에서 발생(갭 1 mm는 25°도). 수정: 정확한 마이터(오프셋 구간이 정확히 평행 → 갭 슬래브 =
  갭 × 평균 길이, 쌍 검사 정확), 갭이 있으면 15° 미만 꼭짓점은 추가·패널 검사에서 각도와 함께 거부(마이터 > ~7.7h). 폴리곤도 같은 규칙.
  검증: `test_sharp_corners.py` — V 꼭짓점 10/15/20/25/40° × 갭 0/0.3/1: 갭 0 모두 빌드, ≥ 15° 모두 첫 시도 EXACT×2·경고 0·파트 사이 최소
  간격 = 갭(0.3000/1.0000), 10°+갭은 추가 거부("10.0 degrees … at least 15")·저장된 컷의 패널 문제; 폴리곤 20° 뾰족 + 갭 1 빌드(간격 1.0),
  10° 거부. 프로브(이전 코드): 15°/20° × 0.3/1, 25° × 1 실패 재현.
- [x] **D21 아주 작은 폴리곤**: 0.5 mm 미만(2 × 면적 / 둘레 < 0.25 mm, 또는 bbox 안 부피 < 1e-5 × bbox 부피)이면 추가·패널·Build에서
  "too small or too narrow to cut out: … at least 0.5 mm across". 프로브: 0.01·0.1 mm 정사각형은 이전에 Build 실패(부피 허용치 아래), 0.5 mm는 빌드.
  검증: `test_polygon_cut.py`(0.01/0.1/0.4 정사각형·0.2 mm 띠 거부, 0.5 mm 빌드 EXACT×2, 저장 후 줄이면 패널 문제·Build 오류).
- [x] **낮음** 폴리곤 바닥 커넥터가 벽에 걸리면 "pin or socket would reach into the wall of the polygon cut-out"(Build), Distribute/클릭 이유
  "too close to the wall of the polygon cut-out"(`RibbonBarrier.wall`). 검증: `test_polygon_cut.py`.
- [x] **낮음** 궤도 회전 뒤 점 찍기: Ctrl 15° 스냅과 첫 점 닫기가 저장된 3D 점의 **현재** 화면 위치를 매 이벤트 계산(화면 좌표 저장 삭제).
  검증: `test_points_modal.py`(기울인 뷰에서 Ctrl 클릭 → 그 뷰 화면에서 165°, 첫 꼭짓점이 40 px 이상 옮겨진 뒤 그 위치 클릭으로 닫힘).
- [x] **정보** Fill Holes가 바깥으로 뒤집은 기존 면 수를 보고; `schema_version`을 컷 추가 시 명시적으로 기록(기본값은 파일에 저장되지
  않음, `test_model`: 저장·로드 후 `is_property_set`); 같은 커스텀 형상의 다른 공차 = 새 캐시 항목·공차 유지(`test_custom_socket`);
  Apply Rotation & Scale가 delta 회전·스케일도 적용(scale 0.5/delta 2가 남던 문제, `test_validate_ops`: 월드 정점 동일·delta 초기화).
- [x] README 알려진 제한(꼭짓점 15°·0.5 mm·세션 캐시·delta), CHANGELOG **0.4.1**(동작 수정이 있어 패치 버전).
- 뮤테이션 14/14 검출(클램프 마이터 복원 ×2, 꼭짓점 거부 끔 ×2, 크기 검사 끔, 패널 크기 검사 끔, 벽 문구·이유 끔, 오래된 스냅 좌표,
  닫기 위치 고정, delta 미초기화, 뒤집힘 보고 누락, schema 미기록, 캐시 키에서 공차 제거).

결과(2026-10-10, fix/p4-followups, Blender 5.2.2): 헤드리스 **44/44 PASS**(새 test_sharp_corners), `--zip dist/splitforge-0.4.1.zip`
44/44 + 설치 검사 PASS, `--gui` **8/8 PASS**(p1_adjust_plane 26.1 s, p1_panel 186.9 s, p2_stroke 47.7 s, p2_build_progress 49.4 s,
p3_connector_click 21.7 s, p3_connector_types 10.0 s, p4_points 36.1 s, p4_fix 126.2 s), `--slow test_perf_large`(514 560면) PASS:
평면 Auto 13.81 / Accurate 50.32 s, 타입 13.94 / 47.44 s, S자 9.10 / 43.83 s, 폴리라인+폴리곤 11.30 / 46.92 s(< 120 s).
`extension validate` 성공, `extension build` → `dist/splitforge-0.4.1.zip`(44파일, 155 950 B, tests·pycache 없음).

### D22 (검증자, 0.4.1 거부 사유): 큰 오브젝트의 정상 포켓 거부

- [x] **D22**: D21의 부피 규칙(`면적 × 두께 ≥ 1e-5 × bbox 부피`)이 오브젝트 크기에 비례해 300 mm 큐브 4×4×10·6×6×5, 500 mm 큐브 10×10×5,
  40 mm 큐브 1×1×0.5 포켓까지 거부(잘못된 문구 "0.5 mm across"), 0.4.0 파일의 그런 포켓은 Build 실패. 수정: 규칙 셋, 각자 문구 —
  폭(절대, 2 × 면적 / 둘레 ≥ 0.25 mm: "too narrow to cut out (… mm across)"), 깊이(절대 ≥ 0.2 mm: "too shallow"), 부피(불리언 결과 검사가
  실제로 쓰는 허용치에 맞춤: 제거 부피 ≥ 2 × `VOLUME_TOLERANCE`(1e-6) × bbox 부피 — 500 mm 큐브 250 mm³, "too small for an object this large
  (… mm^3; the booleans need at least … mm^3 here)"). 검증: `test_polygon_cut.py` — 300 mm 4×4×10(160)·6×6×5(180), 500 mm 10×10×5(500),
  40 mm 1×1×0.5(0.5) 모두 EXACT×2 빌드·플러그 부피 1e-3; 0.4.0 방식으로 저장된 500 mm 큐브 포켓은 패널 문제 없음·빌드; 0.01/0.2/0.49 mm
  정사각형 "too narrow", 깊이 0.1 "too shallow", 2 m 큐브 1×1×1 "too small for an object this large".
  결과(2026-10-10, fix/p4-d22, 5.2.2): 헤드리스 44/44 PASS, `--zip dist/splitforge-0.4.1.zip`(44파일, 156 341 B) 44/44 + 설치 검사 PASS,
  `--gui p4_points` PASS(36.1 s), `extension validate`/`build` 성공. 뮤테이션 5/5 검출(이전 상대 규칙 복원, 부피·깊이·폭 규칙 끔, 폭을
  오브젝트 크기에 비례). 버전은 0.4.1 유지(0.4.1은 아직 릴리스되지 않음; CHANGELOG 항목 갱신).
