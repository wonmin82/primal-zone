# Issue #50 Phase 50-A 실제 브라우저 검증

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
