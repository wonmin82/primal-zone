# 개인 줄임말과 묶음 명령

이 기능은 본부 재설계와 별개의 서버 명령 기능이다. 현재 구현, 변경 시 유지할 안전 계약, 의도된 한계와 개선 후보를 이 문서에서 추적한다.

## 현재 구현과 사용법

```text
상태, 장비, 소지품 해
귀환, 승강기, 3층, 동, 북 해

줄임말 추가 장확 장비
줄임말 추가 점검 상태, 장비, 소지품 해
줄임말 추가 인사 안녕, 반가워 말
줄임말 추가 출발 점검, 탐사용손전등 켜 해
점검
출발
점검, 북, 북 해

줄임말
줄임말 삭제 점검
줄임말 모두 삭제
줄임말 모두 삭제 확인
```

`해`는 후치형 행동이며 실제 `해` command의 인자에서만 콤마를 구분자로 해석한다. 두 명령 이상이 필요하고 빈 항목은 오류다. `상태 해`, `상태,, 장비 해`, `, 상태 해`, `상태, 장비, 해`는 하나도 실행하지 않는다. 모든 입력을 먼저 콤마로 분리하는 전역 pre-parser는 없다.

`안녕, 반가워 말`과 `'안녕, 반가워`는 각각 한 번의 채팅이다. 등록 정의도 마지막 행동이 `해`인 경우에만 묶음으로 해석한다. 따라서 `점검`은 `["상태", "장비", "소지품"]`, `인사`는 `["안녕, 반가워 말"]`로 저장한다. 작은따옴표로 시작하는 정의는 끝에 `해`가 있어도 단일 채팅이다.

등록에서 `추가` 뒤 첫 token이 이름이고 나머지 전체가 정의다. 입력에 `=`는 필요 없다. 같은 이름은 원자적으로 교체한다. 목록은 이름순으로 표시하고 다중 정의에는 `해`를 붙여 재등록 가능한 형태로 보여 준다. 출력의 `=`는 이름/정의 경계를 보여 주는 표시일 뿐이다. `줄임말 삭제 모두`는 이름이 `모두`인 정의 하나만 지우며, 참조하는 다른 정의를 연쇄 삭제하지 않는다. 삭제된 이름은 다음 실행 시 일반 command input으로 취급한다.

## 저장과 profile migration

`profile.command_shortcuts`가 캐릭터별 유일한 영구 설정이다. Evennia object alias/nick이나 account 전체 설정을 사용하지 않는다.

```python
"command_shortcuts": {
    "장확": ["장비"],
    "점검": ["상태", "장비", "소지품"],
    "인사": ["안녕, 반가워 말"],
}
```

profile 최신 버전은 **9**다. v9는 정신력·회복 기본값을 추가하며 아래 v8 저장 어휘 변환과 줄임말 형식은 유지한다. 신규 profile에는 빈 dict가 있고 v1~v6는 기존 migration을 적용한 뒤 빈 `command_shortcuts`를 보완한다. 기존 보급칩(저장 키 credits)·소지품·장비·보관·성장·임무·전투·방문 데이터는 그대로 유지하며 반복 migration은 idempotent다. 등록·교체·개별 삭제·전체 삭제는 기존 `caller.change()` transaction과 저장 경계를 사용한다.

### v8 저장 어휘와 새 예약 이름 충돌

`commands/vocabulary.py`의 pure migration은 v7의 `가`/`가방`, 상점/메뉴/shop, 도주, 회복/응급치료/heal, 의무관 action 치료, 내리기를 소지품/상품/도망/응급처치/진료/내려로 변환한다. exact 글로벌 입력과 standalone command 또는 마지막 action token만 바꾸며 채팅 내용·대상 이름·아이템 이름은 바꾸지 않는다. 변환한 입력은 alias 대신 canonical로 저장한다. 같은 v8 profile의 재변환은 없다.

