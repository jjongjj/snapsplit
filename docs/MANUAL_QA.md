# 수동 검증 체크리스트 (GUI 전용)

headless 테스트(`python3 tests/run_tests.py`)로 확인할 수 없는 모달·마우스·뷰포트 표시 항목.
각 항목을 Blender 5.2에서 실행하고 결과 표에 날짜·버전·결과(OK/NG + 메모)를 적는다(Phase 4부터 5.2 전용, 사용자 결정 2026-10-10;
아래 표의 4.5 열은 Phase 3까지의 기록).

### 자동화 현황 (`python3 tests/run_tests.py --gui`)

`tests/gui/gui_runner.py`가 GUI Blender(`--enable-event-simulate`, 비공개 TEMP)를 띄워 아래 단계를 실제 이벤트
(마우스 이동·클릭·키)로 실행하고 검증한다. 스크린샷은 `tests/_out/gui/<시나리오>_<버전>_<단계>.png`.

| 시나리오 | 자동으로 검증하는 것 |
|---|---|
| `p1_adjust_plane` | QA-5: 활성 컷 평면 gpu 오버레이가 보임(오버레이 끔 대비 주황 픽셀), `splitforge.cut_adjust_plane` 마우스 드래그로 평면이 법선 방향으로 이동, 휠 = 정확히 1 mm, 좌클릭 확정 후 **실제 Ctrl+Z / Ctrl+Shift+Z 키 이벤트**로 되돌리기·다시하기(오퍼레이터가 undo 단계 1개를 남김), X 키 축 정렬, Esc 복원, 모달 중 undo/redo 반복(크래시 회귀), 모달 중 파일 로드 → `cancel()` |
| `p1_panel` | QA-6: 사이드바 SplitForge 탭을 클릭으로 열고, 버튼 위치를 hover 스캔(`ui.copy_python_command_button`/`copy_data_path_button`)으로 찾아 **실제 클릭**: X 컷 추가 → Ctrl+Z/Ctrl+Shift+Z, 목록 체크박스로 활성 토글, Remove, Distribute(커넥터), Build(4파트 매니폴드, 원본 숨김·불변), Export(파트당 STL), Clear Build. 스크린샷 `panel_start`·`panel_built` → `docs/qa/p1_panel_<ver>.png` |
| `p2_stroke` | QA-7: 구멍 메운 Suzanne(눈 셸 포함) 정면 뷰에서 `splitforge.stack_add_stroke`를 실제 LMB 드래그로 S자 → 릴리스 후 스트로크·리본 프리뷰(비스듬한 뷰로 이동해도 유지, 따뜻한 픽셀 증가), Enter → STROKE 컷(방향 = 뷰 방향 +Y), 오버레이에 리본 면, **실제 Ctrl+Z/Ctrl+Shift+Z**, 모달 Build → 매니폴드 2파트 + "2 separate shell(s)" 정보(눈 통째로), 분리 표시 스크린샷, Esc/RMB 흔적 없음·핸들러 제거, Shift 릴리스 = 수평 직선(법선 Z), Redraw(같은 uid, 새 점), 그리는 중 파일 로드 → `cancel()` |
| `p2_build_progress` | QA-8: 13만 면 Suzanne에 스트로크 + X 평면 + Distribute, 모달 Build 중간에 **창 전체 스크린샷**(상태바 "SplitForge Build: … (n/m)"), 진행 단계(A/B 쪽, 커넥터) 마지막 = 합계, 4파트 매니폴드; 재빌드 중간 Esc → 이전 파트·메시 그대로, "Build cancelled" |
| `p3_connector_click` | QA-9: Z 컷 큐브 위에서 본 뷰에서 `splitforge.connector_add_click` — 프리뷰(gpu 오버레이, 초록)가 커서 아래 시임 위치를 따라감, 모달 중 오브젝트·컬렉션 생성 없음, 실제 LMB 3회 = 커서 위치(±0.5 mm)에 커넥터 3개, S 후 클릭은 핀 쪽 B, 물체 밖 클릭은 무시, **실제 Ctrl+Z 3회로 하나씩 제거·Ctrl+Shift+Z 3회로 복원**(모달 중), Esc 후에도 클릭당 undo 1단계, Build 매니폴드, 파일 로드 → `cancel()`·핸들러 제거 |
| `p3_connector_types` | QA-10: 180×30×30 막대에 Z 컷 + 8종 커넥터(원기둥 핀·사각 테논·도브테일·스냅 핀/테논/도브테일·커스텀 육각 메시·도웰) → Build: A, B, `GUI_Bar_Dowel_1`, 분리 스크린샷(위에서 소켓, 아래에서 핀) |
| `p4_points` | QA-11: 정면 뷰에서 `splitforge.stack_add_polyline` — 실제 LMB 클릭 4번(점이 클릭 위치 ±0.5 mm, 날카로운 꼭짓점 그대로), 모달 중 **실제 Ctrl+Z**가 마지막 점 삭제, 다시 클릭, 비스듬한 뷰로 이동해도 프리뷰 유지, Enter → POLYLINE 컷, 끝난 뒤 실제 Ctrl+Z/Ctrl+Shift+Z(컷당 1단계), Esc/RMB 흔적 없음; 위 뷰에서 `stack_add_polygon`(깊이 10) 꼭짓점 4번 + **첫 점 클릭으로 닫기**, 도려내기 바닥에 `connector_add_click` 실제 클릭(바닥 위치), 모달 Build → 파트 3개(플러그·포켓 몸체·아래) 매니폴드, 분리 스크린샷, 점 찍는 중 파일 로드 → `cancel()` |
| `p4_fix` | QA-12: 회전·스케일·뒤집힌 면·미터 씬 큐브. 사이드바 버튼을 hover 스캔으로 찾아 **실제 클릭**: Check Mesh → 법선 행의 Fix → 법선 바깥; 변환 Fix → 스케일 1·회전 0, 컷 평면(원점 밖)이 월드에서 그대로; **실제 Ctrl+Z/Ctrl+Shift+Z**; 단위 Fix → 대화상자에서 Enter(Keep Units) → Millimeters·0.001 |
(레거시 시나리오 `qa1_preview_color`·`qa2_adjust`·`qa3_connectors`·`qa4_freehand`·`adjust_undo_wheel`·`conn_undo`·`load_adjust`·`load_conn`은
레거시 코드와 함께 Phase 3에서 삭제. 해당 기능의 새 시나리오: QA-5 `p1_adjust_plane`(조정 모달·모달 중 undo·파일 로드), QA-7 `p2_stroke`(곡선 컷),
QA-9 `p3_connector_click`(클릭 배치).)

여전히 사람이 봐야 하는 것(자동화로 대체할 수 없는 이유):
- **시각적 품질**: 주황 평면이 "잘 보이는지", 와이어 프리뷰·스트로크 선·단면 루프 하이라이트가 읽기 쉬운지. 자동 검사는 색
  존재(픽셀 비율)만 보고 가독성은 판단하지 못한다. 스크린샷을 눈으로 확인한다.
- **실제 입력 장치 감각**: 드래그 감도(픽셀당 오프셋), 휠 단계, 태블릿/트랙패드. 시뮬레이션 이벤트는 정확한 좌표로 들어오므로
  손떨림·가속·`mouse_prev`가 거친 장치는 재현하지 않는다.
- **Ctrl+Z 단위**(QA-3 4단계): 키 입력 undo 단계가 사용자 기대(클릭 단위/전체)와 맞는지는 판단 문제라 기록만 한다.
- **Material Preview/Rendered 셰이딩**: 이 모드에서는 X-Ray가 없어 큐브 안 평면이 가려진다(현행 동작). 자동 검사는 Solid만 한다.

공통 준비
- 애드온 설치/활성화 후 새 파일(General). Scene Properties > Units: Metric, Length = Millimeters, **Unit Scale = 0.001**
  (표준 3D 프린트 설정, headless/GUI 테스트 하니스와 같은 설정: 1 BU = 1 mm).
- 기본 큐브를 지우고 `Add > Mesh > Cube`를 **Size 40 mm**(= 40 BU, UI에 "40 mm"로 표시) 또는 Suzanne(Size 40 mm,
  Edit Mode에서 `Mesh > Clean Up > Fill Holes`)로 추가해 선택한다.
- 단위 규약(P1-1 `core/units.py`, 레거시 `utils.unit_mm()`도 이것을 쓴다): Blender 표시와 같다 — **1 BU = Unit Scale m**.
  애드온의 mm 값은 언제나 Blender가 mm로 보여 주는 값과 같다. Millimeters + 0.001 → 1 BU = 1 mm, Meters + 1.0 → 1000 mm,
  Millimeters + 1.0 → 1000 mm(40 BU 큐브가 "40000 mm"). 패널 상단에 실제 "1 unit = … mm"가 보이며, Export STL/OBJ는 항상 mm로 쓴다.
- 3D 뷰포트 N 패널 > **SplitForge** 탭을 연다(Draft/Easy 패널; 레거시 SnapSplit UI는 Phase 3에서 제거).
  콘솔(Window > Toggle System Console)을 켜 두고 오류를 확인한다.

---

## QA-11 폴리라인·폴리곤 컷 (`splitforge.stack_add_polyline` / `stack_add_polygon`, P4-1/P4-2 GUI)

절차:
1. 큐브(40 mm) 선택, 정면 뷰. Draft 컷 목록 옆 직선 아이콘(Add Polyline Cut). 큐브를 가로질러 점 4개를 클릭한다(한 번은 Ctrl을 누른 채).
   Backspace(또는 Ctrl+Z)로 마지막 점을 지우고 다시 찍은 뒤 뷰를 돌려 보고 Enter.
2. 위 뷰(Numpad 7)에서 원 아이콘(Add Polygon Cut). 윗면 위에 사각형 꼭짓점 4개를 찍고 첫 점을 다시 클릭해 닫는다. 컷 상자에서 Depth 10.
3. Connectors 패널에서 Click → 도려낸 영역 안을 클릭, Enter. Build.
4. 아무 점 컷이나 시작해 Esc / 우클릭.

기대 결과:
- 1단계: 클릭마다 점(주황)과 커서까지의 고무줄 선, 유효하면 리본 윤곽선이 보이고(커서를 움직여도 유지) 헤더에 점 개수·키 안내.
  Ctrl 클릭은 화면에서 15° 단위 방향. 꼭짓점은 매끄럽게 되지 않는다. 확정하면 컷 목록에 "Polyline n".
