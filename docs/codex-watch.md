# Codex 비동기 검사 감시기

`scripts/codex_wait.py`는 기존 `scripts/dev.py`의 로컬 검사 또는 고정 GitHub Actions Run을 독립 Python Worker에 맡긴다. 요청별 파일을 먼저 보존하고 지원되는 Codex 세션에 메타데이터 완료 알림을 한 번 전달한다. 상주 데몬·OS 스케줄러·새 패키지를 사용하지 않는다. Windows는 Job Object, Linux는 소유 자손 추적, macOS는 Process Group과 짧은 Supervisor 경계를 사용한다. 구현 여부와 OS별 실검증 여부는 구분하며, macOS 실환경 검증은 아직 수행하지 않았다.

## 실행

저장소 루트에서 프로젝트 Python으로 실행한다. Windows의 `.\.venv\Scripts\python.exe` 또는 Linux/macOS의 `./.venv/bin/python`으로 `uv run python`을 대체할 수 있다. 로컬 자식도 현재 `sys.executable`을 사용한다.

```text
uv run python scripts/codex_wait.py local --thread THREAD_ID --parallel 4
uv run python scripts/codex_wait.py local --command test tests.test_targets --parallel 1
uv run python scripts/codex_wait.py local --command smoke --thread THREAD_ID
uv run python scripts/codex_wait.py local --command smoke-full --timeout 2700
uv run python scripts/codex_wait.py ci --thread THREAD_ID --repo wonmin82/primal-zone --run-id RUN_ID --sha FULL_SHA --attempt 1 --pr PR_NUMBER
uv run python scripts/codex_wait.py status JOB_ID
uv run python scripts/codex_wait.py cancel JOB_ID
```

`THREAD_ID`는 실제 세션 UUID 또는 정확한 세션 이름이다. 다른 사람의 세션을 지정하지 않는다. 알림이 필요 없으면 `--thread`를 생략하고 완료 후 `status`로 복구한다. 로컬 모드 기본 검사는 `test`이며 label·`--parallel`·`--reverse`는 기존 dev.py의 test 인자로만 전달한다. 임의 Shell 문자열이나 다른 dev.py 명령은 실행하지 않는다.

기본 제한은 test30분·smoke15분·smoke-full45분·CI45분이며 CI `--release`는 대기 제한만90분으로 정한다. Release Workflow를 실행하지 않는다. `--timeout`은 초 단위다. 부모는 기본5초(`--ready-timeout`) 안에 Worker의 실제 READY를 확인한 뒤 Job ID를 반환한다. 프로세스 생성만 성공한 상태를 READY로 간주하지 않는다. READY 뒤 검사 시작 실패는 별도 ERROR 결과다.

## 결과와 유효성

기존에 Git에서 제외된 `work/codex-watch/JOB_ID/`에 다음을 보존한다. 이 경로의 파일을 Commit하거나 다른 작업의 파일을 정리하지 않는다.

| 파일 | 내용 |
| --- | --- |
| request.json | 검사 설정·검증 대상·Git 기준 정보 |
| state.json | Worker 식별 정보·준비 상태·현재 상태 |
| result.json | 최종 상태·원래 종료 코드·실행시간·유효성 |
| output.log | 로컬 검사 또는 CI 감시 출력 |
| notification.json | 알림 요청/지원/전달 시도 결과 |

READY 이전의 독립 생존 확인을 위한 `launch.json`과 실행별 Supervisor 제어 파일도 같은 소유 Job 디렉터리 안에 둔다. 이 내부 메타데이터를 최종 검사 성공 근거로 대신 사용하거나 다른 Job으로 옮기지 않는다.

JSON은 임시 파일을 작성한 뒤 원자적으로 교체한다. 결과를 저장한 뒤 알림을 시도한다. 검사의 성공과 알림 성공은 별개다. 상태는 `STARTING`, `RUNNING`, `PASSED`, `FAILED`, `CANCELLED`, `TIMED_OUT`, `STALE`, `INTERRUPTED`, `ERROR`다.

