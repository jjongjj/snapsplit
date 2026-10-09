# 수동 검증 체크리스트 (GUI 전용)

headless 테스트(`python3 tests/run_tests.py`)로 확인할 수 없는 모달·마우스·뷰포트 표시 항목.
각 항목을 Blender 4.5와 5.2에서 각각 실행하고 결과 표에 날짜·버전·결과(OK/NG + 메모)를 적는다.

### 자동화 현황 (`python3 tests/run_tests.py --gui`)

`tests/gui/gui_runner.py`가 GUI Blender(`--enable-event-simulate`, 비공개 TEMP)를 띄워 아래 단계를 실제 이벤트
(마우스 이동·클릭·키)로 실행하고 검증한다. 스크린샷은 `tests/_out/gui/<시나리오>_<버전>_<단계>.png`.

| 시나리오 | 자동으로 검증하는 것 |
|---|---|
| `qa1_preview_color` | QA-1: 프리뷰 평면이 Solid 뷰에서 주황(스크린샷 픽셀: 프리뷰 끔 대비 따뜻한 색 픽셀 비율), 재질 `diffuse_color` 주황, 토글 반복 후 고아 메쉬 0, 끄면 평면·X-Ray 정리 |
| `qa2_adjust` | QA-2: 마우스 드래그로 오프셋 변화 + 평면이 오프셋 위치로 이동, 좌클릭 확정(오프셋 유지·모달 종료), Enter 확정(프리뷰 끔 상태, 고아 메쉬 0), Esc 취소(메시지·평면·X-Ray 정리) |
| `qa3_connectors` | QA-3: 위에서 본 분할 큐브에서 프리뷰가 커서를 따라감(커서 광선∩시임 위치와 일치, 위치 변화), 좌클릭 시 커서 위치에 핀(핀 쪽 부피 +, 소켓 쪽 −, 돌출 정점이 목표 위치 근처), S 후 클릭은 반대 파트에 핀, 두 파트 매니폴드, 우클릭 취소 후 프리뷰·X-Ray 정리 |
| `qa4_freehand` | QA-4: 정면 뷰 Suzanne(머리 셸만)에 좌클릭 스트로크 → Shift 릴리스 축 스냅(평면 법선이 축과 일치) → Enter로 매니폴드 2파트, 부피 합 = 원본(±1 %), Esc는 변경 없음, 모달 중 파일 로드 시 `cancel()` 정리 |
| `adjust_undo_wheel`, `conn_undo` | 모달 중 undo/redo(크래시 회귀), undo 직후 프리뷰 사라짐 → 다음 마우스 이동에서 재생성 |
| `load_adjust`, `load_conn` | 모달 중 파일 로드 → `cancel()` 실행(로드 전 X-Ray 이유가 잡혀 있었고, 로드 후 해제 + 취소 메시지 출력) |

여전히 사람이 봐야 하는 것(자동화로 대체할 수 없는 이유):
- **시각적 품질**: 주황 평면이 "잘 보이는지", 와이어 프리뷰·스트로크 선·단면 루프 하이라이트가 읽기 쉬운지. 자동 검사는 색
  존재(픽셀 비율)만 보고 가독성은 판단하지 못한다. 스크린샷을 눈으로 확인한다.
- **실제 입력 장치 감각**: 드래그 감도(픽셀당 오프셋), 휠 단계, 태블릿/트랙패드. 시뮬레이션 이벤트는 정확한 좌표로 들어오므로
  손떨림·가속·`mouse_prev`가 거친 장치는 재현하지 않는다.
- **Ctrl+Z 단위**(QA-3 4단계): 키 입력 undo 단계가 사용자 기대(클릭 단위/전체)와 맞는지는 판단 문제라 기록만 한다.
- **Material Preview/Rendered 셰이딩**: 이 모드에서는 X-Ray가 없어 큐브 안 평면이 가려진다(현행 동작). 자동 검사는 Solid만 한다.