- 2단계: 첫 점 클릭으로 닫히며 "Polygon n" 추가, 오버레이에 프리즘(바닥은 깊이 10 위치).
- 3단계: 커넥터가 바닥(윗면에서 10 mm 아래)에 놓이고, Build 결과는 플러그(위로 들어 올리면 핀) + 포켓이 있는 몸체 + 폴리라인 아래쪽.
- 4단계: 컷·오브젝트가 생기지 않고 헤더 안내가 사라짐. 잘못된 점(자기 교차, 물체 밖)은 Enter 시 헤더와 보고에 이유.

## QA-12 출력 검사와 Fix 버튼 (P4-3 GUI)

절차:
1. 기본 씬(미터)에서 큐브를 회전·스케일하고 Edit Mode에서 면 하나를 뒤집는다(Flip). Z 컷을 하나 추가하고 원점을 옮긴다.
2. 패널 맨 위 Print checks에서 Check Mesh. 각 행의 Fix를 차례로 누른다(법선 → 변환 → 단위). 단위 대화상자에서 Keep Units / Keep Size 비교.
3. 각 Fix 뒤 Ctrl+Z / Ctrl+Shift+Z.

기대 결과:
- 실패한 검사만 Fix 버튼, 문구가 잘리지 않음. 법선 Fix 뒤 행이 체크로 바뀜(메시 검사 다시 실행).
- 변환 Fix 뒤 컷 평면이 화면에서 움직이지 않음(스택이 메시와 함께 변환), 정보 메시지에 적용한 스케일과 유지한 컷 수.
- Keep Units: 숫자 그대로 mm로 표시, Keep Size: 실제 크기 유지(큐브가 1000배 단위로 커짐, 스케일 미적용 경고).
- Ctrl+Z 한 번에 Fix 하나가 되돌려짐.

## QA-5 컷 평면 모달 조정 (`splitforge.cut_adjust_plane`, P1-4/P1-12 GUI)

절차:
1. 큐브 선택, SplitForge 패널 Draft 모드에서 컷 목록 옆 **Z** 버튼으로 컷 추가. 주황 반투명 사각형(활성 컷)이 큐브 중앙에 보인다.
2. "Adjust in Viewport"를 누르고 마우스를 위아래로 움직인다. 휠(1 mm), Ctrl+휠(0.1 mm), X/Y/Z 키를 눌러 본다.
3. 좌클릭(또는 Enter)으로 확정 → Ctrl+Z → Ctrl+Shift+Z.
4. 다시 Adjust → 움직인 뒤 Esc.

기대 결과:
- 2단계에서 평면이 법선 방향으로 마우스를 따라 움직이고, 헤더에 `Cut offset +x.xx mm` 안내가 보인다. X/Y/Z는 현재 위치에서 법선을 해당 축으로 바꾼다.
- 3단계 Ctrl+Z 한 번에 조정 전 평면으로, Ctrl+Shift+Z로 조정 후 평면으로 돌아간다.
- 4단계 Esc 후 평면이 모달 시작 전 위치·방향으로 돌아오고 헤더 안내가 사라진다.

## QA-7 곡선(스트로크) 컷 (`splitforge.stack_add_stroke`, P2-4 GUI)

절차:
1. 구멍 메운 Suzanne(눈 셸 그대로) 선택, 정면 뷰(Numpad 1). Draft 컷 목록 옆 곡선 아이콘(Add Stroke Cut)을 누른다.
2. 좌클릭 드래그로 모델을 가로지르는 S자를 그리고 놓는다. 마우스 휠/중클릭으로 뷰를 돌려 리본을 확인한다. Enter.
3. Ctrl+Z → Ctrl+Shift+Z. Build. 다시 Add Stroke Cut → 그린 뒤 Esc, 한 번 더 그린 뒤 Shift를 누른 채 놓고 Enter.
4. 첫 스트로크 컷을 선택하고 "Redraw in Viewport"로 다시 그린 뒤 Enter. 자기 자신과 교차하는 고리를 그리고 Enter를 눌러 본다.

기대 결과:
- 2단계: 그리는 동안 주황 선, 놓으면 리본(오브젝트 깊이 앞뒤 선 + 끝 세로선)이 보이고 헤더에 "Enter: confirm cut". 확정 후 오버레이에 주황 반투명 리본 면.
- 3단계: Ctrl+Z 한 번에 컷이 사라지고 Ctrl+Shift+Z로 돌아온다. Build는 진행률을 보이며 매니폴드 2파트, 정보 "2 separate shell(s) not crossed by any cut stay whole …"
  (주둥이 아래 컷이면 눈은 통째로 위쪽 파트). Esc는 아무것도 남기지 않는다(헤더·선 사라짐). Shift 릴리스는 수평/수직 직선 컷.
- 4단계: Redraw는 같은 컷(이름·커넥터 유지)의 모양만 바꾼다. 고리는 "The stroke crosses itself …" 경고와 함께 확정이 거부되고 다시 그릴 수 있다.

## QA-8 대형 메시 Build 진행률 (P2-6 GUI)

절차: Suzanne(Subdivision 4~5 적용) + 스트로크 컷 + 평면 컷 + Distribute, Build. 진행 중 Esc로 한 번 취소한 뒤 다시 Build.

기대 결과: 진행 중 커서 진행률 숫자와 하단 상태바 "SplitForge Build: Stroke 1: side A (1/4)" 같은 텍스트가 갱신되고, UI가 단계 사이에 다시 그려진다.
**알려진 제한**: 상태바 텍스트는 각 불리언 단계 *시작 전에* 갱신되지만, 한 단계(불리언 1회) 동안은 Blender가 응답하지 않는다(UI 정지, Esc도 그 단계가
끝난 뒤 처리). Accurate 품질에서 51만 면 S자 컷은 단계 하나가 ~30 s; Auto/Fast(MANIFOLD)에서는 ~0.7 s. Settings > Booleans로 고른다.
Esc는 진행 중인 불리언 단계가 끝난 뒤 멈추고 경고 "Build cancelled; the previous result is unchanged" — 이전 파트 그대로.

## QA-6 Draft 패널 → Build → Export (P1-12 GUI)

절차:
1. 큐브 선택, Z·X 컷 추가. 목록 체크박스로 한 컷을 껐다 켠다. X 컷을 선택하고 Connectors > Distribute.
2. Build & Export > **Build**. 그 다음 Export 폴더를 지정하고 **Export Parts**. 마지막으로 Clear Build(X 아이콘).

기대 결과:
- 1단계 Distribute 후 X 컷 시임의 두 영역(Z 컷 위/아래)에 커넥터가 2개씩(노란 원 + 핀 쪽 표시 선) 보인다.
- 2단계 Build 후 원본은 숨겨지고(데이터 불변) `SplitForge_Build_Cube` 컬렉션에 매니폴드 파트 4개(`Cube_AA`…)가 생기며,
  파트를 선택해도 패널은 원본의 스택("Part of Cube")을 보여 준다. Rebuild는 같은 컬렉션을 교체한다(오브젝트 누적 없음).
  Export는 파트당 파일(mm 단위)을 쓴다. Clear Build는 파트·컬렉션을 지우고 원본을 다시 보이게 한다.

## QA-9 클릭 커넥터 배치 (`splitforge.connector_add_click`, P3-5 GUI)

절차:
1. 큐브에 Z 컷(갭 0.4). Connectors > New connectors에서 종류(예: Cylinder pin) 선택. 위에서 본 뷰(Numpad 7).
2. **Click**을 누르고 마우스를 시임 위로 움직인다. 서로 다른 세 곳을 좌클릭, 한 번은 그 전에 S.
3. 물체 밖과 가장자리(벽 0.4 mm 미만)를 클릭해 본다. Ctrl+Z 세 번, Ctrl+Shift+Z 세 번. Enter(또는 Esc/RMB).
4. Build. 스트로크 컷에서도(정면에서 그린 S자를 위에서) 클릭해 본다.

기대 결과:
- 2단계: 커서 아래 시임 위치에 커넥터 윤곽(초록, 물체 밖은 빨강)과 핀 방향 선, 헤더에 "U … V … mm | pin side A".
  클릭한 자리에 커넥터가 생기고(목록·노란 오버레이), S 이후는 핀 쪽 B. 프리뷰용 오브젝트·컬렉션은 생기지 않는다.
- 3단계: 물체 밖 "Outside the object", 가장자리 "Does not fit here: would break through the surface"(추가 안 됨).
  Ctrl+Z 한 번에 커넥터 하나씩 사라지고 Ctrl+Shift+Z로 돌아온다(모달 중에도, 끝난 뒤에도).
- 4단계: 클릭한 자리에 핀/소켓. 곡선 시임에서는 리본 위 커서 아래 위치에 놓인다.

## QA-10 커넥터 종류 (P3-1~P3-3 GUI)

절차: 긴 막대(180×30×30)에 Z 컷, 커넥터 목록의 활성 커넥터 상자에서 종류를 바꿔 가며 8종을 하나씩 추가(커스텀은 육각 뿔대 메시 지정),
Build 후 A 파트를 위로 옮겨 아래에서 본다.

기대 결과: 원기둥 핀, 사각 테논, 끝이 좁은 도브테일, 돌기 달린 스냅 핀/테논/도브테일, 커스텀 메시 모양 핀이 A 아래에, 같은 모양의 소켓
(공차만큼 큼, 스냅은 딤플 포함)이 B 위에 있다. 도웰 위치에는 양쪽 모두 구멍, 막대 +X 쪽에 눕힌 `GUI_Bar_Dowel_1`.
커스텀 메시를 열린 메시로 바꾸면 패널 경고(빨강)와 Build 경고 "not a closed manifold … skipped".