로컬 기준은 저장소 경로·브랜치·HEAD SHA·검사 인자·관련 Git 추적 및 미추적 소스/설정 Fingerprint다. 비밀 파일·플레이 DB·로그 내용은 Fingerprint에서 제외한다. 종료 시 코드가 달라졌다면 원래 종료 코드/검사 결과를 보존하고 STALE로 표시하므로 현재 코드의 성공 근거로 사용하지 않는다. 같은 검증 대상·설정의 활성 작업은 원자 등록으로 중복 시작을 막는다. 설정·대상이 다른 검사는 별도 Job이다.

CI는 고정 Run ID와 SHA, Attempt를 시작·종료 양쪽에서 확인하고 `--pr` 지정 시 현재 PR HEAD도 비교한다. `gh run watch`의 종료 코드만으로 성공을 선언하지 않고 최종 Run 상태를 다시 조회한다. Attempt나 PR HEAD가 바뀌면 이전 성공은 STALE다. 조회 오류는 ERROR, 실제 CI 실패는 FAILED, 원격 취소는 CANCELLED로 구분한다. **한 Run의 성공은 PR의 필수 체크 전체 성공이 아니다.** PR 소스·선택된 Run/Attempt 및 필요한 Job 전체를 별도로 확인한다.

`--attempt`를 생략하면 입력 검증 단계에서 짧은 `gh run view`로 현재 Attempt를 한 번 고정한다. 이 사전 조회(최대10초)는 Job의5초 READY 대기와 별도이며, 조회 실패는 접수 전 ERROR다. 사전 조회 CLI가 별도 세션 자손을 만드는 동작은 실환경에서 관측하지 않았고, 이 경로의 임의 자손까지 정리된다는 보장은 하지 않는다. 확정 Attempt를 알고 있으면 명시하여 이 조회를 생략한다. 등록된 Worker의 검사/CI 대기·취소 소유권 검증과 이 짧은 입력 조회를 구분한다.

## 취소·복구·플랫폼 경계

`cancel JOB_ID`는 소유 Worker에 취소를 요청한다. 로컬 작업은 소유 프로세스 트리/그룹을 정리하고 자식 잔존 여부를 확인한다. Windows의 부모 프로세스만 종료한 것을 자식 정리 성공으로 취급하지 않는다. CI 취소는 로컬 감시만 멈추며 원격 Actions Run을 취소하지 않는다.

`status`는 RUNNING 파일만 믿지 않고 Worker PID와 OS 시작 식별 정보, 최종 결과의 존재 여부를 확인한다. READY 이전 비정상 종료도 INTERRUPTED 또는 원인에 맞는 ERROR로 구분하고, 실제 준비 지연만 TIMED_OUT으로 처리한다. 이미 작성된 최종 결과를 READY 대기 판단보다 우선하며 부모의 제한시간 처리가 이를 덮어쓰지 않도록 한다. 손상 JSON이나 PID 재사용을 PASSED로 간주하지 않는다. 실패/중단 로그를 보존한 뒤 원인을 확인하고, 기존 활성 Job을 확인하지 않은 채 같은 검사를 다시 실행하지 않는다.

CLI의 STARTING/RUNNING은 접수·대기 상태이고 검사 성공이 아니다. 최종 PASSED만 성공으로 채택하며 FAILED/STALE/INTERRUPTED/ERROR/CANCELLED/TIMED_OUT은 성공으로 처리하지 않는다. 원래 검사의 종료 코드는 result.json에서 별도로 확인한다. 알림이 늦거나 실패해도 결과를 다시 실행하거나 Queue를 재전송하지 않고 `status`로 읽는다.

`status` 등 CLI는 STARTING/RUNNING/PASSED에0, 실패·취소·Timeout·STALE·INTERRUPTED·ERROR에1을 반환한다. 시작 명령의0도 아직 검사를 완료했다는 뜻이 아니므로 반환된 READY·Job ID와 최종 결과를 구분한다.

