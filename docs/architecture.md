# 원시구역 구조와 설계 결정

## 목표와 구성

사냥·장비 수집·성장을 중심으로 하는 한국어 웹 MUD다. 모든 주요 임무는 혼자 완료할 수 있으며 파티는 선택 사항이다. Python 3.13 / Evennia 6.1.0 / SQLite / HTML·CSS·JavaScript를 사용하고 정확한 버전은 uv.lock으로 고정한다.

| 구성 | 책임 |
| --- | --- |
| world/content/ | 지역별 장소·적 정의와 공통 아이템·가격, Region 결합·무결성 검사 |
| world/quests.py | 임무별 진행 필드·표시 단계·안내 정의 |
| world/rules.py / progression.py | DB나 Evennia에 의존하지 않는 규칙 / 특성·숙련·기술 정의 |
| commands/registry.py / 각 명령 모듈 | 명시적 등록, 인자 문법과 공통 검증, 도움말 metadata |
| typeclasses/interactables.py | 윤대장·정비기록·보급상자·발전기·훈련관의 콘텐츠 행동 |
| world/multiplayer.py | 시간·인원 상수, 단일 서버 상태 변경 잠금과 트랜잭션 |
| typeclasses/parties.py | 영속 파티, 초대, 가입 순서와 리더 관리 |
| typeclasses/enemies.py | 공유 HP, 점유, 위협도, 기여도, 적 공격과 사망 전이 |
| typeclasses/loot.py | 영속 시체·바닥 아이템, 배정과 회수 |
| typeclasses/explorers.py | 개인 성장 저장, 개인 전투 입력과 공격 타이머 |
| world/bootstrap.py / lifecycle.py | 중복 없는 생성 / 시각 기반 복구 |
| world/state.py / web | 공유 월드 스냅샷 / 화면 표시와 텍스트 명령 입력 |

게임 명령은 `대상 + 행동`이다. 마지막 단어를 행동으로 해석하며, `'내용`은 나머지 전부를 채팅으로 처리한다. `내용 말`도 지원한다. 버튼은 같은 텍스트 명령을 보내며 서버가 권한과 결과를 결정한다. 메시지 문자열로 사망·보상 등 상태를 판정하지 않는다.

## 본부 Room 구조 1단계

`world/content/headquarters.py`는 1단계의 출정 대기실·본부 중앙홀, 지원동 1~3층의 복도 각 5칸, 시설 7곳과 옥상 등 Room 25개에 2단계 공용 승강기 Room을 더해 26개를 정의한다. 기존 `dock`과 탐사 구역 15곳은 유지한다. Region `headquarters`는 방문한 실제 Room을 기존 지도에 묶어 표시한다.

출정 대기실의 유일한 출구는 `남 → hq_concourse`다. 중앙홀은 `북 → staging_room`, `서 → dock`, `남 → support_1f_c`이며 부두의 `북 → grass`는 그대로다. 1층 중앙은 `북 → hq_concourse`, `서 → support_1f_w1`, `동 → support_1f_e1`이며 남쪽 출입구는 폐쇄되어 있다. 모든 출구는 기존 사방 반대 방향으로 복귀하며 별도 복귀 방향 예외는 없다. 각 층의 복도는 동서로 연결되고 시설은 북쪽으로 진입·남쪽으로 복귀한다. 층별 방향 그래프는 분리되어 있으며 2단계 승강기 명령으로 각 중앙 복도와 옥상을 오간다.

`blocked_exits`는 방향과 폐쇄 안내 문구만 저장하며 목적지·Exit 객체를 만들지 않는다. `world.navigation.blocked_exit_message()`가 기존 방향 alias로 조회하고, 미등록 명령 fallback에서 이동 입력을 처리한다. 보기 역시 목적지 조회 전에 같은 안내를 반환한다. 기존 관리 Exit가 폐쇄 방향에 남아 있으면 Exit 훅에서 이동·정찰을 차단하고 bootstrap이 해당 stable tag의 관리 Exit만 제거한다. 일반 stale 객체 감사 정책은 유지한다.

Room의 local/distant 표시 경로는 정적 설명 다음에 폐쇄 문구를 넣는다. 지도는 방문한 실제 Room의 방향 목록에 폐쇄 방향을 표시하며 1층 중앙은 `북: 본부 중앙홀`, `남: 폐쇄`다. 방향도·웹 이동 버튼·`pz_state.exits`는 실제 출구만 사용하며 1층 중앙은 서·동·북만 제공한다. 폐쇄 방향을 지도 노드나 동작 버튼으로 만들지 않는다. 기능 없는 시설에는 NPC·보관함·가짜 action hint를 추가하지 않는다.

새 캐릭터는 기존 최초 puppet의 비월드 위치 fallback에서 출정 대기실로 배치되고 새 profile의 `visited`도 대기실에서 시작한다. 재접속 시 유효한 저장 위치와 기존 방문 기록을 보존한다. Evennia fallback `home=dock`은 유지한다. 일반 귀환은 `support_roof`, 전투 패배는 `infirmary`로 명시적으로 이동한다. 상점은 지원동의 실제 Shopkeeper, 의료·휴식은 의무실의 실제 객체를 따른다. 보관·훈련 객체는 아래 3단계 배치를 따른다. bootstrap은 기존 stable tag로 Room/실제 Exit를 재사용·갱신하며 개인 기록을 초기화하지 않는다. 이전 본부 배치의 중앙홀 동쪽·1층 중앙 남쪽 관리 Exit는 같은 목적지를 유지하며 새 남쪽·북쪽 stable tag와 alias로 갱신한다. 이미 새 출구가 있다면 해당 옛 관리 Exit만 제거한다. integrity는 목적지·정반대 방향의 양방향 연결·폐쇄 문구/충돌·본부 고정 배치·시설의 유일 진입·Region membership을 검사한다.

## 본부 2단계: 공용 승강기

`support_elevator`는 safe·실내·인공광·적 없음의 실제 `ZoneRoom`이다. `exits={}`이며 승강기 호출/하차를 cardinal Exit로 만들지 않는다. 기존 중앙 복도의 폐쇄 방향도 유지한다. `world/content/elevator.py`의 `ELEVATOR_STOPS`가 안정적인 정류 층 ID(`1f`, `2f`, `3f`, `roof`)와 한국어 label·목적지 Room의 SSOT다. Command·표시·웹 상태·bootstrap·검사는 이를 재사용한다.

공용 현재 층은 승강기 Room의 persistent `db.current_stop`에 저장하며 개인 profile에는 넣지 않는다. 초기값은 `ELEVATOR_DEFAULT_STOP`이고 bootstrap은 새 Room 또는 유효하지 않은 값만 정규화한다. 정상 층은 월드 재구성·reload/restart 뒤에도 보존한다. 기존 Room·Exit stable ID와 본부 출구 migration은 유지한다.

`ZoneRoom.at_cmdset_get()`은 각 중앙 복도/옥상에 호출용 CmdSet, 승강기 내부에 층 선택/하차용 CmdSet을 제공한다. `승강기`는 호출과 탑승을 한 번에 수행한다. `1층`·`2층`·`3층`·`옥상`은 공용 층만 바꾸고 모든 승객의 location은 승강기 Room이다. `내리기`는 해당 플레이어만 현재 정류 층 Room으로 이동한다. 외부 호출은 기존 승객을 승강기에 둔 채 공용 층을 호출자의 층으로 바꾼다. 같은 층 재선택은 안내만 하며 층 attribute를 다시 저장하지 않는다. 밖에서는 내부 명령이 CmdSet에 없으므로 일반 unknown-command 처리를 따른다. 전역 명령 registry와 도움말에는 내부 층 명령을 추가하지 않는다.

`world.elevator`는 기존 `world_change()`의 단일 서버 잠금·DB transaction으로 동작을 직렬화한다. 탑승·하차는 실제 `move_to()`로 관찰·presence·visited 훅을 재사용하고 실패하면 공용 층 변경도 rollback한다. 승객 이동 알림은 `after_change()`로 성공 뒤 전달하고 기존 GameCommand의 접속자 state push로 함께 갱신한다. 실제 대기 시간·비동기 작업·문 상태 머신은 없다.

Room 본문은 기존 `world.text` semantic 조각으로 호출 방법 또는 현재 층·가능한 명령을 표시한다. `pz_state.elevator`는 서버가 결정한 `inside`, 내부의 `current_stop/current_floor`, `actions[{label, command}]`를 제공하며 이용 불가능한 곳에서는 null이다. 클라이언트는 이 값을 주변 행동에 렌더링하고 같은 텍스트 명령을 보낸다. zone ID 분기나 별도 웹 이동 API는 없다. 지도는 방문한 승강기·상층·옥상을 기존 Room 목록에 표시하며 가짜 방향 연결을 추가하지 않는다. 순수 검사는 cardinal graph와 stop을 포함한 transport reachability를 따로 확인한다.

Integrity는 승강기 Room·headquarters 소속, default·정류 층 ID/label/목적지의 유효성·중복, 정확히 세 중앙 복도와 옥상인 정류 구성, 가짜 방향 출구 금지와 기존 HQ reverse/blocked 검증을 함께 수행한다. 귀환은 옥상에 도착한 뒤 이 승강기로 이동한다. 의료·패배 흐름은 아래 4단계를 따르며 회수 자원 정산은 아래 5단계, NPC 상점은 6단계를 따른다.

## 본부 3단계: 보관·훈련 서비스 이전

`INTERACTABLES`의 기존 `shared_container`와 `personal_locker`는 `storage_room`, `instructor`는 `training_room`에 배치한다. 1층 중앙에서 서·북으로 보관실, 승강기로 2층에 내려 동·북으로 훈련실에 도착한다. 시설 문은 기존 북/남 양방향 출구를 그대로 사용하며 승강기 코드는 변경하지 않는다. 부두에는 윤대장과 탐사 출발 동선이 남는다. 의료·귀환·패배의 현재 배치는 아래 4단계를 따른다.

서비스는 Room 이름이 아니라 실제 world object를 따른다. 보관 명령은 기존 `room_objects`와 Container 대상 선택·가시성·이전 규칙을 사용한다. 훈련 명령도 기존 `resolve_action`으로 Instructor에 위임하며 현재 방의 safe 속성·비전투 상태·Observation/view 정책을 검사한다. `instructor_for`는 같은 관찰 가능한 객체 풀과 `Instructor.available`을 사용하고, 웹의 `training_available`은 그 결과에서 파생된다. 클라이언트가 시설 Room ID로 활성 여부를 판단하지 않는다. 원거리 표시는 존재만 보여 주고 contents·개인 보관·훈련 행동과 성장 상태를 노출하지 않는다.

bootstrap은 stable `primal_interactable` tag로 기존 객체를 찾아 DB ID를 유지한 채 위치·이름·alias 목록을 갱신한다. 다중 alias도 목록으로 전달해 각 이름을 보존한다. 공용 `db.items`와 각 탐사자의 `profile.storage`, 장비·성장·방문 기록에는 쓰지 않으며 profile migration도 없다. 반복 실행은 객체를 중복 생성하지 않는다. integrity는 세 서비스의 본부 배치를 검사하며 실제 사용 권한은 이 정적 배치 검사와 독립적이다.

## 본부 4단계: 의료와 복귀·패배

신규 시작은 `staging_room`, 재접속은 저장된 유효 위치, Evennia fallback `home`은 `dock`이다. `Return`은 비전투 중 `support_roof`로 실제 이동하고, 패배는 home과 무관하게 `infirmary`를 조회한다. 옥상과 의무실 이후 이동은 기존 공용 승강기·사방 출구를 사용한다.

