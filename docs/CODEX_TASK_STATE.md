# Current Task State

확인일: 2026-09-29. 이 문서는 새 Codex 세션을 위한 상태 인계이며, 기능의 상세 설계는 [architecture.md](architecture.md), 사용법은 [README](../README.md), 검증 절차·과거 기록은 [playtest.md](playtest.md)를 따른다. 시작 시 실제 Git/원격 상태를 다시 확인한다.

## Objective

본부 재설계 1단계와 방향 정정은 [PR #13](https://github.com/wonmin82/primal-zone/pull/13)으로 병합됐다. 병합 커밋은 `f9fcd52feb7c449eb94519d9e36f3504558056f4`다. 중앙홀 남/1층 중앙 북과 남쪽 폐쇄 출입구, 대기실 남/중앙홀 북과 중앙홀 서/부두 동을 유지한다. 상세 설계는 [본부 Room 구조 1단계](architecture.md#본부-room-구조-1단계)를 따른다.

테스트 성능 개선은 [PR #14](https://github.com/wonmin82/primal-zone/pull/14)로 병합됐으며 병합 커밋은 `ada6487f254beb3a662340ce81fa75771092cce1`다. 2026-09-28 승강기 작업 시작 시 fetch 후 실제 최신 origin/main도 같은 SHA였고 main 작업 트리는 깨끗했다. 당시 PR #13·#14의 MERGED와 main CI 성공을 직접 확인했다. 아래 테스트 성능 개선 기록은 해당 시점의 결과다.

본부 2단계 공용 승강기는 [PR #15](https://github.com/wonmin82/primal-zone/pull/15)로 병합됐다. 이번 작업 시작 시 unstaged/staged diff가 없는 main에서 fetch했고 로컬 HEAD와 최신 origin/main은 모두 `7cf42145551ea364b5f1a1b69fa68c3e5567bee8`이었다. PR #15의 MERGED 및 해당 main [Game checks](https://github.com/wonmin82/primal-zone/actions/runs/36434012910) success를 직접 확인했다. 로그는 순수 77개·통합 213개, 총 290개 통과이며 통합 52.911초·runner 56.367초다. 아래 PR #15 OPEN 서술은 PR 생성 시점의 과거 기록이다.

현재 승인된 작업은 본부 3단계 보관·훈련 서비스 이전이다. 최신 origin/main에서 `codex/hq-service-relocation`을 만들었다. 구현과 로컬 자동/브라우저 검증을 완료했으며 commit/push/PR 생성과 최신 CI 확인을 진행한다. 기존 세 객체의 stable ID와 저장 데이터를 유지한 채 보관실·훈련실로 이전하고 실제 객체·가시성·안전·비전투 상태를 기준으로 이용 가능 여부를 맞췄다. PR은 병합하지 않는다. 귀환·패배·상점·휴식·윤대장은 계속 부두에 둔다.

기존 광원 기능은 PR #11로 완료됐고 인계 문서는 PR #12로 병합됐다. 아래 광원·본부 1·2단계·테스트 성능 개선의 설계·검증은 시점별 과거 기록이며 보존한다. 3단계 이후 의료/귀환/사망 개편, 단일 화폐/정산, NPC 상점, 통합 closeout은 후속 범위다.

### 본부 3단계 구현과 검증 (2026-09-29)

- 시작 기준은 `7cf42145551ea364b5f1a1b69fa68c3e5567bee8`이며 작업 브랜치는 `codex/hq-service-relocation`이다. 최종 로컬 검토를 위한 재fetch에서도 origin/main은 같아 rebase 재작성은 필요 없었다. PR #13/#14/#15는 병합 완료이며 승강기는 재설계하지 않았다.
- `shared_container`/`personal_locker`는 `storage_room`, `instructor`는 `training_room`으로 정의 위치만 이전한다. stable `primal_interactable` tag로 기존 DB 객체를 재사용하고 bootstrap이 key/location/alias를 갱신한다. 기존 다중 alias 전달이 두 번째 이름을 category로 처리하던 문제를 수정해 목록 전체를 보존한다. 삭제·재생성·profile version 변경은 없다.
- 공용 `Container.db.items`, 각 `profile.storage`와 개인 inventory/equipment/growth/skills/proficiency/visited·기존 캐릭터 위치는 bootstrap이 쓰지 않는다. 자동 및 별도 DB의 반복 이전 검사에서 객체 ID·전체 객체 수·Room ID와 모든 개인 profile·shared contents를 보존했다. 검증 DB의 세 객체 ID는 134/135/137로 그대로이며 `stale_definitions()`는 빈 목록이다. A/B가 같은 개인 보관함을 사용해도 자신의 contents만 보인다.
- 보관은 기존 current-room Container resolve·selector·Observation과 transfer transaction을 유지한다. 훈련은 실제 Instructor의 같은 Room·현재 Room safe·비전투·can_perceive/view 조건을 검사한다. `instructor_for`는 기존 `room_objects`의 관찰 가능한 풀과 같은 availability를 사용하며 `push_state`는 같은 observed_at으로 `training_available`을 계산한다. unsafe/없는/숨긴 NPC와 전투 중에는 웹과 명령 모두 훈련할 수 없다. 다른 안전 Room에 실제 객체를 옮겨도 서비스는 객체를 따른다.
- Web은 기존 server-owned interactables/training_available과 동일 텍스트 명령을 유지하고 훈련 안내와 JS cache query만 갱신했다. storage_room/training_room client zone 특례가 없으며 dock 상점·휴식 UI, 윤대장, home/귀환/패배 목적지는 그대로다. distant는 보관 contents/개인 정보/훈련 행동·기술 상태를 노출하지 않는다. 세 정적 서비스 배치는 integrity에 추가했다.
- 최종 production 기준의 `scripts/dev.py check` 통과, 전체 `scripts/dev.py test` 순수 78개(0.080초)·통합 219개(78.633초), 총 297개 통과·실패/skip 없음이다. 통합 runner는 88.088초이며 근거 `work/hq-services-final-full-success.log`다. 관련 순수 51개(0.091초), 새 이전 suite 역순·병렬 6개(10.204초, runner 19.491초)도 통과했다. 새 suite는 WorldCommandTest 5개와 이전 lifecycle을 직접 검증하는 GameCommandTest 1개로 나뉜다.
- 첫 관련 검사의 새 오류 문구 기대값·다중 alias 문제와 최초 전체의 옛 부두 상자 조명 fixture를 수정했다. 실패한 조명 1개(2.557초)부터 통과시킨 뒤 위 전체를 실행했다. 최종 전체 이후 production 변경은 없고, 기존 물건 전달 테스트의 실제 NPC 거절 경계를 유지하기 위해 부두 fixture를 명시한 뒤 해당 1개만 재검증했다(2.506초, runner 11.083초, `work/hq-services-give-recheck.log`). 문서·PR 갱신만을 이유로 전체 검사를 반복하지 않는다.
- JavaScript 문법·diff 검사 통과, game과 별도 검증 서버 정적 파일을 수집했다. Chrome 두 일반 계정으로 보관실 객체/보기/공용·개인 넣기·꺼내기·개인 분리, 실제 승강기 훈련실 동선·대화·배분/학습 버튼과 직접 명령의 동등한 결과·특성/기술/전체 재훈련, 부두의 대상 실패·훈련 비활성·상점/휴식/윤대장과 부두 귀환을 확인했다. 실제 JS query는 hq-services다. 앱 console 오류는 발견하지 않았으나 로그인 Chrome 확장 메시지 채널 종료 오류가 계정별 2건 있었다. 포트 4301의 Windows 바인딩 오류는 격리 서버를 5401 계열로 바꿔 해결했다. 검증 서버·탭은 종료했고 플레이 DB는 읽거나 변경하지 않았다. [상세 검증 기록](playtest.md#본부-3단계-보관훈련-이전-확인)을 따른다.
- 전체 smoke는 현재 파일에 보관/훈련 Flow가 없고 관련 자동/브라우저 검증으로 확인해 미실행이다. UI layout 변경이 없어 좁은 화면을 반복하지 않았다. 실제 OS IME·이번 변경의 재시작 재접속·운영 플레이 DB 적용은 미실행이며 이전 승강기 기록을 이번 실행처럼 쓰지 않는다.
- 커밋·PR 생성 후 실제 기능 HEAD/PR 번호와 최신 CI를 후속 원격 기록에 추가한다. 이번 요청은 PR 병합을 허용하지 않는다. 다음 단계는 3단계 PR 검토·병합 후 최신 main에서 별도 요청으로 시작하는 의료·귀환·사망 흐름이다.

### 본부 2단계 구현과 검증 (2026-09-28, 과거 기록)

- `support_elevator` 실제 ZoneRoom을 headquarters에 추가했다. 본부 26개·전체 41개 Room이며 승강기의 사방 Exit는 없다. 기존 HQ 방향·폐쇄 출입구·출구 migration과 부두 서비스는 보존한다.
- `world/content/elevator.py`의 `ELEVATOR_STOPS`가 `1f/2f/3f/roof`와 세 중앙 복도·옥상의 대응 SSOT다. 승강기 Room의 persistent `db.current_stop`은 모든 승객이 공유한다. bootstrap은 새/invalid 값만 1층으로 정규화하고 정상 층·Room/Exit ID·플레이어 위치는 보존한다.
- 호출 Room의 location CmdSet은 `승강기`, 내부 CmdSet은 층 선택과 `내리기`를 제공한다. 밖에서는 내부 명령을 일반 unknown-command로 처리한다. `world_change()`와 실제 `move_to()`를 재사용하며 외부 호출에도 기존 승객은 내부에 남고 하차는 한 명씩이다. 성공 후 승객 알림과 기존 접속자 state push를 사용한다. 지연·문 상태 머신은 없다.
- 텍스트와 `pz_state.elevator`는 같은 서버 controls를 사용한다. 웹은 현재 층과 서버 actions를 렌더링하고 동일 명령을 전송한다. client zone 분기·가짜 cardinal Exit는 없다. 지도는 방문한 Room을 기존 목록에 표시한다. integrity와 cardinal/transport reachability 검사를 분리해 보완했다.
- 최종 로컬 기준은 `ada6487f254beb3a662340ce81fa75771092cce1` 위의 이 기능 미커밋 변경이다. `scripts/dev.py check` 통과, `scripts/dev.py test` 순수 77개(0.071초)·통합 213개(78.955초), 총 290개 통과다. 통합 runner는 88.978초이며 실패·skip은 없다. 근거 `work/elevator-final-full.log`. 이후 변경은 기록 문서뿐이다.
- 관련 순수 50개·통합 31개(51.656초), 승강기 역순 8개(17.995초)도 통과했다. `--parallel 2 --reverse`는 테스트 클래스가 하나여서 실제 worker 하나를 사용하며 관련 31개와 전체 검사는 여러 worker로 수행했다. 최초 전체의 기존 Room 명령 없음/옛 JS query 기대값 2건은 승강기 controls와 새 query를 정확히 검증하도록 갱신하고 해당 2개부터 통과시킨 뒤 전체를 재검증했다.
- JavaScript 문법 검사와 diff 검사 통과, game과 별도 검증 환경의 정적 파일을 수집했다. 별도 SQLite DB의 두 계정으로 네 호출 버튼·내부 버튼/직접 명령·공용 층·외부 호출·독립 하차·재접속·지도·폐쇄 방향·승강기 밖 unknown·부두 귀환을 확인했다. 정상 서버 종료·재시작 후 승객 Room과 옥상 current stop 보존·하차도 확인했다. 실제 390px 문서 375/375px·로그 339/339px로 넘침이 없었고 데스크톱도 확인했다. 앱 코드 console 오류는 없었으나 로그인 시 자동완성 확장 오류와 일시 UI 차단이 있었다. 검증 서버·임시 탭은 종료했고 플레이 DB를 보존했다. 상세 근거는 [승강기 검증 기록](playtest.md#본부-2단계-공용-승강기-확인)을 따른다.
- 전체 smoke는 기존 사냥/귀환 Flow를 변경하지 않아 미실행이며 관련 자동/브라우저 검증으로 확인했다. 실제 OS IME·강제 종료·운영 배포 검증은 미실행이다. 플레이 DB는 초기화하거나 변경하지 않았다.
- 원격 기록 작성 시 branch는 `codex/hq-elevator`, 로컬/원격/PR HEAD는 `5b07ba7ae7be0ef2c00bf5d72cdcf256a54df878`로 같고 작업 트리는 깨끗했다. fetch 후 origin/main은 시작 시와 같은 `ada6487f254beb3a662340ce81fa75771092cce1`이며 이미 포함돼 rebase 재작성은 필요 없었다. [PR #15](https://github.com/wonmin82/primal-zone/pull/15)는 OPEN·비Draft·MERGEABLE이다. 이 구현 HEAD의 [Game checks](https://github.com/wonmin82/primal-zone/actions/runs/36432069851)는 success이며 SHA를 직접 대조했다.
- 이 원격 기록은 PR 생성 후의 문서 전용 후속 커밋에 포함한다. 위 SHA는 기능 구현·CI의 확인 기준이고 문서 커밋 이후의 최종 HEAD는 실제 `git rev-parse HEAD`와 PR에서 확인한다. 실행 코드·테스트가 같아 로컬 전체 검사는 반복하지 않으며 최종 문서 HEAD의 CI는 푸시 후 별도로 확인해 PR Validation에 기록한다. PR은 사용자 요청대로 병합하지 않는다.

### 자동 테스트 성능 개선 (2026-09-28)

- 시작 시 작업 트리는 깨끗했고 main과 fetch 후 origin/main은 `f9fcd52`로 같았다. 열린 PR은 없고 해당 main CI는 성공이었다. 인계의 PR #13 OPEN 상태보다 실제 병합 상태가 최신임을 확인했다. 최신 원격에서 `codex/test-performance`를 만들었다.
- `settings_test`에 테스트 전용 메모리 SQLite·빠른 해시를 두고 `tests.base`에 클래스별 실제 월드 생성, Room ID 공유·일괄 조회, DB rollback 후 강제 객체/명령 캐시 정리와 한 번의 GC를 구현했다. 최초 로그인 검사는 기존 월드 준비 순서를 유지한다. 기존 통합 199개 본문·assertion은 변경하지 않았다.
- 로컬 기본은 CPU 수에 따라 최대 4개 프로세스다. `--parallel 1`, 선택한 통합 테스트 경로, `--reverse`를 지원한다. Django의 DB 복제·rollback·결과 수집을 사용하고 Evennia worker 초기화·설정 모듈 경로·실패한 subTest의 요약 전달을 보완했다. `tblib 3.2.2`는 병렬 traceback 전달용 개발 의존성이다.
- CI는 2개 프로세스, PR과 main push로 변경했다. 로컬 검증 시점에는 푸시 전이므로 새 구성의 원격 CI는 미실행이었다. 푸시 후 최신 PR HEAD의 CI를 직접 확인하며 기존 main CI를 이 변경의 통과 근거로 사용하지 않는다.
- 최종 `scripts/dev.py check` 통과. `scripts/dev.py test`는 순수 72개(0.075초)와 통합 205개(60.975초), 총 277개 통과이며 실패·skip은 없다. DB 준비 등을 포함한 통합 runner 시간은 70.112초다. 근거 `work/test-optimization-final-full.log`. 이후 변경은 기록 문서뿐이다.
- 오류 전달 보완 전 직렬 전체는 통합 204개 251.349초, 병렬 전체는 204개 99.704초로 통과했다. 최종 추가된 1개 오류 전달 검사와 관련 보완은 해당 직렬 2개 검사 및 최종 전체 병렬로 확인했다. 직렬 전체의 기준 차이를 최종 205개 성공으로 바꿔 쓰지 않는다. 관련 역순 병렬 49개도 통과했다.
- 실제 2개 worker에서 일반 실패와 Evennia 객체를 가진 subTest 실패를 의도적으로 발생시켜 원래 조건·traceback·실패 종료 코드 1과 `failures=2`를 확인했다. 이는 별도 실패 경로 진단이며 정식 전체 suite의 실패가 아니다. 근거 `work/test-optimization-worker-failure-final.log`. 임시 DB 복제본은 제거됐고 플레이 DB는 변경하지 않았다. 브라우저·smoke는 게임/UI 동작 변경이 없어 미실행이다.

### 본부 작업 시작 상태

- fetch 후 `main`과 `origin/main`은 PR #12 병합 커밋 `fd3e884fd6cc426b95b267b7960c216ab7abc70d`로 같았고 unstaged/staged diff가 없었다. PR #12는 병합·소스 브랜치 삭제 완료, 해당 main CI는 성공이었다.
- 최신 `origin/main`에서 `codex/hq-room-skeleton`을 만들었다. 이 작업의 Git·검증 상태는 완료 기록과 실제 저장소에서 확인한다.
- 기존 `architecture.md`의 profile 최신 버전 설명은 5였지만 코드는 6이다. 이번 작업에서 저장 schema를 바꾸지 않았으며 기존 방문 기록·위치를 보존한다. 본부 설계만 추가하고 과거 migration 설명의 별도 정비는 하지 않았다.

### 본부 1단계 최초 완료 기록 (방향 수정 전)

- Room 25개 추가, 월드 총 40개·Region 3개다. 대기실 남/중앙홀 북, 중앙홀 서/부두 동과 중앙홀 동/1층 중앙 남의 동선을 구현했다. 부두 북/초지와 기존 서비스 객체는 보존했다.
- 복도 15칸·시설 7곳·옥상, 폐쇄 방향 22개를 정의했다. 시설은 Room만 생성하고 기능 없는 hint/NPC는 없다. 2·3층과 옥상은 층간 이동을 구현하지 않아 일반 동선에 연결하지 않았다.
- 폐쇄 입력/정찰은 안내만 반환한다. local/distant/지도에 기존 표시 방식을 사용하고 웹 출구에는 실제 이동 방향만 보낸다. stable tag로 bootstrap 재사용·갱신 및 명시적 폐쇄 관리 Exit 정리를 검증했다.
- 새 최초 접속/visited는 대기실이고 유효한 재접속 위치·기존 profile 방문 기록은 유지한다. home/귀환/패배는 dock다.
- `.\.venv\Scripts\python.exe scripts/dev.py check` 통과, `scripts/dev.py test` 순수 72 + 통합 198 = 총 270 통과. 근거 `work/hq-final-full.log`, 통합 1010.005초. 관련 통합 19개도 통과했으며 상세는 [본부 확인 기록](playtest.md#본부-room-구조-1단계-확인)을 따른다. 전체 성공 뒤에는 기록 문서만 수정했다.
- 별도 DB 브라우저에서 최초 대기실, 버튼/명령 이동·폐쇄 입력/보기·지도, 부두/초지·귀환·재접속 위치 보존을 확인했다. 1366/390px 가로 넘침 및 탭 오류/경고 없음. 검증 서버 종료, 플레이 DB 보존. 실제 OS IME와 플레이 DB에 계정을 남기는 전체 smoke는 미실행이다.
- 구현 완료 보고 시점의 fetch에서 origin/main은 여전히 `fd3e884`였고 해당 기존 main CI는 성공이었다. 당시 본부 변경은 브랜치의 미커밋 변경으로 보존했고 commit/push/PR 생성·병합하지 않았다. 이후 사용자 요청으로 같은 변경을 커밋·푸시하여 PR에 포함한다. 최신 commit/PR/CI 상태는 실제 Git과 GitHub에서 확인하며 기존 main CI를 본부 변경의 CI 성공 근거로 사용하지 않는다.

### 본부 방향 정정 (2026-09-28)

- 시작 시 `codex/hq-room-skeleton` HEAD와 PR #13 HEAD는 `bef94dd0129317b6a74570b3fb137c5030dd418c`였고 작업 트리는 깨끗했다. fetch 후 `origin/main`은 `fd3e884`였으며 PR은 OPEN, 해당 기존 HEAD의 push·PR CI는 모두 성공이었다. 인계의 PR 생성 예정 문구보다 실제 PR 생성 상태가 최신이다.
- 중앙홀 남/1층 중앙 북으로 통일하고 남쪽 폐쇄 출입구, Room 설명·지도·웹 출구 기대값을 수정했다. 본부의 복귀 방향 데이터와 검사 예외는 제거하고 일반 정반대 방향 검증을 사용한다.
- bootstrap은 옛 본부 관리 Exit 두 개만 같은 Room/목적지에서 새 방향 tag·alias로 재사용한다. Room ID·캐릭터 위치·진행·서비스 객체와 일반 stale 감사 정책은 보존한다.
- 별도 DB에서 기존 본부 Exit 2개의 ID를 보존한 갱신과 새 일반 계정의 대기실 남/중앙홀 남 이동, 북 명령 복귀·부두 왕복, 남쪽 폐쇄 이동/보기·지도·실제 버튼, 부두 귀환·지원동 재접속 위치 보존을 확인했다. console 오류/경고 0개, 근거 `work/hq-direction.png`. 검증 서버·탭 종료, 플레이 DB 보존. 이전 브라우저 기록은 방향 수정 전 근거로 구분한다.
- 최종 `scripts/dev.py check` 통과, `scripts/dev.py test` 순수 72 + 통합 199 = 총 271 통과(통합 1153.144초, `work/hq-direction-full.log`). 관련 통합에서 발견한 미사용 옛 tag 잔존을 수정하고 실패한 bootstrap 1개를 먼저 통과시킨 뒤 전체를 실행했다. 전체 성공 후 실행 코드·테스트는 고정했다. 상세는 [본부 확인 기록](playtest.md#본부-room-구조-1단계-확인)에 남긴다. 수정 커밋을 같은 PR에 푸시하며 최신 HEAD의 원격 CI는 GitHub/PR 설명에서 직접 확인한다.

## Current Repository State

아래 표는 인계 문서 최초 작성 시점의 기록이다. 이후 사용자 요청으로 이 문서를 `codex/task-state-handoff` 브랜치의 문서 PR에 포함한다. 현재 브랜치·HEAD·추적 여부·PR·CI 상태는 시작 시 실제 저장소와 GitHub에서 다시 확인하며, 이 표의 과거 상태를 현재 상태로 간주하지 않는다.

| 항목 | 확인한 상태 |
| --- | --- |
| 저장소 | `wonmin82/primal-zone` |
| 현재 브랜치 | `main` |
| 로컬 HEAD / fetch 후 origin/main | 모두 `c38ff0081ca1e67000289628d2e826d6e9e82e7b` |
| 인계 작성 전 | working tree 깨끗함, unstaged/staged diff 없음 |
| 인계 작성 후 | 새 `docs/CODEX_TASK_STATE.md`만 미추적 상태. commit/stage/push하지 않음 |
| PR #11 | [환경 시야와 광원 시스템 확장](https://github.com/wonmin82/primal-zone/pull/11), MERGED |
| 병합 | 2026-09-28, merge commit `c38ff0081ca1e67000289628d2e826d6e9e82e7b` |
| PR 최종 HEAD | `7698c72b71e2bbef0f543942240e9d2c921989bd`; 병합 커밋과 tree diff 없음 |
| 소스 브랜치 | `codex/environment-visibility-lighting` 원격·로컬 모두 삭제 완료 |
| 열린 PR | 확인 시 없음 |

최근 관련 이력:

- `ba96c2c`: Observation·광원·공용 시설의 최초 구현.
- `0768afc`: 시설의 실제 밝기 기여, versioned 시설 state, 구조화 hint, 광원 보기, 시설 가동 알림.
- `7698c72`: clear hint의 target/text 선언 순서 조합과 FACILITIES 정의 검증 보완.
- `570e8d3`: PR #10 Environment 병합. 후속 `75a1ba8`의 정적 기상 충돌·알림·환경 version 수정 포함.
- `0567810`: PR #9 아이템 상호작용·방향 정찰 병합.
- `45dbf80`: PR #8 전리품 상세 회수 안내 병합; `3c0b36c`는 PR #7 selector/loot 기반.

기존 인계 문서는 없었다. `AGENTS.md`는 개발 지침이고 기존 docs는 설계/검증 기록이므로 중복 수정하지 않았다. `work/`, DB, 비밀 설정, 로그, 가상환경, 수집된 정적 파일은 Git 제외 대상이며 인계 때문에 삭제·초기화하지 않는다.

## Confirmed Requirements

- Room은 정적 장소, Environment는 현재 공용 시간·날씨·빛, Object는 현재 존재·행동, Observation은 관찰자별 실제 식별을 소유한다.
- 불변 EnvironmentSnapshot은 viewer-independent다. 손전등은 Observation의 effective 값에만 반영한다.
- DEFAULT / INDEX / ALL과 relation/loot parser, 방 안의 임시 번호·공통 정렬을 유지한다. 번호는 DB에 저장하지 않는다.
- Room prose는 자연어, SURROUNDINGS/버튼/상태 control은 compact label을 허용한다. 상세 행동은 실제 실행 가능한 명령을 안내한다.
- `봐`는 모든 `보기` 대상의 alias, `때려`는 기존 `공격` alias다. 방향 보기와 실제 이동은 분리한다.
- 원거리 selector·HP·claim·파티·loot·보관함 contents·action hint는 노출하지 않는다. 잠긴 진행 경계의 내부 환경·객체는 조회하기 전에 차단한다.
- 광원 삽입 canonical 문법은 `<광원>에 <전원 소스> 넣어`다. 호환 타입·용량은 metadata에서 읽는다.
- 발전기 개인 `generator_fixed`와 shared `outpost_power`는 독립이다. 부품 3개, XP 50, 개인 ridge 진입 조건을 그대로 유지한다.
- PR #11의 병합과 소스 브랜치 삭제는 사용자의 명시적 요청으로 완료됐다. 이전의 “PR을 merge하지 말라”는 당시 작업 단계의 제한이며 PR #11이 현재 보류 상태라는 뜻이 아니다. 인계 문서 PR의 생성 요청은 해당 PR의 병합 요청을 포함하지 않는다.

## Design Decisions

- Environment 계산은 `world/environment.py`의 pure model, 저장/알림은 `environment_state.py`와 WorldLifecycle이 담당한다. 조회는 snapshot projection이며 DB/profile을 저장하지 않는다.
- World state 변화와 ambient 사용자 알림을 구분한다. 동일 `observed_at`의 저장 before/after 문장이 실제 달라질 때만 날씨/시간대 알림을 보낸다. fixed-light 실내의 동일 문장 period 변화는 생략하고 웹 state는 갱신한다.
- 이동 차단은 pure `entry_block()`의 requirement 판정, 이동 안내는 `requires.message`, 정찰 안내는 optional `requires.observe_message`다. 누락 시 물리적 문을 가정하지 않는 fallback을 쓴다. `blocks_distant_view=False`는 관찰만 허용하며 Room view lock은 여전히 적용된다.
- Exit는 DistantViewContext를 만들고 목적지 Room으로 위임한다. Room은 별도 distant path를 조립하고 각 객체가 visibility/presence를 제공한다. 일반 Room appearance를 호출한 뒤 문자열을 지우는 방식은 채택하지 않았다.
- ActionObject의 distant visibility는 기본 hidden/명시적 opt-in이다. detectability와 view permission은 별도 조건이며 광원으로 정책상 hidden을 우회하지 않는다.
- stack inventory와 pure `rules.move_item()`을 유지한다. transfer의 DB mutation은 `item_transfers.transfer()`/`world_change()` 안에서 이루어진다. 장착된 복사본 수만 예약하고 여분은 이동 가능하다.
- Light Source는 `strength/range/power_type`, Power Source는 `type/capacity_seconds`를 소유한다. 전원 ID 분기, 손전등 고정 30분 상수, 별도 parser, 모호한 `손전등 교체`는 채택하지 않았다.
- 전원은 삽입 시 스택 하나를 소비한다. 잔량이 있는 전원은 교체 거절하며 partial-charge instance를 만들지 않는다. 마지막 광원 이전 시 내부 전원 상태를 폐기하는 단순 정책을 택했다.
- 시설 정의/현재 state/Room 연결을 분리한다. `FACILITIES`가 ID/default SSOT, script state가 on/off, `facility_lights`가 조명 연결이다. base와 시설 빛의 최대를 ambient로 사용하고 시설이 실제 강할 때만 문장에서 강조한다.
- Room hints는 stable INTERACTABLES ID/action 또는 일반 text다. 원본 선언 순서로 렌더링하고 대상 이름 SSOT·can_perceive를 재사용한다. clear에서는 target+text, limited에서는 보이는 target만, 없으면 제한 안내다.

## Implemented

### 기존 명령·전리품·보관

- `때려`, `버려/줘`, `먹어/마셔`, `벗어/해제`, `넣어/꺼내`, `봐`와 방향 `북 봐/n 보기`가 등록되어 있다.
- 아이템 기본 이동은 1개, `아이템 모두`는 이동 가능분 전부다. numeric `3개` 수량·inventory instance 번호·여러 recipient/container 동시 이전은 지원하지 않는다.
- 직접 버린 물건은 기존 public DroppedLoot, 공용 Container는 persistent `db.items`, 개인 보관함은 caller의 `profile.storage`다. 같은 객체를 써도 개인 contents는 분리한다.
- 임무 핵심 `jungle_cell`은 `transferable=False`로 버림/양도/보관을 차단한다. 음식은 야전식량 12 HP/4크레딧, 정제수 6 HP/3크레딧이며 비전투·단일 소비·만HP 실패·치료 숙련 미증가다. 붕대의 회복 경로는 별도 유지한다.
- weapon/armor None과 base attack의 맨손 전투를 지원한다. 장착 복사본을 뺀 수량만 버림/양도/보관 가능하다.
- Corpse/DroppedLoot 상세는 단독 `가져` 안내 대신 실제 회수 문법을 제공한다. 시체가 여럿이면 공통 room-local 번호, 하나면 무번호다. party assignment/protection·TTL·respawn semantics는 유지한다.

### 장소·정찰·환경

- 모든 15개 Room의 정적 desc와 객체 존재/행동을 분리했다. dock 고정 안개, office 현재 강우, marsh 고정 물안개 대신 장소/누수 흔적/습한 성향을 기술한다.
- Enemy content의 `presence/distant_presence`를 typeclass가 읽고 같은 종류를 자연어로 묶는다. respawning Enemy·expired Corpse를 원거리에서 non-mutating 방식으로 제외한다.
- 원거리의 다른 Explorer는 익명 인원 요약이다. 작은 기록/표식/보급품과 DroppedLoot는 기본 hidden이며 상자·개인 보관함 내부를 읽지 않는다.
- 4배속 게임 시간, 시간대·28일 달 주기, 하나의 `island` Weather Zone, Room exposure/light_profile, 주변광·시야, seed/deadline 기반 weather 전이·재시작 catch-up이 구현돼 있다.
- `ENVIRONMENT_VERSION=1`이며 version 없는 state의 epoch/weather/seed/step/기한을 보존하고 미래 version은 오류다. 조회는 복사본, 저장은 reconcile transaction에서만 수행한다.

### Observation·광원·시설

- local/distant prose, room selector, SURROUNDINGS, target action, loot, 신규 combat target이 공통 지각 정책을 사용한다: clear=모두, reduced=normal/conspicuous, poor=conspicuous. Exit는 어둠으로 숨기지 않는다. 이미 교전 중인 target은 계속 추적한다.
- 시체 존재(normal)와 내부 작은 전리품/subtle 회수는 구분한다. 정확한 숨은 이름을 입력해도 perception을 우회하지 못한다.
- 탐사용손전등(alias 손전등) strength 2/range 1과 건전지 `flashlight_battery`/1800초가 있다. local 시야 최대 2단계, distance=1 최대 1단계 개선하며 off/전원 없음/소유 없음/범위 밖은 효과가 없다.
- profile v6의 `light_sources[item_id]`는 `on/power_source/charge_seconds/started_at`를 저장한다. `storage/discoveries` 및 기존 임무·장비·전투 데이터를 보존하며 emergency claim은 `discoveries.emergency_light_cache`다.
- timestamp projection/ceil 분 표시, 켜/꺼/확인, 소진 자동 off/전원 제거, logout/정상 종료 잔량 확정, 마지막 광원 이전 상태 폐기가 구현됐다. 매 tick 잔량 저장은 하지 않는다.
- `손전등 보기`는 정적 설명+현재 status+사용법, `손전등 확인`은 같은 lighting.status의 빠른 조회다. 보기/확인/웹은 동일 observed_at projection을 사용한다.
- wreck 비상장비함은 conspicuous, 플레이어당 최초 손전등 ×1/건전지 ×2다. 부두 상점 30/6크레딧, JungleCache는 기존 붕대 ×2+건전지 ×2다. 60분 compatible 전원은 test fixture이며 production 아이템으로 추가하지 않았다.
- `FACILITY_STATE_VERSION=1`, `db.facilities={"version":1,"states":{"outpost_power":false}}`다. legacy bare dict True를 보존하고 None/빈 dict는 기본값, 미래 version은 오류/덮어쓰기 없음이다. light 조회는 write-free다.
- FACILITIES ID/dict/엄격한 bool default와 Room 조명의 양수 strength·always_on/power 배타 조건을 integrity에서 검사한다. runtime 일반 helper에 특정 power ID 분기를 두지 않는다.
- dock 상시 조명 4, office/generator는 outpost_power일 때 4다. clear day dock은 낮빛, 밤이나 어두운 실내는 실제 기여한 시설 조명 문장이다.
- 개인 발전기 진행+공용 전력 저장은 원자적이며 False→True에 영향권 접속자 시설 가동 알림, True→True에는 반복 알림 없음이다. 기존 state push도 유지한다.
- 웹은 environment와 observation payload를 분리하고 현재 시야, compatible 전원별 삽입 버튼·광원 controls를 제공한다. FIELD GUIDE 환경 확인은 `날씨`, CSS/JS query version은 `lighting`이다.
- clear dock `윤대장 대화 · 상점 · 휴식`, commander view:false이면 `상점 · 휴식`; wreck clear/손전등 clear는 두 상자 안내, poor는 `비상장비함 조사`만 표시한다.

## Partially Implemented / In Progress

본부 PR #13, 테스트 성능 개선 PR #14, 승강기 PR #15는 병합 완료다. 3단계 보관·훈련 이전은 구현·로컬 검증 완료이며 PR 검토·병합을 남긴다. 실제 branch/HEAD/diff/원격 CI를 직접 확인한다. 의료·귀환·사망, 경제·상점, 통합 closeout은 미구현이다. optional 지역 climate presentation profile과 향후 관찰 수단/거리 확장도 구현 완료로 간주하지 않는다.

## Validation

검증 기준과 실행 시점을 구분한다. 본부 1단계는 별도 완료 기록을 추가한다. 아래 표는 이전 광원 구현/병합에서 실제 실행한 결과를 로그·GitHub로 재확인한 것이며 본부 변경의 검증 결과로 간주하지 않는다.

| 기준 | 검증 근거/결과 |
| --- | --- |
| PR 최종 코드 `7698c72` | Windows `scripts/dev.py check` 통과, `scripts/dev.py test` 처음부터 끝까지 순수 65 + 통합 190 = 총 255 통과. 로컬 로그 `work/lighting-final-full.log`에 두 OK, 통합 820.371초 |
| 같은 코드 관련 검증 | `tests.test_lighting` 28개와 diff 검사 통과. local 기록은 `work/lighting-final-related.log` |
| PR 최종 CI | [pull_request](https://github.com/wonmin82/primal-zone/actions/runs/36369059416), [push](https://github.com/wonmin82/primal-zone/actions/runs/36369055993) 모두 같은 HEAD 성공 |
| 병합 main `c38ff00` | [Game checks](https://github.com/wonmin82/primal-zone/actions/runs/36370218528) success, CI head SHA 일치. 로그의 check 성공, 순수 65/통합 190 각각 OK 확인 |
| 최종 후속 브라우저 | 별도 SQLite DB에서 1366px dock·wreck poor/clear/손전등 hint와 SURROUNDINGS, 390px 줄바꿈 확인. 문서 client/scroll width 1351/1351, 375/375px, 최종 탭 오류 0/경고 0. 캡처 `work/lighting-hints-1366.jpg`, `work/lighting-hints-390.jpg` |
| 앞선 광원/시설 구현 | 당시 JS 문법·collectstatic, 전원 없음/삽입/켜기/소진/재접속, 시설 off/on·개인/shared 분리 등을 별도 DB 브라우저에서 검증. 시점별 상세 근거는 docs/playtest.md |

과거 광원 최종 후속 수정은 JS/CSS를 바꾸지 않아 node/collectstatic을 반복하지 않았다. 인계 문서 PR #12는 문서만 추가했으므로 당시 로컬 게임 테스트·브라우저·smoke·정적 파일 수집을 반복하지 않았다. 문서 경로·링크·명령과 구현·Git 상태·기존 로그/CI를 대조하고 문서 diff를 검사했다. 이 과거 판단은 현재 본부 구현의 검사 범위를 제한하지 않는다.

핵심 테스트는 전원 30/60분 동일 parser·실패 rollback·잔량 projection·migration, 시설 legacy/future/cache rollback·actual contribution, hint/selector/SURROUNDINGS SSOT, 광원 보기/확인/웹 시간 일치, locked privacy와 기존 combat/loot/quest 회귀다.

## Known Issues

- **의도적으로 남긴 시나리오:** 이미 공용 발전기가 가동 중일 때 후속 플레이어가 개인 발전기 단계를 진행하는 서사와 회수부품 소비 의미는 추후 시나리오 재검토 대상이다. 현재도 개인 부품 3개/XP 50/flag/진입 조건을 처리하며 “발전기가 다시 돌아가기 시작했다”는 후속 플레이어 문구를 부분 변경하지 않았다.
- **최적화 후보:** restore_outpost_power의 개인 change callback과 shared push_lighting으로 caller에게 state payload가 두 번 갈 가능성. 최종 검증에서 새 중복 사건/로그 부작용은 발견하지 않았으며 수정하지 않았다. 다음 변경 전에 실제 부작용 재현이 필요하다.
- 마지막 손전등을 이전하면 내부 잔량이 폐기된다. 강제 프로세스 종료 직전의 정확한 전원 잔량은 보장하지 않는다. 정상 logout/서버 종료와 강제 종료를 혼동하지 않는다.
- flashlight가 weather visibility까지 보완하는 것은 현재 정책의 단순화다. 물리 조도·LOS 모델로 해석하지 않는다.
- transient 번호는 lifecycle/state push와 클릭 사이에 짧게 stale할 수 있다. opaque/persistent selector는 도입하지 않았다.
- 실제 OS 한글 IME, 이전 asset cache를 미리 채운 조건, 모든 날씨/달/노출 조합의 수동 브라우저 전수 검증은 미실행이다. 자동 문자열 입력/단위 테스트로 대체해 통과라고 쓰지 않는다.
- PostgreSQL 운영·실제 배포 환경 검증은 이 세션에서 확인하지 않았다. 운영 DB/server 상태는 시작 시 확인 필요이며 인계가 배포 실행을 의미하지 않는다.
- **기록의 차이:** docs/playtest.md의 238/252개와 중간 실패 후 관련 재검증은 이전 HEAD 기록이다. 최종은 전체 suite 255개 성공이다. 병합 전 PR 본문의 “PR은 병합하지 않습니다” 문구도 과거 단계의 서술이며 GitHub의 실제 MERGED 상태가 우선이다.
- **설계 문서의 차이:** docs/architecture.md의 기존 데이터 절은 최신 profile을 v5로 적지만 실제 `rules.PROFILE_VERSION`과 후반 광원 설계는 v6다. 기존 데이터 절의 버전 설명은 갱신이 필요한 과거 기록이며 실제 코드와 광원 migration 설계를 기준으로 삼는다.

## Remaining Work

1. 새 세션에서 인계 문서와 Git/원격/CI 상태를 대조한다. 이 문서는 현재 기능 PR에 함께 갱신하며 최초 작성 당시의 미추적 상태와 현재 추적·PR 상태를 구분한다. 미커밋 변경이 있다면 브랜치 전환 시 보존하고 main에 직접 commit하지 않는다.
2. 다음 기능/수정 목표를 사용자와 확정한다. 이 문서의 부채 목록은 자동 구현 요청이 아니다.
3. 발전기 시나리오를 선택한다면 먼저 이미 켜진 시설/개인 미완료/기존 완료 캐릭터의 현재 흐름과 비용·보상 의미를 재현·설계한다. 합의 없이 비용·flag·gate를 수정하지 않는다.
4. push 중복을 선택한다면 실제 callback 횟수와 UI 영향부터 측정한다. 단순 중복 가능성만으로 저장/알림 경계를 다시 설계하지 않는다.

의도적 비범위: multi-room LOS/raycast·lux·광원 전파·부분 전원 회수·충전·연료·전력망 topology·night vision·망원경·은신·Enemy hearing·날씨 전투 modifier/환경 damage·온도/습도. 배고픔/갈증·아이템 무게/용량·container nesting·거래창/우편·숫자 수량/다중 지급도 구현 요청으로 남기지 않는다.

## Recommended Next Step

먼저 AGENTS와 이 문서를 읽고 `git status --short`, unstaged/staged diff, `git fetch origin`, branch/HEAD/origin/main 및 원격 PR·CI 상태를 확인한다. 3단계 보관·훈련 PR을 검토하고 사용자의 별도 병합 요청을 기다린다. 이번 구현 요청은 병합을 허용하지 않는다. 동일 코드의 성공 검사는 PR 생성만을 이유로 반복하지 않는다.

다음 계획은 **4단계 — 의료 시스템 및 복귀 흐름**이다. 3단계 PR 검토·병합 후 최신 main에서 별도 사용자 요청으로 진행한다. Doctor/Bed를 의무실에 준비하고 귀환은 옥상, 패배/사망은 의무실로 바꾸며 사망 최소 복구와 일반 치료를 분리한다. 현재 PR이 열린 동안 구현을 시작하지 않는다. 단일 화폐/회수부품 정산, NPC 상점과 통합 closeout은 이후 단계다.

## Important Files

| 파일 | 역할 |
| --- | --- |
| `AGENTS.md`, `README.md`, `pyproject.toml`, `uv.lock` | 프로젝트 지침/사용법/실제 의존성 |
| `scripts/dev.py`, `game/server/conf/settings_test.py`, `game/server/conf/test_runner.py`, `game/tests/base.py`, `game/tests/test_fixtures.py` | 테스트 전용 설정, 프로세스 병렬 실행·오류 전달, 실제 월드 fixture 재사용과 DB/runtime 격리 |
| `docs/architecture.md`, `docs/playtest.md`, `docs/text-examples.md` | 설계 SSOT, 수동 절차·시점별 결과, 실제 표현 예시 |
| `game/world/content/starter.py`, `game/world/content/deep_jungle.py` | Room desc/hints/requires, Enemy local/distant metadata |
| `game/world/content/headquarters.py`, `game/world/test_headquarters.py`, `game/tests/test_headquarters.py` | 본부 Room/폐쇄 방향 정의, 순수 integrity·동선 검사와 실제 이동·접속·bootstrap·기존 서비스 회귀 |
| `game/world/content/elevator.py`, `game/world/elevator.py`, `game/commands/elevator.py`, `game/world/test_elevator.py`, `game/tests/test_elevator.py` | 정류 층 SSOT, 공용 승강기 상태·표시·실제 이동, location CmdSet, 순수/통합/웹/멀티플레이·격리 검증 |
| `game/world/content/items.py`, `game/world/content/environment.py`, `game/world/content/facilities.py`, `game/world/content/integrity.py` | item/가격/전원, 환경 상수, 시설 정의, 참조·형식 integrity |
| `game/world/environment.py`, `game/world/environment_state.py` | pure 환경 version/계산, DB 저장·읽기 전용 snapshot·전환 알림 |
| `game/world/observation.py`, `game/world/lighting.py` | 지각 matrix/context, metadata 전원·timestamp charge·status |
| `game/world/facility_state.py`, `game/world/facilities.py` | pure 시설 version/정규화, shared transaction·조명 lookup·가동 event |
| `game/world/room_hints.py` | 선언 순서 target/text 조합과 현재 perception |
| `game/world/targets.py`, `game/world/target_presentation.py`, `game/world/distant_presentation.py`, `game/world/navigation.py` | selector/parser/정렬, local 번호·loot 표시, distant contract, pure entry 판정 |
| `game/world/rules.py`, `game/world/item_transfers.py`, `game/world/multiplayer.py`, `game/world/state.py` | profile v6/pure 규칙, 이전 transaction, 공유 atomic/callback, 웹 대상/전리품 state |
| `game/world/lifecycle.py`, `game/world/bootstrap.py`, `game/typeclasses/scripts.py` | tick/restart 소유권, idempotent 월드 구성, persistent WorldLifecycle |
| `game/typeclasses/zone_rooms.py`, `game/typeclasses/exits.py`, `game/typeclasses/enemies.py`, `game/typeclasses/interactables.py`, `game/typeclasses/loot.py`, `game/typeclasses/explorers.py` | 실제 객체와 Room/Exit appearance·action·지각·저장/웹/전투 훅 |
| `game/commands/character.py`, `game/commands/items.py`, `game/commands/inventory.py`, `game/commands/combat.py`, `game/commands/registry.py` | Look/Weather, 이전/광원/소비/해제, 구매/회수, 기존 공격, help 등록 |
| `game/web/templates/webclient/webclient.html`, `game/web/static/webclient/js/primal.js`, `game/web/static/webclient/css/primal.css` | 웹 표시/controls/cache query |
| `game/tests/test_hq_services.py`, `game/tests/test_growth.py`, `game/world/test_headquarters.py` | 보관·훈련 이전/저장 보존/객체·가시성 정책, 성장 회귀와 본부 배치 integrity |
| `game/world/test_lighting.py`, `game/world/test_environment.py`, `game/world/test_rules.py` | pure 규칙·migration·환경/광원 테스트 |
| `game/tests/test_lighting.py`, `game/tests/test_environment.py`, `game/tests/test_distant_view.py`, `game/tests/test_item_interactions.py` | 통합 광원/시설/hint, 환경 저장, 정찰 privacy, stack 이전 |
| `game/tests/test_targets.py`, `game/tests/test_loot.py`, `game/tests/test_combat.py`, `game/tests/test_lifecycle.py`, `game/tests/test_web_state.py` | selector/권한/전투/lifecycle/웹 회귀 |
| `scripts/dev.py`, `scripts/smoke.py`, `.github/workflows/tests.yml` | 실제 개발 검사/서버 흐름/CI. smoke는 플레이 DB에 계정을 남김 |

## Do Not Regress

- 이미 완료된 selector/loot·아이템·환경·광원 기능을 기존 대화만 보고 다시 구현하지 않는다. 특히 초기 “visibility는 표시만” 제한은 PR #11로 대체됐다.
- 환경 조회/원거리 정찰에 profile write·방문·quest/discovery·combat claim·목적지 lifecycle을 추가하지 않는다. 일반 local 보기의 기존 reconcile 경로와 구분한다.
- hidden/view lock/locked privacy를 flashlight 또는 정확한 target 문자열로 우회하지 않는다. selector·hint·SURROUNDINGS는 같은 perception 정책을 쓴다.
- distant 객체 번호·HP·loot·개인 보관 contents·플레이어 이름을 노출하지 않는다. 진행 조건 미충족이면 destination 환경/객체를 읽기 전에 차단한다.
- clear hint의 일반 안내와 선언 순서, poor wreck 비상장비함 발견 경로를 보존한다.
- facility presence와 실제 밝기 기여를 구분한다. 낮 dock의 자연광을 시설 문장으로 덮지 않는다.
- 환경/시설 legacy migration은 값과 epoch를 보존하며 미래 버전은 silent reset하지 않는다. read-only 조회를 migration write로 바꾸지 않는다.
- Power Source 타입/용량 metadata와 기존 relation parser를 유지하고 charge 계산·분 반올림 SSOT를 복제하지 않는다.
- 마지막 광원 이전·소진·logout invariant, shared/person quest의 원자성, 실패 시 inventory·profile·container·facility rollback을 유지한다.
- 기존 party round-robin·reserved/assigned/protection·Corpse TTL·Enemy respawn·전투 타이머/보상·붕대 회복·빈 장비 상태를 유지한다.
- 기존 commit rewrite, main 직접 commit/push, 무관한 미커밋 변경 포함, 플레이 DB 초기화, 보호 규칙 우회를 하지 않는다. 새 작업은 최신 대상에서 별도 branch/PR, 기존 PR 수정은 해당 branch이며 병합은 명시 요청 때만 수행한다.