v7 저장 명령의 `ㅂ/ㄴ/ㄷ/ㅅ`과 `상/능/기/장`은 당시의 고정 변환표로 해석한다. 현재 플레이에서 쓰는 8방향 초성 단축어는 방향 SSOT에서 파생하며, 향후 정책이 바뀌어도 과거 v7 profile의 변환 의미는 달라지지 않는다. 옛 `가` 입력은 `소지품`으로 변환한다.

새 글로벌 `소`, 대각선 `ㅂㄷ/ㄴㄷ/ㄴㅅ/ㅂㅅ`, 미래 예약 `치료/힐/heal`과 새 실제 명령/alias 이름이 기존 개인 key와 충돌하면 조용히 삭제하지 않는다. 이름순으로 `<이름>_개인`, 이미 있으면 `_개인2`·`_개인3`의 유효하고 고유한 이름을 정한다. 20자 한도 안에서 suffix 공간을 확보하고 exact 중첩 참조만 함께 바꾼다. 예를 들어 v7의 `힐=["가방"]`, `생존=["힐"]`은 `힐_개인=["소지품"]`, `생존=["힐_개인"]`으로 보존되며 채팅·대상 문자열 속 힐은 바꾸지 않는다. 목록에서 변경된 이름과 정의를 확인할 수 있다. `heal` 기술 Rank와 예약 action은 `firstaid`로 보존하며 다른 진행 데이터는 유지한다.

v7 historical 입력의 `치료 → 진료`, `heal → 응급처치`는 당시 기능을 해석하는 계약이며 그대로 유지한다. 향후 runtime의 `치료/힐/heal`은 정신력 기반 자신·타인 치료 기술용 예약 이름으로, 현재 사용할 수 없다. 두 계약을 혼동하지 않는다. 이 어휘 변환은 v8 단계의 계약이며 정신력 추가에 따른 최신 profile v9에서도 그대로 유지한다.

## Parser 우선순위와 이름 정책

기존 후치형 게임 명령·엔진 관리 명령·location/Exit와 lock semantics를 먼저 적용한다. 기존 공용 SHORTCUTS는 기존 엔진 우선순위를 유지한 채 입력 전체에만 적용한다. 정상 match가 없고 실제 key/alias와도 충돌하지 않는 경우에만 개인 이름 전체의 exact match를 내부 실행 command로 연결한다. `점검 말`이나 `오늘 점검했어 말`의 일부 단어는 치환하지 않는다.

`줄임말` 관리만 명시적인 prefix 문법을 사용한다. `줄임말 도움말`은 기존 후치 도움말로 해석한다. 개인 정의 조회는 `profile_snapshot()`을 사용하며 parser 호출만으로 migration write·save·state push를 하지 않는다. 게임 명령이 없는 인증 cmdset은 기존 default parser를 그대로 사용한다.

이름은 공백 없는 1~20자이며 한글 완성형·자모·영문·숫자·`_`를 허용한다. 영문은 casefold해 저장/조회하므로 `Gear`와 `gear`는 같은 이름이다. 콤마·공백·`=`·관리 prefix 등 문법 문자는 금지한다. 기존 command key/alias, 잠긴 엔진 command, 시스템 SHORTCUTS, 현재 merged cmdset 및 콘텐츠의 모든 정적 방향·승강기 명령은 등록할 수 없다. 엔진이 생략을 허용하는 `@` 등 prefix를 제거한 이름도 예약한다. 미래 동적 cmdset에서 같은 이름의 실제 명령이 생기면 실제 명령이 우선한다.

게임이 제공하는 글로벌 **단축어**와 캐릭터가 만드는 개인 **줄임말**을 구분한다. 방향 초성은 `world/content/directions.py`의 `DIRECTION_SHORTCUTS`, 정보 초성은 `commands/aliases.py`의 `INFORMATION_SHORTCUTS`이며 합성한 `SHORTCUTS`를 parser와 `단축어` 출력이 공유한다. 방향 8개는 `ㅂ/ㅂㄷ/ㄷ/ㄴㄷ/ㄴ/ㄴㅅ/ㅅ/ㅂㅅ`, 정보는 `상/능/기/장/소`다. 옛 `가`는 글로벌/예약 목록에서 제거되어 새 개인 이름으로 등록할 수 있다. `치료/힐/heal`은 `FUTURE_RESERVED_COMMAND_NAMES`에 있어 개인 이름으로도 사용할 수 없다.