`Doctor(ActionObject)`의 stable ID는 `doctor`(의무관/의사), `Bed(ActionObject)`는 `infirmary_bed`(침대/병상)이며 `INTERACTABLES`에서 의무실에 배치한다. bootstrap은 기존 stable tag 기반으로 하나씩 생성·재사용하며 Room·Exit·개인 기록과 기존 서비스 객체를 보존한다. Room 정적 설명은 환경만 담고 객체 presence가 실제 존재를 표현한다. integrity는 의료 배치와 행동 정의를 검사한다.

`치료`/`의무관 치료`/`의무관에게 치료`와 `휴식`/`침대 휴식`/`침대에서 휴식`은 현재 `room_objects`의 보이는 Doctor/Bed를 공통 selector로 선택한다. bare 입력은 0개면 대상 없음, 1개면 자동 선택, 2개 이상이면 명시적 지정 요구다. 숨은 대상은 개수·오류·selector·hint·Web에 포함하지 않는다. 발견 이후 `perform_action`이 같은 Room·관찰·비전투를 검사하고 각 pure rule이 현재 Room의 safe를 검사한다. 실제 객체를 다른 안전 Room으로 옮겨도 서비스는 객체를 따른다. 전투 중 보이는 대상은 대상 없음 대신 기존 RuleError로 거절한다.

`rules.treat`와 `rules.rest`는 별도 public rule이며 현재는 각각 무료·즉시 full HP다. 내부 유효성 검사만 공유하고 서로 호출하지 않는다. 최대 HP이면 쓰기 없이 거절한다. 붕대 `rules.heal`과 독립이며 아이템·크레딧·medicine 숙련·heal Rank를 변경하지 않는다. 침대 점유·예약·시간 지연은 없다.

`enemy_attack`은 피해·defeated 판정만 반환한다. `apply_defeat`가 `lost=min(credits,10)`을 차감하고 `DEFEAT_RECOVERY_HP=1`로 최소 생존 상태를 설정한다. 일반 의료 rule/객체는 호출하지 않는다. Enemy lifecycle은 하나의 `world_change` 안에서 피해·패널티·저장·`leave_combat`·의무실 이동을 처리한다. 패배자만 combatants/threat/contribution과 queued action·guard·타이머를 정리하고 다른 참가자는 유지한다. 이동 False/실패는 예외로 rollback하며 DB profile·FK와 Evennia attribute/location/contents 캐시를 복구한다. 타이머 취소와 구조 안내는 `after_change`로 commit 뒤 실행한다. 기존 `save_profile`의 deferred push가 새 의무실 상태를 패배자에게 보내므로 적 Room의 broadcast에만 의존하지 않는다. visited는 실제 이동 hook으로 의무실 방문을 추가하며 나머지 진행 기록은 보존한다. 출력 문구로 lifecycle을 판정하지 않는다.

서버 interactable allowlist에는 의료 `치료`/`휴식`만 추가한다. 같은 객체의 visible/safe/noncombat availability로 Web action과 target/action Room hint를 결정한다. 클라이언트는 서버 명령을 렌더링할 뿐 infirmary zone 특례가 없다. 부두의 휴식 버튼·hint는 제거했으며 현재는 6단계에서 상점 특례도 제거됐다. 원거리 관찰은 의료 서비스 행동을 노출하지 않는다.

의료 동선과 회복 규칙은 통합/수동 검사로 확인한다. 실제 서버 gameplay smoke는 fixture 로그인과 공동 사냥 1회, 귀환→옥상→승강기 3층→무기상 구매·재접속을 확인한다. 공개 가입 rate limit은 그대로 유지하며 gameplay smoke와 분리한다. 시체/재생성/보호의 production 시간 의미는 Full Gameplay E2E가 맡는다.

## 본부 5단계: 단일 화폐와 회수 자원 정산

Credits는 유일한 구매 currency, scrap은 material/resource다. `profile.inventory["scrap"]`와 개인 storage의 기존 저장 형식을 유지하며 migration·자동 환전은 없다. 적 전리품·이전·보관 정책과 발전기의 부품 3개 소비를 보존한다. `world/content/economy.py`의 `SALVAGE_CREDIT_RATE=10`은 정산율 SSOT다. 기존 장비용 EXCHANGE 정의/export와 구매 flag를 제거하고 `rules.buy(profile, shop_id, item_id)`는 6단계 SHOP_CATALOGS의 명시적 catalog에서 크레딧 가격을 조회한다. 5단계 당시 부두 임시 상점은 6단계에서 실제 Shopkeeper로 대체됐다.

실제 persistent `SettlementOfficer`의 stable ID는 `salvage_officer`, 표시명은 자원 정산관, alias는 정산관이며 `salvage_office`에 배치한다. 기존 bootstrap의 stable tag 재사용으로 객체 ID·alias·정상 배치를 유지하고 다른 객체·개인 profile·shared inventory를 초기화하지 않는다. integrity는 위치·환율/교환 action 정의·양의 정수 정산율과 기존 본부 구조를 검사한다.

`환율`과 `교환`은 보이는 current-room SettlementOfficer에 위임한다. discovery는 기존 `room_objects`/names/parse_selector/resolve를 사용하며 bare는 0명 거절, 1명 자동 선택, 여러 명 대상 지정 요구다. targeted 입력은 `정산관에게 회수부품 10개 교환`처럼 공통 `에게` relation과 이름/번호를 사용한다. hidden/view lock은 개수·selector·hint·Web에서 제외한다. 이용은 실제 같은 Room·can_perceive·현재 Room safe·비전투 조건이며 특정 Room ID가 권한을 부여하지 않는다. 전투 중 보이는 NPC는 기존 전투 오류를 반환한다.

`world/settlement.py`는 정산 resource와 1/N개/모두 수량만 해석한다. 일반 가방/보관/전리품 parser의 수량 범위를 확장하지 않는다. `rules.settle_salvage(profile, quantity)`는 비전투·양의 정수·가방 보유량을 전부 검증한 뒤 consume과 Credits 증가를 수행하고 획득액을 반환한다. 객체가 `caller.change()` 경계 안의 최신 profile에서 모두 수량을 구하므로 실패 시 부분 저장이 없다. 0개 inventory entry는 consume이 제거한다. 저장한 부품·임무용 부품·성장 등은 정산 대상 가방 수량 이외에 변경하지 않는다.

서버는 실제 visible/available NPC에서 환율 명령과 보유 scrap이 있을 때 대상 지정 모두 정산 명령을 만든다. 기존 interactable actions를 재사용하고 전체 ActionObject action을 개방하지 않는다. Room hint도 실제 target/action의 availability를 따른다. `pz_state.resources.scrap={name,count}`는 같은 profile snapshot의 가방에서 파생하고 Credits wallet과 구분한다. 별도 balance를 저장하지 않으며 client는 payload와 완성된 command를 렌더링한다. zone ID·NPC 이름·환율·수량으로 action을 추론하지 않는다.

## 본부 6단계: NPC 기반 상점

`Shopkeeper(ActionObject)`는 실제 persistent NPC다. `supply_shopkeeper`(보급관/보급상인)는 `supply_shop`, `weapon_shopkeeper`(무기상/무기 상인)는 `weapon_shop`, `armor_shopkeeper`(방어구상/방어구 상인)는 `armor_shop`에 배치한다. `db.shop_id`의 supply/weapon/armor가 catalog identity이며 Room ID나 NPC 이름에서 추론하지 않는다. bootstrap은 stable tag로 같은 객체를 재사용하고 정의의 위치·alias·shop_id를 정규화한다. 재고 상태·profile migration은 없다.

`world/content/shops.py`의 `SHOP_CATALOGS`가 유일한 판매/가격 SSOT다. 보급품 5종·무기 5종·방어구 4종의 기존 14개 가격을 모두 보존한다. `rules.buy(profile, shop_id, item_id)`는 비전투·유효 catalog·해당 상품·Credits 충분 여부를 전부 검증한 뒤 Credits와 가방을 함께 변경한다. scrap 정산·임무 소비·전리품·기술 가격·패배 패널티는 변경하지 않는다. 무한 재고로 매번 1개만 판매한다.

`상점`(`메뉴`/`shop`)과 `구매`는 현재 `room_objects`의 실제 보이는 Shopkeeper를 찾는다. 메뉴의 bare 후보는 모든 판매자, 구매의 bare 후보는 그 물건을 파는 판매자만이다. 0명 거절·1명 선택·여럿 대상 지정 요구이며 targeted 구매는 `무기상에게 강철마체테 구매`처럼 기존 parse_relation/names/selector/resolve를 사용한다. 번호는 기존 공통 정렬의 임시 번호다. 발견 후 같은 Room·safe·비전투를 검사하며 숨은 판매자는 selector·개수·오류·hint·Web에서 제외한다. 서비스는 실제 NPC를 따라 다른 safe Room에서도 동작한다.

메뉴는 실제 NPC 제목과 그 catalog의 Credit 가격만 표시하고 상세 보기는 메뉴/targeted 구매 사용법을 안내한다. 각 시설 hint는 actual stable NPC와 상점 action을 참조하며 availability를 확인한다. 부두의 static 상점 hint·Shop/Buy gate·Web 상점 버튼을 제거했다. 다른 사용처가 없는 `GameCommand.at_dock()`과 global SHOP도 제거했다.

모든 `ActionObject`가 `web_actions(caller, target, observed_at)` capability를 제공한다. 기본 allowlist는 대화/조사/수리/보기와 available 의료 행동을 보존한다. Container는 보기만, Instructor는 기존 대화와 별도 TRAINING UI를 유지한다. SettlementOfficer와 Shopkeeper만 필요한 동적 action을 override한다. `world.state`는 subclass를 구분하지 않고 capability만 호출한다. Shopkeeper는 available일 때 메뉴와 catalog별 targeted 구매의 완성된 label/command를 서버에서 만든다. client는 기존 렌더링을 사용하며 Room·가격·이름으로 구매를 추론하지 않는다.

Integrity는 세 판매자 배치·catalog ID/행동, catalog 비어 있지 않음·상품 존재·양의 정수 가격·중복 금지·기존 14개 합집합을 검사한다. smoke의 구매는 옥상→승강기 3층→동·북 무기점에서 실제 Credits 차감/장비 증가를 확인하고 해당 Room에서 재로그인 상태를 비교한다. 7단계 전체 closeout은 별도 요청이다.

## 공통 대상 선택

`world/targets.py`의 `TargetSelector`는 DEFAULT / INDEX / ALL을 표현한다. 일반 대상은 `<대상>`, `<대상> <번호>`, `<대상> 모두`로, 전리품 출처는 `시체에서`, `시체 2에서`, `모든 시체에서`로 해석한다. 출처 ALL도 내부에서는 같은 ALL이며, 한국어 조사에 맞춰 표시 문법만 다르다. 번호와 모두는 함께 사용할 수 없다. 실제 이름/alias 전체가 일치하면 숫자로 끝나는 이름을 우선하고, 이후 접미 선택자를 해석한다. 이전 prefix `전체` 문법은 지원하지 않는다.

`ordered()`의 객체 ID 오름차순을 Room 서술, SURROUNDINGS, 보기, 공격, 콘텐츠 행동, 시체 회수에서 공유한다. 번호는 방 안의 보이는 후보에 붙이는 1부터 시작하는 transient presentation index이며 DB에 저장하거나 객체 ID 자체를 노출하지 않는다. 같은 이름끼리 번호를 붙이되 `시체`는 방 전체 Corpse pool을 사용한다. 시체가 만료되면 남은 시체 번호도 다시 계산된다.

