# Issue #50 Cross-Issue E2E 검증

## 2026-10-12 최초 성공 RELEASE 및 최종 Closeout 준비

[PR #60](https://github.com/wonmin82/primal-zone/pull/60)은 Merge Commit `855ada380e5276334f0744797a86a5aef300297c`으로 병합됐다. 첫 부모는 `82641de0ea66898676b0b29194d7918489443def`, 둘째 부모는 검토 Source `26da18221f890f3405aca84b746741e3da7f747b`이며 임시 병합 결과와 Tree가 같고 원본 이력이 보존됐다. [당시 main CI](https://github.com/wonmin82/primal-zone/actions/runs/38239786496)의 네 Job은 모두 SUCCESS다.

[최초 RELEASE 실패](https://github.com/wonmin82/primal-zone/actions/runs/38241057595)는 삭제하지 않는다. 8개 중 7개 Job은 SUCCESS였지만 Full Smoke가 60초 후 정상 닫힌 회복실 문을 열지 않고 이동해 실패했다. 이는 QA 이동 경로의 누락이며 게임의 차단은 정상이다. [최소 수정 PR #61](https://github.com/wonmin82/primal-zone/pull/61)의 `0a03b44612822796f703e4d077916330e909a4fb`는 실제 `회복실 문 열어`를 양쪽 이동 전에 실행한다. 정상·실패·비관련 출구 회귀3개를 추가했으며 게임 정책·타이머·프로토콜·저장 형식은 바꾸지 않았다. 수정 Merge는 `11a1c6bce91a5499292f8fbabff3e308663814fe`이고 부모는 `855ada380e5276334f0744797a86a5aef300297c`와 `0a03b44612822796f703e4d077916330e909a4fb`다.

**최초 성공 RELEASE SHA: `11a1c6bce91a5499292f8fbabff3e308663814fe`.** [main CI](https://github.com/wonmin82/primal-zone/actions/runs/38244636657) 네 Job SUCCESS, [RELEASE](https://github.com/wonmin82/primal-zone/actions/runs/38251167392) 8개 Job SUCCESS, main/workflow_dispatch/attempt1 및 입력·GITHUB_SHA·실제 Checkout SHA 일치를 모든 Job의 Guard8개로 확인했다. RELEASE 전체 병렬 경과는 819초다. Job 로그·Assertion 및 안전한 Artifact를 직접 검토했다. 아래 최초 실패/성공과 과거 로컬 검증을 서로 다른 실행으로 보존한다.

**최종 SHA Closeout은 아직 대기 중이다.** 이 문서 PR을 Merge Commit으로 병합한 뒤 새 `FINAL_MAIN_SHA`의 push CI 네 Job과 RELEASE8개 Job을 다시 실행한다. 같은 SHA의 성공으로 대체하지 않는다. 최종 실행 증거는 [Issue #50 공식 Final Closeout 기록](https://github.com/wonmin82/primal-zone/issues/50#issuecomment-6124806608)에 추가하고, 결과 때문에 새 Git Commit을 만들어 SHA를 다시 바꾸지 않는다. 최종 Gate를 확인한 뒤에만 #50·#45를 종료하고 병합된 작업 브랜치를 안전하게 정리한다.

| Job | 실제 결과 | 경과 시간 | 실행 증거 |
| --- | --- | --- | --- |
| baseline | SUCCESS | 5초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817552240) |
| test | SUCCESS | 426초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597631) |
| timing-e2e | SUCCESS | 808초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597684) |
| contracts | SUCCESS | 13초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597752) |
| smoke | SUCCESS | 74초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597770) |
| persistence-e2e | SUCCESS | 132초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597853) |
| browser-e2e-full | SUCCESS | 718초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597895) |
| smoke-full | SUCCESS | 514초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597957) |

### 실제 시간과 정상 재시작