## 확장과 순차 실행

DB/Evennia 없는 `commands/shortcuts.py`가 정의/묶음 parsing, 재귀 flatten, 순환/한도 검사, 이름 및 fingerprint 검사를 담당한다. `commands/command_shortcuts.py`는 설정 관리·예약 이름·기존 dispatcher 연결을 담당한다. JavaScript에 expansion이나 별도 관리 UI를 만들지 않는다.

실제 명령을 하나라도 dispatch하기 전에 모든 정의를 snapshot에서 확장한다. 다른 개인 줄임말과 즉석 묶음에서의 참조를 지원한다. 등록/교체도 prospective graph 전체를 검사하므로 이후 등록으로 새 순환이 생기는 경우를 차단한다. 실행 시에도 순환과 한도를 다시 검사한다.

한도 SSOT는 `commands/shortcuts.py`다.

| 항목 | 현재 값 |
| --- | --- |
| 최종 command 수 | 최대 10 |
| 개인 줄임말 참조 깊이 | 최대 5 |
| 최종 command 문자열 길이 합계 | 최대 1000자, 구분자 제외 |
| 이름 길이 | 1~20자 |
| 전체 삭제 확인 TTL | 60초 |

Syntax/expansion/사전 안전 검사 실패는 전체를 거절하고 어떤 명령도 실행하지 않는다. 검증 완료 후 각 command는 `caller.execute_cmd()`로 현재 위치의 cmdset과 기존 parser/lock/gameplay 규칙을 다시 통과한다. 구매 뒤 무장, 이동 뒤 승강기 등 앞의 state를 다음이 읽는다. 실행 중 새로 등록된 이름을 최종 leaf에서 다시 확장하지 않아 count/depth 검사를 우회할 수 없다.

설치된 Evennia **6.1.0**의 `DefaultObject.execute_cmd()`는 cmdhandler의 Deferred를 반환한다. cmdhandler는 pre/post hook을 기다리지만 일반 `func()`가 반환한 Deferred는 기다리지 않는다. 따라서 묶음의 `Sequence.at_post_cmd()`에서 각 dispatch Deferred를 순서대로 yield한다. 임의 sleep으로 순서를 맞추거나 gameplay rule을 직접 호출하지 않는다. 실제 비동기 pre/post hook을 가진 명령에서도 다음 dispatch가 먼저 시작되지 않는 것을 integration으로 검증한다.

묶음 시작 시점의 merged cmdset(`self.cmdset`)에서 식별되는 generator/coroutine `func`는 실행 전에 거절한다. 특히 Evennia의 progressive generator는 command dispatcher의 Deferred보다 나중에 완료되므로 해당 명령은 단독 실행한다. 앞 명령이 위치/상태를 바꿔 새로운 CmdSet을 활성화한 뒤에만 나타나는 progressive command까지 사전에 예측하는 것은 보장하지 않는다. 상세 경계는 아래 현재 한계를 따른다. 기존 게임 명령과 일반 엔진 명령의 단독 semantics는 변경하지 않는다.

개별 command가 RuleError·대상 없음·UnknownCommand로 실패해도 다음 command를 계속 실행한다. 묶음은 `&&`나 transaction이 아니며 이미 성공한 행동을 되돌리지 않는다. 다른 사용자/입력과 전체 묶음을 하나의 atomic action으로 만들지도 않는다.

## 전체 삭제 안전 계약

```text
사용자 직접 입력 #1: 줄임말 모두 삭제
→ 현재 개수 안내 + 삭제 요청만 생성
→ 실제 shortcut 변경 없음

사용자 직접 입력 #2: 줄임말 모두 삭제 확인
→ 유효한 요청·TTL·fingerprint 확인 후 한 번에 삭제
```