공통 준비
- 애드온 설치/활성화 후 새 파일(General). Scene Properties > Units: Metric, Length = Millimeters, Unit Scale = 1.0
  (headless/GUI 테스트 하니스와 같은 설정).
- 기본 큐브를 지우고 `Add > Mesh > Cube`를 **Size 40 BU**(이 설정에서 UI에는 "40 m"로 표시됨) 또는 Suzanne(Size 40 BU,
  Edit Mode에서 `Mesh > Clean Up > Fill Holes`)로 추가해 선택한다.
- 이유(현행 레거시 단위 규약): `utils.unit_mm()`은 Length = Millimeters **이고** Unit Scale = 1.0이면 1 BU = 1 mm로 본다
  (그 밖의 설정은 1 BU = 1 m). 따라서 이 설정에서 큐브를 "40 mm"(= 0.04 BU)로 만들면 핀·플러그 등 mm 단위 값이
  모델보다 1000배 크게(예: 핀 프리뷰 5 × 5 × 7.7 BU) 나온다. 기본 단위(Length = Meters, Unit Scale 1.0)에서 Size 0.04 m로
  만드는 것도 일관되지만, 테스트와 같은 위 설정을 기본으로 한다. Unit Scale ≠ 1.0(예: 0.001)은 아직 잘못 계산된다.
- **P1-1(`core/units.py`, `scale_length`·`length_unit` 전부 반영)이 들어오면 이 규약은 바뀐다**: 그때 "실제 40 mm" 기준으로
  이 준비 절차를 다시 쓴다.
- 3D 뷰포트 N 패널 > SnapSplit 탭을 연다. 콘솔(Window > Toggle System Console)을 켜 두고 오류를 확인한다.

---

## QA-1 분할 프리뷰 표시 (P0-6 GUI)

절차:
1. 큐브 선택, Split Axis = Z, Number of Parts = 3.
2. "Show split preview"를 켠다.
3. Split Axis를 X로 바꾸고, Number of Parts를 2로 바꾼다.
4. "Show split preview"를 끈다.

기대 결과:
- 2단계에서 큐브를 가로지르는 반투명 주황 평면 2개가 보이고(X-Ray 자동 켜짐), 콘솔에 `AttributeError ... shadow_method`가 없다.
- 3단계에서 평면이 X축 방향 1개로 즉시 갱신된다.
- 4단계에서 평면이 사라지고 X-Ray가 원래 상태로 돌아온다. Outliner에 `_SnapSplit_PreviewPlane_*` 오브젝트가 남지 않는다.

## QA-2 모달 분할 위치 조정 (`snapsplit.adjust_split_axis`)

절차:
1. 큐브 선택, Split Axis = Z, Parts = 2. "Show split preview" 옆의 "Adjust" 버튼을 누른다.
2. 마우스를 위아래로 움직이고, 휠/↑↓ 키로 미세 조정한다.
3. 좌클릭(또는 Enter)으로 확정한 뒤 "Planar Split"을 실행한다.
4. Ctrl+Z로 되돌린 다음 다시 "Adjust"를 실행하고 Esc로 취소한다.

기대 결과:
- 2단계에서 주황 평면이 마우스/휠을 따라 Z 방향으로 움직이고, Split Offset (mm) 값이 함께 바뀐다. 평면은 오브젝트 경계 밖으로 나가지 않는다.
- 3단계 분할 결과의 절단 높이가 마지막 평면 위치와 일치하고, 두 파트 모두 단면이 막혀 있다(캡).
- 4단계 Esc 후 정보 메시지 "Adjust split axis cancelled."가 뜨고 프리뷰 평면·X-Ray가 정리된다.
- 모달 중 대상 오브젝트가 사라지면(스크립트 삭제·undo) 오류 없이 "Adjust split axis cancelled."로 끝난다.

## QA-3 클릭 커넥터 배치 (`snapsplit.place_connectors_click`)