DEFAULT는 구조적으로 행동을 지원하는 첫 대상을 선택한다. INDEX는 표시 순서의 정확한 개체를 선택한다. 실제 점유·임무·한 번 보상·전리품 권한은 행동/규칙 계층이 판단하며 resolver가 가능한 다음 대상으로 자동 이동하지 않는다. 보기와 가져만 ALL을 지원한다. 공격·대화·조사·수리·무장·착용·구매·학습·파티 인물 조작은 단일 대상이다. 정산의 교환은 NPC 하나를 선택하고 회수부품에는 정산 전용 1/N개/모두 수량을 적용한다. 전투가 시작된 뒤 공격·강타·방어·회복·도주는 기존 combat_target을 사용한다. 특성의 `힘 2 배분`처럼 수량을 받는 명령은 해당 명령의 인자 문법을 유지한다. 파티 초대/관리의 기존 원격 캐릭터 범위도 유지한다.

`world/target_presentation.py`는 개체 수를 자연어로 묘사하고 필요한 경우에만 `'갈퀴사냥룡 1'`, `'시체 2'` 같은 지정 방법을 문장으로 안내한다. Room 본문과 세계 서술은 객체 표가 아니다. SURROUNDINGS·버튼·상태/조작 control에서는 빠른 인식과 조작을 위해 `시체 1 · 갈퀴사냥룡의 시체` 같은 compact label·번호·상태를 사용할 수 있다. `world/state.py`가 label/command를 생성하고 웹은 그대로 텍스트 명령을 전송하므로 클라이언트에 선택 parser를 복제하지 않는다.

`world.state.loot_controls()`는 웹 상태와 Corpse/DroppedLoot 상세 보기의 지정명·회수 명령을 함께 생성한다. 시체는 현재 보이는 방 전체 Corpse pool, 바닥 물건은 같은 아이템의 객체/entry 순서를 기존 helper로 계산한다. 상세 보기에는 단독으로 실행할 수 없는 `가져` 대신 `시체 2에서 모두 가져`, `회수부품 2 가져` 같은 명령을 안내한다. 시체가 하나면 번호를 생략하고, 빈 시체에는 회수 안내를 표시하지 않는다. 이 helper는 표시만 담당하며 번호를 저장하거나 권한·수량 규칙을 다시 구현하지 않는다. 실제 실행은 현재 방 상태에서 기존 resolver와 전리품 규칙을 사용한다.

전리품 요청은 `LootRequest(source, target)`로 정규화한다. `모두 가져`는 가상 target `전리품`의 ALL이다. source가 없으면 DroppedLoot를, DEFAULT source면 시체 하나만 처리한다. source ALL에는 target ALL이 필수다. target DEFAULT/INDEX는 선택 entry에서 한 개를, ALL은 일치하는 entry의 전체 quantity를 처리한다. entry 순서는 객체 ID와 객체 내부의 저장 entry 순서이며, 번호를 별도 저장하지 않는다. 회수 전 같은 timestamp로 lifecycle을 정리한 뒤 world_change에서 선택·수량 차감·배정자 저장을 원자적으로 처리한다. 보호된 entry는 ALL에서 건너뛰며 하나라도 지급되면 성공이다. 수령 권한은 기존 recipient_for를 사용한다.

## 성장의 다섯 계층

| 계층 | 역할 | 변경 방법 |
| --- | --- | --- |
| Level | 전체 성장 단계, 기존 레벨 1~10과 XP 문턱 유지 | 처치·임무 XP |
| Attribute | 현재 선택한 신체·정신 빌드 | 특성 포인트 배분, 재분배 |
| Proficiency | 실제로 해 온 행동의 장기 경험 | 유효한 개인 행동, 재훈련으로 반환하지 않음 |
| Skill | 선택해서 사용하는 전투 능력의 강도 | 교관 학습과 Rank 투자, 기술 재분배 |
| Equipment | 교체 가능한 외부 전투 보정 | 기존 드롭·크레딧 구매·착용 |

`attributes`는 각 ID별 `{base: 10, allocated: 0}`이다. 기본 10은 기존 전투 수치의 기준점이며 추가 보너스를 주지 않는다. 현재 값은 base + allocated다. 특성 포인트 총량은 `레벨 × 2 + 2`이며 Lv.1에서 4점, Lv.10에서 22점이다. 미사용 포인트는 총량에서 투자량 합계를 뺀 값으로 계산하므로 별도 가변 카운터의 중복 지급이 없다.

| 특성 | 투자 효과 |
| --- | --- |
| 힘 | 투자 2점마다 공격 +1 |
| 민첩 | 투자 3점마다 방어 +1 |
| 체질 | 투자 1점마다 최대 HP +4 |
| 지혜 | 투자 1점마다 붕대 회복 +2 |

기존 레벨·장비 공식에 위 보정을 더한다. 최대 HP는 `60 + (레벨-1)×10 + 체질 투자×4`, 공격은 `7 + (레벨-1)×2 + 장비 + 힘 투자//2 + 무기 숙련 Rank//3`, 방어는 `(레벨-1)//2 + 장비 + 민첩 투자//3`이다. 초기에는 확률 명중·회피를 추가하지 않고 민첩을 안정적인 생존 보정으로 사용한다.

## 숙련의 실제 결과와 한계

`proficiencies`는 무기(weapon), 방어(defense), 응급처치(medicine)별 `{xp: 0}`이다. 20 XP마다 1 Rank, 최대 10 Rank/200 XP다. 실제 Enemy HP를 감소시킨 개인 공격 한 번, guard로 실제 피해를 줄인 적 공격 한 번, 붕대로 실제 HP를 높인 회복 한 번에 해당 숙련 XP 1을 준다. 피해량에 비례하지 않는다.

순수 규칙의 공격 계산만으로 무기 XP를 주지 않고 Enemy의 실제 HP 감소와 개인 profile 저장을 같은 world_change 트랜잭션에서 처리한다. 적 차례와 회복도 기존 영속 next_attack_at 검사를 통과한 행동에만 적용한다. 실패·가득 찬 HP·예약/명령 반복·중복 callback은 성장시키지 않으며 타 파티원의 숙련도 공유하지 않는다. 파티의 처치 XP 분배는 그대로 별도 시스템이다.

약한 적 반복으로 최고 숙련을 달성하지 못하도록 적 정의의 training_cap을 사용한다. 어린청소룡은 Rank 2, 갈퀴사냥룡은 4, 고장난경비기은 7, 우두머리는 10까지다. 비전투 붕대 사용은 Rank 2까지다. 이미 상한보다 높은 XP는 깎지 않고 더 주지 않는다. 무기 Rank 3마다 공격 +1, 방어 Rank 3마다 guard 적용 후 피해 추가 -1, 응급처치 Rank 2마다 회복 +1이다. 모든 실제 피해의 최솟값은 1이다.

## 기술 학습과 두 포인트 경제

`skills`는 heavy/guard/heal의 Rank다. 새 캐릭터와 기존 캐릭터 모두 강타·방어·응급치료 무료 Rank 1을 갖는다. 기본 공격은 학습하지 않는다. 정의에는 id/name/description/max_rank/requirements/point_cost/credit_cost/cooldown/action_type/related_proficiency를 명시한다. 현재 기술은 최대 Rank 3이다.

| 다음 Rank | 요구 레벨 | 기술점수 | 크레딧 |
| --- | --- | --- | --- |
| 2 | 1 | 1 | 4 |
| 3 | 3 | 2 | 8 |

기술점수 총량은 `레벨 + 1`이다. 사용량은 무료 Rank를 제외한 각 Rank별 point_cost의 합계로 계산한다. 두 자원 모두 **총 획득 = 현재 투자 + 미사용** 관계를 유지한다. 포인트·레벨·크레딧·최대 Rank를 전부 검사한 뒤 한 번만 저장한다.

강타 피해 배율은 Rank 1/2/3에서 1.8/2.0/2.2이고 재사용 대기는 7.5초다. 방어는 적 피해를 `2 + Rank`로 정수 나눗셈한 뒤 방어 숙련 보정을 뺀다. 붕대 회복은 `35 + 지혜 투자×2 + (Rank-1)×5 + 응급처치 숙련 Rank//2`이며 실제 부족한 HP까지만 회복한다. 전투 중 회복은 여전히 기본 공격을 대체한다. Skill은 기존 두 타이머와 전투 상태 머신 위에 수치 계층만 더한다.

## 지원동 훈련관과 재훈련

지원동 2층 훈련실의 영속 NPC **탐사대 훈련관**은 기존 전투 기록을 분석하고 신체·전술 훈련 계획을 다시 짠다. `힘 1 배분`, `강타 배워`, `특성 재분배`, `기술 재분배`, `전체 재훈련`을 제공한다. 현재 방의 관찰 가능한 실제 교관, 현재 Room 정의의 safe 속성, combat_target이 없는 상태를 서버에서 검사한다. 훈련관이 없거나 보이지 않으면 웹과 명령 모두 이용 불가이며, 다른 안전 Room으로 옮겨도 같은 정책을 따른다. 웹 버튼도 같은 텍스트 명령만 보낸다.

현재 콘텐츠에서는 재훈련 비용을 항상 무료로 정했다. 특성 재분배는 allocated만 0으로, 기술 재분배는 무료 Rank 1로 되돌린다. 무료 Rank는 투자분에 포함되지 않으며 학습에 쓴 크레딧은 반환하지 않는다. 전체 재훈련은 복사본에서 두 풀을 동시에 계산하고 하나의 world_change/DB 트랜잭션으로 저장한다. 저장 실패 시 부분 상태가 남지 않는다.

Level·XP·Proficiency·Inventory·Equipment·Quest·Kills·Visited·Party를 유지한다. next_attack_at·heavy_ready_at·guard_until·queued_action·player_round를 초기화하지 않고 Enemy에도 영향을 주지 않는다. 체질 배분/재분배 시 `HP = min(기존 HP, 새 최대 HP)`를 적용한다. 최대 HP를 올려도 즉시 회복되지 않고 내릴 때만 clamp하므로 반복 재훈련으로 무료 회복할 수 없다. 숙련은 빌드 선택이 아니라 실제 경험이므로 반환하거나 재배분하지 않는다.

## 공통 동사와 객체 action dispatch

parser는 마지막 token으로 행동만 찾는다. Command는 인자 문법·이름 검색·공통 검증을, 대상 객체는 콘텐츠별 동작을, rules는 순수 계산과 상태 변경을 담당한다. 공백을 제거한 이름 비교는 대상 검색에서 수행하며 parser가 특정 NPC나 성장 공식을 알지 않는다.

`조사/대화/수리`는 현재 방의 ActionObject에서 이름과 supports_action을 검사하고 `perform_action(caller, action, args)`로 위임한다. `배워/배분/재분배`는 해당 서비스를 제공하는 현재 방의 객체를 찾아 위임한다. 윤대장, 정비기록, 보급상자, 발전기, 훈련관은 stable tag로 bootstrap하며 반복 실행해도 중복 생성하거나 개인 기록을 초기화하지 않는다. 다른 방의 객체에 직접 행동하는 것도 거부한다.

명령은 base, character, combat, inventory, party, social, world_actions, skills로 나누고 registry.COMMANDS에서 명시적으로 등록한다. gameplay는 기존 import 호환 경로만 남긴다. 각 명령의 category/usage/summary와 실제 aliases로 `도움말`을 생성한다. command discovery나 콘텐츠별 parser 분기는 없다.