손상 JSON은 신뢰할 수 있는 기존 사본과 로그를 보존해 진단하며 PASSED 필드를 수동으로 만들어 복구하지 않는다. 비정상 종료로 소유 자식 정리를 확인할 수 없는 활성 등록은 자동 해제하지 않는다. 저장된 PID/시작 식별 정보와 실제 소유 프로세스 종료를 운영자가 확인한 뒤에만 해당 Job의 `request.json`에 기록된 key와 일치하는 `.active-KEY.json` 등록 하나를 별도 보존·정리하고 재요청한다. 기존 Job 디렉터리와 다른 key·Job·프로세스는 유지한다. 정리를 확인할 수 없으면 INTERRUPTED/ERROR 상태를 그대로 두고 추가 실행을 보류한다.

Windows와 POSIX는 별도 소유 프로세스 정리 경계를 사용한다. 실제 검증하지 않은 OS는 아래 결과에서 NOT RUN으로 표시한다. 앱 종료·샌드박스 정리·로그아웃·재부팅 이후 Worker 생존이나 자동 복구를 보장하지 않는다. 강제 종료·시스템 장애 뒤에는 `status`로 복구하고 소유권을 확인할 수 없는 다른 PID·서버·Worktree는 종료하지 않는다.

기존 Smoke는 POSIX에서 Portal/Server를 별도 세션으로 시작한다. 부모 프로세스 그룹이 비었다는 사실만으로 해당 자손까지 정리됐다고 판단하지 않는다. 권한·샌드박스 제약으로 소유 프로세스 경계를 구성하거나 정리 결과를 확인할 수 없으면 오류로 남기며 다른 서버를 대상으로 광범위한 종료 명령을 사용하지 않는다.

### macOS A안 — Process Group과 Smoke 실행 경계

사후 `ps` ancestry 조회만으로는 빠르게 종료한 중간 부모가 만든 별도 세션 자손을 놓칠 수 있다. Apple의 [XNU event.h](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/event.h)는 NOTE_TRACK/NOTE_CHILD/NOTE_TRACKERR가10.5이후 미지원임을 명시하므로 FreeBSD의 기능을 macOS 지원으로 가정하지 않는다.

최초 구현은 사용자 승인에 따라 macOS 검사를 시작 전에 ERROR로 제한했다. 이번 PR 보완에서는 사용자가 지정한 A안으로 이를 대체한다. 일반 로컬 검사, Quick/Full Smoke, CI와 Queue의 외부 명령은 감시기가 만든 독립 Session/Process Group의 최소 Supervisor 경계에서 실행한다. 검사 프로세스가 먼저 끝나도 Supervisor를 유지해 저장된 PGID만 믿고 종료하지 않으며, 현재 소유권과 잔여 프로세스 및 정리 완료를 확인한 뒤 결과를 기록한다. Worker 자신과 다른 작업의 프로세스 그룹을 종료하지 않는다.

Smoke의 Portal/Server는 **macOS에서 watcher가 만든 실행 경계와 현재 Session·Process Group이 실제로 일치하는 경우에만** 검사 그룹을 상속한다. 환경변수의 존재만으로 적용하지 않는다. 일반 `scripts/dev.py smoke`는 기존대로 Portal/Server를 별도 Session으로 시작한다. 그룹 상속 모드에서는 개별 Portal/Server PID를 PGID로 사용하지 않으며, 소유 프로세스에 대한 개별 종료와 Supervisor의 최종 그룹 정리를 구분한다. 정상 종료와 재시작은 기존 Evennia 공식 종료 절차를 유지한다.

정상/실패 종료, Timeout과 Cancel에서 종료 코드와 소유 그룹 정리 결과를 각각 확인한다. 그룹 정리는 실행 중인 비-zombie 멤버가 없는지 확인하고 직접 생성한 자식은 wait로 회수한다. 소유권·잔여 프로세스·종료 코드를 확인할 수 없거나 예상하지 못한 Session 이탈이 관측되면 ERROR로 처리하고 추정 PID/PGID를 종료하지 않는다. 임의의 악의적 daemon을 격리하는 범용 Sandbox는 아니며 알려진 Primal Zone 검사 경로를 대상으로 한다. 별도 Linux/macOS 실환경 검증은 이번 보완 범위에서 수행하지 않으며, Mock 통과를 macOS 실환경 PASS로 표현하지 않는다.

