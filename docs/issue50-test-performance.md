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
