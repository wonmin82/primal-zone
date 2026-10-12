# Issue #50 검증 성능 기록

## 2026-10-12 최초 성공 RELEASE 및 최종 Closeout 준비

[PR #60](https://github.com/wonmin82/primal-zone/pull/60)은 Merge Commit `855ada380e5276334f0744797a86a5aef300297c`으로 병합됐다. 첫 부모는 `82641de0ea66898676b0b29194d7918489443def`, 둘째 부모는 검토 Source `26da18221f890f3405aca84b746741e3da7f747b`이며 임시 병합 결과와 Tree가 같고 원본 이력이 보존됐다. [당시 main CI](https://github.com/wonmin82/primal-zone/actions/runs/38239786496)의 네 Job은 모두 SUCCESS다.

[최초 RELEASE 실패](https://github.com/wonmin82/primal-zone/actions/runs/38241057595)는 삭제하지 않는다. 8개 중 7개 Job은 SUCCESS였지만 Full Smoke가 60초 후 정상 닫힌 회복실 문을 열지 않고 이동해 실패했다. 이는 QA 이동 경로의 누락이며 게임의 차단은 정상이다. [최소 수정 PR #61](https://github.com/wonmin82/primal-zone/pull/61)의 `0a03b44612822796f703e4d077916330e909a4fb`는 실제 `회복실 문 열어`를 양쪽 이동 전에 실행한다. 정상·실패·비관련 출구 회귀3개를 추가했으며 게임 정책·타이머·프로토콜·저장 형식은 바꾸지 않았다. 수정 Merge는 `11a1c6bce91a5499292f8fbabff3e308663814fe`이고 부모는 `855ada380e5276334f0744797a86a5aef300297c`와 `0a03b44612822796f703e4d077916330e909a4fb`다.

**최초 성공 RELEASE SHA: `11a1c6bce91a5499292f8fbabff3e308663814fe`.** [main CI](https://github.com/wonmin82/primal-zone/actions/runs/38244636657) 네 Job SUCCESS, [RELEASE](https://github.com/wonmin82/primal-zone/actions/runs/38251167392) 8개 Job SUCCESS, main/workflow_dispatch/attempt1 및 입력·GITHUB_SHA·실제 Checkout SHA 일치를 모든 Job의 Guard8개로 확인했다. RELEASE 전체 병렬 경과는 819초다. Job 로그·Assertion 및 안전한 Artifact를 직접 검토했다. 아래 최초 실패/성공과 과거 로컬 검증을 서로 다른 실행으로 보존한다.

**최종 SHA Closeout은 아직 대기 중이다.** 이 문서 PR을 Merge Commit으로 병합한 뒤 새 `FINAL_MAIN_SHA`의 push CI 네 Job과 RELEASE8개 Job을 다시 실행한다. 같은 SHA의 성공으로 대체하지 않는다. 최종 실행 증거는 [Issue #50 공식 Final Closeout 기록](https://github.com/wonmin82/primal-zone/issues/50#issuecomment-6124806608)에 추가하고, 결과 때문에 새 Git Commit을 만들어 SHA를 다시 바꾸지 않는다. 최종 Gate를 확인한 뒤에만 #50·#45를 종료하고 병합된 작업 브랜치를 안전하게 정리한다.

### 병합 main CI 실측

| Job | 실제 결과 | 경과 시간 | 실행 증거 |
| --- | --- | --- | --- |
| contracts | SUCCESS | 13초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38244636657/job/114795369005) |
| test | SUCCESS | 690초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38244636657/job/114795369391) |
| smoke | SUCCESS | 72초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38244636657/job/114795369480) |
| browser-e2e | SUCCESS | 694초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38244636657/job/114795369504) |

병렬 전체 698초.

### 최초 성공 RELEASE 실측

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

병렬 전체 819초. 설치·업로드를 포함한 Job 경과와 각 테스트의 시간은 구분한다. 최초 실패 RELEASE805초는 별도 실패 이력이며 성공 실행에 합산하지 않는다. 목표시간을 맞추기 위해 필수 검사/실제600초를 줄이지 않았다. 문서 병합 뒤 다른 SHA에서 실행하는 두 번째 성공 RELEASE는 필수 최종 검증이며 동일 코드의 불필요한 로컬 전체 반복과 구분한다.

### 로그의 실제 건수/시간