절차:
1. 큐브를 Z로 2분할한 뒤 두 파트를 모두 선택한다. Connector type = CYL_PIN.
2. "Place connectors (click)"를 누르고 마우스를 시임(절단면) 위로 움직인다.
3. 시임 위 서로 다른 세 곳을 좌클릭한다. 한 번 S 키를 눌러 핀/소켓을 바꾼 뒤 한 번 더 클릭한다.
4. Esc(또는 우클릭)로 종료한 뒤 Ctrl+Z를 반복한다.

기대 결과:
- 2단계에서 커서를 따라 커넥터 프리뷰가 시임 평면에 붙어 움직인다.
- 3단계에서 클릭한 위치마다 한쪽 파트에 핀, 반대쪽에 소켓이 생기고, S 이후 클릭은 핀/소켓 쪽이 반대로 생성된다. 두 파트는 매니폴드를 유지한다(3D Print Toolbox 또는 `Select > Select All by Trait > Non Manifold`로 선택 0개).
- 4단계 종료 후 프리뷰 오브젝트와 `_SnapSplit_Cutters` 컬렉션이 남지 않는다. Ctrl+Z 동작(한 번에 전체/클릭 단위 중 어느 쪽인지)을 메모한다(현행 동작 기록용, Phase 3에서 클릭 단위로 바꿀 예정).

## QA-4 Freehand 스트로크 컷 (`snapsplit.freehand_cut`)

절차:
1. Suzanne(구멍 메운 것) 선택. **눈은 별도 셸이므로 지운다**(Edit Mode에서 눈 위에 커서 → L → X). Freehand Cut 단계 B3은
   컷이 지나가지 않는 별도 셸이 있으면 "The source contains unrelated or uncut separate surface shells" 오류로 확정을 거부한다
   (현행 제한). 정면 뷰(Numpad 1), 패널의 "Freehand Cut" 버튼을 누른다.
2. 좌클릭 드래그로 모델을 가로지르는 사선을 그리고 놓는다. 다시 그릴 때는 Shift를 누른 채 놓아 축 스냅을 확인한다.
3. Enter로 확정한다.
4. Ctrl+Z 후 다시 실행하여 스트로크를 그리고 Esc로 취소한다.

기대 결과:
- 2단계에서 그리는 동안 스트로크 선이, 놓은 뒤에는 컷 평면 프리뷰(선택된 단면 루프)가 보인다. Shift 릴리스 시 평면이 가장 가까운 축 방향으로 스냅된다.
- 3단계에서 스트로크 방향의 평면으로 2파트가 생성되고 단면이 막혀 있다. 이후 "Add connectors"로 경사 시임에 커넥터가 배치된다.
- 4단계 Esc 후 헤더 텍스트·드로우 핸들러가 정리되고(뷰포트에 잔상 없음) 오브젝트 수가 실행 전과 같다.

---

## 스크립트(MCP·타이머)로 QA를 자동화할 때의 규칙

배경: 2026-10-09 Blender 5.2.2 크래시(`EXCEPTION_ACCESS_VIOLATION`, `IDP_GetPropertyFromGroup`에서 주소 0x18 읽기,
스택 바닥이 `py_timer_execute`). 원인은 Python이 보관한 `scene.snapsplit` 참조가 undo/redo 뒤에 해제된 메모리를 가리킨 것이다.
memfile undo/redo는 Scene ID 주소는 그대로 두고 ID 프로퍼티(= `scene.snapsplit` PropertyGroup)만 새로 읽어 들이므로,
Blender가 이 중첩 참조를 무효화하지 못하고 다음 읽기/쓰기가 use-after-free가 된다(Object 같은 ID 자체는 `ReferenceError`로 막힌다).
SnapSplit 타이머는 없으므로 타이머에서 읽은 쪽은 MCP 애드온이 실행한 QA 스크립트였다(`--enable-event-simulate` GUI 재현에서
같은 패턴으로 동일한 예외 주소·스택이 재현됨). 애드온의 모달(`adjust_split_axis`, `place_connectors_click`)도 같은 패턴을 갖고 있어 함께 수정했다.