공용 단축어는 입력 전체가 정확히 `ㅂ/ㄴ/ㄷ/ㅅ/상/능/기/장/가`일 때만 각각 `북/남/동/서/상태/능력/기술/장비/가방`으로 바꾼다. 기존 엔진 명령이 그 이름을 차지하면 엔진 명령을 우선한다. 인증·관리 명령은 기본 parser를 유지하고 작은따옴표 채팅, `내용 말`의 내용, 대상 이름 일부는 치환하지 않는다. prefix 게임 문법은 계속 거부한다.

`상태`는 전투 수치와 특성 요약, `능력`은 특성과 숙련, `기술`은 Rank·학습 조건, `경험치`는 개인/숙련 XP, `장비`는 착용품, `가방`은 전체 소지품이다. pz_state는 계산된 포인트와 성장 목록, 서버가 판단한 훈련 가능 여부를 전달한다. 웹은 profile을 직접 수정하지 않는다.

## Party의 단일 상태

Party는 위치가 없는 영속 Evennia 객체다. DB identity 하나가 파티의 고유 ID이며 leader, members, invitations, loot_mode, round_robin_cursor, created_at을 소유한다. members의 순서가 가입 순서다. Character에는 party_id 참조만 저장하며 전체 상태를 복제하지 않는다.

최대 4명, 초대는 60초간 유효하다. 초대·제외·위임·분배 모드 설정은 파티장만 가능하다. 수락할 때도 초대 유효성, 현재 소속과 정원을 재검사한다. 자신·동일/다른 파티 소속·없는 탐사자 초대는 거부한다. 중복 초대는 만료 기한을 무한 연장하지 않는다. 한 탐사자는 대기 초대 하나만 받는다.

파티장이 명시적으로 탈퇴하면 남은 가입 순서의 첫 멤버가 승계한다. 접속 종료는 파티장 변경 사유가 아니다. 마지막 멤버가 나가면 파티를 삭제한다. 교전 중 새 파티 생성·가입은 거부하며, 탈퇴·제외는 해당 탐사자의 전투 참여도 함께 정리한다. 기존 파티장의 위임은 그룹 identity를 바꾸지 않는다.

## 공유 Enemy와 두 공격 타이머

ROOMS.enemies는 spawn 정의다. 실제 적은 방의 영속 Enemy 객체다. grass:scavenger와 wreck:scavenger는 서로 다른 객체이며 현재 총 15개 spawn이 있다. bootstrap을 반복해도 기존 적의 현재 HP·사망·재생성 상태를 초기화하거나 spawn을 중복 생성하지 않는다. 최대 HP는 최신 Enemy 정의에 맞추고 현재 HP는 보존하되 새 최대치를 넘으면 그 값으로 제한한다.

Enemy가 HP/max HP, alive/respawning 상태, respawn_at, claim, claim_last_activity, combatants, contribution, threat, enemy_round, next_attack_at을 소유한다. 모든 탐사자가 같은 HP를 본다. 개인 profile에는 combat_target 참조, queued_action, next_attack_at, heavy_ready_at, guard_until, player_round만 저장한다. 적 HP는 개인 profile에 없다.

각 탐사자의 공격은 자신의 타이머로 약 2.5초마다 실행된다. Enemy도 별도 타이머 하나로 약 2.5초마다 한 명을 공격한다. 탐사자 수나 공격 명령 반복에 따라 적의 반격 횟수가 증가하지 않는다. 타이머 중복 방지와 영속 next_attack_at 검사로 입력 반복이나 지연된 콜백의 추가 공격을 막는다. 밀린 차례를 한꺼번에 실행하지 않는다.

위협도는 실제 깎은 HP만큼 증가한다. 적은 같은 방·접속 중·해당 적을 공격 중인 탐사자 중 위협도가 가장 높은 사람을 선택하고 동률은 캐릭터 ID 순서로 해결한다. 강타는 7.5초 재사용 대기시간, 회복은 다음 개인 공격을 대체하며, 방어는 개인 공격을 유지하고 다음 공격 간격 동안 받는 피해를 줄인다.

보스의 예고/돌진은 공유 enemy_round를 따른다. 능선 보스는 2·5차례에 예고하고 3·6차례에 돌진하며 밀림 보스는 3·7차례에 예고하고 4·8차례에 돌진한다. 주기는 Enemy 정의의 `special_period`를 사용한다. 도주·패배·접속 종료·장소 이탈 시 전투 소속과 위협도·기여도를 정리한다. 일반 이동은 전투 중 거부하며, 강제 이동도 이동 후 정리한다. 패배 시 장비·경험치·소지품·진행은 보존하고 최대 10크레딧을 잃으며 의무실에서 체력 1로 의식을 되찾는다. 일반 치료·휴식은 이후 플레이어가 직접 사용한다.

## 점유와 보상 자격

일반 적의 combat_mode는 claimed다. 첫 교전 탐사자 또는 파티가 점유한다. 같은 파티는 합류할 수 있고 외부 그룹은 서버에서 거절된다. 실제 전투 행동이 점유 활동 시각을 갱신한다. 명령 반복만으로 기한을 늘리지 않는다. 그룹 전원 도주·이탈·접속 종료 시 즉시 점유를 해제하며, 활동이 15초간 없으면 남은 참여를 종료하고 해제한다.

살아 있는 적은 참가자가 없고 마지막 활동부터 15초가 지나면 최대 HP로 회복하고 위협도·기여도·차례를 초기화한다. 도주 직후 재공격하면 아직 남은 HP로 싸울 수 있다. 기존처럼 도주가 즉시 적 HP를 초기화하지 않는다. 공용 보스도 전원이 이탈한 뒤 같은 유휴 회복 정책을 따른다.

우두머리는 public으로 여러 솔로/파티가 참여할 수 있다. contribution에는 캐릭터별 damage, last_action_at, group identity를 기록한다. 자기 회복·방어만으로 최초 보상 자격이 생기지는 않는다. 지원/치유 기여 가중치는 아직 구현하지 않았다.

처치 시 실제 피해 기여가 있고, 같은 방에서 접속한 채 교전 중이며, 최근 15초 내 행동한 탐사자만 적격이다. 파티에 있다는 이유로 원격·AFK·미참여 멤버에게 지급하지 않는다. 도주 후 재참여하면 이전 기여는 이어받지 않는다.

경험치·크레딧은 적격 그룹의 피해 합계 비중으로 나누고, 파티 안에서는 적격 멤버끼리 균등 분배한다. 일반 적은 점유 그룹만 존재하므로 그 그룹이 전체 풀을 받는다. 각 단계에서 최대 나머지법으로 정수 총량을 보존하며, 같은 나머지는 그룹 키/캐릭터 ID 오름차순으로 결정한다. 보스 처치 플래그도 적격 탐사자 각각에게만 적용한다. 막타와 회수 명령자는 보상 자격을 독점하지 않는다.

## 시체·아이템 배정·바닥 전리품

사망 전이는 HP 감소, alive→respawning, 경험치·크레딧·임무 보상, 드롭 추첨 한 번과 Corpse 한 개 생성을 같은 트랜잭션으로 처리한다. state와 HP 조건을 다시 검사하여 중복 호출을 무시한다. DB 실패 시 Evennia의 Attribute/identity/방 내용 캐시도 복구하고 화면 전송·예약 작업은 성공 후 처리한다.

Corpse는 실제 방 객체이며 source spawn/enemy, created_at, decay_at과 loot entries를 저장한다. 회수부품 1개와 기존 확률 장비 드롭은 처치 시 한 번 결정된다. 경험치·크레딧은 즉시 지급하지만 아이템은 가방에 자동 지급하지 않는다.

공용 보스도 시체는 하나다. 각 아이템은 정렬된 보상 그룹의 누적 피해 비중 구간에, 전체 드롭 개수로 나눈 등간격 중점을 대응시켜 그룹을 결정한다. 예를 들어 50:50 두 그룹에 두 아이템이면 각각 하나씩 배정된다. 아이템 수가 적으면 기여 비중이 낮은 그룹은 아이템을 못 받을 수 있다. 경험치·크레딧 비례 배분과는 별개이며 첫 회수자가 전체 드롭을 갖지 않는다.

선정된 파티의 실제 참여자를 가입 순서로 정렬하고 Party.round_robin_cursor를 적용한다. 아이템 한 개마다 순번을 증가시킨다. 현재 지원 모드는 round_robin뿐이며 `순번 파티분배`로 설정한다. free_for_all·need_greed·leader 방식과 관련 UI는 구현하지 않았다.

각 entry는 item, quantity, reserved_party, reserved_player, assigned_player, protection_until을 저장한다. 보호 중에는 배정된 탐사자 또는 원래 파티원이 회수를 요청할 수 있으나 실제 가방은 assigned_player에게 지급된다. 배정자는 탈퇴·접속 종료해도 바뀌지 않는다. 보호 종료 뒤에는 회수 명령자가 받는다. 특정 아이템은 한 개, `<아이템> 모두`는 선택한 출처의 같은 종류 전체 수량을 처리한다. 여러 시체 전체의 회수는 `모든 시체에서 모두 가져`로 명시한다.

시체는 처치 후 30초에 남은 entries를 DroppedLoot 방 객체로 옮기고 삭제된다. 원래 권한과 처치 후 120초인 protection_until은 그대로 유지된다. 적은 처치 후 45초(시체 30초 + 대기 15초)에 같은 spawn으로 재생성한다. 바닥 아이템은 재생성 시 삭제하지 않으며 현재 별도 영구 소멸 기한은 없다. 장기간 운영 시 누적량 관리 정책이 필요하다.

## 시각 기반 생명주기와 재시작

상수는 world/multiplayer.py에서 관리한다. persistent timestamp가 진실이며 delay/task는 실행 편의다. 서버 시작, 5초 간격 WorldLifecycle script, 보기·공격·회수 시 같은 reconcile 함수를 사용한다. 지연된 시체는 바닥으로 옮기고 재생성 시각이 지난 적은 복원한다. 보호 만료는 metadata를 지우지 않고 현재 시각 비교로 FFA가 된다. 초대도 만료 시각으로 정리한다. 반복 reconcile은 전리품을 복제하지 않는다.

재시작 때 개인 combat_target과 Enemy의 참여·위협도를 정리한다. 파티와 개인 성장 기록은 유지되며 접속 후 살아 있는 상대를 다시 지정한다. 오프라인 중 자동 사냥 보상을 주지 않는다. 비정상 연결 종료는 서버가 단절을 인지하기 전까지 전투가 진행될 수 있다.

## 기존 데이터와 운영 범위

profile의 최신 버전은 6이다. v1/v2의 개인 encounter 제거·전투 입력 필드·성장 기본값 변환을 거친 뒤, v1~v3의 첫 임무 boolean을 `quests.radio_tower`의 진행 필드로 옮긴다. `cache_claimed`는 `discoveries.supply_cache`로 옮긴다. v1~v4에는 개인 보관 `storage={}`의 기본값을 추가한다. XP, HP, credits, inventory, equipment(명시적 None 포함), kills, 완료 여부와 visited 및 개인 전투 상태를 유지한다. 이미 받은 보상은 재지급하지 않는다. v1~v5에는 개인 광원 `light_sources={}`를 보완하고 v6 반복 로드·저장은 초기화하지 않는다.