- `Ran 232 tests in 1.195s`
- `Ran 816 tests in 406.650s`
- `{"profile": "timing", "tests": 2, "seconds": 771.064}`
- `ℹ tests 52`
- `ℹ duration_ms 110.876848`
- `PASS [quick] 완료 / process stop / temp cleanup: 60.549s`
- `{"profile": "persistence", "tests": 2, "seconds": 92.719}`
- `Ran 33 tests in 2.249s`
- `{"profile": "pr", "tests": 14, "seconds": 635.77}`
- `PASS [full] 완료 / process stop / temp cleanup: 504.680s`

### 실제 시간과 정상 재시작

- TEST-TIMING-DOOR **PASS/100.737초**: 실제 열기/양방향OPEN·통과 완료 기준+60초·중복 열기/실패 통과 예약 불변·중간 관측·만료4초 전 이후 최대500ms 목표 반복·최종 `deadline-1.0 <= end <= deadline-0.5` 완료·만료후 실제 이동 거절·정상 Tick CLOSED·웹 양쪽 동기화. 단위 Clock 주입으로 대체하지 않았다.
- TEST-TIMING-PARTY **PASS/640.504초**: A 마지막 소유 Puppet 종료·실제 offline_since·B온라인·300초 부근/직전/최종 완료 창까지 A 유지·실제600초 이후 정상 Tick 승계·A재접속 권한 자동복원 없음·구성/전술/아이템/Claim 보존.
- 같은 RELEASE Helper의 Node 시간16개는30/58초 CLOSED·58초LOCKED·예약변경·300/598초승계·필수관측 누락/지연/조회오류를 실제로 거절한다. 조회 상한2초/최종 유효 창은 완화하지 않았고 누락 시FAIL이다. E2E11의599.999/600 서비스 주입과 실제 시간 검사를 별도로 기록한다.
- 독립 persistence 재검증 E2E12 **45.936초**, E2E13 **16.846초**: 실제 Exit 및 DoorInstallation·Profile/줄임말·Item UUID/장착/수량·Party·Quest/Credential·Native/Legacy/Claim·정상 만료와 데이터 손실 구분·상위 Rollback/알림 차단. 일반 Exit의 독립성도 비교한다.


## 아래 기록의 시점

아래 기존 NOT RUN·PENDING·OPEN·Pre-merge 및 Phase 범위 표기는 해당 구현·리뷰 당시의 역사적 기록이다. 삭제하거나 새 SHA의 실행 결과로 재작성하지 않는다. 현재 결과와 최종 확인 절차는 위 기록 및 연결된 Final Closeout 기록을 따른다.

이번 범위는 Phase 50-A다. P-02의 시간 예산은 성공한 **한 번 실행**의 경과 시간이고 개발·실패 수정·다운로드 재시도 시간을 숨기는 기준이 아니다.

`npm run test:browser`의 `run.json`은 DB 준비부터 실제 브라우저, Portal/Server 종료와 격리 확인까지 총 경과 시간을 기록한다. `results.json`은 각 TEST-50A-01~06의 실제 시간을 가진다. CI Job 시작/종료·설치 시간을 포함한 경과 시간은 연결 PR Validation에서 실제 Run URL·SHA와 함께 기록한다.

일반 PR 네 Job은 독립 Runner/DB로 병렬 실행한다. browser-e2e의 Playwright worker는 1이며 한 테스트 안의 독립 Context 여러 개는 허용한다. 기존 test 20분/smoke 10분은 변경하지 않았고 새 browser-e2e 15분/contracts 5분 제한을 둔다.

600초 리더 승계·60초 Door 전수·Full Gameplay·정상 서버 Restart RELEASE는 이번 단계 **NOT RUN**이다. 일반 PR 목표 12~20분 및 RELEASE 20~35분은 정책을 완화하는 절대 제한이 아니다.