규칙:
- **bpy 참조를 호출 사이에 보관하지 않는다.** `bpy.app.driver_namespace`, 모듈 전역, 클로저(`check_is_finished` 포함)에
  `scene.snapsplit`, `obj.modifiers[...]`, `mesh.vertices`, Area/Region/Space 등을 넣지 않는다. 이름(`obj.name`)·숫자만 저장하고
  매번 `bpy.context.scene.snapsplit`, `bpy.data.objects.get(name)`으로 다시 찾는다.
- **한 스크립트 안에서도** `bpy.ops.ed.undo()/redo()`, `wm.read_homefile/open_mainfile/revert_mainfile`, 애드온 disable/enable 뒤에는
  그 전에 얻은 참조(`p = scene.snapsplit` 등)를 버리고 다시 얻는다. 예: `p = bpy.context.scene.snapsplit; bpy.ops.ed.undo(); p.split_offset_mm` 금지.
- `event_timer_add`로 만든 타이머는 같은 스크립트(또는 `try/finally`)에서 `event_timer_remove`한다. 덮어쓰기(`driver_namespace["qa_timer"] = ...`
  재실행)로 이전 타이머를 잃어버리지 않는다.
- 모달을 스크립트로 띄운 채 undo를 실행하는 시나리오는 의도한 테스트일 때만 쓴다(실제 GUI에서는 모달이 Ctrl+Z를 가로챈다).
  회귀 테스트는 `tests/cases/test_modal_undo_safety.py`(headless)와 `python3 tests/run_tests.py --gui`
  (`tests/gui/gui_runner.py`: 모달 중 undo/redo·휠 입력, 커넥터 프리뷰 재생성, 모달 중 파일 로드 시 `cancel()` 정리를
  이벤트 시뮬레이션 GUI 인스턴스에서 확인. 실행 중 창을 건드리지 말 것).
- 사용자가 쓰는 Blender(MCP 서버 호스트)로 크래시 재현을 하지 않는다. 별도 인스턴스를 `--factory-startup`으로 띄우고,
  `TEMP`/`TMP`를 별도 폴더로 지정해 `%TEMP%\blender.crash.txt`·`quit.blend`를 덮어쓰지 않게 한다
  (WSL에서는 `WSLENV=TEMP:TMP`로 전달). `tests/run_tests.py`는 모든 Blender 하위 프로세스를 `tests/_out/tmp`로 돌리며,
  `bpy.app.tempdir`가 그 안에 있지 않으면 FAIL 처리한다.

---

## 결과 기록