(QA-1~QA-4는 레거시 SnapSplit 기능(분할 프리뷰, Adjust Split Axis, 레거시 클릭 배치, Freehand Cut)으로 Phase 3에서 코드와 함께 삭제.
아래 결과 기록은 이력으로 남긴다.)

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
- **라이브 세션에서 애드온 코드를 바꾼 뒤에는 disable/enable만으로는 새 코드가 로드되지 않는다**(파이썬 모듈 캐시).
  disable → `sys.modules`에서 `bl_ext.<repo>.<pkg>`와 `bl_ext.<repo>.<pkg>.*`를 모두 삭제 → enable 순서로 다시 읽는다.
  모달이 떠 있지 않은지 먼저 확인한다(`window.modal_operators` 비어 있음). 예:
  ```python
  import bpy, sys
  mod = "bl_ext.splitforge_dev.splitforge"   # 이름 변경 전 레포: bl_ext.splitforge_dev.snapsplit
  bpy.ops.preferences.addon_disable(module=mod)
  for k in [k for k in sys.modules if k == mod or k.startswith(mod + ".")]:
      del sys.modules[k]
  bpy.ops.preferences.addon_enable(module=mod)
  ```
  (참고: `/mnt/c/code/snapsplit_probe/mcp/qa3/reload2.py`.) 패키지 폴더가 `snapsplit/`→`splitforge/`로 바뀌었으므로
  라이브 extension 레포의 폴더도 새 이름으로 맞춰야 한다.
- 사용자가 쓰는 Blender(MCP 서버 호스트)로 크래시 재현을 하지 않는다. 별도 인스턴스를 `--factory-startup`으로 띄우고,
  `TEMP`/`TMP`를 별도 폴더로 지정해 `%TEMP%\blender.crash.txt`·`quit.blend`를 덮어쓰지 않게 한다
  (WSL에서는 `WSLENV=TEMP:TMP`로 전달). `tests/run_tests.py`는 모든 Blender 하위 프로세스를 `tests/_out/tmp`로 돌리며,
  `bpy.app.tempdir`가 그 안에 있지 않으면 FAIL 처리한다.

---

## P1 라이브 검증 (Blender 5.2.2, 공식 MCP, 2026-10-09, develop e148026)

독립 검증자(verifier)가 사용자 세션 Blender 5.2.2에서 MCP 스크립트(`/mnt/c/code/snapsplit_probe/mcp/qa4/`)로 실행.
안전 규칙 준수: MCP로 undo 없음, bpy 참조 보관 없음, 타이머 없음, 프리퍼런스 리셋 없음, MCP 애드온 미변경.

1. 재로드(`qa4/reload.py`): `bl_ext.splitforge_dev.snapsplit` disable → `bl_ext.splitforge_dev.*` 13개 `sys.modules`에서 삭제 →
   `extensions.repo_refresh_all` → `bl_ext.splitforge_dev.splitforge` enable. 로드 경로 `C:\code\snapsplit-develop\splitforge\__init__.py`,
   `Scene.splitforge`·`Object.splitforge_stack`·`splitforge.*` 오퍼레이터 등록, `SNAP_PT_panel`은 `bl_parent_id=SPLITFORGE_PT_main`, `DEFAULT_CLOSED`.
2. 검증(`step1`): mm 씬(Millimeters, 1.0)에 40 BU 큐브 `QA4_Cube` → `splitforge.validate` "Mesh is ready", 리포트 전부 OK.
3. 컷(`step2`): Z 컷(offset −5 mm) + 임의 각도 컷(origin (3,0,0), normal (1,0.6,0.35) → (0.821,0.493,0.288), gap 0.5 mm),
   각 컷 Distribute → 시임 영역별 2개씩, 컷당 4개(총 8개). 오버레이: 활성 컷 주황, 다른 컷 파랑, 커넥터 노란 원 [패널](qa/p1_live_52_draft_panel.png).
4. Build(`step3`): FINISHED, `SplitForge_Build_QA4_Cube`에 4파트(AA/AB/BA/BB) 모두 매니폴드, 경고 없음, 원본 정점 해시 빌드 전후 동일
   (`752b1341…`), 원본 숨김·모디파이어 0·scale 1, 새 오브젝트 4·메쉬 4, 고아 메쉬 0, `_SplitForge_Operand` 잔존 없음.
   부피 합 62894.7 mm³(원본 64000 − 갭 − 소켓/핀 차) [파트](qa/p1_live_52_parts.png).
5. Easy Cut(`step4`): 원기둥(r 15, h 50) `splitforge.easy_cut(axis='Z', offset_mm=4)` → 스택 1개(커넥터 2), 매니폴드 2파트
   (14996.8 / 20203.8 mm³, 핀·소켓 반영 수치와 일치), 원본 불변. 패널 Easy 모드·Build & Export·접힌 Settings/Legacy [Easy 패널](qa/p1_live_52_easy_panel.png).
6. Export: `splitforge.export_parts(directory=…\qa4\out\stl, formats={'STL'})` → 파트당 STL 4개(26–33 KB). WSL에서 파싱: 부피 합 62894.7 mm³
   (Blender 값과 일치 → mm 단위 기록), bbox ±20 mm 범위.

결과: PASS, 단 아래 결함 확인.
- **[중간] 임의 각도 컷의 자동 커넥터가 외곽을 뚫음**: 위 4단계 큐브에서 경사 컷 커넥터 4개 모두 핀이 큐브 외곽(±20 mm) 밖으로
  0.4–1.65 mm 나가고, 커넥터 2의 소켓은 외벽을 0.94 mm 관통(`qa4/probe_protrude.py`). 조립 상태에서 외면에 초승달 모양 돌기/구멍이 보인다
  [스크린샷](qa/p1_live_52_exterior_artifacts.png). `distribute_points`는 중심만 시임 안에 두고 커넥터 반경·기울어진 핀 축과 벽의 거리를
  보지 않는다(P1-8 수용 기준 범위 밖). 축 정렬 컷(40 mm 큐브, 원기둥)에서는 발생하지 않음. 빌드 경고도 없음.
- [낮음] 단위 표시 차이(P1-1 사용자 결정 대기): 패널 Origin X가 3 BU를 "3000 mm"로 표시.
- [낮음] UI 목록이 좁은 사이드바에서 컷 이름이 잘림("C…", "gap …").

후속 수정(fix/p1-followups, 2026-10-09):
- 외곽 관통(D1) → Distribute가 시임 영역을 커넥터 반경+클리어런스+벽 0.4 mm만큼 안쪽으로 줄이고, 핀·소켓(양쪽 핀 방향 모두)을
  3D로 원본 안에 있는지 검사해 안 맞으면 영역 중심 쪽으로 옮기거나(이미 놓인 커넥터와 겹치지 않게) 버리고 경고한다. Build는 원본
  밖으로 나가는 커넥터(수동 배치 포함)를 경고와 함께 건너뛴다. 위 재현(Z −5 + 경사 컷)은 `tests/cases/test_connectors_fit.py`:
  경사 컷 커넥터 4개 모두 안쪽으로 이동, 빌드 경고 0, 모든 파트 정점이 큐브(±20 mm) 안.
- 단위 → 사용자 결정대로 Blender 표시 규약(1 BU = Unit Scale m). 표준 준비가 Millimeters + Unit Scale 0.001로 바뀌어 Origin도 mm로 표시.
- 목록 잘림 → 컷 목록은 체크박스+이름만, 갭·커넥터 수는 아래 상자에 표시. 커넥터 목록은 "1 Pin  pin A".

D7 수정(fix/d7-crosscut, 2026-10-09): 다른 컷을 넘어 세 번째 파트로 들어가는 핀/소켓(재현: Z −6 + 법선 (1,0.2,1.2) gap 0.5,
Z 컷 커넥터가 BB로 2.64 mm)을 Distribute가 옮기거나 버리고, Build는 "reach across another cut" 경고와 함께 건너뛴다
(`tests/cases/test_connectors_crosscut.py`). 함께 수정: 컷이 지나가지 않는 내부 공동(별도 셸)의 법선이 캡 처리 중 뒤집혀
공동이 부피로 바뀌던 버그, 내부 판정의 칼날 모서리 오판, 샘플 간격보다 얇은 내부 특징 관통.

---

## P1 후속 수정 라이브 검증 (Blender 5.2.2, 공식 MCP, 2026-10-09, develop fafaed4)

독립 검증자(verifier), 스크립트 `/mnt/c/code/snapsplit_probe/mcp/qa5/`, 같은 안전 규칙(MCP undo·참조 보관·타이머·프리퍼런스 리셋 없음).

1. 재로드(`qa5/reload.py`): disable → `bl_ext.splitforge_dev.splitforge*` 39개 `sys.modules` 삭제 → enable. 새 `connectors/fit.py` 로드, `units.LENGTH_UNIT_MM` 없음(새 규약).
2. 씬 Metric + Millimeters + **Unit Scale 0.001** → `bu_to_mm_factor` 1.0, validate "Mesh is ready: … 1 unit = 1 mm", `mm_per_unit` 1.0.
3. 재현(`qa5/scenario.py`, 40 mm 큐브 y=100): Z −5 + 경사 컷(origin (3,0,0), normal (1,0.6,0.35), gap 0.5) → Distribute
   "3 connector(s) on Cut Z", "4 connector(s) on Cut 2, 4 moved inward to fit" → Build 경고 0, 4파트 매니폴드, 원본 해시 불변,
   **모든 파트 정점이 큐브(±20 mm) 안(최대 바깥 0.0)**, 파트 간 상호 관입(레이 패리티) 없음, 고아 메쉬 0.
   외면 돌기·구멍 없음(이전 QA4 큐브와 나란히) [파트](qa/p1f_live_52_parts.png).
4. 패널: "Part of QA5_Repro / Editing the source's cuts", "1 unit = 1 mm", 컷 목록 "Cut Z"/"Cut 2" 잘림 없음, "Gap 0.5 mm, 4 connector(s)",
   Origin X **3 mm**(이전 "3000 mm"), 커넥터 목록 "1 Pin pin A", "Pin on A (+N)" [패널](qa/p1f_live_52_panel.png).
5. Export STL(`qa5/out/stl`) → WSL 파싱: 좌표 mm(bbox x −20..20, y 80..120, z −20..20), 부피 합 62886.3 mm³ = Blender 값.

결과: 후속 수정(단위·D1 외곽·D3–D6) PASS. **새 결함(D7, 중간~높음)**: 가파른 경사 컷(`QA5_Steep`: Z −6 + normal (1,0.2,1.2),
origin (0,0,2), gap 0.5)에서 Z 컷 커넥터 1의 핀(AA 쪽, 중심 (16.4,−14,−6))이 경사 컷 너머 세 번째 파트 BB 안으로 최대 2.64 mm 들어간다
(BB에는 소켓 없음 → 조립 불가). `fit.worst_depth`는 원본 외곽만 검사하고 다른 컷의 시임/갭은 보지 않으며, 2D inset은 시임 평면에서만
적용되어 핀의 법선 방향 길이와 기울어진 다른 컷 평면을 고려하지 않는다. headless 재현은 같은 장면(검증자 스크래치 케이스).
빌드 경고 없음. 제안: 핀·소켓 샘플을 원본 대신 컷 후 조각(pin 조각 ∪ socket 조각) 기준으로 검사.

