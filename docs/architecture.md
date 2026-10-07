# 원시구역 구조와 설계 결정

## 현재 runtime contract와 명시적 변환

일반 아이템은 ItemEntity, 실물 전리품 권리는 LootClaim, 보급칩 전리품은 CurrencyLoot/CurrencyLootShare, 접근 권한은 Credential ItemEntity가 SSOT다. 문서 끝의 Phase 1~5 legacy 설명은 당시 기록이며 cutover 이후 gameplay backend로 사용하지 않는다. `ItemRuntime.version=1`과 Explorer/native loot marker를 검사하고 미변환 world는 서버 시작과 일반 item 접근에서 migration-required 오류를 낸다.

`item_migration.scan/convert/audit/workflow`는 source 계획, 원자적 변환, legacy/native 독립 대조, 운영 단계로 나뉜다. ItemMigrationLedger는 version/kind/영속 ObjectDB ID의 DB unique와 원본 digest·완료 snapshot을 저장한다. apply는 source별 완료만 기록하고 global marker는 verify 성공 후 별도 cutover에서 설정한다. 로그인·명령·startup conversion과 dual-write는 없다. 실제 운영 절차와 재시도는 [item-migration](item-migration.md)을 따른다.

EquipmentProfile의 inventory는 DB에서 파생한 일시적 수량 계산 context다. pure rules의 보상·소모 delta는 owner lock 안에서 item_inventory가 실제 Entity에 적용하고 저장할 때 legacy item 필드는 원형으로 되돌린다. equipment/storage/light_sources legacy 필드는 gameplay에서 읽지 않는다. item location·UUID·tree·state mutation은 기존 API와 full_clean을 사용하며 장비 및 광원 reference hook을 유지한다. quest 자원 제출은 명시적 tree operation `submit`으로 구분한다. Shopkeeper는 재고를 소유하지 않고 source/sink로 동작한다.

가격·modifier·drop·Boss scaling은 pure content/rules 계층, actual-shot 감소·지급·migration은 persistence 계층이다. Boss 참여자 수는 기존 reward_groups를 재사용하고 한 encounter에서 감소하지 않는다. 추가 max HP만 current HP에 더해 이미 입힌 damage를 보존한다. 전체 회복 또는 respawn 후 다음 encounter는 1명 기준으로 시작한다. [최종 콘텐츠](final-content.md)의 확정 수치를 임의 tuning하지 않는다.

## 현재 접근·상점·전리품 계약

Quest state는 entitlement와 진행 이력이며 access authority는 실제 Credential ItemEntity다. `can_enter`는 Room availability → 개인 credential → 기존 quest 환경 gate를 읽기 전용으로 검사한다. 파티에 권한을 공유하지 않고 제한실에서 public 공간으로 나갈 수 있다. [출입증·접근·상점](credentials-access-shops.md)을 따른다.

Shopkeeper는 재고 owner가 아닌 source/sink 서비스다. `purchase_catalog`는 구매 목록, `accepts`는 매입 category다. `shop_service`는 credits와 ItemEntity 생성·삭제를 한 transaction으로 처리한다. 일반 아이템·소각·보관도 native Entity를 사용하며 archive profile 필드에 쓰지 않는다. [장비](equipment.md), [광원·총기](lighting-firearms.md), [전리품](loot-claims.md), [아이템 API](item-entities.md)는 현재 계약을 먼저 설명한다.

## 지원 운영 구성과 설치

현재 지원 구성은 SQLite + single Evennia server다. 현재 전환할 실제 플레이 DB는 없으며 최종 운영 시작은 fresh empty DB → schema → 첫 서버 시작의 `initialize_fresh`/ItemRuntime.version=1 → native bootstrap → 새 Explorer 순서다. 기존 DB 업그레이드는 별도 maintenance migration 경로다. [설치](installation.md), [Phase 7A/B/C 경계](phase7-final-integration-audit.md), [PostgreSQL future infrastructure](postgresql-transition.md)를 따른다.

## 정신력과 주기 회복

`world/progression.py`가 레벨 기본 능력치·특성·기술 수치의 SSOT이며 `world/rules.py`가 현재 자원과 저장 변환을 담당한다. 정신력은 레벨 기본값 + 지혜 투자×4다. 기술 비용은 지혜를 제외한 기본값, 호흡 회복은 실제 최대값을 사용한다. 레벨 상승은 최대치 증가분을 현재 값에 더하고 특성 투자·재훈련은 무료 회복 없이 clamp한다.

`world/recovery.py`는 DB 없는 공통 계산 계층이다. profile.recovery의 updated_at/boundary는 고정 Unix 시각의 10초 경계를 추적한다. ready는 마지막 경계 이전의 미지급 기여, credit은 경계 이후 시간의 기여다. accrue는 소수 기여만 더하며 자원을 지급하지 않고, commit은 ready의 정수 부분만 지급한다. 소수와 마지막 10초 미만 구간은 보존하며 full 자원의 두 bucket은 버려 미래 피해를 미리 회복하지 못하게 한다.

| source | HP/분 | 정신력/분 | 전투 중 |
| --- | --- | --- | --- |
| 기본 | 2 + max_hp/60 | 4 + max_mental/20 | HP 제외, 정신력 유지 |
| Room.recovery | hp_per_minute | mental_per_minute | 둘 다 제외 |
| 장착 ItemEntity recovery modifier | hp_per_minute | mental_per_minute | 둘 다 유지 |
| recovery_effects | hp_per_minute | mental_per_minute | 둘 다 유지 |

Room/Item metadata는 누락 시 0이며 integrity가 유한한 0 이상의 수만 허용한다. 초기 장소는 의무실 6/2, 본부 중앙홀 2/2, 폐쇄된 관리동 2/1, 옥상 9개 Room 0/2다. 출정 대기실에는 보너스가 없다. 장비 회복은 native equipment snapshot의 장착 modifier를 집계한다. 생존모듈·재생모듈·정신안정모듈 등 실제 회복 장비가 존재한다. recovery_effects는 started_at/expires_at와 선택 회복률을 저장하며 시작·만료 시각으로 구간을 나눈다. 만료 시각까지의 기여를 반영한 뒤 expired effect를 제거한다. 활성 조건은 started_at <= now < expires_at이며 미래 효과만 필요하면 그 시작 시점 하나를 예약한다. 새 소비품·범용 buff API는 없다.

Explorer.change와 전투의 직접 저장 경계는 변경 전 accrue를 수행한다. 공통 이동 hook의 checkpoint_recovery는 이전 Room의 기여만 저장하고 state/prompt를 보내지 않는다. Exit·귀환·승강기·패배 이동이 같은 규칙을 쓴다. move_to의 world_change는 목적지 hook 거절도 실패로 rollback하고, 도착 state와 방 출력은 성공 후 실행한다. world_change의 profile/location rollback을 유지한다. 현재 자원은 주기 commit 또는 기존 명시적 회복/피해에서만 바뀐다. 접속 중 실제 회복할 자원이 있을 때 다음 경계 하나만 예약하며 full 또는 전투 중 HP만 부족하고 bonus가 없으면 예약하지 않는다.

마지막 unpuppet에서 전투를 끝내고 경과를 checkpoint한다. Evennia 6.1은 location을 비우고 db.prelogout_location에 옛 Room을 남기므로 offline batch는 그 Room을 사용한다. 새 puppet은 offline의 경계 통과분을 지급한 뒤 staging_room으로 이동한다. 살아 있는 session의 at_sync는 위치를 유지하고 restart reconcile은 접속자만 회복 저장·재예약한다. offline 캐릭터마다 timer를 만들거나 restart에서 모든 profile을 회복 저장하지 않는다.

적은 같은 credit/commit 계산을 사용하되 HP만 회복한다. 교전 종료의 15초 유예, alive·비교전·0<HP<max 조건과 `8+max_hp/15`를 적용한다. 빈 방은 접근 때 batch 계산하고 관찰 중만 다음 경계를 예약한다. 재교전 구간은 기여 0으로 시간만 진행하고 앞 소수 기여는 보존한다. 위협·점유·차례 정리는 회복과 분리되며 사망/45초 respawn은 기존 정책을 유지한다.

## 프롬프트 출력 lifecycle

`world.text.resource_prompt`는 `[ 60/60 · 40/40 ] >`의 내용과 현재 숫자 색을 소유한다. 67% 이상 success·34% 이상 warning·양수 error·0 critical이며 최대치·구두점은 기본색이다. prompt는 자원 요약과 한 입력 처리가 끝났다는 표식이다. Explorer meter는 최신 HUD이고 prompt는 출력의 시간 순서/스크롤 기록이다.

save_profile은 저장·Web state·회복 예약만 맡고 prompt를 출력하지 않는다. parser는 선택된 command의 사본에 `commands/prompt.py`의 pre/post lifecycle만 연결한다. func·locks·dispatch와 progressive generator 처리는 그대로이며 Evennia 6.1이 generator 완료 때 호출하는 실제 at_post_cmd를 사용한다. 일반/실패/Exit/관리 명령과 묶음·개인 줄임말은 중첩 context를 공유해 모든 결과 뒤 최종 prompt 하나를 출력한다. 시스템 no-match/no-input/multimatch도 동일 완료 경계를 사용한다. 사용자 명령 시작 때 이미 지난 회복 경계만 정산하고 회복 prompt는 명령 완료에 합친다.

출력 context는 시작한 Explorer를 별도로 보관한다. MuxAccountCommand의 parse가 caller를 Account로 바꾸는 접속자·종료 명령도 같은 Explorer의 context를 종료한다. 마지막 unpuppet에서는 중단된 입력 대기의 context와 예약 prompt를 정리해 재로그인 후 출력이 막히지 않게 한다.

빈·공백 Enter는 서버에서 공식 no-input command로 처리한다. get_input 임시 CmdSet에 답변으로 보내거나 최근 명령·Web history에 넣지 않는다. 이미 지난 경계만 반영하므로 연타로 회복이 빨라지지 않는다. 아직 경계를 넘지 않은 조회/실패 입력은 저장 시계를 불필요하게 쓰지 않는다.

자동 전투 라운드·공격·레벨업 저장과 일반 비동기 알림은 prompt를 만들지 않는다. 입력 없는 recovery commit이 실제 HP/정신력 정수값을 바꿀 때만 prompt를 요청한다. fraction·재예약·full/no-change는 출력하지 않는다. 요청은 reactor의 다음 turn으로 합쳐 같은 구간의 전투 메시지 뒤에 출력하고, 중간에 사용자 명령이 시작되면 그 완료 prompt로 합친다. 패배는 공격/구조/손실·전투 종료·의무실 방 출력을 완료한 뒤 최종 HP 1의 prompt를 요청한다. 로그인도 offline 정산·위치·방/환영 출력을 끝낸 뒤 한 번 출력하며 logout/shutdown은 출력하지 않는다. sync/restart의 내부 state 갱신만으로 prompt를 중복 생성하지 않는다.

Telnet은 정상 prompt channel, Web은 pz_log의 kind=prompt와 semantic segments로 같은 formatter를 전송한다. Web의 고정 prompt DOM/CSS는 제거했다. prompt는 메인 로그에 일반 폰트·왼쪽 정렬·작은 간격으로 남고 기존 near-bottom 자동 scroll/위로 읽는 scroll-lock 및 400개 보관 한도를 따른다. 문자열/ANSI 재파싱으로 색이나 명령을 계산하지 않는다. Web max_mental과 HP/정신력/XP meter 갱신은 유지한다.

Web command echo는 별도 `› 명령` entry가 아니다. 마지막 entry가 대기 prompt이면 command semantic을 오른쪽에 붙여 `[ 60/60 · 40/40 ] > 상태` 입력 행으로 완료한다. 서버의 다음 prompt는 새 대기 행이다. 비동기 메시지 또는 이미 완료한 입력 행이 마지막이면 과거 prompt를 검색/수정하지 않고 로그 끝에 새 입력 행을 만든다. 이는 Telnet local echo와 같은 시각적 모델이며 blank는 어떤 command span도 붙이지 않는다.

`pz_state.resource_prompt`는 `{kind: "prompt", segments: ...}`의 입력 echo용 metadata다. 현재 profile과 stats로 서버 resource_prompt formatter에서 생성하며 state 수신 자체는 로그나 고정 UI를 렌더링하지 않는다. client의 latestPrompt는 이 서버 metadata와 새 semantic prompt에서 갱신한다. 자동 피해로 currentServerPrompt가 바뀌어도 lastRenderedPrompt는 그대로일 수 있다. 이때 입력 행은 WebSocket FIFO에서 마지막으로 수신한 서버 값을 사용하며 별도 echo ACK/round-trip은 없다. 제출 직전 미수신 상태의 작은 race는 다음 authoritative 결과 prompt로 정상화된다.

직접 입력·버튼·채팅·계정 명령은 공통 command 경로에서 같은 행을 만들고 성공 전송한 non-empty 명령만 history에 넣는다. 입력 제출은 bottom으로 이동하고 비동기 출력은 scroll-lock을 유지한다. 60초 keepalive는 send만 하고 echo/history를 만들지 않으며 Evennia inputfunc가 idle을 dispatch 전에 소비한다. progressive의 최초 입력과 non-empty 추가 응답도 같은 입력 행 표현을 사용하지만 get_input/완료 hook은 바꾸지 않는다. 회귀는 Node 표준 모듈의 `scripts/tests/test_web_prompt.cjs`가 실제 primal.js의 DOM/WS 경계를 실행하고 `tests.test_web_prompt`가 전체 Python suite에서 연결한다. Node.js가 없는 환경은 명시적으로 skip한다.

## 보급칩 경제와 전리품 자산

`world/content/economy.py`의 CURRENCY는 id=credits·이름=보급칩·단위=칩·별칭·설명의 SSOT다. `world/currency.py`의 format_currency는 127칩을 만들며 profile의 credits 숫자를 유지한다. 최신 profile version은 10이다. 화폐는 ITEMS나 inventory에 넣지 않는다. Web은 서버의 currency metadata/formatted/전리품 display_label과 take_command를 표시한다. take_target은 칩/칩 2 같은 명령 선택자, display_label은 8칩 같은 표시 문자열이며 화면 문자열을 재해석해 명령을 만들지 않는다.

`world.loot_service`가 모델을 backend-neutral snapshot으로 제공한다. ItemEntity root와 LootClaim, CurrencyLoot/Share가 authoritative하며 legacy normalize_entry는 migration·historical 호환용이다. snapshot.as_entry의 eligible_players/remaining_shares는 share rows에서 파생한 pure 계산 입력이며 CurrencyLoot에 중복 저장하지 않는다. 조회는 DB를 변경하지 않는다.

