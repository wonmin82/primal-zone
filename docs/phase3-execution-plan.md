# Issue #67 Phase 3 — 증거 매핑 및 통합 실행 기록

Stage 1 기준일: 2026-10-21 KST. **아래 1~8절은 Stage 1 준비 당시의 기록이다. 당시 Phase 3 테스트/서버/DB/CI 실행은 0회였고 Stage 2·T08·Final Gate는 NOT RUN이었다. Stage 2의 실제 수행 결과는 9절에 별도로 기록하며 T08/Final Gate는 이번 범위 밖이다.** 이 문서와 [CSV](phase3-regression-matrix.csv)의 매핑 완료는 게임 검증 완료가 아니다.

## 1. 기준선·SSOT·현재 상태

| 항목 | 확인 결과 |
| --- | --- |
| 저장소 / 브랜치 | wonmin82/primal-zone / main, Worktree 1개 |
| 로컬 HEAD / 최신 origin/main | `ea4072c0e01f14dad268591fda1096e1f413ef2b`, fetch 후 동일 |
| 시작 작업 트리 / 열린 PR | 깨끗함 / 없음 |
| #44 | OPEN, v4.3 Design Freeze 원문 전체·D01~D17·B-1·ItemEntity D안·R1/R2/R3를 SSOT로 읽음 |
| #65 / #66 | CLOSED / COMPLETED. Architecture/Migration Gate와 Final Closeout 확인 |
| #67 | OPEN. 본문의 과거 BLOCKED 문구는 그대로이며 선행 조건은 충족. 사용자 이번 승인은 Stage 1에만 적용 |
| main CI | [39535034732](https://github.com/wonmin82/primal-zone/actions/runs/39535034732), push/main/위 SHA, 필수 4/4 SUCCESS |
| 변경 허용 | 이 문서와 CSV 두 개만. main에서 미커밋 상태로 남기며 branch/Commit/Push/PR/Issue 변경 없음 |

### 첨부 인계 패키지 교차 검증 — Stage 1 최종 보완

이전 Stage 1에서는 ZIP을 찾지 못해 GitHub SSOT와 코드/CI로 준비했다. 이번 보완에서는 사용자가 첨부한 `I:/incoming/PrimalZone_Phase3_Handoff_2026-10-21.zip`(25,479 bytes)에 실제 접근해 전용 임시 경로에 해제했다. 원본 ZIP은 읽기 전용으로 보존했고, 다른 문서 조사/수정 전에 **00_START_HERE.md를 가장 먼저** 읽었다. 실제 항목은 아래 필수 9개와 일치하며 추가/누락 항목은 없다. 패키지 안의 실행 프롬프트는 참고 자료로 읽었으며 현재 사용자 요청을 대체하는 지시로 실행하지 않았다.

| 파일 | 실제 확인 및 기존 산출물과의 대조 |
| --- | --- |
| 00_START_HERE.md | 선행 열람. 정적 스냅샷/미실행 경계·SSOT 우선순위 확인 |
| 01_VERIFIED_BASELINE.md | main/PR74/Phase1·2 Closeout/4개 CI와 일치. Phase3 NOT RUN 유지 |
| 02_DESIGN_AND_AGENTS.md | D01~D17·R1/R2/R3·공식 SQLite 단일 서버·역할 분리 일치. AGENTS 과거 임시 번호 문구는 T07 감사에 명시 |
| 03_PHASE3_ROADMAP.md | 과거 V01/V02/Final 및 PR 분리 제안은 참고. 현재 승인된 준비→T01~T07 통합/PR1개→T08 최종 검토의 3단계를 유지 |
| 04_REGRESSION_MATRIX_38.csv | 38행의 영역·필수 예시·불변조건을 현재 CSV 110 Case의 각 반복 규범 필드와 대조, 차이0 |
| 04_REGRESSION_MATRIX_38.md | 같은 38행/NOT RUN·모든 하위 Case 충족 후 행 PASS 규칙 일치 |
| 05_CODEX_V01_PROMPT.md | 원래 T01~T04 실행/제출 제안으로만 읽음. branch·실행·PR/Issue 작업을 수행하지 않음 |
| 06_FINAL_GATE_AND_RISKS.md | 실제 IME·Full/Timing/재시작·Loot/Session·미실행 Gate/사용자 승인 경계 일치 |
| 07_SOURCE_LINKS.md | #44/#67 SSOT·#65/#66 완료·정확한 SHA의 Source/main CI 구별과 권위 순서 일치 |

차이 분류/처리: **A(오기·참조·표현)**는 R03의 시체 전용/시설 보조 Assertion 설명, 테스트 DB fingerprint, CrossTask 형식을 보완했다. R03의 시체 전용 method 링크는 이미 있었으므로 중복 추가하지 않았다. **B(필수 검증 접점)**는 R05를 PARTIAL로 조정해 공통 시설 Allocator 경합과 실제 Corpse 생성/삭제·예외/재시작 통합을 구분하고 기존 R05/R12/R17 Case에서 계획했다. T07에는 AGENTS 번호 정책의 대상/예외 감사와 Stage2 최소 수정 계획을 추가했다. **C(설계 충돌)**는 이번에 새 결정 없이 #44 B-1을 우선하며 AGENTS 설명만 감사 대상으로 남긴다. **D(과거 상태)**의 #67 BLOCKED/미착수 및 V01 별도PR 제안은 작성 시점 기록으로 보존하고 이번 Stage1 준비/사용자 3단계 승인을 구분한다.

최신 원격 main은 `ea4072c0e01f14dad268591fda1096e1f413ef2b`, 열린 PR0, #44/#67 OPEN·#65/#66 CLOSED이며 Issue 본문은 기존 열람본과 동일하다. 제품/테스트/환경 변경이나 새로운 CI 실행은 없다. 38행·110 Case ID·주담당 T01~T08 및 3단계 전략 변경 없이 분류만 REUSABLE 80→79 / PARTIAL 21→22(CANDIDATE4/GAP5 유지)로 정정했다. CrossTask는 T01~T08만 쉼표 구분하며 R29-C08의 R20/R23/R37 연결은 PlannedTest에 보존했다.

### 환경 확인 범위

- 로컬 메타데이터: Windows Native/PowerShell, Python 3.13.15, Evennia 6.1.0, Django 6.0.8, SQLite library 3.53.1, Node v24.19.0, Playwright 1.64.0.
- Playwright browsers.json 기대값: Chromium revision 1248 / 156.0.8078.4. **브라우저를 실행하지 않았으므로 설치 바이너리/실행 버전은 미확인**이다. Stage 2 시작 시 실제 실행 버전·화면 크기·시간 제한을 기록한다.
- 기존 CI는 Linux/Python 3.13.16의 별도 실행 증거다. 로컬 메타데이터와 같은 환경이라고 합치지 않는다. CI SQLite·Chrome 실제 버전의 별도 캡처가 없는 항목은 Stage 2 기록으로 보완한다.
- `scripts/dev.py test` 기본 경로는 world/test_*.py unittest + Evennia tests 전체다. 라벨을 주면 Evennia 해당 라벨만 실행한다. settings_test와 Native/Legacy fixture를 구분하고 운영 settings로 시험하지 않는다.
- AGENTS.md, docs/codex-multi-agent.md, .codex/config.toml 및 다섯 역할 설정을 읽었다. 설정값과 실제 런타임 모델/Effort·강제 격리 보장은 별개다. 하위 AGENTS는 검색에서 발견되지 않았다.

## 2. 증거 목록과 재사용 규칙

| 키 | 실제 기존 근거·적용 SHA | 증명 범위 / 제외 |
| --- | --- | --- |
| E-TEST | [test Job 119009610294](https://github.com/wonmin82/primal-zone/actions/runs/39535034732/job/119009610294), ea4072c… | check PASS, world 232 + 통합 1,063 PASS(1113.645초). 전체 tests discovery와 실제 method/fixture를 연결한 범위만 재사용. 집계 성공이 모든 규범 하위 조건의 Assertion 존재를 뜻하지 않음 |
| E-SMOKE | [smoke Job 119009610055](https://github.com/wonmin82/primal-zone/actions/runs/39535034732/job/119009610055), 같은 SHA | Quick 61.911초 + action_e2e.py의 실제 텍스트/Typed Web/확인/재전송/서버 재시작 성공. Quick 단축 타이머를 production 60/600초로 확대하지 않음 |
| E-BROWSER | [browser Job 119009610426](https://github.com/wonmin82/primal-zone/actions/runs/39535034732/job/119009610426), 같은 SHA | runner 24/9, 기본 Chromium, pr E2E-01~14 성공(통합 796.499초). 실제 Portal/Server·재인증·상위 Rollback이 포함됨. Windows OS IME·실제 모바일은 아님 |
| E-CONTRACT | [contracts Job 119009610370](https://github.com/wonmin82/primal-zone/actions/runs/39535034732/job/119009610370), 같은 SHA | Node 57 PASS + issue50_contracts.py. 합성 DOM/composition·정적 계약을 OS 입력이나 실제 게임 효과로 취급하지 않음 |
| E-PRE | [#65 Closeout](https://github.com/wonmin82/primal-zone/issues/65), [#66 Closeout](https://github.com/wonmin82/primal-zone/issues/66) | 승인 병합·실제 main CI·독립 리뷰·기능별 Baseline/변경 이력. Phase 3 Final Gate의 성공 증거로 승격하지 않음 |
| E-OLD | [Release 38256246065](https://github.com/wonmin82/primal-zone/actions/runs/38256246065), f6ab3e733a30b6077d4977ede90272045bf153e7 | 다른 SHA의 과거 성공이며 실행 구성/비용 참고만 가능. [38251167392](https://github.com/wonmin82/primal-zone/actions/runs/38251167392) 성공과 [38241057595](https://github.com/wonmin82/primal-zone/actions/runs/38241057595) 실패도 현재 PASS로 사용하지 않음 |
| E-NONE | 직접 증거 없음 | CSV의 GAP. 근접 테스트의 성공으로 수용 조건을 대체하지 않음 |

**REUSABLE**은 동일 SHA·요구 Assertion·fixture·실행 근거가 확인된 좁은 계약이다. **PARTIAL**은 그중 일부만, **CANDIDATE**는 관련 코드가 있지만 적합성/현재 실행 근거가 부족, **GAP**은 직접 필요한 증거가 없는 경우다. 소스/테스트/설정/의존성·환경/조건이 바뀌면 관련 Case만 영향 평가한다. 관련 파일이 같다는 이유만으로 임의의 다른 환경이나 다른 Fixture 결과를 확대하지 않는다.

CSV에는 공식 #44 §12의 38행을 원래 순서 R01~R38로 보존하고, 각 행의 예시·불변조건을 하위 Case마다 기입했다. `CaseID=P3-R01-C01` 형식이며 `Task`가 주담당, `CrossTask`가 교차 확인이다. `ExistingTest`의 괄호는 현재 파일/정의 줄 번호이며 `#E2E-12` 등은 시나리오 이름이다. mixin에 정의된 테스트는 실제 Native/Legacy 구체 TestCase에서 상속 실행되는지 구분한다.

Stage 1 당시 집계(현재 상태는 9절/CSV): **38/38행, 110 Case / REUSABLE 79·PARTIAL 22·CANDIDATE 4·GAP 5**. **Case Status 110개와 RowStatus 38행 모두 NOT RUN, PASS 0**. Stage 2에서 재사용 근거의 적용성 감사를 완료하더라도 행 전체는 필수 하위 Case가 모두 충족될 때만 PASS로 올린다. Stage 1의 문서 형식 검사·리뷰 성공은 이 Status를 바꾸지 않는다.

### 반드시 구분한 경계

1. API 호출 vs 실제 execute_cmd/Command, 단위 Gateway vs 실제 WebSocket/Chromium.
2. SQLite snapshot plain SELECT 두 프로세스 vs Evennia Portal/Server 재시작 및 ORM/캐시/scheduler 재구성.
3. A/B 순차 권리 검사 vs Barrier를 사용하는 동시 Gateway 회수. `test_simultaneous_players_share_single_server_lock_and_award_once`는 실제 서버 RLock·동일 연결 직렬화·SUCCESS/REFUSED·지급/알림 1회를 검사하므로 공식 **SQLite+단일 서버 계약에서 재사용 가능**하다. 독립 연결 row-lock/PostgreSQL·다중 서버 지원을 새 필수 범위로 확대하지 않는다.
4. mock time 159.999/160·통과 완료 deadline vs 실제 벽시계 Door 60초/Party 600초.
5. E2E-08의 stale Exit command DOM vs Action ID/UUID 기반 stale Item/Loot 요청.
6. Playwright 합성 composition vs 실제 Windows/Chrome 한국어 IME.

### Timing/Persistence의 중복 제거

`integration_e2e.py --profile pr`는 E2E-01~14다. `--profile persistence`는 **E2E-12/13의 동일한 부분집합**이므로 이미 성공한 현재 근거를 이름 때문에 다시 실행하지 않는다.

- **E2E-12:** 실제 Portal/Server 종료·같은 격리 DB 재시작·재인증 뒤 선택된 items/doors/installations/claims/currency/shares/legacy/profile/party snapshot을 비교한다. B-1 NumberScope/SelectionNumber·다음 counter의 명시적 비교는 없어 그 조건은 PARTIAL이다.
- **E2E-13:** Native A/B의 순차 회수 후 상위 Rollback과 재산/권리 불변·성공 알림 부재다. 동시 성공 지급 증거는 별도 R37의 Barrier 검사와 연결한다.
- **Full Smoke (R29-C08):** 현재 SHA의 CI는 Quick뿐이다. scripts/smoke.py의 Full 전용 실제 30초 Corpse→Ground·45초 respawn·120초 보호 만료 elapsed 및 smoke_closeout의 본부·두 임무·실제 재시작 증거는 Stage 2 안정화 후 smoke-full 1회로 확보한다. Door60/Party600과 별도이며 R20/R23/R37에 교차 연결한다.
- **격리 backup/restore (R12-C05):** 강화 E2E-12의 같은 소유 fixture에서 SQLite backup→소유 서버 정상 정지→별도 소유 파일 복원→실제 Evennia 재시작/재인증→B-1·재산·권리 비교로 통합한다. 운영 복원·강제 crash·별도 persistence 전체 run을 추가하지 않는다.
- **TIMING-DOOR/PARTY:** 일반 main/PR CI에 없다. Door는 통과 완료부터 60초 연장·중복 open 미연장·중간/만료 직전/최종 시각·양방향 거절/자동 닫힘을, Party는 실제 600초 오프라인·접속/재접속 후 리더 승계와 구성/권리를 검사한다. 현재 HEAD 증거를 한 번 확보한다.
- 별도 Release workflow는 현재 main을 guard하는 workflow_dispatch다. PR 승인 전 Source 검증을 대신하지 않는다. **배포용 Release 전체 8개 Job을 Stage 2에서 자동 dispatch하지 않는다.** 필요한 Timing은 같은 script를 격리 실행하고, 전체 Release/승인 병합 후 main 결과 판정은 T08/Stage 3가 소유한다.

## 3. T01~T08 담당 Case

- **T01 (38 Case):** P3-R01-C01, P3-R02-C01, P3-R06-C01, P3-R08-C01, P3-R08-C02, P3-R09-C01, P3-R09-C02, P3-R09-C03, P3-R11-C01, P3-R11-C02, P3-R13-C01, P3-R13-C02, P3-R14-C01, P3-R14-C02, P3-R15-C01, P3-R18-C01, P3-R18-C02, P3-R18-C03, P3-R18-C04, P3-R18-C05, P3-R18-C14, P3-R21-C01, P3-R21-C02, P3-R24-C01, P3-R24-C02, P3-R25-C02, P3-R27-C01, P3-R27-C02, P3-R28-C01, P3-R28-C02, P3-R32-C01, P3-R32-C02, P3-R33-C01, P3-R33-C02, P3-R34-C01, P3-R34-C02, P3-R36-C01, P3-R36-C02
- **T02 (27 Case):** P3-R03-C01, P3-R03-C02, P3-R04-C01, P3-R04-C02, P3-R05-C01, P3-R05-C02, P3-R07-C01, P3-R12-C01, P3-R12-C02, P3-R12-C03, P3-R12-C05, P3-R16-C01, P3-R16-C02, P3-R17-C01, P3-R17-C02, P3-R17-C03, P3-R18-C06, P3-R18-C07, P3-R18-C08, P3-R18-C09, P3-R18-C10, P3-R18-C11, P3-R23-C01, P3-R25-C01, P3-R26-C01, P3-R26-C02, P3-R31-C01
- **T03 (20 Case):** P3-R01-C02, P3-R02-C02, P3-R07-C02, P3-R07-C03, P3-R07-C04, P3-R07-C05, P3-R12-C04, P3-R18-C13, P3-R23-C02, P3-R29-C04, P3-R29-C05, P3-R29-C06, P3-R29-C07, P3-R29-C08, P3-R37-C01, P3-R37-C02, P3-R37-C03, P3-R37-C04, P3-R37-C05, P3-R37-C06
- **T04 (10 Case):** P3-R06-C02, P3-R10-C01, P3-R10-C02, P3-R18-C12, P3-R19-C01, P3-R19-C02, P3-R19-C03, P3-R19-C04, P3-R20-C01, P3-R20-C02
- **T05 (4 Case):** P3-R10-C03, P3-R15-C02, P3-R29-C02, P3-R29-C03
- **T06 (5 Case):** P3-R22-C01, P3-R22-C02, P3-R22-C03, P3-R35-C01, P3-R35-C02
- **T07 (2 Case):** P3-R29-C01, P3-R31-C02
- **T08 (4 Case):** P3-R30-C01, P3-R30-C02, P3-R38-C01, P3-R38-C02

Case ID는 실행 단위 수가 아니다. 같은 method/Fixture/scenario를 여러 행에서 참조해도 한 실행 결과를 교차 연결한다. 아래 계획은 모든 Case를 일괄 재실행하라는 목록이 아니다.

## 4. Stage 2 통합 실행 계획 — T01~T07

### 공통 착수·완료 규칙

Stage 2는 **별도 사용자 지시 후** 시작한다. 최신 main/작업 트리/CI·위 문서의 미커밋 변경을 보존하고 새로운 작업 브랜치 하나·PR 하나를 사용한다. 현재 main에서 Commit·새 브랜치 생성은 하지 않았다.

먼저 CSV 110 Case의 REUSABLE을 같은 환경/현재 코드에 적용 가능한지 확인해 채택하고, PARTIAL/CANDIDATE는 관련 Assertion을 더 찾아 **코드 추가/실행 전 재사용으로 해소할 수 있는지** 판단한다. GAP 다섯 개 중 R30/R38의 미래 Final Gate는 Stage 3 소유다. Stage 2의 실제 구현 공백과 수동 공백을 구분한다.

| Task / 코드 소유 영역 | 재사용 및 실제 추가 범위 | Fixture·명령 / 기대 결과 | 비용·실패 재검증 / 완료 조건 |
| --- | --- | --- | --- |
| T01 / commands, actions registry/parser/resolver/composer | E-TEST의 우선순위·별칭·수량/대상·기본 정책·충돌·동기 완료 재사용. R11 Provider 부재/진단·R13 두문 번호/별칭 결합·R18 Item 단독2 표시/조합·R36 대안 안내의 부족한 trace만 보완 | 기존 NativeItem/WorldCommand/validation fixture. 관련 module만 dev.py test. 선택 ID·Variant·Service·성공/거절·무변경/Prompt assertion | 코드가 같으면 기존 method 반복 없음. 수정 시 실패한 class/모듈과 공유 resolver 영향만. T06 새 fixture와 한 번 연결 |
| T02 / selection_numbers, item_entities, lifecycle | E-TEST의 공통 시설 Allocator RLock 경합·UUID/수량/번호·중첩 Rollback 재사용. R05의 실제 Corpse 생성/삭제·마지막 소멸 경합/예외 통합은 별도 확인하고 R03의 1삭제 예시와 결합한다. R12/R17의 실제 서버 재시작 B-1/Counter·격리 backup/restore, R26 Item 이름/별칭 변경의 Counter 불변 접점 보완, R31 9개 Scope/예외 정적 대응 | **기존 E2E-12**의 소유 DB fixture에 Root/inside/Corpse/Ground Item·Currency·Door·Enemy 및 NumberScope/SelectionNumber·next 값을 추적. 같은 소유 fixture의 backup·정상 정지·별도 소유 파일 복원과 실제 재시작/재인증 뒤 생존 ID/번호·counter 일치와 다음 신규 객체 번호 확인 | plain SELECT 검사로 대신하지 않음. 강화 E2E-12만 1회 실행하고 R05/12/17에 공유. 변경 없는 E2E-13 재실행 안 함. 서버 재시작 시 정상 만료 허용과 데이터 손실을 구분 |
| T03 / loot_claims/loot_service/item transfer, economy/combat/doors | E-TEST의 A/B·동시 Gateway·0지분·권리/Unique·경제/Quest 회귀 재사용. 실제 TIMING-DOOR/PARTY·Full Smoke 30/45/120초 및 R23의 실제 죽음/리스폰 번호 assertion 접점 | 기존 Native A/B·파티/외부인/부분 수량 fixture. timing profile 1회·안정화 후 smoke-full 1회·기존 lifecycle 시나리오의 번호 전후 보강. 지급량/잔액/XP·권리·번호·알림 1회·실패 0 | 단일 SQLite/Evennia 범위 유지. 실제 두 연결 전송이 별도로 필요한 조건은 Gateway Barrier 근거와 구분해 부족한 요청 경계만 추가. 고위험 지급/Lock 변경이면 해당 변경에만 신규 Auditor |
| T04 / gateway, inputfuncs, prompt, npc_dialogue, observation | E-TEST/E-SMOKE/E-BROWSER Session/Puppet/토큰/확인/중복·완료 재사용. R10 stale reset/이동 및 R15·R20 관찰/Lifecycle 결합의 부족한 채널만 보완 | 실제 text/Typed invocation 비교와 View/Help/state 반복. 숨겨진 정보·다른 Session·Prompt·거절 재산 불변, 커밋 후 상태/출력 | Service 계산/권리 규칙 복제 금지. Session 보안 변경일 때만 Auditor. 영향받은 Prompt/대화/Action class와 실제 시나리오 재검증 |
| T05 / primal.js, browser specs·안전 증거 | 기본 Chromium/12·pr14의 유효 근거 재사용. 변경된 R10/R15/R22 접점 UI 및 실제 Windows IME·수동 시각 점검 | 기존 browser_e2e Harness. Desktop 1280x900/좁은390x844 대표 UI. Action payload의 UUID/Scope, Prompt·출력·버튼 효과 검증. 아래 수동 IME 절차 별도 | E2E 전체14를 개발 매번 실행하지 않음. 변경 scenario만 --scenario 선택. JS 변경 시 node --check+contracts, 정적 자산 변경 시 최종 collectstatic 후 확인. OS 수동 결과 없으면 NOT RUN/미충족 유지 |
| T06 / 테스트 전용 ContentPackage·fixture | R22 직접 수용 GAP, R35 두 NPC 표시는 같은 fixture로 해소. 기존 registry/runtime negative는 재사용 | 새 공개 Verb 1개(운영 Manifest에 넣지 않음), 서로 다른 Service 2개를 한 NPC에 선언. 구분 가능한 Variant/Role. 기존 Shop/Quest/Dialogue 등 도메인 서비스를 연결하거나 동일 의미의 테스트 전용 명시 서비스 구성. Loader→Index→Help→실제 Command→Typed Web→각 Service 효과 1회/거절0·DB/권리 보존을 assert | 공통 parser/중앙 COMMANDS/dispatcher의 소스 수정 없이 통과해야 함. 한 테스트 패키지/통합 scenario에 정상2서비스·Confirm/Prompt·복수 Provider/별칭 충돌·2NPC 표시를 묶되 독립 assertion 유지. 필요하지 않은 운영 콘텐츠·새 게임 정책 추가 금지 |
| T07 / registry call graph, Help, 사용자/설계 docs, AGENTS.md | E-PRE·M06 독립 리뷰/매핑 재사용, 최신 변경 범위 재감사. R29 기능표별 의미 동등성 대조·R31 Scope 표 및 AGENTS.md §3 번호 설명 감사 | runtime 등록/실제 호출/typed payload와 act/perform_action/web_actions 검색을 함께 대조. 문서12개·Help6섹션·별칭/Provider/비공개 표시·승인 Legacy 유지 확인. AGENTS.md의 임시 번호 설명을 #44 B-1 대상, 기존 Player/Party 예외, 무번호 Engine/기타 객체, 여전히 유효한 DEFAULT/INDEX/ALL·자연어/compact label 설명으로 분리하고 Stage2 T07에서만 최소 수정 | 문자열 발견만으로 삭제/전체테스트 실행 안 함. docs/phase3-validation.md 역사 기록 보존. 새 테스트/코드/문서 한 최종 통합 Reviewer 회차, 좁은 수정만 bounded follow-up |

**T06 구체 수용 관측:** 인덱스 등록 전후 새 Verb/Action/Binding/Role을 확인하고, 새 NPC를 실제 방에 배치해 각 서비스별 입력과 웹 payload가 지정 NPC/Variant/Service로만 가는지 검사한다. 호출 카운터만 있는 validation record를 실제 도메인 효과 전체의 증거로 오인하지 않는다. 서비스 2개는 서로 다른 ServiceDefinition과 서로 구별되는 결과를 가져야 하며, 기존 상점 메뉴/임무 조회처럼 읽기 동작을 선택하면 그 순수성·권한·출력도 검사한다. 두 번째 NPC 및 현재 권한 변화를 넣어 모호성/숨김/명시 선택을 함께 증명한다. 신규 공개 Verb+복합 NPC의 요구조건은 단순 compile 성공만으로 완료되지 않는다.

### 실행 묶음 — 모두 미실행 계획 명령

명령은 저장소 루트의 PowerShell 예시다. 아래의 선택 모듈 명령은 **변경/공백이 실제 있을 때만** 고른다. REUSABLE 79개를 위해 전부 실행하지 않는다. mixed-in method는 구체 TestCase 확인 후 라벨을 선택하며 기본은 관련 모듈로 묶어 fixture setup을 공유한다.

```powershell
$p3Python = ".\\.venv\\Scripts\\python.exe"

# T01/T06 신규/영향 모듈만: 새 수용 테스트 모듈명은 구현 시 확정
& $p3Python scripts/dev.py test tests.test_action_registry tests.test_action_runtime tests.test_action_cutover --parallel 1

# T02~T04 변경이 실제 있는 모듈만 선택
& $p3Python scripts/dev.py test tests.test_selection_numbers tests.test_loot_action_invariants tests.test_npc_dialogue --parallel 1

# 강화한 실제 재시작 시나리오만: 변경 없는 E2E-13을 함께 반복하지 않음
& $p3Python scripts/integration_e2e.py --scenario E2E-12

# 일반 CI에 없는 production 60/600초 두 시나리오, 한 번
& $p3Python scripts/integration_e2e.py --profile timing

# 공통/넓은 코드 변경으로 전체 검사가 필요해진 경우 안정화 뒤 1회
& $p3Python scripts/dev.py check
& $p3Python scripts/dev.py test --parallel 4

# Stage 2 안정화 후 실제 30/45/120초 Full Smoke 1회 (Door/Party timing과 별도)
.\.venv\Scripts\python.exe scripts/dev.py smoke-full

# Stage 2 최종 제품 기준 Quick, Push 후 해당 Source HEAD 필수 CI 4개
& $p3Python scripts/dev.py smoke
```

새 확대 fixture/시나리오의 이름이 확정되면 CSV PlannedTest에 실제 명령·실행 ID·Fixture를 연결한다. 예상 이름만 있는 신규 테스트를 기존 실행 증거로 적지 않는다. `scripts/browser_e2e.py` 전체 실행과 integration `--profile pr`는 실제 변경 영향이나 최종 검증 필요에 맞춰 한 번만 통합한다. 안정화 이후 문서만 바뀌었다면 게임 검사를 반복하지 않는다.

### Windows/Chrome 실제 IME·수동 UI 기록

실제 Windows에서 한국어 Microsoft IME와 Chrome 안정판의 버전·OS 빌드·화면·입력기를 기록한다. 테스트 계정/격리 서버만 사용한다.

1. 조합 중 한글·받침/띄어쓰기/다단어 후치 명령을 입력하고 조합 중 Enter가 조기 실행·중복 전송되지 않는지 확인한다.
2. 조합 완료 후 Enter 1회가 실제 게임 명령/Prompt 1회인지 확인한다. Backspace·Esc·History·단축어/묶음·Prompt 입력·취소·재접속에서도 조합 깨짐/오발송을 기록한다.
3. 같은 허가된 대상의 직접 명령과 Typed 버튼 결과/UUID/재산·권한·거절 의미를 비교한다. NPC·Shop·Door·Item·Loot와 Desktop/좁은 화면의 버튼/Focus·출력·비공개 상태를 확인한다.
4. 합성 composition 테스트와 수동 기록을 별도 Case 증거로 보관한다. 성공/실패·재현 순서·실제 전송 횟수·sanitized 화면/로그·적용 SHA를 기록한다. 수행자가 없거나 실제 IME를 확인할 수 없으면 **NOT RUN 또는 BLOCKED**, 최종 Gate 완료 금지다.

## 5. 격리 DB·증거 안전성

공식 SQLite + 단일 Evennia Server만 사용한다. tests는 settings_test, 실브라우저/재시작은 기존 Harness의 새 marker/전용 포트·fixture 계정·run_dir로 실행한다. 운영 DB에 직접 접근하지 않으며 복사·조회·해시 계산·Migration/Seed/초기화를 하지 않는다. 테스트 전용 DB만 별도 소유 경로/격리 환경에 생성한다. 실행 전 운영 DB 경로를 열지 않고 Harness 설정·테스트 환경변수와 명시된 경로의 분리 및 소유 marker/포트를 검증한다. 운영 서비스와 타 에이전트 프로세스를 중지하지 않는다.

Stage 2 실행 담당자는 소유 경로·프로세스/포트·DB·자격 증명 정리 책임을 먼저 기록한다. 재시작/실패 주입은 새 격리 DB에만 수행하며, fixture backup은 SQLite backup API로 같은 소유 run_dir의 새 파일에 생성하고 기존 파일을 덮지 않는다. 복원은 소유 서버를 정상 정지한 뒤 소유 백업으로만 하며 같은 환경에서 무결성·재인증/번호/수량/권리를 확인한다. 활성 transaction 도중 복사·운영 파일 교체는 금지한다.

- 테스트 전용 DB의 전후 fingerprint와 예상 변경/거절·Rollback 시 데이터 무결성을 비교한다. 운영 DB fingerprint 확인은 요구하지 않으며 운영 DB를 열거나 복사·조회·해시 계산하지 않는다. 백업·복원·Rollback·실제 재시작은 테스트 전용 DB에서만 수행한다. 소유 서버/브라우저 종료·credentials 제거를 기존 Harness로 확인한다. 성공한 소유 임시 자원만 정리하고 실패 진단은 보존한다.
- Windows 재귀 정리/이동 전에 절대 경로가 소유 workspace/run_dir 안인지와 marker를 검증한다. 타 작업 산출물·과거 실패 DB를 임의 정리하지 않는다.
- 비밀번호·token·입력 원문·개인 정보·DB·trace/video를 공개 Artifact로 업로드하지 않는다. 기존 허용목록의 sanitized evidence와 안정 ID/수량 등 필요한 비식별 관측만 사용한다.
- Postgres·독립 서버 row-lock, 강제 crash/운영 복원 검증은 이번 공식 보장으로 확대하지 않는다. 실패/rollback·정상 재시작·백업/복원 검증은 각각 다른 Case 증거로 기록한다.

## 6. 비용 최소화·실패 시 범위

예상치는 기존 CI 실측 또는 타이머 최소값이며 보장 시간이 아니다.

| 묶음 | 비용 참고 | 최소화 방식 |
| --- | --- | --- |
| 기존 unit/integration 전체 | CI 통합 1,063개 1113.645초, 로컬/병렬 수에 따라 다름 | 같은 SHA의 유효 79 Case는 재실행하지 않고 추가/실패 module 우선 |
| Quick+Action E2E | Quick61.911초 + 별도 server restart E2E | 최종 제품에서 한 번. 실패하면 해당 단계·변경 영향만 진단 |
| 기본 Chromium+pr14 | 기존 기본60.296초/통합796.499초 | 변경 시나리오만 개발 검사, 최종 CI 전체는 그대로 유지 |
| Full Smoke | 실제 30/45/120초·본부/두 임무·재시작 및 setup | 안정화 후 1회, R29-C08과 R20/R23/R37 공유. Quick/timing으로 대체 금지 |
| E2E-12 강화 | 기존 해당 시나리오의 setup·재시작 비용 | R05/12/17·backup/restore 공동 증거로 연결. persistence 프로필 전체와 중복 금지 |
| TIMING-DOOR / PARTY | 실제 60초/600초 + setup·정리 | 두 production timing을 한 번 순차 실행. sleep 단축·mock으로 대체 금지 |
| 실제 Windows IME/수동 UI | 수행자/환경 확보가 필요 | 자동 체크와 동일한 fixture/화면 재사용, 수동 증거는 별도로 남김 |

실패 시 Assertion 삭제·timeout 임의 증가·fixture 사전 지급·Mock 확대로 결함을 숨기지 않는다. 재현 로그와 원래 실행을 보존하고 관련 제품/설정/fixture Diff를 확인한다. DB/권한/지급 고위험 수정은 신규 Auditor, 일반 회귀는 최종 Reviewer가 담당하되 같은 검사를 형식적으로 반복하지 않는다. 구현자·검증자의 파일/DB 자원 소유권과 동시 최대 3개·중첩 금지를 따른다.

## 7. PR 하나와 Stage 3/T08 인계

Stage 2는 V01/T01~T04와 V02/T05~T07을 한 작업 브랜치·PR로 통합한다. 독립된 선행 의존이나 안전상 필요가 실제 확인되지 않으면 V01/V02 PR을 나누지 않는다. Agent는 조사/구현/리뷰 목적에 맞춰 필요한 역할만 사용한다. 현재 Stage 1의 Scout/Reviewer는 파일·Git 쓰기 없이 조사했고 두 문서는 Orchestrator가 통합한다.

Stage 2 제출 조건:
- 모든 38행의 필수 하위 Case를 실제 결과/재사용 적용성/실행 ID·SHA·환경에 연결하고 미충족을 숨기지 않는다. 수동 조건이 남으면 PR/보고는 Hold/미완료로 구분하며 최종 A로 가장하지 않는다.
- 새 Verb/2Service NPC 수용과 실제 timing·강화 persistence 등 새 공백을 실행 검증한다. 고위험 지적과 일반 결함을 해결하고 최신 Diff에 최종 통합 Reviewer 1회 중심으로 검토한다.
- 변경 영향 check/직접 회귀·최종 Quick와 PR Source HEAD의 필수 test/smoke/contracts/browser-e2e 4/4 SUCCESS. 예비 리뷰·CI 성공은 병합 승인이 아니다.
- PR OPEN/non-Draft/사용자 승인 대기, 자동 Merge/Issue Close/브랜치 삭제 없음. 기존 사용자 변경과 두 미커밋 준비 문서를 보존한다.

**T08은 Stage 3 소유**다. 38행 전수·모든 하위 Case/수동/실제 시간·재시작·신규 선언 확장 증거의 적용 최종 SHA 감사, 최종 독립 리뷰, 필수 전체 로컬/원격 검증 적합성 판정·최종 보고·사용자 승인 후 Merge/main CI/Closeout을 남긴다. Stage 2에서 이미 확보한 같은 최종 제품/테스트·환경·조건의 실행은 Stage 3에서 적용성을 검토해 재사용하며 형식적 전체 재실행을 추가하지 않는다. Final 이전 코드/설정이 바뀌면 영향받는 검사·리뷰만 갱신한다.

Release workflow의 현재-main guard 때문에 승인 전 PR을 위해 dispatch를 우회하지 않는다. 최종 병합 후 실행을 요구하는 Release/Timing/Persistence 증거의 적용성은 Stage 3가 판단하고, Stage 2에서 같은 scenario/동일 조건을 이미 검증했다면 지원되는 근거로 연결해 반복 비용을 평가한다. 운영 Migration/Seed/복원은 별도 명시 승인 대상이며 Phase 3 테스트 fixture 검증과 혼동하지 않는다.

## 8. Stage 1 완료 검토

- 읽기 전용 Scout `scout_oriole`: T01/T04~T07의 Assertion/브라우저/확장 공백 조사. 공식 R번호 초반 오기를 정정하고 stale Exit vs Typed Action 및 persistence 부분집합을 구분했다.
- 읽기 전용 Scout `scout_marlin`: T02/T03의 번호·Item·권리·Door·재시작 조사. 동시 Loot Barrier 검사 존재를 재확인해 불필요한 다중 DB/경합 재시험을 요구하지 않도록 보완했다.
- 최종 문서 소유자: Orchestrator. 읽기 전용 Reviewer reviewer_larkspur는 공식 38행·실제 Assertion/fixture·원격 4 Job 로그를 독립 확인했다. 최초 B 판정의 P2 지적(증거 과대범위·정확한 참조·번호/별칭 결합·Full Smoke/backup 추적)을 반영했다. R18/R26/R13은 PARTIAL, R12 snapshot은 number만 주장하도록 축소하고 대화/동적 이동/registry의 정확한 method를 연결했다. Full Smoke와 backup/restore Case를 추가했다. 후속 좁은 재확인에서 집계 잔여 2곳과 보상 개인 출력의 정확한 method 연결을 추가 보완했다. Reviewer가 이 두 정정까지 재확인한 최종 판정은 **A — Ready for Review(Stage 1 계획 준비), 잔여 P0/P1/P2 0/0/0**이다. Phase 3 실행 성공이나 Final Gate 완료 판정이 아니다.
- 실제 Close 도구가 없어 Done과 Close·슬롯 해제를 동일시하지 않는다. Auditor는 새 고위험 변경이 없고 이번은 정적 증거 조사여서 추가하지 않았다.
- Stage 1 수행: 정적 소스/Assertion·Workflow·기존 CI 로그·Issue·환경 메타데이터 읽기와 문서 형식 검증만. 테스트/Quick/Smoke/E2E/CI 재실행·서버·DB·제품/테스트/설정 변경·Git Commit/Push·branch·PR/Issue 변경은 수행하지 않았다.


### 이번 최종 보완의 검토 범위

사용자 P2-1~4를 Orchestrator가 두 문서에 한정해 정적 보완했다. R03은 이미 존재한 시체 전용 링크의 Assertion 범위를 명확히 했고 R05-C01만 REUSABLE→PARTIAL로 변경했다. R05-C02의 snapshot/실제 재시작 구분 및 R31-C02의 AGENTS 감사 계획을 연결했다. CrossTask의 +/범위/규범행 혼합 14개 값을 Task 쉼표 목록으로 정규화하고 기존 정보를 보존했다. Case ID·Primary Task·Status는 변경하지 않았다.

이전 Reviewer A는 이전 문서 버전의 독립 검토 기록이며 이번 보완의 새 독립 리뷰 결과로 표현하지 않는다. 이번 작은 문서 보완은 새 에이전트 없이 Orchestrator가 패키지 9개/공식38행/변경 Assertion/CSV 형식·집계·승인 경계를 직접 대조했다. 검토한 P2 네 범주는 해소됐고 확인된 잔여 P0/P1/P2는 0/0/0이다. **A — Ready for Stage 2(문서·실행 계획 준비만)**이며 실제 Phase3 Case/행은 모두 NOT RUN, Stage2는 별도 지시 전 미착수다.


## 9. Stage 2 실행 결과 및 Stage 3 인계 — 2026-10-22~23 KST

이 절은 시간순 실행 이력을 보존한다. 중간 실패·판정과 후속 보완을 구분하며 최신 종합 상태는 마지막 결과 절과 PR #75 Validation을 따른다.

### 기준선·범위와 증거 채택

시작 main/origin/main은 `ea4072c0e01f14dad268591fda1096e1f413ef2b`, 열린 PR0, Worktree1개였다. 기존 미커밋 Stage1 문서2개를 보존해 `codex/issue67-phase3-integration` 하나에서 진행했다. #44/#67 OPEN, #65/#66 CLOSED이며 v4.3 원문/기존 Closeout은 변경하지 않는다. T01~T07의106개 Case만 대상이며 T08의4개 Case는 NOT RUN으로 남긴다.

기존 REUSABLE79 중 Stage2 주담당은77개(T08의2개 제외)다. 초기 근거 채택 당시 관련 제품/규칙/저장/Loader/Parser/Registry/Resolver/Gateway/Service/ContentPackage/가격/권리 정의는 기준선과 동일했다. 이후 표시 계산 보완(0e9b87c)은 공통 Presentation의 반복 관찰 조회만 바꾸므로, 해당 표시 경로는 별도 영향 회귀와 실제 브라우저/Full로 재검증한다. 실행·지급·권한·번호·저장 도메인은 변경하지 않았다. 기존 규칙232·통합1063 및 실제 브라우저/Action E2E의 Assertion·fixture·SHA와 연결되는 좁은 계약을 채택한다. 새 fixture/검증 Harness 변경은 기존 Domain 성공을 새 실행으로 표현하지 않으며 영향받은 실행기·실제 재시작·브라우저 조건만 새로 확인한다. PARTIAL/CANDIDATE/GAP은 해당 추가 근거가 확보되기 전까지 PASS로 올리지 않는다.

### T07의 Scope·실행 경로 정합성

아래 표는 Issue44 §4.2의 논리 Scope와 `selection_numbers.api.descriptor()/records_for()/number_for()`의 실제 분기, `NumberScope/SelectionNumber` 제약, 기존 기능별 Assertion을 대조한 것이다. 물리 owner와 논리 Scope를 혼동하지 않는다.

| 규범 범위 | 실제 Scope / Group / 근거 |
| --- | --- |
| Room + Corpse | room:<roomID> / world:corpse, 실제 Corpse 생성·삭제 mixin과 신규 첫삭제/경합 회귀 |
| Room + Enemy | room:<roomID> / enemy:<enemy_id>, respawning에도 같은 ObjectDB ID/번호, 신규 실제 사망·reconcile 회귀 |
| Room + NPC/시설 | room:<roomID> / 명시 selection_group_id 또는 definition/typeclass, 신규2NPC 공유group 및 기존 충돌/이동 회귀 |
| Room + Door | room:<roomID> / world:door, Endpoint 실제Exit ID와 같은방 공통 번호·별칭 선택 회귀 |
| Character + Root ItemEntity | character:<characterID> / 명시그룹 또는 item:<definition_id>, inventory/equipment 물리 위치를 같은 Scope로 관찰 |
| Parent UUID + inside ItemEntity | inside:<parentUUID> / Item그룹, 부모 이동 후 Scope유지·추출 시 새번호, 기존Storage/Inside Assertion |
| 논리 Container + Item | shared_storage:<containerID> 또는 personal_storage:<characterID> / Item그룹, 기존보관 API의 실제 location_kind와 소유예외 Assertion |
| Corpse + Loot Item/Currency | corpse_loot:<sourceID> / Item그룹 또는 currency:credits, LootClaim 가용성과 정규번호 분리 |
| Room + Ground Loot Item/Currency | ground:<roomID> / Item그룹 또는 currency:credits, Source가 달라도 같은 논리RoomScope; stale 원래UUID 거절 |

Room 자체는 Provider 참조를 제공하되 번호 저장 대상이 아니다. 기존 Player/Party·전투 참가자 목록 번호와 비대상 Engine/기타 객체는 B-1로 강제 전환하지 않는다. AGENTS.md §3의 임시번호 설명만 현행화하고 DEFAULT/INDEX/ALL·여러출처 문법·자연어Room/compact Control 표현은 보존했다.

운영 Manifest는 기존 room_npc/item_shared/item_equipment/storage/firearm_lighting/loot를 유지한다. `commands.registry`와 `docs/action-migration.md` M01~M06 매핑의 전환동사는 Dynamic Command 또는 Typed Web → Resolver → Gateway → Binding/Service → 기존 Domain으로 단일 실행한다. 신규 회귀 fixture만 settings override Loader로 넣고 운영 Manifest/중앙 Command 수동분기/Parser/Registry/Dispatcher는 수정하지 않았다. 전역 봐·말·도움, pz_dialogue, Engine/Exit·이동·전투·Player/Party·버려/줘·줄임말/묶음 및 Historical 읽기 API는 승인 유지 경로다. 단순 문자열 발견이나 과거 기록을 현재 활성 Legacy로 오판하지 않는다.

### 구현·안전성 및 발견한 실패 보존

- 신규 Native 회귀는 실제 Corpse 첫삭제/경합/예외, Item 표시·결번/reset·이름/별칭/Counter, 두 Door Endpoint 선택, Provider없는 실제 붕대 사, 숫자실명/가시성, 실제 Enemy사망/respawn을 보완한다.
- 테스트전용 ExtensionBroker는 새 Verb 조율/중개, 예치/반환 서로다른2Service, 실제 지갑↔NPC 원장/영수증, Loader/Help/execute_cmd/pz_action/Typed Gateway·Confirm/Prompt·권한/예외Rollback·복수NPC/모호성을 검증한다. 운영 게임 경제/콘텐츠를 추가하지 않는다.
- 기존 Smoke/Browser/Action E2E의 운영DB 해시 호출을 제거했다. 소유Run/marker/격리설정 검증 후 테스트DB의 전후 fingerprint만 기록한다. 데이터가 바뀌는 정상 게임실행에서 hash 동등성을 요구하지 않고 실제 상태 Assertion으로 무결성을 검증한다.
- Auditor 지적을 반영해 정상 재시작은 공식 Evennia AMP 종료→소유Popen exit0 확인을 사용하고 강제정리 fallback을 정상재시작 성공으로 채택하지 않는다. backup/restore 경로의 dangling symlink·외부경로·기존파일을 거절하고 배타생성·integrity_check·정지DB보존을 적용했다. 준비부분실패는 원래오류를 fingerprint오류로 덮지 않는다.
- 최초14개 신규회귀 중 Item표시1개 실패: descriptor()는 번호를 결합하지 않는 순수metadata API였다. records_for() 및 실제 inventory_rows()를 사용하도록 Fixture/Assertion 경로를 수정했다. 기대값을 완화하지 않고 후속14개 모두PASS(13.206초).
- 최초 FullSmoke(`work/smoke/full-rs5ygzjt`)는 corpse→ground28.391초 vs 기존하한28.5초에서 FAIL. 플레이어 화면을 기다린 뒤의 death_seen을 서버사망 시각으로 오인한 측정경계였다. 소유DB의 실제 Corpse.created_at을 같은호스트 시계에 연결하도록 검증코드만 수정했고 허용오차/운영타이머는 변경하지 않았다. 실패DB/로그는 보존한다.
- 최초 강화E2E12(`work/browser-e2e/run-9rhhwrwl`,239.448초)는 복원뒤다른방에서 버린Item을 hq_concourse의 Counter와 비교한 Fixture오류로 FAIL. 같은 Ground Scope의 실제목적지로 공개Exit를 통해 이동하도록 수정했다. 이때 강제stop 경로는 최종 정상재시작 근거가 아니며, 수정후 새 실행으로 검증한다.

### 수동·최종 경계

이 환경의 네이티브 OS 입력기 제어가 제공되지 않아 Windows/Chrome 실제 한국어 IME는 검증하지 못했다. Playwright 합성composition/Chromium자동화 성공을 대신 쓰지 않는다. R29-C03은 BLOCKED/MANUAL PENDING이며 위 수동절차와 실제 OS/Chrome/입력기버전·전송횟수·Prompt·재접속 근거가 필요하다. 실제 모바일·PostgreSQL/다중서버는 UNVERIFIED다.

PR은 단일 Draft/HOLD로 준비하며 수동증거 확보 전 Merge Ready/A로 표현하지 않는다. Stage3 T08의4Case·38행전수최종감사·사용자병합승인·병합후main CI·Issue Closeout은 미수행으로 남긴다. 운영DB 접근/조회/복사/해시·Migration/Seed/복원은 수행하지 않는다. 실제 실행 및 원격CI 결과는 아래 최종 집계에 추가한다.


### 직접 영향 검사·실제 실행 근거 — 진행 이력

아래 진행형 상태는 각 실행 당시의 기록이다. 이 절 끝의 최종 집계가 현재 상태이며 과거 실패·미확정 원인은 보존한다.

| 실제 명령/실행 | 결과·범위 |
| --- | --- |
| dev.py test tests.test_phase3_regression tests.test_phase3_extension --parallel 1 | 기존9+확장5=14 PASS / 13.206초, 최초 Item metadata/번호 결합 실패 후 보완 |
| dev.py test tests.test_phase3_regression.Phase3VisibilityTests --parallel 1 | 1 PASS / 14.147초. 최초 WorldFixture의 생성후enemy_id로 번호없음 및 서로다른입력반향 비교 실패를 보존하고, 처음부터ID선언·같은입력 부재/어둠 비교로 보완 |
| Item 표시 method 단독 재검사 | 1 PASS / 3.309초. 추가검사에서 단독1 생략을 의무로 가정한 실패를 확인했다. #44는 생략 가능이므로 현재 label/selector의 명시1을 유지하며 검증했고 제품표시 코드는 바꾸지 않음 |
| unittest test_integration_runner.py | 13 PASS / 4.761초. 새4개는 backup/restore·외부/symlink·정상종료 경계, 실제수용E2E와별개 |
| unittest test_smoke_ownership.py | 2 PASS / 0.008초. 운영DB 연결/관측 전 거절·환경변수분리; CI smoke Job에도 추가 |
| unittest test_browser_runner.py | 24 실행 / 23 PASS·기존 POSIX 전용1개 Windows SKIP / 5.165초. Skip신규추가 없음 |
| integration_e2e.py --scenario E2E-12 | PASS / 239.500초, work/browser-e2e/run-wasv0si1. 실제 Chromium156.0.8078.4·소유 정상종료·복원·B-1·권리·재인증 |
| integration_e2e.py --profile timing 중 TIMING-DOOR | PASS / 215.962초, work/browser-e2e/run-oj5sp81j. 실제60초/통과완료연장·중복open미연장·만료양방향거절 |
| dev.py check / git diff --check | PASS. 이후 문서/개별Assertion 변경은 해당 범위만 정적/직접검사 |


최종 Reviewer의 중간 지적을 반영해 E2E-12에 **같은 DB의 Corpse 마지막 삭제·두 생성 경합**을 setup에 추가했다. 경합 후2/3·Counter4/생존ID·삭제ID를 저장하고 실제 재시작·복원 후 전체 NumberScope/SelectionNumber 및 개별 행을 비교한다. Evennia SaverList는 deserialize()로 plain배열로 투영하며 JS Array.isArray/길이2를 검사한다. 해당 후속 E2E-12는 **PASS / 206.500초 / work/browser-e2e/run-9vhx95hr**다. 앞선239.500초 실행을 이 보강의 새 실행으로 표현하지 않는다.

실제 Timing profile은 **2 PASS / 963.491초**다. TIMING-DOOR는 위215.962초, TIMING-PARTY는 **747.262초 / work/browser-e2e/run-yfkl0jor**로 실제600초 오프라인/중간·직전·최종 시각/권리·구성불변·리더승계·재접속을 확인했다. 새 Runtime제품 변경이 없어 해당Timing 실행 파일과 후속Fixture/문서변경은 서로 영향을 주지 않는다.


당시 검증 코드 스냅샷은 `86dd2c6db5dd7e7b72004e762fad7cb5055d9e17`이다(초기 구현 `5f63f7eed470848b8e69668313612ad6da6475d7` + 독립 리뷰 보완). E2E12/단위 검사는 커밋 전 동일 파일의 명시 Diff에서 실행됐으며, 이후 변경은 해당 Assertion 보강 및 문서/증거 정리에 한정한다. Timing에는 후속 E2E12/Item 테스트 보강이 영향을 주지 않는다. 최종 Source HEAD와 필수 원격 CI의 정확한 실행 URL은 단일 PR의 Validation에 기록하며 문서만 달라진 새 Commit을 이유로 같은 로컬 게임검사를 반복하지 않는다.

소유 실행 결과의 읽기 가능한 정제 요약은 ignored `work/issue67/stage2-observed-evidence.json`에 제공했다. 원본 E2E `run.json/results.json`의 정제 메타데이터와 root가 실제 도구 stdout에서 관측한 단위결과 요약을 구분하며, stdout 요약을 원본 로그 파일이라고 주장하지 않는다. 읽기 권한이 거부된 원본 Artifact에 대해 Reviewer가 직접 확인했다고 기록하지 않는다. 최종 CI 로그는 정확한 Source HEAD의 별도 원격 실행 근거다.

위 표의 Django 테스트 시간은 테스트 본문 시간이며 DB setup/teardown을 포함한 총시간과 다르다(최종14개 total27.335초, Visibility total26.112초, Item후속 total12.600초). E2E/Timing의 실행기 seconds는 setup·브라우저·정리를 포함한 실제 wall time이다. 과거 실패의 미측정 총시간을 임의 합산하지 않는다.


후속 Full(`work/smoke/full-zgxtys4z`)은 실제 시체30/리스폰45/보호120초 경계를 **31.016/45.915/122.018초 PASS**했지만 본부 장비 검사가 과거 `절단마체테 [주무기]` 문자열을 기다려 timeout FAIL했다. 현행 B-1 표시의 명시번호를 반영하지 않은 과거 검증 가정이며 전체 Full 성공으로 기록하지 않는다. 뒤쪽 방어구·장도 검사도 같은 방식인지 감사하고 실제 UUID/정규 selector·장착/주무기·격리 DB 효과를 연결하도록 보완한다. 타이머·게임표시/경제·timeout을 바꾸지 않는다. R29-C08은 현재 FAIL/PARTIAL이며 후속 실제 성공 전 PASS로 올리지 않는다.


Chromium 기본 통합 실행은 **PASS /147.150초 /work/browser-e2e/run-qgdkqtp3 /HEAD86dd2c6**이다. TEST-66B의 실제 버튼 Scope 이동 후 새 요청ID stale 거절 및 TEST-66C의 병합 후 UUID·두 viewport를 확인했다. 마스킹된 1280×900/390×844 스크린샷을 직접 확인해 가로 overflow 없는 배치와 입력/장비 버튼을 확인했다. 로그와 입력의 자홍색 마스킹은 증거 보안 처리이며 게임 화면 결함이 아니다. 실제 OS IME의 근거로 확대하지 않는다.


추가 Full(`full-3idkch_x`)은 본부 UUID/정규번호 장비 검사와 실제30/45/120초(31.447/46.117/121.078초)를 통과했으나 후속 탐사화 구매의 수량증가 대기에서 FAIL했다. 이 실패의 원인은 사후 DB의수량1만으로 확정할 수 없다. 독립된 새 격리 공개 재현(`quick-sr_ecpv4`)에서 같은 구매를 두번 수행해0→1→2,150→120→90,서로다른UUID·각30칩차감을 확인했다. Unique 제한은 없으며 확률드롭으로 미리 소지할 가능성과 구매 timeout원인을 혼동하지 않는다. 새구매UUID를 명시하는 검사와 실패진단을 보완한 뒤 Full 전체를 재검증한다. 실패 증거는 보존하며 미확정 원인을 임의로 게임결함/환경문제로 확정하지 않는다.


최종 Quick은 **PASS /148.724초 /quick-xi_uymvo**이며 소유 프로세스·임시 DB 정리까지 완료했다. 이번 Full 전용 장비검사 변경은 Quick 경로에 영향이 없어 같은 Quick을 반복하지 않는다. Lifecycle Case R20-C02는 실제 Door60초 Timing과 이 Quick 및 기존 고정시간 Assertion의 각 범위를 구분해 PASS로 채택한다.


Action E2E 후속 실행(`quick-er2yt53_`)은 실제Text/Typed ID/Confirmation/재전송/정상재시작 Assertion이 모두 통과했지만 최종 discard가 Windows WinError32(channel_mudinfo.log 열린파일)로 실패하여 **전체 FAIL**이다. 현재 원인은 미확정이며 final stop의 강제종료·Windows 로그핸들 경계를 조사한다. 파일정리 실패를 무시하거나 임의 대기·재시도로 PASS 처리하지 않는다. 해당실행의 정리실패와 부분삭제된 소유진단 경로를 보존하고, 운영/타작업 프로세스는 중지하지 않는다.


Action E2E의 성공 종료에만 공식 AMP 종료를 먼저 요청하고 finally의 기존 소유프로세스 정리를 보장하도록 최소보완했다. 정상종료실패는 그대로 전파되어 discard/PASS하지 않는다. 후속 실제 `scripts/action_e2e.py`(root 실행33755)는 **Text/Typed ID/Confirm/replay/정상재시작 + 소유 process/fixture cleanup 전부 PASS(exit0)**다. 실행기전체 wall time은 별도계측하지 않아 추정하지 않는다. 앞선WinError32의 정확한 핸들 소유자는 미확정이며 후속성공을 근본원인확정으로 표현하지 않는다. 정상/실패/원오류보존 pureunit3개를 추가해 ownership suite최종5개를 검증했다. 공유Harness.stop 구현은변경하지않았다.


기존 `world.test_smoke`의 과거 subprocess patch가 새정상종료위임과 맞지 않아 1개ERROR를 실제재현했고, 전체순수계약검사에서 15PASS/3FAIL(옛stop Mock2개 및 Native identity없는boots Fixture1개)을 확인했다. 기존4method의 검증목표를 보존하면서 현재경계로 현행화해 **18 PASS/1.550초**다. 공식 AMP명령/cwd/env/check·소유PIDexit0/비0거절·소유검사선행/오류전파·restart순서·원오류·동일DB/env/ports·dropUUID보존/신규구매UUID/정확차감을 검증한다. 제품Domain 변경이 아니라 기존 실행기계약테스트 현행화다.

Full의 선행 stop_for_restart()와 Harness.restart()가 정상종료를 중복요청하는 부분은 Full/check_alive 전제를 유지하고 Harness.restart()의 정상종료→stopped snapshot→시작 경계 한번으로 정리했다. 역사적다른호출자가 있는 stop_for_restart() 함수는 보존한다. 이전 stopped/after·광원정산·UUID/수량/시간 Assertion은 그대로다.


R10-C03의 기존66C는 split/merge뒤삭제한원UUID와새Source를 구분했지만 번호reset을명시단언하지않았다. 같은Ground그룹 전체소멸→표시1재발급·다른subjectUUID를 직접단언하도록 세부검사를추가했다. 기존브라우저 성공범위를Scope/merge로보존하고 이Case는후속브라우저확인전NOT RUN/PARTIAL로되돌린다. 실제실행없는PASS확대를피하기위한추가정밀화다.


후속 Full(`full-t9iilp90`)은 실제시체31.126초/리스폰45.869초/보호124.153초 및 패배·회복까지 통과했으나 본부조끼구매의count==1 대기에서FAIL했다. 소유실패DB read-only조회에서 vest1inventory와B-1번호1, 정상ON광원1800초가저장된것을확인해 구매거절/Unique/광원부족을원인으로단정하지않는다. 앞선boots실패DB도실제boots1/번호1이저장돼있었다. 전체Full반복을잠시멈추고실패summary에공개Inventory id/UUID/count/equipped와최근공개오류3개만보강해실제Client관측과DB효과를분리진단한다. 비밀번호/인증프레임/전체대화로그는수집하지않는다. R29-C08은계속FAIL이며단순timeout증가/조회명령추가로기대값을우회하지않는다.


작은 본부재현(`full-7hvu0kyl`)에서는 광원삽입/점등후조끼구매가 UI0→1 및297→227로정상반영됐다. 뒤의 장비검사는 해당작은Fixture가 아직구매하지않은 cutting_machete를 전제로해중단됐으므로 전체성공으로기록하지않는다. 원래Full의조끼timeout은미재현이며, 새Full은실행흐름을변경하지않고보강된실패summary로관측한다.


추가진단Full(`full-3m5wl72n`)은 실제31.073/46.001/121.162초를통과했으나 더이른마체테구매count대기에서FAIL했다. 실패당시공개Client Inventory는cutting_machete0/credits351/공개오류0인반면 종료후소유DB에는실제cutting_machete1이저장돼있었다. 세가지다른구매위치에서관측돼잘못된장비이름/Unique라고원인확정하지않고상태전송과실제처리지연을구분한다. Scout에해당단일경로만읽기전용조사를배정했으며추측에따른timeout증가나강제조회fallback은하지않는다.


번호reset·다른UUID·동일scope_id를명시한최종Chromium은 **12개시나리오전부PASS /142.759초 /run-mn8rxoxn /Chromium156.0.8078.4**다. 소유서버/브라우저종료·credentials제거를확인했고R10-C03을새근거로PASS/REUSABLE로갱신했다. Run별격리DB이며테스트별새Browser Context/Session을사용한다(테스트마다새DB라고주장하지않음).


관측용Full(`full-7spad_pf`)은원래10초한도를유지했다. 조끼구매직전rev207/칩285/수량0에서10.011299초에predicatefalse로실패했고,10.073435초에rev208/209/210 상태가연속도착해칩215/조끼UUID1·수량1을정확히반영했다. 추가관측후에도원래TimeoutError를다시발생시켜**exit1/FAIL**을유지했고GatePASS로채택하지않는다. 정제타임라인은ignored work/issue67/client-timeout-full-7spad_pf.json에있다. 이실행에서는상태소실이아닌클라이언트deadline초과를확인했으며서버처리/전송중어느부분인지는분리하지않았다. 기존구매전부를같은원인으로소급확정하지않는다. 기본/Quick/실제시간허용오차를유지한Full명령statewait의분리안을실측근거로독립검토하고새표준Full전체실행으로검증한다. 관측Wrapper의첫cp949출력실패는DB/서버준비전UnicodeEncodeError였고표준dev와같은-X utf8로수정한진단만위근거다.


Full 공개 명령의 수신 예산을 15초로 분리한 코드는 `03a2b0d2ecb45da3084874d9f84e7e9b2286ce1c`에 고정했다. 기본·Quick은10초, 명시 timeout(0포함)이 우선이며 Typed Action/Prompt/실제30·45·120초의 허용 상한은 그대로다. 재전송·강제조회·결과 완화는 없다. 순수 경계 회귀3개 PASS(0.012초), 코드 검사 PASS, 지정 Diff 독립 Reviewer A/잔여0이다. 이는 처리 지연의 원인 해결이나 성능 개선 주장이 아니며 새 표준 Full 전체 결과를 별도로 확인한다.

### 표시 계산 보완 전 로컬 결과 — Draft / HOLD

이 표는 표시 계산 보완 전 상태다. 현재 상태는 이 절 끝의 후속 결과와 CSV를 따른다. 위 진행형 문장은 당시의 이력이며 후속 성공으로 과거 실패를 삭제하지 않는다. 당시 검증 코드 스냅샷은 `03a2b0d2ecb45da3084874d9f84e7e9b2286ce1c`이며 이후 두 증거 문서만 통합한다. 최종 PR Source HEAD 및 원격 CI의 정확한 URL·결과는 PR Validation에서 별도 확인한다.

| Task | Case | PASS | FAIL | BLOCKED | NOT RUN |
| --- | ---: | ---: | ---: | ---: | ---: |
| T01 Action/Parser/Target | 38 | 38 | 0 | 0 | 0 |
| T02 번호/원자성/재시작 | 27 | 27 | 0 | 0 | 0 |
| T03 Multiplayer/경제/Timing/Full | 20 | 19 | 1 | 0 | 0 |
| T04 Gateway/Session/Lifecycle | 10 | 10 | 0 | 0 | 0 |
| T05 Chromium/실제 IME | 4 | 3 | 0 | 1 | 0 |
| T06 선언형 확장성 | 5 | 5 | 0 | 0 | 0 |
| T07 Legacy/Help/Docs | 2 | 2 | 0 | 0 | 0 |
| Stage 2 합계 | 106 | 104 | 1 | 1 | 0 |
| T08 Stage 3 소유 | 4 | 0 | 0 | 0 | 4 |

38규범 행은 **35 PASS / R29 FAIL / R30·R38 NOT RUN**이다. 전체110 Case의 재사용 분류는 **REUSABLE106 / PARTIAL1 / CANDIDATE0 / GAP3**이다. 기존 증거 채택77 Case와 이번 새 근거27 PASS를 구분하며, T08의 REUSABLE2개도 Status는 NOT RUN이다. Case 수는 독립 테스트 실행 횟수가 아니다.

최종 표준 Full `full-zsrw7m0k`는 실제 시체31.023초·리스폰45.912초·보호123.906초, 본부 서비스, 실제 구매·장비, 1차 보스 및 윤대장 보고까지 통과했다. 그러나 후속 `정글장도 사`의 수량 predicate가 Full 전용15초 안에 확인되지 않아 **전체 FAIL(exit1)**했다. 종료 후 해당 소유 DB를 read-only로 열어 `jungle_longblade`의 새 UUID·수량1·inventory 저장만 좁게 확인했다. 클라이언트 관측에는 해당 Item이 없었다. 원인·처리시간을 분리 확정하지 못했고 15초의 충분성을 주장하지 않는다. 대기 예산을 재증가하거나 성공으로 처리하지 않는다. 최종 재시작 구간은 미도달이며, 별도 성공한 강화 E2E-12로 Full 전체를 대체하지 않는다. 소유 프로세스 정리와 테스트 DB 전후 fingerprint를 확인했고 실패 DB/로그는 보존했다.

추가 실행 비용은 측정된 값만 기록한다. 신규게임 method15개는 초기14개 PASS(본문13.206초)와 가시성1개 PASS(14.147초), 기존 Item method 보강 재검사1개 PASS(3.309초)다. 실행기 integration13 PASS(4.761초), ownership5 PASS(0.012초), browser24실행/23 PASS·기존 Windows POSIX전용SKIP1(5.165초), 기존 Smoke계약18 PASS(1.550초)+새예산3 PASS(0.012초)를 구분한다. 강화 E2E-12 206.500초, 실제 Timing 두개963.491초, 최종 Chromium12개142.759초, Quick148.724초는 각 실행기 실측이다. Action E2E의 최종 전체 PASS는 exit0으로 확인했으나 전체 시간을 계측하지 않아 적지 않는다. 실패 실행의 미측정 총시간이나 원격 CI 소요시간을 추정하지 않는다.

독립 Reviewer `reviewer_celadon`의 실제 코드 Diff 검토는 A/잔여 P0·P1·P2=0/0/0이며, Full/IME의 필수 증거 미완료를 해결됐다고 판단한 것은 아니다. 소유 자원·정상 종료·backup/restore에 대한 `auditor_linden`의 정적 감사 A와 root의 실제 실행 증거를 구분한다. Implementer의 할당 파일 구현·직접 검사와 Reviewer의 읽기 전용 검토를 구분했고 파일 소유권을 반환받았다. Agent 결과 Done은 확인했으나 전용 Close 기능이 없어 스레드 Close·슬롯 해제를 보장하지 않는다. 설정의 모델/Effort와 실제 런타임 적용도 구분하며 강제 OS 격리를 주장하지 않는다.

**이 중간 시점의 판정은 C — Hold**다. R29-C08의 표준 Full 전체 성공과 R29-C03의 실제 Windows/Chrome IME 수동 증거가 없으므로 Stage 2 완료·Merge Ready로 제출하지 않는다. 단일 PR을 Draft/HOLD로 만들고 최신 Source HEAD의 필수 CI 네 Job을 별도 확인한다. CI가 성공해도 이 두 공백을 덮지 않는다. Full 지연 진단·영향 검사/전체 재검증과 §4의 실제 OS IME 절차가 병합 전 필요하다. Stage 3 T08/38행 전수 최종 감사·사용자 Merge 승인·병합 후 main CI·Issue Closeout은 미착수로 남긴다. 운영 DB 접근·Migration·Seed·복원, Release dispatch, PR Merge·브랜치 삭제·Issue 변경은 수행하지 않았다.

최종 문서 후속 확인에서 Reviewer는 38/110·104 PASS/1 FAIL/1 BLOCKED/4 NOT RUN, 분류106/1/0/3, 채택77+새근거27, 행35/1/2가 실제 CSV와 일치함을 독립 확인했다. 실행 당시6644+명시 Diff와03a2의 동일 spec 대응, 정제 메타데이터의 root 원본 열람 provenance, 최신 Full FAIL/최종 재시작 미도달 및 IME/HOLD 보존을 확인했다. 새 문서·코드 P0/P1/P2 지적은0이며 코드 A와 Stage2 필수 증거 미완료 C를 구분한다. Reviewer의 원본 Artifact 직접 열람 범위를 과장하지 않는다.

### PR CI 1차 취소 및 제한적 재현

PR #75의 Source `48beea9c3791e5c0a7012169d63c675f8e409f68`에 대한 [CI 39689479142](https://github.com/wonmin82/primal-zone/actions/runs/39689479142)는 contracts/smoke/browser-e2e SUCCESS, test는20분 Job 제한으로 CANCELLED다. 규칙235개는1.296초 PASS, 통합1078개를 발견했으나 완료 결과가 없어 통합 PASS로 기록하지 않는다. 전체 CI4/4도 아직 충족하지 못했다. 병렬 worker가 subsuite 전체 결과를 모아 전송하는 구조라 마지막 Door 로그/도트로 정지 test를 특정할 수 없다. 이전 main의1063개1113.645초 성공은 참고 근거이며 새 CI 성공으로 대체하지 않는다.

같은 신규15개를 `scripts/dev.py test tests.test_phase3_regression tests.test_phase3_extension --parallel 2`로 분리해 **15 PASS /본문21.496초·전체33.991초**를 확인했다. Windows spawn 조건의 성공이며 Ubuntu fork의 전체1078개 무정지를 증명하지 않는다. 실제20분취소와 이전18.56분 통합 검사의 제한된 여유를 근거로 CI test Job에만 유한25분 예산과 opt-in worker별 test ID·시작/종료 시각 관측을 적용한다. 테스트·Assertion·병렬수·게임시간·Full 응답 예산은 바꾸지 않으며 25분 내에도 완료되지 않으면 실제 active test를 바탕으로 진단한다. 시간 부족이 원인이라고 미리 확정하지 않는다.

GitHub Check Run annotation도 `The job has exceeded the maximum execution time of 20m0s`를 명시해 1차 취소의 직접 사유를 확인했다. 진행 관측 변경은 기본off/켜짐·buffer false/true·정상/실패/오류 이벤트·flush·부모 예외 전파의 순수8검사와 코드 검사 PASS다. Reviewer의 좁은 정적 검토 A/지적0이며, 25분 예산은 hang 해결이나 완료 보장이 아니므로 새 HEAD의 실제 전체 CI 결과가 필요하다.
추가 순수 pickle 왕복도 기본 RemoteTestResult와 비교해 기본off/on 각각 정상·실패·오류 이벤트/테스트수/성공·중단 상태를 보존함을 확인했다. stdout/stderr 제외 규약은 그대로이고 새 직렬화 상태는 None/float 시각만 포함한다. 기존8검사는 반복하지 않았다.


### 표시 계산의 반복 조회 보완 — 고정 코드 0e9b87c

소유 실패 Full DB의 원본 hash를 보존하며 별도의 새 소유 DB에 복제하고 테스트 계정 인증만 새 소유 자격으로 바꿔 관측했다. 자원·권한·진행은 추가하지 않았으며 이 진단을 Full 또는 Gate PASS로 채택하지 않는다. `full-l1un7azt`의 공개 정글장도 재구매는 수량1→2·174→64칩을 정확히 반영했고 응답6.721초/명령6.657초, 호출자 push_state 두번3.003/3.051초를 관측했다. cProfile 별도 복제 `full-6_fcaqch`는 측정 오버헤드 포함 상태 한 번6.5초, action_controls6.26초, NPC render47회, profile_snapshot243회, SQL4006회를 기록했다. 모든 과거15초 실패의 원인을 이 값만으로 확정하지 않는다.

`0e9b87cf2d27f3a418af9fb1261e0b763982156c`는 한 action_controls 호출의 ContextVar 범위 안에서만 동일 Actor의 관찰 프로필을 재사용하고 반환마다 깊은 사본을 만든다. 동일 Provider 객체·고정 non-None 시각의 available만 재사용하며, 다른 Actor·다음 요청·중첩·예외·직접 Presenter·None 시각은 격리한다. Binding별 access(view/call), Scope·Role·UUID·정규번호, 실제 Gateway/Domain 재검증과 잠금·커밋·지급·게임 타이머는 변경하지 않았다. 제어 Row/권한 결과를 프로세스 전체에 저장하지 않는다.

신규6개 경계 method는 최초5개 전체 PASS(본문12.187/전체21.235초) 및 직접 Presenter·채워진 캐시 예외 복원 보강2개 후속 PASS(전체19.060초)로 검증했다. 첫5ERROR는 직접 deepcopy import가 동기 검사기의 표준 라이브러리 참조 탐색 한도에 걸린 문제이며, 검사기 정책을 바꾸지 않고 동기 copy.deepcopy 모듈 경유로 수정했다. 다음1FAIL은 available 내부 view 조회 감소와 Binding별 접근 횟수를 합산한 테스트 기대 오류로, Binding별 call 불변 비교로 구분했다. 이 정정은 실제 권한 루프를 완화하지 않으며 Auditor와 Reviewer가 독립 확인했다.

후속 기존 `test_action_cutover/test_action_runtime/test_web_state/test_npc_dialogue/test_phase3_extension`는92 PASS(본문279.209/전체288.758초)다. 캐시 없는 동일 관측 기준과 Typed control Row가 같고 실제 DB·SelectionNumber·Counter가 변하지 않음을 신규 native fixture에서 확인했다. 기존 채택77개 중34 Case의 인용 모듈이 이92개에 포함돼 해당 Assertion을 새 코드로 재확인했다. 77은 최초 채택 수이며 이후 영향 재검증과 상호 배타적인 실행 수가 아니다. 다른 인용 근거의 원래 SHA와 부분 검증 범위를 유지한다.

프로파일러 없는 후속 동일 소유 DB 복제 `full-u5fewm5x`는 같은 구매 수량/가격을 반영하며 응답4.098초, 명령4.032초, 호출자 상태 계산1.784/1.677초를 관측했다. 이는 단일 관측의 비용 감소이며 보편적 성능 보장·과거 실패 원인 전체 확정·Full 성공을 의미하지 않는다. 원본 hash와 소유 프로세스 종료를 확인했다. 최초 py_compile은 외부 PyCache 쓰기 권한 때문에 실패했으므로 통과로 기록하지 않으며, 파일 쓰기 없는 compile과 실제 진단 실행을 별도로 확인했다.

보완 HEAD의 Chromium은12/12 PASS(143.589초, run-sjl1mnfe)다. 소유 서버·브라우저 종료/자격 제거를 확인했고, 마스킹된1280×900/390×844 스크린샷을 직접 확인해 가로 overflow 없는 배치와 조작 표시를 확인했다. 자동화/이미지 확인은 실제 OS IME 증거가 아니다.

독립 `auditor_rosequartz`는 지정4파일 해시가 같은 상태에서 Actor/시간/수명·정보 격리·readonly·실행 재검증/원자성을 소스로 확인해 A/지적0으로 판정했다. 테스트/서버/DB는 실행하지 않았다. Reviewer의 지정 Diff 일반 정확성·Typed control/Help/API/검증 기준 확인도 정적 A/지적0이며 실제 성능/Full을 새로 실행한 것으로 표현하지 않는다. 기존 Linux1078 CI 성공은 표시 보완 전 d96ebd8 기준이므로 후속 최종 HEAD CI와 구별한다.

표준 Full `full-0935ya4g`는 실제30/45/120초 경계(34.986/46.199/124.642초), 본부 서비스·두 임무·두 보스, 정상 shutdown의 광원 정산과 동일 DB startup/relogin의 Item UUID·수량·트리 보존을 통과한 뒤 마지막 Loot façade 딕셔너리 비교에서 실패했다(exit1). 전후 Loot snapshot이 저장되지 않아 실제로 달라진 필드는 미확정이며 정상 Claim 만료 또는 데이터 소실로 단정하지 않는다. 소유 프로세스 종료와 격리 DB fingerprint를 확인했고 실패 자료를 보존했다. 전체 성공 전 R29-C08은 FAIL로 유지한다. 실제 IME BLOCKED와 T08의4 NOT RUN도 유지한다. 표시 보완을 이유로 기존 실제 Door60/Party600/강화 E2E12를 무조건 반복하지 않는다. 해당 Domain·타이머·영속 상태와 Harness는 그대로이며, 변경된 표시는 위 직접 회귀와 브라우저·표준 Full/최종 CI에서 다시 확인한다.


### Full 최종 보존검사 보강 — 고정 코드 21fdf04

`21fdf0401f29c693fe0c12ede71821a0ab624c74`는 표시용 entry dict 대신 Native Item UUID/수량/sequence/state/tree, LootClaim 행 ID·권리, CurrencyLoot ID·금액·0 지분 Share를 비교한다. 실제 `decay_source`의 entry별 신규 Ground Source 분리와 같은 Room을 검증하며, 기존 Source 재사용·서로 다른 entry의 합류·실물/지분 손실·미만료 Claim 삭제·새 보호 부여를 거절한다. 기존 Item Claim이 관측 완료 시각까지 만료한 경우 삭제만 허용한다. 게임 Domain·Lock·지급·타이머 정책은 바꾸지 않았다.

Reviewer가 지적한 혼합 시점 snapshot과 Source 전환 검사의 P2 두 건을 반영했다. 소유 SQLite의 전체 eager projection을 단일 `BEGIN DEFERRED` 읽기로 묶고 항상 rollback해 공통 IMMEDIATE 설정을 변경하지 않는다. before/stopped/after/final JSON은 marker·DB 경로를 검증한 소유 실행 경로에 배타 저장한다. 현재 Harness 구조상 startup 자체가 실패하면 stopped 파일 저장 전일 수 있다. 순수 신규10개 검사와 Ruff·`scripts/dev.py check` PASS, 독립 Reviewer의 좁은 재검토 A/잔여0이다. 중간 루트 순수29개 성공과 이후10개 보완 검사를 같은 시점의31개 전체 실행으로 합산하지 않는다. 최초 루트 unittest discovery는 game import 경로 오류로2ERROR 후 올바른 경로의29개로 정정했다.

실제 집중 Fixture `full-1xb0mee4`는 정상 Portal/Server 종료·같은 DB 재시작·재인증과 실제120초 보호 만료(관측126.530초)를 확인했다. ItemUUID2개/CurrencyID1개/0지분을 보존하고 Item Claim2개 만료 삭제를 확인했다. 옛 entry dict 비교 실패도 재현됐으며 실제 차이는 assigned_player/protection_until/reserved_player였다. 총157.625초 PASS, 소유 프로세스 종료·테스트 DB 전후 fingerprint를 확인하고4단계 JSON을 보존했다. 이는 별도의 합성 격리 Fixture 결과이며 이전 Full의 미저장 전후 필드나 Full 전체 성공을 증명하지 않는다. 최초 집중 실행 `full-4tqkcmyk`는 서버 startup 전 lifecycle script 미생성 상태의 snapshot 호출 오류로36.145초 FAIL했고 서버 실행/DB 변경 없이 정리했다. 관측을 서버 ready 뒤로 옮겨 재실행했으며 Domain 수정은 없다.

고정 코드21fdf04의 표준 Full 전체를 새 소유 격리 실행으로 검증했으며 결과는 아래 후속 기록과 같다. 집중 Fixture PASS만으로 R29-C08을 변경하지 않으며 최종 전체 결과와 정상 정리 확인 후 갱신한다. 실제 OS IME는 BLOCKED이고 T08의4개 Case는 NOT RUN이다.


표준 Full `full-wy4onm34`(21fdf04)는30/45/120초를31.021/45.859/122.934초로 통과했고 본부·패배/회복·실제Lv4/HP126 장비 준비까지 통과했으나 첫 보스전에서 패배해 종료했다. 재시작 보존 검사에 미도달해 전체FAIL을 유지한다. 소유 프로세스 종료·DB fingerprint 확인·진단 보존을 완료했다. 게임 수치·Fixture 자원을 바꾸지 않고 공개 전투의 자동 클라이언트 전략을 소스에서 조사한다.


### Full 전투 클라이언트의 응답·소비 경계 보완 — 2026-10-23

`scout_kestrelwood`는 공개 전투 명령이 다음2.5초 Player 기회를 대체하는 단일 큐를 사용하지만 기존 `Client.act()`는 임의 새 상태만 기다려 명령 수락·소비와 구분하지 못함을 소스에서 확인했다. 실제 실패 run에서 이 경합이 패배의 단독 원인이었다고 확정하지 않는다. 예고보다 강타를 우선하는 기존 전략은 그대로 두며, 새로운 자원·밸런스·치료 전략·타이머·대기 예산을 추가하지 않는다.

`implementer_larchsong`은 Full에서만 명령 전의 응답 경계, 명시 성공 ack와 이후 queue→attack 및 Player round 증가를 구분하고 미소비 큐 덮어쓰기·재전송·대상 교체·패배·오류를 거절하도록 보완했다. ack 시점에 이미 소비된 경우 한 번의 자연 라운드를 더 기다릴 수 있으며 이를 정확한 서버 명령 토큰 보장이라고 확대하지 않는다. 전투 종료는 별도 진단이며 기존 kill의 XP 증가·의무실 패배 아님 assertion을 유지한다. 회복실 도착 때 자연회복으로 이미 HP·정신력이 최대이면 불필요한 침대 요청만 생략하며, 부족하면 기존 실제 회복을 그대로 검증한다.

최초 복제 진단 `full-5ayslo2j`는 이미 자원이 가득한 침대의 정상 거절 후 상태 대기로128.387초 FAIL했다. 다음 `full-6rhej_1s`는 붕대의 실제 일반 text 응답을 semantic pz_log만 기다리는 초기 helper가 놓쳐142.781초 FAIL했다. 실제 로그에서 round47/HP66/붕대8개 전송 후 round52/7개로 소모됐으나 ack를 못 봤음을 확인했다. 이 P1은 독립 Reviewer `reviewer_sagewing`도 코드로 확인했다. 두 진단 모두 소유 복제의 공개 구매·회복만 사용했고 원본 hash 불변·소유 프로세스 종료와 실패 자료 보존을 확인했다. 원래 Full 패배와 새 helper의 채널 결함을 구분한다.

붕대 text와 강타·견제 pz_log가 모두 적재되는 실제 Client messages에서 새 성공 ack를 확인하고, 새 구조화 오류는 별도로 거절하도록 고쳤다. 기존 응답은 전송 전에 분리하고 수신 Condition으로 놓친 wake를 방지한다. 공통 Client와 서버 프로토콜은 변경하지 않는다. 실제 `Client.receive()`를 raw text/pz_log/pz_state로 구동한 프로토콜 회귀를 포함해 순수36개 PASS(1.598초), Ruff·diff check PASS다. 중간35개 성공과 P1 미수정 상태를 최종 성공으로 덮지 않는다. 새 실제 보스전 집중 재현과 표준 Full 전체 결과는 별도 기록한다.


위 전투 helper의 고정 코드는 `93724ec64a9840f5085c68bcbbf3c667ddb85237`이다. 독립 `reviewer_sagewing`이 같은 두 파일의 blob hash를 확인해 P1 해결·코드 A/잔여0으로 판정했다. 읽기 전용 리뷰이며36개 검사와 실제 전투를 직접 실행한 결과는 아니다. 소비 상태 뒤에 오류 로그가 별도 패킷으로 늦게 도착하는 경계는 직접 검증하지 않았고, 현재 단독 Full Fixture에서 수락 후 자원이 외부 변경되는 구체 조건도 확인하지 못했다. 이를 범용 명령 완료 토큰이나 모든 네트워크 순서의 보장으로 확대하지 않는다.


수정된 helper의 집중 복제 `full-a2cj74qg`는 공개 준비(실제 붕대8개 구매·기존T1 장비·Lv4/HP126) 뒤 첫 보스 실제 승리로 끝났다. HP27·XP421을 관측했고164.290초에 종료·원본 hash 불변·소유 프로세스 종료를 확인했다. 실행 당시93724ec와 동일한 두 파일 Diff를 사용했다. client.log에서 붕대의 실제 예약→20HP 회복/수량차감, 강타의 예약→정신력8 소모/피해 반영을 확인했다. 전투 기회·재고·타이머를 늘리지 않았다. 이 한 번의 집중 승리는 기존 Full 패배 원인 전체 확정이나 표준 Full PASS를 대신하지 않는다. 고정93724ec에서 새 표준 Full을 실행해 전체 결과를 별도로 확인한다.


표준 Full `full-ztl8ybql`(93724ec)은33.530/46.399/121.355초의 실제30/45/120초, 본부·성장 준비까지 통과했으나 첫 보스전 패배로 전체FAIL이다. 이번에는 로그에서 모든 성공 ack·붕대8개 차감과20HP 회복·강타 비용/피해가 소비 경계에 반영됐음을 확인했다. 마지막 붕대 소진 뒤 HP45/적HP34·정신력31 상태에서 사망했고 재시작 구간은 미도달이다. 원본 전후 차이가 없었던 과거 Full과 달리 이번 단계의 전투 관측은 실제 저장된 로그에 근거한다. 소유 프로세스 종료·격리 DB fingerprint 및 실패 자료를 보존했다. 동일 설정을 성공할 때까지 재실행하지 않는다.

새 최종 통합 `reviewer_willowfinch`는93724ec+당시 문서2개의 Diff·관련 Assertion·정제 근거를 독립 확인해 코드 A/신규P0·P1·P2=0/0/0, 현재 Stage2 C—Hold로 판정했다. 38/110·104PASS/1FAIL/1BLOCKED/4NOTRUN 및분류106/1/0/3, 기존채택77/표시영향재확인34의 구분이 일치함을 확인했다. 실행·원본DB/Artifact·CI를 직접 확인한 것으로 확대하지 않는다. 첫 보스 준비 단계의 후속 변경은93724ec 밖의 별도 Delta로 검토한다.

첫 보스도 기존 두 번째 보스 준비와 같이 실제 공개 사냥으로 한 단계 더 성장한 뒤 도전하는 제한적 보완을 계획한다. 기존 profile XP/자원·권한을 쓰거나 미리 지급하지 않고 최대3회의 고정 공개 사냥으로 실제 XP 증가를 확인한다. 기존 game 규칙의Lv5 임계360XP와 현재291XP를 비교해 갈퀴사냥룡38+청소룡22+청소룡22의 기존 보상 경로를 사용하며, 이미충분하면 불필요 사냥을 하지 않는다. 이 보완도 실제 사냥·상점·성장·전투·임무의 도메인 효과를 그대로 검증하고 생존/XP assertion·타이머/timeout을 유지해야 한다. 구현·실행이 완료됐다고 미리 표시하지 않는다.


공개 사냥 준비 보완의 고정 코드는 `5ab989db5f79117ac3fd69dc919e343f02977320`이다. `implementer_pineglade`가 지정2파일만 수정했고 최대3회의 실제 사냥·회수, 목표 즉시중단·무부작용·대상 부재/생존/XP/유한 실패 경계를 보강했다. 순수39개 PASS, Ruff·diff check PASS다. `reviewer_willowfinch`는 실제 보상38+22+22와360XP 임계, 기존 kill·구매·성장·회복·보스 승리 조건 유지 및 사전 지급0을 확인해 좁은 Delta A/신규지적0으로 판정했다. Lv4 난이도 benchmark가 이번 규범 수용 조건이 아닌 통합 검증 목적에서 실제 사냥 준비는 성공 조건 완화가 아니며, 실제 실행은 별도 근거가 필요함을 명시했다.

집중 복제 `full-90ogghd4`는 공개 사냥으로 XP291→329→351→373/Lv5를 실제 관측했다. 실제 성장 배분·침대 회복 뒤 HP144로 준비하고 보스전 승리 HP85·XP503을 확인했다. 총233.248초, 원본 hash 불변·소유 프로세스 종료·진단 보존을 확인했다. 실행 당시 두 파일은5ab989d와 동일하다. 준비 전 자원·XP를 미리 지급하지 않았고 예산/타이머도 변경하지 않았다. 이 집중 승리는 표준 Full을 대신하지 않는다. 고정5ab989d에서 새 표준 Full 전체와 콘솔 증거를 별도 소유 작업 경로에 기록한다.


### Stage 2 최신 로컬 결과 및 제출 경계 — 고정 실행 코드5ab989d

표준 `scripts/dev.py smoke-full`의 `full-9pigsbrh`가 **exit0 / PASS1297.484초**로 완료됐다. 별도 콘솔 `work/issue67/full-5ab989d-console.log`에 원 실행 출력을 보존했으며 Source는5ab989d다. 실제30/45/120초는31.058/45.868/120.922초, 실제 공개XP291→329→351→373/Lv5, T1 HP144/T2최종Lv7 HP184, 두 보스·최종보고·추가훈련을 통과했다. 정상 AMP shutdown은 광원ON/active UUID를OFF/None으로 정산했고 잔량1800→874.566은project_power 범위 안이다. 정상 startup/relogin은Item UUID·quantity·sequence·tree/state·주무기를 엄격 보존했다. 기존NativeItem1/Currency2를 보존했고 이번 Full의 만료Claim삭제는0건이다. 별도 집중 실시간 만료Claim삭제2건과 합쳐 같은 실행처럼 표현하지 않는다. 프로필·party·world/시설·시계 및 전투/권리 정합화와 process stop/temp cleanup까지 통과했으며 실행 경로가 실제로 없음을 후속 확인했다. 성공 Run의 임시4단계JSON은 정상정리로 삭제됐고, 원콘솔/소유DB 전후fingerprint·정제 metadata는 보존했다. 원본 DB를 보관한 실패/집중 Run과 구분한다.

| Task | Case | PASS | FAIL | BLOCKED/NOT RUN |
| --- | ---: | ---: | ---: | ---: |
| T01 | 38 | 38 | 0 | 0 |
| T02 | 27 | 27 | 0 | 0 |
| T03 | 20 | 20 | 0 | 0 |
| T04 | 10 | 10 | 0 | 0 |
| T05 | 4 | 3 | 0 | 1 BLOCKED |
| T06 | 5 | 5 | 0 | 0 |
| T07 | 2 | 2 | 0 | 0 |
| Stage2 합계 | 106 | 105 | 0 | 1 BLOCKED |
| T08(Stage3) | 4 | 0 | 0 | 4 NOT RUN |

38개 규범 행·110개 Case ID/요구/Task 관계를 유지했다. 현재 전체105 PASS/1 BLOCKED/4 NOT RUN이며 행35 PASS/1 BLOCKED(R29)/2 NOT RUN(R30,R38)이다. 분류는107 REUSABLE/0 PARTIAL/0 CANDIDATE/3 GAP이다. 직전106/1/0/3에서 R29-C08만 표준Full 전체 성공으로 PARTIAL→REUSABLE/FAIL→PASS로 변경했다. 최초기존채택77개 중34개는표시영향92검사로재확인했으며, 새 근거의PASS Case는28개다. 이Case집계는물리적실행수나테스트method수와다르다.

최종 코드의 `scripts/dev.py check`와 문서 `git diff --check`를 확인한다. Smoke 순수 검사는공개사냥의3개추가method를포함39 PASS이며, 중간36개1.598초와39개의실행시간을같은값으로표현하지않는다. 최종 Full1297.484초와각집중실행157.625/164.290/233.248초는각실측이며미측정실패Run의총시간을추정해합산하지않는다. 동일Domain의실제Door60/Party600/강화E2E12는유효기존근거를재사용해대기를반복하지않았다. 제품표시변경은92개영향회귀/6개경계검사/최신Chromium12개와Full에서재확인했다.

**IME Case P3-R29-C03은 BLOCKED**다. 실제 Windows/Chrome OS 입력기를 이용한 수동증거가 없고 Native 컴퓨터 입력이 제공되지 않으므로 DOM/composition 자동화나이미지로대체하지않는다. §4 수동절차를수행해실제환경·SHA·입력·1회실행/정확한대상·서버결과를기록해야한다. T08 4개Case·38행전수FinalGate·사용자Merge승인·병합후mainCI·IssueCloseout은Stage3 미착수다. Stage2의자동로컬근거완료를Phase3완료나Merge승인으로확대하지않는다.

최종 Source HEAD와필수CI(test/smoke/contracts/browser-e2e)의정확한Run URL·결과는 [PR #75 Validation](https://github.com/wonmin82/primal-zone/pull/75)에서Source별관리한다. d96ebd8의 [CI39716657961](https://github.com/wonmin82/primal-zone/actions/runs/39716657961) 규칙235/통합1078·4/4 SUCCESS는표시/Full보완전근거이며최종HEAD를대신하지않는다. 코드5ab989d 뒤에는증거문서만변경하고한번에Push해최신CI를확인한다. IME미완료이므로PR은Draft/HOLD로유지하며, 최종SourceCI까지성공하면제출판정은 **B — Conditional(IME 해결 전Merge 불가)**다. SourceCI가실패하거나미확인이면C/Hold로기록한다. 운영DB 접근·Migration·Seed·복원, Release dispatch, Merge·브랜치삭제·Issue변경은수행하지않았다.
