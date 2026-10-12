# Issue #50 실제 브라우저 검증 기록

## 2026-10-12 최초 성공 RELEASE 및 최종 Closeout 준비

[PR #60](https://github.com/wonmin82/primal-zone/pull/60)은 Merge Commit `855ada380e5276334f0744797a86a5aef300297c`으로 병합됐다. 첫 부모는 `82641de0ea66898676b0b29194d7918489443def`, 둘째 부모는 검토 Source `26da18221f890f3405aca84b746741e3da7f747b`이며 임시 병합 결과와 Tree가 같고 원본 이력이 보존됐다. [당시 main CI](https://github.com/wonmin82/primal-zone/actions/runs/38239786496)의 네 Job은 모두 SUCCESS다.

[최초 RELEASE 실패](https://github.com/wonmin82/primal-zone/actions/runs/38241057595)는 삭제하지 않는다. 8개 중 7개 Job은 SUCCESS였지만 Full Smoke가 60초 후 정상 닫힌 회복실 문을 열지 않고 이동해 실패했다. 이는 QA 이동 경로의 누락이며 게임의 차단은 정상이다. [최소 수정 PR #61](https://github.com/wonmin82/primal-zone/pull/61)의 `0a03b44612822796f703e4d077916330e909a4fb`는 실제 `회복실 문 열어`를 양쪽 이동 전에 실행한다. 정상·실패·비관련 출구 회귀3개를 추가했으며 게임 정책·타이머·프로토콜·저장 형식은 바꾸지 않았다. 수정 Merge는 `11a1c6bce91a5499292f8fbabff3e308663814fe`이고 부모는 `855ada380e5276334f0744797a86a5aef300297c`와 `0a03b44612822796f703e4d077916330e909a4fb`다.

**최초 성공 RELEASE SHA: `11a1c6bce91a5499292f8fbabff3e308663814fe`.** [main CI](https://github.com/wonmin82/primal-zone/actions/runs/38244636657) 네 Job SUCCESS, [RELEASE](https://github.com/wonmin82/primal-zone/actions/runs/38251167392) 8개 Job SUCCESS, main/workflow_dispatch/attempt1 및 입력·GITHUB_SHA·실제 Checkout SHA 일치를 모든 Job의 Guard8개로 확인했다. RELEASE 전체 병렬 경과는 819초다. Job 로그·Assertion 및 안전한 Artifact를 직접 검토했다. 아래 최초 실패/성공과 과거 로컬 검증을 서로 다른 실행으로 보존한다.

**최종 SHA Closeout은 아직 대기 중이다.** 이 문서 PR을 Merge Commit으로 병합한 뒤 새 `FINAL_MAIN_SHA`의 push CI 네 Job과 RELEASE8개 Job을 다시 실행한다. 같은 SHA의 성공으로 대체하지 않는다. 최종 실행 증거는 [Issue #50 공식 Final Closeout 기록](https://github.com/wonmin82/primal-zone/issues/50#issuecomment-6124806608)에 추가하고, 결과 때문에 새 Git Commit을 만들어 SHA를 다시 바꾸지 않는다. 최종 Gate를 확인한 뒤에만 #50·#45를 종료하고 병합된 작업 브랜치를 안전하게 정리한다.

### 최종 통합 브라우저 증거

Playwright1.64.0·Chromium156.0.8078.4·Node24·Python3.13·Evennia6.1·GitHub Ubuntu. 실제50-A9개+E2E14개=**23 PASS**. 독립 시나리오15개 Harness와 **46개 Context/Puppet 종료 관측**을 확인했다. 별도 실제 Timing2개는5개, Persistence2개는6개 종료 관측이다. 실패/Flaky/재시도0이며 플랫폼 전용 Runner1개 N/A는 성공 수에 더하지 않는다.

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

### 실제 시간과 정상 재시작

- TEST-TIMING-DOOR **PASS/100.737초**: 실제 열기/양방향OPEN·통과 완료 기준+60초·중복 열기/실패 통과 예약 불변·중간 관측·만료4초 전 이후 최대500ms 목표 반복·최종 `deadline-1.0 <= end <= deadline-0.5` 완료·만료후 실제 이동 거절·정상 Tick CLOSED·웹 양쪽 동기화. 단위 Clock 주입으로 대체하지 않았다.
- TEST-TIMING-PARTY **PASS/640.504초**: A 마지막 소유 Puppet 종료·실제 offline_since·B온라인·300초 부근/직전/최종 완료 창까지 A 유지·실제600초 이후 정상 Tick 승계·A재접속 권한 자동복원 없음·구성/전술/아이템/Claim 보존.
- 같은 RELEASE Helper의 Node 시간16개는30/58초 CLOSED·58초LOCKED·예약변경·300/598초승계·필수관측 누락/지연/조회오류를 실제로 거절한다. 조회 상한2초/최종 유효 창은 완화하지 않았고 누락 시FAIL이다. E2E11의599.999/600 서비스 주입과 실제 시간 검사를 별도로 기록한다.
- 독립 persistence 재검증 E2E12 **45.936초**, E2E13 **16.846초**: 실제 Exit 및 DoorInstallation·Profile/줄임말·Item UUID/장착/수량·Party·Quest/Credential·Native/Legacy/Claim·정상 만료와 데이터 손실 구분·상위 Rollback/알림 차단. 일반 Exit의 독립성도 비교한다.


### 안전성과 별도 검증 상태

시나리오/Job마다 새 marker·SQLite·동적 포트·합성 일반 계정·독립 Browser Context/실제 WS를 사용한다. 공개 증거의 run.json은 SHA·자격 증명 제거·Node/Chromium 및 Evennia 소유 프로세스 종료·플레이 DB 불변을 모두 true로 확인한다. observations의 모든 Context가 종료되고 소유 Puppet ID가 해제됐다. Artifact는 허용된 JSON/HTML·원문 비수집 로그 요약과 명시 마스킹 PNG2개만 포함하며 인증·개인 메시지·임의 입력·DB·원본 Snapshot·Trace/Video는 없다. 성공14일/실패30일 정책을 유지하고 실제 성공 Artifact의 만료 시각도 대조했다. 실패 원본 DB/로그는 운영 DB와 구분된 소유 로컬 경로에만 보존한다.

실제 플레이 DB의 SHA256은 `a33b102000a62dfe761fc8db5a90f1c4c4ffa012d9aec14a716c1d3784a592c3`이며 size/mtime/hash 불변이다. 운영 서버·운영 데이터 적용/마이그레이션은 수행하지 않았다. 신규 미해결 P0/P1은 없고 비차단 favicon P2는 [#59](https://github.com/wonmin82/primal-zone/issues/59)에서 OPEN 추적한다. #58은 변경하지 않았다. OS 한글 IME는 **PRIOR VERIFIED**, 최초 Visual Baseline은 **PENDING REVIEW**이며 객관적 DOM·접근성 PASS와 주관적 이미지 승인은 구분한다. Ubuntu는 실제 RELEASE, Windows는 보존된 실제 로컬 증거이며 macOS는 미지원/NOT RUN이다.


## 아래 기록의 시점

아래 기존 NOT RUN·PENDING·OPEN·Pre-merge 및 Phase 범위 표기는 해당 구현·리뷰 당시의 역사적 기록이다. 삭제하거나 새 SHA의 실행 결과로 재작성하지 않는다. 현재 결과와 최종 확인 절차는 위 기록 및 연결된 Final Closeout 기록을 따른다.

범위는 [v1.2 DESIGN FREEZE](https://github.com/wonmin82/primal-zone/issues/50)의 50-A 기반 구축이다. 50-B~50-F 및 E2E-01~14 전수 완료와 구분한다. 게임/콘텐츠/프로토콜/영속 모델은 변경하지 않는다.

## 실행 환경과 진입점

- `@playwright/test` **1.64.0**, `package-lock.json` 고정. 대응 Chromium **156.0.8078.4 / revision 1248**을 사용한다.
- Node **24 LTS**, Python **3.13**, Evennia **6.1.0**. 로컬 Windows, CI Ubuntu에서 같은 실행기를 사용한다.
- [공식 설치 안내](https://playwright.dev/docs/intro), [브라우저 버전·설치 계약](https://playwright.dev/docs/browsers), [Node LTS](https://nodejs.org/en/download)를 확인했다.

```bash
npm ci
npx playwright install --no-shell chromium
npm run test:browser
npm run test:contracts
```

CI는 `npx playwright install --with-deps --no-shell chromium`으로 OS 의존성까지 설치한다. `channel: chromium`의 실제 Chromium 새 headless 모드를 사용하며 별도 Headless Shell을 요구하지 않는다. Windows 설치 때 첫 CDN의 인증서 체인 오류가 발생한 기록은 보존한다. 공식 대체 CDN에서 받은 Chromium/FFmpeg/Winldd를 사용했고 TLS 검증을 끄지 않았다.

## 서버와 Fixture

`scripts/browser_e2e.py`는 기존 `smoke_harness.Harness('full')`을 그대로 사용한다. 새 서버 관리 엔진이나 RPC가 없다. 준비·migration·일반 계정·정적 파일 수집·동적 포트·HTTP/WS readiness·Portal/Server 시작/종료/재시작 책임은 Harness에 있다. `full`은 **production 타이머**이며 브라우저 QA를 위해 게임 시간을 단축하지 않는다. Full Gameplay Smoke 시나리오를 실행한다는 의미는 아니다.

초기 Fixture는 기존 `smoke_setup.py`의 검증가/검증나/검증다 3개 일반 Account·Explorer와 대기실 배치다. Fixture의 준비금·아이템 등 초기 조건과 실제 UI 행동을 구분한다. 테스트 중 상태를 덮어쓰지 않는다. 이후 역할·장소 준비가 필요하면 기존 Fixture/게임 명령을 이용하며 핵심 서비스는 실제 경로로 실행한다.

각 Player는 독립 `browser.newContext()`와 실제 WebSocket을 가진다. HTML/로그인 버튼/명령 입력/Enter/종료/재연결은 실제 DOM을 사용한다. 프레임은 관찰만 하며 `pz_auth` 내용을 기록하거나 변조하지 않는다. 로그인 완료는 인증 응답·초기 `pz_state`·사용자 이름·활성 입력창 모두로 판정한다. 명령은 실제 전송 횟수·`pz_log` 결과·새 서버 Prompt를 확인한다.

`scripts/browser_probe.py`는 marker와 격리 DB 경로를 검증한 뒤 SQLite `mode=ro`로 실제 `db_sessid`만 읽는다. 재접속 전 1 → 종료 후 0 → 새 세션 1과 ID 변경을 검사한다. DB 변경이나 게임 우회 API는 없다. 같은 Harness의 정상 `restart()`를 후속 50-D에서 재사용할 수 있지만 이번 단계에서는 서버 재시작 전수 검증을 실행하지 않는다.

## 화면·증거·보안

- Desktop **1366×768**, Narrow **390×844**: 입력/출력, 가로 overflow 없음, 핵심 버튼의 접근 가능한 이름을 확인한다. Narrow에서 탐사 수첩을 숨기는 기존 CSS 정책을 보존한다.
- `safe-viewport-1366.png`, `safe-viewport-390.png`은 로그·명령 입력·인증 UI를 마스킹한 **리뷰용 레이아웃 증거**다. 최초 구현 당시 `viewport-*.png` 기록은 아래 실행 이력에 보존한다. 승인 Visual Baseline이나 주관적 UI 품질 자동 PASS는 아니다(P-01).
- 진단은 Fixture A/B/C, 작업 분류·길이, 허용된 URL 경로, 상태 존재·Revision, 프레임 수·종료 여부와 안전한 오류 단계만 수집한다. 명령·채팅·개인/일행/NPC 자유 입력, 인증 프레임·임의 payload·URL query/인증정보·Console 오류 원문은 저장하지 않는다. 정확한 전송 비교를 위한 임시 입력 참조는 명령 완료/실패 시 제거한다.
- 인증정보는 marker로 검증한 격리 실행 디렉터리의 접근 제한 임시 파일로만 전달한다. 파일 생성부터 Node 생성·대기·종료까지 바깥 `finally`로 보호해 `Popen()` 실패 때도 삭제를 시도한다. 프로세스 정리와 파일 삭제는 독립적으로 실행하며 원래 오류와 정리 오류는 함께 전달한다. 삭제 실패는 실패이며 PASS로 기록하지 않는다.
- Trace/영상은 인증정보 및 향후 개인 메시지가 포함될 수 있어 **수집하지 않는다**. 일반 HTML Report는 인증 Trace를 내장하지 않는 escaped JSON 보고서다.
- 원본 결과는 `work/browser-e2e/run-*`에 있다. 잠근 Playwright 1.64.0의 `PLAYWRIGHT_NO_COPY_PROMPT=1`로 실패 DOM snapshot을 중지하고, 나머지 자동 `error-context.md`도 Reporter와 Python의 중단 정리 경로에서 폐기한다. 폐기 실패는 오류와 실패 상태로 전달한다. Playwright 업그레이드 시 이 비수집 경계를 다시 검증한다. 원본 서버/Node 로그는 업로드하지 않는다.
- 업로드 경계 `publish_evidence()`는 JSON을 안전 스키마로 재구성하고 escaped HTML을 만든다. 로그는 존재 여부/줄 수만 기록하고, 승인한 두 마스킹 PNG만 경로·파일명·PNG signature 검사 후 복사한다. Playwright 첨부의 40자리 digest 명명 규칙을 허용하되 임의 파일명/외부 경로는 제외한다. 임의 첨부·추가 이미지·DB/secret 설정/인증 파일은 기본 제외다. 비밀번호 치환은 추가 방어이며 비공개 메시지 제거 수단으로 간주하지 않는다.
- `work/browser-evidence/run-*`만 업로드한다. 성공 Artifact 14일, 실패 30일. 성공 시 격리 DB/서버 디렉터리를 삭제하고 실패 시 원본 로그/DB를 로컬 격리 디렉터리에 보존한다. 자격 증명 파일은 실패 때도 제거하고 소유 프로세스를 종료한다. 보존된 원본 DB/로그를 수동 업로드하지 않는다.
- SIGTERM/Interrupt/서버 조기 종료/Node 실패/Timeout은 cleanup으로 귀결된다. 정상 종료가 실패할 때만 소유 PID/프로세스 그룹을 종료한다. 강제 OS 종료·Runner 자체 소실 시 Artifact 확보는 보장하지 않는다.
- 기존 `/favicon.ico` 404는 비차단 `favicon-404` 분류만 남긴다. 다른 Console/JavaScript 오류는 계속 실패하며 자유 오류 원문은 수집하지 않는다. favicon 리소스 수정은 이번 범위 밖이다.

## PR #57 리뷰 보완의 세션 정리

`Player.login()`은 인증 전/후의 읽기 전용 Puppet ID 차이로 이번 Context가 만든 ID를 기록한다. `Player.close()`는 Context 종료 후 브라우저 채널 종료와 해당 ID의 실제 서버 해제를 유한한 조건 polling으로 확인한다. 다른 살아 있는 ID를 종료하거나 캐릭터 전체 세션 0을 공통 조건으로 강요하지 않는다. TEST-50A-06은 Desktop 정리 완료 후에만 Narrow를 생성한다.

Context 종료 뒤 Playwright가 WebSocket close 이벤트를 전달하지 않을 수 있다. 따라서 브라우저 종료는 close 이벤트 또는 닫힌 Page로 확인하되, 실제 Puppet 해제는 별도 Probe로 확인한다. 진단의 `contextClosed`, socket `closed`, `detached`는 각기 브라우저 채널·관측 이벤트·서버 해제 결과이며 서로 대신하지 않는다. 기존 재접속은 실제 WebSocket close 이벤트 및 Puppet 1→0→1·새 ID를 계속 검사한다.

`finishActors()`는 한 Context의 정리나 진단/첨부가 실패해도 모든 Context의 정리를 시도하며 실패를 AggregateError로 전달한다. TEST-P2-02-D/03-D의 예상된 Assertion·첨부·Probe·Timeout 실패는 명시적인 음성 회귀이며 실제 게임 수령/인증을 Mock으로 대체하지 않는다. 임의 실패 화면의 스크린샷은 수집하지 않고 안전한 실패 메타데이터만 보존한다. 상세 추적과 실제 결과는 [리뷰 보완 표](issue50-integration-matrix.md#pr-57-리뷰-보완)를 따른다.

실제 실패 경계를 확인하는 별도 로컬 실행은 `PRIMAL_BROWSER_FAILURE_PROBE=1` 환경에서 `npm run test:browser`를 실행한다. PowerShell에서는 `$env:PRIMAL_BROWSER_FAILURE_PROBE='1'`을 설정하고 `finally`에서 해당 환경 변수를 제거한다. **Assertion 실패 1개와 종료 코드 1이 예상 결과**이며 일반 E2E 성공으로 합산하지 않는다. 기본 실행과 CI는 해당 옵션 없이 TEST-50A-01~06 및 신규 P2 3개를 모두 실행한다. 세션 정리 실패를 재시도만으로 숨기지 않으며 Playwright retries는 0이다.

## 판정과 후속 범위

실제 실행 SHA·시간·실패 수정 이력은 [검증 매트릭스](issue50-integration-matrix.md), [실행 기록](playtest.md#issue-50-phase-50-a), [성능 기록](issue50-test-performance.md)에 남긴다. 최신 PR HEAD의 원격 CI URL과 최종 A-01~20 판정은 Issue #50의 Phase 50-A 진행 구역 및 연결 PR Validation에서 확정한다. 이전 SHA의 성공을 새 SHA의 결과로 대체하지 않는다.

한국어 OS IME는 사용자의 기존 Windows 수동 성공 **PRIOR VERIFIED**다. 신규 자동 PASS 수에 포함하지 않고 재검증을 요구하지 않는다. E2E-01~14, 전체 명령/Help 전수, 실제 Door 60초·리더 600초·서버 재시작·RELEASE는 후속 단계 **NOT RUN**이다.


## P2-04 — 소유 브라우저 프로세스 트리 정리

이전 리뷰 HEAD `9651918018517527cdfa96fb694ab09bc66f298e`에서 `stop_browser()`는 부모 `poll()` 종료를 이유로 즉시 반환했다. Windows 격리 Python 부모가 종료 코드 2로 먼저 끝난 뒤 실제 자식이 STILL_ACTIVE인 상태를 재현했으며, 기존 정리를 호출한 뒤에도 자식이 남았다. 운영 발생 빈도나 정상 CI의 Chromium 잔류를 확인한 것으로 과장하지 않는다.

`scripts/browser_processes.py`의 `OwnedBrowser`가 소유 수명만 관리한다. 새 게임 서버/큐/프로토콜이 아니다. 보호 프로세스는 표준 라이브러리만 필요하므로 Windows venv 런처 대신 `sys._base_executable`을 직접 사용한다. 자식 시작 전 `.ready`로 소유권 확정을 확인하고 원본 실행 결과는 비공개 격리 디렉터리의 숫자 종료 코드로 전달한다. 기존 결과/ready 파일을 소유 증거로 재사용하지 않는다.

- Windows: 실행기가 UUID Job 핸들을 만들고 kill-on-close를 설정한다. 보호 프로세스가 자신을 Job에 먼저 등록한 후 임시 Job 핸들을 닫고 Node를 생성한다. 자식은 Job을 상속하며 breakaway를 허용하지 않는다. 부모 Node/보호 프로세스가 이미 종료됐어도 Job active count를 확인한다. 가능하면 CTRL_BREAK로 정상 종료를 요청하고, 잔류 Job만 TerminateJobObject로 종료한 뒤 active count 0을 확인한다. 마지막 Job 핸들은 실행기만 보유한다. Job 등록 실패 시 자식을 만들지 않고 실패한다. 기존 외부 Job과 양립할 수 없는 환경에서는 검증을 우회하지 않는다.
- Linux/POSIX: `start_new_session=True`의 보호 프로세스가 PGID를 유지한다. 다만 Playwright 1.64.0은 Chromium을 별도 detached 그룹으로 실행하므로 Node 그룹 종료만으로는 충분하지 않다. 자식 생성 전에 Linux PR_SET_CHILD_SUBREAPER를 설정하고, Node 종료 뒤 보호 프로세스가 입양한 실제 자식을 /proc의 커널 부모 관계로 확인한다. 각 자식의 pidfd를 열어 소유 부모를 재확인한 뒤 그 핸들에만 SIGTERM/필요 시 SIGKILL을 보낸다. 이후 입양되는 하위 자식까지 종료·reap하고 정리 증거를 기록해야 보호 프로세스가 종료한다. 외부 PGID나 미확인 PID에 신호를 보내지 않고 PID 재사용에 의존하지 않는다. PID/명령행/환경은 Artifact에 포함하지 않는다. 보호 프로세스 소실로 소유 증거를 잃으면 실패한다. macOS는 같은 입양/pidfd 보증을 검증할 환경이 없어 현재 실행기가 명시적으로 차단하며 지원 완료를 주장하지 않는다.
- `browser_processes_stopped`는 Node/Chromium을 포함한 위 소유 컨테이너의 실제 정리 완료다. 기존 `processes_stopped`는 Evennia Portal/Server 결과다. 부모 종료 코드만으로 둘을 대신하지 않으며 어느 정리가 미완료여도 전체 실행은 실패한다. P2-01의 인증 파일 삭제와 원래 오류+cleanup 오류 보존, P2-02의 비수집/허용목록, P2-03의 Puppet 해제는 유지한다.

근거: [Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects), [Python subprocess](https://docs.python.org/3.13/library/subprocess.html), [Python pidfd](https://docs.python.org/3.13/library/os.html#os.pidfd_open). Windows 실제 OS 회귀와 Chromium은 로컬에서, Linux 실제 detached 자식·pidfd 회귀와 Chromium은 기존 Ubuntu browser-e2e Job에서 확인한다. macOS 실행 환경이 없어 **NOT RUN**이며 macOS 지원 검증 완료라고 주장하지 않는다. 외부 Chromium/Node/Evennia의 이름이나 미확인 PID를 종료하지 않는다.

Linux의 Node 실행 시작 실패 시 자식 없음 증거를 기록한 보호 프로세스가 먼저 종료할 수 있다. 이미 검증된 정리 증거가 있으면 닫힌 파이프에 종료 요청을 보내지 않는다. BrokenPipe가 발생한 경우에도 보호 프로세스 종료·실제 `.clean`의 stopped=true를 확인한 경우만 정리 완료로 인정한다. 증거 없이 부모 종료만 확인된 경우는 실패다. 전체 Runner는 이 경계 추가 후 24개이며 과거 23개 기록은 보존한다.
# Phase 50-B~F 준비의 브라우저 확장

## 실행 구조와 범위

`npm run test:browser`는 기존50-A9개를 유지한다. `npm run test:browser:integration`은 새 E2E-01~14를 시나리오별 새 DB/서버에서 순차 실행한다. Playwright1.64.0/Chromium156.0.8078.4·Node24 LTS·Python3.13, Windows/Linux 소유 프로세스 수명 보호는 그대로다. macOS는 기존 명시적 미지원/NOT RUN을 유지한다.

실제 UI 인증·Enter·NPC 버튼 키보드/클릭·이동 버튼·독립2~3 Context·실제 WebSocket·재접속을 사용한다. 초기Fixture/읽기 전용 DB Probe/정상 Harness restart/시각 및 상위 rollback 주입은 [E2E 문서](issue50-e2e-validation.md)에 구분한다. Actor Context 종료 후 해당 소유 Puppet ID의 실제 해제를 계속 확인한다.

## WEB 요구 연결

| ID | 검증 책임 | 실제 위치 | 현재 판정 |
| --- | --- | --- | --- |
| T50-WEB-01 | Chromium·HTTP·WS·실제 인증 | TEST-50A-01/03, 모든 E2E actors.create | 개발 성공, 최종 CI 미확정 |
| T50-WEB-02 | 입력/Enter·정확한 한 번 전송 | TEST-50A-02, E2E-01/14, Player.command | 개발 성공, 전체 미확정 |
| T50-WEB-03 | History·Backspace·실제 clipboard paste | E2E-14 | NOT RUN (최종 결과 미확정) |
| T50-WEB-04 | 실제 버튼·명령과 동일 서버 경로 | E2E-02 NPC selection·E2E-04 Exit 버튼·Node 기존 Action 계약 | 개별 개발 성공, 최종 코드 재확인 필요 |
| T50-WEB-05 | Prompt·비동기 WS 상태 | E2E-06/08/14·기존 Prompt 계약 | 개별 개발 성공, 최종 전체 필요 |
| T50-WEB-06 | Desktop1366×768 | TEST-50A-06/E2E-14 | 기존 증거 보존, 새 전체 결과 미확정 |
| T50-WEB-07 | Narrow390×844·overflow/viewport | TEST-50A-06/E2E-14 | 기존 증거 보존, 새 전체 결과 미확정 |
| T50-WEB-08 | Focus·이름·키보드·hit-test | E2E-02/14·TEST-50A-06 | NOT RUN (최종 결과 미확정) |
| T50-WEB-09 | 개인 활성 키워드·중복 보상 방지 | E2E-02, NPCDialogueTests·Node 키워드 계약 | Python/Node PASS, 새 전체 Chromium 미확정 |
| T50-WEB-10 | 독립 Context/계정·수신 범위 | E2E-05/06/07/08/11 | 개별 개발 성공, 최종 전체 필요 |
| T50-WEB-11 | Console/HTML/Semantic Text | 기존50-A·E2E-05/14·Node27개 | Node PASS, 실제 전체 미확정 |
| T50-WEB-12 | 재접속·세션·안전한 증거 | E2E-11/12·P2회귀·엄격한 export | Runner PASS, 실제 재시작 조사/전체 미확정 |

이 표의 미확정 항목을 예상 PASS로 처리하지 않는다. 최종 실행 SHA·CI·개수·시간은 통합 매트릭스와 최종 PR Validation에서 실제 결과로 갱신한다. IME는 **PRIOR VERIFIED**, 새 수동 검사 없음. 시각 기준 이미지는 **PENDING REVIEW**, 구조적 Assertion이 주관적 UI 승인을 대신하지 않는다.

## 발견한 테스트 인프라 결함

긴 실제 사용자 흐름에서 기존 Player Fixture가60초 `idle` keepalive를 사용자 명령으로 세어 횟수·원문 비교를 덮었다. E2E-02에서 실제 실패를 재현하고 `isCommandFrame`으로 transport keepalive와 사용자 제출을 분리했다. 운영 keepalive/타이머/프로토콜을 수정하지 않았다. Node 음성 경계와 실제60초를 넘는 Quest 흐름으로 보완을 확인했다.

인증/개인·일행/자유 입력·clipboard 원문·임의 WS Payload·Snapshot·Trace/Video·자동 오류 DOM은 수집하지 않는다. clipboard는 테스트가 쓴 값이 그대로 남아 있을 때만 원래 값으로 복원한다. 최초 실패의 Popen/Job/subreaper/Puppet/인증 제거 보호는 유지한다. 서버 복사본의 failure/clock Hook은 PRIMAL_SMOKE 경로 검사를 통과한 실행에만 설치한다.


## 최종 로컬 제출 검증 (원격 CI 전)

순수229/통합814 PASS, 기존50-A9 + 실제E2E01~14 PASS. Runner Windows23(정의24/POSIX1 N/A)+신규6, Harness18, Node28 PASS. 실행 SHA/개발 diff와 실제 개별 시간은 통합 매트릭스에 구분했다. 후속 NPC 역할 보강3개는83.015/152.005/92.905초, 정상 restart의 만료 sweep 분류 보강은128.467초 PASS다. 이는 원격 최신HEAD/RELEASE 실행 성공을 의미하지 않는다.

이 문서 앞의 미확정/초기 실행 기록은 개발 당시 이력이다. 현재 로컬 WEB01~12 기능 수용은 PASS이며 정확한 최종 Push HEAD Quick 및 네 GitHub Job은 PR/Issue50에서 새로 확정한다. 실제60/600/Full/최종main RELEASE는 NOT RUN, IME PRIOR VERIFIED, 이미지 PENDING REVIEW 유지. 비차단 favicon은 [후속P2 #59](https://github.com/wonmin82/primal-zone/issues/59)에 이관했다.


## PR #60 리뷰 보완 관측 경계

실제 Windows Chromium E2E08 151.801초, E2E11 141.538초, E2E12 보완 후143.987초(각 격리 준비~정리) PASS. 기준은 리뷰HEAD d7736c54 + 해당 개발diff이며 커밋 이후 새 실행으로 표현하지 않는다. E2E08은 OPEN 당시 실제 이동 버튼 HTMLElement를 보관한다. B의 실제 닫기 후 최신 버튼이 disabled이고, 교체돼 detached인 이전 버튼만 QA 소유 컨테이너에 재연결해 실제 click → 기존 document 이벤트 → text WS → 실제 서버로 보낸다. 게임 상태를 mock하거나 새 RPC를 쓰지 않는다. A의 위치/admin Door 상태/예약 불변과 이후 최신 정상 이동 버튼의 성공을 모두 검사한다.

E2E12는 실제 ObjectDB의 전체 Exit PK/Location/Destination/Typeclass/key/관리 태그/Door Attribute와 설치 원본을 재시작 전후 정확히 비교한다. 정상 만료 sweep은 Door state/예약에만 허용하고 Exit 변경은 허용하지 않는다. 정적 routes는 이동 계획 전용이다. Probe는 기존 소유 DB 검증과 query_only를 유지하며 원본 Snapshot을 Artifact로 보내지 않는다.

RELEASE 관측: wall clock Date.now와 저장 deadline을 사용하고 조회 소요는 monotonic performance.now로 확인한다. 최대5초 간격으로 만료 전 상태를 관측하며 중간30/300초 이후와 예약4초 전부터의 직전 관측을 필수로 한다. Probe2초 상한, 관측 완료가 만료0.5초 전까지여야 하며 누락/지연은 FAIL이다. 정상 Tick 후 확인 상한8초는 5초 Tick+2초 Probe+1초 scheduling 여유다. 실제 통과 요청~응답 창 안에 예약-60초가 있어야 한다(시계 정밀도0.1초 허용). 오프라인 시작도 마지막 Puppet 종료 요청~완료 시각에 대조한다. 운영 타이머는 바꾸지 않는다.

30/300초 조기 실행·늦은 관측은 별도 음성 회귀로 거절한다. 주입시각 E2E11와 이 순수 관측 검출 검사를 실제 RELEASE Wall Clock PASS로 합산하지 않는다. 실제60/600은 NOT RUN. IME PRIOR VERIFIED, Visual Baseline PENDING REVIEW, macOS 기존 미지원 유지. P2-01~04 자격 증명/증거/Puppet/프로세스 보호는 유지한다.


## PR #60 P2-03 — 최종 시간 경계 관측 보완

리뷰 기준 `5193aa2fd3232976eecf2a0f362cd4ec3e013fb5`, 수정 코드 `653340465930e9782a80aa6dde9154fddd71455a`, Base `82641de0ea66898676b0b29194d7918489443def`. 기존 4건 리뷰/실패/성공 이력은 당시 기록으로 보존한다. 이 보완은 게임·운영 타이머·프로토콜·영속 형식을 변경하지 않는다. 최종 문서 포함 Source HEAD의 Quick/새 네 CI는 실제 완료 후 [PR #60](https://github.com/wonmin82/primal-zone/pull/60)과 [Issue #50](https://github.com/wonmin82/primal-zone/issues/50)에 기록한다. 이 문서 커밋 시점에는 해당 게이트 PENDING이다.

`review-contracts.cjs::monitorBeforeDeadline()`은 더 이상 만료4초 전에 반환하지 않는다. 시작~중간~만료4초 전은 최대5초, 마지막 구간은 최대500ms의 시작 간격을 목표로 하며 직전 monotonic 조회 비용을 대기에서 뺀다. 조회가500ms보다 오래 걸리면 추가 대기 없이 다음 조회를 시작한다. 개별 조회 전체 비용 상한은 기존2,000ms다. 스케줄러 지연·2초 초과 조회·서버/세션 오류·필수 체크포인트 누락은 FAIL이며 창을 넓히거나 재시도로 숨기지 않는다.

중간 완료는 중간 시각부터7초 이내(5초 간격+최대2초 조회), 직전 반복 관측은 만료4~2초 전 구간에 실제 조회가 완료되어야 한다. **최종 유효 창은 `deadline - 1.0 <= observation.end <= deadline - 0.5`**다. 완료를 만료0.75초 전으로 맞추도록 직전 조회 비용을 고려한다. 관측 시작만 유효하거나 만료 직전 조회가 늦게 완료된 경우는 실패한다. 반환하는 `middleSeen/nearSeen/finalSeen`은 상태 원문을 포함하지 않으며 두 RELEASE 시나리오가 세 값 모두 true를 요구한다.

`integration_probe.py --timing`은 소유 경로/marker/명시 DB 검사를 거친 후 SQLite `mode=ro`·`query_only`·읽기 트랜잭션으로 실제 Door/일행/위치/Puppet/아이템/Claim을 읽는다. Attribute는 현재 내장 데이터만 복원하며 전역 객체/global·중복/소실은 거절한다. 기존 전체 Snapshot의 실제 Exit/설치/Room 영속 검사는 그대로 유지한다. 시간 검사와 E2E-11의 실제 DB projection 대조만 이 경량 조회를 사용한다. 원본 Snapshot/DB·사용자 입력·인증정보는 Artifact에 포함하지 않는다.

- 수정 전58초 CLOSED/598초 승계 음성2개는 `Missing expected rejection`으로 FAIL(0.149초)하여 기존 관측 공백을 재현했다. 수정 후 같은 Helper의 P203-01~12와 추가 중간/직전 누락을 모두 거절/수용한다. 기존30초/300초·2초 조회 지연 회귀를 유지한다.
- 최종 Node 계약 **52 PASS/0.399초**, 기존43+신규9, fail/skip0. 시간 회귀16개와 Exit 회귀8개, 기존 웹/보호28개를 포함한다. Python 통합 Runner **9 PASS/2.393초**, 기존8+실제 SQLite projection/해시·mtime 비변경·손상 거절1개. 기존 Browser Runner Windows23 PASS·POSIX1 N/A/5.724초(정의24).
- 실제 Chromium E2E-11 **PASS/80.126초**, 서버 준비~정리119.703초(명령 진입점 전체120.619초). 실제599.999/600 서비스 주입·재접속·projection과 정상 실제 DB·소유 Puppet3관측 해제 확인. Node/Chromium/Evennia 종료·인증 삭제·성공DB 삭제·실제 플레이DB hash/mtime/size 불변 true.
- `npm run test:browser:timing`→TIMING-DOOR/PARTY→동일 관측 Helper 연결 및 RELEASE Workflow 호출을 Runner가 확인했다. 정상/조기 회귀는 주입 Clock 검증이며 **실제60초/600초 Wall Clock PASS로 합산하지 않는다**.
- check·변경JS 구문·diff PASS. 게임/Python 전체 구현 및 의존성은 변경하지 않았다. 기존 로컬 전체229/816 성공(이전 리뷰 SHA의 기록)을 새 실행으로 표현하지 않고, 이번 직접 영향 QA 회귀와 새 HEAD의 원격 전체 Suite로 확인한다.

RF-33~46은 관측 구현/검출 회귀/실제 서비스 주입/RELEASE 연결/안전성으로 확인한다. RF-47~50 최종 Quick·새 네 CI·기록·차단 결함 감사는 실제 완료 후 PR/Issue에서 확정한다. RF-51~52: **실제 Door60초·리더600초 RELEASE NOT RUN**, PR60 OPEN/Ready·Source 유지·Issue50/45 OPEN. G-12 Full·G-14 최종main CI/RELEASE·G-15 FinalCloseout NOT RUN, IME PRIOR VERIFIED, Visual Baseline PENDING REVIEW, Issue58 비범위, 기존 favicon P2 #59 추적 유지. Merge/브랜치 삭제/Issue Close는 수행하지 않는다.