`rules.reward_allocation(amount, groups)`는 그룹 기여도 비례 → 파티 내부 균등 → deterministic 최대 나머지법으로 총량을 보존한다. XP는 즉시 지급하고 보급칩은 그룹별 CurrencyLoot로 생성한다. Share=0 행도 원래 eligibility를 유지한다. 부분 지급은 양수 remaining 몫만 weight로 쓰며 quantity·shares·offline 포함 모든 recipient credits가 같은 transaction에 저장된다. Missing recipient는 전체 rollback이다. 만료 후 잔액은 caller에게 지급하고 decay는 owner만 바꾸며 share·reservation·deadline을 보존한다.

currency_request는 기존 TargetSelector에서 금액만 읽는다. 20칩은 양의 정수 금액, 칩 2는 공통 INDEX, 칩 모두는 ALL이다. source/관계 parsing은 기존 helper를 사용하고 여러 시체에는 ALL target을 요구한다. 기본 화폐 대상은 접근 가능한 entry에서 선택하며 기존 item 선택 정책은 바꾸지 않는다. player 간 전달·버리기와 전리품 회수는 world_change 안에서 관련 profile/loot를 함께 변경하고 실패 시 rollback한다. 임무·정산·NPC 판매는 직접 source, 구매·학습·패배는 sink이며 패배 손실은 드롭하지 않는다.

`SHOP_CATALOGS`는 purchase_catalog/accepts를 분리한다. 가격은 value와 explicit purchase_unit_value/resale_unit_value, 탄약 bundle의 purchase_quantity로 결정한다. 일반 resale은 floor(value/2), explicit resale은 우선한다. 탄창은 empty resale + 잔탄×ammo resale, 총기는 full_standard package로 구매한다. Stack 판매는 1/N개/모두, non-stack은 stable instance selector를 사용한다. field-only/T2 장비도 category/policy/가격이 맞으면 기본점에서 매입한다. [최종 가격·catalog](final-content.md)를 따른다.

## 목표와 구성

사냥·장비 수집·성장을 중심으로 하는 한국어 웹 MUD다. 모든 주요 임무는 혼자 완료할 수 있으며 파티는 선택 사항이다. Python 3.13 / Evennia 6.1.0 / SQLite / HTML·CSS·JavaScript를 사용하고 정확한 버전은 uv.lock으로 고정한다.

| 구성 | 책임 |
| --- | --- |
| world/content/ | 지역별 장소·적 정의와 공통 아이템·가격, Region 결합·무결성 검사 |
| world/quests.py | 임무별 진행 필드·표시 단계·안내 정의 |
| world/rules.py / progression.py | DB나 Evennia에 의존하지 않는 규칙 / 특성·기술 정의 |
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

<a id="본부-room-구조-1단계"></a>

## 현재 본부 Room 구조

`world/content/headquarters.py`는 출정 대기실·본부 중앙홀, 지원동 1~3층 복도와 시설·공용 승강기, 옥상 9곳과 전초·예약 시설을 포함해 Room 41개를 정의한다. 기존 `dock`과 탐사 구역 15곳은 유지한다. Region `headquarters`는 방문한 실제 Room을 기존 지도에 묶어 표시한다.

출정 대기실의 유일한 출구는 `남 → hq_concourse`다. 중앙홀은 `북 → staging_room`, `서 → dock`, `남 → support_1f_c`이며 부두의 `북 → grass`는 그대로다. 1층 중앙은 `북 → hq_concourse`, `서 → support_1f_w1`, `동 → support_1f_e1`이며 남쪽 출입구는 폐쇄되어 있다. 모든 정식 방향 출구는 반대 방향으로 복귀하며 별도 복귀 방향 예외는 없다. 각 층의 복도는 동서로 연결되고 기존 시설은 북쪽, 새 2층 훈련 시설 세 곳은 남쪽으로 진입하며 반대 방향으로 복귀한다. 층별 방향 그래프는 분리되어 있으며 2단계 승강기 명령으로 각 중앙 복도와 옥상을 오간다.

`blocked_exits`는 방향과 폐쇄 안내 문구만 저장하며 목적지·Exit 객체를 만들지 않는다. `world.navigation.blocked_exit_message()`가 기존 방향 alias로 조회하고, 미등록 명령 fallback에서 이동 입력을 처리한다. 보기 역시 목적지 조회 전에 같은 안내를 반환한다. 기존 관리 Exit가 폐쇄 방향에 남아 있으면 Exit 훅에서 이동·정찰을 차단하고 bootstrap이 해당 stable tag의 관리 Exit만 제거한다. 일반 stale 객체 감사 정책은 유지한다.

Room의 local/distant 표시 경로는 정적 설명 다음에 폐쇄 문구를 넣는다. 지도는 방문한 실제 Room의 방향 목록에 폐쇄 방향을 표시하며 1층 중앙은 `북: 본부 중앙홀`, `남: 폐쇄`다. 방향도·웹 이동 버튼·`pz_state.exits`는 실제 출구만 사용하며 1층 중앙은 북·동·서만 제공한다. 폐쇄 방향을 지도 노드나 동작 버튼으로 만들지 않는다. 기능 없는 시설에는 NPC·보관함·가짜 action hint를 추가하지 않는다.

## 8방향과 고정 compass

`world/content/directions.py`의 `DIRECTIONS`가 canonical 한국어 방향, 영문 alias, opposite, 3×3 좌표를 소유한다. `DIRECTION_ORDER`는 북부터 시계방향인 북·북동·동·남동·남·남서·서·북서다. alias/reverse mapping은 같은 정의에서 파생하며 `items.py`는 방향을 소유하지 않는다. 기존 `world.content.OPPOSITES` import는 `DIRECTION_ALIASES`와 동일한 객체를 export하는 호환 경로만 유지한다. bootstrap의 실제 Evennia Exit alias, blocked 방향 조회, integrity, 지도·Web 출구 순서와 개인 줄임말 예약 이름이 이 정의를 사용한다. 별도 대각선 command는 없다. 방향 보기의 selector·gate·원거리 지각 정책과 묶음 dispatch는 기존 경로다.

옥상 중앙 `support_roof`는 `support_roof_n/ne/e/se/s/sw/w/nw`로 나가는 여덟 Exit를 갖는다. `ROOF_SIDES`의 stable Room ID는 사용자 입력용 방향 alias에서 파생하지 않고 명시적으로 고정한다. 각 주변 Room의 유일한 Exit는 정확한 opposite로 중앙에 돌아오며 서로 연결하지 않는다. 옥상 9개 Room은 headquarters·safe·적 없음·outdoor/natural인 navigation/UI 회귀 기준 공간이다. `headquarters_errors()`는 비어 있지 않은 `hints`·`requires`·`quest`·`items`·`rewards`를 금지하고, 전체 `errors(interactables)`는 중앙과 주변 모두의 NPC/interactable/service 배치를 금지한다. 환경·시설 조명 등 다른 schema 필드를 일반적으로 금지하지 않는다. 승강기의 옥상 정류장은 여전히 중앙 하나이며 `support_elevator.exits={}`와 일반 Exit의 승강기 직접 연결 금지는 유지한다. integrity와 반복 bootstrap/실제 이동 검사가 이를 검증한다.

지도는 실제 출구와 폐쇄 출구의 방향을 먼저 합쳐 `ordered_directions()`로 한 번 정렬한다. 한 Room의 전체 표시가 canonical 시계방향 순서를 따르며 기타 특수 출구는 원래 입력 순서대로 뒤에 표시한다. 방문한 목적지 이름·미탐사·폐쇄·현재 위치와 semantic 방향 token은 유지한다.

Web은 기존 `pz_state.exits`만 렌더링한다. 오른쪽 DOM은 SURROUNDINGS → PARTY → OBJECTIVE → TRAINING → EQUIPMENT & SUPPLIES이며 SURROUNDINGS 안에서는 compass → hint/context 순이다. 고정 3×3 grid의 중앙은 row 2/column 2이며 출구가 없는 방향은 버튼만 생략한다. 출구 개수와 주변 행동 수가 grid geometry와 panel 내 위치를 바꾸지 않는다. connector/has-direction 가변 행은 제거했고 기타 특수 출구 fallback은 유지한다. 기존 1150px grid·700px flex breakpoint를 따르며 서비스/action 선정 정책과 서버가 소유하는 텍스트 명령은 바꾸지 않는다.

Telnet `exit_diagram()`은 30 display cells × 5줄의 canvas를 사용한다. `[현재]`는 0 기준 12열, 북/남 label과 fullwidth `｜`는 14열에서 시작한다. 없는 방향의 label/connector는 공백이며 대각선에는 `／`·`＼`, 가로축에는 ASCII `-`를 사용한다. 방향 semantic token을 배치한 뒤 terminal 색 변환을 적용한다. `world.text.display_width()`는 기존 east_asian_width W/F=2 정책을 `row()`와 공유하며 ANSI escape 길이를 계산하지 않는다. 실제 terminal/font의 fullwidth glyph 지원은 별도 클라이언트 조건이다.

새 캐릭터는 기존 최초 puppet의 비월드 위치 fallback에서 출정 대기실로 배치되고 새 profile의 `visited`도 대기실에서 시작한다. 새 로그인/재로그인은 출정 대기실에 배치하고 방문을 포함한 진행 기록은 보존한다. 살아 있는 세션의 server reload는 기존 위치를 유지한다. Evennia fallback `home=dock`은 유지한다. 일반 귀환은 `support_roof`, 전투 패배는 `infirmary`로 명시적으로 이동한다. 상점은 지원동의 실제 Shopkeeper, 의료·휴식은 의무실의 실제 객체를 따른다. 보관·훈련 객체는 아래 3단계 배치를 따른다. bootstrap은 기존 stable tag로 Room/실제 Exit를 재사용·갱신하며 개인 기록을 초기화하지 않는다. 이전 본부 배치의 중앙홀 동쪽·1층 중앙 남쪽 관리 Exit는 같은 목적지를 유지하며 새 남쪽·북쪽 stable tag와 alias로 갱신한다. 이미 새 출구가 있다면 해당 옛 관리 Exit만 제거한다. integrity는 목적지·정반대 방향의 양방향 연결·폐쇄 문구/충돌·본부 고정 배치·시설의 유일 진입·Region membership을 검사한다.

## 본부 2단계: 공용 승강기

`support_elevator`는 safe·실내·인공광·적 없음의 실제 `ZoneRoom`이다. `exits={}`이며 승강기 호출/하차를 cardinal Exit로 만들지 않는다. 기존 중앙 복도의 폐쇄 방향도 유지한다. `world/content/elevator.py`의 `ELEVATOR_STOPS`가 안정적인 정류 층 ID(`1f`, `2f`, `3f`, `roof`)와 한국어 label·목적지 Room의 SSOT다. Command·표시·웹 상태·bootstrap·검사는 이를 재사용한다.

공용 현재 층은 승강기 Room의 persistent `db.current_stop`에 저장하며 개인 profile에는 넣지 않는다. 초기값은 `ELEVATOR_DEFAULT_STOP`이고 bootstrap은 새 Room 또는 유효하지 않은 값만 정규화한다. 정상 층은 월드 재구성·reload/restart 뒤에도 보존한다. 기존 Room·Exit stable ID와 본부 출구 migration은 유지한다.

`ZoneRoom.at_cmdset_get()`은 각 중앙 복도/옥상에 호출용 CmdSet, 승강기 내부에 층 선택/하차용 CmdSet을 제공한다. `승강기`는 호출과 탑승을 한 번에 수행한다. `1층`·`2층`·`3층`·`옥상`은 공용 층을 바꾸고 선택자만 자동 하차한다. 다른 승객은 승강기 Room에 남아 `내려`로 현재 층에 내린다. 외부 호출은 기존 승객을 승강기에 둔 채 공용 층을 호출자의 층으로 바꾼다. 같은 층 재선택도 선택자를 하차시키며 층 attribute는 다시 저장하지 않는다. 밖에서는 내부 명령이 CmdSet에 없으므로 일반 unknown-command 처리를 따른다. 전역 명령 registry에는 내부 층 명령을 추가하지 않는다. 이동 분류 도움말은 정류장 SSOT에서 해당 조작을 안내한다.

`world.elevator`는 기존 `world_change()`의 단일 서버 잠금·DB transaction으로 동작을 직렬화한다. 탑승·하차는 실제 `move_to()`로 관찰·presence·visited 훅을 재사용하고 실패하면 공용 층 변경도 rollback한다. 승객 이동 알림은 `after_change()`로 성공 뒤 전달하고 기존 GameCommand의 접속자 state push로 함께 갱신한다. 실제 대기 시간·비동기 작업·문 상태 머신은 없다.

Room 본문은 기존 `world.text` semantic 조각으로 호출 방법 또는 현재 층·가능한 명령을 표시한다. `pz_state.elevator`는 서버가 결정한 `inside`, 내부의 `current_stop/current_floor`, `actions[{label, command}]`를 제공하며 이용 불가능한 곳에서는 null이다. 클라이언트는 이 값을 주변 행동에 렌더링하고 같은 텍스트 명령을 보낸다. zone ID 분기나 별도 웹 이동 API는 없다. 지도는 방문한 승강기·상층·옥상을 기존 Room 목록에 표시하며 가짜 방향 연결을 추가하지 않는다. 순수 검사는 cardinal graph와 stop을 포함한 transport reachability를 따로 확인한다.

Integrity는 승강기 Room·headquarters 소속, default·정류 층 ID/label/목적지의 유효성·중복, 정확히 세 중앙 복도와 옥상인 정류 구성, 가짜 방향 출구 금지와 기존 HQ reverse/blocked 검증을 함께 수행한다. 귀환은 옥상에 도착한 뒤 이 승강기로 이동한다. 의료·패배 흐름은 아래 4단계를 따르며 회수 자원 정산은 아래 5단계, NPC 상점은 6단계를 따른다.

## 본부 3단계: 보관·훈련 서비스 이전

`INTERACTABLES`의 기존 `shared_container`와 `personal_locker`는 `storage_room`에 배치한다. stable ID `instructor`는 기존 객체를 훈련관리관(`TrainingManager`)으로 갱신해 `training_office`로 이동한다. 의무실·훈련실의 기존 출입문을 유지하고 2층 서쪽 끝·중앙·동쪽 끝의 남쪽 문에 전술훈련실·훈련관리실·사격장을 추가한다. Room은 환경·출구만 담당하고 훈련은 실제 교관이 제공한다. 부두에는 윤대장과 탐사 출발 동선이 남는다.