| 항목 | Blender 4.5 | Blender 5.2 | 날짜/메모 |
|---|---|---|---|
| QA-1 분할 프리뷰 표시 | requires manual check | PARTIAL | 2026-10-09, 5.2.2 라이브 인스턴스(MCP 스크립트로 패널 속성 변경). Z/3파트 → 평면 2개(z=±6.7 mm), X-Ray 자동 켜짐, 콘솔 출력 없음(`shadow_method` 오류 없음); X/2파트 → X축 평면 1개로 즉시 갱신; 끄면 평면·`_SnapSplit_Preview` 컬렉션 제거, X-Ray 원복. **NG: 평면이 주황이 아니라 회색** — Solid 셰이딩(Color=Material)은 `diffuse_color`를 쓰는데 `build_orange_preview_material`은 노드(Emission)만 주황으로 설정(`diffuse_color`=0.8 회색). Material Preview에서는 X-Ray가 꺼져 큐브 안 평면이 안 보임. [z3](qa/qa1_52_preview_z3.png) [x2](qa/qa1_52_preview_x2.png) [off](qa/qa1_52_preview_off.png) |
| QA-2 모달 분할 위치 조정 | requires manual check | PARTIAL | 2026-10-09, 5.2.2 라이브: INVOKE_DEFAULT → `window.modal_operators`에 실행 중, 평면 표시·X-Ray 켜짐 [modal](qa/qa2_52_adjust_modal.png). 실제 마우스 이벤트로 오프셋 -1.9 mm·평면 z=-1.9 mm로 이동 확인. 오프셋 -1.9 mm로 Planar Split → 절단 높이 일치, 두 파트 비매니폴드 0. 모달 종료는 파일 로드(`cancel()`)로 확인: "분할 축 조정이 취소되었습니다", 모달·X-Ray 정리. 휠 입력·Esc 정리·undo/redo 중 안전성은 `run_tests.py --gui`(adjust_undo_wheel, load_adjust) PASS로 대체. 좌클릭/Enter 확정과 실제 드래그 감각은 사람 확인 필요. 참고: show_split_preview가 꺼진 채 조정하면 매 이벤트마다 프리뷰 평면이 삭제·재생성되어 고아 메쉬가 쌓임(17개 관찰) |
| QA-3 클릭 커넥터 배치 | requires manual check | PARTIAL | 2026-10-09, 5.2.2 라이브: 2파트 선택 + CYL_PIN에서 INVOKE_DEFAULT → 모달 실행, 와이어 핀 프리뷰가 시임 중앙에 표시, 상태바 "S: swap pin / socket (default) \| LMB: place \| RMB / Esc: cancel" [40 BU 큐브](qa/qa3_52_click_preview_40bu.png). 파일 로드 `cancel()`로 프리뷰·X-Ray 정리 확인. **NG(문서/단위)**: 공통 준비대로(Unit Scale 1.0, Size 40 mm = 0.04 BU) 하면 `unit_mm()`이 1.0을 돌려 핀 프리뷰가 5×5×7.7 BU(=5 m)로 큐브의 125배 [mm 씬](qa/qa3_52_click_preview_mm_scene.png); 레거시 단위 규약(1 BU = 1 mm, P1-1에서 수정 예정)대로 큐브를 40 BU로 만들어야 정상 크기. 커서 추종·클릭 배치·S 스왑·매니폴드·Ctrl+Z 단위는 미확인(사람 확인 필요). undo 후 프리뷰 재생성·Esc/파일 로드 정리는 `--gui`(conn_undo, load_conn) PASS |
| QA-4 Freehand 스트로크 컷 | requires manual check | PARTIAL | 2026-10-09, 5.2.2 라이브: 구멍 메운 Suzanne(40 BU, 비매니폴드 0), 정면 뷰에서 INVOKE_DEFAULT → 모달 실행, 헤더 "Draw with LMB \| Shift-release: axis snap \| Esc/RMB: exit" [modal](qa/qa4_52_freehand_modal.png). 활성 오브젝트 해제 → 다음 TIMER 이벤트에서 스스로 정리: 모달 종료, 헤더 텍스트 제거, `_ACTIVE_OPERATORS` 비움, 오브젝트 수 동일 [after](qa/qa4_52_freehand_after_cancel.png). 스트로크 그리기·Shift 축 스냅·Enter 확정·Esc는 마우스 입력이 필요해 미확인(사람 확인 필요; `--gui` 하네스에 freehand 시나리오 없음) |

자동 GUI 결과(`python3 tests/run_tests.py --gui`, 2026-10-09, `fix/qa-findings`):

| 시나리오 | Blender 4.5.5 | Blender 5.2.2 | 메모 |
|---|---|---|---|
| qa1_preview_color | PASS | PASS | 수정 전(2ac1865): 평면 회색(따뜻한 픽셀 0.0002 → 수정 후 0.0593), 고아 메쉬 누적 |
| qa2_adjust | PASS | PASS | 수정 전: 드래그 이벤트마다 평면 삭제·재생성으로 고아 메쉬 누적 |
| qa3_connectors | PASS | PASS | |
| qa4_freehand | PASS | PASS | Suzanne는 눈(별도 셸) 제거 후 사용 |
| adjust_undo_wheel / conn_undo / load_adjust / load_conn | PASS | PASS | |