## Codex Queue

런타임에 `codex queue --help`로 `--thread`/`--message` 구문 지원을 확인한다. 미설치/미지원은 UNSUPPORTED, 전송 실패는 FAILED, 종료 코드0은 ACCEPTED_UNCONFIRMED다. 알림을 요청하지 않으면 NOT_REQUESTED다. 같은 완료 알림을 반복 자동 발송하지 않는다.

알림에는 Job ID·상태·종료 코드·실행시간·결과 파일 경로만 포함한다. 테스트 출력과 외부 CI 로그를 Codex 지시문에 복사하지 않는다. **결과 저장 성공, Queue 명령 성공, 실제 세션 재개는 세 가지 다른 사실이다.** 실제 턴 재개를 관측하지 못하면 UNVERIFIED로 남긴다. 자동 재개가 지원되지 않아도 `status`와 결과 파일은 정식 완료 확인 경로다. 완료 알림은 추가 실행·Merge·Issue 종료 승인이 아니다.

## 검증

```text
python -m unittest discover -s scripts/tests -p test_codex_wait.py
python scripts/dev.py check
```

T01~T06은 짧은 자식과 가짜 CLI/Mock을 사용하며 실제 Evennia 서버·새 GitHub Run을 만들지 않는다. 구현기 검증을 이유로 로컬 게임 전체·Smoke·브라우저를 반복 실행하지 않는다. 기존 필수 CI의 `contracts` Job에서 Python 3.13 `uv sync` 이후 전용 테스트 Step 하나를 실행한다. 새 Job이나 Workflow를 만들거나 기존 검사를 축소하지 않는다. Ubuntu CI가 수행한 자동 회귀와 별도 Linux/macOS 수동 실환경 검증을 구분한다. OS 기능에 의존하는 조건부 미실행 항목은 그대로 보고하며, 실제 Queue 전달과 실제 세션 재개도 구분한다. 모델 호출/토큰 감소량은 관측하지 않은 수치를 실측으로 주장하지 않는다.

구현 착수 환경은 Windows Native/Python3.13.15, gh2.97.0, codex-cli0.164.0이다. 이 gh는 `run view --json`의 `attempt`와 `run watch --exit-status`를 제공하며 실제 Codex 도움말은 `queue --thread --message`를 제공했다. 설치 버전의 구문 확인과 실제 알림 전달은 다른 검사다. Linux 실행 환경은 WSL 서비스 불가, macOS 실행 환경도 없어 실환경 검증은 NOT RUN이다. 이 한계를 Mock 통과나 기존 Ubuntu 게임 CI 성공으로 대체하지 않는다.

최초 형상 `05b888a`의 Windows 자동 검증은 T01~T06 전체6개 PASS, unittest 측정12.331초(명령 전체13.070초)였다. 독립 CLI 부모 종료 후 Worker 완료, 실제 소유 자식 Timeout/Cancel 정리와 타 프로세스 보호, Junction 경계 및 복구 실패를 포함했다. 10초 목표는 초과했으며 감사 전 형상의 더 짧은 실행시간으로 대체하지 않는다. 당시 `scripts/dev.py check`도 통과했다. 이 결과는 이번 A안·READY 보완의 새 실행 결과와 구분한다.