서비스는 Room 이름이 아니라 실제 world object를 따른다. 보관 명령은 기존 `room_objects`와 Container 대상 선택·가시성·이전 규칙을 사용한다. 성장 명령은 같은 객체 풀에서 담당 SkillTrainer/AttributeTrainer/TrainingManager를 찾고 action을 위임한다. 교관은 현재 방의 safe 속성·비전투·Observation/view 정책과 담당 ID를 검증한다. Web `training_controls`도 같은 provider와 서버 생성 명령에서 파생되며 클라이언트가 시설 Room ID로 활성 여부를 판단하지 않는다. 원거리 표시는 존재만 보여 주고 contents·개인 보관·훈련 행동과 성장 상태를 노출하지 않는다.

bootstrap은 stable `primal_interactable` tag로 기존 객체를 찾아 DB ID를 유지한 채 위치·이름·alias 목록을 갱신한다. 다중 alias도 목록으로 전달해 각 이름을 보존한다. 공용 `db.items`와 각 탐사자의 `profile.storage`, 장비·성장·방문 기록에는 쓰지 않으며 profile migration도 없다. 반복 실행은 객체를 중복 생성하지 않는다. integrity는 세 서비스의 본부 배치를 검사하며 실제 사용 권한은 이 정적 배치 검사와 독립적이다.

## 본부 4단계: 의료와 복귀·패배

신규 시작은 `staging_room`, 재접속은 출정 대기실, Evennia fallback `home`은 `dock`이다. `Return`은 비전투 중 `support_roof`로 실제 이동하고, 패배는 home과 무관하게 `infirmary`를 조회한다. 옥상과 의무실 이후 이동은 기존 공용 승강기·사방 출구를 사용한다.

`Doctor(ActionObject)`의 stable ID는 `doctor`(의무관/의사), `Bed(ActionObject)`는 `infirmary_bed`(침대/병상)이며 `INTERACTABLES`에서 의무실에 배치한다. bootstrap은 기존 stable tag 기반으로 하나씩 생성·재사용하며 Room·Exit·개인 기록과 기존 서비스 객체를 보존한다. Room 정적 설명은 환경만 담고 객체 presence가 실제 존재를 표현한다. integrity는 의료 배치와 행동 정의를 검사한다.

`진료`/`의무관 진료`/`의무관에게 진료`와 `휴식`/`침대 휴식`/`침대에서 휴식`은 현재 `room_objects`의 보이는 Doctor/Bed를 공통 selector로 선택한다. bare 입력은 0개면 대상 없음, 1개면 자동 선택, 2개 이상이면 명시적 지정 요구다. 숨은 대상은 개수·오류·selector·hint·Web에 포함하지 않는다. 발견 이후 `perform_action`이 같은 Room·관찰·비전투를 검사하고 각 pure rule이 현재 Room의 safe를 검사한다. 실제 객체를 다른 안전 Room으로 옮겨도 서비스는 객체를 따른다. 전투 중 보이는 대상은 대상 없음 대신 기존 RuleError로 거절한다.

`rules.treat`와 `rules.rest`는 별도 public rule이며 무료·즉시 회복이다. 진료는 HP만 full로 만들고 HP가 가득하면 거절한다. 휴식은 HP와 mental을 모두 full로 만들며 둘 다 가득할 때만 거절한다. 붕대 `rules.use_bandage`·플레이어 치료와 독립이며 아이템·보급칩·기술 Rank를 변경하지 않는다. 침대 점유·예약·시간 지연은 없다. 가득 찬 자원의 recovery credit은 제거한다.

`enemy_attack`은 피해·defeated 판정만 반환한다. `apply_defeat`가 `lost=min(credits,10)`을 차감하고 `DEFEAT_RECOVERY_HP=1`로 최소 생존 상태를 설정한다. 일반 의료 rule/객체는 호출하지 않는다. Enemy lifecycle은 하나의 `world_change` 안에서 피해·패널티·저장·`leave_combat`·의무실 이동을 처리한다. 패배자만 combatants/threat/contribution과 queued action·간파·타이머를 정리하고 다른 참가자는 유지한다. 이동 False/실패는 예외로 rollback하며 DB profile·FK와 Evennia attribute/location/contents 캐시를 복구한다. 타이머 취소와 구조 안내는 `after_change`로 commit 뒤 실행한다. 기존 `save_profile`의 deferred push가 새 의무실 상태를 패배자에게 보내므로 적 Room의 broadcast에만 의존하지 않는다. visited는 실제 이동 hook으로 의무실 방문을 추가하며 나머지 진행 기록은 보존한다. 출력 문구로 lifecycle을 판정하지 않는다.

서버 interactable allowlist에는 의료 `진료`/`휴식`만 추가한다. 같은 객체의 visible/safe/noncombat availability로 Web action과 target/action Room hint를 결정한다. 클라이언트는 서버 명령을 렌더링할 뿐 infirmary zone 특례가 없다. 부두의 휴식 버튼·hint는 제거했으며 현재는 6단계에서 상점 특례도 제거됐다. 원거리 관찰은 의료 서비스 행동을 노출하지 않는다.

의료 동선과 회복 규칙은 통합/수동 검사와 Full의 실제 패배→의무실→Bed 회복 및 Doctor 진료로 확인한다. Quick smoke는 fixture 로그인과 공동 사냥 1회, 귀환→옥상→승강기 3층→무기상 구매·재접속을 확인한다. 공개 가입 rate limit은 그대로 유지하며 gameplay smoke와 분리한다. 시체/재생성/보호의 production 시간 의미는 Full Gameplay E2E가 맡는다.

## 본부 5단계: 단일 화폐와 회수 자원 정산

보급칩은 유일한 구매 currency, scrap은 일반 경제 resource다. Native inventory/storage의 ItemEntity 수량을 사용하며 `SALVAGE_CREDIT_RATE=10`으로 정산한다. 발전기는 별도 submit-only `generator_repair_part` 3개를 소비하므로 일반 scrap을 잃어 진행이 막히지 않는다. 수송차 cache는 미수리 상태에서만 부족분을 보충하고 수리 완료 후 지급하지 않는다.

실제 persistent `SettlementOfficer`의 stable ID는 `salvage_officer`, 표시명은 자원 정산관, alias는 정산관이며 `salvage_office`에 배치한다. 기존 bootstrap의 stable tag 재사용으로 객체 ID·alias·정상 배치를 유지하고 다른 객체·개인 profile·shared inventory를 초기화하지 않는다. integrity는 위치·환율/교환 action 정의·양의 정수 정산율과 기존 본부 구조를 검사한다.

`환율`과 `교환`은 보이는 current-room SettlementOfficer에 위임한다. discovery는 기존 `room_objects`/names/parse_selector/resolve를 사용하며 bare는 0명 거절, 1명 자동 선택, 여러 명 대상 지정 요구다. targeted 입력은 `정산관에게 회수부품 10개 교환`처럼 공통 `에게` relation과 이름/번호를 사용한다. hidden/view lock은 개수·selector·hint·Web에서 제외한다. 이용은 실제 같은 Room·can_perceive·현재 Room safe·비전투 조건이며 특정 Room ID가 권한을 부여하지 않는다. 전투 중 보이는 NPC는 기존 전투 오류를 반환한다.

`world/settlement.py`는 정산 resource와 1/N개/모두 수량만 해석한다. 일반 소지품/보관/전리품 parser의 수량 범위를 확장하지 않는다. `rules.settle_salvage(profile, quantity)`는 비전투·양의 정수·소지품 보유량을 전부 검증한 뒤 consume과 credits 증가를 수행하고 획득액을 반환한다. 객체가 `caller.change()` 경계 안의 최신 profile에서 모두 수량을 구하므로 실패 시 부분 저장이 없다. 0개 inventory entry는 consume이 제거한다. 저장한 부품·임무용 부품·성장 등은 정산 대상 소지품 수량 이외에 변경하지 않는다.

서버는 실제 visible/available NPC에서 환율 명령과 보유 scrap이 있을 때 대상 지정 모두 정산 명령을 만든다. 기존 interactable actions를 재사용하고 전체 ActionObject action을 개방하지 않는다. Room hint도 실제 target/action의 availability를 따른다. `pz_state.resources.scrap={name,count}`는 같은 profile snapshot의 소지품에서 파생하고 보급칩 wallet과 구분한다. 별도 balance를 저장하지 않으며 client는 payload와 완성된 command를 렌더링한다. zone ID·NPC 이름·환율·수량으로 action을 추론하지 않는다.

## 본부 6단계: NPC 기반 상점

`Shopkeeper(ActionObject)`는 실제 persistent NPC다. `supply_shopkeeper`(보급관/보급상인)는 `supply_shop`, `weapon_shopkeeper`(무기상/무기 상인)는 `weapon_shop`, `armor_shopkeeper`(방어구상/방어구 상인)는 `armor_shop`에 배치한다. `db.shop_id`의 supply/weapon/armor가 catalog identity이며 Room ID나 NPC 이름에서 추론하지 않는다. bootstrap은 stable tag로 같은 객체를 재사용하고 정의의 위치·alias·shop_id를 정규화한다. 재고 상태·profile migration은 없다.

`world/content/shops.py`는 5개 상점의 purchase_catalog/accepts를 소유한다. `shop_service`가 같은 방·시야·safe·비전투·잔액·policy를 검증하고 credits와 native ItemEntity를 원자적으로 변경한다. 무한 재고 source/sink이며 탄약 구매는 purchase_quantity bundle, 총기는 full_standard package다. 상품별 quest/credential 조건은 없고 공간 access가 progression을 결정한다.

`상품`(별칭 없음)과 `구매`는 현재 `room_objects`의 실제 보이는 Shopkeeper를 찾는다. 메뉴의 bare 후보는 모든 판매자, 구매의 bare 후보는 그 물건을 파는 판매자만이다. 0명 거절·1명 선택·여럿 대상 지정 요구이며 targeted 구매는 `무기상에게 절단마체테 구매`처럼 기존 parse_relation/names/selector/resolve를 사용한다. 번호는 기존 공통 정렬의 임시 번호다. 발견 후 같은 Room·safe·비전투를 검사하며 숨은 판매자는 selector·개수·오류·hint·Web에서 제외한다. 서비스는 실제 NPC를 따라 다른 safe Room에서도 동작한다.

메뉴는 실제 NPC 제목과 그 catalog의 보급칩 가격만 표시하고 상세 보기는 메뉴/targeted 구매 사용법을 안내한다. 각 시설 hint는 actual stable NPC와 상품 action을 참조하며 availability를 확인한다. 부두의 static 상점 hint·Shop/Buy gate·Web 상점 버튼을 제거했다. 다른 사용처가 없는 `GameCommand.at_dock()`과 global SHOP도 제거했다.

모든 `ActionObject`가 `web_actions(caller, target, observed_at)` capability를 제공한다. 기본 allowlist는 대화/조사/수리/보기와 available 의료 행동을 보존한다. Container는 보기만, 성장 교관은 담당 분야의 배워·배분 또는 재훈련 action을 제공하며 TRAINING UI도 같은 명령을 사용한다. SettlementOfficer와 Shopkeeper는 필요한 동적 action을 override한다. `world.state`는 subclass를 구분하지 않고 capability만 호출한다. Shopkeeper는 available일 때 상품과 catalog별 targeted 구매·가치·비착용 물품 판매의 완성된 label/command를 서버에서 만든다. client는 기존 렌더링을 사용하며 Room·가격·이름으로 구매를 추론하지 않는다.

Integrity는 세 판매자 배치·catalog ID/행동, catalog 비어 있지 않음·상품 존재·양의 정수 가격·중복 금지·기존 14개 합집합을 검사한다. smoke의 구매는 옥상→승강기 3층→동·북 무기점에서 실제 보급칩 차감/장비 증가를 확인하고 재로그인 시 대기실 위치와 구매한 장비·보급칩의 보존을 비교한다. 7단계 closeout의 Full은 본부 전체 서비스와 두 임무/보스 최종 보고 및 실제 Portal+Server 재시작을 연결 검증한다.

## 공통 대상 선택

`world/targets.py`의 `TargetSelector`는 DEFAULT / INDEX / ALL을 표현한다. 일반 대상은 `<대상>`, `<대상> <번호>`, `<대상> 모두`로, 전리품 출처는 `시체에서`, `시체 2에서`, `모든 시체에서`로 해석한다. 출처 ALL도 내부에서는 같은 ALL이며, 한국어 조사에 맞춰 표시 문법만 다르다. 번호와 모두는 함께 사용할 수 없다. 실제 이름/alias 전체가 일치하면 숫자로 끝나는 이름을 우선하고, 이후 접미 선택자를 해석한다. 이전 prefix `전체` 문법은 지원하지 않는다.

`ordered()`의 객체 ID 오름차순을 Room 서술, SURROUNDINGS, 보기, 공격, 콘텐츠 행동, 시체 회수에서 공유한다. 번호는 방 안의 보이는 후보에 붙이는 1부터 시작하는 transient presentation index이며 DB에 저장하거나 객체 ID 자체를 노출하지 않는다. 같은 이름끼리 번호를 붙이되 `시체`는 방 전체 Corpse pool을 사용한다. 시체가 만료되면 남은 시체 번호도 다시 계산된다.

DEFAULT는 구조적으로 행동을 지원하는 첫 대상을 선택한다. INDEX는 표시 순서의 정확한 개체를 선택한다. 실제 점유·임무·한 번 보상·전리품 권한은 행동/규칙 계층이 판단하며 resolver가 가능한 다음 대상으로 자동 이동하지 않는다. 보기·가져와 허용된 물품 이전·스택 판매·소각은 각 행동의 ALL 계약을 따른다. 공격·대화·조사·수리·무장·착용·구매·학습·파티 인물 조작은 단일 대상이다. 정산의 교환은 NPC 하나를 선택하고 회수부품에는 1/N개/모두 수량을 적용한다. 스택 판매·소각도 같은 개 suffix 수량 parser를 사용한다. 전투가 시작된 뒤 공격·강타·사격·간파·견제·치료·호흡·도망는 기존 combat_target을 사용한다. 특성의 `힘 2 배분`처럼 수량을 받는 명령은 해당 명령의 인자 문법을 유지한다. 파티 초대/관리의 기존 원격 캐릭터 범위도 유지한다.

`world/target_presentation.py`는 개체 수를 자연어로 묘사하고 필요한 경우에만 `'갈퀴사냥룡 1'`, `'시체 2'` 같은 지정 방법을 문장으로 안내한다. Room 본문과 세계 서술은 객체 표가 아니다. SURROUNDINGS·버튼·상태/조작 control에서는 빠른 인식과 조작을 위해 `시체 1 · 갈퀴사냥룡의 시체` 같은 compact label·번호·상태를 사용할 수 있다. `world/state.py`가 label/command를 생성하고 웹은 그대로 텍스트 명령을 전송하므로 클라이언트에 선택 parser를 복제하지 않는다.

