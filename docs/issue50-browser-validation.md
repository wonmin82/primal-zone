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
- `viewport-1366.png`, `viewport-390.png`은 **리뷰용 증거**다. 최초 이미지를 승인 Visual Baseline으로 자동 채택하거나 주관적 UI 품질을 PASS로 판단하지 않는다(P-01).
- 실패 진단에는 마지막 명령·공개 상태 요약·URL·프레임 종류·Console 오류·스크린샷을 남긴다. 비밀값은 제거한다.
- 인증정보는 격리 실행 디렉터리의 접근 제한 임시 파일로만 전달하고 Node 종료 시 삭제한다. DB/secret 설정/인증 파일은 업로드하지 않는다.
- Trace/영상은 인증정보 및 향후 개인 메시지가 포함될 수 있어 **수집하지 않는다**. 일반 HTML Report는 인증 Trace를 내장하지 않는 escaped JSON 보고서다.
- 원본 결과는 `work/browser-e2e/run-*`, 업로드 가능 증거는 **정리·비밀 제거 이후에만** `work/browser-evidence/run-*`로 복사한다. 성공 Artifact 14일, 실패 30일. 성공하면 격리 DB/서버 디렉터리를 삭제하고 실패하면 로컬 진단 DB만 보존한다. 소유 프로세스는 양쪽 모두 종료한다.
- SIGTERM/Interrupt/서버 조기 종료/Node 실패/Timeout은 cleanup으로 귀결된다. 정상 종료가 실패할 때만 소유 PID/프로세스 그룹을 종료한다. 강제 OS 종료·Runner 자체 소실 시 Artifact 확보는 보장하지 않는다.
- 기존 `/favicon.ico` 404는 게임 실행과 무관한 비차단 HTTP 경고로 원 증거를 남긴다. 다른 Console 오류·JavaScript 오류는 실패한다. favicon 수정은 게임/화면 변경을 추가하지 않기 위해 이번 인프라 PR에 포함하지 않는다.

## 판정과 후속 범위

실제 실행 SHA·시간·실패 수정 이력은 [검증 매트릭스](issue50-integration-matrix.md), [실행 기록](playtest.md#issue-50-phase-50-a), [성능 기록](issue50-test-performance.md)에 남긴다. 최신 PR HEAD의 원격 CI URL과 최종 A-01~20 판정은 Issue #50의 Phase 50-A 진행 구역 및 연결 PR Validation에서 확정한다. 이전 SHA의 성공을 새 SHA의 결과로 대체하지 않는다.

한국어 OS IME는 사용자의 기존 Windows 수동 성공 **PRIOR VERIFIED**다. 신규 자동 PASS 수에 포함하지 않고 재검증을 요구하지 않는다. E2E-01~14, 전체 명령/Help 전수, 실제 Door 60초·리더 600초·서버 재시작·RELEASE는 후속 단계 **NOT RUN**이다.