---

## D7 수정 라이브 검증 (Blender 5.2.2, 공식 MCP, 2026-10-09, develop ff7ecdb)

독립 검증자, 스크립트 `/mnt/c/code/snapsplit_probe/mcp/qa6/`, 같은 안전 규칙. Millimeters + Unit Scale 0.001.

1. 재로드(`qa6/reload.py`): `bl_ext.splitforge_dev.splitforge*` 40개 purge 후 enable.
2. `QA5_Steep`(Z −6 + normal (1,0.2,1.2), gap 0.5)을 **저장된 옛 커넥터 그대로** Rebuild(`qa6/steep.py`): 경고 3건
   "Cut Z connector 1/2, Cut 2 connector 3: … reach across another cut into a part without a socket, skipped", 4파트 매니폴드,
   모든 정점 큐브 안, **AA 핀이 BB로 2.64 mm 들어가던 관입 사라짐**.
3. Distribute 다시(컷당 2개, "2 position(s) dropped") → Rebuild 경고 0, 4파트 매니폴드, 외곽 밖 0, 파트 간 관입 없음
   (레이 패리티 probe가 AA↔AB 1정점 0.2 mm를 표시했으나 `fit.is_inside`로 재확인 시 0건 → probe 쪽 레이 스침 오탐), 고아 메쉬 0
   [스크린샷](qa/p1d7_live_52_steep.png): 분해 표시한 4파트, 오버레이, 패널 "Gap 0.5 mm, 2 connector(s)".

headless 적대 케이스(검증자 스크래치, 커밋 안 함): 컷 3개(Z + 경사 2개), 벽 8 mm 중공 박스(공동 관통 컷), 벽 3 mm 중공, L자(경사 컷 2개),
0.6 mm 슬롯 — 모두 매니폴드·원본 밖 정점 0·파트 간 관입 0. 공동을 지나지 않는 컷은 공동을 유지(부피 42176 = 56000 − 24³).
슬롯에 걸친 수동 커넥터는 경고와 함께 건너뜀. 이전 재현 3종(repro/steep/shallow) 관입 0.

열린 항목:
- [중간~낮음] D8: 벽 8 mm 중공 박스(핀 Ø5 + 클리어런스 + 벽이 들어갈 공간 있음)에 기본 설정(LINE 2개, margin 15 %) Distribute → 커넥터 0개
  ("No connector fits"). LINE은 선 위 구간 중앙(v)만 고르고 u 방향 벽 위치를 찾지 않으며, 2D inset에서 걸러진 점은 dropped에도 세지 않는다.
  수동 (−16, 0)은 정상 빌드. GRID 5×5도 0개.
- [낮음] Distribute 경고 문구가 다른 컷 때문에 버린 경우에도 "would break through the surface"라고 표시.
- [낮음] Build의 `max_step`(1 mm 샘플 간격) 전달을 지우는 뮤테이션은 테스트가 잡지 못함.

---

## P2 곡선 컷 라이브 검증 (Blender 5.2.2, 공식 MCP, 2026-10-09, develop 29cd845)

독립 검증자(verifier), 스크립트 `/mnt/c/code/snapsplit_probe/mcp/qa7/`, 같은 안전 규칙(MCP undo·참조 보관·타이머·프리퍼런스 리셋 없음,
MCP 애드온 미변경). Millimeters + Unit Scale 0.001. 마우스로 그리기는 MCP로 할 수 없으므로 스트로크는 오퍼레이터
`splitforge.stack_add_stroke(points=…, direction=(0,1,0))`(레코드 API)로 만들었다 — 실제 LMB 드래그·Shift·Enter·Esc는 `--gui` p2_stroke가 담당.

1. 재로드(`qa7/reload.py`): `bl_ext.splitforge_dev.splitforge*` 40개 purge 후 enable, 로드 경로 `C:\code\snapsplit-develop\splitforge`, `cuts.stroke` 로드.
2. 40 mm 큐브(`QA7_Cube`, x=−40)에 S자(진폭 7, 점 50 → 정리 후 147점, 방향 +Y), gap 0.5, Distribute 3 → 시임 위 3개
   (u −15.45/−0.07/15.30). Build(`qa7/scenario.py`): 2파트 매니폴드(31853.6 + 31206.0 = 63059.6 mm³ = 64000 − 갭 − 핀/소켓 차),
   불리언 EXACT×4(폴백 없음), 파트 관입 0, 경고 0, 원본 해시 불변·숨김·모디파이어 0, `_SplitForge_*` 잔존 0, 고아 메쉬 0.
3. 구멍 메운 Suzanne(눈 셸 포함, `QA7_Monkey`, 3셸 17636.6 mm³), 주둥이 아래 S자(z −6, gap 0.5): 2파트 매니폴드, EXACT_SELF로 시작
   (소스 셸 교차 감지), 정보 "2 separate shell(s) not crossed by any cut stay whole in the part that contains them", 눈은 위쪽 파트 A
   (EXACT_SELF가 머리와 합침, A 1셸), 부피 합 17121.2(= 원본 − 눈/머리 겹침 − 갭), 관입 0, 원본 불변. 여기서는 Distribute가 0개
   ("2 would break through the surface, 1 no room" — 주둥이 단면이 얇음, 정상 거부).
4. 이마 S자(`QA7_Monkey2`, z 13, gap 0.5): Distribute 1개(2개 "too close"), Build 2파트 매니폴드·관입 0·같은 눈 정보, 커넥터 UNION은
   EXACT_SELF "not manifold" → MANIFOLD 폴백(체인이 라이브에서 동작), DIFFERENCE EXACT_SELF. 파트 A에 브로 위 작은 섬 2개(컷 위쪽의
   눈썹 돌기, 기하학상 정상).
5. 스크린샷: 큐브 S 리본 오버레이(주황 리본 + 노란 커넥터 원)와 패널("Stroke 1", "Gap 0.5 mm, 1 connector(s)", "Stroke: 124 points",
   "Redraw in Viewport", 커넥터 U/V, Rebuild, "2 part(s)") [리본+패널](qa/p2_live_52_cube_ribbon_panel.png),
   Suzanne 리본 [Suzanne](qa/p2_live_52_monkey_ribbon.png), 분해 표시한 큐브 파트(B의 곡면 시임에 소켓 구멍)
   [큐브 파트](qa/p2_live_52_cube_parts.png), 눈이 위쪽 파트에 남은 Suzanne 파트 [Suzanne 파트](qa/p2_live_52_monkey_parts.png).
   (패널은 `wm.call_panel` 팝업이라 열린 채 남아 Monkey2 스택을 보여 줌.)

headless 적대 케이스(검증자 스크래치, 커밋 안 함): 지그재그·0.3 mm 헤어핀(갭 0/0.1은 빌드, 갭 0.5/3은 "bends too sharply" 오류·변경 없음),
넓은 U(양 끝이 같은 변으로), 0.5 mm 짧은 스트로크(직선 연장), 물체 밖에서 시작해 안에서 끝나는 스트로크 → 모두 2파트 매니폴드·관입 0·원본 불변·
임시 데이터 0. 물체 밖 스트로크 "does not cross", 닫힌 고리 "crosses itself", 거의 닫힌 고리·나선 "straight extension crosses"(보수적 거부).
회전·비균일 스케일·이동한 오브젝트에서 컷이 그린 월드 위치(z −25.000)에 정확히. Suzanne `use_self=False` EXACT 빈 결과 재현(504/2010/8040면 모두
면 0, EXACT_SELF·MANIFOLD는 정상) — 원인 규명 확인. 전부 실패 주입 → BuildError, 원본·오브젝트·메쉬·컬렉션 수 불변.

열린 항목:
- [중간~낮음] D9: 곡선 컷 쌍 검증 허용치(4 % + 갭)가 셸 교차가 없는 경우에도 적용된다. 큐브 S자에서 한쪽 결과를 3 %·3.5 %·**5 %** 부피를 잃게
  주입해도 모두 통과(경고 없음, 합 61493 vs 정상 ~63060). Suzanne 눈 셸 하나(~2 %)를 잃는 결과도 걸러지지 않는다. 제안: 셸 교차가 없으면 허용치를 0.1 % 수준으로.
- [낮음~중간] D10: 곡선 컷 양쪽이 VOXEL 폴백으로만 성공해도 Build 경고가 없다(`_stroke_split`이 `res.message`를 warnings에 넣지 않음; 커넥터 불리언은 넣음).
  모듈 설명("reported as a warning")과 다름.
- [낮음] D11: Distribute와 Build의 자기 시임(own seam) 판정이 경계에서 엇갈림: 진폭 14 S자 큐브에서 Distribute가 3개를 놓았는데(검사 own_margin +0.045)
  저장된 위치로 Build가 1개를 "curved seam bends into" 경고와 함께 건너뜀(−0.102). 기하는 안전(관입 0), 사용자 혼란.
- [낮음] 테스트 공백: 변환된 오브젝트의 스트로크(로컬 저장) — 월드 점을 그대로 저장하는 뮤테이션을 커밋된 테스트가 못 잡음(코드는 정확, 위 확인).

---

## P2 후속 수정 라이브 검증 (Blender 5.2.2, 공식 MCP, 2026-10-09, develop 398154a)

독립 검증자, 스크립트 `/mnt/c/code/snapsplit_probe/mcp/qa8/`, 같은 안전 규칙. Millimeters + Unit Scale 0.001. 재로드: `bl_ext.splitforge_dev.splitforge*` 43개 purge 후 enable.