`world.state.loot_controls()`는 웹 상태와 Corpse/DroppedLoot 상세 보기의 지정명·회수 명령을 함께 생성한다. 시체는 현재 보이는 방 전체 Corpse pool, 바닥 물건은 같은 아이템의 객체/entry 순서를 기존 helper로 계산한다. 상세 보기에는 단독으로 실행할 수 없는 `가져` 대신 `시체 2에서 모두 가져`, `회수부품 2 가져` 같은 명령을 안내한다. 시체가 하나면 번호를 생략하고, 빈 시체에는 회수 안내를 표시하지 않는다. 이 helper는 표시만 담당하며 번호를 저장하거나 권한·수량 규칙을 다시 구현하지 않는다. 실제 실행은 현재 방 상태에서 기존 resolver와 전리품 규칙을 사용한다.

전리품 요청은 `LootRequest(source, target)`로 정규화한다. `모두 가져`는 가상 target `전리품`의 ALL이다. source가 없으면 DroppedLoot를, DEFAULT source면 시체 하나만 처리한다. source ALL에는 target ALL이 필수다. target DEFAULT/INDEX는 선택 entry에서 한 개를, ALL은 일치하는 entry의 전체 quantity를 처리한다. entry 순서는 객체 ID와 객체 내부의 저장 entry 순서이며, 번호를 별도 저장하지 않는다. 회수 전 같은 timestamp로 lifecycle을 정리한 뒤 world_change에서 선택·수량 차감·배정자 저장을 원자적으로 처리한다. 보호된 entry는 ALL에서 건너뛰며 하나라도 지급되면 성공이다. can_take_entry가 회수 자격을, recipient_for_item이 item 순번 배정 대상을, currency_payouts가 잔여 금액 배분을 판단한다.

## 레벨·특성·기술의 세 성장축

수치와 상태 규칙은 [장기 성장 설계](progression.md)에 정리한다. `world/progression.py`의 SKILLS와 순수 helper가 SSOT이고 `world.test_progression`이 대표 값·경계를 검증한다. 장비는 기존 외부 능력치 보정이며 별도 숙련은 없다. 레벨 cap은 기본 기술의 추가 Rank 합 +1로 도출한다.

profile v10의 `attributes`는 기본 10과 추가 투자, `skills`는 여덟 Rank다. 남은 포인트·훈련은 레벨과 투자량에서 도출하며 가변 잔액을 저장하지 않는다. migration은 옛 기술을 R1로 환원하고 proficiency/guard를 제거한다. 특성은 canonical 순서로 +20·레벨 예산을 제한하고 기존 XP·장비·소지품·임무·월드 진행을 유지한다. 현재 버전의 잘못된 Rank도 저장 전에 같은 정규화를 거친다. read-only snapshot은 입력과 DB를 바꾸지 않는다.

## NPC 소유 훈련과 지원동 시설

지원동 2층에 전술훈련실(`tactics_room`, 서쪽 끝 남), 훈련관리실(`training_office`, 중앙 남), 사격장(`shooting_range`, 동쪽 끝 남)을 추가한다. 기존 의무실과 훈련실 ID는 유지하며 본부는 37 Room이다. Room에는 성장 action을 두지 않는다.

여덟 기술 교관은 공통 `SkillTrainer`와 `skill_id`, 네 특성 교관은 공통 `AttributeTrainer`와 `attribute_id`를 사용한다. 기존 managed `instructor` identity는 `TrainingManager`로 바꿔 훈련관리실에 배치한다. bootstrap은 ID·진행 기록을 보존하며 typeclass를 갱신한다. 훈련관리관은 세 무료 초기화만 제공한다.

명령은 기존 relation/selector로 명시적 NPC를 해석하고 생략 시 해당 담당 provider가 정확히 하나일 때만 위임한다. 실제 교관이 safe/same-room/visibility/비전투/예산/cap을 검증하며 `caller.change`에서 전량 적용한다. Web growth controls는 주변 실제 NPC의 action metadata를 전송할 뿐 계산을 복제하지 않는다.

## 전투 기술의 행동 기회와 영속 상태

기존 자동 공격 scheduler를 유지한다. 강타·사격·견제는 다음 공격을 바꾸며 간파·치료·호흡·붕대는 한 공격 기회를 대신한다. 자원·cooldown은 실행 차례에 다시 검증하고 성공 때만 commit한다. `skill_ready_at`은 절대시각이며 재로그인·재훈련으로 초기화하지 않는다. `heavy_ready_at`은 기존 deadline 호환성을 유지한다.

`insight`는 플레이어의 한 대상에만 귀속되고 유효한 공격 적중·사망·전투 종료·양쪽 이동에서 해제한다. 지원 행동은 소모하지 않는다. 파티 치료는 예약과 실행 양쪽에서 동일 방·파티·관찰 조건을 검증하고 단일 world_change로 양쪽을 저장한다. 대상이 바뀌거나 사라지면 무료 공격으로 바꾸지 않고 그 지원 기회를 종료한다.

견제는 공유 Enemy의 `suppressions[str(source_player_id)]`에 Rank·개별 감소율·남은 공격 횟수를 저장한다. 동일 source의 효과만 Rank 비교하며 다른 source와 공존한다. `progression.apply_suppression`이 applied/refreshed/upgraded/preserved를 반환하고 `combined_suppression`이 곱산 후 `suppression_cap`으로 최종 감소율만 제한한다. public 전투의 여러 파티·솔로 참여는 유지하며 source 수에 제한을 두지 않는다. 상한은 MAX Rank 네 효과 기준(일반56.953279%·보스32.9198049375%)이며 cap에 걸려도 모든 효과의 수명과 소비는 같다. 전투 보스 판정은 `boss` flag를 사용해 각 효과의 감소율을 한 번만 절반으로 적용하고 해당 상한을 선택한다. `boss_quest`는 임무 진행에만 사용한다. 적 attack event마다 `consume_suppressions`로 모든 효과를 한 번 소비한다. 현재 엔진은 단일 대상 확정 공격이며 향후 miss/AoE도 event 단위 helper를 호출해야 한다. telegraph는 추가 소비하지 않는다. 마지막 combatant 이탈·claim timeout·Enemy 이동·사망·respawn에서 전체 정리하며 HP 회복과 수명을 분리한다. source 없는 옛 suppression은 reconcile/bootstrap에서 제거한다. 간파와 견제는 플레이어별 절대 deadline으로10초 cooldown을 적용한다. 액티브 guard와 응급처치 기술은 사용하지 않는다.

기술 정신력 검증은 `progression.mental_cost(action, level)`의 결과를 메시지에도 사용한다. 실패 시 기술명과 실제 필요량을 안내하며 자원·cooldown·예약·대상 상태를 변경하지 않는다. 기존 검증 우선순위와 치료의 단일 transaction 경계는 유지한다.

전문 교관은 공통 SkillTrainer/AttributeTrainer와 담당 ID·presence·description·dialogue 데이터로 구성한다. object appearance는 담당 훈련과 사용법만 안내하고 현재 성장 수치·효과는 조회/도움말에 맡긴다. Web growth controls는 appearance와 별개로 실제 NPC provider에서 생성한다. TrainingManager만 재분배를 제공하며 `rules.retrain`의 scope·초기화 이후 available 총량을 받아 scope별 문장으로 안내한다. 현재 HP/정신력을 무료 복원하지 않고 cooldown도 보존한다.

## 공통 동사와 객체 action dispatch

parser는 마지막 token으로 행동만 찾는다. Command는 인자 문법·이름 검색·공통 검증을, 대상 객체는 콘텐츠별 동작을, rules는 순수 계산과 상태 변경을 담당한다. 공백을 제거한 이름 비교는 대상 검색에서 수행하며 parser가 특정 NPC나 성장 공식을 알지 않는다.

`조사/대화/수리`는 현재 방의 ActionObject에서 이름과 supports_action을 검사하고 `perform_action(caller, action, args)`로 위임한다. `배워/배분/재분배`는 해당 서비스를 제공하는 현재 방의 객체를 찾아 위임한다. 윤대장, 정비기록, 보급상자, 발전기, 훈련관은 stable tag로 bootstrap하며 반복 실행해도 중복 생성하거나 개인 기록을 초기화하지 않는다. 다른 방의 객체에 직접 행동하는 것도 거부한다.

명령은 base, character, combat, inventory, party, social, world_actions, skills로 나누고 registry.COMMANDS에서 명시적으로 등록한다. gameplay는 기존 import 호환 경로만 남긴다. 각 명령의 category/usage/summary와 실제 aliases로 `도움말`을 생성한다. command discovery나 콘텐츠별 parser 분기는 없다.

공용 단축어는 입력 전체가 정확히 `ㅂ/ㅂㄷ/ㄷ/ㄴㄷ/ㄴ/ㄴㅅ/ㅅ/ㅂㅅ/상/능/기/장/소`일 때만 각각 `북/북동/동/남동/남/남서/서/북서/상태/능력/기술/장비/소지품`으로 바꾼다. 기존 엔진 명령이 그 이름을 차지하면 엔진 명령을 우선한다. 인증·관리 명령은 기본 parser를 유지하고 작은따옴표 채팅, `내용 말`의 내용, 대상 이름 일부는 치환하지 않는다. prefix 게임 문법은 계속 거부한다.

`상태`는 전투 수치와 특성 요약, `능력`은 특성 투자, `기술`은 Rank·남은 훈련, `경험치`는 누적 XP, `장비`는 착용품, `소지품`은 전체 소지품이다. pz_state는 계산된 포인트와 성장 목록, 서버가 판단한 훈련 가능 여부를 전달한다. 웹은 profile을 직접 수정하지 않는다.

## 명령 vocabulary·글로벌 단축어·도움말

방향 정의의 shortcut에서 여덟 방향을 파생하고 정보 단축어와 합성한다. 글로벌 단축어와 개인 줄임말은 별도다. 현재 치료/힐/heal은 활성 플레이어 기술이며 붕대 사용과 분리한다. Doctor 진료(treat)는 HP, Bed 휴식(rest)은 HP·정신력을 무료로 채운다. generic item heal field는 일반 회복량 데이터이며 skill ID heal과 다른 문맥이다. profile v10에서 숙련은 제거한다.

`commands/help_pages.py`의 명시적 여섯 분류 순서·query·대표 명령과 각 command의 help-only `category`가 root/분류/detail을 구성한다. 입력할 수 없는 '8방향 이동'은 text role이다. query는 casefold → 글로벌 단축어 → 실제 command key/alias → 방향/영문 alias → category/topic 순서로 판정한다. 파티 detail이 category보다 우선하며 parser 상세는 `입력 도움말`로 분리했다. 승강기 내부 명령은 registry에 넣지 않고 이동 분류에서 현재 stop SSOT로 안내한다.

과거 v8 migration은 `skills.heal → firstaid` Rank와 `queued_action`을 보존한다. pure `commands/vocabulary.py`는 저장 정의의 실제 명령 위치만 canonical로 변환하고 새 글로벌/command/미래 예약 이름과 충돌한 개인 key를 `_개인[번호]`로 보존한다. exact 중첩 참조만 갱신하며 채팅·대상 문자열은 유지한다. 상세 계약은 [command-shortcuts.md](command-shortcuts.md)에 있다.

새 authentication 이후 `Account.puppet_object()`가 호출하는 `Explorer.at_pre_puppet()`은 `staging_room`을 배치한 뒤 기본 hook을 수행한다. Evennia 6.1의 `ServerSession.at_sync()`는 live-session reload의 `puid`를 기존 Object에 직접 연결하고 puppet hook을 호출하지 않아 위치를 보존한다. 실제 두 lifecycle 경로를 integration에서 검증한다. `home=dock`, 일반 귀환/패배 위치, profile 진행은 별개 계약으로 유지한다.

승강기 선택/수동 하차는 단일 `world_change()` 안의 `_disembark()`를 공유한다. 층과 이동 실패는 rollback하며 승강기 이동의 도착 화면은 `after_change()` 이후 전송한다. Web 버튼·NPC action·hint는 새 서버 canonical 명령을 보내며 client가 진료/상품/서비스 권한을 위치로 추론하지 않는다. asset 공통 query는 `long-term-growth`다.

## 개인 줄임말과 묶음 명령

`해`의 인자에서만 콤마를 구분자로 사용하며 일반 채팅은 바꾸지 않는다. 순수 `commands/shortcuts.py`가 정의 parsing·재귀 flatten·cycle/depth/count/size 검증·전체 삭제 fingerprint/TTL을 담당하고, `commands/command_shortcuts.py`가 관리와 기존 dispatcher의 순차 호출을 연결한다. parser는 실제 명령·lock·시스템 shortcut을 먼저 처리한 뒤 입력 전체가 개인 이름일 때만 `profile_snapshot()`으로 조회한다. 설정 등록은 `줄임말 추가 이름 정의`의 명시적인 전치형이다.

실행 전 전체 flat 목록을 확정한 뒤 각 `execute_cmd()` Deferred 완료를 기다린다. Evennia 6.1은 일반 `func`의 Deferred 반환을 기다리지 않으므로 dispatch는 `at_post_cmd`에서 수행한다. 시작 시점 merged cmdset에서 식별되는 generator/coroutine 명령은 사전 거절한다. 앞 명령이 새 CmdSet을 활성화한 뒤 등장하는 progressive command는 예측하지 않으며 현재 gameplay에는 해당 command가 없다. game command failure는 이후 실행을 막지 않는다. 전체 묶음은 transaction이 아니다. 실행 중 새로 등록된 정의는 같은 묶음에서 재확장하지 않는다.

`profile.command_shortcuts`는 캐릭터별 영구 설정이다. 과거 v8 migration의 응급처치 ID·저장 명령·예약 이름 변환 이후, 현재 v10은 제거된 행동과 새 기술 이름 충돌을 변환한다. 전체 삭제 요청과 확인은 각각 별개의 top-level 직접 입력만 허용하며 `primal_sequence_leaf` 간접 실행은 pending을 건드리기 전에 거절한다. 캐릭터 ndb의 60초 요청과 목록 fingerprint를 검증한 경우에만 한 번 저장한다. 확인 단독 입력·만료·목록 변경·로그아웃/종료 후에는 삭제하지 않는다. 콤마 segment·동적 CmdSet preflight의 한계와 향후 후보는 [개인 줄임말과 묶음 명령](command-shortcuts.md)을 따른다.

## Party의 단일 상태

Party는 위치가 없는 영속 Evennia 객체다. DB identity 하나가 파티의 고유 ID이며 leader, members, invitations, loot_mode, round_robin_cursor, created_at을 소유한다. members의 순서가 가입 순서다. Character에는 party_id 참조만 저장하며 전체 상태를 복제하지 않는다.