향후 refactor에서도 다음 계약을 유지해야 한다.

- **확인 command 단독 입력은 삭제 권한이 아니다.** 이전 요청이 없으면 안내만 하고 정의를 보존한다.
- **전체 삭제 요청과 확인은 각각 별개의 top-level 직접 입력만 허용한다.** 묶음/개인 줄임말의 최종 dispatch에는 `primal_sequence_leaf=True`가 붙으며 `Shortcuts.run()`은 두 operation의 간접 실행을 pending 읽기·생성·소비·검증과 profile 변경 전에 거절한다.
- `줄임말 모두 삭제, 줄임말 모두 삭제 확인 해`, `상태, 줄임말 모두 삭제 해`, `상태, 줄임말 모두 삭제 확인 해`와 같은 묶음이나 이를 저장한 개인 줄임말로는 삭제 요청/확인을 할 수 없다. 일반 묶음의 상태 조회 등 다른 명령은 기존 실패 후 계속 semantics를 따른다.
- `삭제요청 = 줄임말 모두 삭제`, `확정 = 줄임말 모두 삭제 확인`, `초기화 = 줄임말 모두 삭제, 줄임말 모두 삭제 확인 해`를 등록해도 간접 요청은 pending을 만들거나 갱신하지 않는다. 간접 확인은 기존 유효 pending을 소비하지 않으므로 이후 직접 확인은 TTL/fingerprint가 유효하면 성공한다.
- 요청은 캐릭터의 `ndb.shortcut_delete_all_request`에 monotonic timestamp와 정렬된 이름/command list의 SHA256 fingerprint로 저장한다. profile/DB/account에 저장하지 않는다.
- 요청부터 60초 미만에만 확인할 수 있다. timestamp가 역행하거나 만료하면 거절하며 lazy expiry를 사용한다. 별도 scheduler가 없다.
- 성공한 등록·교체·개별 삭제는 pending request를 취소한다. 별도 경로에서 목록이 바뀌어도 확인 시 fingerprint 불일치로 차단한다.
- 새 요청은 현재 상태 기준으로 이전 요청을 교체한다. 0개이면 요청을 만들지 않고 이전 요청도 제거한다.
- 허용된 top-level 확인 시 request를 먼저 소비한다. 성공은 `profile["command_shortcuts"] = {}` 한 번의 저장으로 처리하며 같은 확인을 재사용할 수 없다. 실패한 정상 확인 후에도 새 요청이 필요하다. 금지된 간접 확인은 이 one-shot flow에 진입하지 않는다.
- 로그아웃/정상 서버 종료 hook에서 제거하고 실제 프로세스 restart에서도 non-persistent 요청은 살아남지 않는다.
- char1의 요청으로 char2가 확인할 수 없고 char2의 확인이 char1 요청을 소비하지도 않는다.

## 현재 한계

| 지원하지 않는 것 | 이유/경계 |
| --- | --- |
| 인자 치환 `$1/$2/$*` | quoting·selector·argument 전달 계약 필요 |
| 조건부 `&&/\|\|` | command 공통 success/failure contract 필요 |
| 반복·자동 반복 | 자동 전투·server load 정책 필요 |
| sleep/delay/예약·progressive 엔진 자동화 | logout/restart/scheduler ownership 및 완료 계약 필요 |
| 전체 묶음 rollback | 개별 게임 행동과 공유 월드 transaction이 별개 |
| 공백 포함 이름·account 공용 설정 | 한-token/캐릭터 단위만 지원 |
| import/export·Web 관리 UI | 현재는 서버 텍스트 명령만 지원 |
| 무제한 확장 | 10개/5단계/1000자 한도로 부하·순환 방지 |
| Literal comma를 포함하는 묶음 segment | 단순 `split(",")`이며 segment escaping/quoting은 지원하지 않음. 개인 줄임말 참조로 사용 |
| 동적 CmdSet에서 새로 나타나는 progressive command | 사전 검사는 시작 시점 cmdset 기준. 이동/상태 변경 후 등장하는 command의 완료는 사전 보장하지 않음 |