최초 형상 `05b888a`에 대한 당시 독립 Auditor는 동결 코드·실제 Assertion·원로그를 대조하여 A — Ready for Review, 잔여 P0/P1/P2 0건으로 판정했다. 이후 해당 코드로 기존 완료 [Run40093727301](https://github.com/wonmin82/primal-zone/actions/runs/40093727301), Attempt1, SHA `f9b6f474ffac477125da168c56d65efc9ff6cddb`, PR75 HEAD를 읽기 전용 확인했다. Worker의 실제 READY 후 PASSED/종료 코드0/3.164초와 소유 자손 정리를 확인했으며 새로운 CI Run은 생성하지 않았다. 실제 Queue 명령은 종료 코드0·ACCEPTED_UNCONFIRMED, 알림 자손 정리 확인으로 기록됐다. 실제 세션 재개는 UNVERIFIED이며, 완료 결과는 `status`로 복구 확인했다. 이 과거 Run과 감사는 A안 보완의 최신 코드 검증을 대신하지 않는다.

### A안·READY·CI 연결 보완의 로컬 결과

Windows Native에서 기존 T01~T06 여섯 테스트군 전체가 PASS, 23.711초였다. 이후 정리 미확인 시 활성 등록을 보존하는 마지막 변경은 T06(1개 PASS, 8.698초)과 T02/T03(2개 PASS, 4.280초)만 재검증했다. 나머지 군은 해당 변경의 정상 정리 경로가 같아 기존 성공을 재사용했다. Smoke ownership 단위 테스트 5개는 0.051초에 PASS했고 `scripts/dev.py check`, `git diff --check`도 통과했다. 초기 Fixture 실패와 보완 원로그는 ignored `work/issue76/supplement-*`에 보존한다. 10초 목표를 맞추려고 중요한 안정성 검증을 제거하지 않았다.

Windows에서 macOS의 Supervisor 소유권·Session/PGID·marker·Smoke 상속/개별 종료·세션 이탈·정리 실패·CI/Queue 차단 제거는 Mock으로 확인했다. T01의 POSIX Supervisor 커널 하위 사례는 Windows에서 실행하지 않았으며 여섯 테스트군 자체를 SKIP하지 않았다. 같은 명령을 실행하는 Ubuntu `contracts` Step에서 이 조건부 자동 사례도 수행하도록 연결했다. 별도 Linux/macOS 수동 실환경 검증과 실제 게임 서버·로컬 Smoke/E2E 실행은 이번 보완에서 수행하지 않았다. 최신 Source HEAD CI의 실제 결과와 감사 판정은 PR Validation에 기록한다.

독립 감사에서 marker와 환경변수의 nonce가 양쪽 모두 누락되거나 비어 있을 때 비교가 통과하는 P2를 발견했다. T04의 수정 전 실행으로 3개 실패를 재현(6.409초)한 뒤 각각 문자열·32자리 소문자 hex인지 양성 검증하고 일치 여부를 확인하도록 수정했다. 누락·빈 값·잘못된 형식·한쪽 누락·불일치 거절을 추가한 T04 재검증은 PASS(6.322초)였다. 나머지 계약과 여섯 테스트군 구성은 유지했다.

보완 회차의 독립 Auditor는 실제 동결 Diff·Assertion·원로그를 확인하고 위 P2 해결 후 A — Ready for Review, 잔여 P0/P1/P2 0건으로 판정했다. 별도 Linux/macOS 실환경 검증이나 최신 PR CI를 수행한 판정으로 확대하지 않으며, PR 최신 Source의 자동 CI 결과는 별도로 확인한다.

첫 보완 Source `8ea3d6b`의 [Run40144967343](https://github.com/wonmin82/primal-zone/actions/runs/40144967343)에서는 새 `contracts` Step이 실패했다. Git 자동 maintenance가 임시 template의 `.git/objects/maintenance.lock`을 제거하는 동안 복사해 T01 setUp에서 ENOENT가 발생했고 다른 다섯 군은 통과했다. T01 본문과 그 POSIX 하위 사례는 이 실패 실행에서 검증되지 않았다. 테스트 전용 template 저장소에만 commit 전 `maintenance.auto=false`, `gc.auto=0`을 설정하고 복사 후에도 그 설정을 검증하도록 고쳤다. Windows T01 재검증은 PASS(4.692초)였으며 lock 파일 무시·재시도·Sleep·사용자 글로벌 Git 설정 변경은 하지 않았다. 실패 원로그를 보존하고 다음 Source의 자동 CI를 별도 근거로 확인한다.

프로세스 API 근거는 [Python3.13 subprocess](https://docs.python.org/3.13/library/subprocess.html), [Python3.13 os](https://docs.python.org/3.13/library/os.html), [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)를 따른다. Session/Process Group과 Job Object의 정리 결과를 프로세스 생성 성공만으로 추정하지 않고 소유 경계와 회귀로 확인한다.