- TEST-TIMING-DOOR **PASS/100.737초**: 실제 열기/양방향OPEN·통과 완료 기준+60초·중복 열기/실패 통과 예약 불변·중간 관측·만료4초 전 이후 최대500ms 목표 반복·최종 `deadline-1.0 <= end <= deadline-0.5` 완료·만료후 실제 이동 거절·정상 Tick CLOSED·웹 양쪽 동기화. 단위 Clock 주입으로 대체하지 않았다.
- TEST-TIMING-PARTY **PASS/640.504초**: A 마지막 소유 Puppet 종료·실제 offline_since·B온라인·300초 부근/직전/최종 완료 창까지 A 유지·실제600초 이후 정상 Tick 승계·A재접속 권한 자동복원 없음·구성/전술/아이템/Claim 보존.
- 같은 RELEASE Helper의 Node 시간16개는30/58초 CLOSED·58초LOCKED·예약변경·300/598초승계·필수관측 누락/지연/조회오류를 실제로 거절한다. 조회 상한2초/최종 유효 창은 완화하지 않았고 누락 시FAIL이다. E2E11의599.999/600 서비스 주입과 실제 시간 검사를 별도로 기록한다.
- 독립 persistence 재검증 E2E12 **45.936초**, E2E13 **16.846초**: 실제 Exit 및 DoorInstallation·Profile/줄임말·Item UUID/장착/수량·Party·Quest/Credential·Native/Legacy/Claim·정상 만료와 데이터 손실 구분·상위 Rollback/알림 차단. 일반 Exit의 독립성도 비교한다.


| Chromium 테스트 | 결과 | 실제 테스트 시간 |
| --- | --- | --- |
| TEST-50A-01 | PASS | 3.119초 |
| TEST-50A-02 | PASS | 1.499초 |
| TEST-50A-03 | PASS | 3.803초 |
| TEST-50A-04 | PASS | 4.520초 |
| TEST-50A-05 | PASS | 2.799초 |
| TEST-50A-06 | PASS | 3.586초 |
| TEST-E2E-01 | PASS | 24.762초 |
| TEST-E2E-02 | PASS | 62.897초 |
| TEST-E2E-03 | PASS | 29.613초 |
| TEST-E2E-04 | PASS | 25.386초 |
| TEST-E2E-05 | PASS | 28.591초 |
| TEST-E2E-06 | PASS | 36.541초 |
| TEST-E2E-07 | PASS | 29.781초 |
| TEST-E2E-08 | PASS | 40.252초 |
| TEST-E2E-09 | PASS | 12.053초 |
| TEST-E2E-10 | PASS | 15.292초 |
| TEST-E2E-11 | PASS | 41.953초 |
| TEST-E2E-12 | PASS | 48.628초 |
| TEST-E2E-13 | PASS | 17.347초 |
| TEST-E2E-14 | PASS | 14.509초 |
| TEST-P2-02-A | PASS | 2.961초 |
| TEST-P2-02-D | PASS | 4.042초 |
| TEST-P2-03-D | PASS | 2.368초 |

### 안전성과 별도 검증 상태

시나리오/Job마다 새 marker·SQLite·동적 포트·합성 일반 계정·독립 Browser Context/실제 WS를 사용한다. 공개 증거의 run.json은 SHA·자격 증명 제거·Node/Chromium 및 Evennia 소유 프로세스 종료·플레이 DB 불변을 모두 true로 확인한다. observations의 모든 Context가 종료되고 소유 Puppet ID가 해제됐다. Artifact는 허용된 JSON/HTML·원문 비수집 로그 요약과 명시 마스킹 PNG2개만 포함하며 인증·개인 메시지·임의 입력·DB·원본 Snapshot·Trace/Video는 없다. 성공14일/실패30일 정책을 유지하고 실제 성공 Artifact의 만료 시각도 대조했다. 실패 원본 DB/로그는 운영 DB와 구분된 소유 로컬 경로에만 보존한다.

