# Issue #50 통합 검증 추적

[v1.2 DESIGN FREEZE](https://github.com/wonmin82/primal-zone/issues/50)의 D01~D28 및 P-01/P-02를 유지한다. 이 PR은 **50-A만** 구현한다. 일반 PR CI는 test/smoke/browser-e2e/contracts이며 최종 RELEASE와 구분한다.

## 기준선 감사

착수 main: `7afc09d064ea0e45dc68f77ab7ede6c5e7237202`. #45/#50 OPEN, #46~#49/#54 CLOSED 및 아래 PR MERGED를 GitHub에서 재조회했다. 기존 기록을 새 실행으로 표현하지 않는다.

| 선행 | 최종 PR HEAD | Merge Commit | PR CI / 병합 main CI |
| --- | --- | --- | --- |
| #46 / #51 | `261cf95952ac409e2dcee97433d4b06b5793efb5` | `06c90ac92974dfcaf7ef6c2564ed9207e8dee8e8` | [성공](https://github.com/wonmin82/primal-zone/actions/runs/38045483861) / [성공](https://github.com/wonmin82/primal-zone/actions/runs/38046992168) |
| #47 / #52 | `37b70f22b4cc73a42d9aac8330c7cfc7b9f27b6b` | `49669e24ebccfc7d876a6027e175a2e4e3d85382` | [성공](https://github.com/wonmin82/primal-zone/actions/runs/38093587658) / [성공](https://github.com/wonmin82/primal-zone/actions/runs/38094190782) |
| #48 / #53 | `119272247d2e0e4936d447a9c5554e562fcd74d9` | `f48a632a1dd6a56b283f3864d6a4ace7e0f3b355` | [성공](https://github.com/wonmin82/primal-zone/actions/runs/38111536068) / [성공](https://github.com/wonmin82/primal-zone/actions/runs/38112582794) |
| #54 / #55 | `d68995287a1d6b10753a06a4aa06f487c074cbb3` | `bd18e6ff4e9f1d2e345015eba805353be0e1cae1` | [성공](https://github.com/wonmin82/primal-zone/actions/runs/38114034353) / [성공](https://github.com/wonmin82/primal-zone/actions/runs/38115248134) |
| #49 / #56 | `c80a14ba0b2316901da1adae2e81cd3a0da7fba3` | `7afc09d064ea0e45dc68f77ab7ede6c5e7237202` | [성공](https://github.com/wonmin82/primal-zone/actions/runs/38134927725) / [성공](https://github.com/wonmin82/primal-zone/actions/runs/38146739731) |

선행 로컬 전체/Quick 결과와 실패 이력은 기존 `docs/playtest.md` 및 각 PR/Issue 검증 기록을 보존한다. #46의 당시 전체 검사와 이후 정확한 Push HEAD Quick/Smoke는 같은 종류의 검증으로 합산하지 않는다.

## 50-A 수용 테스트

실행: `npm run test:browser`. 실제 테스트 경로: `scripts/browser/phase50a.spec.cjs`의 아래 제목. 상태는 다음 실행 기록과 연결한다. CI 링크는 [Issue #50 Phase 50-A 진행 구역](https://github.com/wonmin82/primal-zone/issues/50)의 연결 PR에서 **실제 최신 SHA**로 갱신한다.

| 테스트 | Decision | 검증 Assertion | 후속 연결 |
| --- | --- | --- | --- |
| TEST-50A-01 | D06/D07/D12/D13 | Chromium HTTP 200, 실제 WS, 인증·초기 상태·이름·입력·차단 Console 오류 없음 | 50-C / T50-WEB |
| TEST-50A-02 | D03/D11 | 점수 Enter 실제 전송 1회, 서버 sheet·상태·새 Prompt | 50-B/C / CMD·WEB |
| TEST-50A-03 | D10/D12 | 서로 다른 Account/Context/WS, 실제 Puppet 각 1, 이름 혼동 없음 | 50-D |
| TEST-50A-04 | D10/D11 | 같은 방 공개 원문 동일, 두 화면 각 1회, HTML 문자열 비실행 | 50-C/D / MSG |
| TEST-50A-05 | D10/D12 | 실제 종료·재연결·재인증, Puppet 1→0→1, 새 ID | 50-D / DATA |
| TEST-50A-06 | D08/D09/D11/P-01 | 두 Viewport, 가로 overflow 없음, 입력/출력·접근 가능한 버튼·PNG | 50-C |

Runner 회귀: `scripts/tests/test_browser_runner.py`의 비밀번호 제거, 외부 DB 거절, 실제 SQLite 읽기 전용 세션 조회 3개. Node 계약은 기존 `scripts/tests/test_web_prompt.cjs` 16개를 유지한다. 기존 Harness 회귀는 `world.test_smoke` 및 `tests.test_smoke_infrastructure` 18개다.

### 실행 증거와 제출 Gate

2026-10-12 Windows 실행 HEAD는 `7afc09d064ea0e45dc68f77ab7ede6c5e7237202` + 미커밋 인프라였으며 이후 코드 커밋 `f63a12756346aae5dc841b208bacc3113267436d`와 실행 코드가 동일하다. 이를 커밋 후 새 실행으로 표현하지 않는다. 이후 변경은 문서이며 동일 브라우저 회귀를 반복하지 않는다. 최종 Push HEAD의 Quick/Smoke 및 원격 네 Job은 연결 PR/Issue에 실제 SHA와 URL로 별도 확정한다.

| 테스트 | 상태 | 실제 시간 | 근거 |
| --- | --- | --- | --- |
| TEST-50A-01 | PASS | 3.972초 | 실제 Chromium 156.0.8078.4 인증·초기 상태 |
| TEST-50A-02 | PASS | 3.481초 | 점수 1회 전송·새 Prompt·서버 sheet |
| TEST-50A-03 | PASS | 8.063초 | 서로 다른 두 Account/Context/WS·Puppet 각 1 |
| TEST-50A-04 | PASS | 8.269초 | 두 세션 동일 공개 원문·각 1회·HTML 비실행 |
| TEST-50A-05 | PASS | 8.477초 | Puppet 1→0→1·새 세션 ID |
| TEST-50A-06 | PASS | 7.708초 | 두 Viewport·입력/버튼/overflow·리뷰용 PNG |

로컬 `run-8m2ki8dx/results.json` 및 `run.json`: 6개 성공, 건너뜀/예상치 못한 실패/Flaky 0, Playwright 41.921초 / 준비·종료 포함 89.154초, 플레이 DB 불변·소유 프로세스 종료. 이 ignored 증거 경로는 영구 배포물이 아니며 최종 CI Artifact가 원격 증거다. [실패 이력](playtest.md#issue-50-phase-50-a)을 함께 보존한다.

| Gate | 로컬 근거 / 제출 확인 |
| --- | --- |
| A-01~02 | 최신 main·선행 5개 PR/CI 감사, 기존 Harness 재사용, 게임 파일 diff 없음 |
| A-03~07 | TEST-50A-01/02 실제 서버·Chromium·HTTP/WS·UI 인증·명령·Prompt PASS |
| A-08~10 | TEST-50A-03/04/05 독립 두 플레이어·공개 메시지·재접속 PASS |
| A-11~13 | TEST-50A-06 두 Viewport·PNG 및 실패 결과/로그 수집 PASS. 이미지 승인 미실행 |
| A-14~15 | DB hash/mtime/size 불변, 서버 종료, 기존 Node 16개/Python 18개 및 신규 격리 3개 PASS |
| A-16~17 | 이 문서 작성 시 NOT RUN. 최종 Push HEAD Quick 및 최신 원격 test/smoke/browser-e2e/contracts 결과는 PR/Issue에서 확정 |
| A-18~19 | 매트릭스·브라우저·성능·실행/실패 기록 작성, 50-B~F NOT RUN |
| A-20 | 이 문서 작성 시 PR 제출 전. 실제 Ready PR 링크는 Issue #50 진행 구역에 추가 |

## 후속 미실행 상태

| Phase / 검증 그룹 | 상태 | 남은 작업 |
| --- | --- | --- |
| 50-B / T50-CMD·ALIAS·GAME·NPC·MSG·PARTY·DOOR·HELP·DATA 전수 | NOT RUN | 현행 테스트 연결·공백 및 교차 계약 추가 |
| 50-C / E2E-01~14 및 T50-WEB 전수 | NOT RUN | 실제 역할별 기능·버튼·Focus·승인 이미지·접근성 확대 |
| 50-D / 전체 동시성·600초·60초·정상 서버 Restart | NOT RUN | 실제 시간·다중 세션·영속 비교 / RELEASE |
| 50-E / 기능 결함 Closeout | NOT RUN | 별도 재현·영향 평가·수정 PR 및 사용자 승인 |
| 50-F / 최종 main RELEASE·G-01~15·상위 #45 종료 | NOT RUN | 최종 병합 main 별도 검증·5개 산출물·승인 |
| OS 한국어 IME | PRIOR VERIFIED | 기존 사용자 Windows 수동 성공, 신규 PASS 합산 제외 |

50-A 성공을 Issue #50 전체 구현/통합 검증 완료로 해석하지 않는다. PR/Issue는 OPEN 유지하며 자동 Merge·브랜치 삭제·Close를 수행하지 않는다.