### 콤마가 포함된 명령을 묶음에서 사용하기

일반 단일 입력 `안녕, 반가워 말`은 한 번의 채팅이다. 하지만 `안녕, 반가워 말, 상태 해`는 `안녕` / `반가워 말` / `상태`로 나뉘므로 literal comma가 포함된 command를 묶음의 한 segment로 직접 작성할 수 없다. 작은따옴표 채팅 문법은 묶음 segment를 quoting하는 문법이 아니다. `\,` escape·CSV-like parser·새 separator는 구현하지 않는다.

현재 workaround는 해당 command를 단일 개인 줄임말로 저장하고 묶음에서 이름을 참조하는 것이다.

```text
줄임말 추가 인사 안녕, 반가워 말
인사, 상태 해
```

최종 expansion은 `["안녕, 반가워 말", "상태"]`이며 단일 command 안의 콤마는 그대로 유지된다. 즉석 묶음과 저장 정의의 separator 문법은 동일하다.

### 동적 CmdSet과 progressive 사전 검사

예를 들어 `북`으로 이동한 연구소에서만 추가 입력을 받는 `해킹` 명령이 활성화된다면, `북, 해킹, 상태 해`를 시작할 때의 cmdset에는 해킹이 없어 사전 검사에서 발견하지 못할 수 있다. 실제 두 번째 dispatch는 이동 후 cmdset을 사용한다. 현재 `game/commands`의 실제 gameplay `func()`에는 이 조건을 만족하는 generator/coroutine command가 없어 알려진 실제 회귀는 없다.

미래의 위치/상태 CmdSet을 예측·합성하지 않으며 dispatch 직전 progressive를 발견해 중단하는 정책도 이번 PR에서는 추가하지 않는다. 앞 명령이 이미 실행된 뒤의 중단은 partial execution 계약을 따로 정의해야 한다. 향후 그러한 command를 추가할 때 metadata(`allow_in_sequence`/progressive 여부), 현재 cmdset 재검사, runtime 중단과 partial execution 허용 여부, command completion/result contract를 함께 검토한다.

## 향후 구현 후보

확정 roadmap이나 자동 착수 요청이 아니다.

| 후보 | 검토할 설계 이슈 |
| --- | --- |
| 인자형 줄임말 | quoting과 selector, 치환 후 검증 |
| 조건부 실행 | 공통 command 결과 contract |
| 반복 | 전투 속도·서버 부하·중단 정책 |
| delay/예약 | 세션 종료·restart·scheduler 소유권 |
| 계정 공용 줄임말 | 캐릭터별 override와 권한/마이그레이션 |
| import/export | 비신뢰 정의의 예약 이름·한도/순환 검증 |
| Web 관리 UI | 동일 서버 명령 및 삭제 요청·확인 계약 재사용 |
| rename | 다른 정의의 참조를 함께 바꿀지 결정 |
| 검색/필터 | 안정적인 목록 순서와 결과 범위 |
| 시스템 기본 단축어 사용자화 | 기존 명령 precedence와 호환성 |
| 묶음 segment escaping/quoting | escape syntax·채팅 quoting과의 관계·backward compatibility·저장 정의와 즉석 묶음의 동일 grammar |
| 동적 CmdSet + progressive 실행 정책 | command metadata·dispatch 직전 재검사·중단/partial execution·completion/result contract |

## 검증 위치

순수 suite는 `world.test_command_shortcuts`, DB/dispatcher suite는 `tests.test_command_shortcuts`다. 기존 `tests.test_integration`/`tests.test_text`와 전체 suite가 후치형·채팅·관리·lock·인증 parser와 기존 gameplay 회귀를 검증한다. Quick live smoke는 실제 서버/WS/scheduler의 기존 전체 경로를 검증한다. 이번 기능 때문에 smoke scenario나 client UI를 확장하지 않는다.

### 2026-09-29 PR #22 리뷰 반영 검증