실제 플레이 DB의 SHA256은 `a33b102000a62dfe761fc8db5a90f1c4c4ffa012d9aec14a716c1d3784a592c3`이며 size/mtime/hash 불변이다. 운영 서버·운영 데이터 적용/마이그레이션은 수행하지 않았다. 신규 미해결 P0/P1은 없고 비차단 favicon P2는 [#59](https://github.com/wonmin82/primal-zone/issues/59)에서 OPEN 추적한다. #58은 변경하지 않았다. OS 한글 IME는 **PRIOR VERIFIED**, 최초 Visual Baseline은 **PENDING REVIEW**이며 객관적 DOM·접근성 PASS와 주관적 이미지 승인은 구분한다. Ubuntu는 실제 RELEASE, Windows는 보존된 실제 로컬 증거이며 macOS는 미지원/NOT RUN이다.


## 아래 기록의 시점

아래 기존 NOT RUN·PENDING·OPEN·Pre-merge 및 Phase 범위 표기는 해당 구현·리뷰 당시의 역사적 기록이다. 삭제하거나 새 SHA의 실행 결과로 재작성하지 않는다. 현재 결과와 최종 확인 절차는 위 기록 및 연결된 Final Closeout 기록을 따른다.

이 문서는 v1.2 D02/D05/D10/D12~D17의 실제 게임 경로를 추적한다. Phase 50-A 이력은 기존 브라우저 문서에 보존한다. 현재는 **Pre-merge 개발 검증**이며 RELEASE/main 완료 보고가 아니다.

## 실행과 격리

`npm run test:browser:integration`은 E2E-01~14를 각각 새 `Harness('full')` DB/서버/포트에서 실행한다. 하나의 시나리오만 조사하려면 `uv run python scripts/integration_e2e.py --scenario E2E-08`을 사용한다. Playwright Worker1/retries0, 실제 Chromium/일반 Account/독립 Context/WebSocket을 사용한다. 기존 가입 제한은 변경하지 않는다.

[`integration_setup.py`](../scripts/integration_setup.py)는 서버 시작 전 초기 조건만 준비한다. 신규 인증의 출정 대기실 이동 정책을 보존하고 [`integration-helpers.cjs`](../scripts/browser/integration-helpers.cjs)가 실제 Exit 명령으로 장소에 도착한다. [`integration_probe.py`](../scripts/integration_probe.py)는 Smoke marker·DB 경로 확인 뒤 SQLite `query_only`로 읽는다. Snapshot 원문은 Assertion 메모리에만 존재하며 Artifact에 포함하지 않는다.

## 시나리오와 Assertion

모든 실제 테스트는 [`integration.spec.cjs`](../scripts/browser/integration.spec.cjs)에 있다. `TEST-E2E-NN`이 동결 `E2E-NN`에 해당한다. 개별 실행의 안전한 `results.json`/`run.json`이 ID·SHA·시간·성공/실패 및 정리 근거다. 개발 중 실행 SHA는 Base/단계 커밋과 해당 미커밋 diff를 함께 해석한다. 최종 제출에서는 정확한 PR HEAD의 CI와 연결한다.

| ID | 초기 조건 | 실제 사용자 경로 | 확인하는 DB·출력·부작용 |
| --- | --- | --- | --- |
| E2E-01 | 일반 신규 계정, 출정 대기실 | `상`, 양쪽 Help suffix, 변수/묶음 줄임말 | 실제 점수·Help·변수 관찰, 저장 정의, Prompt/정확한 단일 전송 |
| E2E-02 | A: 과거 보스 처치·미수락, 수리 부품3. B: 완료 임무·분실 출입증 | NPC 화제 → 수락 Enter/보고 클릭, 정비기록·발전기 수리, 재발급 | started/record/generator/claimed, XP100·칩100 한 번, 실제 Native 출입증1·재발급 중복/보상 없음. 보스 전투 자체는 이 초기 조건의 기수행 전제이며 공동 전투는 E2E-06에서 실제 실행 |
| E2E-03 | 준비금·빈 손, 무기 상점 | 절단마체테 구매·정보·무장·해제·판매 | UUID 소지/장착/수량, 55칩 지출·27칩 매입, 정보 조회의 ItemEntity 불변 |
| E2E-04 | HP20 부족·SP1, 의료 서비스 | 유료20 회복 → 실제 Exit 이동 → 문 닫기/거절/열기 → 이동 버튼 → 침대 | 실제 HP/과금 산식·SP, 닫힌 문 이동 거절, 무료 휴식·칩 불변 |
| E2E-05 | 독립 A/B/C, 같은 방 | 개인 대화·차단·일행 초청/가입, B 다른 방에서 일행대화 | 정확한 B 수신, C 비수신, 차단 본문 부재, 실제 Party/원격 수신 |
| E2E-06 | A/B 실제 초지, 일반 맨손 | 일행 생성·영속 방어·공동 공격·실제 처치·회수·중복 요청 | 양쪽 XP 증가, 실제 Native 지급/Claim, 중복 칩·아이템 없음, 기존 전투 주기 |
| E2E-07 | 격리 historical audit DB: A Native/B Legacy, 확정 개인 권리·지분, 기존 Party | 두 단계 해체 → C 거절 → A Native/B Legacy 실제 회수 | Party 삭제 뒤 개인 수량/화폐 권리 유지·실제 지급·제삼자 불변·Claim 소진 |
| E2E-08 | 독립 A/B, 관리실 처음 LOCKED | 열쇠함 조사·해제·열기·양쪽 진입·동시 닫기·오래된 이동·재개방/통과 | 두 방향 SSOT/웹 can_move, 거절 위치 보존, 실제 Exit PK 및 완료 시각+60초 연장 |
| E2E-09 | 중앙 로비의 실제 Exit/LOCKED 문 | 개인 묶음으로 휴게실→로비→잠긴 동→점수 | 실행 직전 현재 CmdSet, 거절 후 위치/LOCKED 불변·다음 명령 정상 |
| E2E-10 | 중앙 로비의 문 및 합성 NPC/Doctor/기존 hunter 정의 적, 정상 방어 장비 | 실제 교전 → 관리실 문/NPC 수락/유료 회복 → 도망 | 실제 combat_target 유지 중 각 거절, Quest/칩/관리실 Door 불변. 합성 객체는 격리 초기 fixture이며 운영 콘텐츠/적 수치 변경 없음 |
| E2E-11 | 온라인 A 리더/B 멤버·영속 방어 | 마지막 A Puppet 종료 → 599.999/600 시각 인자 → 재접속·위임·즉시 승계 | 실제 세션 해제·599.999 승계 없음·600 첫 서비스 승계·리더 복원 없음·방어 보존. 실제 wall clock는 RELEASE 별도 |
| E2E-12 | Native/Legacy·UUID·Claim/화폐·개인 줄임말·Party·열쇠·실제 열린 문 | 모두 정상 detach → Portal/Server 정상 종료/같은 DB → 재인증 | Profile/Item UUID/장착/Quest/Legacy전리품·지분/Party·DoorInstallation/Exit PK 비교. 정상 만료 sweep과 재로그인 위치 정책을 데이터 손실로 오인하지 않음 |
| E2E-13 | 실제 Native/Legacy 지급 대상과 보호 권리 | 양쪽 실제 `가져` → 최상위 변경 실패 주입 | 원래 선택·권리·지급 성공 뒤 상위 rollback, items/Claim/화폐/Legacy/양쪽칩 불변, `챙겼다/회수했다` 성공 출력 없음 |
| E2E-14 | Desktop/Narrow 독립 순차 Context | 연속 명령·History·Backspace·실제 clipboard paste/Enter·HTML 입력·이동 | 단일 정확 전송·Prompt/Semantic Text·HTML 비실행·Focus·viewport/입력/버튼 hit-test·overflow/오류 없음. 소유 Puppet 해제 뒤 다음 viewport |

Historical audit의 Legacy source를 운영 Native cutover에 자동 편입하지 않는다. 기존 `settings_test` 방식과 같이 별도 새 QA DB에서만 legacy 감사 설정을 사용한다. Legacy 실물은 Legacy 수령인, Native 실물은 Native 수령인이 실제 회수하며 금지된 저장소 간 이동을 우회하지 않는다.

## 시간·재시작·실패 주입 경계

- PR의 E2E-11은 기존 WorldLifecycle의 정상 tick 이후 같은 `Party.reconcile_leader(now=...)` 서비스에 `since+599.999/600` 인자만 전달한다. 실제 캐릭터 세션과 영속 offline_since를 사용한다. 부모 실행기/Probe가 DB나 세션을 덮어쓰지 않는다. 이 Hook은 marker가 검증된 소유 서버 복사본에만 설치된다.
- E2E-13은 같은 복사본의 실제 `Take.run()`을 외부 `world_change()`로 감싸 지급 후 RuleError를 발생시킨다. 정상 게임 입력/프로토콜을 새 RPC로 대체하지 않는다. Savepoint/네트워크 전송 실패 경계는 T50-DATA의 실제 Python 회귀도 병행한다.
- 재시작 제어는 파일 allowlist의 `restart`만 기존 `Harness.restart()`에 전달한다. 정상 stop 뒤 checkpoint/동일 DB 재오픈·HTTP/WS Ready를 확인한다. 정상 만료 Door만 CLOSED/예약 없음으로 정규화될 수 있으며 다른 PK/권한/예약/설치 이력 리셋은 실패다.

## RELEASE와 아직 미실행인 Gate

`npm run test:browser:timing`은 별도 격리 서버에서 production Door 실제60초 및 리더 실제600초를 조건 기반 polling으로 검증한다. 타이머 단축 없음. `npm run test:browser:persistence`는 정상 재시작/롤백을 별도 서버에서 재실행한다. **G-09/G-10은 현재 NOT RUN**이며 실행기 존재로 PASS 처리하지 않는다. 최종 main의 RELEASE는 사용자 리뷰·병합 승인 뒤 별도 Workflow에서 수행한다.

OS IME는 PRIOR VERIFIED, 최초 Visual Baseline은 PENDING REVIEW다. Trace/Video/임의 실패 화면/원본 snapshot·DB·자격 증명·자유 입력은 업로드하지 않는다.


## 로컬 최종 결과와 후속

실제 E2E01~14 각각 PASS. 후속 Role 감사에서 E2E01의 기술/특성/훈련관리 NPC 및 권한 거절·저장 불변, E2E02의 실제 Credential/Quest로 밀림 길잡이 수락, E2E03의 정산관 실제 Native 교환도 추가해3개 PASS를 확인했다. NPC22개 전체 정적/권한/Help 계약은 실제 Python 전수와 연결한다.

정상 재시작의 만료 확정은 도달한 원래 deadline에서만 허용한다. 지연 sweep의 raw OPEN/원래 예약은 그대로 보존할 수 있으며 조기 닫힘/초기값/예약 리셋/자동 잠금/중복 Door는 허용하지 않는다. 논리적 만료 차단은 PR의 정확한 Door 경계 회귀 및 RELEASE 실제60초에서도 검사한다.

모든 직접 영향 성공의 SHA/개발 diff·실제시간·안전한 run ID는 통합 매트릭스에 있다. 최종 PR HEAD CI는 아직 PENDING이며 최종main RELEASE/실제60/600/Full은 NOT RUN이다.


## PR #60 리뷰 보완

- E2E08: 이전 실제 버튼을 보관하고 B 닫기 후 최신 UI 거절과 오래된 click 요청의 실제 서버 거절·위치/예약 불변을 확인한다. 재개방 뒤 최신 정상 버튼 통과도 검사한다. 텍스트 입력만으로 stale 버튼 PASS를 대체하지 않는다.
- E2E12: 실제 DB Exit/Room 및 DoorInstallation 교차 비교. PK/위치/목적지/Typeclass/관리ID/door_id/설치 증거를 정확히 보존하며 일반 출구 편입·중복/재생성은 거절한다. 잘못된 Snapshot의 음성 회귀도 포함한다.
- TIMING-DOOR/PARTY: 중간·만료 직전과 최대5초 간격의 pre-deadline 관측, 실제60초 연장 창, 실제 마지막 Puppet 해제·B 온라인·600초 미만 원리더 유지, 정상 Tick 이후 결과. 필수 관측 누락/늦음은 FAIL이다. 읽기2초/직전 시작-4초·완료최소-0.5초/정상Tick8초 상한은 브라우저 검증 문서에 기록한다.
- Windows 정상 restart 첫 보완 실행에서 checkpoint의 UTF-8 출력이 부모 CP949 기본 디코딩과 충돌했다. Harness.checkpoint에 encoding=utf-8를 명시하고 실제 자식 프로세스의 Unicode 출력 회귀 및 새 E2E12 성공으로 재검증했다. 실패97.320초와 안전한 정리 기록을 보존한다. 게임 구현 결함이나 정책 변경은 아니다.

정상 관측 및 조기30초 닫힘/300초 승계·Exit 구조 손상 음성 검출 PASS와 실제 RELEASE NOT RUN을 구분한다. E2E11의599.999/600 실제 서비스 주입 검사는 유지했다. 원본 DB/Snapshot/인증/입력/개인 메시지/Trace/Video는 공개 증거로 수집하지 않는다.


## PR #60 P2-03 — 최종 시간 경계 관측 보완

리뷰 기준 `5193aa2fd3232976eecf2a0f362cd4ec3e013fb5`, 수정 코드 `653340465930e9782a80aa6dde9154fddd71455a`, Base `82641de0ea66898676b0b29194d7918489443def`. 기존 4건 리뷰/실패/성공 이력은 당시 기록으로 보존한다. 이 보완은 게임·운영 타이머·프로토콜·영속 형식을 변경하지 않는다. 최종 문서 포함 Source HEAD의 Quick/새 네 CI는 실제 완료 후 [PR #60](https://github.com/wonmin82/primal-zone/pull/60)과 [Issue #50](https://github.com/wonmin82/primal-zone/issues/50)에 기록한다. 이 문서 커밋 시점에는 해당 게이트 PENDING이다.

`review-contracts.cjs::monitorBeforeDeadline()`은 더 이상 만료4초 전에 반환하지 않는다. 시작~중간~만료4초 전은 최대5초, 마지막 구간은 최대500ms의 시작 간격을 목표로 하며 직전 monotonic 조회 비용을 대기에서 뺀다. 조회가500ms보다 오래 걸리면 추가 대기 없이 다음 조회를 시작한다. 개별 조회 전체 비용 상한은 기존2,000ms다. 스케줄러 지연·2초 초과 조회·서버/세션 오류·필수 체크포인트 누락은 FAIL이며 창을 넓히거나 재시도로 숨기지 않는다.

중간 완료는 중간 시각부터7초 이내(5초 간격+최대2초 조회), 직전 반복 관측은 만료4~2초 전 구간에 실제 조회가 완료되어야 한다. **최종 유효 창은 `deadline - 1.0 <= observation.end <= deadline - 0.5`**다. 완료를 만료0.75초 전으로 맞추도록 직전 조회 비용을 고려한다. 관측 시작만 유효하거나 만료 직전 조회가 늦게 완료된 경우는 실패한다. 반환하는 `middleSeen/nearSeen/finalSeen`은 상태 원문을 포함하지 않으며 두 RELEASE 시나리오가 세 값 모두 true를 요구한다.

`integration_probe.py --timing`은 소유 경로/marker/명시 DB 검사를 거친 후 SQLite `mode=ro`·`query_only`·읽기 트랜잭션으로 실제 Door/일행/위치/Puppet/아이템/Claim을 읽는다. Attribute는 현재 내장 데이터만 복원하며 전역 객체/global·중복/소실은 거절한다. 기존 전체 Snapshot의 실제 Exit/설치/Room 영속 검사는 그대로 유지한다. 시간 검사와 E2E-11의 실제 DB projection 대조만 이 경량 조회를 사용한다. 원본 Snapshot/DB·사용자 입력·인증정보는 Artifact에 포함하지 않는다.

| ID | 정상/음성 조건 | 검증 결과 |
| --- | --- | --- |
| P203-01 | Door60 중간·4초 전 이후·최종 완료 창 | PASS |
| P203-02 | Door30 조기 CLOSED | 거절 검출 PASS |
| P203-03 | 56 OPEN→58 CLOSED | 거절 검출 PASS |
| P203-04 | 56 OPEN→58 LOCKED | 거절 검출 PASS |
| P203-05 | OPEN 유지·58초 예약 변경 | 거절 검출 PASS |
| P203-06 | Party600 중간·직전·최종 완료 창 | PASS |
| P203-07 | Party300 조기 승계 | 거절 검출 PASS |
| P203-08 | 596 원래 리더→598 새 리더 | 거절 검출 PASS |
| P203-09 | 최종 창 스케줄링 누락 | 거절 검출 PASS |
| P203-10 | 유효한 시작·만료 이후 조회 완료 | 거절 검출 PASS |
| P203-11 | 200ms/800ms 조회 지연·완료 창·간격 | PASS |
| P203-12 | 서버 조회 실패·오류 원문 비수집 | 거절 검출 PASS |

실제 테스트: `scripts/tests/test_integration_observations.cjs`; `npm run test:contracts`. 주입 wall/mono/pause로 동일 RELEASE 관측 Helper를 실행하며 실제60/600 대기를 하지 않는다. 별도 추가 회귀는 중간·만료4~2초 구간 누락과 최종0.5초 이후 완료를 검출한다.

- 수정 전58초 CLOSED/598초 승계 음성2개는 `Missing expected rejection`으로 FAIL(0.149초)하여 기존 관측 공백을 재현했다. 수정 후 같은 Helper의 P203-01~12와 추가 중간/직전 누락을 모두 거절/수용한다. 기존30초/300초·2초 조회 지연 회귀를 유지한다.
- 최종 Node 계약 **52 PASS/0.399초**, 기존43+신규9, fail/skip0. 시간 회귀16개와 Exit 회귀8개, 기존 웹/보호28개를 포함한다. Python 통합 Runner **9 PASS/2.393초**, 기존8+실제 SQLite projection/해시·mtime 비변경·손상 거절1개. 기존 Browser Runner Windows23 PASS·POSIX1 N/A/5.724초(정의24).
- 실제 Chromium E2E-11 **PASS/80.126초**, 서버 준비~정리119.703초(명령 진입점 전체120.619초). 실제599.999/600 서비스 주입·재접속·projection과 정상 실제 DB·소유 Puppet3관측 해제 확인. Node/Chromium/Evennia 종료·인증 삭제·성공DB 삭제·실제 플레이DB hash/mtime/size 불변 true.
- `npm run test:browser:timing`→TIMING-DOOR/PARTY→동일 관측 Helper 연결 및 RELEASE Workflow 호출을 Runner가 확인했다. 정상/조기 회귀는 주입 Clock 검증이며 **실제60초/600초 Wall Clock PASS로 합산하지 않는다**.
- check·변경JS 구문·diff PASS. 게임/Python 전체 구현 및 의존성은 변경하지 않았다. 기존 로컬 전체229/816 성공(이전 리뷰 SHA의 기록)을 새 실행으로 표현하지 않고, 이번 직접 영향 QA 회귀와 새 HEAD의 원격 전체 Suite로 확인한다.

추가 실측에서 기존 전체 Snapshot13회는4,065~5,822ms(중앙4,464ms), 최초 Django projection1회도3,826ms로2초 예산을 초과했다. 실제 E2E-11의 두 조회 사이 정상 회복실60초 Sweep으로 새 Door 전수 동일 비교가93.260초 실행에서 FAIL했다. 과거 실패를 보존하고, 만료 예약 없는 관리실은 정확히 비교하며 회복실의 정상 만료를 다른 조회 시점의 상태 손상으로 오인하지 않는다. 실제 회복실/Exit 보존은 기존 E2E-08/12 및 RELEASE에서 계속 검증한다.

최종 SQLite 전용 조회는 같은 실제 E2E-11에서 **145.697ms(1회)**로 측정했다. 이는 Windows 한 실행의 실측이며 모든 CI 지연을 보증하지 않는다. 200ms·800ms 정상 지연/지연 초과·스케줄링 누락 음성 회귀가 별도로 있고 실제 최종 창을 놓치면 정상 PASS로 처리하지 않는다. 단위 Fixture의 Windows 연결 핸들 닫힘 누락도 실패 후 명시 close로 보완했다. 실패 DB/로그는 소유 로컬 경로에만 보존하고 자격 증명·프로세스는 제거했다.

RF-33~46은 관측 구현/검출 회귀/실제 서비스 주입/RELEASE 연결/안전성으로 확인한다. RF-47~50 최종 Quick·새 네 CI·기록·차단 결함 감사는 실제 완료 후 PR/Issue에서 확정한다. RF-51~52: **실제 Door60초·리더600초 RELEASE NOT RUN**, PR60 OPEN/Ready·Source 유지·Issue50/45 OPEN. G-12 Full·G-14 최종main CI/RELEASE·G-15 FinalCloseout NOT RUN, IME PRIOR VERIFIED, Visual Baseline PENDING REVIEW, Issue58 비범위, 기존 favicon P2 #59 추적 유지. Merge/브랜치 삭제/Issue Close는 수행하지 않는다.