1. 구멍 메운 Suzanne(눈 포함, Subsurf 2 모디파이어 → 평가 메시 ~8k 면, `QA8_Monkey`), 눈을 지나는 S자(gap 0.5) + 수동 커넥터 1(u −8)(`qa8/scenario.py`):
   - Accurate 2.16 s: 곡선 컷 EXACT_SELF ×2, 커넥터 UNION/DIFFERENCE는 EXACT_SELF "not manifold" → MANIFOLD. 정보 "Booleans (Accurate): 2x EXACT_SELF, 2x MANIFOLD; fallbacks: …".
     파트 6976.7 / 8612.4 mm³(눈 겹침 합쳐짐).
   - Fast 0.21 s: "Booleans (Fast): 4x MANIFOLD", 파트 7033.4 / 8733.7(겹침 유지, A는 2셸·각 셸 닫힘).
   - Auto(8k 면 < 200k) = Accurate와 같은 결과. 모두 매니폴드, 원본 해시 불변, 임시 데이터 0.
2. 갭 UX(`qa8/stroke2.py`, `gap6.py`, `fix.py`): 3주기 S자 Stroke 2에 gap 0.5–4 → 문제 없음, 5 이상 → `cut.problem` "The stroke bends too sharply for its gap (6) …"
   (Build의 BuildError와 같은 문구). 패널: 목록 이름 옆 경고 아이콘, 컷 상자에 빨간 "Cannot build this cut:" + 줄바꿈된 이유
   [패널](qa/p2f_live_52_gap_problem.png). 그 상태로 Build → 같은 오류, 이전 파트 유지. 0.5로 내리면 문제 문자열 비고 Build 성공. 고아 메쉬·모달 0.

headless(검증자 스크래치, 커밋 안 함):
- 삼각분할 여유(D9 재확인): 한쪽 결과에 0.5–3 % 손실 주입. 촘촘한 메시(ico 4단계, UV 96×48, Subsurf한 머리만 Suzanne 1·2단계) 여유 0–0.09 % → 전부 거부·재시도.
  **거친 비평면 메시에서는 여유가 커서 손실 통과**: 원본 머리만 Suzanne(438면) 여유 0.73 %(0.5 % 손실 통과), 꼭짓점을 흔든 큐브 1.3 % / 3.3 %(최대 3 % 손실 통과),
  비평면 64각형 뚜껑 원기둥 5.9 % / 15.3 %(3 % 손실 모두 통과). 삼각형 메시(STL)는 여유 0.
- Accurate 평면 Build 커넥터 폴백 원인: 평면 컷(bisect)은 눈/머리 겹침을 그대로 두므로 파트의 "before" 부피가 겹침(AA 834.7, AB 707.2 mm³, 8k 면)을 두 번 센다.
  EXACT_SELF는 겹침을 합치며 핀을 더해 66871.6 = 자기합집합 66580.0 + 핀 291.6으로 **정확**하지만 "volume did not grow"로 거부되어 MANIFOLD로 간다(51만 면에서도 같은 3건).
- 쪽 판정(D11): 그린(스무딩된) 스트로크 10종 2만 점씩 정확한 2D 판정과 불일치 0. `clean=False` 원시 지그재그(꺾임 140°)에서 649/20000 불일치(리본에서 최대 5.4 mm) —
  최근접 면 법선이 날카로운 볼록 꼭짓점에서 틀림. 같은 스트로크 + 평면 컷 + 커넥터 빌드 4종은 관입 0(다른 검사가 막음).

열린 항목:
- [중간~낮음] D13: 삼각분할 여유에 상한이 없어 거친 비평면 사각형/n각형 메시에서 쌍 검사가 다시 느슨해짐(위 수치). 제안: 조각을 먼저 삼각분할하거나 여유 상한(예: 0.5 %).
- [중간] D14: 셸이 겹친 평면 파트의 커넥터 불리언에서 Accurate의 EXACT_SELF 결과(정확)를 부피 검사가 거부 → MANIFOLD 폴백(정보 줄에 표시됨). Accurate 툴팁("셸을 하나로 합침")과 다르고
  51만 면에서 ~47 s를 버림. 제안: self_intersect일 때 before를 자기합집합 부피로.
- [낮음] D15: 리본 법선 쪽 판정이 꺾임 > ~120° 꼭짓점 근처에서 틀림(`clean=False` 스크립트 입력만 해당); 2D 폴백 분기를 쓰지 않는 뮤턴트를 테스트가 못 잡음.
- [낮음] Fast/Auto(>200k)에서 겹친 셸이 남는다는 사실은 툴팁에만 있고 Build 정보 줄은 솔버 이름만 보여 준다. 각 셸은 닫혀 있고 부피 양수(슬라이서용으로 유효).
- [낮음] `cut.problem`은 갭 변경·스트로크 저장 때만 다시 계산(나중에 오브젝트 스케일·단위 배율을 바꾸면 갱신되지 않음; Build는 항상 다시 검사).

---

## D13–D15 수정 라이브 검증 (Blender 5.2.2, 공식 MCP, 2026-10-09, develop 3d90da6)

독립 검증자, 스크립트 `/mnt/c/code/snapsplit_probe/mcp/qa9/`, 같은 안전 규칙. Millimeters + Unit Scale 0.001. 재로드 43개 purge 후 enable.

1. 구멍 메운 Suzanne(눈 포함, Subsurf 2 모디파이어, `QA9_Monkey`) + Z 평면 컷(−8, gap 0.3, Distribute 1) + 눈을 지나는 S자(gap 0.5, Distribute 3)(`qa9/scenario.py`):
   - Fast 0.32 s: "Intersecting shells stay overlapping in the parts (Booleans: Fast); slicers unite them, Accurate unites them here", "Booleans (Fast): 6x MANIFOLD", 3파트 매니폴드.
   - Accurate 1.06 s: "Intersecting shells were united into one solid (Booleans: Accurate)", "Booleans (Accurate): **6x EXACT**", **폴백 0**, 3파트 매니폴드, 파트 관입 0.
   - 원본 해시 불변, 임시 오브젝트·고아 메쉬 0, `view_layer.objects`에 None 0.
   - Fast 파트에서 레이 홀짝 관입 프로브가 AB→AA 최대 2.0 mm를 표시했으나, AA는 겹친 셸을 가진 자기교차 메시(BVH 자기 겹침 750쌍)라
     홀짝 판정이 불안정한 것(레이 3개 투표 1/0/0). 해당 정점은 정확한 2D 판정으로 모두 B 쪽, 리본에서 1.6–1.7 mm(> 반갭) — 실제 관입 아님.
2. 스크린샷: Accurate 3파트 분해 표시, S 리본(커넥터 3) + Z 평면(커넥터 1) 오버레이, 패널 "Part of QA9_Monkey", "3 part(s)" [Accurate 파트](qa/p2g_live_52_accurate_parts.png).

headless(검증자 스크래치, 커밋 안 함):
- D13 재확인: 이전 적대 메시 9종(ico, UV 구, 머리만 Suzanne 0/1/2단계, 흔든 큐브 2/4, 비평면 64각형 뚜껑 원기둥 2/5)에 한쪽 0.5–3 % 손실 주입 → **36건 모두 거부·재시도**(이전에는 거친 메시 13건 통과).
- D15 재확인: 원시 지그재그(꺾임 140°) 포함 스트로크 11종 × 2만 점 — 리본 쪽 판정과 정확한 2D 판정 불일치 **0**(이전 649).
- 내부 공동 + 겹친 셸(벽 3 mm 중공 상자 + 윗벽에 박힌 원기둥): Accurate는 합친 뒤 공동을 유지(공동 셸 −39135 = 34³ − 원기둥이 공동으로 들어간 부피),
  컷이 공동을 지나면 공동이 열린 U자 파트, Fast는 원기둥이 겹친 별도 셸로 남고 정보 줄로 알림. 모두 매니폴드.
- 셸 합치기 결과 검증: EXACT_SELF 합집합 결과를 3 % 줄이도록 주입하면 **그대로 받아들여짐**(부피 16839.8 vs 정상 17360.6, 경고 없음) — 아래 D16.

열린 항목:
- [중간~낮음] D16: `boolean.unite_bm`이 결과 부피의 상한(≤ 원래 부피)만 검사하고 하한이 없어, 부피를 잃은 합집합(셸 하나 빠짐·축소)을 받아들인다.
  이후 모든 불리언 검사가 이 잘못된 기준으로 진행된다. 제안: 하한(≥ 가장 큰 셸 부피, ≥ 원래 부피 − 작은 셸들 부피 합) 또는 MANIFOLD 합집합과 비교.
- [낮음] 곡선 컷 조각은 전체를 삼각분할하므로 곡선 컷이 지나간 파트는 사각형 토폴로지를 잃는다(프린트에는 무관).
- [낮음] 51만 면 Accurate 시간이 구현자 수치보다 ~20 % 김(평면 46.5 s vs 38.2, S자 41.9 s vs 38.8; 상한 120 s 안).

---

## Phase 3 커넥터 라이브 검증 (Blender 5.2.2, 공식 MCP, 2026-10-10, develop f2a2f46)

독립 검증자(verifier), 스크립트 `/mnt/c/code/snapsplit_probe/mcp/qa10/`, 같은 안전 규칙(MCP undo·참조 보관·타이머·프리퍼런스 리셋 없음,
MCP 애드온 미변경). Millimeters + Unit Scale 0.001. 재로드(`qa10/reload.py`): `bl_ext.splitforge_dev.splitforge*` 43개 purge 후 enable,
`Scene.snapsplit`·레거시 오퍼레이터 미등록, `connector_add_click` 등록.

1. 40 mm 큐브 `QA10_Cube`(x −150)에 Z 평면 컷(−8, gap 0.4) + S자 스트로크(z 8 ± 3, gap 0.4), 8종 전부(`qa10/scenario.py`):
   Z 컷 원기둥 핀(A)·사각 테논(B)·도브테일(A)·스냅 핀(B)·도웰, S자 스냅 테논(A)·스냅 도브테일(B)·커스텀(육각 뿔대, 법선 뒤집힘)·도웰.
   Build(Auto) 1.39 s, **경고 0**, "Booleans (Auto): 6x EXACT, 2x EXACT_SELF", 파트 AA/AB/BB + `QA10_Cube_Dowel_1`(Cut Z connector 5)·`Dowel_2`
   (Stroke 2 connector 4) 모두 매니폴드, 원본 해시 불변·숨김·모디파이어 0, 고아 메쉬·`_SplitForge*` 0, 큐브 밖 0.