변환은 기존 프로필의 복사본에서 첫 임무·보급 boolean을 새 구조로 옮기고 오래된 key를 제거한다. 기존 플레이어는 현재 레벨에 해당하는 포인트를 즉시 사용할 수 있고, 무료 기본 기술 Rank 1과 미투자 특성은 기존 전투 성능을 유지한다. Party·Enemy·Corpse·DroppedLoot는 profile 밖에 있으므로 migration이 수정하지 않는다. 기존 DB의 로드 시 점진적으로 변환하며 DB 삭제·교체는 필요 없다. 위의 서버 재시작/재접속 전투 정리 정책과 migration 자체의 보존 정책은 별개다.

원자성 보장은 단일 Evennia 게임 서버 프로세스와 그 DB를 전제로 한다. 현재 잠금은 프로세스 내부 RLock이며 다중 게임 서버가 같은 월드를 동시에 쓰는 구조는 지원하지 않는다. PostgreSQL 설정 연결점은 있으나 이번 검증은 SQLite 기준이다. 수평 확장 전 DB 수준 락과 트랜잭션 경계·캐시 정책을 다시 설계해야 한다.

127.0.0.1 바인딩, HTTP 4001 / WebSocket 4002로 로컬 실행한다. 외부 배포 전 HTTPS/WSS, 프록시, 백업·복구·부하와 운영 권한을 검증한다. 정적 파일은 직접 제공하고 Neo둥근모 Code 글꼴도 공식 배포본·라이선스를 저장소에 포함한다. 추가 빌드/npm/CDN 의존성은 없다.

### 현재 위치 방향 표시

`ROOMS[zone]["exits"]`를 서버 이동·`pz_state.exits`·Room 텍스트 방향도의 공통 출처로 사용한다. `ZoneRoom`의 formatter는 실제 사방 출구와 연결선만 순수 문자로 출력한다. 웹 SURROUNDINGS는 CSS Grid에 같은 방향을 배치하고 기존 `data-command` 버튼으로 방향 텍스트를 전송한다. 중앙 `[현재]`는 비대화형 표시이며 기타 출구는 별도 목록으로 표시한다. 이동 후 기존 appearance/state 전송으로 즉시 갱신하고 출구 배열이 같은 주기 전송에서는 버튼을 유지한다. 일반 로그의 `textContent` 출력과 서버 이동 제한은 변경하지 않는다.

## 텍스트와 의미별 색상

세계 사건과 조회 화면은 같은 데이터를 서로 다른 형식으로 표현한다. Room·공격·처치·전리품·NPC 대화는 한국어 서술이고, 상태·능력·경험치·기술·장비·가방·상점·임무·파티·도움말은 `[제목]`과 짧은 행으로 구성한 compact 정보창이다. Room과 대상 보기는 기존 구분선과 설명·행동 안내를 유지한다. Room은 실제로 보이는 대상만 묘사하며 명령 목록을 넣지 않는다. 가능한 행동은 대상 보기와 command registry 기반 도움말에서 확인한다.

`world/text.py`의 `Text`는 색 없는 문자열과 `{text, role}` 조각을 함께 가진다. `token`, `text`, `join`, `sheet`, `compact`, `row`가 조합과 한글 표시 폭을 담당한다. 조사는 색 코드를 붙이기 전 원래 이름의 받침으로 선택한다. `world/presentation.py`는 기존 rules·성장 정의·ITEMS·SHOP_CATALOGS에서 조회값을 읽는다. Enemy/Corpse/DroppedLoot/ActionObject/Explorer의 실제 타입과 콘텐츠 정의가 대상 역할과 행동을 결정한다. 이름별 색상 목록이나 완성된 문자열 검색은 사용하지 않는다.

`rules.player_attack()`은 피해량과 구조화된 행동 결과를 반환한다. Enemy가 실제 HP 감소량을 확정한 뒤 문장을 만든다. 사망·보상·전리품 권한 판정에 출력 문장을 사용하지 않는다. 전투 공식, 타이머, 포인트 경제, 가격, 보상·배정, profile 버전과 저장 구조는 변경하지 않는다.

웹 경로는 `Explorer.msg(Text)` → `pz_log` → 허용된 role의 `<span>` → `textContent`다. 이름·대사·아이템·입력의 내용은 항상 텍스트이며 링크나 HTML로 해석하지 않는다. raw 전송으로 Evennia inline function 치환도 차단한다. 일반 인증·관리 출력은 기존 `text`/`plainText()` 경로를 유지한다. 기존 inert template는 웹으로 받은 레거시 출력에서 문자만 추출하며 live DOM에 넣지 않는다. command echo는 입력 전체를 기존 스타일로 보여주고 클라이언트 명령 parser를 추가하지 않는다.

웹 팔레트는 `primal.css`의 `--semantic-*` 변수 한 곳에서 관리한다. semantic role과 실제 색상은 1:1이 아니며 플레이어/행동/성공, 객체/보상/경고는 같은 색을 공유한다. 장비도 일반 아이템과 같은 색을 쓰고 `[착용]`으로 상태를 구분한다. 비웹 세션은 같은 조각을 이스케이프한 후 ANSI 근사색으로 변환한다. 사용자 ESC 제어문자는 제거하고 `|`는 literal로 처리한다. 기본 서버 설정은 Telnet을 비활성화한 상태다.

| 역할 | 실제 웹 색 | 의미 |
| --- | --- | --- |
| text, title | `#e1e9de` | 일반 문장·정보창 제목 |
| muted | `#9aac9e` | 보조 설명·구분선 |
| hostile, error | `#e6a08c` | 적·오류 |
| npc | `#8ecfce` | NPC |
| player, command, direction, success | `#bbdb98` | 탐사자·실제 행동/출구·완료 표시 |
| object, reward, warning | `#d6bc80` | 상호작용 객체·확정 보상·경고 |
| item | `#c7b4e6` | 소모품·재료·장비 |
| remains | `#b9a5ac` | 시체·전리품 원천 |

텍스트의 색은 클릭 기능이 아니다. SURROUNDINGS 버튼만 기존 명령을 전송하고 서버가 최종 허용 여부를 판단한다. 색이 없어도 대상 이름, 서술, `[착용]`, 임무의 `+ / > / -`, 위험 경고 문장으로 의미를 이해할 수 있다.

### 현재 방 보기와 원거리 관찰

`보기`의 정식 alias `봐`는 기존 DEFAULT/INDEX/ALL과 모든 조회 대상에 적용한다. 현재 방의 실제 Exit key/alias를 공통 resolver로 선택하므로 별도 방향 parser나 alias 목록은 없다. Exit 대상 관찰은 현재 방의 reconcile과 state push, at_desc trigger를 건너뛰며 이동/방문/임무 상태를 변경하지 않는다. 일반 현재 방·객체 보기의 기존 정밀 표시 경로는 유지한다.

`Exit.return_appearance()`는 관찰 경로를 담은 `DistantViewContext`를 만들어 목적지 `ZoneRoom.return_distant_appearance(context)`에 위임한다. Room은 `world.distant_presentation`을 통해 static Room 설명과 제한된 존재 요약을 조립한다. 일반 `return_appearance()`를 호출하거나 그 결과에서 문자열을 지우지 않는다. context에는 viewer/source_room/target_room, 선택적인 via/direction, distance와 snapshot 시각 observed_at이 있다. 현재 명령은 인접 한 칸만 선택하며 distance는 탐색/LOS를 실행하지 않는 확장용 정보다. 방향 없이 다른 관찰 수단이 같은 Room API를 호출할 수 있다.

Room description은 장소의 지형·건축·분위기·지속되는 흔적만 설명한다. Enemy/NPC/Corpse/Interactable/Container의 현재 존재·행동·상태는 객체 presentation이 담당한다. 발톱 자국·바퀴 자국·부러진 나무 등 흔적은 환경에 포함할 수 있지만 숨겨야 하는 객체를 static description에서 다시 노출하지 않는다. 모든 15개 장소를 이 기준으로 점검했다. 선착장의 밧줄/장비, 관리동의 종잇장, 둥지의 오래된 장비는 조작 객체와 무관한 환경 흔적으로 남겼다.

Enemy content definition의 `presence`와 `distant_presence`는 종류별 현재/원거리 문장이다. Enemy의 `get_local_presence()`와 `get_distant_presence(context)`가 이를 제공하고 두 Room 조립기는 이름/문장별 자연어 grouping을 유지한다. 로컬은 자세한 행동과 selector 안내를, 원거리는 제한된 움직임과 수량만 제공한다. 새 Enemy는 두 문장을 함께 정의하며 integrity 검사로 누락을 검출한다.

객체의 `DistantPresenceMixin.is_distant_visible(context)`와 `get_distant_presence(context)`가 노출 정책과 의미별 이름/단위/문장을 제공한다. Room 원거리 조립기는 객체 종류를 분기하지 않고 동일 요약을 자연어 수량으로 묶는다. Mixin과 ActionObject의 기본은 숨김이다. Commander/Instructor/Pathfinder, Container/PersonalLocker, Generator/SignalDevice만 ActionObject에서 명시적으로 opt-in하며 SupplyCache/MaintenanceLog/JungleMarker(WatchMarker/WaterMarker)/JungleCache는 숨긴다. 새 ActionObject는 설정 없이 원거리 노출되지 않는다. typeclass의 distant_visible 또는 객체 attribute override로 조정할 수 있고 기존 view access는 override와 무관하게 존중한다. Enemy/만료 전 Corpse/Explorer는 별도의 기존 노출 contract를 유지한다. Explorer는 익명 탐사자 수로만 표시하고 viewer 자신은 제외한다. 추가로 식별할 객체가 없으면 `그 밖에 눈에 띄는 것은 없다.`로 마무리한다.

원거리 객체 조립은 profile·상자 contents·loot entries를 읽지 않고 local selector/labels·행동/권한/HP 정보를 생성하지 않는다. Enemy는 살아 있고 HP가 양수일 때만, Corpse는 observed_at이 decay_at 이전일 때만 표시한다. 만료 시체를 필터링해도 삭제나 DroppedLoot 전환은 수행하지 않는다. 재생성 시각이 지난 Enemy도 저장된 alive 상태가 아니면 숨기며 실제 상태 갱신은 기존 lifecycle 소유자가 담당한다. Room view access가 없으면 장소명과 내부 객체를 보여주지 않는다.

`world.navigation.entry_block(profile, destination_zone)`는 Room requires와 임무 진행을 비교하는 pure helper다. 이동 hook은 이 결과의 기존 message로 이동을 거절한다. Exit의 `can_observe_through(context)`도 같은 결과를 사용하지만 이동 hook을 호출하지 않는다. 관찰에는 저장을 하지 않는 `Explorer.profile_snapshot()` 사본을 사용하여 구버전 데이터도 메모리에서만 변환한다. 현재 주요 진행문은 이동/관찰 모두 차단하고 목적지 이름·설명·객체를 읽거나 표시하지 않는다. 이동 가능성과 관찰 가능성은 별개 정책이며 투명 방벽 같은 미래 경계는 Exit의 `blocks_distant_view=False` attribute 또는 can_observe_through override로 관찰만 허용할 수 있다. 이 override는 이동 조건이나 view lock을 해제하지 않는다.

