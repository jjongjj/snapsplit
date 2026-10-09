# 수동 검증 체크리스트 (GUI 전용)

headless 테스트(`python3 tests/run_tests.py`)로 확인할 수 없는 모달·마우스·뷰포트 표시 항목.
각 항목을 Blender 4.5와 5.2에서 각각 실행하고 결과 표에 날짜·버전·결과(OK/NG + 메모)를 적는다.

### 자동화 현황 (`python3 tests/run_tests.py --gui`)

`tests/gui/gui_runner.py`가 GUI Blender(`--enable-event-simulate`, 비공개 TEMP)를 띄워 아래 단계를 실제 이벤트
(마우스 이동·클릭·키)로 실행하고 검증한다. 스크린샷은 `tests/_out/gui/<시나리오>_<버전>_<단계>.png`.

| 시나리오 | 자동으로 검증하는 것 |
|---|---|
| `p1_adjust_plane` | QA-5: 활성 컷 평면 gpu 오버레이가 보임(오버레이 끔 대비 주황 픽셀), `splitforge.cut_adjust_plane` 마우스 드래그로 평면이 법선 방향으로 이동, 휠 = 정확히 1 mm, 좌클릭 확정 후 **실제 Ctrl+Z / Ctrl+Shift+Z 키 이벤트**로 되돌리기·다시하기(오퍼레이터가 undo 단계 1개를 남김), X 키 축 정렬, Esc 복원, 모달 중 undo/redo 반복(크래시 회귀), 모달 중 파일 로드 → `cancel()` |
| `p1_panel` | QA-6: 사이드바 SplitForge 탭을 클릭으로 열고, 버튼 위치를 hover 스캔(`ui.copy_python_command_button`/`copy_data_path_button`)으로 찾아 **실제 클릭**: X 컷 추가 → Ctrl+Z/Ctrl+Shift+Z, 목록 체크박스로 활성 토글, Remove, Distribute(커넥터), Build(4파트 매니폴드, 원본 숨김·불변), Export(파트당 STL), Clear Build. 스크린샷 `panel_start`·`panel_built` → `docs/qa/p1_panel_<ver>.png` |
| `qa1_preview_color` | QA-1: 프리뷰 평면이 Solid 뷰에서 주황(스크린샷 픽셀: 프리뷰 끔 대비 따뜻한 색 픽셀 비율), 재질 `diffuse_color` 주황, 토글 반복 후 고아 메쉬 0, 끄면 평면·X-Ray 정리 |
| `qa2_adjust` | QA-2: 마우스 드래그로 오프셋 변화 + 평면이 오프셋 위치로 이동, 좌클릭 확정(오프셋 유지·모달 종료), Enter 확정(프리뷰 끔 상태, 고아 메쉬 0), Esc 취소(메시지·평면·X-Ray 정리). 비스듬한 뷰(평면이 면으로 보이게), 두 번째 확정 메시지는 그 실행 이후 출력에서만 찾음 |
| `qa3_connectors` | QA-3: 위에서 본 분할 큐브에서 프리뷰가 커서를 따라감(커서 광선∩시임 위치와 일치, 위치 변화), 좌클릭 시 커서 위치에 핀(핀 쪽 부피 +, 소켓 쪽 −, 돌출 정점이 목표 위치 근처), S 후 클릭은 반대 파트에 핀, 두 파트 매니폴드, 우클릭 취소 후 프리뷰·X-Ray 정리. 오버레이 켜고 촬영(와이어 프리뷰는 오버레이 엔진이 그림) |
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
- 애드온 설치/활성화 후 새 파일(General). Scene Properties > Units: Metric, Length = Millimeters, **Unit Scale = 0.001**
  (표준 3D 프린트 설정, headless/GUI 테스트 하니스와 같은 설정: 1 BU = 1 mm).
- 기본 큐브를 지우고 `Add > Mesh > Cube`를 **Size 40 mm**(= 40 BU, UI에 "40 mm"로 표시) 또는 Suzanne(Size 40 mm,
  Edit Mode에서 `Mesh > Clean Up > Fill Holes`)로 추가해 선택한다.
- 단위 규약(P1-1 `core/units.py`, 레거시 `utils.unit_mm()`도 이것을 쓴다): Blender 표시와 같다 — **1 BU = Unit Scale m**.
  애드온의 mm 값은 언제나 Blender가 mm로 보여 주는 값과 같다. Millimeters + 0.001 → 1 BU = 1 mm, Meters + 1.0 → 1000 mm,
  Millimeters + 1.0 → 1000 mm(40 BU 큐브가 "40000 mm"). 패널 상단에 실제 "1 unit = … mm"가 보이며, Export STL/OBJ는 항상 mm로 쓴다.
- 3D 뷰포트 N 패널 > **SplitForge** 탭을 연다(새 Draft/Easy 패널; 레거시 SnapSplit UI는 맨 아래 접힌 "Legacy" 서브패널).
  콘솔(Window > Toggle System Console)을 켜 두고 오류를 확인한다.

---

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

## QA-6 Draft 패널 → Build → Export (P1-12 GUI)

절차:
1. 큐브 선택, Z·X 컷 추가. 목록 체크박스로 한 컷을 껐다 켠다. X 컷을 선택하고 Connectors > Distribute.
2. Build & Export > **Build**. 그 다음 Export 폴더를 지정하고 **Export Parts**. 마지막으로 Clear Build(X 아이콘).

기대 결과:
- 1단계 Distribute 후 X 컷 시임의 두 영역(Z 컷 위/아래)에 커넥터가 2개씩(노란 원 + 핀 쪽 표시 선) 보인다.
- 2단계 Build 후 원본은 숨겨지고(데이터 불변) `SplitForge_Build_Cube` 컬렉션에 매니폴드 파트 4개(`Cube_AA`…)가 생기며,
  파트를 선택해도 패널은 원본의 스택("Part of Cube")을 보여 준다. Rebuild는 같은 컬렉션을 교체한다(오브젝트 누적 없음).
  Export는 파트당 파일(mm 단위)을 쓴다. Clear Build는 파트·컬렉션을 지우고 원본을 다시 보이게 한다.

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

## 결과 기록

| 항목 | Blender 4.5 | Blender 5.2 | 날짜/메모 |
|---|---|---|---|
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