2. 조립 검사(`qa10/assembly.py`, 커넥터마다 핀 쪽 파트를 갭만큼 법선 방향으로 옮김): 9개 모두 파트 관입 0, 최소 여유(c 0.2) — 원기둥 0.199,
   테논 0.200, 도브테일 0.200(면 수직), 스냅 3종 0.1925(구 면 분할), 커스텀 0.1875, 도웰 2개 0.199(곡선 시임 포함). 도웰 길이 10/8, 지름 5,
   원본 +X 면에서 5 mm, 바닥 z −20. (갭이 열린 상태의 스냅 돌기는 딤플과 갭만큼 어긋나 최대 0.12 mm 겹침 — 설계상 정상.)
3. Export STL(`qa10/out/stl`): AA/AB/BB + **Dowel_1/Dowel_2** 5개 파일.
4. 스크린샷: 분해 표시한 3파트(소켓·핀·커스텀 육각 핀) + 눕힌 도웰 2개 + 오버레이 + 패널(커스텀 커넥터 상자 "Custom mesh / QA10_Hex",
   목록 "1 Snap tenon pin A … 4 Dowel both sides", "5 part(s)") [파트+패널](qa/p3_live_52_parts_panel.png).
   인터페이스 번역을 잠시 켠 한국어 패널(원래 설정 ko_KR + 번역 끔으로 복원) [한국어](qa/p3_live_52_ko_panel.png): "새 커넥터", "도웰 (별도 파트)",
   "모따기", "라인/격자", "개수", "여백 %", "클릭", 목록 "1 스냅 테논 핀 A … 4 도웰 양쪽"은 번역됨. **"Distribute", "Redraw in Viewport"는 영어**(D18).

headless(검증자 스크래치 `/mnt/c/code/snapsplit_probe/p3v/`, 커밋 안 함):
- 커넥터 매트릭스 8종 × 6장면(중앙 회전 핀 A/B, 벽 0.1 mm/관통 위치, 4 mm 판, 다른 컷 교차, S자 Distribute 3, 세로 S 리본 옆): 48빌드 모두 매니폴드,
  외곽 면적 = 커넥터 없는 빌드(관통 0), 가장자리·판 두께 초과·다른 컷/리본 교차 커넥터는 이유와 함께 건너뜀, 조립 시 관입 0, 핀 여유 0.234–0.250(c 0.25),
  도웰(곡선 시임 포함) 0.249.
- 커스텀 적대 메시 14종: L자·법선 뒤집힘·원뿔(양 방향)·토러스·셸 2개(겹침/분리)·미세(0.1 µm) 정상(관입 0); 열린 메시·20 480면·납작 → "… skipped";
  9 728면 UV 구 빌드 4.1 s. 별 모양 오목 꼭짓점 여유 0.177, 날카로운 원뿔 끝 0.215(c 0.25). **0.3 mm 슬롯(< 2c)**: 오프셋이 접혀 합치기가 D16 검사에 거부
  → 파트 불리언 EXACT_SELF 비매니폴드 → MANIFOLD 폴백 → 조립 시 핀이 소켓 파트를 0.05 mm 관통, 경고 없음(정보 줄 "fallbacks"만)(D17). 슬롯 0.45/0.6/1.0은 정상.
- D16 검사: 얇은 교차 판 200×200×0.6(수평·수직), 겹친 구 30개 → 모두 합침 승인. 뒤집힌 셸 입력 거부. 비용: 24.8만 면 `winding_volume` 0.1 s.
  누락 검출: 0.3 mm 두께 판 셸(부피 0.75 %)을 잃는 경우 8개 위치 중 2개에서 광선 사이로 빠져 미검출(격자 간격 bbox/96 미만 셸, 낮음).
- 옛 파일: 8fe02fa(레거시 포함)로 레거시 `planar_split`+`add_connectors`+Scene.snapsplit 값(커스텀 포인터, PETG)+P2 스택을 저장한 .blend를 새 애드온으로 열기 →
  오류·트레이스백 0, 패널 4개 정상 그리기(레거시 소스/파트/P2 큐브), P2 큐브 Rebuild·레거시 파트에 새 스택 Build 매니폴드, 다시 저장·열기 정상.

열린 항목:
- [낮음~중간] D17: 커스텀 메시의 오목 특징이 2×공차보다 좁으면(슬롯 등) 법선 오프셋 소켓이 접히고, MANIFOLD 폴백 결과가 조립 시 0.05 mm 간섭.
  경고 없음. 날카로운 꼭짓점/오목 모서리 여유가 공차보다 작음(0.18/0.25). 제안: 합치기 실패 시 경고, 또는 셸 팩터 대신 면 오프셋 합집합(민코프스키 근사).
- [낮음] D18: 패널의 오퍼레이터 버튼 텍스트 5개("Cut", "Adjust in Viewport", "Draw Cut", "Distribute", "Redraw in Viewport")는 `("*", …)` 항목만 있고
  `("Operator", …)` 항목이 없어 ko/de에서 영어로 표시. `test_i18n`은 이 컨텍스트를 검사하지 않음. f-문자열 라벨("Part of …", "Gap … mm", "On …",
  "Stroke: … points")도 미번역.
- [낮음] 패널의 커스텀 메시 문제 캐시는 (이름, 정점/변/면 수)로만 갱신되고 평가 전 메시(`obj.data`)를 검사(Build는 평가 메시) — 개수를 유지한 편집이나
  모디파이어로 닫히는 메시에서 패널 표시가 Build와 다를 수 있음.
- [낮음] 클릭 모달: S가 Ctrl과 함께여도 핀 쪽을 바꾸고(Ctrl+S 저장을 먹음), Alt+LMB도 소비.
- [낮음] 51만 면 Accurate 평면 Build 59.6 s(구현자 49.6 s; 상한 120 s 안). Auto의 BB 소켓 불리언이 EXACT_SELF 5.5–7.9 s(겹침 표시된 파트).

---

## Phase 3 후속 수정 라이브 검증 (Blender 5.2.2, 공식 MCP, 2026-10-10, develop d9f7225)

독립 검증자, 스크립트 `/mnt/c/code/snapsplit_probe/mcp/qa11/`, 같은 안전 규칙. Millimeters + Unit Scale 0.001. 재로드 36개 purge 후 enable.

1. 도웰 배치(`qa11/scenario.py`): `QA10_Cube`(Z + S자, 8종) Rebuild 3.08 s, 경고 0. Settings > Dowel layout을 Flat → Upright → At assembly → Flat로
   바꾸면 기존 도웰 파트가 즉시 이동: Flat = 원본 +X 면에서 5 mm, X축으로 눕혀 바닥 z −20; Upright = 같은 줄에 세움(높이 10/8 mm, 바닥 z −20);
   조립 위치 = 소켓 안(Z 시임의 세로 도웰, S자 시임의 기울어진 도웰) [눕힘](qa/p3f_live_52_dowel_flat.png) [세움](qa/p3f_live_52_dowel_upright.png)
   [조립](qa/p3f_live_52_dowel_assembled.png). 조립 위치 상태에서 Export STL → 도웰 STL의 bbox가 눕힌 자세와 같음(x −125..−115, z −20..−15),
   내보낸 뒤 오브젝트 행렬은 조립 자세 그대로(차이 1e-7). 잘못된 폴더(파일 경로 아래)로 Export → `os.makedirs` 예외가 트레이스백으로 보고됨(try 이전, 기존 코드, 낮음),
   도웰 위치는 바뀌지 않음.
2. 커스텀 0.3 mm 슬롯 메시(`qa11/slot.py`, 이전 D17 재현): Z 컷 큐브에 핀 A/B(회전 45°) → Build 0.62 s(같은 형상 재빌드 0.03 s, 캐시), 경고 0,
   "4x EXACT", 매니폴드, 조립(갭 닫음) 관입 0·여유 0.250(c 0.25). 이전 0.05 mm 간섭 해결.
3. 한국어(인터페이스 번역 잠시 켬 → 원래 ko_KR·번역 끔으로 정확히 복원) [한국어](qa/p3f_live_52_ko_panel.png): "QA10_Cube의 파트", "1 단위 = 1 mm",
   "틈 0.4 mm, 커넥터 4개", "스트로크: 점 118개", "뷰포트에서 다시 그리기", "Stroke 2에 배치", 버튼 "자동 배치"/"클릭". 툴팁: `pgettext_tip`이
   Distribute 설명·Dowel layout 설명·도브테일 테이퍼 설명을 한국어로 반환(마우스 hover 표시는 MCP로 확인 불가).

headless(검증자 스크래치 `/mnt/c/code/snapsplit_probe/p3f/`, 커밋 안 함):
- 커넥터 매트릭스 48빌드 재실행: 모두 매니폴드, 관통 0, 조립 관입 0, 최소 여유 0.2337(= 0.93c, 커스텀 육각 뿔대), 건너뜀 경고 이전과 같음.
- 커스텀 14종: 모든 빌드 관입 0, 여유 ≥ 0.2395(0.96c) — 슬롯 0.250(이전 −0.05), 별 0.2395(이전 0.177), 원뿔 0.2395(이전 0.215). 경고 0.
  **빌드 시간**: 뾰족한 원뿔(17면) 43.7 s / 뒤집은 원뿔 45.4 s, 별 8.8 s(민코프스키 폴백, 첫 계산; 같은 형상·크기·공차는 세션 캐시). 별·원뿔·고밀도 UV 구의
  소켓 DIFFERENCE는 EXACT_SELF 비매니폴드 → MANIFOLD 폴백(정보 줄만; 조립 여유는 정상).
- D16: 0.3 mm 판 셸 누락이 8개 위치 모두 검출(이전 6/8), 얇은 판·구 30개 정상 합침 승인, 24.8만 면 3축 적분 0.38 s.
- 옛 .blend(레거시 + P2 스택) 열기 재확인: 오류 0, Rebuild·새 스택 Build 매니폴드.

열린 항목:
- [중간~낮음] D19: 민코프스키 폴백이 느림 — 17면 원뿔 하나가 ~44 s(Build, 그리고 같은 형상의 첫 Distribute/클릭 fit 검사 중 UI 정지), 크기·공차를 바꿀 때마다
  다시 계산, 애드온 재로드 시 캐시 소실. 진행 표시·경고 없음. 제안: 모서리 원기둥/꼭짓점 구를 볼록한(오목 아닌) 곳만, 또는 먼저 합치기 조각 수 줄이기, 진행률.