시작 PR HEAD는 `7cb85ad37ac5fb5516769acd1db03a855aeba87c`, fetch 후 origin/main은 `a748d284d42935ce42ca151cf9e8c36c6942b731`이었다. 기존 `codex/personal-command-shortcuts`에서 P1 guard·회귀를 추가했고 P2는 문서만 보완했다.

| 실행 | 새 실제 결과 |
| --- | --- |
| `scripts/dev.py check` | 통과 |
| `scripts/dev.py test world.test_command_shortcuts tests.test_command_shortcuts tests.test_integration tests.test_text --parallel 2 --reverse` | 63 통과 / 21.685초, runner 29.934초 |
| `scripts/dev.py test` | pure 109 / 2.144초, integration 274 / 89.825초, total 383, 통합 runner 99.229초 |
| `scripts/dev.py smoke` | Quick 성공 / 54.160초, process stop·temp cleanup 완료 |
| 플레이 SQLite 보호 | smoke 전후 SHA256·mtime_ns·size 동일 |

새 integration 5개는 request+confirm 한 묶음·초기화 shortcut, 간접 request의 pending 생성/갱신 차단, shortcut/sequence 간접 confirmation의 pending 보존과 이후 직접 confirmation 성공을 검증한다. 기존 직접 요청·단독 확인 차단·TTL/fingerprint·목록 변경 취소·one-shot·0개·캐릭터 격리·logout/shutdown·이름 모두 테스트는 유지했다.

Full/브라우저/OS IME는 미실행이며 UI/asset/gameplay timer 변경이 없어 반복하지 않았다. AST로 현재 gameplay `func()` 5개에 generator/coroutine이 없음을 확인했고 순수 expansion으로 literal comma의 개인 줄임말 workaround를 확인했다. escaping/quoting·동적 CmdSet 예측·progressive runtime 중단·command-result framework는 구현하지 않았다. 최종 PR HEAD의 원격 test/smoke CI는 push 후 PR Validation에서 workflow headSha와 대조한다.

### 2026-09-29 최초 구현 검증 (과거 기록)

기준 main은 `a748d284d42935ce42ca151cf9e8c36c6942b731`, branch는 `codex/personal-command-shortcuts`다. 아래는 이번 구현에서 실제 실행한 로컬 결과다.

| 실행 | 결과 |
| --- | --- |
| `scripts/dev.py check` | 통과 |
| `scripts/dev.py test world.test_command_shortcuts tests.test_command_shortcuts tests.test_integration tests.test_text --parallel 2 --reverse` | 58 통과 / 18.355초, runner 26.681초 |
| `scripts/dev.py test` | pure 109 / 1.653초, integration 269 / 86.780초, total 378, 통합 runner 95.745초 |
| `scripts/dev.py smoke` | 기존 실제 서버/WS/scheduler 전체 Quick 성공 / 46.471초, process stop·temp cleanup 완료 |
| 플레이 SQLite 보호 | SHA256·mtime_ns·size가 smoke 전후 동일 |

개발 중 발견한 `줄임말 도움말`의 prefix 충돌을 기존 도움말 경로로 수정하고 회귀를 추가했다. 기존 광원 migration 테스트의 고정 버전 6 기대는 최신 PROFILE_VERSION으로 갱신하고 상태 보존 assertion은 유지했다. 저장·순환·파싱·확인 안전성 오류는 실패한 관련 검사부터 재검증했다. 최종 코드에서 기존 테스트를 삭제하거나 assertion을 느슨하게 하지 않았다.

Full/restart/브라우저/OS IME는 미실행이다. 이번 서버 명령 기능의 새 semantics는 DB/dispatcher integration으로, 기존 live 연결은 Quick으로 확인했다. Web UI·JS·asset·production timer 변경이 없어 node 검사·collectstatic·브라우저와 production-duration Full을 반복하지 않았다. 실제 OS IME 검증을 자동 테스트 통과로 대신하지 않는다. 최종 PR HEAD의 원격 test/smoke CI는 PR Validation에서 별도로 대조한다.
