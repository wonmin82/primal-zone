# Current Task State

확인일: 2026-10-04. 이 문서는 새 Codex 세션을 위한 상태 인계이며, 기능의 상세 설계는 [architecture.md](architecture.md), 사용법은 [README](../README.md), 검증 절차·과거 기록은 [playtest.md](playtest.md)를 따른다. 시작 시 실제 Git/원격 상태를 다시 확인한다.

## Objective

기존 OPEN [PR #26](https://github.com/wonmin82/primal-zone/pull/26)의 Web 명령 입력 표현을 `codex/mental-recovery`에서 보강했다. 시작 fetch의 로컬·원격·PR HEAD는 `c18177736e44b93f9d469c22fd5caf661d52d823`, origin/main·PR base는 `500ad782a8f4c16621728a50d511be1b7d926523`이며 작업 트리는 깨끗했다. 완료 전 fetch에서도 같은 기준을 확인했다. 새 branch/PR, rebase, force push 또는 merge는 수행하지 않는다. 최종 후속 HEAD와 정확히 같은 headSha의 test·smoke CI 및 링크는 기존 PR의 최신 Validation에 기록한다. 아래 이전 검증 기록은 당시 결과로 보존한다.

### Web 입력 행 후속 변경

별도 `› 명령` log entry를 제거했다. 마지막 entry가 대기 prompt일 때만 command semantic을 오른쪽에 붙여 `[ 60/60 · 40/40 ] > 상태` 한 행으로 완료한다. 비동기 출력이나 완료한 입력 행 뒤에는 과거 prompt를 수정하지 않고 최신 서버 semantic으로 새 입력 행을 만든다. `pz_state.resource_prompt`는 서버 `world.text.resource_prompt()`의 입력 echo용 metadata이며 state 수신 자체로 화면에 prompt를 추가하지 않는다. 고정 prompt UI는 없다. currentServerPrompt와 lastRenderedPrompt를 구분하며 JS의 숫자/색/formatter 계산과 별도 ACK를 추가하지 않았다.

빈/공백 Enter는 command span/history 없이 서버 prompt만 추가한다. 직접 입력·버튼·채팅·실패·Account 명령은 같은 경로를 사용하며 성공 전송한 실제 명령만 history에 저장한다. keepalive idle은 echo/history가 없고 Evennia inputfunc에서 consume된다. 직접 제출은 bottom으로, 비동기 출력은 기존 scroll-lock으로 처리한다. 정적 cache version은 `prompt-input-row`다. 서버 gameplay/lifecycle·회복·정신력·enemy recovery·Telnet prompt channel은 변경하지 않았다.

### 후속 검증 (2026-10-04)

- `.venv\Scripts\python.exe scripts/dev.py check`, `node --check game/web/static/webclient/js/primal.js`, `git diff --check` 성공. game의 `python -m evennia collectstatic --noinput` 성공(2개 복사/211개 최신 유지). 수집 이후 static 변경 없음.
- `node --test scripts/tests/test_web_prompt.cjs`: 실제 primal.js의 DOM/WS 경계를 실행하는 9개 회귀 성공. 기본 행·비동기 피해·최신 회복 행·blank/history·버튼·60초 idle·연속 제출·scroll-lock·채팅/실패/Account/progressive 입력의 literal command semantic을 검사했다. 새 framework/의존성 없이 Node 표준 모듈을 사용하며 전체 Python suite의 tests.test_web_prompt로도 실행했다(Node 미설치 환경은 명시적 skip).
- `scripts/dev.py test tests.test_prompt tests.test_recovery tests.test_web_prompt tests.test_text --parallel 2 --reverse`: 40개 / 17.644s, runner 26.602s 성공.
- 전체 `scripts/dev.py test`: pure 147개 / 1.790s, integration 339개 / 123.478s, 합계 486개 성공, integration runner 132.635s. 이후 추가한 Telnet full-resource assertion의 formatter 인자 누락을 수정하고 `tests.test_recovery --parallel 2 --reverse` 14개 / 6.504s·runner 15.523s로 확인했다. 실행 코드 변경 없이 assertion만 보강했으므로 전체 검사를 반복하지 않았다.
- Quick smoke 51.212s, Full smoke 332.477s 성공. Full은 첫 round 2.818s, corpse decay 29.903s/respawn 44.815s/protection expiry 121.310s, 적 15초 유예/17→18 점진 회복, 실제 패배·본부·두 임무/보스·Portal+Server restart와 진행 보존을 확인했다.
- 격리 browser 1440/1100/390px에서 `[ 60/60 · 40/40 ] > 상태`·버튼 동일 행, 별도 command 행 없음, 실제 자동 공격 뒤 old 60 prompt 보존/current 57 입력 행, 자연회복 49→50의 최신 행에 입력, blank/space·history ↑↓·실패·채팅·접속자·종료를 확인했다. full 자원 상태의 96초 idle 동안 추가 로그가 없었고 위로 읽는 recovery scroll-lock과 직접 제출 bottom 이동을 확인했다. 390px 긴 명령은 한 입력 행에서 두 visual line으로 wrap되며 page/log 가로 overflow가 없다. 기존 3×3 compass/SURROUNDINGS 순서와 앱 console error/warning 없음도 확인했다.
- Telnet 정상 prompt channel의 `[ 60/60 · 40/40 ] >`, ANSI와 Web semantic 동등 내용·기존 progressive/Account 완료 동작은 자동 검증했다. 실제 OS IME, 외부 Telnet 클라이언트/font와 browser의 실제 progressive 추가 응답은 수동 미검증이며 renderer 경계와 Evennia lifecycle은 자동 검사했다. 별도 echo ACK를 추가하지 않아 제출 직전 미수신 state의 작은 race는 다음 authoritative 결과 prompt로 정상화된다.
- Quick·Full·browser 전후 플레이 DB size/mtime_ns/SHA256 불변. 테스트 서버/탭을 종료·정리했으며 DB/runtime/credential/log/screenshot은 Git 제외 work에만 보관했다. PR은 검토를 위해 OPEN으로 남기고 merge하지 않는다.

## PR #26 회복 리뷰·출력 lifecycle Objective (과거 기록)

기존 OPEN [PR #26](https://github.com/wonmin82/primal-zone/pull/26)의 회복 리뷰와 프롬프트 출력 lifecycle을 `codex/mental-recovery`에서 보강했다. 시작 fetch의 로컬·원격·PR HEAD는 `9fd2e1f5c1fb59cb8b3d560d44b36b2b089dba54`, origin/main과 PR base는 `500ad782a8f4c16621728a50d511be1b7d926523`로 일치했으며 작업 트리는 깨끗했다. 최종 검증 후 fetch에서도 기준은 동일했다. 새 PR을 만들거나 merge하지 않는다. 후속 최종 HEAD와 해당 HEAD의 test·smoke CI 링크는 PR Validation에 기록한다. 아래 최초 구현과 이전 PR 검증은 당시 기록으로 보존하며 현재 출력 정책보다 우선하지 않는다.

### 현재 구현과 정책

save_profile에서 prompt를 분리하고 이동 checkpoint는 조용히 저장한다. move_to의 transaction은 목적지 hook 거절도 profile/recovery/location rollback으로 처리하며 도착 화면은 성공 후 출력한다. 만료 effect는 과거 기여 반영 후 제거하고 future effect는 활성으로 취급하지 않으며 필요한 시작 시점만 예약한다. ENEMY_RECOVERY_DELAY_SECONDS를 timing SSOT의 canonical 이름으로 사용하고 구 PRIMAL_ENEMY_RESET_SECONDS fallback/import alias와 production 15초를 보존한다. profile v9·회복률·전투/경제 계약은 유지한다.

실제 Evennia 6.1 pre/post hook과 no-input/no-match/multimatch를 사용해 정상·실패·Exit·engine/account·progressive·묶음 입력의 마지막에 prompt 한 번을 출력한다. MuxAccountCommand가 caller를 Account로 바꿔도 시작 Explorer의 context를 종료하고 마지막 logout 때 중단 context를 제거한다. 빈/공백 Enter는 서버 최신 정상 경계 정산 후 prompt만 출력하며 echo/history/최근 명령/입력 대기 답변에 넣지 않는다. 자동 전투와 일반 비동기 알림은 prompt를 추가하지 않고 실제 정수 recovery만 다음 reactor turn에서 합쳐 출력한다. 패배는 피해·구조/손실·의무실 설명 뒤 HP 1, 로그인은 방/환영 뒤 최종 한 번이며 logout/shutdown은 출력하지 않는다.

Web은 고정 prompt DOM/state/CSS를 제거하고 서버 resource_prompt semantic을 메인 scrollback의 kind=prompt로 표시한다. 현재 숫자만 비율별 색을 적용하고 HP/정신력/XP HUD와 기존 scroll-lock/near-bottom scroll을 유지한다. 상세 정책은 [architecture의 lifecycle](architecture.md#프롬프트-출력-lifecycle), 실제 출력 예는 [text-examples](text-examples.md#자원-prompt)를 따른다.

### 후속 최종 검증 (2026-10-04)

- `.venv\Scripts\python.exe scripts/dev.py check` 성공. 전체 `scripts/dev.py test`는 pure 147개 / 6.156s, integration 337개 / 124.407s, 총 484개 성공이며 integration runner는 141.929s다.
- 관련 `scripts/dev.py test tests.test_prompt tests.test_recovery tests.test_item_interactions --parallel 2 --reverse`는 42개 / 18.653s·runner 27.749s 성공. 실제 dispatcher·progressive 완료·Account caller 변경·unpuppet/puppet·transport의 프롬프트 순서/중복, silent 이동/rollback, 경계 정산을 검사했다. pure future effect/만료 정리·timing fallback 테스트도 보강했다.
- 초기 전체 검사에서 command 사본의 객체 identity 기대와 실시간 10초 경계에 걸친 아이템 실패 비교를 발견했다. dispatcher key/실제 func 보존을 확인하고 아이템 suite 시계를 고정해 기존 전체 profile 불변 assertion을 유지했다. 브라우저에서 종료 후 재로그인 prompt 누락을 발견해 실제 Account command의 red 테스트로 재현하고 context 소유자/마지막 logout 정리를 수정한 뒤 위 최종 검사를 통과했다.
- Quick live smoke 49.295s 성공. 실제 일반/계정/실패/빈 입력 prompt, 종료 명령·재로그인 prompt 복원, 파티/화폐·상점·회복·진행 보존을 확인했다.
- Full live smoke 335.660s 성공. 첫 combat 2.923s, corpse decay 29.833s, respawn 44.779s, protection expiry 121.368s로 production 30/45/120초를 확인했다. 적 15초 유예/부분 회복 16→17·재교전 HP, 패배/본부 전체/두 임무·보스/실제 Portal+Server restart와 relogin을 통과했다.
- `node --check game/web/static/webclient/js/primal.js`, game 디렉터리의 `python -m evennia collectstatic --noinput`, `git diff --check` 성공. 최종 static 수집 뒤 JS/CSS 변경은 없다. 새 profile의 상태와 resource_prompt를 직접 생성해 최신 예시와 대조했다.
- 격리 browser의 1440px desktop·1100px 중간 폭·390px mobile에서 메인 prompt/기존 meter·compass/SURROUNDINGS, 일반/실패/빈 입력·history·묶음 마지막 한 번, 자동 전투 무출력/정수 자연회복, 실제 피해→구조/10칩 손실→의무실→HP 1 prompt, Doctor HP만/Bed 양 자원 회복, Account 접속자 및 종료 후 같은 캐릭터 재로그인 prompt를 확인했다. 위로 읽는 scroll-lock과 새 기록으로 이동도 유지했다. 앱 console error/warning·가로 overflow/clipping은 없다.
- Quick·Full·browser 전후 플레이 DB size/mtime_ns/SHA256은 733184 / 1790080153765082800 / `b1318296f505b9b7522fcbdedff7642a06cf055e9de72802198c70e6b8a7f700`로 불변이다. 소유한 테스트 서버/탭을 종료·정리했고 runtime/DB/credential/log/screenshot은 Git 제외 work에만 보관했다.
- 실제 OS IME와 별도 Telnet 클라이언트/font는 미검증이다. Telnet 정상 prompt 채널·ANSI·Web semantic 동등 내용과 출력 순서는 자동 검사했다. 회복 장비/소비품·정신력 소비/치료 기술은 추가하지 않았다. 최신 후속 HEAD의 두 CI가 성공하고 미해결 blocker가 없을 때 merge-ready로 보고하되 병합은 수행하지 않는다.

## PR #26 최초 구현 Objective (과거 기록)

정신력과 10초 주기 자연회복 시스템의 구현·검증·문서 정리를 독립 branch `codex/mental-recovery`에서 완료했다. 시작 fetch의 최신 origin/main은 `500ad782a8f4c16621728a50d511be1b7d926523`이며 작업 트리는 깨끗했다. PR #25는 MERGED이고 아래 경제 PR의 병합 준비/OPEN 표현은 과거 기록이다. 구현 커밋은 `1e87004f10f14acaf392adefd4ea975e15489e4f`다. 사용자의 후속 PR 생성 요청에 따라 같은 branch를 push하고 main 대상 PR과 최종 HEAD의 test·smoke CI를 확인한다. 병합은 요청되지 않았다.

현재 정신력과 최대치·v9 migration, DB 없는 accrue/commit 계산, Room/equipment/timed effect source, offline 옛 위치 batch, 살아 있는 session reload 보존, 플레이어 단일 경계 예약과 적 15초 유예/점진·lazy 회복을 구현했다. 진료는 HP만, 휴식은 HP·정신력을 채우며 firstaid/의술·기존 경제를 보존한다. Web 정신력 meter와 로그와 분리된 prompt를 추가했다. 회복 장비/소모품·정신력 소비/치료 기술은 범위 밖이다.

### 완료 검증 (2026-10-03)

- 최종 `.venv\Scripts\python.exe scripts/dev.py test`: pure 145개(3.441s), integration 325개(141.898s), 합계 470개 성공, integration runner 152.662s. 신규 recovery pure 12개·integration 14개이며 기존 migration·경제·전투·장비·의료 assertion을 유지했다.
- 관련 `tests.test_recovery --parallel 2 --reverse`: 14개 성공(7.245s, runner 16.981s). 전투·장비·아이템 이동·정산·상점·지역·환경의 관련 reverse/parallel 검사 73개 성공(57.460s, runner 67.083s), restart harness 검사 10개 성공.
- `scripts/dev.py check`, `node --check game/web/static/webclient/js/primal.js`, `git diff --check` 성공. 최종 정적 파일의 collectstatic 성공(213개 최신 유지), 실제 새 profile의 상태·능력·경험치·기술·소지품·장비·능 도움말·prompt를 문서 예시와 대조했다.
- Quick live smoke 53.424s 성공: 실제 10초 경계 정신력 증가, 시체 화폐·보호·respawn·구매/판매·재로그인 진행 보존. 이후 Full 전용 fixture/restart snapshot·테스트 기대·0 prompt ANSI 강조 보정은 Quick의 검증 경로에 영향을 주지 않아 기존 성공 근거를 재사용했다.
- Full live smoke 361.952s 성공: 첫 라운드, 시체 decay 29.542s/respawn 44.506s/보호 종료 120.250s, 적 15초 유예 후 부분 회복 18→20(29.623s), 재교전 HP 보존, 실제 패배/진료/휴식·본부 전체·두 임무/보스·Portal+Server restart/relogin. 실행 중 snapshot 이후의 정상 전투까지 보존하려고 프로세스 종료 DB snapshot과 restart 결과를 비교한다.
- 초기 Full은 자연회복으로 저체력 fixture가 적을 처치해 패배 검사에 실패했다. 정상 Lv1 fixture와 실제 갈퀴사냥룡 교전으로 수정했다. 두 번째 Full의 restart 비교는 실행 중 snapshot과 종료 사이의 라운드를 포함하지 않아 실패했고, 종료 시점 snapshot으로 경합을 제거했다. production 수치와 진행 보존 assertion은 바꾸지 않고 최종 Full을 통과했다.
- 격리 browser에서 1440px desktop·1100px 중간 폭·390px mobile, HP/정신력/XP 분리·prompt·자연회복 중 로그 개수 불변·SURROUNDINGS/compass 유지·지혜 투자·의무관 진료의 정신력 비회복·HP full/정신력 부족 상태의 침대 버튼을 확인했다. 앱 console error/warning과 가로 overflow 없음. 실제 OS IME와 별도 Telnet 클라이언트/font는 미검증이며 입력 composition 코드는 변경하지 않았다. Telnet prompt 채널/ANSI/현재 숫자만 semantic 색 적용은 자동 검사했다.
- Quick·Full·browser의 play DB size/mtime_ns/SHA256 불변: 733184 / 1790080153765082800 / `b1318296f505b9b7522fcbdedff7642a06cf055e9de72802198c70e6b8a7f700`. 성공 임시 서버는 종료·정리했고 실패 진단은 gitignored work 아래에 보존했다. runtime/DB/credential/screenshot은 소스에 포함하지 않는다.
- 구현 완료 당시 최종 fetch에서도 origin/main은 시작 SHA와 같았고 로컬 커밋까지 진행했다. 후속 PR 준비 fetch에서도 main과 실행 코드는 동일했다. 변경은 이 인계 문서뿐이므로 위 로컬 성공 근거를 재사용하며 실제 PR URL·최종 HEAD·새 CI 결과는 PR 본문과 GitHub Actions에서 확인한다.

### PR #26 CI 후속 검증

[PR #26](https://github.com/wonmin82/primal-zone/pull/26)을 생성했다. 초기 문서 HEAD `477bb6f762905447592b48a13f7c97233118a2a0`의 test CI는 성공했지만 Linux Quick 흐름이 첫 회복 지급 전에 끝나 정신력 증가 assertion이 실패했다. smoke에서 실제 정신력이 증가한 state를 두 경계와 통신 여유(최대 30초) 안에 기다리도록 보강했다. 고정 sleep이나 회복 규칙·production 타이머 변경은 없다. 후속 `world.test_smoke` 10개(7.901s, runner 11.677s), check, Quick 60.222s와 play DB fingerprint 불변을 확인했다. 전체 게임 테스트·Full·browser는 게임/정적 코드가 같아 위 성공 근거를 재사용한다. 후속 최종 HEAD의 test·smoke CI와 SHA는 PR Validation에 기록한다.

### 다음 작업

새 PR에서 현재 구현을 리뷰한다. 실제 회복 장비·시간제 회복 소비품·정신력 소비/치료 기술은 별도 요청에서 다룬다. PR은 검토를 위해 OPEN 상태로 남기며 병합하지 않는다.

## 이전 PR #25 병합 준비 Objective (과거 기록)

보급칩 경제와 [PR #25](https://github.com/wonmin82/primal-zone/pull/25)의 후속 리뷰 네 항목 구현·검증을 완료했다. 사용자의 병합·소스 브랜치 삭제 요청에 따라 최종 인계 문서를 정리한다. 병합 준비 fetch에서 로컬/원격/PR 구현 HEAD는 `f81eb3a51a0cf6d65c6d3f89ee4fc09c001d4195`, origin/main과 PR base는 `0229a2275f33436a74f75274c94e464c8077b3a2`로 일치하고 작업 트리는 깨끗했다. 최신 main을 이미 포함하므로 rebase 재작성은 필요하지 않다. 아래 과거 OPEN·병합 금지 설명은 당시 작업 범위이며 현재 승인 범위보다 우선하지 않는다.

이 문서는 병합 전 최종 인계다. 문서 후속 HEAD의 test·smoke와 병합 후 main의 CI를 각각 확인하며, 실제 최종 HEAD·병합 커밋·브랜치 정리 결과는 PR과 GitHub Actions에서 확인한다. 구현 완료 이후의 신규 기능은 별도 요청으로 진행한다.

### PR #25 후속 리뷰 구현과 검증 (2026-10-03)

Web 기본 판매는 1개이며 판매 가능한 비착용 복사본이 2개 이상일 때만 별도 모두 판매/총액 action을 제공한다. 일반 전달·버리기·보관·판매는 공통 `lighting.discard_device_state_if_unowned`로 마지막 광원 소유권 상실 시 장치 상태를 제거하며 여분은 유지한다. 재구매 시 과거 건전지가 부활하지 않는다. protected currency는 고정 `eligible_players`와 감소하는 `remaining_shares`를 분리한다. 자기 몫이 0인 원래 참여자도 다른 참여자의 남은 지급을 trigger하고, payout은 remaining_shares만 weight로 쓴다. 현재 파티를 권한 계산에 다시 조회하지 않으며 offline persistent Explorer에도 지급한다. 객체 누락은 전체 rollback한다. expiry 후 free와 decay의 quantity/자격/잔여 몫/reservation/deadline 보존, 초기 PR shares·legacy item의 읽기 전용 normalize 호환을 유지한다. Web `display_label`은 8칩, `take_target`은 칩/칩 2로 분리했고 take_command를 그대로 전송한다. profile version 8·credits·기존 가격/XP/item 배정은 변경하지 않는다.

새 pure 3개·integration 7개를 추가하고 기존 판매/파티 snapshot 검사를 보강했다. 먼저 25개 red 실행에서 판매 의미·광원 state·권리/표시 필드의 실패를 재현했다. 관련 경제/loot/reward/shop/Web/lighting/item interaction `--parallel 2 --reverse` 108개는 41.049초·runner 50.189초 통과, 이후 추가 경계 3개는 8.924초·runner 17.969초 통과했다. 최종 check 통과, 전체 test는 pure 133개 / 1.902초·integration 311개 / 128.939초·total 444개·통합 runner 139.261초 성공이다. 최초 Quick은 전체 테스트·Full과 동시 실행 중 outsider claim 거절 메시지 timeout으로 실패했고 당시 플레이어 state에는 사냥이 이미 종료되어 있었다. 실패 DB/로그를 보존했고 코드 변경 없이 재실행한 Quick은 66.657초 성공했다. Full은 335.086초 성공: 첫 round 2.970초·decay 29.892초·respawn 44.766초·protection 123.261초, 본부/두 임무/보스/실제 Portal+Server restart·권리/잔액 보존을 확인했다. 두 최종 smoke와 browser 전후 플레이 DB SHA256/mtime_ns/size는 동일했다.

computer-use skill로 별도 DB/일반 fixture의 desktop 1440px·mobile 390px을 확인했다. 붕대 3개 기본 판매로 1개/4칩, 남은 2개 모두 판매로 8칩이 지급됐다. 강철마체테 3개/착용 1개에서는 모두 판매 60칩 후 착용 1개가 남았다. 두 참여자 화폐 fixture(각 4칩)에서 7칩 회수 후 자기 몫 0인 요청자의 1칩 버튼은 활성 상태였으며 다른 참여자에게만 마지막 1칩을 지급하고 양쪽 화면을 갱신했다. 시체/ground의 8칩 표시와 20칩 버리기, 칩 1/칩 2 버튼의 정확한 selector/회수, 기존 3×3 compass와 SURROUNDINGS 순서·가로 overflow/clipping 없음을 확인했다. 앱 소스 오류/경고는 관찰되지 않았고 두 Chrome 탭에서 각각 외부 listener/message-channel 계열 오류 3건을 별도 기록한다. node --check와 격리 game의 python -m evennia collectstatic --noinput 성공, CSS/JS cache query는 supply-chip-review다. browser viewport/탭과 소유한 서버/격리 DB는 정리했으며 screenshot/log·최초 실패 진단은 Git 제외 work에만 있다. 실제 OS IME는 미검증이다.

후속 구현 HEAD `f81eb3a51a0cf6d65c6d3f89ee4fc09c001d4195`와 [Game checks run 37077328246](https://github.com/wonmin82/primal-zone/actions/runs/37077328246)의 headSha를 직접 대조해 test·smoke 모두 success를 확인했다. 이번 병합 준비 변경은 인계 Markdown뿐이며 실행 코드·테스트·정적 파일은 동일하므로 위 로컬 검증을 반복하지 않고 문서/링크/차이와 git diff --check를 확인한다. 문서까지 포함한 최종 HEAD의 CI는 별도로 대조한다. 초기 PR shares에서 이미 삭제된 참여자 key는 원본 정보가 없어 자격을 복원할 수 없고, 남아 있는 key로만 호환 해석한다. 최초 구현 검증과 이전 PR 기록은 아래에 보존한다.

### 최초 경제 구현 시작 기준 (과거 기록)

PR #24는 MERGED이고 시작 fetch의 최신 origin/main은 `0229a2275f33436a74f75274c94e464c8077b3a2`였다. 깨끗한 main에서 `codex/supply-chip-economy`를 생성해 경제 기능을 구현하고 PR #25를 만들었다. 아래 수치는 최초 구현 당시 기록이다.

### 최초 구현과 검증 (과거 기록)

보급칩 currency SSOT/공통 formatter, 소지품 잔액, give/drop/부분·전체 take, typed item/currency와 legacy read, 처치 XP 즉시/화폐 corpse snapshot, party remaining shares·그룹 보호·expiry/decay, ITEMS.value 가격과 가치/판매, 서버 소유 Web action을 구현했다. 적 8종 화폐와 기존 14개 구매 가격·XP 분배·profile version 8 및 credits 저장 키는 유지한다. 새 PR의 최종 HEAD/CI 링크는 PR Validation에 기록한다.

2026-10-03 관련 경제/상점/전리품/보상/선택자/지역/텍스트 90개를 `--parallel 2 --reverse`로 실행해 46.738초·runner 56.087초에 통과했다. 추가 Web 상태 3개도 통과했다. 최종 `scripts/dev.py check`와 전체 `scripts/dev.py test`는 pure 130개(2.081초)·integration 304개(109.920초)·total 434개·통합 runner 119.070초에 통과했다. 최초 전체 실행에서 currency 추가에 따른 기존 Web ground 개수 기대를 발견해 화폐 종류·금액·권한 assertion까지 보강했다.

최종 Quick 50.463초, Full 296.236초 성공. Full의 실제 첫 round 2.813초·corpse→ground 29.955초·respawn 44.867초·protection 121.670초를 확인했다. 파티 부분 화폐 분배·expiry 후 outsider 자유 회수·가치/판매/재구매·재로그인 잔액 보존, Full의 본부/두 임무/보스/Portal+Server restart와 미회수 loot 보존을 검증했다. 첫 Full은 판매 후 재구매를 추가한 fixture 예산 부족으로 실패했고 준비금만 150칩으로 조정한 뒤 최종 성공했다. 실제 플레이어 시작 잔액 20칩과 게임 가격은 변경하지 않았다. 플레이 SQLite의 SHA256/mtime_ns/size는 smoke 전후 모두 동일했다.

격리 DB/일반 fixture의 브라우저 desktop 1440px·mobile 390px에서 상태/소지품 잔액, 20칩 버리기·바닥 화폐 버튼·전체 회수, 상품 가격·가치·판매, 처치 직후 잔액 불변·20칩 초과 회수 거절·2칩 파티 분배 후 두 화면 각각 +1칩, currency decay 및 기존 item 버튼을 확인했다. 가로 overflow 없고 compass/SURROUNDINGS 순서를 유지했다. 앱 오류/경고는 관찰되지 않았으나 Chrome에서 비동기 listener/message channel 오류 3건이 기록되어 별도로 남긴다. OS IME 자체는 미검증이다. `node --check` 성공, 격리 game의 fixture setup에서 collectstatic 완료, 기본 formatter 7종의 실제 출력을 text-examples와 대조해 일치했다. 브라우저 소유 프로세스/탭은 종료했으며 정책이 삭제를 차단한 임시 브라우저 DB/자료는 Git 제외 work 아래에 보존했다. 일반 개발 서버와 DB는 변경하지 않았다.

## 이전 PR #24 Objective (과거 기록)

PR #23은 MERGED이며 시작 main은 `d30fa74f25166cf79565b205a028ae10a02deffc`다. 현재 작업은 기존 OPEN [PR #24](https://github.com/wonmin82/primal-zone/pull/24)의 **의료 용어 체계 정리**이며 `codex/command-vocabulary-help`에서 이어간다. 시작 fetch 후 로컬·원격·PR HEAD는 `2c425bf55339ab924b662a165189d446945593dd`로 일치했고 작업 트리는 깨끗했다. origin/main은 기존 base와 동일하다. 새 PR을 만들거나 merge하지 않는다. 아래 PR #23 OPEN 설명과 과거 검증 수치는 당시 기록으로 보존한다.

### 현재 구현

소지품(가방/가진거/i/인벤토리)·상품(별칭 없음)·도망(flee)·응급처치(붕대/firstaid)·진료(treat)·내려로 어휘를 정리한다. 방향 SSOT에 8방향 초성을 추가하고 정보 단축어는 상/능/기/장/소다. 가는 글로벌에서 제거하고 개인 이름으로 허용한다. 단축어는 고정 조회, 줄임말은 캐릭터 설정이다. 도움말은 여섯 분류 root/category/detail/input이며 실제 command detail이 category보다 우선한다. 의료는 분야, 의술(medicine)은 숙련, 응급처치(firstaid)는 붕대 기술, 진료(treat)·휴식(rest)은 시설 서비스, 회복은 HP 증가 결과다. 치료/힐/heal은 미래 정신력 기반 자신·타인 치료 기술용 예약 이름이며 실제 기능은 구현하지 않는다.

profile v8은 heal Rank/queued action을 firstaid로 변환하고 저장된 명령 위치만 canonical로 migration한다. 새 예약 이름 충돌 데이터는 _개인[번호]로 보존하고 exact nested 참조도 갱신한다. 진행 데이터와 read-only snapshot·전체 삭제 직접 요청/확인 safety는 유지한다. 승강기 층 선택자는 자동 하차하고 다른 승객은 남으며 내려는 같은 helper를 사용한다. 새 puppet은 출정 대기실, live-session reload at_sync는 기존 위치다. Web canonical 버튼과 공통 asset version을 갱신한다. Full smoke에서 Portal+Server 재시작 시 격리 SQLite의 read→write 경합이 재현되어 smoke 전용 DB만 IMMEDIATE transaction/30초 busy timeout으로 직렬화하고 회귀 검사를 추가했다. 일반 플레이 DB 설정과 production timer는 변경하지 않았다.

### 의료 용어 후속 검증 (2026-09-30)

medicine 표시명을 의술로 바꾸고 미래 예약 이름에 힐을 추가했다. v7의 힐 충돌은 기존 _개인[번호] 정책과 exact nested 참조 갱신으로 보존한다. historical 치료→진료·heal→응급처치와 v7 고정 단축어 계약, profile version 8, 실제 응급처치·진료·휴식 규칙은 유지한다. 새 profile의 능력·경험치·기술과 응급처치/진료/휴식 도움말을 생성해 현재 문서와 대조했고 Web 성장 이름도 서버 PROFICIENCIES에서 파생됨을 확인했다. README·architecture·command-shortcuts·text-examples·playtest 현재 절차를 갱신하고 과거 기록은 보존했다.

관련 `scripts/dev.py test world.test_vocabulary tests.test_vocabulary tests.test_text world.test_medical tests.test_medical --parallel 2 --reverse`는 41개 / 19.370초·runner 33.165초 통과했다. 최종 `scripts/dev.py check` 통과, 전체 `scripts/dev.py test`는 pure 123개 / 1.679초·integration 293개 / 100.727초·total 416개·통합 runner 109.625초 통과했다. `git diff --check` 통과. 최종 서비스 출력 assertion 보강도 위 전체 검사에서 검증했다. 이번 diff는 Python 표시명·예약 상수·테스트와 Markdown이며 gameplay 공식·타이머·Web static은 변경하지 않아 로컬 smoke/Full·browser·node·collectstatic·OS IME는 반복하지 않았다. 기존 PR #24에 후속 commit을 push하고 최종 HEAD와 두 CI job의 headSha·결과는 PR Validation에 기록한다. 치료/힐/heal의 실제 기술과 정신력 시스템은 구현하지 않았으며 PR은 merge하지 않는다.

### 기존 구현 검증 및 인계 (과거 기록)

최종 `scripts/dev.py check` 성공, 전체 `scripts/dev.py test`는 pure 120(1.767초)·integration 292(102.089초)·total 412·runner 110.948초 성공이다. 관련 50개는 `--parallel 2 --reverse`에서 22.607초·runner 31.509초 통과했다. 최종 Quick live smoke는 48.391초 성공, Full은 294.325초 성공하며 실제 첫 공격 2.928초·시체 만료 29.868초·적 재생성 44.762초·전리품 보호 만료 121.177초와 Portal+Server 재시작을 검증했다. 첫 Full 시도에서는 재시작 중 SQLite 잠금이 재현됐고 smoke 전용 DB 설정을 수정한 뒤 최종 Full을 성공시켰다. 일반 플레이 SQLite는 두 smoke의 SHA256·mtime_ns·size가 시작 전 값과 동일했다.

격리 브라우저의 desktop 1249px·중간 1100px·mobile 390px에서 소지품/응급처치/도망·진료·상품 버튼, 3×3 방향도·SURROUNDINGS 순서, 승강기 3층 자동 하차, Credits 구매, 재로그인 대기실 시작·진행 보존을 확인했다. 앱 console error/warning과 가로 overflow는 없었다. 실제 체력 가득 상태에서 진료/붕대 버튼의 명령 연결과 정상 거절을 확인했으며 OS IME 입력 자체는 미검증이다. `node --check`와 격리 환경 collectstatic도 성공했다. 상세 어휘/migration/예약·묶음 한계는 [command-shortcuts.md](command-shortcuts.md), 구조는 [architecture.md](architecture.md), 최신 수동 절차는 [playtest.md](playtest.md) 앞부분을 따른다.

기능 commit은 `df1648e4efb8493fa2a130414146cedd158e2724`, 새 [PR #24](https://github.com/wonmin82/primal-zone/pull/24)는 OPEN·base main·branch `codex/command-vocabulary-help`다. 기능 commit의 [Game checks run 36637618558](https://github.com/wonmin82/primal-zone/actions/runs/36637618558)는 headSha 일치, `test`·`smoke` 모두 success였다. 이 인계 기록을 추가한 뒤 바뀌는 최종 PR HEAD의 CI는 PR Validation과 GitHub Actions에서 다시 확인한다.

## 이전 PR #23 Objective (과거 기록)

현재 작업은 열린 [PR #23](https://github.com/wonmin82/primal-zone/pull/23)의 **지도 방향 통합 정렬 / 옥상 콘텐츠 불변조건 / stable Room ID 독립성** 리뷰 반영이다. `codex/eight-direction-navigation`에서 계속 작업한다. 시작 fetch 후 로컬 HEAD·원격 branch·PR HEAD는 모두 `ec3fd38bde0b73102442cd70e3d45ad27c27814a`, origin/main은 `6b2adcc306cdf8108232c036de1b447c93f95621`로 동일했고 작업 트리는 깨끗했다. 아래 최초 구현·검증 수치는 당시 기록으로 보존한다. 새 PR을 만들거나 merge하지 않는다.

### PR #23 후속 리뷰 반영 (2026-09-30)

지도는 실제 출구와 blocked 출구를 합쳐 한 번 정렬하며 canonical 전체 순서와 특수 출구의 입력 순서, 방문/미탐사/폐쇄/현재/semantic 표시를 보존한다. `ROOF_SIDES`는 기존 여덟 stable ID를 명시적으로 고정하여 command alias 정책과 분리했다. Room/Exit ID rename·profile 변경·migration은 없다. `headquarters_errors()`는 옥상 9개 Room의 비어 있지 않은 `hints`·`requires`·`quest`·`items`·`rewards`를 차단하고, 전체 `errors(interactables)`는 해당 Room의 모든 NPC/interactable/service 배치를 차단한다. Room schema에서 별도 progression 필드는 확인되지 않았으며 환경·시설 조명 등 관계없는 필드는 새로 금지하지 않았다. 일반 서비스 Room과 Web/CSS/JS·context action 정책은 바꾸지 않는다.

기존 stable mapping의 canonical key/정확한 ID 집합 검사를 보강하고, 회귀 테스트 5개를 추가했다. 지도 혼합 순서/semantic/방문 상태·특수 출구 fallback 2개, 정상 `INTERACTABLES`와 옥상 전체 배치 금지 1개, 모든 옥상 Room의 다섯 금지 필드 검출과 빈 값 허용 2개다. `world.test_directions world.test_headquarters` 단독 순수 검사는 16개 / 0.074초 통과했다. 관련 `scripts/dev.py test world.test_directions world.test_headquarters tests.test_directions tests.test_headquarters tests.test_integration tests.test_regions --parallel 2 --reverse`는 69개 / 64.682초·runner 77.096초 통과했다.

최종 `.\.venv\Scripts\python.exe scripts/dev.py check` 통과, `scripts/dev.py test`는 pure 117 / 1.819초·integration 285 / 108.329초·total 402·통합 runner 117.999초 성공이다. `scripts/dev.py smoke`는 49.269초 성공했고 기존 파티/점유/전리품/lifecycle·옥상/승강기/구매/재접속을 유지했다. owned process/temp를 정리했고 play SQLite의 SHA256·mtime_ns·size는 최초 기록과 동일했다. 근거는 Git 제외 `work/direction-review-related.log`, `work/direction-review-full.log`, `work/direction-review-quick.log`다. `git diff --check` 통과. 실행 코드·테스트 검증 이후 문서에 결과만 반영했다. Full은 production timer를 변경하지 않아 미실행이며 JS/node/collectstatic/browser/OS IME는 Web 코드 변경이 없어 반복하지 않았다. 후속 commit을 기존 PR #23에 push하고 최종 HEAD 및 두 CI job의 실제 결과를 PR Validation에서 대조한다.

### 최초 구현 시작 기준 (2026-09-29, 과거 기록)

본부 재설계 1~7단계/P0 smoke와 개인 줄임말·묶음 명령은 완료된 선행 작업이다. 현재 독립 작업은 **8방향 이동 / 고정 Web·Telnet 방향 인터페이스**다. `E:\Work\primal-zone`의 원격이 `wonmin82/primal-zone`임을 확인했고 status·unstaged/staged diff는 깨끗했다. fetch 후 시작 HEAD/origin/main은 `6b2adcc306cdf8108232c036de1b447c93f95621`, PR #22는 MERGED, 열린 PR은 없었다. 해당 main [Game checks run 36575655451](https://github.com/wonmin82/primal-zone/actions/runs/36575655451) success를 확인하고 최신 main에서 `codex/eight-direction-navigation`을 생성했다. 과거 단계의 OPEN/부두 서비스 설명과 검증 수치는 시점 기록으로 보존하며 현재 상태보다 우선하지 않는다.

### 8방향 이동 / 고정 compass (2026-09-29)

방향 SSOT는 `world/content/directions.py`의 canonical 8개·시계방향 순서·alias·opposite·3×3 좌표다. alias/reverse는 파생하며 기존 `world.content.OPPOSITES`는 동일 mapping의 호환 export만 남긴다. `items.py`의 alias 정의와 integrity의 별도 reverse dict는 제거했다. 실제 Exit/bootstrap, blocked alias, 지도/Web 출구 순서, 줄임말 예약 이름이 같은 정의를 따른다. 대각선 command·새 시스템 단축어·profile migration은 추가하지 않는다.

본부는 34개 Room이다. `support_roof`에서 `support_roof_n/ne/e/se/s/sw/w/nw`로 이동하고 각 주변 Room은 opposite Exit 하나로 중앙에 돌아온다. 9개 옥상 Room 모두 safe·적 없음·outdoor/natural이며 주변에 NPC/action/hint/quest/reward를 넣지 않는다. 기존 1~3층 graph·서비스·승강기 정류장과 승강기 방향 Exit 금지는 유지한다. 두 번 bootstrap의 Exit stable/DB ID·alias·object 수·player profile/location 보존과 stale 없음, 실제 Korean/English 왕복·대각선 보기·묶음 왕복을 자동 검증한다.

Web DOM은 SURROUNDINGS → PARTY → OBJECTIVE → TRAINING → EQUIPMENT & SUPPLIES, panel 내부는 고정 3×3 compass → hint/context다. 빈 방향은 버튼만 없고 행/열은 유지한다. old connector/has-direction CSS·JS는 제거하고 특수 Exit fallback과 기존 action 선정 정책을 유지한다. CSS/JS cache query는 둘 다 `eight-directions`다. Telnet은 visible 30 cells × 5줄, `[현재]` 시작 12열과 fullwidth 중앙/대각선 축을 사용하며 semantic token을 보존한다. 기존 `row()`의 표시 폭 정책을 작은 `display_width()` helper와 공유한다.

격리 smoke DB·일반 Player 계정으로 desktop 1424px·701px grid·390px mobile을 확인했다. 옥상 8↔1, 승강기 0개, 상점의 여러 action에서도 grid 높이/중앙의 panel 내 위치가 같다. 대각선 clipping·horizontal overflow·앱 console error/warning이 없었고 승강기 층 선택/하차·무기 구매 버튼도 정상이다. 격리 game setup에서 collectstatic을 실행하고 새 query가 실제 로드됨을 확인했다. viewport/탭/owned process/temp를 정리하고 play SQLite SHA256·mtime_ns·size 불변을 확인했다. screenshot/log는 Git 제외 work에만 둔다. 실제 OS IME·Telnet font 렌더링은 미실행이며 Full은 production timer를 바꾸지 않아 반복하지 않는다.

최종 `.\.venv\Scripts\python.exe scripts/dev.py check`와 `node --check game/web/static/webclient/js/primal.js`, `git diff --check`는 통과했다. 최종 `scripts/dev.py test`는 pure 115 / 1.975초, integration 282 / 139.278초, total 397, 통합 runner 151.385초 성공이다. `scripts/dev.py smoke`는 68.232초 성공했고 process/temp 정리와 play DB SHA256·mtime_ns·size 불변을 실제 확인했다. 방향/본부/줄임말/semantic text/Web 관련 `--parallel 2 --reverse` 69개는 56.115초·runner 66.036초 통과했다. 개발 중 기존 dict 순서·가변 방향도·asset cache key·전체 Room 수 기대를 새 계약에 맞췄고 마지막 이동 보기의 Evennia `msg(text=(appearance, ...))` 전달 검사는 단독 1개 / 4.996초·runner 17.423초 재검증 및 위 전체 검사에서 통과했다. 최종 추가 `tests.test_integration tests.test_environment tests.test_regions tests.test_directions --parallel 2 --reverse`는 59개 / 50.133초·runner 62.257초 통과했다. assertion을 삭제하거나 무관하게 완화하지 않았다. 근거는 Git 제외 `work/eight-directions-related.log`, `work/eight-directions-full.log`, `work/eight-directions-movement.log`, `work/eight-directions-regression.log`, `work/eight-directions-quick.log`와 browser screenshot/log다.

전체 성공 이후 실행 코드·테스트는 변경하지 않고 문서에 결과만 반영한다. 최종 fetch에서 main 포함 여부를 확인한 뒤 기능 단위 한 커밋으로 push하고 새 PR을 생성한다. 최종 PR HEAD와 test/smoke workflow headSha 대조 결과는 PR 검증 항목에 기록한다. PR은 병합하지 않는다.

### 개인 줄임말 PR 생성 시점의 Objective (과거 기록)

본부 재설계 1~7단계와 P0 smoke 인프라는 PR #13~#21으로 병합·closeout 완료됐다. 현재 작업은 본부 8단계가 아닌 **개인 줄임말 / 묶음 명령** 독립 기능이다. 시작 시 main 작업 트리는 깨끗했고 status·unstaged/staged diff 확인 및 fetch 후 HEAD/origin/main은 모두 `a748d284d42935ce42ca151cf9e8c36c6942b731`이었다. PR #21 MERGED와 병합 후 [Game checks run 36547264547](https://github.com/wonmin82/primal-zone/actions/runs/36547264547)의 test/smoke success를 실제 확인했다. 해당 과거 main CI는 pure 101·integration 252·total 353, runner 100.197초·Quick 18.965초다. 최신 main에서 `codex/personal-command-shortcuts`를 생성했다. 아래 단계별 OPEN·부두 서비스 설명은 당시 기록이며 현재 상태보다 우선하지 않는다.

### PR #22 리뷰 반영 (2026-09-29)

이번 작업 시작 시 PR #22는 OPEN, branch는 `codex/personal-command-shortcuts`, 로컬/원격 PR HEAD는 `7cb85ad37ac5fb5516769acd1db03a855aeba87c`였다. 작업 트리는 깨끗했고 status·unstaged/staged diff 확인 및 fetch 후 origin/main은 `a748d284d42935ce42ca151cf9e8c36c6942b731`로 동일했다. 새 PR 없이 기존 branch에서 P1 코드/테스트와 P2 문서만 수정한다.

P1: `Shortcuts.run()`의 전체 삭제 request/confirmation은 각각 top-level 직접 입력만 허용한다. 기존 `primal_sequence_leaf`를 pending 읽기·생성·소비·검증·profile 변경 전에 검사하므로 묶음/개인 줄임말의 간접 request는 pending을 만들거나 갱신하지 않고 간접 confirmation은 기존 valid pending을 보존한다. 이후 직접 confirmation은 TTL/fingerprint가 유효하면 정상 동작한다. 기존 확인 단독 차단·60초·목록 변경 취소·정상 확인 one-shot·0개·캐릭터 격리·logout/shutdown 계약은 유지한다. 새 integration 5개가 request+confirm 묶음/초기화 shortcut·간접 request·간접 confirmation·이후 직접 확인을 검증하며 기존 안전 테스트도 그대로 유지한다.

P2는 구현 확장 없이 알려진 한계로 기록한다. 묶음은 단순 comma split이므로 literal comma가 있는 command는 직접 segment로 표현할 수 없다. 단일 개인 줄임말로 저장한 뒤 `인사, 상태 해`로 참조할 수 있다. progressive 사전 검사는 시작 시점 merged cmdset 기준이며 이동/상태 변경 후 새 CmdSet에 나타나는 progressive command까지 예측하지 않는다. 현재 `game/commands`의 실제 `func()` 5개를 AST로 확인했고 generator/coroutine은 없었다. escaping/quoting·future CmdSet 합성·runtime 중단/partial execution 정책·completion/result contract는 향후 설계 후보이며 이번 PR에서 구현하지 않았다. 상세 SSOT는 [command-shortcuts.md](command-shortcuts.md)다.

관련 `world.test_command_shortcuts tests.test_command_shortcuts tests.test_integration tests.test_text --parallel 2 --reverse`는 63개 / 21.685초·runner 29.934초 통과했고 `scripts/dev.py check`도 통과했다. 최종 `scripts/dev.py test`는 pure 109 / 2.144초·integration 274 / 89.825초·total 383·통합 runner 99.229초 성공이다. `scripts/dev.py smoke`는 54.160초 성공했고 owned process/temp 정리 및 play SQLite SHA256·mtime_ns·size 불변을 확인했다. 근거는 Git 제외 `work/shortcuts-review-related.log`, `work/shortcuts-review-full.log`, `work/shortcuts-review-quick.log`다. 아래 378개/46.471초는 최초 구현 시점 결과이며 리뷰 수정의 새 결과로 재사용하지 않는다.

Full/브라우저/OS IME는 미실행이다. 이번 변경은 destructive 관리 guard와 문서이며 Web UI/asset/gameplay timer를 바꾸지 않아 관련 integration·전체 test·Quick으로 검증했다. JS가 동일하므로 node/collectstatic도 반복하지 않았다. 최종 fetch의 origin/main은 동일했고 이미 포함하므로 rebase로 커밋을 재작성하지 않았다. 전체 검사 이후 실행 코드·테스트는 변경하지 않고 문서에 결과만 반영했다. 후속 commit의 최종 PR HEAD와 test/smoke CI는 push 후 workflow headSha를 직접 대조해 PR Validation에 기록한다.

### 개인 줄임말 / 묶음 최초 구현 (2026-09-29, 과거 검증 기록)

`해` 인자의 콤마만 sequence separator로 사용하며 일반 콤마 채팅은 유지한다. `줄임말 추가 이름 정의`는 = 없는 prefix 문법이고 목록·교체·개별 삭제·중첩·exact-match를 지원한다. profile v7의 `command_shortcuts`는 캐릭터별 명령 list이며 v1~v6 migration은 기존 게임 데이터를 보존한다. 실제 명령·lock·시스템 shortcut이 개인 설정보다 우선한다. parser 조회는 `profile_snapshot()`으로 저장 부작용이 없다.

순수 helper는 `commands/shortcuts.py`, 서버 관리/dispatch는 `commands/command_shortcuts.py`, parser fallback은 `server/conf/cmdparser.py`다. 실행 전에 전체 재귀 flatten과 순환/깊이 5/명령 10/문자 합계 1000 검사를 완료하고 각 `execute_cmd()` 완료를 기다린다. 개별 gameplay 실패는 다음 실행을 막지 않는다. 설치된 Evennia 6.1의 progressive engine `func` 완료 계약 때문에 시작 cmdset에서 식별되는 해당 명령의 묶음 자동화는 사전 거절하며 단독 실행은 유지한다. 동적 CmdSet의 보장 경계는 위 리뷰 기록을 따른다.

전체 삭제 요청은 캐릭터 `ndb.shortcut_delete_all_request`의 monotonic timestamp + 목록 SHA256 fingerprint다. 요청만으로 삭제하지 않고, 확인 단독 입력도 삭제하지 않는다. 60초 내 동일 목록인 경우만 한 번 삭제하며 등록·교체·개별 삭제·로그아웃·종료에서 무효화한다. 0개 요청·캐릭터 간 권한 공유·확인 재사용을 차단한다. 현재 설계/안전 계약/한계/향후 후보는 [command-shortcuts.md](command-shortcuts.md), 짧은 사용법은 README에 있다.

최종 로컬 `scripts/dev.py check` 통과, `scripts/dev.py test` pure 109 / 1.653초·integration 269 / 86.780초·total 378·통합 runner 95.745초다. `world.test_command_shortcuts tests.test_command_shortcuts tests.test_integration tests.test_text --parallel 2 --reverse`는 58개 / 18.355초·runner 26.681초 통과했다. 실제 Quick smoke는 46.471초 성공했고 owned process/temp를 정리했다. play DB의 size 733184·mtime_ns 1790080153765082800·SHA256 `b1318296f505b9b7522fcbdedff7642a06cf055e9de72802198c70e6b8a7f700`은 동일했다. 근거는 Git 제외 `work/shortcuts-full-tests-final.log`, `work/shortcuts-related-reverse.log`, `work/shortcuts-quick.log`다. 개발 중 도움말 prefix 충돌을 수정하고 고정 v6 광원 migration 기대를 최신 버전으로 갱신했으며 기존 데이터 보존 검사는 유지했다.

이번 실행 코드·테스트 검증 이후 변경은 문서뿐이다. Full/restart/브라우저/OS IME는 서버 명령 변경과 직접 관련된 자동/integration·Quick 범위로 검증해 반복하지 않았다. JS·asset 변경이 없어 node/collectstatic은 미실행이다. 운영 DB에 테스트로 접속하지 않았다. 최종 원격 HEAD와 test/smoke CI는 PR Validation에서 실제 SHA를 대조한다.

### 7단계 PR 생성 시점의 Objective (과거 기록)

본부 1~6단계와 P0 smoke 인프라는 PR #13~#20으로 병합 완료됐다. 7단계 시작 시 작업 트리는 깨끗하고 fetch 후 HEAD/origin/main은 `63dca1bf9366d60af06a1728f0aaefb2bfdb6526`였다. PR #20은 MERGED이며 병합 후 [Game checks #106](https://github.com/wonmin82/primal-zone/actions/runs/36528666351)은 test/smoke 모두 success다(순수 99·통합 250·총 349, runner 100.141초, Quick 19.336초). 열린 PR은 없었다. 최신 main에서 `codex/hq-final-closeout`을 생성했다. 7단계 통합 cleanup·전체 회귀검증·closeout으로 실제 restart/Full progression/최종 Web 확인을 완료하고 PR #21을 생성했다. 아래 OPEN 및 부두 서비스 설명은 시점별 과거 기록이다. 본부 재설계 1~7단계 구현 및 로컬 최종 검증을 완료했다. 구현 HEAD의 test/smoke CI도 성공했다. 문서 후속 커밋의 최종 HEAD CI는 PR Validation에서 별도 확인하며 PR은 병합하지 않는다.

### 본부 7단계 closeout (2026-09-29)

시작 main `63dca1bf9366d60af06a1728f0aaefb2bfdb6526`, branch `codex/hq-final-closeout`. PR #13~#20 MERGED, 시작 시 열린 PR 없음과 main Game checks #106/run 36528666351의 test/smoke success를 확인했다. 아래 결과는 이번 최종 코드의 새 실행이며 과거 수치를 재사용하지 않는다.

| 검사 | 실제 결과 |
| --- | --- |
| `scripts/dev.py check` | 통과 |
| `scripts/dev.py test` | pure 101 / 1.875초, integration 252 / 84.920초, total 353, 통합 runner 94.315초 |
| `scripts/dev.py test world.test_smoke tests.test_hq_closeout tests.test_hq_services --parallel 2 --reverse` | 18 통과 / 14.875초, runner 23.496초 |
| `node --check game/web/static/webclient/js/primal.js` | 통과, JS 변경 없음 |
| `scripts/dev.py smoke` 즉시 연속 #1 / #2 | 45.956초 / 44.344초, 둘 다 성공·owned process 종료·temp 삭제 |
| `scripts/dev.py smoke-full` | 293.796초, 실제 restart와 두 임무/보스 최종 보고 포함, 성공·정리 완료 |
| Full 실제 첫 combat / corpse / respawn / protection | 2.835초 / 29.886초 / 44.501초 / 121.950초 |
| play SQLite 안전성 | 모든 실행에서 size 733184, mtime_ns 1790080153765082800, SHA256 `b1318296f505b9b7522fcbdedff7642a06cf055e9de72802198c70e6b8a7f700` 동일 |

전체 managed Object의 DB IDs/key/location/destination/aliases/stable tags/shop_id를 두 번 bootstrap 전후 비교했다. player profile 전체와 저장 위치, 공용 contents, 승강기 3층, facility/environment state가 같았고 integrity/stale는 비었다. malformed normalization·selector/poor/locked/distant privacy·멀티플레이 leader/leave/removal/XP/loot/한 명 패배 후 잔여 전투/rollback·동승 독립 하차는 기존 전체 integration 회귀가 유지한다.

Live Full에서는 보관상자/개인 보관함에 넣기·꺼내기와 일부 보관, 부품 7개 정산/3개 수리용 보존, 강타 Rank 2 학습, Doctor 치료, outsider 실제 패배·의무실 HP 1·최대 10C·Bed 회복, 옥상 귀환·3종 상점 구매·장착을 연결했다. 정비기록→발전기 부품 3개 소비→능선 보스→윤대장 보고, 길잡이→두 표식→신호전지 소비→두 번째 gate→밀림 보스→최종 보고가 actual 서버/명령/DB/WS로 완료됐다. 두 gate의 미충족 거절도 확인했다. RNG drop을 반복 기다리거나 결과를 fixture로 완료하지 않았다.

실제 restart 전 A는 승강기 3층에 있었고 B는 초지의 live claimed combat 중이었다. 공용 발전기와 상자·개인 보관·완료 임무·전리품이 있었다. harness가 같은 SQLite/설정/포트의 Portal+Server 두 프로세스를 실제 종료/시작한 뒤 세 계정 모두 재인증했다. DB identity/location/home=dock·XP/Credits/inventory/equipment/storage/growth/quests/discoveries/visited·파티·승강기·공용 contents·시설·환경 clock이 보존됐다. live combat/claim은 정리되고 남은 시체와 respawn은 실제 callback/sweep을 기다려 완료됐으며 모든 기존 loot entry가 ground에 유지됐다. forced OS crash 검증과 다르며 광원은 기존 off 정책을 따른다.

브라우저는 별도의 guarded 격리 SQLite/서버에서 일반 Player 권한 계정으로 진행했다. 대기실/중앙홀·보관 보기/넣기·정산 환율/모두 교환(부품 10→0, 1000C→1100C)·승강기 1/2/3층/옥상·TRAINING disclosure와 Rank 2 학습·Doctor/Bed full HP·세 판매자 메뉴/붕대·마체테·강화조끼 구매·부두 윤대장/서비스 버튼 없음·초지 실제 사냥/바닥 회수 버튼을 확인했다. DOM clientWidth/scrollWidth는 데스크톱 1234/1234, 390px override 375/375로 같았고 구매 control 시각 줄바꿈도 확인했다. 앱 console error/warning은 발견하지 않았고 Chrome extension의 async listener channel 종료 오류 3건은 구분했다. viewport override를 복원하고 탭·서버·temp DB/runtime credential 파일을 정리했다. JS/CSS asset 변경이 없어 cache version을 올리지 않았으며 fixture setup에서 격리 서버의 static을 수집했다.

근거는 Git 제외 `work/hq-closeout-tests.log`, `work/hq-closeout-quick1.log`, `work/hq-closeout-quick2.log`, `work/hq-closeout-full.log`, `work/hq-closeout-desktop.png`, `work/hq-closeout-mobile.png`다. 초기 관련 검사의 없는 모듈명/Evennia FK 필드명 기대를 바로잡고 실패한 새 검사부터 재검증했다. 개발 중 확장 Full 270.196초도 성공했지만 위 최종 Full은 restart callback 완료 polling까지 포함한다. assertion을 느슨하게 하거나 기존 테스트를 삭제하지 않았다.

실제 OS IME·강제 OS crash·Windows CI·PostgreSQL/운영 DB·모든 날씨/달 조합·모든 quest branching은 미실행이며 이 closeout의 의도된 non-scope다. live 주요 progression의 최종 보고와 production timing은 이번 Full로 새로 검증했다. test/smoke CI job은 그대로 분리하고 Full은 일반 CI에 추가하지 않았다. branch protection 설정은 수정하지 않았다. 최신 PR HEAD/CI는 PR Validation 및 완료 보고에서 직접 대조한다.

### 선행 단계 착수·검증 이력 (과거 기록)

본부 재설계 1단계와 방향 정정은 [PR #13](https://github.com/wonmin82/primal-zone/pull/13)으로 병합됐다. 병합 커밋은 `f9fcd52feb7c449eb94519d9e36f3504558056f4`다. 중앙홀 남/1층 중앙 북과 남쪽 폐쇄 출입구, 대기실 남/중앙홀 북과 중앙홀 서/부두 동을 유지한다. 상세 설계는 [본부 Room 구조 1단계](architecture.md#본부-room-구조-1단계)를 따른다.

테스트 성능 개선은 [PR #14](https://github.com/wonmin82/primal-zone/pull/14)로 병합됐으며 병합 커밋은 `ada6487f254beb3a662340ce81fa75771092cce1`다. 2026-09-28 승강기 작업 시작 시 fetch 후 실제 최신 origin/main도 같은 SHA였고 main 작업 트리는 깨끗했다. 당시 PR #13·#14의 MERGED와 main CI 성공을 직접 확인했다. 아래 테스트 성능 개선 기록은 해당 시점의 결과다.

본부 2단계 공용 승강기는 [PR #15](https://github.com/wonmin82/primal-zone/pull/15)로 병합됐다. 3단계 작업 시작 시 unstaged/staged diff가 없는 main에서 fetch했고 로컬 HEAD와 최신 origin/main은 모두 `7cf42145551ea364b5f1a1b69fa68c3e5567bee8`이었다. PR #15의 MERGED 및 해당 main [Game checks](https://github.com/wonmin82/primal-zone/actions/runs/36434012910) success를 직접 확인했다. 로그는 순수 77개·통합 213개, 총 290개 통과이며 통합 52.911초·runner 56.367초다. 아래 PR #15 OPEN 서술은 PR 생성 시점의 과거 기록이다.

본부 3단계는 [PR #16](https://github.com/wonmin82/primal-zone/pull/16)으로 병합됐다. 4단계 작업 시작 시 깨끗한 main에서 fetch 후 HEAD와 origin/main은 모두 `a10623ba92df9bcd412994fd3eb0a69a2f44e18b`이었다. PR #13/#14/#15/#16 MERGED이며 PR #16 및 해당 main [Game checks](https://github.com/wonmin82/primal-zone/actions/runs/36491116507) success를 실제 확인했다. 해당 병합 CI는 순수 78개(0.027초)·통합 219개(51.605초), 총 297개·runner 55.717초 통과다. 4단계는 아래 PR #17로 병합 완료됐으며 이번 승인 범위는 5단계 단일 화폐 및 회수 자원 정산이다. 아래 PR #16 OPEN/부두 귀환·휴식 서술은 3단계 당시 기록이며 현재 상태보다 우선하지 않는다.

기존 광원 기능은 PR #11로 완료됐고 인계 문서는 PR #12로 병합됐다. 아래 광원·본부 1~3단계·테스트 성능 개선의 설계·검증은 시점별 과거 기록이며 보존한다. 본부 1~4단계는 PR #13/#14/#15/#16/#17 MERGED다. 2026-09-29 이번 작업 시작 시 status·unstaged/staged diff는 없었고 fetch 후 HEAD와 origin/main은 모두 `d1f3e54bcd7172bd11aec1a10624d4084b03e8c5`였다. PR #17 MERGED와 해당 main [Game checks](https://github.com/wonmin82/primal-zone/actions/runs/36502424759) success를 직접 확인했다. 병합 CI는 pure 82개(0.024초)·integration 231개(57.207초), total 313개·runner 60.563초다. 최신 origin/main에서 `codex/hq-resource-settlement`를 생성했다. 현재 작업은 5단계 단일 화폐 및 회수 자원 정산이며 아래 PR #17 OPEN 서술은 과거 생성 시점 기록이다.

### 본부 6단계 구현과 검증 (2026-09-29, 과거 기록)

- 시작 main은 `d7141fbfd12572a19e744b36fd978fd8150c135e`, branch는 `codex/hq-npc-shops`다. PR #13/#14/#15/#16/#17/#18는 MERGED다. 최종 재fetch에서도 origin/main은 시작 SHA와 같고 이미 포함하므로 rebase 재작성은 필요 없었다. 6단계 구현·로컬/브라우저 검증·commit/push·PR 생성을 완료했다.
- `Shopkeeper(ActionObject)`의 `supply_shopkeeper`(보급관/보급상인)→supply_shop, `weapon_shopkeeper`(무기상/무기 상인)→weapon_shop, `armor_shopkeeper`(방어구상/방어구 상인)→armor_shop을 추가했다. persistent `db.shop_id`는 각각 supply/weapon/armor이며 `world/content/shops.py`의 SHOP_CATALOGS가 유일한 catalog/가격 SSOT다. 기존 14개 가격과 Credits-only 1개 구매·무한 재고를 보존한다.
- 메뉴는 `상점`/`메뉴`/`무기상 상점`/`무기상 메뉴`, 구매는 `강철마체테 구매`/`무기상에게 강철마체테 구매`처럼 사용한다. current room_objects의 실제 visible NPC를 공통 selector로 고른다. bare 메뉴는 보이는 상인이 하나일 때, bare 구매는 해당 상품 판매자가 하나일 때 선택하며 여럿은 이름·번호 지정이 필요하다. 실제 같은 Room·safe·비전투를 검사하며 hidden/view lock은 후보·오류·명령·hint·Web에서 제외한다. 다른 safe Room으로 실제 NPC를 옮기면 서비스가 따라간다.
- global SHOP, 부두 Shop/Buy gate·static 상점 hint·Web 보급소 버튼과 더 이상 호출하지 않는 GameCommand.at_dock()을 제거했다. 모든 ActionObject가 web_actions capability를 제공하고 state는 subclass 이름을 구분하지 않는다. 기본 allowlist는 Commander/조사/수리/의료/Container 보기·Instructor 대화와 별도 TRAINING UI를 보존하며 SettlementOfficer/Shopkeeper만 동적 action을 override한다. 메뉴·가격 포함 구매 label·targeted command는 서버가 생성한다. client 상점 zone 특례는 없다.
- bootstrap은 stable tag로 세 NPC를 한 개씩 생성·재사용하고 위치/alias/shop_id를 정규화한다. 반복 두 번 실행에서 DB ID·객체 수·기존 모든 interactable·두 플레이어 전체 profile·shared contents·공용 승강기 현재 층을 보존했다. profile migration·persistent stock은 없다. integrity는 세 배치/행동/catalog ID와 14개 상품 합집합·중복·상품 존재·양의 정수 가격·빈 catalog를 검사한다.
- smoke는 옥상 귀환→승강기 3층→동·북 무기점에서 구매·무장 후 남·서→승강기 1층→북·서 부두→초지·관리동으로 복귀한다. 죽은 return_to_dock helper를 목적에 맞게 교체했다. 정산→무기점 구매 E2E도 갱신했으며 scrap 3개 발전기 소비, loot/이전/보관, 기술 Credits·패배 패널티·의료·훈련·승강기는 유지한다.
- 최종 `scripts/dev.py check` 통과, 전체 `scripts/dev.py test` pure 91개(0.127초)·integration 248개(82.570초), total 339개 통과·실패/skip 없음, 통합 runner 91.606초다. 근거는 `work/shops-final-full-success.log`다. 초기 fixture 실패 2개와 새 suite 역순·병렬 11개(15.312초, runner 26.203초)도 통과했다. 옛 자산 query assertion 실패는 해당 1개부터 수정 검증한 뒤 위 전체를 실행했다. 최종 성공 이후 production/test 변경은 없다.
- JS 문법·smoke Python syntax·diff 검사 통과다. game과 별도 SQLite 검증 서버에서 최종 정적 파일을 수집했다. 일반 계정으로 세 NPC/메뉴/구매, 버튼·직접 붕대 구매의 동일 효과, 정산 6개→60C→무기점 구매, 부두 상인 없음·윤대장 보존을 확인했다. 정산·의료·Container 보기와 기존 훈련 panel 표시/활성을 확인했으며 의료·훈련을 브라우저에서 다시 실행하지는 않았다. 데스크톱 폭 1234/1234px, 390px에서 375/375px로 가로 overflow가 없었다. 앱 JS stack 오류는 관찰하지 않았고 Chrome 비동기 listener 채널 오류 2건은 별도 기록했다. 검증 탭/서버 종료·viewport 원복 완료, 플레이 DB는 읽거나 변경하지 않았다. [상세 기록](playtest.md#6단계-실제-검증-기록-2026-09-29)을 따른다.
- 전체 smoke는 610초 가입 대기와 실제 반복 전투 때문에 미실행이며 변경된 경로를 자동/별도 DB 브라우저/syntax로 확인했다. 실제 OS IME·이번 변경의 전체 restart/reconnect·운영 DB 적용·전체 멀티플레이 수동 검증도 미실행이다. 7단계 통합 cleanup/전체 회귀검증은 이 PR 검토·병합 후 최신 main에서 별도 요청으로 진행한다. PR은 병합하지 않는다.
- 원격 기록 작성 시 로컬/원격/PR 구현 HEAD는 `117bc17beaf1c73417ecd150b2145997f2a551ef`로 같고 작업 트리는 깨끗했다. [PR #19](https://github.com/wonmin82/primal-zone/pull/19)는 OPEN·비Draft·MERGEABLE이다. 이 SHA의 [Game checks](https://github.com/wonmin82/primal-zone/actions/runs/36518994902) success를 headSha와 직접 대조했다. 원격 check 통과, pure 91개(0.045초)·integration 248개(99.501초), total 339개·runner 105.321초다. 근거는 `work/shops-first-ci.log`다.
- 이 PR/CI 기록은 문서 전용 후속 커밋에 포함한다. 위 SHA/CI는 기능 구현의 확인 기준이며 최종 문서 HEAD의 원격 CI는 push 후 별도로 직접 확인해 PR Validation과 완료 보고에 기록한다. 실행 코드·테스트가 같아 로컬 전체 검사는 반복하지 않고 문서 diff·링크·기록을 검증한다. 기존 구현 CI를 최종 HEAD 결과로 대신하지 않는다.

### 본부 5단계 구현과 검증 (2026-09-29, 과거 기록)

- 시작 main은 `d1f3e54bcd7172bd11aec1a10624d4084b03e8c5`, 작업 branch는 `codex/hq-resource-settlement`다. 최종 fetch에서도 origin/main은 같고 이미 포함하므로 rebase 재작성은 필요 없다. Stage 1~4와 테스트 인프라는 그대로다.
- 실제 `SettlementOfficer`의 stable ID는 `salvage_officer`, 표시명 자원 정산관, alias 정산관이며 `salvage_office`에 배치한다. 기존 bootstrap이 stable tag로 같은 DB 객체·alias를 재사용하고 두 번 실행 후 객체 수·모든 기존 서비스 ID/위치·공용 contents·개인 inventory/storage/profile이 보존됨을 자동 테스트로 확인했다. 정산관 mutable inventory나 profile migration·자동 환전은 없다.
- `world/content/economy.py`의 `SALVAGE_CREDIT_RATE=10`이 1 scrap = 10 Credits의 SSOT다. 장비 직접 교환 EXCHANGE 정의/export·exchange flag를 제거하고 `rules.buy(profile,item_id)`는 Credits만 사용한다. SHOP 14개 가격과 부두 Shop/Buy·at_dock은 유지하며 scrap은 inventory material/transferable이다. 발전기 3개 소비와 전리품·보관/전달·기술 비용·의료·귀환/패배·home·승강기는 유지한다.
- 명령은 `환율`/`정산관 환율`/`자원 정산관 환율`, `회수부품 교환`(1개)/`회수 부품 교환`/`회수부품 N개 교환`/`회수부품 모두 교환`, `정산관에게 회수부품 ... 교환`이다. NPC 이름/번호와 alias는 기존 names·parse_selector·resolve·parse_relation을 사용한다. 수량 parser는 정산에 한정하며 일반 이전 문법을 확장하지 않는다. bare는 보이는 NPC 1명만 자동 선택하고 다중 대상은 지정을 요구한다. hidden/view lock은 대상 수·명령·Web·hint에서 제외한다. actual current-room NPC + safe + noncombat으로 이용하며 다른 safe Room에서도 객체를 따른다.
- `rules.settle_salvage`는 peace/양의 정수/보유량을 검증하고 consume과 Credits 증가를 수행한다. `caller.change()` 안에서 모두 수량을 결정하며 실패는 전체 profile 불변, 0개 entry는 제거한다. 환율 조회는 profile을 저장하지 않는다. `pz_state.resources.scrap={name,count}`는 inventory snapshot에서 파생하며 wallet과 구분한다. 서버가 실제 available NPC로 환율/targeted 모두 명령을 만들고 client는 그대로 렌더링한다. zone 특례·NPC/환율/수량 추론은 없다.
- 최종 `scripts/dev.py check` 통과, 전체 `scripts/dev.py test` pure 88개(0.068초)·integration 239개(86.866초), total 327개·실패/skip 없음, 통합 runner 95.978초다. 근거 `work/settlement-final-full.log`. 정산 전용 역순·병렬 8개(10.815초, runner 19.337초) 통과이며 이 검사는 최종 상세 보기 semantic 조정 전, 규칙은 같다. 이후 최종 관련 20개(15.119초, runner 23.778초)와 전체에서 상세 보기까지 검증했다. JS node 문법 및 diff 검사 통과다. 이후 변경은 문서뿐이므로 로컬 게임 검사 재실행은 하지 않는다.
- game과 별도 SQLite 검증 서버에서 최종 정적 파일을 수집했다. 일반 계정으로 1층 중앙 서·서·북→정산소, actual NPC와 환율 버튼·별도 resource 표시, 직접 1개 정산(7→6/+10C), 서버 targeted 모두 버튼(6→0/+60C), 모두 버튼 제거를 확인했다. 기존 출구로 부두 이동→보급소 보기→Credit-only 가격·직접 강철마체테 구매(60C/잔액 10C/장비 +1)도 확인했다. 데스크톱 문서 폭 1234/1234px와 390px의 375/375px로 overflow 없고 자원 행·긴 버튼 줄바꿈을 캡처했다. 앱 코드 console 오류는 발견하지 않았으나 Chrome 비동기 listener 메시지 2건은 별도 기록했다. 검증 탭·서버는 종료하고 viewport를 원복했다. 상세는 [5단계 검증](playtest.md#본부-5단계-단일-화폐회수-자원-정산-확인)을 따른다.
- 전체 smoke 미실행 — 최신 `scripts/smoke.py`에는 장비 직접 교환/정산 전제가 없고 기존 Credit 구매·4단계 의료 흐름을 유지한다. 일반 가입 rate limit의 610초 대기와 실제 반복 전투를 포함한 전체 smoke 대신 관련 자동·별도 DB 웹 검증을 수행했다. 실제 OS IME·이번 기능의 서버 restart/reconnect·운영 DB/배포는 미실행이다. 기존 플레이 DB는 읽거나 변경하지 않았다.
- 구현·로컬/브라우저 검증·commit/push 완료. 원격 기록 작성 시 로컬/원격/PR 구현 HEAD는 `7196e58470717417319523fd9b56387731ebb83b`로 같고 작업 트리는 깨끗했다. [PR #18](https://github.com/wonmin82/primal-zone/pull/18)은 OPEN·비Draft·MERGEABLE이며 이 SHA의 [Game checks](https://github.com/wonmin82/primal-zone/actions/runs/36505944424) success를 headSha와 대조했다. 실제 CI는 check 통과, pure 88개(0.023초)·integration 239개(58.178초), total 327개·runner 61.265초다. 근거 `work/settlement-first-ci.log`. 재fetch 후 origin/main도 시작 SHA와 같고 이미 포함돼 rebase 재작성은 하지 않았다.
- 이 기록은 PR 생성 후 문서 전용 후속 커밋에 포함한다. 위 SHA/CI는 기능 구현의 확인 기준이며 후속 커밋까지 포함한 최종 HEAD는 실제 Git/PR에서 확인한다. 코드·테스트는 동일하므로 로컬 전체 검사는 반복하지 않고 문서 diff·링크·기록을 검사한다. 최종 문서 HEAD의 CI는 푸시 후 별도로 확인해 PR Validation과 완료 보고에 기록하며 구현 CI를 최종 HEAD 결과로 대신하지 않는다. PR은 merge하지 않는다. 6단계는 이 PR 검토·병합 후 최신 main에서 별도 요청으로 진행한다.

### 본부 4단계 구현과 검증 (2026-09-29, 과거 기록)

- 시작 main은 `a10623ba92df9bcd412994fd3eb0a69a2f44e18b`, 브랜치는 `codex/hq-medical-lifecycle`이다. 신규 시작 `staging_room`, 저장 위치 재접속, fallback `home=dock`은 유지하고 일반 귀환만 `support_roof`, 전투 패배만 `infirmary`로 실제 이동한다. 공용 승강기 production 코드는 변경하지 않았다.
- 실제 `Doctor`의 stable ID는 `doctor`(의무관/의사), `Bed`는 `infirmary_bed`(침대/병상)이며 의무실에 배치한다. 기존 tag bootstrap으로 객체를 하나씩 생성·재사용하고 반복 실행 시 DB ID·alias·전체 객체 수·기존 플레이 기록을 보존한다. integrity는 의료 위치와 행동 정의를 검사한다.
- `치료`/`의무관 치료`/`의무관에게 치료`, `휴식`/`침대 휴식`/`침대에서 휴식`과 alias는 보이는 current-room Doctor/Bed를 공통 selector로 선택한다. bare 입력은 정확히 하나일 때만 자동 선택한다. hidden/view lock은 대상 수·오류·selector·Web·hint에서 제외하며 실제 객체가 다른 안전 Room으로 옮겨도 서비스는 객체를 따른다. 보이는 전투 중 대상은 기존 전투 RuleError, unsafe는 안전 조건 오류로 거절한다.
- `rules.treat`/`rules.rest`는 별도 public rule이며 현재 둘 다 무료·즉시 full HP다. 최대 HP에서는 상태를 바꾸지 않는다. 붕대 `heal`·크레딧·medicine 숙련과 독립이고 Bed 점유·시간 지연은 없다. 서버 allowlist에 의료 행동만 추가해 실제 availability로 contextual action과 target/action hint를 제공한다. client infirmary zone 특례 없이 부두의 휴식 버튼/hint만 제거하고 상점·윤대장·`at_dock()`은 유지한다.
- `enemy_attack`은 피해/defeated 판정, `apply_defeat`는 `lost=min(credits,10)`과 `DEFEAT_RECOVERY_HP=1`, Enemy lifecycle은 전투 정리와 의무실 이동을 맡는다. 하나의 `world_change`로 저장·membership·이동을 처리하며 move False/부분 이동 실패 시 DB와 attribute/location/contents 캐시를 복구한다. 타이머 정리·구조 안내·기존 save_profile state push는 성공 이후 실행한다. 다른 참가자는 전투를 계속하고 패배 복구는 Doctor/Bed rule을 호출하지 않는다. 장비·inventory·storage·성장·임무·발견 기록을 보존하며 실제 이동은 의무실 visited만 추가한다.
- `scripts/smoke.py`는 회복을 옥상 귀환→승강기 2층→의무실 침대→승강기 1층→부두→초지로, 구매를 옥상 귀환→승강기 1층→부두로 갱신했다. 이미 full HP이면 침대 명령을 생략하며 가입 rate limit과 610초 대기는 유지한다.
- 최종 `scripts/dev.py check` 통과, 전체 `scripts/dev.py test` 순수 82개(0.069초)·통합 231개(79.003초), 총 313개 통과·실패/skip 없음이다. 통합 runner는 88.001초이고 근거는 `work/medical-final-full.log`다. 의료 전용 역순·병렬 11개도 통과했다(12.440초, runner 21.135초, `work/medical-reverse.log`). 역순 검사는 최종 presence/부두 안내 문구 조정 전이며 의료 실행 규칙은 같고 최종 전체에서 해당 조정도 검증했다. 최종 전체 이후 문서만 수정하므로 로컬 전체 검사를 반복하지 않는다.
- JS `node --check game/web/static/webclient/js/primal.js`, smoke Python syntax, diff 검사 통과다. game과 별도 검증 서버에서 최종 정적 파일을 수집했다. 별도 SQLite DB의 일반 계정으로 실제 Enemy 패배→의무실 HP 1/10크레딧 손실/전투 종료, 의무관 버튼 full HP, 탐사 지역 직접 귀환→옥상, 승강기 2층→의무실·침대 버튼 full HP, 승강기 1층→부두·상점·윤대장·부두 휴식 대상 실패를 확인했다. 앱 코드 console 오류는 발견하지 않았으나 Chrome 비동기 listener 채널 종료 메시지 2건을 관찰했다. 검증 서버·탭은 종료했고 플레이 DB는 읽거나 변경하지 않았다. 상세 결과는 [4단계 검증](playtest.md#본부-4단계-의료복귀패배-확인)을 따른다.
- 전체 smoke 미실행 — 일반 계정 가입 rate limit의 610초 대기와 반복 실제 전투 때문에 변경된 경로는 관련 자동 및 별도 DB 브라우저로 검증했다. 실제 OS IME·이번 변경의 전체 서버 재시작 재접속·좁은 화면 재검사·운영 DB 적용도 미실행이며 UI layout은 변경하지 않았다. 멀티플레이와 실패 rollback은 자동 integration으로 확인했다.
- 원격 기록 작성 시 브랜치는 `codex/hq-medical-lifecycle`, 로컬/원격/PR 구현 HEAD는 `61c0effd4f0295394fd25daba22c3949f64f8967`로 같고 작업 트리는 깨끗했다. 최종 재fetch에서도 origin/main은 시작 SHA와 같고 이미 포함하므로 rebase로 이력을 재작성하지 않았다. [PR #17](https://github.com/wonmin82/primal-zone/pull/17)은 OPEN·비Draft·MERGEABLE이다. 이 구현 HEAD의 [Game checks](https://github.com/wonmin82/primal-zone/actions/runs/36498164252)는 success이며 headSha를 직접 대조했다. 원격 check 통과, 순수 82개(0.046초)·통합 231개(86.100초), 총 313개 통과·통합 runner 92.199초다. 근거 `work/medical-first-ci.log`.
- 이 원격 기록은 PR 생성 뒤 문서 전용 후속 커밋에 포함한다. 위 SHA/CI는 기능 구현의 확인 기준이며 문서 커밋 이후 최종 HEAD는 실제 Git/PR에서 확인한다. 실행 코드·테스트가 같아 로컬 전체 검사는 반복하지 않고 문서 내용·링크·diff를 검사한다. 최신 문서 HEAD의 CI는 푸시 후 별도로 직접 확인해 PR Validation과 완료 보고에 기록하며 구현 CI를 최신 HEAD 결과로 대신하지 않는다. PR은 병합하지 않는다. 다음 기능은 이 PR 검토·병합 후 최신 main에서 별도 요청으로 시작하는 5단계 단일 화폐 및 회수 자원 정산이다.

### 본부 3단계 구현과 검증 (2026-09-29, 과거 기록)

- 시작 기준은 `7cf42145551ea364b5f1a1b69fa68c3e5567bee8`이며 작업 브랜치는 `codex/hq-service-relocation`이다. 최종 로컬 검토를 위한 재fetch에서도 origin/main은 같아 rebase 재작성은 필요 없었다. PR #13/#14/#15는 병합 완료이며 승강기는 재설계하지 않았다.
- `shared_container`/`personal_locker`는 `storage_room`, `instructor`는 `training_room`으로 정의 위치만 이전한다. stable `primal_interactable` tag로 기존 DB 객체를 재사용하고 bootstrap이 key/location/alias를 갱신한다. 기존 다중 alias 전달이 두 번째 이름을 category로 처리하던 문제를 수정해 목록 전체를 보존한다. 삭제·재생성·profile version 변경은 없다.
- 공용 `Container.db.items`, 각 `profile.storage`와 개인 inventory/equipment/growth/skills/proficiency/visited·기존 캐릭터 위치는 bootstrap이 쓰지 않는다. 자동 및 별도 DB의 반복 이전 검사에서 객체 ID·전체 객체 수·Room ID와 모든 개인 profile·shared contents를 보존했다. 검증 DB의 세 객체 ID는 134/135/137로 그대로이며 `stale_definitions()`는 빈 목록이다. A/B가 같은 개인 보관함을 사용해도 자신의 contents만 보인다.
- 보관은 기존 current-room Container resolve·selector·Observation과 transfer transaction을 유지한다. 훈련은 실제 Instructor의 같은 Room·현재 Room safe·비전투·can_perceive/view 조건을 검사한다. `instructor_for`는 기존 `room_objects`의 관찰 가능한 풀과 같은 availability를 사용하며 `push_state`는 같은 observed_at으로 `training_available`을 계산한다. unsafe/없는/숨긴 NPC와 전투 중에는 웹과 명령 모두 훈련할 수 없다. 다른 안전 Room에 실제 객체를 옮겨도 서비스는 객체를 따른다.
- Web은 기존 server-owned interactables/training_available과 동일 텍스트 명령을 유지하고 훈련 안내와 JS cache query만 갱신했다. storage_room/training_room client zone 특례가 없으며 dock 상점·휴식 UI, 윤대장, home/귀환/패배 목적지는 그대로다. distant는 보관 contents/개인 정보/훈련 행동·기술 상태를 노출하지 않는다. 세 정적 서비스 배치는 integrity에 추가했다.
- 최종 production 기준의 `scripts/dev.py check` 통과, 전체 `scripts/dev.py test` 순수 78개(0.080초)·통합 219개(78.633초), 총 297개 통과·실패/skip 없음이다. 통합 runner는 88.088초이며 근거 `work/hq-services-final-full-success.log`다. 관련 순수 51개(0.091초), 새 이전 suite 역순·병렬 6개(10.204초, runner 19.491초)도 통과했다. 새 suite는 WorldCommandTest 5개와 이전 lifecycle을 직접 검증하는 GameCommandTest 1개로 나뉜다.
- 첫 관련 검사의 새 오류 문구 기대값·다중 alias 문제와 최초 전체의 옛 부두 상자 조명 fixture를 수정했다. 실패한 조명 1개(2.557초)부터 통과시킨 뒤 위 전체를 실행했다. 최종 전체 이후 production 변경은 없고, 기존 물건 전달 테스트의 실제 NPC 거절 경계를 유지하기 위해 부두 fixture를 명시한 뒤 해당 1개만 재검증했다(2.506초, runner 11.083초, `work/hq-services-give-recheck.log`). 문서·PR 갱신만을 이유로 전체 검사를 반복하지 않는다.
- JavaScript 문법·diff 검사 통과, game과 별도 검증 서버 정적 파일을 수집했다. Chrome 두 일반 계정으로 보관실 객체/보기/공용·개인 넣기·꺼내기·개인 분리, 실제 승강기 훈련실 동선·대화·배분/학습 버튼과 직접 명령의 동등한 결과·특성/기술/전체 재훈련, 부두의 대상 실패·훈련 비활성·상점/휴식/윤대장과 부두 귀환을 확인했다. 실제 JS query는 hq-services다. 앱 console 오류는 발견하지 않았으나 로그인 Chrome 확장 메시지 채널 종료 오류가 계정별 2건 있었다. 포트 4301의 Windows 바인딩 오류는 격리 서버를 5401 계열로 바꿔 해결했다. 검증 서버·탭은 종료했고 플레이 DB는 읽거나 변경하지 않았다. [상세 검증 기록](playtest.md#본부-3단계-보관훈련-이전-확인)을 따른다.
- 전체 smoke는 현재 파일에 보관/훈련 Flow가 없고 관련 자동/브라우저 검증으로 확인해 미실행이다. UI layout 변경이 없어 좁은 화면을 반복하지 않았다. 실제 OS IME·이번 변경의 재시작 재접속·운영 플레이 DB 적용은 미실행이며 이전 승강기 기록을 이번 실행처럼 쓰지 않는다.
- 원격 기록 작성 시 branch는 `codex/hq-service-relocation`, 로컬/원격/PR 구현 HEAD는 모두 `c3abbff934b419aa17bf99a5fc378f4c93e0447f`였고 working tree는 깨끗했다. 최종 재fetch에서도 origin/main은 시작 SHA와 같고 이미 포함돼 rebase 재작성은 필요 없었다. [PR #16](https://github.com/wonmin82/primal-zone/pull/16)은 OPEN·비Draft·MERGEABLE이며 이 구현 HEAD의 [Game checks](https://github.com/wonmin82/primal-zone/actions/runs/36457348765) success와 headSha를 직접 대조했다. 원격 check 통과, 순수 78개(0.044초)·통합 219개(76.276초), 총 297개 통과이며 통합 runner는 81.926초다. 근거 `work/hq-services-first-ci.log`.
- 이 기록은 PR 생성 후 문서 전용 후속 커밋에 포함한다. 위 SHA와 CI는 기능 구현의 확인 기준이며 최종 HEAD는 이 문서 커밋 이후의 실제 Git/PR에서 확인한다. 실행 코드·테스트가 같아 로컬 전체 검사는 반복하지 않고 문서 내용·링크·diff를 검사한다. 최신 문서 HEAD의 원격 CI는 푸시 후 직접 확인해 PR Validation과 완료 보고에 기록하며 이전 구현 CI를 최신 HEAD 결과로 대신하지 않는다. 이번 요청은 PR 병합을 허용하지 않는다. 다음 단계는 3단계 PR 검토·병합 후 최신 main에서 별도 요청으로 시작하는 의료·귀환·사망 흐름이다.

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

현재 기준은 맨 위 Objective와 PR #25 후속 구현·검증 기록이다. 선행 PR #22~#24는 MERGED이며 경제 작업 브랜치는 `codex/supply-chip-economy`다. 구현 HEAD와 성공 CI는 위에 고정해 기록하고, 최종 문서 HEAD 및 병합 상태는 PR #25의 실제 원격 상태를 따른다. 아래 과거 브랜치/OPEN 기록을 현재 상태로 해석하지 않는다.

### PR #22 리뷰 시점 저장소 상태 (과거 기록)

현재 branch는 `codex/personal-command-shortcuts`, 시작 main은 `a748d284d42935ce42ca151cf9e8c36c6942b731`이다. PR #13~#21 MERGED이며 본부 계획은 closeout 완료다. [PR #22](https://github.com/wonmin82/primal-zone/pull/22)은 OPEN·비Draft이며 최초 구현 커밋은 `ce3dfe8fad5ce2f91d99f927c40cf08d158bd952`, 이번 리뷰 시작 HEAD는 `7cb85ad37ac5fb5516769acd1db03a855aeba87c`다. 위 리뷰 보강을 후속 commit으로 같은 PR에 push하며 문서까지 포함한 최종 HEAD의 test/smoke CI를 workflow headSha와 직접 대조해 PR Validation에 기록한다. 과거 HEAD의 CI를 이번 최종 결과로 대신하지 않으며 PR을 merge하지 않는다.

### 7단계 PR 생성 직후 저장소 상태 (과거 기록)

현재 기준은 Objective와 7단계 closeout 기록이다. branch는 `codex/hq-final-closeout`, 시작/fetch main은 `63dca1bf9366d60af06a1728f0aaefb2bfdb6526`이며 PR #13~#20 MERGED다. [PR #21](https://github.com/wonmin82/primal-zone/pull/21)은 OPEN·비Draft·MERGEABLE이며 병합하지 않았다. 구현 커밋은 `736f10df437f3d809d779838a50c61d30a6b00fa`다.

구현 HEAD와 직접 대조한 [Game checks run 36545108714](https://github.com/wonmin82/primal-zone/actions/runs/36545108714)의 test/smoke는 모두 success다. CI는 pure 101개 / 0.766초, integration 252개 / 101.456초, total 353개, 통합 runner 107.901초이며 Quick은 20.265초다. 위 로컬 결과와 별도의 원격 실행이다. branch protection의 required context는 실제 API 확인 시 `test`만이며 smoke job은 자동 실행된다.

이 원격 기록은 문서 전용 후속 커밋에 포함한다. 실행 코드·테스트가 동일하므로 로컬 전체 검사는 반복하지 않고 문서 diff·링크·기록을 검사한다. 문서 후속 커밋까지 포함한 최종 HEAD의 test/smoke CI는 push 후 따로 확인하고 PR Validation과 완료 보고에 SHA·실행 링크·결과를 기록한다. 구현 HEAD의 성공을 최종 HEAD 결과로 대신하지 않는다.

### 최초 인계 시점 저장소 기록

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

### P0 격리형 live smoke 인프라 (2026-09-29)

- [PR #20](https://github.com/wonmin82/primal-zone/pull/20)을 생성했다. 최초 구현 HEAD `981bd81feaae0587055263ed386e3933fc5e09fd`의 CI는 job 시작 전 startup_failure였다. 저장소 Actions 허용 목록이 checkout/setup-uv만 허용하여 선택적 upload-artifact action을 제거하고 기본 shell/Python failure log 출력으로 전환했다. Actions/branch protection을 변경하지 않았으며 gameplay 코드는 동일하다.
- CI 설정 수정 HEAD `d85d83ece5d300342c7b1a30d1fe98c5dab01220`의 [test](https://github.com/wonmin82/primal-zone/actions/runs/36526697395/job/109271210799)와 [smoke](https://github.com/wonmin82/primal-zone/actions/runs/36526697395/job/109271210590)가 모두 success이며 headSha를 대조했다. Ubuntu에서 check·pure 99개(0.728초)·integration 250개(95.112초), total 349개·runner 101.100초, actual Quick 19.001초를 확인했다. 로그는 `work/smoke-implementation-ci.log`다. 이 기록은 문서 전용 후속 커밋에 포함하며 최종 문서 HEAD의 두 CI는 push 후 별도로 확인하여 PR Validation과 완료 보고에 기록한다. 이전 HEAD의 CI를 최종 HEAD 결과로 대신하지 않는다.

- 시작 main: `e4977132206e9edc285a35773758ef989d4fb6dd`, PR #19 MERGED·main CI success를 직접 확인했다. 최신 origin/main에서 `codex/smoke-p0-isolation` 생성, 기존 unstaged/staged 변경 없음. 현재 HEAD/PR은 실제 Git 및 아래 원격 기록으로 확인한다.
- P0 여섯 항목을 해결했다: 실행별 SQLite로 플레이 DB 오염 차단, fixture 인증으로 가입 throttle/610초 분리, Quick만 짧은 타이머, 공통 단계/Quick·Full 분리, 매 실행 새 DB/월드·계정·시설 상태로 재실행 격리, CI에 실제 Evennia/WS smoke job 추가. 기존 required `test` job/가입 throttle/production 타이머/테스트 인프라는 유지한다.
- `settings_smoke` marker·SQLite engine·정확한 DB/작업 경로 guard를 fixture의 Django 초기화/migrate 전에 확인한다. `PRIMAL_DB_*`를 자식 환경에서 제거한다. `work/smoke/<mode>-<run-id>` 아래에 새 코드 복사본/SECRET_KEY/DB를 준비하고 정상 Account/Character API로 일반 계정을 만든다. Credentials는 런타임 메모리/자식 stdin만 사용한다. 성공 시 디렉터리 삭제, 실패 시 DB/로그 보존; CI 실패 단계는 로그 tail만 출력한다(DB 제외).
- OS가 고른 loopback 포트 4개를 예약하고 actual foreground Portal/Server 두 Popen을 추적한다. HTTP+WS readiness polling과 scenario health monitor, finally의 own process/group 정리, marker/경로/종료 확인 뒤 cleanup을 구현했다. 외부 개발 서버의 launcher stop/reload/kill을 사용하지 않는다. 로그인은 실제 연결 안내 이후 인증하여 Portal 세션 등록 race를 피한다.
- `world/timing.py` production SSOT: combat 2.5·corpse 30·respawn delay 15·loot protection 120·claim/participation/reset 각 15초. Quick: 0.25·1·1·2·2·2·2초. Full은 production 기본값. 실제 delay와 기존 WorldLifecycle 5초 sweep을 재사용하고 직접 미래 reconcile/mock timer를 쓰지 않는다.
- 실제 공통 Flow: fixture 로그인/staging→본부/윤대장→파티 초대·수락→공동 처치/outsider claim 거절→시체의 순번 배정·파티 권한/outsider 회수 거절→actual corpse decay/ground→동일 spawn respawn→보호 만료/outsider 실제 회수→옥상 귀환/승강기 3층/무기상 Credits 구매→disconnect/relogin 상태 비교. 사냥은 1회, 구매 자금 100C/HP만 fixture로 준비하며 blade/시체는 미리 지급하지 않는다.
- `scripts/dev.py check` 통과. 최종 `scripts/dev.py test`: pure 99개/2.030초, integration 250개/81.877초, total 349개, 통합 runner 91.526초, 실패/skip 없음(`work/smoke-final-tests.log`). 기존 91+248 검사는 유지했고 pure 8·integration 2개를 추가했다. 일반 설정에서 guard가 DB 초기화 이전에 거절하는지, Quick/Full settings, CLI, owned process failure cleanup/다음 run, production 기본값을 검증한다.
- 실제 연속 `scripts/dev.py smoke`: 43.486초·43.960초, 둘 다 성공(`work/smoke-final-quick-1.log`, `work/smoke-final-quick-2.log`). `scripts/dev.py smoke-full`: 168.024초 성공(`work/smoke-final-full.log`), first combat round 2.804초, corpse 29.924초, enemy respawn 44.879초, protection expiry 121.373초. 서버/월드 준비·인증·종료를 포함한 시간이며 signup 대기는 없다.
- 각 최종 live 실행 전후 일반 플레이 DB의 SHA256/mtime_ns/size 동일(733184 bytes). PostgreSQL에 접속하지 않았다. 성공한 실행 디렉터리/서버는 정리됐다. 개발 중 API 인자/로그인 ordering/기존 smoke의 낡은 보호 오류 기대를 수정했고 실패 run의 DB/로그를 보존했다. 이후 성공했으며 guard/실패 cleanup 자동 검사도 통과했다.
- 문서/지침을 새로운 CLI·DB 안전·Quick/Full 역할에 맞춰 갱신했다. JS/UI 변경 없음으로 node/브라우저 검증 미실행. 공개 가입 장시간 throttle, 실제 server restart E2E, browser DOM 자동화, OS IME, Windows/PG CI, coverage, 전체 boss/progression closeout은 이번 P0 비범위다. P0 PR 검토·병합 후 별도 7단계 요청을 기다린다.


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
- wreck 비상장비함은 conspicuous, 플레이어당 최초 손전등 ×1/건전지 ×2다. 현재 손전등/건전지는 1층 보급관에게 30/6크레딧으로 구매한다. JungleCache는 기존 붕대 ×2+건전지 ×2다. 60분 compatible 전원은 test fixture이며 production 아이템으로 추가하지 않았다.
- `FACILITY_STATE_VERSION=1`, `db.facilities={"version":1,"states":{"outpost_power":false}}`다. legacy bare dict True를 보존하고 None/빈 dict는 기본값, 미래 version은 오류/덮어쓰기 없음이다. light 조회는 write-free다.
- FACILITIES ID/dict/엄격한 bool default와 Room 조명의 양수 strength·always_on/power 배타 조건을 integrity에서 검사한다. runtime 일반 helper에 특정 power ID 분기를 두지 않는다.
- dock 상시 조명 4, office/generator는 outpost_power일 때 4다. clear day dock은 낮빛, 밤이나 어두운 실내는 실제 기여한 시설 조명 문장이다.
- 개인 발전기 진행+공용 전력 저장은 원자적이며 False→True에 영향권 접속자 시설 가동 알림, True→True에는 반복 알림 없음이다. 기존 state push도 유지한다.
- 웹은 environment와 observation payload를 분리하고 현재 시야, compatible 전원별 삽입 버튼·광원 controls를 제공한다. FIELD GUIDE 환경 확인은 `날씨`이며 현재 CSS query는 `lighting`, JS query는 `hq-shops`다.
- clear dock `윤대장 대화`, commander view:false이면 안내 없음이다. 실제 상점 hint는 지원동의 보이는/이용 가능한 Shopkeeper를 따른다. wreck clear/손전등 clear는 두 상자 안내, poor는 `비상장비함 조사`만 표시한다. 의무실 의료 hint는 실제 보이는/이용 가능한 의무관·침대의 target/action을 따른다.

## Partially Implemented / In Progress

본부 1~7단계와 P0·8방향·명령 체계 선행 작업은 병합 완료다. 보급칩 경제와 네 후속 리뷰 수정의 구현·회귀검증도 완료했으며 미완료 기능을 이번 병합에 포함하지 않는다. 은행/거래창/재고/가격 변동 등의 의도적 비범위와 실제 OS IME 미검증, 구형 shares의 소실된 자격 복원 한계는 그대로 남는다.

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
- **7단계 해결:** README/architecture의 최신 profile v5 오기는 실제 v6 migration에 맞춰 바로잡았다. 코드 schema/version은 변경하지 않았다.

## Remaining Work

1. 새 세션에서 인계 문서와 Git/원격/CI 상태를 대조한다. 이 문서는 현재 기능 PR에 함께 갱신하며 최초 작성 당시의 미추적 상태와 현재 추적·PR 상태를 구분한다. 미커밋 변경이 있다면 브랜치 전환 시 보존하고 main에 직접 commit하지 않는다.
2. 다음 기능/수정 목표를 사용자와 확정한다. 이 문서의 부채 목록은 자동 구현 요청이 아니다.
3. 발전기 시나리오를 선택한다면 먼저 이미 켜진 시설/개인 미완료/기존 완료 캐릭터의 현재 흐름과 비용·보상 의미를 재현·설계한다. 합의 없이 비용·flag·gate를 수정하지 않는다.
4. push 중복을 선택한다면 실제 callback 횟수와 UI 영향부터 측정한다. 단순 중복 가능성만으로 저장/알림 경계를 다시 설계하지 않는다.

의도적 비범위: multi-room LOS/raycast·lux·광원 전파·부분 전원 회수·충전·연료·전력망 topology·night vision·망원경·은신·Enemy hearing·날씨 전투 modifier/환경 damage·온도/습도. 배고픔/갈증·아이템 무게/용량·container nesting·거래창/우편·일반 이전 명령의 숫자 수량/다중 지급도 구현 요청으로 남기지 않는다. 정산 전용 N개 수량은 이번 5단계 범위다.

## Recommended Next Step

PR #25의 최종 문서 HEAD와 병합 후 main의 test·smoke를 대조하고, 병합 포함 여부를 확인한 뒤 요청된 소스 브랜치를 정리한다. 이후 새로운 기능 작업은 별도 요구사항을 확정한 뒤 최신 main의 독립 브랜치에서 시작한다. [command-shortcuts.md](command-shortcuts.md)의 향후 후보와 기존 최적화 후보는 자동 구현 요청이나 확정 roadmap이 아니다.

## Important Files

| 파일 | 역할 |
| --- | --- |
| `AGENTS.md`, `README.md`, `pyproject.toml`, `uv.lock` | 프로젝트 지침/사용법/실제 의존성 |
| `scripts/dev.py`, `game/server/conf/settings_test.py`, `game/server/conf/test_runner.py`, `game/tests/base.py`, `game/tests/test_fixtures.py` | 테스트 전용 설정, 프로세스 병렬 실행·오류 전달, 실제 월드 fixture 재사용과 DB/runtime 격리 |
| `game/world/content/economy.py`, `game/world/settlement.py`, `game/commands/settlement.py`, `game/world/test_settlement.py`, `game/tests/test_settlement.py` | 정산율 SSOT, 정산 전용 수량 parser, 실제 정산관 명령과 단위/통합 검증 |
| `docs/architecture.md`, `docs/playtest.md`, `docs/text-examples.md` | 설계 SSOT, 수동 절차·시점별 결과, 실제 표현 예시 |
| `game/world/content/starter.py`, `game/world/content/deep_jungle.py` | Room desc/hints/requires, Enemy local/distant metadata |
| `game/world/content/directions.py`, `game/world/test_directions.py`, `game/tests/test_directions.py` | 8방향 SSOT·blocked alias·display width와 실제 Exit/보기/묶음/Web/Telnet 고정 canvas 검증 |
| `game/world/content/headquarters.py`, `game/world/test_headquarters.py`, `game/tests/test_headquarters.py` | 본부 Room/폐쇄 방향 정의, 순수 integrity·동선 검사와 실제 이동·접속·bootstrap·기존 서비스 회귀 |
| `game/world/content/elevator.py`, `game/world/elevator.py`, `game/commands/elevator.py`, `game/world/test_elevator.py`, `game/tests/test_elevator.py` | 정류 층 SSOT, 공용 승강기 상태·표시·실제 이동, location CmdSet, 순수/통합/웹/멀티플레이·격리 검증 |
| `game/world/content/items.py`, `game/world/content/environment.py`, `game/world/content/facilities.py`, `game/world/content/integrity.py` | item/가격/전원, 환경 상수, 시설 정의, 참조·형식 integrity |
| `game/world/environment.py`, `game/world/environment_state.py` | pure 환경 version/계산, DB 저장·읽기 전용 snapshot·전환 알림 |
| `game/world/observation.py`, `game/world/lighting.py` | 지각 matrix/context, metadata 전원·timestamp charge·status |
| `game/world/facility_state.py`, `game/world/facilities.py` | pure 시설 version/정규화, shared transaction·조명 lookup·가동 event |
| `game/world/room_hints.py` | 선언 순서 target/text 조합과 현재 perception |
| `game/world/targets.py`, `game/world/target_presentation.py`, `game/world/distant_presentation.py`, `game/world/navigation.py` | selector/parser/정렬, local 번호·loot 표시, distant contract, pure entry 판정 |
| `game/world/rules.py`, `game/world/item_transfers.py`, `game/world/multiplayer.py`, `game/world/state.py` | profile v8/pure 규칙, 이전 transaction, 공유 atomic/callback, 웹 대상/전리품 state |
| `docs/command-shortcuts.md`, `game/commands/shortcuts.py`, `game/commands/command_shortcuts.py`, `game/server/conf/cmdparser.py` | 줄임말/묶음 설계·안전 계약, 순수 확장/한도, 설정·확인·순차 dispatch, read-only exact fallback |
| `game/world/test_command_shortcuts.py`, `game/tests/test_command_shortcuts.py` | 문법/그래프/확인/migration pure 검사와 실제 DB/dispatcher/precedence/confirmation 격리 회귀 |
| `game/world/lifecycle.py`, `game/world/bootstrap.py`, `game/typeclasses/scripts.py` | tick/restart 소유권, idempotent 월드 구성, persistent WorldLifecycle |
| `game/typeclasses/zone_rooms.py`, `game/typeclasses/exits.py`, `game/typeclasses/enemies.py`, `game/typeclasses/interactables.py`, `game/typeclasses/loot.py`, `game/typeclasses/explorers.py` | 실제 객체와 Room/Exit appearance·action·지각·저장/웹/전투 훅 |
| `game/commands/character.py`, `game/commands/items.py`, `game/commands/inventory.py`, `game/commands/combat.py`, `game/commands/registry.py` | Look/Weather, 이전/광원/소비/해제, 구매/회수, 기존 공격, help 등록 |
| `game/web/templates/webclient/webclient.html`, `game/web/static/webclient/js/primal.js`, `game/web/static/webclient/css/primal.css` | 웹 표시/controls/cache query |
| `game/tests/test_hq_services.py`, `game/tests/test_growth.py`, `game/world/test_headquarters.py` | 보관·훈련 이전/저장 보존/객체·가시성 정책, 성장 회귀와 본부 배치 integrity |
| `game/world/content/shops.py`, `game/commands/shops.py`, `game/world/test_shops.py`, `game/tests/test_shops.py` | 고정 catalog/가격, 현재 보이는 판매자 선택, 구매 원자성·상점 privacy·bootstrap·Web·실제 구매 동선 |
| `game/world/test_medical.py`, `game/tests/test_medical.py`, `game/commands/world_actions.py` | 독립 의료/패배 pure rule, 의료 대상 선택과 객체 기반 권한, 복귀·멀티플레이 패배·rollback·Web state 검증 |
| `game/world/test_lighting.py`, `game/world/test_environment.py`, `game/world/test_rules.py` | pure 규칙·migration·환경/광원 테스트 |
| `game/tests/test_lighting.py`, `game/tests/test_environment.py`, `game/tests/test_distant_view.py`, `game/tests/test_item_interactions.py` | 통합 광원/시설/hint, 환경 저장, 정찰 privacy, stack 이전 |
| `game/tests/test_targets.py`, `game/tests/test_loot.py`, `game/tests/test_combat.py`, `game/tests/test_lifecycle.py`, `game/tests/test_web_state.py` | selector/권한/전투/lifecycle/웹 회귀 |
| `scripts/dev.py`, `scripts/smoke.py`, `scripts/smoke_harness.py`, `scripts/smoke_setup.py`, `.github/workflows/tests.yml` | pure/integration과 실행별 격리 Quick/Full live smoke, fixture·서버 자동 관리, test/Quick CI |
| `game/world/timing.py`, `game/server/conf/settings_smoke.py`, `game/server/conf/smoke_support.py`, `game/world/test_smoke.py`, `game/tests/test_smoke_infrastructure.py` | production/Quick 타이머 SSOT, smoke marker·DB/경로 guard, settings/CLI/실패 cleanup 자동 검증 |

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