- [낮음] Export 폴더가 만들 수 없는 경로면 처리되지 않은 예외(트레이스백) — `os.makedirs`가 try 밖(Phase 1 코드).
- [낮음] 별·원뿔 등 폴백 소켓의 파트 DIFFERENCE가 MANIFOLD로 폴백(경고 아님, 정보 줄).

---

## Phase 4 라이브 검증 — 릴리스 zip (Blender 5.2.2, 공식 MCP, 2026-10-10, develop bdd59e3)

독립 검증자, 스크립트 `/mnt/c/code/snapsplit_probe/mcp/qa12/`, 같은 안전 규칙(MCP로 undo 없음, 저장된 참조·타이머 없음, 환경설정 리셋 없음, MCP 애드온 손대지 않음).
develop에서 다시 빌드한 `splitforge-0.4.0.zip`(44파일, p4 워크트리 zip과 파일 내용 동일, git HEAD 파일과 바이트 동일)을 사용자처럼 설치:
개발 저장소 애드온 `bl_ext.splitforge_dev.splitforge` 비활성 + 모듈 37개 purge → `extensions.package_install_files(repo="user_default",
enable_on_install=True)` → `bl_ext.user_default.splitforge` 활성, 연산자 7종 등록, 설치된 manifest `version 0.4.0`·`blender_version_min 5.2.0`.
새 씬 `QA12V`(미터)에서:

1. 일부러 망가뜨린 메시(40 큐브, 면 하나 삭제, 면 2개 뒤집음, 떨어진 정점, 모서리 분리로 중복 정점 2개, 스케일 1.5·회전 20°): Check Mesh가 6가지 모두 보고
   (열린 모서리 8, 떨어진 정점 1, 법선 불일치 4, 중복 2, 변환, 1 unit = 1000 mm). Fix 순서대로: Merge(2개 병합) → Fill Holes(면 1개, 정점 1개 삭제;
   이때 법선 재계산도 같이 되어 법선 행도 해결) → Recalculate Normals(할 일 없음 CANCELLED) → Apply Rotation & Scale → Units(Keep Units) → 모든 행 통과,
   부피 216000 = 60³. 두 번째 실행은 다섯 Fix 모두 CANCELLED + "already" 정보.
2. 폴리라인 컷(정면, 점 4개, 갭 0.2) + 폴리곤 도려내기(위, 28×28, 깊이 12, 갭 0.2), 각각 Distribute 2개 → Build 0.18 s, "8x EXACT", 경고 0, 파트 3개 매니폴드
   (플러그 9465.3 / 포켓 몸체 121635.4 / 아래 83780.3). Export STL 3파일: 각 파일 삼각형 280/564/284, 부피가 파트와 같음.
   [빌드·패널](qa/p4v_live_52_release_built.png): 플러그 들어 올림, 포켓 바닥의 핀 2개, 폴리라인 시임, 검사 행 모두 체크.
3. 한국어(인터페이스 번역 잠시 켬 → ko_KR·번역 끔·툴팁/보고 켬으로 정확히 복원) [한국어](qa/p4v_live_52_ko_panel.png): "출력 검사", "메시 검사", "회전·스케일 적용됨",
   "닫힘(구멍 없음)", "법선이 바깥을 향함", "중복 정점 없음", "깊이 (mm)", "폴리곤: 꼭짓점 4개", "뷰포트에서 다시 그리기". 오류·정보 메시지는 영어(알려진 범위).
4. 개발 애드온으로 돌아가기: 환경설정 > 추가 기능에서 SplitForge(User Default) 끄기 또는 제거 → "SplitForge dev (develop)" 저장소의 SplitForge 켜기
   (같은 세션이면 먼저 끈 쪽 모듈이 남지 않도록 Blender 재시작 권장).

headless(검증자 스크래치 `/mnt/c/code/snapsplit_probe/p4v/`, 커밋 안 함):
- D19 볼록 소켓 수치 검사(면 300점/삼각형, 모서리 40점, 정점): 원뿔·뒤집은 원뿔·상자·사면체·얇은 판·바늘 최소 여유 0.2500, UV 구 0.2496(0.998c), 최대 0.2545(+1.8 %),
  매니폴드, 면적 0 삼각형 0, 원뿔 0.006 s; 별(오목) 2.0 s·0.2500.
- 적대 폴리곤/폴리라인 26건: 나비넥타이·되접힘 거부, 오목 별(시계/반시계) 깊이 10 = 2645, 물체 일부 밖 = 2000/62000(커넥터 겹친 영역 안), 옆에서(깊이 8) 3200,
  깊이 100/40 → 관통·Distribute "set a Depth", 깊이 0.05 → 20, 일직선+중복점 폴리라인 = 평면 컷, 같은 점 2개/3개·되돌아감 거부. 좁은 폴리곤(6 mm)에 5/9 mm
  커넥터 → 배치 0(CANCELLED), 벽에 억지로 둔 커넥터는 Build가 건너뜀.
- Fix 적대: 3면 모서리 메시(남김·보고), 열린 평면(채울 수 없음 보고), 빈 메시(모두 CANCELLED), 음수 스케일 + 자식·손자(월드 차이 1.9e-6, 부피 양수, Build 부피 동일),
  공유 메시 4종 거부, delta 스케일(월드 유지, 스케일 0.5·delta 2로 남음), Keep Size 63개 오브젝트(계층·카메라·조명·엠프티) 물리 크기 모두 유지.
- Phase 3(5054c05) 코드로 저장한 .blend(평면 + 스트로크 + 도브테일) → develop에서 열기·Build 매니폴드·폴리곤 추가·저장·다시 열기 정상.

열린 항목:
- [중간~낮음] D20: 꼭짓점이 ~20° 이하로 뾰족한 폴리라인 + 갭 > 0 → 추가·패널 검사는 통과하지만 Build가 "parts A + B = … with VOXEL, VOXEL; no solver left"로 실패
  (아무것도 바뀌지 않음; 25° 이상은 정상, 폴리곤은 15°도 정상). 마이터 제한(cos ≥ 0.25) 때문에 쌍 부피 검사가 맞지 않음. 제안: 그런 꼭짓점을 추가 시점에 거부하거나 갭 부피 계산을 실제 리본으로.
- [낮음] D21: 0.01 mm 폴리곤이 추가되고 Build에서 "failed with every boolean solver"(변경 없음) — 추가 시점 최소 크기 검사 없음.
- [낮음] 폴리곤 바닥 커넥터가 벽에 걸리면 경고 문구가 "the curved seam bends into …"(곡선 시임 문구 재사용).
- [낮음, 코드 리뷰] 점 찍는 중 뷰를 돌리면 첫 점 닫기(12 px)와 Ctrl 15° 스냅이 클릭 당시의 화면 좌표를 기준으로 함.
- [정보] Fill Holes가 법선도 재계산하지만 보고에 뒤집은 면 수가 없음; `schema_version`은 파일에 쓰이지 않음(기본값만 읽힘 — 추가형 변경이라 문제 없음).

---

## 결과 기록