최대 4명, 초대는 60초간 유효하다. 초대·제외·위임·분배 모드 설정은 파티장만 가능하다. 수락할 때도 초대 유효성, 현재 소속과 정원을 재검사한다. 자신·동일/다른 파티 소속·없는 탐사자 초대는 거부한다. 중복 초대는 만료 기한을 무한 연장하지 않는다. 한 탐사자는 대기 초대 하나만 받는다.

파티장이 명시적으로 탈퇴하면 남은 가입 순서의 첫 멤버가 승계한다. 접속 종료는 파티장 변경 사유가 아니다. 마지막 멤버가 나가면 파티를 삭제한다. 교전 중 새 파티 생성·가입은 거부하며, 탈퇴·제외는 해당 탐사자의 전투 참여도 함께 정리한다. 기존 파티장의 위임은 그룹 identity를 바꾸지 않는다.

## 공유 Enemy와 두 공격 타이머

ROOMS.enemies는 spawn 정의다. 실제 적은 방의 영속 Enemy 객체다. grass:scavenger와 wreck:scavenger는 서로 다른 객체이며 현재 총 15개 spawn이 있다. bootstrap을 반복해도 기존 적의 현재 HP·사망·재생성 상태를 초기화하거나 spawn을 중복 생성하지 않는다. 최대 HP는 최신 Enemy 정의에 맞추고 현재 HP는 보존하되 새 최대치를 넘으면 그 값으로 제한한다.

Enemy가 HP/max HP, alive/respawning 상태, respawn_at, claim, claim_last_activity, combatants, contribution, threat, enemy_round, next_attack_at을 소유한다. 모든 탐사자가 같은 HP를 본다. 개인 profile에는 combat_target 참조, queued_action, next_attack_at, skill_ready_at, heavy_ready_at, insight, heal_target, player_round만 저장한다. 적 HP는 개인 profile에 없다.

각 탐사자의 공격은 자신의 타이머로 약 2.5초마다 실행된다. Enemy도 별도 타이머 하나로 약 2.5초마다 한 명을 공격한다. 탐사자 수나 공격 명령 반복에 따라 적의 반격 횟수가 증가하지 않는다. 타이머 중복 방지와 영속 next_attack_at 검사로 입력 반복이나 지연된 콜백의 추가 공격을 막는다. 밀린 차례를 한꺼번에 실행하지 않는다.

위협도는 실제 깎은 HP만큼 증가한다. 적은 같은 방·접속 중·해당 적을 공격 중인 탐사자 중 위협도가 가장 높은 사람을 선택하고 동률은 캐릭터 ID 순서로 해결한다. 강타는 7.5초 재사용 대기시간, 회복은 다음 개인 공격을 대체하며, 방어는 개인 공격을 유지하고 다음 공격 간격 동안 받는 피해를 줄인다.

보스의 예고/돌진은 공유 enemy_round를 따른다. 능선 보스는 2·5차례에 예고하고 3·6차례에 돌진하며 밀림 보스는 3·7차례에 예고하고 4·8차례에 돌진한다. 주기는 Enemy 정의의 `special_period`를 사용한다. 도망·패배·접속 종료·장소 이탈 시 전투 소속과 위협도·기여도를 정리한다. 일반 이동은 전투 중 거부하며, 강제 이동도 이동 후 정리한다. 패배 시 장비·경험치·소지품·진행은 보존하고 최대 10칩을 잃으며 의무실에서 체력 1로 의식을 되찾는다. 일반 치료·휴식은 이후 플레이어가 직접 사용한다.

## 점유와 보상 자격

일반 적의 combat_mode는 claimed다. 첫 교전 탐사자 또는 파티가 점유한다. 같은 파티는 합류할 수 있고 외부 그룹은 서버에서 거절된다. 실제 전투 행동이 점유 활동 시각을 갱신한다. 명령 반복만으로 기한을 늘리지 않는다. 그룹 전원 도망·이탈·접속 종료 시 즉시 점유를 해제하며, 활동이 15초간 없으면 남은 참여를 종료하고 해제한다.

살아 있는 적은 마지막 참가자의 교전 종료부터 15초 유예 후 `8 + max_hp/15`의 분당 회복률로 점진 회복한다. 위협도·기여도·차례 정리와 HP 회복을 분리하며 재교전은 현재 HP를 유지한다. 빈 방은 회복 tick 없이 다음 접근에서 batch 계산하고, 접속 관찰자가 있을 때만 다음 10초 경계를 하나 예약한다. 죽은 적은 회복하지 않고 기존 45초 respawn에서 최대 HP로 돌아온다. timing SSOT와 smoke의 canonical key는 ENEMY_RECOVERY_DELAY_SECONDS다. PRIMAL_ENEMY_RECOVERY_DELAY_SECONDS override가 우선하고 없으면 기존 PRIMAL_ENEMY_RESET_SECONDS를 fallback으로 읽는다. 기존 ENEMY_RESET_SECONDS import는 호환 alias만 남기며 production 유예 15초를 유지한다.

우두머리는 public으로 여러 솔로/파티가 참여할 수 있다. contribution에는 캐릭터별 damage, last_action_at, group identity를 기록한다. 자기 회복·방어만으로 최초 보상 자격이 생기지는 않는다. 지원/치유 기여 가중치는 아직 구현하지 않았다.

처치 시 실제 피해 기여가 있고, 같은 방에서 접속한 채 교전 중이며, 최근 15초 내 행동한 탐사자만 적격이다. 파티에 있다는 이유로 원격·AFK·미참여 멤버에게 지급하지 않는다. 도망 후 재참여하면 이전 기여는 이어받지 않는다.

경험치·보급칩은 적격 그룹의 피해 합계 비중으로 나누고, 파티 안에서는 적격 멤버끼리 균등 분배한다. 일반 적은 점유 그룹만 존재하므로 그 그룹이 전체 풀을 받는다. 각 단계에서 최대 나머지법으로 정수 총량을 보존하며, 같은 나머지는 그룹 키/캐릭터 ID 오름차순으로 결정한다. 보스 처치 플래그도 적격 탐사자 각각에게만 적용한다. 막타와 회수 명령자는 보상 자격을 독점하지 않는다.

## 시체·아이템 배정·바닥 전리품

사망 전이는 HP 감소, alive→respawning, 경험치·임무 보상과 시체 화폐 snapshot, 드롭 추첨 한 번과 Corpse 한 개 생성을 같은 트랜잭션으로 처리한다. state와 HP 조건을 다시 검사하여 중복 호출을 무시한다. DB 실패 시 Evennia의 Attribute/identity/방 내용 캐시도 복구하고 화면 전송·예약 작업은 성공 후 처리한다.

Corpse는 실제 공간 객체이며 source spawn/enemy, created_at, decay_at을 저장한다. Drop V1의 consumable/resource와 special은 독립 roll이며 각각 최대 1종/1개, Boss trophy는 별도 100%다. 경험치만 즉시 지급하고 실물 ItemEntity/LootClaim과 CurrencyLoot/Share가 시체에 남는다. Blob entries는 native loot SSOT가 아니다.

공용 보스도 시체는 하나다. 각 아이템은 정렬된 보상 그룹의 누적 피해 비중 구간에, 전체 드롭 개수로 나눈 등간격 중점을 대응시켜 그룹을 결정한다. 예를 들어 50:50 두 그룹에 두 아이템이면 각각 하나씩 배정된다. 아이템 수가 적으면 기여 비중이 낮은 그룹은 아이템을 못 받을 수 있다. 경험치·보급칩 비례 배분과는 별개이며 첫 회수자가 전체 드롭을 갖지 않는다.

선정된 파티의 실제 참여자를 가입 순서로 정렬하고 Party.round_robin_cursor를 적용한다. 아이템 한 개마다 순번을 증가시킨다. 현재 지원 모드는 round_robin뿐이며 `순번 파티분배`로 설정한다. free_for_all·need_greed·leader 방식과 관련 UI는 구현하지 않았다.

Physical root는 ItemEntity definition/quantity와 별도 LootClaim의 reserved_party/reserved_player/assigned_player/protection_until로 표현한다. 보호 중에는 배정된 탐사자 또는 원래 파티원이 회수를 요청할 수 있으나 실제 소지품은 assigned_player에게 지급된다. 배정자는 탈퇴·접속 종료해도 바뀌지 않는다. 보호 종료 뒤에는 회수 명령자가 받는다. 특정 아이템은 한 개, `<아이템> 모두`는 선택한 출처의 같은 종류 전체 수량을 처리한다. 여러 시체 전체의 회수는 `모든 시체에서 모두 가져`로 명시한다.

시체는 처치 후 30초에 남은 entries를 DroppedLoot 방 객체로 옮기고 삭제된다. 원래 권한과 처치 후 120초인 protection_until은 그대로 유지된다. 적은 처치 후 45초(시체 30초 + 대기 15초)에 같은 spawn으로 재생성한다. 바닥 아이템은 재생성 시 삭제하지 않으며 현재 별도 영구 소멸 기한은 없다. 장기간 운영 시 누적량 관리 정책이 필요하다.

## 시각 기반 생명주기와 재시작

Production 기본값은 world/timing.py, 실행 설정의 해석·사용은 world/multiplayer.py에서 관리한다. persistent timestamp가 진실이며 delay/task는 실행 편의다. 서버 시작, 5초 간격 WorldLifecycle script, 보기·공격·회수 시 같은 reconcile 함수를 사용한다. 지연된 시체는 바닥으로 옮기고 재생성 시각이 지난 적은 복원한다. 보호 만료 조회는 현재 시각 비교로 free로 해석하고 명시적 source reconcile은 expired LootClaim row만 삭제한다. 초대도 만료 시각으로 정리한다. 반복 reconcile은 전리품을 복제하지 않는다.

재시작 때 개인 combat_target과 Enemy의 참여·위협도를 정리한다. 파티와 개인 성장 기록은 유지되며 접속 후 살아 있는 상대를 다시 지정한다. 오프라인 중 자동 사냥 보상을 주지 않는다. 비정상 연결 종료는 서버가 단절을 인지하기 전까지 전투가 진행될 수 있다.

## 기존 데이터와 운영 범위

profile version은 10이며 `rules.migrate_profile()`은 과거 성장·임무·discovery·명령 설정을 사본에서 정규화하는 pure helper다. ItemEntity로 아이템을 생성하거나 world source를 전환하는 함수가 아니다. XP/HP/credits/quest와 성장 호환은 [성장 설계](progression.md)를 따르고, legacy item 필드는 별도 archive로 보존한다.

기존 DB의 inventory/equipment/storage/container/loot/currency/light/reference/entitlement 전환은 versioned `item_migration`의 explicit maintenance workflow다. 전체 source apply/verify 이후 cutover해야 일반 gameplay를 시작할 수 있다. Profile 정규화가 로그인 시 item lazy migration이나 legacy gameplay fallback을 허용하지 않는다. 정확한 source 범위·ledger·retry는 [item-migration](item-migration.md)을 따른다.

원자성 보장은 단일 Evennia 게임 서버 프로세스와 그 DB를 전제로 한다. 현재 잠금은 프로세스 내부 RLock이며 다중 게임 서버가 같은 월드를 동시에 쓰는 구조는 지원하지 않는다. PostgreSQL 설정 연결점은 있으나 이번 검증은 SQLite 기준이다. 수평 확장 전 DB 수준 락과 트랜잭션 경계·캐시 정책을 다시 설계해야 한다.