Room `requires.message`는 이동 실패 안내, optional `requires.observe_message`는 정찰 차단 안내다. 조건 판정은 `entry_block()`에 그대로 남기고 Exit가 관찰이 차단된 경우에만 해당 콘텐츠 문구를 선택한다. observe_message는 방향과 독립적인 문장 뒷부분이며 Exit가 기존 direction_phrase와 direction semantic token을 앞에 붙인다. 누락 시 `그 방향은 아직 자세히 살펴볼 수 없다.`라는 물리적 구조를 가정하지 않는 fallback을 사용한다. 무결성 검사는 이 필드를 강제하지 않으며, 지정했다면 비어 있지 않은 문자열인지 검사한다. 실제 진입문/출입문만 문 표현을 사용하고 임무 보고 조건은 중립적인 안내를 사용한다. `blocks_distant_view=False`와 can_observe_through override는 이 문구 선택보다 먼저 적용하며 Room view lock을 우회하지 않는다.

### Compact 정보 조회

`compact(title, *lines, summary=...)`는 기존 Text 조각을 보존하면서 제목과 요약을 한 줄에 놓고 첫 내용까지 빈 줄을 추가하지 않는다. 기존 `sheet`는 Room·대상 보기 등에 남긴다. 상태는 전투 수치·특성·장비 요약, 능력은 기본값과 투자값, 장비는 슬롯별 보정으로 역할을 나눈다. 가방은 비어 있지 않은 분류마다 한 행을 만들고, 기술은 SKILLS의 설명과 다음 조건을 그대로 한 항목에 표시한다. R은 Rank, C는 크레딧이며 비용 화면에 단위 안내를 둔다. 임무는 완료 수/전체 단계와 ASCII `+`(완료), `>`(현재), `-`(대기)로 구분한다.

기본 도움말은 registry 순서와 category를 사용한 명령 지도다. `명령이름 도움말`은 같은 metadata의 summary/usage/aliases를 표시하며 등록 별칭과 공용 단축어로도 조회할 수 있다. 상세 조회에서 단축어를 해석하는 것은 도움말 대상 검색이며 이동이나 게임 입력 parser는 바꾸지 않는다. `능력 도움말`은 ATTRIBUTES의 설명을 추가로 표시하고 기존 웹 성장 패널 tooltip도 유지한다.

웹은 기존 semantic span과 textContent 경로를 사용한다. 정보창은 `word-break: keep-all`로 공백을 우선해 줄바꿈하되 기존 `overflow-wrap: anywhere`로 공백 없는 긴 이름의 가로 넘침을 막는다. 글자 크기와 색상은 변경하지 않는다. CSS URL의 버전 표시는 이전 스타일 캐시가 새 줄바꿈을 가리지 않도록 한다. terminal ANSI 변환도 같은 Text를 사용하며 저장·경제·전투 규칙을 변경하지 않는다.

### 슬롯별 무장과 착용

`ITEMS[id].slot`이 장비 종류의 단일 출처다. `EQUIPMENT_ACTIONS`는 슬롯을 행동에 대응하며 `weapon → 무장`, `armor → 착용`이다. `Wield`와 `Equip`은 같은 구현을 사용하고 `rules.equip(profile, item_id, expected_slot)`에 기대 슬롯만 전달한다. 모든 검증은 저장 전에 끝나며 다른 슬롯·소지 수량·진행 상태는 바꾸지 않는다. 내부 규칙 호출은 expected_slot 생략 시 기존 공통 장착을 지원하지만 사용자 `equip` 별칭은 제거했다. parser는 변경하지 않았다.

대상 보기와 `pz_state.inventory[].equip_action`도 이 슬롯 대응을 사용한다. 웹은 전달된 행동을 기존 텍스트 명령 버튼으로 전송하며 장비 이름 목록을 따로 관리하지 않는다. `stats()`와 장비 화면은 양쪽 슬롯의 공격·방어를 모두 합산하므로 사냥창의 방어와 경량전술조끼의 공격도 적용된다.

