# Issue #50 검증 성능 기록

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