| 항목 | Blender 4.5 | Blender 5.2 | 날짜/메모 |
|---|---|---|---|
| QA-11 폴리라인·폴리곤 컷 | — (5.2 전용) | PASS (자동) | 2026-10-10 feat/p4-final: `--gui` p4_points — 실제 클릭 4번·모달 중 Ctrl+Z 점 삭제·Enter·실제 Ctrl+Z/Ctrl+Shift+Z·Esc/RMB·첫 점 클릭으로 폴리곤 닫기·바닥 커넥터 클릭·모달 Build 3파트·파일 로드 `cancel()` [폴리라인](qa/p4_polyline_oblique_5.2.png) [폴리곤](qa/p4_polygon_preview_5.2.png) [빌드](qa/p4_built_apart_5.2.png). 사람 확인 남음: 점 찍기 감각, 프리뷰 가독성 |
| QA-12 출력 검사·Fix | — (5.2 전용) | PASS (자동) | 2026-10-10: `--gui` p4_fix — 사이드바 실제 클릭: Check Mesh, 법선 Fix, 변환 Fix(컷 월드 위치 유지)·실제 Ctrl+Z/Ctrl+Shift+Z, 단위 Fix 대화상자 Enter [발견](qa/p4_fix_checks_found_5.2.png) [수정 후](qa/p4_fix_checks_fixed_5.2.png). 사람 확인 남음: 문구·대화상자 설명 |
| D19·Export 폴더(Phase 3 후속 열린 항목) | — | PASS (headless) | 2026-10-10: D19 원뿔 소켓 17.4 s → 0.01 s, Distribute+Build 42 s → 0.08 s, 별·원뿔 소켓 DIFFERENCE 평범한 EXACT(폴백 없음); Export 폴더/파일 오류가 경로를 밝힌 ERROR(`test_custom_socket`, `test_export`) |
| P3 후속(D17·D18·도웰 배치) | PASS (자동) | PASS (자동) | 2026-10-10 fix/p3-followups: `--gui` p3_connector_types 도웰 배치 전환(조립·세움·눕힘) [조립](qa/p3f_dowel_assembled_5.2.png) [세움](qa/p3f_dowel_upright_5.2.png); D17·D18은 헤드리스. 사람 확인 남음: 한국어 툴팁 문구, 실제 출력 시 커스텀 소켓 끼움 |
| Phase 3 후속 수정 라이브(MCP) | — | PASS (새 결함 D19) | 2026-10-10 verifier, develop d9f7225: 도웰 배치 3종 전환·Export 눕힘·자세 복원, 0.3 mm 슬롯 커스텀 여유 0.250, 한국어 버튼·값 라벨·툴팁. `--gui` 전체 6×2·헤드리스 39/39 ×2·`--slow` PASS, 뮤테이션 4/4. 위 "Phase 3 후속 수정 라이브 검증" 절 |
| Phase 3 커넥터 라이브(MCP) | — | PASS (결함 D17·D18) | 2026-10-10 verifier, develop f2a2f46: Z+S자 큐브에 8종(커스텀·도웰 2개 포함) Build 경고 0·매니폴드·조립 관입 0·여유 0.19–0.20(c 0.2), STL에 도웰 2개, 한국어 패널. `--gui` 6×2·헤드리스 38/38 ×2·`--slow` PASS, 뮤테이션 7/7. 위 "Phase 3 커넥터 라이브 검증" 절 |
| QA-9 클릭 커넥터 배치 | PASS (자동) | PASS (자동) | 2026-10-09 feat/p3-connectors: `--gui` p3_connector_click — 실제 클릭 3회·S·물체 밖 무시·실제 Ctrl+Z 3회 하나씩/Ctrl+Shift+Z 3회(모달 중과 끝난 뒤)·Build·파일 로드 `cancel()`. 사람 확인 남음: 프리뷰 가독성, 실제 마우스 감각 [프리뷰](qa/p3_click_preview_5.2.png) [배치](qa/p3_click_placed_5.2.png) [빌드](qa/p3_click_built_5.2.png) |
| QA-10 커넥터 종류 | PASS (자동) | PASS (자동) | 2026-10-09: `--gui` p3_connector_types — 8종 빌드(A, B, Dowel_1) [소켓](qa/p3_types_built_5.2.png) [핀](qa/p3_types_pins_5.2.png). 사람 확인 남음: 실제 출력 후 끼움 감각(공차·스냅 돌기 높이) |
| D16 셸 합치기 하한 | — | PASS (headless 재확인) | 2026-10-09: headless `test_unite_check`(3 %·1 % 축소·셸 누락 주입 거부). 2026-10-10 verifier: 얇은 판·구 30개 합침 승인, 24.8만 면 0.1 s, bbox/96보다 얇은 셸 누락은 일부 미검출(낮음) |
| D13–D15 수정 라이브(MCP) | — | PASS (새 결함 D16) | 2026-10-09 verifier, develop 3d90da6: 눈 있는 Suzanne 평면+S자+커넥터 — Accurate "6x EXACT" 폴백 0·셸 합침 정보, Fast "6x MANIFOLD"·겹침 정보. `--gui` 12×2·헤드리스 38/38 ×2·`--slow` PASS. 위 "D13–D15 수정 라이브 검증" 절 |
| P2 후속 수정 라이브(MCP) | — | PASS (결함 D13–D15) | 2026-10-09 verifier, develop 398154a: 품질 Accurate/Fast/Auto 비교(눈 있는 Suzanne S자), 정보 줄 솔버·폴백, 갭 문제 패널 표시·해제. `--gui` 12×2·헤드리스 37/37 ×2·`--slow` PASS. 위 "P2 후속 수정 라이브 검증" 절 |
| P2 곡선 컷 라이브(MCP) | — | PASS (결함 D9–D11) | 2026-10-09 verifier, develop 29cd845: 큐브·Suzanne(눈) S자 gap 0.5, 곡면 시임 커넥터, Build 매니폴드·관입 0·원본 불변·눈 정보 메시지. `--gui` 12시나리오 ×2·헤드리스 34/34 ×2·`--slow` PASS. 열린 항목 — 위 "P2 곡선 컷 라이브 검증" 절 |
| QA-7 곡선(스트로크) 컷 | PASS (자동) | PASS (자동) | 2026-10-09 feat/p2-curved: `--gui` p2_stroke — 실제 LMB 드래그·Enter·Ctrl+Z/Ctrl+Shift+Z·모달 Build(눈 셸 정보)·Esc/RMB·Shift 스냅·Redraw·파일 로드. 사람 확인 남음: 리본 프리뷰 가독성, 원근 뷰에서 그린 감각(압출은 뷰 방향 하나, 원근 광선이 아님) [4.5](qa/p2_stroke_4.5.png) [5.2](qa/p2_stroke_5.2.png) |
| QA-8 Build 진행률 | PASS (자동) | PASS (자동) | 2026-10-09: `--gui` p2_build_progress — 13만 면, 빌드 중 상태바 텍스트 [5.2](qa/p2_build_progress_5.2.png), Esc 중간 취소 이전 결과 유지. 사람 확인 남음: 51만 면에서 불리언 한 단계(~30 s) 동안은 UI가 멈춤(단계 사이에만 갱신) |
| QA-5 컷 평면 모달 조정 | PASS (자동) | PASS (자동) | 2026-10-09 feat/p1-mvp2: `--gui` p1_adjust_plane — 오버레이 주황, 드래그·휠·X·LMB·Esc, 실제 Ctrl+Z/Ctrl+Shift+Z, 모달 중 undo/redo, 파일 로드 `cancel()`. 사람 확인 남음: 드래그 감도, 오버레이 가독성 [5.2](qa/p1_adjust_plane_5.2.png) |
| QA-6 Draft 패널 → Build → Export | PASS (자동) | PASS (자동) | 2026-10-09: `--gui` p1_panel — 실제 버튼 클릭(추가·undo/redo·체크박스·삭제·Distribute·Build·Export·Clear). 사람 확인 남음: 패널 배치·문구 [4.5](qa/p1_panel_4.5.png) [5.2](qa/p1_panel_5.2.png). 라이브 5.2(MCP)에서는 확인하지 않음(사용자 세션 미사용 규칙) |
| D7 수정 라이브(MCP) | — | PASS | 2026-10-09 verifier, develop ff7ecdb: QA5_Steep 옛 커넥터 Rebuild → 다른 컷 넘는 3개 경고·건너뜀, 재배치 후 경고 0·관입 0·외곽 밖 0. 열린 항목 D8(중공 벽에 자동 배치 0개) — 위 "D7 수정 라이브 검증" 절 |
| P1 후속 수정 라이브(MCP) | — | PASS (새 결함 D7) | 2026-10-09 verifier, develop fafaed4: Unit Scale 0.001에서 1 unit = 1 mm, 경사 컷 재현 외곽 관통 0·경고 0·STL mm 확인. 가파른 경사 컷에서 핀이 세 번째 파트로 2.64 mm 관입(D7) — 위 "P1 후속 수정 라이브 검증" 절 |
| P1 라이브(MCP) 검증 | — | PASS (결함 1건) | 2026-10-09 verifier, develop e148026: 재로드·validate·Z+경사(gap 0.5) 컷·커넥터 8·Build(4파트 매니폴드, 원본 해시 불변)·Easy Cut·STL Export(mm 확인). 경사 컷 자동 커넥터가 외곽 관통(중간) — 위 "P1 라이브 검증" 절 |
| QA-1 분할 프리뷰 표시 | requires manual check | PASS | 2026-10-09 재검증(4f257db, 5.2.2 라이브, 애드온 재로드): 40 BU 큐브 Z/3파트 → 평면 2개(z=±6.667)가 Solid 뷰에서 **주황**으로 보임(`diffuse_color`=(1, 0.45, 0, 0.8), `show_in_front`) [fixed](qa/qa1_52_preview_z3_fixed.png); X/2파트 → X축 평면 1개; 끄면 평면·컬렉션 제거, X-Ray 원복, **고아 메쉬 0**(수정 전 8). 콘솔 오류 없음. `--gui` qa1_preview_color PASS(따뜻한 픽셀 0.0002→0.0593). 이전 결과(회색): [z3](qa/qa1_52_preview_z3.png) |
| QA-2 모달 분할 위치 조정 | requires manual check | PASS | 2026-10-09 재검증(4f257db, 5.2.2 라이브): 프리뷰 끈 상태로 Adjust 실행 중 오프셋을 5번 바꿔도 평면이 삭제·재생성되지 않고 **고아 메쉬 0**(수정 전 17), 파일 로드 `cancel()` 후 모달·X-Ray·`_ADJUST_RUNNING` 정리, 이후 프리뷰 갱신 정상. 드래그(4×25 px → +2.0 mm, 평면 동일 위치)·좌클릭/Enter 확정·Esc 취소는 `--gui` qa2_adjust(4.5/5.2) PASS로 확인. 오프셋으로 Planar Split 높이 일치·캡은 이전 라이브 확인. 사람 확인 남음: 실제 장치의 드래그 감도 |
| QA-3 클릭 커넥터 배치 | requires manual check | PASS | 2026-10-09 재검증(4f257db, 5.2.2 라이브): 수정된 공통 준비(mm, Unit Scale 1.0, 큐브 40 BU)에서 핀 프리뷰 5×5×7.7 BU가 40 BU 큐브 시임 중앙에 올바른 비율로 표시, 상태바 키 안내 [fixed](qa/qa3_52_click_preview_fixed.png); 파일 로드 `cancel()` 후 프리뷰·고아 메쉬 0·X-Ray 정리. 커서 추종·좌클릭 배치(핀 쪽 부피 +, 소켓 쪽 −, 목표 위치)·S 스왑·매니폴드·우클릭 정리는 `--gui` qa3_connectors PASS. 사람 확인 남음: Ctrl+Z 단위 기록, 와이어 프리뷰 가독성 |
| QA-4 Freehand 스트로크 컷 | requires manual check | PASS (제한 있음) | 2026-10-09: 라이브에서 모달·헤더 안내·자체 정리 확인(이전 행 참고 [modal](qa/qa4_52_freehand_modal.png)). 스트로크·Shift 축 스냅·Enter로 매니폴드 2파트(부피 합 일치)·Esc 무변경·파일 로드 `cancel()`은 `--gui` qa4_freehand PASS. **열린 항목**: 눈(별도 셸)이 있는 Suzanne는 확정을 거부(B3 제한) → 절차에서 눈 제거 |

자동 GUI 결과(`python3 tests/run_tests.py --gui`, 2026-10-09, `feat/p1-mvp2`): 아래 10개 시나리오 모두 4.5.5/5.2.2 PASS
(p1_adjust_plane ~25 s, p1_panel ~185 s: 버튼 hover 스캔 3회). 이전 기록(`fix/qa-findings`):

| 시나리오 | Blender 4.5.5 | Blender 5.2.2 | 메모 |
|---|---|---|---|
| p1_adjust_plane | PASS | PASS | feat/p1-mvp2 |
| p1_panel | PASS | PASS | feat/p1-mvp2. 처음 실행에서 X 컷 커넥터가 Z 컷 평면 위에 놓여 건너뛰어지는 버그를 찾음 → 시임 영역별 배치로 수정 |
| qa1_preview_color | PASS | PASS | 수정 전(2ac1865): 평면 회색(따뜻한 픽셀 0.0002 → 수정 후 0.0593), 고아 메쉬 누적 |
| qa2_adjust | PASS | PASS | 수정 전: 드래그 이벤트마다 평면 삭제·재생성으로 고아 메쉬 누적 |
| qa3_connectors | PASS | PASS | |
| qa4_freehand | PASS | PASS | Suzanne는 눈(별도 셸) 제거 후 사용 |
| adjust_undo_wheel / conn_undo / load_adjust / load_conn | PASS | PASS | |