실제 로컬 시간·실패 이력은 [50-A 실행 기록](playtest.md#issue-50-phase-50-a)에 연결한다. 최신 원격 실행은 [Issue #50](https://github.com/wonmin82/primal-zone/issues/50)의 Phase 50-A 연결 PR에서 추적한다.

## 2026-10-12 로컬 측정

Windows / Python 3.13.15 / Node 24.19.0. 실행 기준은 착수 HEAD `7afc09d064ea0e45dc68f77ab7ede6c5e7237202` + 이후 코드 커밋 `f63a12756346aae5dc841b208bacc3113267436d`와 동일한 미커밋 인프라다. 문서 이후 동일 코드 재검사를 새 실행으로 기록하지 않는다.

| 검사 | 건수·결과 | 실제 시간 |
| --- | --- | --- |
| 실제 Chromium 최소 E2E | 6 PASS·skip/flaky 0 | 41.921초 |
| 서버 준비~DB/프로세스 정리 전체 | 성공·플레이 DB 불변 | 89.154초 |
| 기존 Node 계약 | 16 PASS | 0.486초 |
| 신규 실행기 격리 | 3 PASS | 0.173초 |
| 관련 Python Harness 회귀 | 18 PASS | 12.545초 / runner 27.741초 |

정확한 최종 Push HEAD의 Quick/Smoke와 설치·업로드를 포함한 원격 Job 시간은 실제 실행 이후 연결 PR Validation에 기록한다. 이 표의 89.154초를 CI Job 전체 시간이나 Full Gameplay 검증 시간으로 해석하지 않는다.

## PR #57 리뷰 보완 측정

실행 환경은 위 Windows/Node/Python/Playwright 버전을 유지한다. 기준은 `7ddf8d5` + 리뷰 수정 diff이며 코드 커밋 `b0fd1b2a4fe776d6d173793854eddc54ac352f42`에 연결한다. 기존 최초 구현·실패 시간은 삭제하지 않는다.

| 검사 | 건수·결과 | 실제 시간 |
| --- | --- | --- |
| Python Runner 직접 회귀 | 기존 3 + 신규 9 = 12 PASS | 0.544초 |
| Node 계약 | 기존 16 + 신규 10 = 26 PASS | 0.229초 |
| 기존 Python Harness 통합 | 18 PASS | 테스트 12.533초 / runner 23.506초 |
| 정상 Chromium 연속 1회 | 9 PASS | E2E 62.703초 / 전체 106.081초 |
| 정상 Chromium 연속 2회 | 9 PASS | E2E 62.624초 / 전체 106.446초 |
| 정상 Chromium 연속 3회 | 9 PASS | E2E 62.652초 / 전체 106.320초 |
| 최종 비수집 경계 정상 실행 | 9 PASS·종료 0 | E2E 62.735초 / 전체 105.839초 |
| 실제 Assertion 음성 검사 | 1개 예상 FAIL·종료 1, 비수집/정리 검증 성공 | E2E 8.943초 / 전체 50.316초 |

초기 수정 실행의 9 FAIL/278.124초, favicon 분류 보정 전 6 FAIL·3 PASS/107.575초 및 음성 선택 패턴 오류의 0개 실행/50.636초를 [실패 이력](playtest.md#pr-57-p2-리뷰-보완)에 별도로 남긴다. 음성 검사의 FAIL을 일반 브라우저 PASS 수에 합산하지 않는다. 정확한 최종 Push HEAD Quick 및 원격 네 Job의 SHA·경과 시간·URL은 [PR #57](https://github.com/wonmin82/primal-zone/pull/57) Review Fixes에서 실제 실행 후 기록한다. 성공 Artifact 14일/실패 30일과 기존 네 Job의 시간 제한은 유지한다.


## P2-04 최종 로컬 측정

기준은 리뷰 HEAD `9651918`와 P2-04 diff이며 커밋 이후 새 실행으로 표현하지 않는다. 실제 Windows 소유 경계에서 아래 연속 3회 성공을 확인했다. 이후 추가한 Linux detached Chromium의 subreaper/pidfd 분기 및 실행 시작 실패 증거는 Windows 정상 분기를 변경하지 않았으며, 오류 경계는 전체 Runner를 다시 실행했다. Linux 실제 실행은 Ubuntu CI의 별도 필수 결과이고 macOS는 NOT RUN이다.

| 최종 Windows 반복 | 실제 E2E | 서버·브라우저 정리 포함 | 결과 |
| --- | --- | --- | --- |
| 1 / run-cgrozeie | 9개 / 63.419초 | 106.729초 | PASS |
| 2 / run-h_8pirtg | 9개 / 64.531초 | 108.734초 | PASS |
| 3 / run-m3fyai8u | 9개 / 61.993초 | 106.195초 | PASS |

각 실행의 browser_processes_stopped/Evennia processes_stopped/credentials_removed/play_db_unchanged가 true이고 실제 관측의 Context 종료·소유 Puppet 해제가 모두 true였다. 안전 Artifact 9개 파일만 존재하며 비공개 입력/인증 원문·DB·Trace/영상·임의 오류 context가 없음을 확인했다.

- 최종 Runner: 정의 23개, Windows 해당 22개 PASS·POSIX 전용 1개 N/A, 5.462초. 신규 11개 중 Windows 해당 10개 실제 실행. Ubuntu에서는 Windows 전용 1개 N/A 및 Linux detached/강제 종료/소유권 실패를 실행한다.
- Node 계약 26개 PASS/0.242초, 관련 Python Harness 18개 PASS/10.166초, dev.py check/git diff --check PASS. 게임·Harness·JavaScript 변경 없음.
- 최초 Chromium 및 개발 안정화 시간/실패는 playtest.md에 보존한다. 정확한 Push HEAD Quick, PR 네 Job, Merge Commit/main 네 Job 시간은 PR #57/Issue #50 P2-04 기록에서 실제 SHA·URL로 확정한다. CI 전/병합 전 결과를 미리 PASS로 쓰지 않는다.

## P2-04 시작 실패 파이프 보완

최초 Ubuntu Run 38187028065의 Runner는 FAIL/1.552초였고 Chromium은 NOT RUN이다. 수정 후 Windows Runner 정의 24개 중 23개 PASS·POSIX 전용 1개 N/A/5.280초를 확인했다. 새 HEAD의 Quick/Ubuntu 결과는 PR 및 Issue에서 확인하며 이전 시간 표를 새 실행으로 재사용하지 않는다. 실패·원인은 [실행 이력](playtest.md#p2-04-최초-ubuntu-ci-실패-및-수정)에 보존한다.
## Phase 50-B~F 준비의 실측과 실행 분리

- 계약74개에 연결된 실제70개 테스트: 186.579초 PASS. 최종 신규 계약3개:23.133초/전체34.899초 PASS. Frozen Alias의 순서까지 요구한 최초 전체 실행은 FAIL이며 수정 전 기록은 [실행 이력](playtest.md)에 보존한다.
- 기존 Runner 정의24개 중 Windows 해당23 PASS/7.248초·POSIX 전용1 N/A, 새 제어/manifest/main SHA guard5 PASS/1.391초. Node27 PASS/0.336초. 플랫폼 N/A를 PASS 수에 더하지 않는다.
- Windows 개별 Chromium 준비~정리 개발 실측: E2E-01 73.276초, E2E-03 113.085초, E2E-05 144.714초, E2E-04 129.640초, E2E-06 142.665초, E2E-07 121.022초, E2E-09 133.066초, E2E-10 70.517초, E2E-11 131.311초. 실제 NPC 버튼을 추가한 E2E-02는 다른 로컬 검사와 병행한244.529초였다. 이 값은 최신 전체 단독 실행이나 Ubuntu CI의 실측으로 표현하지 않는다.
- 매 시나리오는 새 격리 Harness로 초기 조건/DB/타이머 간섭을 없앤다. 실제 게임 명령·WS를 Mock으로 대체하여 시간을 줄이지 않는다. 읽기 전용 Probe는 Python 초기화 비용이 있어 로컬 병행 실행의 부하를 따로 기록한다. 초기 테스트 작성/실패 수정 시간은 D21/P-02 성공1회 시간 예산과 구분한다.
- PR의 기존 네 Job 유지. browser-e2e에서50-A와 전체14 및 실행기 회귀를 실행하며 worker1/retries0이다. Job timeout20분은 오류 발견을 위한 상한이며 수용 기준을 줄이지 않는다. 최종 네 CI Job별 시간/전체 경과는 실제 Run 완료 후 기록한다.
- RELEASE는 test/Quick/Full/contracts/browser전체/timing/persistence를 각 독립 DB/서버에서 병렬 실행한다. timing의 최소 실제600초는 줄이지 않으며 다른 Job과 병렬이다. 일반 PR12~20분·RELEASE20~35분/30분 이내 목표를 유지한다. **실제 RELEASE 시간은 NOT RUN**, Workflow 준비만으로 목표를 달성했다고 주장하지 않는다.


## 최종 로컬 제출 검증 (원격 CI 전)

순수229/통합814 PASS, 기존50-A9 + 실제E2E01~14 PASS. Runner Windows23(정의24/POSIX1 N/A)+신규6, Harness18, Node28 PASS. 실행 SHA/개발 diff와 실제 개별 시간은 통합 매트릭스에 구분했다. 후속 NPC 역할 보강3개는83.015/152.005/92.905초, 정상 restart의 만료 sweep 분류 보강은128.467초 PASS다. 이는 원격 최신HEAD/RELEASE 실행 성공을 의미하지 않는다.

이 문서 앞의 미확정/초기 실행 기록은 개발 당시 이력이다. 현재 로컬 WEB01~12 기능 수용은 PASS이며 정확한 최종 Push HEAD Quick 및 네 GitHub Job은 PR/Issue50에서 새로 확정한다. 실제60/600/Full/최종main RELEASE는 NOT RUN, IME PRIOR VERIFIED, 이미지 PENDING REVIEW 유지. 비차단 favicon은 [후속P2 #59](https://github.com/wonmin82/primal-zone/issues/59)에 이관했다.


## PR #60 리뷰 보완 실측

직접 영향: Node 기존28+관측15=43 PASS/0.337초, Runner 기존통합6+신규2=8 PASS/1.357초, 기존브라우저Runner Windows23 PASS·POSIX1 N/A/5.445초. 문서계약 기존3+신규2=5 PASS/19.449초(전체28.661초), Door/Bootstrap/스키마/Exit/Smoke 영향70 PASS/102.156초(전체113.213초). 실제 E2E08/11/12 각151.801/141.538/143.987초 전체 PASS. 재시작 Unicode 실패97.320초는 별도로 보존하며 최종 성공 시간에 합치지 않는다.

최종 Python 전체·정확한 Push HEAD Quick·원격 네 Job은 실제 실행 완료 후 PR/Issue50에 개수/시간/SHA를 확정한다. RELEASE 실제60/600/Full 및 최종main 실행은 NOT RUN. 샘플5초/중간·직전필수·조회상한2초는 비용 절감으로 타이밍 조건을 완화하기 위한 것이 아니다. 지연으로 필수 관측을 놓치면 FAIL이다.


### 리뷰 보완 최종 로컬 결과

관측/버튼/Probe/checkpoint `51f418bc409ba637e2d27b3db64894d4fc7e2bdb`, 기능 문서 계약/정정 `52e630047ca5cb0172c6c779709b13b7ce4af310`. 검증은 리뷰HEAD d7736c54+동일 개발diff에서 시작했으며 해당 코드가 그대로 이 두 커밋에 포함됨을 확인했다. 이후 검증 문서만 추가했으므로 같은 전체 회귀를 다시 실행하지 않는다.

- 최종 전체 `uv run python scripts/dev.py test --parallel 4`: 순수229 PASS/2.534초, 통합816 PASS/513.301초, 전체523.943초. 기존814에 문서 검사2개 추가, 실패0.
- Node43 PASS/0.518초(시간7·Exit8 신규 음성/정상 포함), 통합Runner8 PASS/1.713초, 기존브라우저Runner Windows23 PASS·POSIX1 N/A/5.445초. 문서5/19.449초·직접영향70/102.156초·실제08/11/12 전체151.801/141.538/143.987초 PASS.
- `check`·변경JS구문·`git diff --check` PASS. GFM 변경10문서 렌더, 전체Markdown59/상대링크567/앵커194/기존README앵커12 오류0.
- 실제 플레이DB hash/mtime/size 불변과 실제브라우저 소유프로세스/인증/Puppet 정리를 확인했다. 정확한 최종 문서 포함 HEAD의 Quick 및 새 원격 CI는 실제 완료 후 PR/Issue50에 기록한다. 현재 문서 작성 시점에는 아직 실행 전이다.
- 실제60/600·Full·최종main CI/RELEASE·FinalCloseout은 NOT RUN이다. 기존 성공/개발 FAIL·최초CI38204318598은 역사 기록으로 보존한다. PR60/Source/Issue50·45 유지, Issue58 비범위, #59 추적.


## PR #60 P2-03 — 최종 시간 경계 관측 보완

리뷰 기준 `5193aa2fd3232976eecf2a0f362cd4ec3e013fb5`, 수정 코드 `653340465930e9782a80aa6dde9154fddd71455a`, Base `82641de0ea66898676b0b29194d7918489443def`. 기존 4건 리뷰/실패/성공 이력은 당시 기록으로 보존한다. 이 보완은 게임·운영 타이머·프로토콜·영속 형식을 변경하지 않는다. 최종 문서 포함 Source HEAD의 Quick/새 네 CI는 실제 완료 후 [PR #60](https://github.com/wonmin82/primal-zone/pull/60)과 [Issue #50](https://github.com/wonmin82/primal-zone/issues/50)에 기록한다. 이 문서 커밋 시점에는 해당 게이트 PENDING이다.

추가 실측에서 기존 전체 Snapshot13회는4,065~5,822ms(중앙4,464ms), 최초 Django projection1회도3,826ms로2초 예산을 초과했다. 실제 E2E-11의 두 조회 사이 정상 회복실60초 Sweep으로 새 Door 전수 동일 비교가93.260초 실행에서 FAIL했다. 과거 실패를 보존하고, 만료 예약 없는 관리실은 정확히 비교하며 회복실의 정상 만료를 다른 조회 시점의 상태 손상으로 오인하지 않는다. 실제 회복실/Exit 보존은 기존 E2E-08/12 및 RELEASE에서 계속 검증한다.

최종 SQLite 전용 조회는 같은 실제 E2E-11에서 **145.697ms(1회)**로 측정했다. 이는 Windows 한 실행의 실측이며 모든 CI 지연을 보증하지 않는다. 200ms·800ms 정상 지연/지연 초과·스케줄링 누락 음성 회귀가 별도로 있고 실제 최종 창을 놓치면 정상 PASS로 처리하지 않는다. 단위 Fixture의 Windows 연결 핸들 닫힘 누락도 실패 후 명시 close로 보완했다. 실패 DB/로그는 소유 로컬 경로에만 보존하고 자격 증명·프로세스는 제거했다.

- 수정 전58초 CLOSED/598초 승계 음성2개는 `Missing expected rejection`으로 FAIL(0.149초)하여 기존 관측 공백을 재현했다. 수정 후 같은 Helper의 P203-01~12와 추가 중간/직전 누락을 모두 거절/수용한다. 기존30초/300초·2초 조회 지연 회귀를 유지한다.
- 최종 Node 계약 **52 PASS/0.399초**, 기존43+신규9, fail/skip0. 시간 회귀16개와 Exit 회귀8개, 기존 웹/보호28개를 포함한다. Python 통합 Runner **9 PASS/2.393초**, 기존8+실제 SQLite projection/해시·mtime 비변경·손상 거절1개. 기존 Browser Runner Windows23 PASS·POSIX1 N/A/5.724초(정의24).
- 실제 Chromium E2E-11 **PASS/80.126초**, 서버 준비~정리119.703초(명령 진입점 전체120.619초). 실제599.999/600 서비스 주입·재접속·projection과 정상 실제 DB·소유 Puppet3관측 해제 확인. Node/Chromium/Evennia 종료·인증 삭제·성공DB 삭제·실제 플레이DB hash/mtime/size 불변 true.
- `npm run test:browser:timing`→TIMING-DOOR/PARTY→동일 관측 Helper 연결 및 RELEASE Workflow 호출을 Runner가 확인했다. 정상/조기 회귀는 주입 Clock 검증이며 **실제60초/600초 Wall Clock PASS로 합산하지 않는다**.
- check·변경JS 구문·diff PASS. 게임/Python 전체 구현 및 의존성은 변경하지 않았다. 기존 로컬 전체229/816 성공(이전 리뷰 SHA의 기록)을 새 실행으로 표현하지 않고, 이번 직접 영향 QA 회귀와 새 HEAD의 원격 전체 Suite로 확인한다.

시간 관측 추가 대기는 이전4초 전 반환 대비 정상최종 완료까지 약3~3.5초/시나리오이며 실제60/600 운영 시간 자체는 증가하지 않는다. 일반PR은 Wall Clock 검사를 실행하지 않아 새52개 Node 계약의 비용만 수백ms 수준으로 증가한다. 새 GitHub 전체Job/RELEASE의 실시간은 실행 후 기록하며 추정치를 실제 결과로 표시하지 않는다.

RF-33~46은 관측 구현/검출 회귀/실제 서비스 주입/RELEASE 연결/안전성으로 확인한다. RF-47~50 최종 Quick·새 네 CI·기록·차단 결함 감사는 실제 완료 후 PR/Issue에서 확정한다. RF-51~52: **실제 Door60초·리더600초 RELEASE NOT RUN**, PR60 OPEN/Ready·Source 유지·Issue50/45 OPEN. G-12 Full·G-14 최종main CI/RELEASE·G-15 FinalCloseout NOT RUN, IME PRIOR VERIFIED, Visual Baseline PENDING REVIEW, Issue58 비범위, 기존 favicon P2 #59 추적 유지. Merge/브랜치 삭제/Issue Close는 수행하지 않는다.
