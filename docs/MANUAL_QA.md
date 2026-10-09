# 수동 검증 체크리스트 (GUI 전용)

headless 테스트(`python3 tests/run_tests.py`)로 확인할 수 없는 모달·마우스·뷰포트 표시 항목.
각 항목을 Blender 4.5와 5.2에서 각각 실행하고 결과 표에 날짜·버전·결과(OK/NG + 메모)를 적는다.

공통 준비
- 애드온 설치/활성화 후 새 파일(General). Scene Properties > Units: Metric, Length = Millimeters, Unit Scale = 1.0.
- 기본 큐브를 지우고 `Add > Mesh > Cube`(Size 40 mm) 또는 Suzanne(Size 40 mm, Edit Mode에서 `Mesh > Clean Up > Fill Holes`)를 추가해 선택한다.
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
1. Suzanne(구멍 메운 것) 선택. 정면 뷰(Numpad 1), 패널의 "Freehand Cut" 버튼을 누른다.
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
  회귀 테스트는 `tests/cases/test_modal_undo_safety.py`.
- 사용자가 쓰는 Blender(MCP 서버 호스트)로 크래시 재현을 하지 않는다. 별도 인스턴스를 `--factory-startup`으로 띄우고,
  `TEMP`/`TMP`를 별도 폴더로 지정해 `%TEMP%\blender.crash.txt`·`quit.blend`를 덮어쓰지 않게 한다.

---

## 결과 기록

| 항목 | Blender 4.5 | Blender 5.2 | 날짜/메모 |
|---|---|---|---|
| QA-1 분할 프리뷰 표시 | requires manual check | requires manual check | |
| QA-2 모달 분할 위치 조정 | requires manual check | requires manual check | |
| QA-3 클릭 커넥터 배치 | requires manual check | requires manual check | |
| QA-4 Freehand 스트로크 컷 | requires manual check | requires manual check | |
