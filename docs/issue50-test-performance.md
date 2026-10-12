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