프로젝트 기본 Portal 서비스는 Telnet 8700·Web 8701·WebSocket 8702·Telnet SSL 8703·SSH 8704를 모두 IPv4 `0.0.0.0`에 bind한다. `ALLOWED_HOSTS = ["*"]`로 LAN IP/hostname의 HTTP Host를 허용하며 WebSocket URL은 접속 hostname에서 결정한다. 내부 Web 8705·AMP 8706은 loopback 연결이며 인증·가입·protocol 정책은 유지한다. SSL/SSH 선택 의존성은 Twisted `conch`/`tls` extras를 lockfile로 설치하고 최초 생성 key/cert는 명시적으로 Git에서 제외한다. Telnet은 평문이며 방화벽과 NAT 구성에 따라 LAN/외부에 노출될 수 있다. 외부 운영용 HTTPS/WSS·프록시·백업·모니터링은 별도 구성이다. 포트·키·cold start와 override 절차는 [설치 안내](installation.md#네트워크와-자동-생성-키)가 기준이다. 격리 Quick/Full smoke는 계속 loopback 인터페이스와 임의 포트를 사용한다. 정적 파일과 Neo둥근모 Code 글꼴·라이선스는 직접 제공하며 추가 빌드/npm/CDN 의존성은 없다.

### 현재 위치 방향 표시

`ROOMS[zone]["exits"]`를 서버 이동·`pz_state.exits`·Room 텍스트 방향도의 공통 출처로 사용한다. `ZoneRoom`의 formatter는 실제 사방 출구와 연결선만 순수 문자로 출력한다. 웹 SURROUNDINGS는 CSS Grid에 같은 방향을 배치하고 기존 `data-command` 버튼으로 방향 텍스트를 전송한다. 중앙 `[현재]`는 비대화형 표시이며 기타 출구는 별도 목록으로 표시한다. 이동 후 기존 appearance/state 전송으로 즉시 갱신하고 출구 배열이 같은 주기 전송에서는 버튼을 유지한다. 일반 로그의 `textContent` 출력과 서버 이동 제한은 변경하지 않는다.

## 텍스트와 의미별 색상

세계 사건과 조회 화면은 같은 데이터를 서로 다른 형식으로 표현한다. Room·공격·처치·전리품·NPC 대화는 한국어 서술이고, 상태·능력·경험치·기술·장비·소지품·상점·임무·파티·도움말은 `[제목]`과 짧은 행으로 구성한 compact 정보창이다. Room과 대상 보기는 기존 구분선과 설명·행동 안내를 유지한다. Room은 실제로 보이는 대상만 묘사하며 명령 목록을 넣지 않는다. 가능한 행동은 대상 보기와 command registry 기반 도움말에서 확인한다.

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

객체의 `DistantPresenceMixin.is_distant_visible(context)`와 `get_distant_presence(context)`가 노출 정책과 의미별 이름/단위/문장을 제공한다. Room 원거리 조립기는 객체 종류를 분기하지 않고 동일 요약을 자연어 수량으로 묶는다. Mixin과 ActionObject의 기본은 숨김이다. Commander/GrowthTrainer/Pathfinder, Container/PersonalLocker, Generator/SignalDevice만 ActionObject에서 명시적으로 opt-in하며 SupplyCache/MaintenanceLog/JungleMarker(WatchMarker/WaterMarker)/JungleCache는 숨긴다. 새 ActionObject는 설정 없이 원거리 노출되지 않는다. typeclass의 distant_visible 또는 객체 attribute override로 조정할 수 있고 기존 view access는 override와 무관하게 존중한다. Enemy/만료 전 Corpse/Explorer는 별도의 기존 노출 contract를 유지한다. Explorer는 익명 탐사자 수로만 표시하고 viewer 자신은 제외한다. 추가로 식별할 객체가 없으면 `그 밖에 눈에 띄는 것은 없다.`로 마무리한다.

원거리 객체 조립은 profile·상자 contents·loot entries를 읽지 않고 local selector/labels·행동/권한/HP 정보를 생성하지 않는다. Enemy는 살아 있고 HP가 양수일 때만, Corpse는 observed_at이 decay_at 이전일 때만 표시한다. 만료 시체를 필터링해도 삭제나 DroppedLoot 전환은 수행하지 않는다. 재생성 시각이 지난 Enemy도 저장된 alive 상태가 아니면 숨기며 실제 상태 갱신은 기존 lifecycle 소유자가 담당한다. Room view access가 없으면 장소명과 내부 객체를 보여주지 않는다.

`world.navigation.entry_block(profile, destination_zone)`는 Room requires와 임무 진행을 비교하는 pure helper다. 이동 hook은 이 결과의 기존 message로 이동을 거절한다. Exit의 `can_observe_through(context)`도 같은 결과를 사용하지만 이동 hook을 호출하지 않는다. 관찰에는 저장을 하지 않는 `Explorer.profile_snapshot()` 사본을 사용하여 구버전 데이터도 메모리에서만 변환한다. 현재 주요 진행문은 이동/관찰 모두 차단하고 목적지 이름·설명·객체를 읽거나 표시하지 않는다. 이동 가능성과 관찰 가능성은 별개 정책이며 투명 방벽 같은 미래 경계는 Exit의 `blocks_distant_view=False` attribute 또는 can_observe_through override로 관찰만 허용할 수 있다. 이 override는 이동 조건이나 view lock을 해제하지 않는다.

Room `requires.message`는 이동 실패 안내, optional `requires.observe_message`는 정찰 차단 안내다. 조건 판정은 `entry_block()`에 그대로 남기고 Exit가 관찰이 차단된 경우에만 해당 콘텐츠 문구를 선택한다. observe_message는 방향과 독립적인 문장 뒷부분이며 Exit가 기존 direction_phrase와 direction semantic token을 앞에 붙인다. 누락 시 `그 방향은 아직 자세히 살펴볼 수 없다.`라는 물리적 구조를 가정하지 않는 fallback을 사용한다. 무결성 검사는 이 필드를 강제하지 않으며, 지정했다면 비어 있지 않은 문자열인지 검사한다. 실제 진입문/출입문만 문 표현을 사용하고 임무 보고 조건은 중립적인 안내를 사용한다. `blocks_distant_view=False`와 can_observe_through override는 이 문구 선택보다 먼저 적용하며 Room view lock을 우회하지 않는다.

### Compact 정보 조회

`compact(title, *lines, summary=...)`는 기존 Text 조각을 보존하면서 제목과 요약을 한 줄에 놓고 첫 내용까지 빈 줄을 추가하지 않는다. 기존 `sheet`는 Room·대상 보기 등에 남긴다. 상태는 전투 수치·특성·장비 요약, 능력은 기본값과 투자값, 장비는 슬롯별 보정으로 역할을 나눈다. 소지품은 비어 있지 않은 분류마다 한 행을 만들고, 기술은 SKILLS의 설명과 다음 조건을 그대로 한 항목에 표시한다. R은 Rank이며 모든 화폐 비용은 공통 formatter로 칩 단위를 표시한다. 임무는 완료 수/전체 단계와 ASCII `+`(완료), `>`(현재), `-`(대기)로 구분한다.

기본 도움말은 registry 순서와 category를 사용한 명령 지도다. `명령이름 도움말`은 같은 metadata의 summary/usage/aliases를 표시하며 등록 별칭과 공용 단축어로도 조회할 수 있다. 상세 조회에서 단축어를 해석하는 것은 도움말 대상 검색이며 이동이나 게임 입력 parser는 바꾸지 않는다. `능력 도움말`은 ATTRIBUTES의 설명을 추가로 표시하고 기존 웹 성장 패널 tooltip도 유지한다.

웹은 기존 semantic span과 textContent 경로를 사용한다. 정보창은 `word-break: keep-all`로 공백을 우선해 줄바꿈하되 기존 `overflow-wrap: anywhere`로 공백 없는 긴 이름의 가로 넘침을 막는다. 글자 크기와 색상은 변경하지 않는다. CSS URL의 버전 표시는 이전 스타일 캐시가 새 줄바꿈을 가리지 않도록 한다. terminal ANSI 변환도 같은 Text를 사용하며 저장·경제·전투 규칙을 변경하지 않는다.

### 슬롯별 무장과 착용

`ITEMS[id].slot`이 장비 종류의 단일 출처다. `EQUIPMENT_ACTIONS`는 슬롯을 행동에 대응하며 `weapon → 무장`, `armor → 착용`이다. `Wield`와 `Equip`은 같은 구현을 사용하고 `rules.equip(profile, item_id, expected_slot)`에 기대 슬롯만 전달한다. 모든 검증은 저장 전에 끝나며 다른 슬롯·소지 수량·진행 상태는 바꾸지 않는다. 내부 규칙 호출은 expected_slot 생략 시 기존 공통 장착을 지원하지만 사용자 `equip` 별칭은 제거했다. parser는 변경하지 않았다.

대상 보기와 `pz_state.inventory[].equip_action`도 이 슬롯 대응을 사용한다. 웹은 전달된 행동을 기존 텍스트 명령 버튼으로 전송하며 장비 이름 목록을 따로 관리하지 않는다. `stats()`와 장비 화면은 양쪽 슬롯의 공격·방어를 모두 합산하므로 사냥창의 방어와 경량전술조끼의 공격도 적용된다.

장비 수치·보급칩 구매·드롭 경로는 [README 장비 표](../README.md#장비와-획득-경로)를 따른다. 두 번째 지역도 기존 장비를 활용하며 새 무기·방어구를 추가하지 않는다. 기존 장비 ID와 획득 경로를 유지한다.

## 아이템 이전·소비·보관

소지품과 보관 공간은 `item_id → quantity` 스택이다. `world.targets.stack_selector()`는 기존 DEFAULT/ALL을 재사용하고 inventory INDEX와 숫자 수량을 거절한다. `parse_relation()`이 `에게`/`에`/`에서`의 경계를 추출한 뒤 기존 selector와 room ordering으로 플레이어/상자 하나를 선택한다. 여러 플레이어·상자 동시 이전은 지원하지 않는다.

`world.item_transfer_native`는 공통 Entity API/world_change를 사용해 사용자 버리기·give·personal/shared storage를 처리한다. operation policy를 유지하고 owner-changing transfer에는 root와 descendants의 transferable=true를 요구한다. 같은 owner 개인 보관은 ownership transfer가 아니므로 Boss unique는 개인 보관 가능, 공용 보관/give는 불가하다. 실패 시 row·profile·참조·회복과 Evennia 캐시를 rollback한다. legacy rules.move_item은 정상 gameplay SSOT가 아니다.

공용 보관은 shared_storage/owner=Container인 ItemEntity, 개인 보관은 personal_storage/owner=Explorer인 ItemEntity다. PersonalLocker는 공간상의 서비스이며 아이템 owner가 아니다. 옛 Container.db.items/profile.storage는 archive이며 읽거나 쓰지 않는다. 두 객체는 지원동 1층 `storage_room`에 배치하며 bootstrap은 기존 DB 객체의 정적 이름·위치·alias만 동기화하고 contents를 초기화하지 않는다. 사용은 현재 Room의 실제 Container resolve를 따르며 Room ID gate를 두지 않는다. 기존 일회 조사 보급상자는 변경하지 않는다. 개인·공용 보관 용량과 nesting은 구현하지 않는다.

밀림 신호전지는 `transferable=False`다. 다른 곳에 옮긴 뒤 수위 표식을 다시 조사하는 복제를 막기 위해 버려·줘·공용/개인 넣어 모두 차단한다. 회수부품과 보스 trophy는 반복 획득하거나 진행 flag로 판정하는 일반 물품이며 이동 가능하다. 직접 버린 물건과 corpse decay는 같은 DroppedLoot 생성 helper를 쓴다. 직접 버린 entry만 예약/배정 없이 protection_until=0으로 생성하고 기존 corpse 권한은 보존한다.

native equipment row가 없으면 빈 슬롯이며 active_weapon은 None일 수 있다. 해제/벗어는 같은 Entity를 inventory로 옮기고 총 보유 수량을 바꾸지 않으며 stats·상태·장비·전투 문장·웹 state에서 빈 슬롯을 처리한다. 맨손 공격은 기존 base attack과 성장 보정만 사용한다. migration은 명시적 None을 초기 장비로 되돌리지 않는다.

야전식량/정제수의 `consume_action`과 `heal`이 소비 행동과 고정 효과의 출처다. 비전투 중 하나만 사용하고 최대 HP에서는 소비하지 않는다. 플레이어 치료의 Rank·지혜 공식을 재사용하지 않는다. 모든 이전과 장비 해제도 비전투 중만 허용하며 줘의 받는 탐사자도 비전투 상태여야 한다. 웹은 서버의 remove_action/consume_action을 기존 텍스트 명령 버튼으로 전송한다.

## Region·임무·Gate 확장

`world/content/starter.py`와 `deep_jungle.py`는 지역 Room/Enemy stable ID를 보존한다. items.py/final_items.py는 최종 아이템·가격, shops.py는 5개 상점 schema, loot_v1.py는 독립 resource/consumable roll과 최대 하나의 special roll 및 별도 trophy를 정의한다. content/__init__.py는 ROOMS/ENEMIES/ITEMS export를 유지한다. Region membership은 Room key에서 파생하며 content integrity가 참조·alias·출구·spawn·확률·획득 경로를 검사한다.

첫 지역 `dock`~`ridge`의 Room ID와 `zone:enemy` spawn ID를 보존한다. 최종 아이템 stable ID와 legacy source mapping은 [item-migration](item-migration.md)에 정의한다. `ridge` 북쪽에 밀림 입구를 연결했다. Spawn을 다른 Room으로 옮길 때는 새 Room의 `spawn_ids[enemy_id]`에 이전 stable tag를 명시하면 동일한 Enemy 객체와 HP를 유지한다. Room의 `requires`는 도착 시 필요한 임무 ID·진행 필드·거절 문구를 선언한다. `Explorer.at_pre_move()`는 이 데이터만 해석하며 지역 이름을 하드코딩하지 않는다. 통신탑은 발전기 복구, 밀림 입구는 첫 임무 보고, 연구구역 외곽은 밀림의 두 표식·신호전지를 확인한 신호 장치 가동을 요구한다. `exits`는 기존 `방향 → Room ID` 형태를 유지해 방향도·웹 버튼·서버 이동이 같은 정의를 읽는다.

`world/quests.py`의 임무별 단계는 `flag/대상/의미 역할/설명`과 안내문으로 구성된다. 선행 임무 조건 `requires`와 시작 전 표시 여부 `visible_from_start`도 임무 정의가 소유하며, 안내 선택과 임무 화면은 이 정의를 순서대로 읽는다. profile은 `quests[quest_id][flag]`와 개인 일회 발견용 `discoveries[id]`를 저장한다. 조회 화면은 완료 임무를 한 줄로 압축하고 진행 임무의 완료·현재·대기 단계를 보여준다. 웹 `pz_state`는 현재 안내 외에 Region ID/이름을 전달한다. 실제 임무 행동은 `ActionObject` subclass와 순수 `rules` 함수가 처리하므로 임무 DSL이나 새 parser는 없다.

`build_world()`는 Room 이름·설명, Exit 방향·별칭·목적지, 상호작용 객체 이름·별칭·위치, Enemy 이름·ID·최대 HP와 유휴 spawn 위치처럼 정적 정의가 소유하는 값을 동기화한다. 이전 정의 기준 alive·full·idle(교전자 없음)이면 새 max HP 기준 full로 맞춘다. damaged idle/교전 중이면 current HP를 유지하고 새 max 이하로 clamp하며 Boss encounter scaling 참가자 상태를 보존한다. Enemy의 교전 중 위치, state, respawn_at, claim, combatants, contribution, threat, round·timer·last_activity와 시체·바닥 전리품, 파티, 플레이어 profile·소지품·임무는 런타임이 소유하므로 초기화하지 않는다. 삭제된 관리 Exit/Interactable/spawn은 `stale_definitions()`로 보고하지만 자동 삭제하지 않는다. 실제 운영 DB에서 제거가 필요하면 상태와 참조를 확인한 뒤 별도 작업으로 정리한다. Region 3 추가 시 지역 정의, 필요하다면 작은 행동 subclass, 임무 정의 및 순수 규칙 함수를 더하고 무결성 검사를 통과시킨다.

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

환경 데이터는 캐릭터에 저장하지 않는다. 현재 개인 광원은 ItemEntity.state와 active_light 참조로 관리하고 legacy profile 광원 필드는 archive로 보존할 수 있지만 gameplay에서 읽지 않는다. 타이머·점유·참여 보상·Corpse/DroppedLoot·파티 정책은 해당 공통 서비스가 담당한다. LOS·외부 날씨 API·조도 전파 엔진·환경 피해는 제공하지 않는다.


## 관찰, 광원과 공용 시설

EnvironmentSnapshot은 viewer-independent 공용 환경이다. Room은 장소, Object는 현재 존재와 행동, immutable ObservationContext/ObservationSnapshot은 특정 관찰자가 실제 식별할 수 있는 정보를 소유한다. `world/observation.py`의 순수 `observe()`는 공용 snapshot과 읽기 전용 profile 사본에서 effective_light/effective_visibility를 계산하며 손전등을 ambient_light에 넣지 않는다. 같은 방의 A/B에게 환경 값은 같고 손전등 사용자의 시야만 달라질 수 있다.

시야 clear/reduced/poor와 객체 detectability conspicuous/normal/subtle을 중앙 matrix로 판정한다. clear는 모두, reduced는 conspicuous와 normal, poor는 conspicuous만 식별한다. Exit는 환경으로 숨기지 않는다. NPC·큰 시설·Container·Boss·비상장비함은 conspicuous, 일반 Enemy/Player/Corpse는 normal, 작은 기록·표식·보급품·DroppedLoot는 subtle이다. typeclass 기본값 또는 객체 `detectability` attribute로 확장한다. distant_visible의 기본 hidden/명시적 opt-in과 view lock은 먼저 유지하며 광원으로 우회하지 않는다.

`targets.visible()`는 view permission, `can_perceive()`는 환경상 지각을 담당한다. 공통 room_objects/resolve, Room local/distant presence, 웹 SURROUNDINGS, ActionObject.perform_action, transfer와 신규 Enemy.engage가 같은 정책을 사용한다. 시체 존재와 내부 작은 전리품은 별도 해상도다. 내부 아이템·회수는 subtle 지각을 요구한다. 기존 combat_target은 전투 중 어두워져도 추적하며 신규 상대 획득만 제한한다. 잠긴 Exit는 destination Environment/Observation을 만들기 전에 차단한다. 원거리 관찰은 profile·임무·방문·lifecycle을 진행시키지 않는다.

Light Source는 strength/range/power_type을, Power Source는 type/capacity_seconds를 선언한다. 호환성은 타입 일치로 판단하고 parser는 특정 battery ID를 분기하지 않는다. canonical 전원 삽입은 `<광원>에 <전원 소스> 넣어`이며 기존 parse_relation/stack_selector와 Store를 재사용한다. 예를 들어 `탐사용손전등에 고용량건전지 넣어`는 새 compatible 아이템 정의만 추가하면 같은 경로를 사용한다. 용량은 전원 정의가 소유하며 손전등 상수로 고정하지 않는다.

광원 runtime SSOT는 ItemEntity.state의 power_type/remaining_power/enabled/started_at과 Explorer의 active_light UUID다. ON 잔량은 읽기 전용 projection이며 OFF·소진·이동·logout/shutdown에서 정산한다. 옛 profile light_sources는 legacy upgrade 입력이며 gameplay fallback이 아니다. [현재 광원 계약](lighting-firearms.md)을 따른다.

전원 삽입은 battery Entity 수량 차감과 flashlight Entity state 변경을 같은 world_change에 저장한다. 잔량이 남으면 교체를 거절하며 부분 전원 회수는 없다. 이동 시 광원은 OFF/참조를 정리하고 잔량을 보존한다. 소실 row의 전원은 함께 사라진다. Legacy 마지막 복사본의 light_sources 제거는 historical adapter 계약이며 native instance 상태와 혼합하지 않는다.

공용 시설은 WorldLifecycle의 별도 `db.facilities = {"version": 1, "states": {"outpost_power": bool}}`에 저장하며 개인 generator_fixed에서 추론하지 않는다. `content/facilities.py`의 FACILITIES는 ID/초기값, Room `facility_lights`는 조명 연결, 저장 state는 현재 on/off를 소유한다. FACILITY_STATE_VERSION과 순수 new/normalize helper는 legacy bare dict의 True를 보존하고 None/빈 값에 기본값을 보완한다. 지원하지 않는 미래 버전은 오류로 중단하며 덮어쓰지 않는다. light_for 조회는 정규화 사본만 읽고 lifecycle/mutation transaction에서만 변환을 저장한다. 조명은 양수 strength와 always_on/power 중 정확히 하나를 선언한다.

발전기 수리의 개인 부품/보상/진행과 shared flag는 하나의 transaction이다. A가 수리해도 B의 개인 조건은 그대로이며 물리 조명은 동일하다. base light는 시간대·달·날씨·light_profile에서, facility light는 상시/공용 전력에서 계산하고 ambient light는 두 값의 최대다. 시설 조명이 존재하는 것과 밝기를 실제로 개선하는 것은 다르다. facility가 base보다 강할 때만 시설 문장으로 강조하며 맑은 낮 부두는 낮빛 표현을 유지한다. 부두 캠프는 상시 4, 관리동/발전실은 outpost_power일 때 4다. False→True에서 영향권 접속자에게 시설 가동 사건을 한 번 보내고 True→True는 반복하지 않는다. 기존 상태 push도 유지한다. bootstrap은 runtime state를 초기화하지 않고 Script attribute cache도 rollback에서 복원한다.

Room `hints`는 stable INTERACTABLES ID/action 또는 일반 text를 참조한다. 대상 이름은 INTERACTABLES가 SSOT이며 실제 방 객체의 태그·지원 행동과 can_perceive를 검사해 안내한다. hint와 SURROUNDINGS/selector는 같은 observed_at의 Observation 정책을 공유한다. clear에서는 지각 가능한 대상 안내와 일반 text를 원본 선언 순서대로 함께 출력한다. 제한된 시야에서는 지각 가능한 대상 안내만 출력하고, 없으면 광원 안내로 대체한다. 숨겨진 객체 이름을 일반 text에 넣지 않는다. wreck의 conspicuous 비상장비함은 poor에서도 안내하고 subtle 보급상자는 clear에서 안내한다.

광원 보기는 정적 item_appearance에 Look이 읽기 전용 lighting.status를 전달해 설명·상태·사용법을 조합한다. presentation은 player DB를 읽지 않는다. 확인은 같은 status helper를 쓰는 빠른 조회이며 동일 observed_at에서 보기/웹 잔량도 같은 ceil 분 표시를 사용한다. 일반 아이템 보기는 정적 정보를 유지한다. 광원이 환경 weather visibility까지 보완하는 것은 이번 matrix의 의도적 단순화이며 lux·LOS·전력망·연료·부분 전원 회수·은신·날씨 전투 modifier는 범위 밖이다.

기존 버전에서 발전기 개인 복구를 마친 캐릭터도 공용 전력이 아직 꺼져 있으면 수리 명령으로 가동할 수 있다. 이때 부품·보상·개인 진행을 다시 변경하지 않으며, 이미 가동된 시설에는 중복 보상을 주지 않는다.

웹은 environment와 observation을 분리하며 현재 시야와 손전등 상태를 표시한다. 소지품의 켜기/끄기/확인은 서버 명령을 보내고 compatible 전원별 삽입 버튼은 실제 아이템 이름을 포함한다. 렌더링이나 시각 조회는 전원 소모를 저장하지 않는다.

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

`world/timing.py`가 production 2.5/30/15/120/15/15/15초 기본값을 갖고 `world.multiplayer`는 선택적인 `PRIMAL_*` settings를 읽는다. `settings_test`는 타이머를 줄이지 않는다. `server/conf/smoke_support.py`의 Quick 값은 2.5/10/2/20/15/15/2초이며 Full은 production 기본값을 그대로 쓴다. Quick에서 점유/참여 만료는 관찰 대상이 아니므로 production 15초를 유지하고 DB/state 전송 지연으로 유효 참가자가 지워지는 false timeout을 막는다. Quick의 outsider 거절/부분 pickup 요청은 병렬 전송해 불필요한 두 command 왕복을 피한다. 공동 전투는 2.5초 공격 간격으로 실제 join/state 전송 전에 한 명만 처치하는 race를 막고, 시체는 10초 관찰 창을 확보한다. 기존 실제 `delay()` 및 WorldLifecycle의 5초 sweep을 재사용하며 fake Clock나 새 scheduler framework는 없다.

`scripts/smoke_harness.py`는 실행마다 새 작업 경로에 게임 코드/새 SECRET_KEY·SQLite를 준비하고 `smoke_setup.py`를 별도 프로세스에서 실행한다. DB 접근 전 marker·정확한 작업/DB 경로·SQLite engine을 검증한다. 사용자 PostgreSQL 환경은 제거한다. Smoke 전용 SQLite는 Portal+Server 재시작 중 읽기→쓰기 승격 경합을 막도록 IMMEDIATE transaction과 30초 busy timeout을 사용한다. 일반 플레이 DB 설정은 바꾸지 않는다. 정상 Evennia Account/Character API로 일반 fixture 계정을 만들고 기본 quest/파티/전투/시작 위치와 구매 자금/HP를 준비한다. 비밀번호는 runtime 메모리와 자식 stdin으로만 전달한다. 결과 장비/시체는 scenario의 실제 동작으로 생성한다.

정상 초기 객체·static 준비를 마친 fixture DB에 초기 setup 완료를 기록해 첫 실행의 자동 재시작을 피한다. 실제 Twisted foreground Portal/Server를 각각 시작해 exit를 추적하고 loopback HTTP/WS readiness를 polling한다. scenario 중 health monitor가 server premature exit를 실패로 전파한다. 실패·interrupt·성공 모두 자체 Popen/process group만 종료하며 개발 서버 launcher stop/reload를 호출하지 않는다. 성공 시 자신이 생성한 marker 경로만 삭제하고 실패 시 진단 DB/로그를 남긴다. CI는 기존 `test`와 추가 `smoke` job을 실행하고 Full은 제외한다. 실패 단계는 로그 tail만 출력하며 DB는 출력/업로드하지 않는다.

Quick/Full의 client·단계·predicate 대기를 공유한다. 공개 register/610초 sleep·5회 반복 사냥을 제거하고 auth/party/combat/corpse/lifecycle/protection/respawn/shop/persistence 단계별 결과를 출력한다. 시체 배정/파티 회수 권한을 읽고 그대로 남겨 그 시체의 ground 전환과 outsider 회수를 검증한다. Full은 실제 관찰 시각의 허용 오차를 적용해 지나치게 빠른 production 만료를 탐지한다. 일반 플레이 SQLite의 hash·mtime·size는 실행 전후 비교할 뿐 migrate/fixture/cleanup 대상이 아니다. 프로필 schema나 production 게임 밸런스는 바꾸지 않는다.


## 본부 7단계: 통합 closeout

훈련·Doctor·Bed·정산관·Shopkeeper에서 같은 Room/safe/비전투/지각의 동일한 조건만 작은 `_service_available` helper로 통일했다. Shopkeeper는 유효한 shop_id도 요구한다. Container는 기존 실제 대상 resolve와 transfer 정책을 유지하며 전투 조건이 다른 일반 조사 객체와 억지로 공통화하지 않는다. `ActionObject.web_actions()` capability와 subclass override는 이미 서버 명령을 소유하므로 유지한다. Room hint의 진료/휴식/환율/상품 availability 분기는 현재 선언과 일반 action의 서로 다른 의미를 정확히 구분하고 있어 유지한다. 새로운 service/action framework는 없다.

runtime at_dock/global SHOP/EXCHANGE/교환 구매 flag 및 client service zone gate는 없다. 지도에서 현재 Room을 표시하는 zone 비교와 content graph·정적 배치·integrity·테스트 경로는 정상 사용이다. 옛 중앙홀/1층 중앙 관리 Exit migration은 기존 DB 호환을 위해 유지한다. 가격·정산율·보상·타이머·profile schema는 변경하지 않는다. 귀환 후 윤대장에게 보고하는 안내는 부두로 직접 귀환한다고 읽히지 않도록 정리했다.

Full만 `scripts/smoke_closeout.py`를 이어 실행한다. 공용/개인 보관, 정산·훈련·Doctor/Bed, 세 상점과 장착, 일반 귀환·실제 적 패배, 발전기 부품 소비·첫 보고, 밀림 표식/신호전지/gate·두 보스를 actual parser/DB/scheduler/WS로 검증한다. Snapshot은 marker/path/SQLite guard 이후 격리 DB에서 읽기만 하며 비밀번호를 조회하지 않는다. Quick은 기존 공동 사냥 1회와 빠른 연결 검증 범위를 유지한다.

Restart는 harness가 소유한 foreground Portal과 Server를 모두 종료하고 같은 DB·설정·포트로 다시 시작한다. 새 migrate/fixture/reset은 하지 않는다. restart 동안만 기존 health monitor를 유예하고 readiness 실패/종료 오류는 그대로 실패한다. 재인증 후 캐릭터 DB ID·위치·home=dock·성장/임무/방문, party membership, 승강기 3층·시설·환경 clock을 비교한다. Native player equipment/personal storage와 공용 상자는 실제 ItemEntity UUID·수량·sequence·canonical 위치/tree를 snapshot으로 비교하며 archive의 빈 equipment/storage/db.items를 보존 근거로 사용하지 않는다. Loot도 native source_entries를 읽는다. live combat/claim은 정리되고 남은 시체 deadline과 respawn은 실제 callback/sweep으로 완료되며 전리품은 ground에 보존된다. 광원은 기존 마지막 session/restart의 off 정책을 따르므로 지속 점등을 기대하지 않는다.

## Historical Phase 1~5 implementation notes

아래는 당시 구현 범위와 결정의 기록이다. 현재 backend·가격·획득·설치 판단은 위 현재 계약과 final-content/item-migration을 따른다. 당시의 미구현·후속 단계 표현은 현재 미구현 상태를 뜻하지 않는다.

## Phase 5 출입증·접근·거래 경계

Quest state는 entitlement/진행 이력이고 실제 access authority는 Credential ItemEntity다. Room access는 availability와 개인 credential을 읽기 전용 can_enter로 검사한다. legacy/native backend와 관계없이 credential_service가 지급·재발급을 소유하고 pure rules의 보상과 profile 저장을 outer world_change로 묶는다. 임무 완료만으로 입장시키거나 profile inventory에 출입증을 복제하지 않는다.

Shopkeeper는 공간상의 서비스 제공자이며 Entity 재고 owner가 아니다. shop_service가 purchase_catalog/accepts를 분리하고 source/sink 거래를 처리한다. 일반 legacy 거래·소각은 profile adapter, native 거래·소각은 ItemEntity API를 사용한다. Legacy의 추가 Entity 소지품 표시는 Credential에만 한정한다. 공통 수량 parser와 destroy_quantity는 부분 stack identity를 유지한다. 기존 lock·reference·회복·LootClaim/화폐 경계를 대체하지 않으며 가격·콘텐츠 전체/migration/cutover는 Phase 6에 남긴다. 자세한 API·모든 이동 경로 조사표는 [출입증·접근·상점](credentials-access-shops.md)을 따른다.

## Phase 4 전리품 권리·화폐 (2026-10-06)

Corpse/DroppedLoot는 공간 owner이며 실물은 ItemEntity, root 권리는 LootClaim, 보급칩은 CurrencyLoot와 player별 CurrencyLootShare다. 0인 share도 원래 요청 자격을 보존한다. 만료 조회는 읽기 전용이고 lifecycle에서 해당 source의 expired claim을 삭제한다. 부분 회수는 source claim 유지→claim 없는 split→inventory 이동/merge이며 전체 회수는 identity/sequence를 유지한다. decay는 tree·권리·화폐 share·보호 기한을 보존한다.

`loot_service → LootSourceSnapshot/LootEntrySnapshot → 기존 권리/payout helper·command·presentation` 경계다. owner→UUID→claim/currency/share lock과 mutation은 persistence 계층에 있고 pure rules에 ORM을 넣지 않는다. generic merge도 root 배정 단위와 권리를 비교한다. 화폐 quantity·share·모든 recipient credits는 기존 world_change 하나에서 처리한다.

현재 사냥과 기존 blob은 legacy SSOT를 유지한다. 신뢰된 native 생성만 새 모델을 선택하며 dual-write/lazy conversion은 없다. backend가 다른 실물 recipient로는 자동 변환하지 않는다. inventory/storage·world blob의 명시적 전체 migration/cutover는 Phase 6이다. 모델·API·기존 필드 대응·해석·검증 공백은 [전리품 권리](loot-claims.md)를 따른다.

## Phase 3 광원·총기 (2026-10-06)

`lighting_service/firearm_service → LightSnapshot/FirearmSnapshot/MagazineSnapshot/EquipmentSnapshot → pure rules/visibility/presentation` 경계로 연결한다. ORM은 persistence service에만 두며 rules/progression/modifier 계산에 넣지 않는다. flashlight power(초)/enabled와 magazine rounds는 ItemEntity.state가 단일 SSOT다. 총기는 rounds를 중복 저장하지 않고 inside/socket=magazine child를 조회한다. active_weapon과 active_light는 실제 Entity UUID 참조이며 같은 item transaction에서 reconcile한다.

ON 잔량은 읽기 전용 projection이고 정상 관찰에서는 저장하지 않는다. switch/OFF/소진/이동/삭제/logout/shutdown에서 상태와 참조를 원자적으로 정리한다. source/destination/parent root의 Explorer owner를 ID 순으로 잠그고 전체 관련 UUID를 모아 잠근다. split/merge도 owner→UUID 순서를 사용한다. 총기 socket은 parent lock과 조건부 DB unique로 보호한다. 중앙 update_item_state는 full_clean/save를 적용하며 user load/unload는 명시적 root policy다.

pure 전투 outcome의 shot_fired와 실제 magazine 감소를 기존 world_change에 묶는다. 빈 firearm은 공격 기회만 사용하고 mental/cooldown commit 전에 반환한다. 성공한 combat reload는 다음 기회 하나를 대체하며 no-op/실패는 기회를 유지한다. legacy firearm은 기본 ammo-free 계약을 유지한다. shared enemy HP·전리품 권리·성장·Defense V1·기존 가격은 바꾸지 않는다.

legacy lighting은 기존 light_sources를 단일 adapter 경계에서 LightSnapshot으로 제공한다. profile inventory/equipment/storage/light_sources, Container.db.items와 Corpse/DroppedLoot legacy data의 SSOT는 Phase 6까지 유지한다. 명령으로 backend 선택/lazy migration/dual-write를 하지 않는다. 최종 V1 콘텐츠와 shop/drop wiring은 적용하지 않았다. 실제 API·명령·state·검증·Phase 4 운반 구조는 [광원·총기](lighting-firearms.md)를 따른다. 아래 과거 단계에서 광원/총기를 후속 단계라고 한 설명은 당시 범위다.

## Phase 2 장비·Modifier·Defense (2026-10-05)

현재 장비 계산은 `equipment_service → EquipmentSnapshot → equipment/modifiers/rules/recovery/presentation` 경계로 연결한다. ORM은 service에 있고 rules/progression/recovery의 계산은 DB·Evennia와 독립적이다. profile version은 10이다. 아래 과거 구현 설명의 고정 방어와 두 legacy 장비 slot은 이번 단계의 최종 계산·slot 계약보다 우선하지 않는다.

Entity 장비는 equipment/Explorer/최종 slot에 저장하며 손 capacity2·반지2·나머지1과 손 조합을 검사한다. 주무기는 Explorer Attribute의 ItemEntity UUID 참조이며 공통 create/move/delete transaction 안에서 자동 선택·승계·제거한다. 장비 변경은 옛 recovery rate 정산 → 새 위치/주무기/snapshot → 새 max/rate 계산 → current clamp → 저장 순서다. 자원 무료 회복과 자동 장비 교체는 없다.

기존 플레이어의 profile 장비 SSOT는 Phase 6까지 유지한다. 제거 가능한 `equipment_legacy` 단일 adapter가 weapon→hands, armor→body와 수치→modifier를 연결한다. 명시적으로 선택한 backend 한 곳만 쓰고 hidden migration/dual-write하지 않는다. stats/combat/recovery/presentation/Web는 공통 snapshot을 사용한다. legacy 이전·판매의 장착분 예약 direct-read만 해당 저장 shape와 함께 후속 단계에 남긴다.

Modifier는 구조화된 target/op/value/scope의 add 합산·multiply 곱·clamp 계약이다. Defense V1은 `raw*20/(20+defense*(1-penetration))*(1-defense_skill_reduction)`이며 양방향 공통 helper에서 마지막에 int 내림·최소1을 적용한다. 성장·콘텐츠 수치는 유지한다. 상세 slot/selector/참조/기술·회복 적용/Phase 6 제거 경계는 [장비 설계](equipment.md), ItemEntity 불변조건은 [영속 기반](item-entities.md)에 기록한다.

## ItemEntity 기반 1단계

`world.item_entities` Django 앱이 독립 실물 아이템 row·전역 순번·canonical 위치·스택·부모 트리·원자적 API를 제공한다. 정적 정의는 기존 ITEMS registry다. 기존 gameplay의 profile/Attribute 저장은 아직 전환하지 않고 새 row와 이중 쓰기를 하지 않는다. profile version은 10이다. 장비·modifier·Defense는 Phase 2 서비스에 연결했고 총기 상태·LootClaim·화폐·Credential·전체 저장 변환은 후속 단계다. DB/application 제약, API와 migration 적용 경계는 [ItemEntity 기반](item-entities.md)을 따른다.


### Historical profile/blob·초기 경제·광원 경계

`world/loot_assets.py`의 읽기 전용 normalize_entry는 legacy {item, quantity}를 {kind: item, id, quantity}로 해석한다. 새 currency entry는 kind=currency·id=credits·quantity·eligible_players·remaining_shares와 공통 reservation/protection_until을 가진다. 초기 PR의 shares는 읽을 때 원래 key를 eligible_players로, 양수 몫을 remaining_shares로 해석한다. 입력을 변경하지 않고 반복 normalize도 안정적이며 새 저장은 분리된 구조를 사용한다. 상세 보기·Web·회수·decay가 이 계층을 공유하며 조회로 DB를 다시 쓰지 않는다.

`rules.reward_allocation(amount, groups)`는 그룹 기여도 비례 → 파티 내부 균등 → deterministic 최대 나머지법으로 총량을 보존한다. XP는 처치 transaction에서 즉시 지급하고 enemy.currency는 그룹별 currency entry로 저장한다. eligible_players는 처치 시점 적격 참여자 snapshot으로 파티 변화·로그아웃과 무관하게 고정된다. remaining_shares는 아직 지급하지 않은 금액만 담는다. 보호 중 루팅 요청자는 protected distribution을 trigger할 자격을 가질 뿐, 자신의 remaining share가 0이라는 이유로 자격을 잃지 않는다. currency_payouts는 remaining_shares만 weight로 부분 지급한 뒤 몫과 quantity를 차감하며 0인 몫은 제거한다. 실제 지급은 session 없이도 persistent Explorer에 저장하며 수령 객체가 없으면 전체 transaction을 rollback한다. 다른 그룹 entry는 남는다. 보호 만료 후에는 남은 금액을 caller에게 지급하며 과거 자격/몫을 적용하지 않는다. 시체 decay는 quantity·eligible_players·remaining_shares·reservation·보호 deadline을 바닥으로 그대로 옮긴다.

ITEMS[*].value만 상품 가치와 구매가를 소유한다. SHOP_CATALOGS는 item ID tuple, Shopkeeper는 shop_id와 catalog의 취급 사실만 소유한다. purchase_price와 resale_price(value//2, 최소 1)가 가격을 계산한다. 가치/판매는 기존 구매의 seller selection·safe/peace/perception 정책을 재사용한다. 판매는 move_item의 transferable·장착 복사본 reservation을 사용하며 일반 판매에 수량 N개 문법은 추가하지 않는다. Web 기본 판매도 1개이며 판매 가능한 복사본이 2개 이상일 때만 별도 모두 판매와 총액(장착분 제외 수량 × 매입가)을 제공한다. value 없는 임무/resource는 매매하지 않는다.

보급칩은 유일한 구매 currency, scrap은 material/resource다. `profile.inventory["scrap"]`와 개인 storage의 기존 저장 형식을 유지하며 migration·자동 환전은 없다. 적 전리품·이전·보관 정책과 발전기의 부품 3개 소비를 보존한다. `world/content/economy.py`의 `SALVAGE_CREDIT_RATE=10`은 정산율 SSOT다. 기존 장비용 EXCHANGE 정의/export와 구매 flag를 제거하고 `rules.buy(profile, shop_id, item_id)`는 6단계 SHOP_CATALOGS의 품목을 확인하고 ITEMS[item_id].value에서 보급칩 가격을 조회한다. 5단계 당시 부두 임시 상점은 6단계에서 실제 Shopkeeper로 대체됐다.

`world/content/shops.py`의 `SHOP_CATALOGS`는 취급 품목만, `ITEMS[*].value`는 가격만 소유한다. 보급품 5종·무기 5종·방어구 4종의 기존 14개 가격을 모두 보존한다. `rules.buy(profile, shop_id, item_id)`는 비전투·유효 catalog·해당 상품·보급칩 충분 여부를 전부 검증한 뒤 credits와 소지품을 함께 변경한다. scrap 정산·임무 소비·전리품·기술 가격·패배 패널티는 변경하지 않는다. 무한 재고로 매번 1개만 판매한다.

`rules.move_item()`은 아이템의 명시적 `transferable` 정책, 보유 수량과 현재 equipment가 예약한 복사본 수를 검사한 뒤 source 차감·destination 증가·빈 스택 제거를 처리한다. 버려·줘·넣어·꺼내는 모두 이 규칙을 쓰며, `world.item_transfers.transfer()`가 기존 `world_change()`의 서버 잠금과 DB transaction 안에서 영속 소유자를 저장한다. 저장 실패 시 기존 DB/Evennia 캐시 rollback과 after_change 정책을 재사용한다. 마지막 공용 아이템의 두 요청도 같은 단일 서버에서 직렬 처리된다. 별도 거래/loot 권한 체계는 없다.

`world/content/starter.py`에는 기존 8개 Room/4종 Enemy의 stable ID를 보존한다. `deep_jungle.py`에는 7개 Room/4종 Enemy를 정의한다. `items.py`는 공통 아이템, `shops.py`는 세 상점의 item ID catalog만 담고 가격은 `items.py`의 value가 소유하며 `content/__init__.py`가 기존 `from world.content import ROOMS, ENEMIES, ITEMS` 경로를 유지한다. `REGIONS[region].rooms`는 각 지역 파일의 Room key에서 파생되므로 Room↔Region 소속을 두 곳에 입력하지 않는다. `ROOM_REGION`은 이 정의에서 파생된다. ID 충돌·참조 누락·출구 역방향·spawn 충돌은 `content.integrity.errors()`로 검사한다.

v6부터 사용하는 `light_sources[item_id]`에는 on, power_source, charge_seconds, started_at을 저장한다. v1~v5 migration은 기존 inventory/equipment/storage/quest/growth/combat을 보존하고 빈 light_sources만 보완한다. 켠 동안의 잔량은 `charge_seconds - (now - started_at)`으로 투영한다. tick마다 차감·저장하지 않고 소진 때 한 번 off/0/전원 없음으로 확정한다. 꺼짐·마지막 session 종료·정상 서버 종료에는 잔량을 확정하며 오프라인 동안 사용하지 않는다. 강제 종료로 마지막 종료 hook이 실행되지 않으면 재시작에서 off로 정규화하며 종료 전 정확한 잔량은 보장하지 않는다.

전원 삽입은 inventory 차감과 장치 상태 설정을 world_change transaction에 함께 저장한다. 잔량이 남은 전원은 교체를 거절하고 부분 충전 아이템 회수는 제공하지 않는다. stack 모델에서 마지막 광원을 이전하면 내부 전원은 폐기하고 안내한다. lighting.discard_device_state_if_unowned는 일반 전달·버리기·컨테이너 보관·판매가 마지막 복사본을 잃을 때 light_sources를 제거하는 공통 소유권 규칙이다. 판매 후 재구매해도 과거 전원/잔량은 부활하지 않는다. 여분 복사본만 이전할 때는 개인 active 상태를 보존한다. 전원/광원 일반 아이템의 이동 및 기존 장착·임무 아이템 보호는 공통 transfer 규칙을 유지한다.

### Historical profile normalization boundary

아래는 성장/profile 호환을 설명하던 당시 기록이다. 현재 full-world item migration 경로는 위 explicit maintenance 계약을 따른다.

profile의 최신 버전은 10이다. v9 이하는 여덟 기술의 기본 Rank와 재투자 가능 훈련으로 정규화하며 자세한 성장 호환은 [성장 설계](progression.md)를 따른다. v1/v2의 개인 encounter 제거·전투 입력 필드·성장 기본값 변환을 거친 뒤, v1~v3의 첫 임무 boolean을 `quests.radio_tower`의 진행 필드로 옮긴다. `cache_claimed`는 `discoveries.supply_cache`로 옮긴다. v1~v4에는 개인 보관 `storage={}`의 기본값을 추가한다. XP, HP, credits, inventory, equipment(명시적 None 포함), kills, 완료 여부와 visited 및 개인 전투 상태를 유지한다. 이미 받은 보상은 재지급하지 않는다. v1~v5에는 개인 광원 `light_sources={}`, v1~v6에는 개인 줄임말 `command_shortcuts={}`를 보완한다. v8 이하에는 현재 최대 정신력과 빈 recovery_effects를 추가하며 timestamp는 첫 mutable accrue에서 초기화한다. migration은 시간을 조회하지 않고 profile_snapshot은 사본만 변환한다.

변환은 기존 프로필의 복사본에서 첫 임무·보급 boolean을 새 구조로 옮기고 오래된 key를 제거한다. 기존 플레이어는 현재 레벨에 해당하는 포인트를 즉시 사용할 수 있고, 무료 기본 기술 Rank 1과 미투자 특성은 기존 전투 성능을 유지한다. Party·Enemy·Corpse·DroppedLoot는 profile 밖에 있으므로 migration이 수정하지 않는다. 기존 DB의 로드 시 점진적으로 변환하며 DB 삭제·교체는 필요 없다. 위의 서버 재시작/재접속 전투 정리 정책과 migration 자체의 보존 정책은 별개다.