장비 수치·크레딧 구매·드롭 경로는 [README 장비 표](../README.md#장비와-획득-경로)를 따른다. 두 번째 지역도 기존 장비를 활용하며 새 무기·방어구를 추가하지 않는다. 기존 장비 ID와 획득 경로를 유지한다.

## 아이템 이전·소비·보관

가방과 보관 공간은 `item_id → quantity` 스택이다. `world.targets.stack_selector()`는 기존 DEFAULT/ALL을 재사용하고 inventory INDEX와 숫자 수량을 거절한다. `parse_relation()`이 `에게`/`에`/`에서`의 경계를 추출한 뒤 기존 selector와 room ordering으로 플레이어/상자 하나를 선택한다. 여러 플레이어·상자 동시 이전은 지원하지 않는다.

`rules.move_item()`은 아이템의 명시적 `transferable` 정책, 보유 수량과 현재 equipment가 예약한 복사본 수를 검사한 뒤 source 차감·destination 증가·빈 스택 제거를 처리한다. 버려·줘·넣어·꺼내는 모두 이 규칙을 쓰며, `world.item_transfers.transfer()`가 기존 `world_change()`의 서버 잠금과 DB transaction 안에서 영속 소유자를 저장한다. 저장 실패 시 기존 DB/Evennia 캐시 rollback과 after_change 정책을 재사용한다. 마지막 공용 아이템의 두 요청도 같은 단일 서버에서 직렬 처리된다. 별도 거래/loot 권한 체계는 없다.

공용 `Container.db.items`는 persistent shared storage다. `PersonalLocker`는 같은 world object를 보더라도 caller의 `profile.storage`만 읽고 쓴다. 두 객체는 지원동 1층 `storage_room`에 배치하며 bootstrap은 기존 DB 객체의 정적 이름·위치·alias만 동기화하고 contents를 초기화하지 않는다. 사용은 현재 Room의 실제 Container resolve를 따르며 Room ID gate를 두지 않는다. 기존 일회 조사 보급상자는 변경하지 않는다. 개인·공용 보관 용량과 nesting은 구현하지 않는다.

밀림 신호전지는 `transferable=False`다. 다른 곳에 옮긴 뒤 수위 표식을 다시 조사하는 복제를 막기 위해 버려·줘·공용/개인 넣어 모두 차단한다. 회수부품과 보스 trophy는 반복 획득하거나 진행 flag로 판정하는 일반 물품이며 이동 가능하다. 직접 버린 물건과 corpse decay는 같은 DroppedLoot 생성 helper를 쓴다. 직접 버린 entry만 예약/배정 없이 protection_until=0으로 생성하고 기존 corpse 권한은 보존한다.

equipment 슬롯은 `None`을 정상 값으로 허용한다. 해제/벗어는 소지 수량을 바꾸지 않으며 stats·상태·장비·전투 문장·웹 state에서 빈 슬롯을 처리한다. 맨손 공격은 기존 base attack과 성장 보정만 사용한다. migration은 명시적 None을 초기 장비로 되돌리지 않는다.

야전식량/정제수의 `consume_action`과 `heal`이 소비 행동과 고정 효과의 출처다. 비전투 중 하나만 사용하고 최대 HP에서는 소비하지 않는다. 붕대 회복과 치료 숙련/성장 보정을 재사용하거나 변경하지 않는다. 모든 이전과 장비 해제도 비전투 중만 허용하며 줘의 받는 탐사자도 비전투 상태여야 한다. 웹은 서버의 remove_action/consume_action을 기존 텍스트 명령 버튼으로 전송한다.

## Region·임무·Gate 확장

`world/content/starter.py`에는 기존 8개 Room/4종 Enemy의 stable ID를 보존한다. `deep_jungle.py`에는 7개 Room/4종 Enemy를 정의한다. `items.py`는 공통 아이템, `shops.py`는 세 상점 catalog와 가격을 담고 `content/__init__.py`가 기존 `from world.content import ROOMS, ENEMIES, ITEMS` 경로를 유지한다. `REGIONS[region].rooms`는 각 지역 파일의 Room key에서 파생되므로 Room↔Region 소속을 두 곳에 입력하지 않는다. `ROOM_REGION`은 이 정의에서 파생된다. ID 충돌·참조 누락·출구 역방향·spawn 충돌은 `content.integrity.errors()`로 검사한다.

첫 지역 `dock`~`ridge`의 Room ID, `zone:enemy` spawn ID, 기존 아이템 ID를 바꾸지 않았다. `ridge` 북쪽에 밀림 입구를 연결했다. Spawn을 다른 Room으로 옮길 때는 새 Room의 `spawn_ids[enemy_id]`에 이전 stable tag를 명시하면 동일한 Enemy 객체와 HP를 유지한다. Room의 `requires`는 도착 시 필요한 임무 ID·진행 필드·거절 문구를 선언한다. `Explorer.at_pre_move()`는 이 데이터만 해석하며 지역 이름을 하드코딩하지 않는다. 통신탑은 발전기 복구, 밀림 입구는 첫 임무 보고, 연구구역 외곽은 밀림의 두 표식·신호전지를 확인한 신호 장치 가동을 요구한다. `exits`는 기존 `방향 → Room ID` 형태를 유지해 방향도·웹 버튼·서버 이동이 같은 정의를 읽는다.

`world/quests.py`의 임무별 단계는 `flag/대상/의미 역할/설명`과 안내문으로 구성된다. 선행 임무 조건 `requires`와 시작 전 표시 여부 `visible_from_start`도 임무 정의가 소유하며, 안내 선택과 임무 화면은 이 정의를 순서대로 읽는다. profile은 `quests[quest_id][flag]`와 개인 일회 발견용 `discoveries[id]`를 저장한다. 조회 화면은 완료 임무를 한 줄로 압축하고 진행 임무의 완료·현재·대기 단계를 보여준다. 웹 `pz_state`는 현재 안내 외에 Region ID/이름을 전달한다. 실제 임무 행동은 `ActionObject` subclass와 순수 `rules` 함수가 처리하므로 임무 DSL이나 새 parser는 없다.

`build_world()`는 Room 이름·설명, Exit 방향·별칭·목적지, 상호작용 객체 이름·별칭·위치, Enemy 이름·ID·최대 HP와 유휴 spawn 위치처럼 정적 정의가 소유하는 값을 동기화한다. 현재 HP는 유지하되 최대 HP가 낮아졌다면 새 최대치로 제한한다. Enemy의 교전 중 위치, state, respawn_at, claim, combatants, contribution, threat, round·timer·last_activity와 시체·바닥 전리품, 파티, 플레이어 profile·가방·임무는 런타임이 소유하므로 초기화하지 않는다. 삭제된 관리 Exit/Interactable/spawn은 `stale_definitions()`로 보고하지만 자동 삭제하지 않는다. 실제 운영 DB에서 제거가 필요하면 상태와 참조를 확인한 뒤 별도 작업으로 정리한다. Region 3 추가 시 지역 정의, 필요하다면 작은 행동 subclass, 임무 정의 및 순수 규칙 함수를 더하고 무결성 검사를 통과시킨다.

밀림 신호전지는 두 번째 지역 임무 전용 열쇠다. 수위 표식은 문이 닫혀 있고 전지가 없을 때만 한 개를 지급하며, 신호 장치 가동은 조건을 모두 확인한 뒤 전지 한 개를 소비하고 gate_open을 기록한다. 철갑등짐승은 신호전지 대신 일반 회수부품을 확률적으로 남긴다. 이미 문을 연 개발 데이터의 잔여 전지는 bootstrap이나 profile 변환에서 임의로 삭제하지 않는다.


## 자동 테스트의 월드 준비와 격리

`scripts/dev.py test`는 순수 규칙 검사를 실행한 뒤 `server.conf.settings_test`로 Evennia 통합 검사를 실행한다. 테스트 설정만 메모리 SQLite·빠른 비밀번호 해시를 사용하며 운영 DB와 인증 설정은 유지한다. 로컬은 최대 4개, CI는 2개 프로세스를 사용하고 Django의 테스트 DB 복제·rollback·결과 수집을 재사용한다. `server.conf.test_runner`는 Windows spawn worker의 설정 모듈 경로와 Evennia 초기화를 보완한다. 병렬 traceback 전달에는 개발 의존성 `tblib`를 사용한다. 실패한 `subTest`는 테스트 객체 전체 대신 이름·조건을 전달해 Evennia 캐시·Mock 직렬화 오류를 피하고 원래 예외와 traceback을 보존한다.

`tests.base.WorldCommandTest`는 클래스 transaction에 실제 `build_world()` 결과를 준비하고 Room ID만 보관한다. 테스트별 준비에서는 ID로 실제 Room을 일괄 조회하므로 ORM 객체·Attribute·NDb를 공유하지 않는다. 테스트 본문의 `build_world()`는 실제 bootstrap을 수행해 반복 생성·정적 갱신·migration 경계를 계속 검증한다. 최초 로그인 전에 월드가 없어야 하는 본부 검사는 `GameCommandTest`로 기존 준비 순서를 유지한다.

DB rollback만으로 Evennia의 NDb와 전역 명령 캐시는 복원되지 않는다. 공통 테스트 base는 기존 계정·세션 teardown을 수행한 뒤 DB rollback 경계에서 idmapper와 명령 merge cache를 비우고 GC를 한 번 수행한다. 클래스 transaction 종료에도 캐시를 비워 다음 그룹을 격리한다. 이 처리는 테스트 전용이며 서버의 캐시·타이머·월드 동작을 변경하지 않는다. `tests/test_fixtures.py`는 Room·출구·적 HP·보관함·추가 객체·NDb 상태를 변형하고 정순·역순 모두 다음 테스트에 남지 않는지 검증한다.

## 동적 환경: Room / Environment / Object

장소 고유의 기후 성향과 흔적은 static description에 둘 수 있지만 현재 기상 상태를 직접 표현하지 않는다. 부두의 해안·숲, 관리동의 오래된 누수 흔적, 습지의 지속적인 습기는 static이며 실제 안개·강우는 Environment가 소유한다. 새 표현의 회귀 검사는 특정 금지 단어 전체가 아니라 알려진 충돌 문구와 clear/fog/rain 전후의 static·객체 불변을 검증한다.

Environment 저장 형식은 `ENVIRONMENT_VERSION = 1`로 식별한다. version 없는 초기 PR 값은 legacy v0로 읽고 순수 `normalize_state()`가 사본에 version만 추가한다. clock epoch, weather와 seed/step·기한은 보존하며 DB 기록은 기존 reconcile transaction에서 한 번 수행한다. 조회의 정규화는 저장하지 않고 두 번째 reconcile은 변경이 없으면 다시 쓰지 않는다. 지원 범위를 넘는 version은 명확한 오류를 발생시키며 초기화하지 않는다. 캐릭터 profile version과는 독립적이다.

내부 weather/period 변화와 사용자 ambient 알림은 다르다. `publish_changes(before, after, zones, observed_at)`는 동일 시각의 `state_snapshot()`으로 저장된 전·후 period/weather를 유지해 문장을 비교한다. 일반 조회용 `snapshot()`은 현재 시각까지 순수 reconcile을 투영하므로 과거 상태 비교에 쓰지 않는다. 표현이 같은 고정 조명 실내의 period 변화는 메시지를 생략하고, rain→storm처럼 실제 실내 빗소리가 달라지면 발행한다. 웹은 두 경우 모두 기존 sweep로 최신 시간대/시각을 받는다. FIELD GUIDE의 환경 확인은 기존 data-command 경로로 날씨를 실행하고 CSS/JS query version은 광원 배포용 `lighting`이다.

Room description은 지형·건축·분위기·지속되는 흔적, Environment는 현재 시간·날씨·달·밝기, Object presence는 현재 존재와 행동을 담당한다. 정적 Room 설명이나 Enemy presence에 현재 비/밤 정보를 복제하지 않는다. 현재 방은 `Room.desc → Environment 문장 → 방향도 → local presence`, 원거리는 `방향/이름 → Room.desc → Environment 문장 → distant presence` 순서다. 환경 문장은 기존 `muted` semantic role을 사용한다.

`world/content/environment.py`는 시간대·달·날씨·전이·빛·노출별 문장의 선언형 SSOT다. `REGIONS[*].weather_zone`은 두 Region 모두 `island`를 가리킨다. 각 Room은 반드시 `exposure`(outdoor/sheltered/indoor)와 독립적인 `light_profile`(natural/filtered/dim/artificial)을 정의한다. office는 indoor/filtered, generator는 indoor/dim, jungle_watch는 sheltered/natural, jungle_nest는 sheltered/filtered이며 나머지는 콘텐츠의 하늘/수관 노출을 따른다. 무결성 검사는 누락·잘못된 값, Weather Zone 참조, 초기 날씨, 전이 대상·양수 가중치·지속 시간·노출별 문장을 검증한다.

`world/environment.py`는 DB/Evennia 없는 순수 계산이다. 4배속 시계는 `game_epoch + (observed_at - real_epoch) * time_scale`로 계산하며 매 tick 시각을 저장하지 않는다. 05/07/18/20시 경계로 시간대를 선택한다. 게임 28일 중 1–4/25–28일은 삭, 12–18일은 보름, 나머지는 반달이며 빛은 0/2/1이다. 달빛은 밤에만 더한다. 자연광은 시간대 빛(밤0/새벽2/낮4/해질녘2)+달+기상 보정+profile 보정으로 계산한다. filtered는 -1, dim은 고정1, artificial은 고정3이다. 점수 4 이상 bright, 3 normal, 1–2 dim, 0 이하 dark다. 시야는 기상 악화와 밝기 악화의 큰 값이며 실내는 직접 기상 악화를 적용하지 않는다. 환경 등급은 Observation을 거쳐 실제 식별에 적용하며 전투 피해 공식은 바꾸지 않는다.

불변 `EnvironmentSnapshot`은 observed_at·게임 날짜/시각·시간대·Weather Zone·날씨·달·exposure·light_profile·최종 밝기·시야를 담는다. 관찰 시작에 얻은 단일 observed_at을 Room, 기존 DistantViewContext, 날씨 명령과 웹 상태에 전달한다. `display()`는 안정적 ID와 한국어 표시명을 분리한다. 웹은 서버 payload를 textContent로 표시하며 자체 시계/기상 계산을 하지 않는다. 목적지 view lock/진행 관찰 차단은 환경 snapshot 계산보다 먼저 검사한다. 환경 조회는 profile migration을 저장하지 않는 profile_snapshot 경로를 사용하며 방문·임무·객체 lifecycle을 진행하지 않는다.

`world/environment_state.py`만 영속 Script 상태와 접속자 발행을 담당한다. 기존 단일 `WorldLifecycle`의 `db.environment`에 clock epoch, 마지막 period, zone별 weather/started_at/next_change_at/RNG seed·step을 저장한다. 5초 sweep에서 순수 reconcile 결과가 달라질 때만 저장한다. seed+step으로 전이를 재현하므로 정상 중단 구간은 한 번에 복구하든 자주 sweep하든 같은 결과다. 조회도 같은 pure reconcile의 사본을 사용하여 deadline과 sweep 사이 상태를 투영하지만 저장·이벤트는 수행하지 않는다. 신규 zone 초기화는 기존 clock을 보존한다. 서버 bootstrap은 Script를 확보한 뒤 restart reconcile하며 기존 상태가 있으면 epoch나 날씨를 초기화하지 않는다.

재시작 시 지난 deadline을 따라 최종 유효 구간까지 복구하고 과거 이벤트는 재생하지 않는다. 매우 긴 중단은 한 reconcile당 256회로 제한하고 이후 현재 시각에서 새 지속 구간을 시작한다. 이 제한을 넘는 중단은 세부 기상 이력을 재현하지 않는다. 변경은 기존 world_change transaction 안에서 저장하며 성공 후 callback으로 발행한다. 저장/외부 transaction 실패 시 상태와 알림을 되돌린다. 최종 weather 또는 period가 실제 달라진 zone의 **현재 session이 있는** 탐사자 중 해당 Room의 환경 표현이 달라진 사람에게만 1–2문장을 보낸다. 같은 날씨의 기간 갱신이나 매 sweep는 로그를 추가하지 않는다. 웹은 기존 sweep의 push_state(observed_at=now) 한 경로로 갱신한다.

환경 데이터는 캐릭터에 저장하지 않는다. profile v6는 개인 광원 상태만 추가하며 타이머·점유·참여 보상·Corpse/DroppedLoot·파티 정책을 유지한다. LOS·날씨 API·조도 전파 엔진·환경 피해는 이 범위에 없다.


## 관찰, 광원과 공용 시설

EnvironmentSnapshot은 viewer-independent 공용 환경이다. Room은 장소, Object는 현재 존재와 행동, immutable ObservationContext/ObservationSnapshot은 특정 관찰자가 실제 식별할 수 있는 정보를 소유한다. `world/observation.py`의 순수 `observe()`는 공용 snapshot과 읽기 전용 profile 사본에서 effective_light/effective_visibility를 계산하며 손전등을 ambient_light에 넣지 않는다. 같은 방의 A/B에게 환경 값은 같고 손전등 사용자의 시야만 달라질 수 있다.

시야 clear/reduced/poor와 객체 detectability conspicuous/normal/subtle을 중앙 matrix로 판정한다. clear는 모두, reduced는 conspicuous와 normal, poor는 conspicuous만 식별한다. Exit는 환경으로 숨기지 않는다. NPC·큰 시설·Container·Boss·비상장비함은 conspicuous, 일반 Enemy/Player/Corpse는 normal, 작은 기록·표식·보급품·DroppedLoot는 subtle이다. typeclass 기본값 또는 객체 `detectability` attribute로 확장한다. distant_visible의 기본 hidden/명시적 opt-in과 view lock은 먼저 유지하며 광원으로 우회하지 않는다.

`targets.visible()`는 view permission, `can_perceive()`는 환경상 지각을 담당한다. 공통 room_objects/resolve, Room local/distant presence, 웹 SURROUNDINGS, ActionObject.perform_action, transfer와 신규 Enemy.engage가 같은 정책을 사용한다. 시체 존재와 내부 작은 전리품은 별도 해상도다. 내부 아이템·회수는 subtle 지각을 요구한다. 기존 combat_target은 전투 중 어두워져도 추적하며 신규 상대 획득만 제한한다. 잠긴 Exit는 destination Environment/Observation을 만들기 전에 차단한다. 원거리 관찰은 profile·임무·방문·lifecycle을 진행시키지 않는다.

Light Source는 strength/range/power_type을, Power Source는 type/capacity_seconds를 선언한다. 호환성은 타입 일치로 판단하고 parser는 특정 battery ID를 분기하지 않는다. canonical 전원 삽입은 `<광원>에 <전원 소스> 넣어`이며 기존 parse_relation/stack_selector와 Store를 재사용한다. 예를 들어 `탐사용손전등에 고용량건전지 넣어`는 새 compatible 아이템 정의만 추가하면 같은 경로를 사용한다. 용량은 전원 정의가 소유하며 손전등 상수로 고정하지 않는다.

profile v6의 `light_sources[item_id]`에는 on, power_source, charge_seconds, started_at을 저장한다. v1~v5 migration은 기존 inventory/equipment/storage/quest/growth/combat을 보존하고 빈 light_sources만 보완한다. 켠 동안의 잔량은 `charge_seconds - (now - started_at)`으로 투영한다. tick마다 차감·저장하지 않고 소진 때 한 번 off/0/전원 없음으로 확정한다. 꺼짐·마지막 session 종료·정상 서버 종료에는 잔량을 확정하며 오프라인 동안 사용하지 않는다. 강제 종료로 마지막 종료 hook이 실행되지 않으면 재시작에서 off로 정규화하며 종료 전 정확한 잔량은 보장하지 않는다.

전원 삽입은 inventory 차감과 장치 상태 설정을 world_change transaction에 함께 저장한다. 잔량이 남은 전원은 교체를 거절하고 부분 충전 아이템 회수는 제공하지 않는다. stack 모델에서 마지막 광원을 이전하면 내부 전원은 폐기하고 안내한다. 여분 복사본만 이전할 때는 개인 active 상태를 보존한다. 전원/광원 일반 아이템의 이동 및 기존 장착·임무 아이템 보호는 공통 transfer 규칙을 유지한다.

공용 시설은 WorldLifecycle의 별도 `db.facilities = {"version": 1, "states": {"outpost_power": bool}}`에 저장하며 개인 generator_fixed에서 추론하지 않는다. `content/facilities.py`의 FACILITIES는 ID/초기값, Room `facility_lights`는 조명 연결, 저장 state는 현재 on/off를 소유한다. FACILITY_STATE_VERSION과 순수 new/normalize helper는 legacy bare dict의 True를 보존하고 None/빈 값에 기본값을 보완한다. 지원하지 않는 미래 버전은 오류로 중단하며 덮어쓰지 않는다. light_for 조회는 정규화 사본만 읽고 lifecycle/mutation transaction에서만 변환을 저장한다. 조명은 양수 strength와 always_on/power 중 정확히 하나를 선언한다.

발전기 수리의 개인 부품/보상/진행과 shared flag는 하나의 transaction이다. A가 수리해도 B의 개인 조건은 그대로이며 물리 조명은 동일하다. base light는 시간대·달·날씨·light_profile에서, facility light는 상시/공용 전력에서 계산하고 ambient light는 두 값의 최대다. 시설 조명이 존재하는 것과 밝기를 실제로 개선하는 것은 다르다. facility가 base보다 강할 때만 시설 문장으로 강조하며 맑은 낮 부두는 낮빛 표현을 유지한다. 부두 캠프는 상시 4, 관리동/발전실은 outpost_power일 때 4다. False→True에서 영향권 접속자에게 시설 가동 사건을 한 번 보내고 True→True는 반복하지 않는다. 기존 상태 push도 유지한다. bootstrap은 runtime state를 초기화하지 않고 Script attribute cache도 rollback에서 복원한다.

Room `hints`는 stable INTERACTABLES ID/action 또는 일반 text를 참조한다. 대상 이름은 INTERACTABLES가 SSOT이며 실제 방 객체의 태그·지원 행동과 can_perceive를 검사해 안내한다. hint와 SURROUNDINGS/selector는 같은 observed_at의 Observation 정책을 공유한다. clear에서는 지각 가능한 대상 안내와 일반 text를 원본 선언 순서대로 함께 출력한다. 제한된 시야에서는 지각 가능한 대상 안내만 출력하고, 없으면 광원 안내로 대체한다. 숨겨진 객체 이름을 일반 text에 넣지 않는다. wreck의 conspicuous 비상장비함은 poor에서도 안내하고 subtle 보급상자는 clear에서 안내한다.

광원 보기는 정적 item_appearance에 Look이 읽기 전용 lighting.status를 전달해 설명·상태·사용법을 조합한다. presentation은 player DB를 읽지 않는다. 확인은 같은 status helper를 쓰는 빠른 조회이며 동일 observed_at에서 보기/웹 잔량도 같은 ceil 분 표시를 사용한다. 일반 아이템 보기는 정적 정보를 유지한다. 광원이 환경 weather visibility까지 보완하는 것은 이번 matrix의 의도적 단순화이며 lux·LOS·전력망·연료·부분 전원 회수·은신·날씨 전투 modifier는 범위 밖이다.

기존 버전에서 발전기 개인 복구를 마친 캐릭터도 공용 전력이 아직 꺼져 있으면 수리 명령으로 가동할 수 있다. 이때 부품·보상·개인 진행을 다시 변경하지 않으며, 이미 가동된 시설에는 중복 보상을 주지 않는다.

웹은 environment와 observation을 분리하며 현재 시야와 손전등 상태를 표시한다. 가방의 켜기/끄기/확인은 서버 명령을 보내고 compatible 전원별 삽입 버튼은 실제 아이템 이름을 포함한다. 렌더링이나 시각 조회는 전원 소모를 저장하지 않는다.

## 테스트 계층과 실제 서버 smoke

| 계층 | 검증 책임 | 제외하는 책임 |
| --- | --- | --- |
| Pure | DB 없이 규칙·콘텐츠·타이밍 기본값·guard/CLI/harness 계약 | 실제 네트워크·scheduler |
| Integration (`dev.py test`) | memory SQLite·빠른 해시·병렬 격리, 주입 시간/delay patch로 lifecycle·rollback·상태 경계 | production wall-clock·브라우저 |
| Quick Live Smoke (`dev.py smoke`) | 실행별 SQLite·fixture 인증·실제 Evennia/WS/delay callback·공동 사냥/HQ/구매/재접속 연결 | production 지속 시간·공개 가입 정책 |
| Full Gameplay E2E (`dev.py smoke-full`) | production combat·30/45/120초, 본부 전체 서비스·패배·두 임무/보스 최종 보고 | signup 610초·브라우저·모든 branching |
| Restart E2E (Full 내부) | 같은 SQLite의 실제 Portal+Server 종료/시작·재인증, profile/party/shared state 보존과 전투 정리·lifecycle callback | 강제 OS crash·PostgreSQL |
| Manual Browser | 표시·버튼/명령 동등성·반응형·실제 OS IME를 필요한 범위에서 확인 | 자동 통과로 IME를 대체하지 않음 |
| Auth/Registration policy | 공개 가입·이름/암호·production throttle 정책 | gameplay smoke의 선행 조건으로 사용하지 않음 |

`world/timing.py`가 production 2.5/30/15/120/15/15/15초 기본값을 갖고 `world.multiplayer`는 선택적인 `PRIMAL_*` settings를 읽는다. `settings_test`는 타이머를 줄이지 않는다. `server/conf/smoke_support.py`의 Quick 값은 0.25/1/1/2/2/2/2초이며 Full은 production 기본값을 그대로 쓴다. 기존 적·캐릭터·Corpse의 실제 `delay()` 및 WorldLifecycle의 5초 sweep을 재사용한다. fake Clock나 새 scheduler framework를 만들지 않았다.

`scripts/smoke_harness.py`는 실행마다 새 작업 경로에 게임 코드/새 SECRET_KEY·SQLite를 준비하고 `smoke_setup.py`를 별도 프로세스에서 실행한다. DB 접근 전 marker·정확한 작업/DB 경로·SQLite engine을 검증한다. 사용자 PostgreSQL 환경은 제거한다. 정상 Evennia Account/Character API로 일반 fixture 계정을 만들고 기본 quest/파티/전투/시작 위치와 구매 자금/HP를 준비한다. 비밀번호는 runtime 메모리와 자식 stdin으로만 전달한다. 결과 장비/시체는 scenario의 실제 동작으로 생성한다.

정상 초기 객체·static 준비를 마친 fixture DB에 초기 setup 완료를 기록해 첫 실행의 자동 재시작을 피한다. 실제 Twisted foreground Portal/Server를 각각 시작해 exit를 추적하고 loopback HTTP/WS readiness를 polling한다. scenario 중 health monitor가 server premature exit를 실패로 전파한다. 실패·interrupt·성공 모두 자체 Popen/process group만 종료하며 개발 서버 launcher stop/reload를 호출하지 않는다. 성공 시 자신이 생성한 marker 경로만 삭제하고 실패 시 진단 DB/로그를 남긴다. CI는 기존 `test`와 추가 `smoke` job을 실행하고 Full은 제외한다. 실패 단계는 로그 tail만 출력하며 DB는 출력/업로드하지 않는다.

Quick/Full의 client·단계·predicate 대기를 공유한다. 공개 register/610초 sleep·5회 반복 사냥을 제거하고 auth/party/combat/corpse/lifecycle/protection/respawn/shop/persistence 단계별 결과를 출력한다. 시체 배정/파티 회수 권한을 읽고 그대로 남겨 그 시체의 ground 전환과 outsider 회수를 검증한다. Full은 실제 관찰 시각의 허용 오차를 적용해 지나치게 빠른 production 만료를 탐지한다. 일반 플레이 SQLite의 hash·mtime·size는 실행 전후 비교할 뿐 migrate/fixture/cleanup 대상이 아니다. 프로필 schema나 production 게임 밸런스는 바꾸지 않는다.


## 본부 7단계: 통합 closeout

훈련·Doctor·Bed·정산관·Shopkeeper에서 같은 Room/safe/비전투/지각의 동일한 조건만 작은 `_service_available` helper로 통일했다. Shopkeeper는 유효한 shop_id도 요구한다. Container는 기존 실제 대상 resolve와 transfer 정책을 유지하며 전투 조건이 다른 일반 조사 객체와 억지로 공통화하지 않는다. `ActionObject.web_actions()` capability와 subclass override는 이미 서버 명령을 소유하므로 유지한다. Room hint의 치료/휴식/환율/상점 availability 분기는 현재 선언과 일반 action의 서로 다른 의미를 정확히 구분하고 있어 유지한다. 새로운 service/action framework는 없다.

runtime at_dock/global SHOP/EXCHANGE/교환 구매 flag 및 client service zone gate는 없다. 지도에서 현재 Room을 표시하는 zone 비교와 content graph·정적 배치·integrity·테스트 경로는 정상 사용이다. 옛 중앙홀/1층 중앙 관리 Exit migration은 기존 DB 호환을 위해 유지한다. 가격·정산율·보상·타이머·profile schema는 변경하지 않는다. 귀환 후 윤대장에게 보고하는 안내는 부두로 직접 귀환한다고 읽히지 않도록 정리했다.

Full만 `scripts/smoke_closeout.py`를 이어 실행한다. 공용/개인 보관, 정산·훈련·Doctor/Bed, 세 상점과 장착, 일반 귀환·실제 적 패배, 발전기 부품 소비·첫 보고, 밀림 표식/신호전지/gate·두 보스를 actual parser/DB/scheduler/WS로 검증한다. Snapshot은 marker/path/SQLite guard 이후 격리 DB에서 읽기만 하며 비밀번호를 조회하지 않는다. Quick은 기존 공동 사냥 1회와 빠른 연결 검증 범위를 유지한다.

Restart는 harness가 소유한 foreground Portal과 Server를 모두 종료하고 같은 DB·설정·포트로 다시 시작한다. 새 migrate/fixture/reset은 하지 않는다. restart 동안만 기존 health monitor를 유예하고 readiness 실패/종료 오류는 그대로 실패한다. 재인증 후 캐릭터 DB ID·위치·home=dock·성장/임무/방문·보관, party membership, 승강기 3층·공용 상자·시설·환경 clock을 비교한다. live combat/claim은 정리되고 남은 시체 deadline과 respawn은 실제 callback/sweep으로 완료되며 전리품 entry는 ground에 보존된다. 광원은 기존 마지막 session/restart의 off 정책을 따르므로 지속 점등을 기대하지 않는다.
