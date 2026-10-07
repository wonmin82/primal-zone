# 광원·총기·탄창

Phase 6 현재 상태: cutover 후 일반 gameplay는 native ItemEntity만 사용한다. 아래 legacy adapter/Phase 6 예정 설명은 Phase 1~5의 설계·검증 기록이며 maintenance migration과 historical audit fixture의 호환 경계로 남는다. 최신 저장·운영 정책은 [item-migration](item-migration.md), 최종 콘텐츠·가격은 [final-content](final-content.md)를 따른다.

## 저장과 계산 경계

`lighting_service`와 `firearm_service`가 ORM·Explorer Attribute·원자적 변경을 맡는다. `lighting.LightSnapshot/LightItem`, `firearms.FirearmSnapshot/MagazineSnapshot`과 `EquipmentSnapshot/EquipmentItem`은 gameplay 정보다. `rules`, `progression`, modifier와 visibility 계산에는 ORM·Evennia 의존성을 추가하지 않았다. `active_weapon()`은 backend-neutral EquipmentItem이며 `active_weapon_item()`은 영속 작업용 Entity row다. 총기도 `loaded_magazine()`과 `loaded_magazine_item()`을 구분한다.

일반 광원·총기·탄창·탄약은 native ItemEntity SSOT다. 기존 DB의 inventory/equipment/storage/light_sources와 loot blob은 maintenance migration 입력/보존 archive이며 gameplay fallback이 없다. 신규 캐릭터는 native로 직접 시작하고 사용자 명령에 lazy migration·fake UUID·dual-write는 없다.

## 손전등

각 Entity의 canonical state는 다음과 같다. 잔량 단위는 초이며 건전지 하나는 1800초다.

```json
{"power_type": "flashlight_battery", "remaining_power": 1800, "enabled": false, "started_at": null}
```

ON일 때 `started_at`을 기준으로 경과 시간을 뺀 읽기 전용 projection을 사용한다. 정상 ON의 관찰·주기 reconcile은 잔량을 매 tick 저장하지 않는다. OFF·교체·소진·소유권/위치 변경·logout/shutdown에서는 elapsed power를 확정한다. 소진은 잔량0/OFF/참조None이다. 일반 OFF·이동·보관은 Entity의 잔량을 보존한다. 삭제된 광원의 상태는 함께 사라진다.

`Explorer.db.active_light_item_id`는 실제 UUID 문자열이다. 현재 소유한 direct inventory 광원이며 enabled/잔량>0일 때만 유효하다. snapshot은 stale 참조를 무시하고 읽기에서 수리하지 않는다. domain reconcile은 참조를 정리하되 다른 소유자의 잘못 참조된 광원은 변경하지 않는다. `switch()`는 현재 ON 광원의 경과 정산/OFF와 새 ON/참조를 같은 transaction에서 처리해 only-one-ON을 보장한다. `insert_power()`는 잔량이 없을 때만 호환 battery stack 한 개 소비와 충전을 원자적으로 수행한다. 실패하면 양쪽 모두 rollback된다.

`lighting_snapshot()`은 정상 runtime에서 Entity 정보를 LightSnapshot으로 제공한다. Legacy adapter는 historical fixture 호환용이다. observation은 한 관찰 시각의 snapshot을 visibility와 Web 표시에서 재사용한다. Legacy definition 단위 light_sources는 migration 입력이며 gameplay에서 Entity state를 복제하거나 fallback하지 않는다. 두 손전등의 잔량·켜짐은 독립적이고 `손전등`/`손전등 2` selector로 구분한다. 확인은 상태·전원·분 단위 잔량, 소지품은 ON/OFF와 백분율을 표시한다.

`날씨`/`환경` 상세는 `ObservationContext.lights`의 같은 LightSnapshot을 `lighting.snapshot_status()`로 표시한다. 환경·광원 projection·시야·상태 push는 한 명령의 `observed_at`을 사용하며 상세 출력을 위해 광원을 다시 조회하지 않는다. 조회 자체는 profile·Entity state·active reference를 쓰지 않는다.

reconciliation 이후 사용할 수 있는 owned direct inventory 광원의 enabled Entity는 유효한 active_light 참조와 일치한다. malformed/missing/None 참조에서는 owned orphan ON 광원의 elapsed power를 정산하고 OFF·started_at=None·참조None으로 정규화한다. 자동으로 다른 광원을 선택하지 않는다. 유효한 active가 있어도 추가 orphan ON은 OFF로 정리하며 정상 active의 잔량을 매번 저장하지 않는다. 다른 소유자·storage·world/corpse loot 광원은 orphan 탐색 대상이 아니다. 기존 이동 hook의 이전 소유 광원 정산은 그대로 유지한다.

## 총기·탄창·탄약

| family | ammo_type | 탄창과 capacity |
| --- | --- | --- |
| pistol_9mm | 9mm | 소형8 / 표준12 / 확장18 |
| carbine_556 | 556mm | 단축15 / 표준20 / 확장30 |
| rifle_762 | 762mm | 표준8 / 확장12 |

탄창은 non-stack이며 `state.rounds`의 정수0..capacity가 잔탄 SSOT다. loose ammo는 탄종별 stack이다. 총기는 rounds/ammo_count를 저장하지 않는다.

```text
Firearm (inventory 또는 equipment root)
└─ Magazine (inside, parent_item=firearm, socket=magazine)
   state.rounds
```

정의·저장 검증은 family/weapon_type, 탄종·용량·비스택, rounds 범위, socket의 parent/child family를 검사한다. parent row lock과 `0003_magazine_socket`의 조건부 unique(parent_item, socket="magazine")가 한 총기에 탄창 하나를 보장한다. 다른 generic socket의 미래 다중 슬롯은 제한하지 않는다.

세 firearm family와 실제 최종 권총/카빈/소총, 탄창 8종·탄약 3종이 registry와 shop catalog에 연결되어 있다. 고장난경비기는 경비카빈+단축탄창 2~6발, 그늘추적룡은 전술권총+표준탄창 2~5발을 드롭한다. [최종 콘텐츠·가격·획득](final-content.md)을 따른다.

`create_firearm()`은 no_mag/empty/partial/full_standard 획득 형태를 제공한다. 탄창 생성·rounds·inside 배치·sequence 발급은 같은 transaction이다. Shop package와 legacy firearm migration은 full_standard, 신규 enemy drop은 content-defined partial을 사용한다. 기존 native tree는 migration에서 보존한다.

## 명령과 재장전

Phase 3 광원·전원·reload/load/unload 명령과 일반 Store/Retrieve는 기존 일반 command recovery reconciliation을 따른다. `equipment_change=True`의 특별 lifecycle은 실제 equipment stat/max/recovery 경계를 바꾸는 착탈·주무기 명령에만 남긴다. ItemEntity mutation 자체는 recovery bypass 사유가 아니다. 각 Phase 3 service에 별도 회복 정산을 복제하지 않으며 combat reload의 기존 accrue_recovery/기회 소비/save_profile 경로도 유지한다.

명령은 공통 target parser와 instance selector를 사용한다. 실제 등록된 기존 총기를 예시로 한다. 미변환 runtime은 migration-required 오류로 거절하며 명령 중 legacy 총기를 자동 변환하지 않는다.

```text
손전등 2 켜
손전등 2 확인
손전등 2에 건전지 넣어
탐사카빈 재장전
탐사카빈에 카빈표준 2 장전
탐사카빈에서 탄창 꺼내
카빈표준 2에 카빈탄 넣어
카빈표준 2 채워
카빈표준 2에서 카빈탄 꺼내
```

자동 reload는 직접 inventory의 호환 탄창 중 양수 잔탄 최대, 동률이면 sequence가 가장 작은 것을 선택한다. 현재 탄창이 같거나 더 많으면 no-op이다. 빈 현재 탄창에 양수 후보가 없으면 실패한다. 7→12, 12→18은 교체하고 12→12는 유지한다. 명시 reload는 양수 잔탄의 호환 inventory instance를 선택하며 현재 instance 지정은 no-op이다. swap은 옛 탄창→inventory와 새 탄창→inside를 함께 처리한다.

성공한 combat reload는 공통 `consume_combat_opportunity()`로 다음 공격 기회 하나를 대체하고 queued_action을 attack으로 정리한다. 아직 도래하지 않은 기회도 `max(now, next_attack_at)`을 기준으로 소비하므로 scheduler 순간에 맞춰 입력할 필요가 없다. 정신력·skill cooldown은 소비하지 않는다. no-op/실패는 기회를 소비하지 않는다.

탄창 분리와 loose ammo load/unload는 비전투에서만 가능하다. 자신의 inventory 탄창 또는 자신의 소지/장착 firearm 안 탄창에 loose ammo를 넣거나 꺼낼 수 있다. 다른 소유자·storage·world/corpse loot는 거절한다. load는 빈 capacity와 보유량 중 작은 만큼 넣고 stack을 차감/삭제한다. unload는 항상 전량이며 compatible inventory stack이 있으면 Phase 1 merge contract로 합쳐 destination ID/sequence를 유지한다. 수량을 지정한 partial unload는 지원하지 않는다.

## 발사와 전투 원자성

pure `rules.player_attack(..., shot_available=True)`의 기본값은 기존 legacy firearm 전투를 유지한다. native persistence 경계는 잠근 active Entity와 magazine의 실제 잔탄으로 shot_available을 전달한다. outcome의 `shot_fired`가 탄약 소비 기준이며 damage/hit/action 표시 문자열을 역해석하지 않는다.

firearm basic/shooting/suppress는 1발, melee basic/suppress·insight/heal/breathing/bandage는 0발이다. 실제 발사라면 미래 miss/zero damage도 1발을 소비하도록 계약을 분리했으며 live miss mechanic은 추가하지 않았다. 탄창 없음/0발의 발사 행동은 피해·발사 없이 기회만 소비하고, mental/cooldown commit 전에 반환한다. ammo 감소 실패는 profile·공유 enemy HP/위협·기여도를 포함한 기존 outer world_change 전체를 rollback한다. Defense V1·기술 성장·비용·적 수치는 유지한다.

## 정책·lock·외부 참조

equip/unequip은 root-only이며 load/unload도 조작하는 root의 명시적 policy다. give/drop/store/sell/burn/loot/consume은 tree-wide 보호를 유지한다. 사용자 load/unload는 operation=None을 쓰지 않는다. migration/bootstrap만 trusted bypass를 사용한다.

삽입 탄창이 있는 총기의 sell/burn은 변경 전에 구조적으로 거절한다. give/drop/store는 tree policy·transferable에 따라 상태를 보존한다. 잔탄 탄창 자체는 sell/burn 가능하며 rounds는 child ammo가 아니다. 실제 shop resale은 기존 magazine_resale(rounds, empty_resale, ammo_resale)의 empty+rounds×단가를 사용하고 소각은 잔탄까지 소멸시킨다.

공통 before/after_item_change는 source/destination/parent root Explorer들을 ID 순으로 잠근 뒤 관련 소유 Entity·트리·조상 UUID 집합을 정렬해 잠근다. inventory 광원도 포함한다. 같은 transaction에서 active weapon과 active light를 reconcile하며 실패하면 이동/삭제·참조·회복·순번·고유 범위가 rollback된다. split/merge도 owner→UUID 순서를 사용해 inventory 서비스와 lock 순서가 역전되지 않도록 한다. lock 전후 location/owner/parent 변경은 거절한다.

`update_item_state()`는 full_clean/save를 수행하는 중앙 mutation 경계다. 상위 domain은 권한·owner와 전체 결합 row lock·참조 처리를 먼저 확보한다. raw QuerySet.update로 state를 쓰지 않는다. ItemSequence의 기존 F update는 별도 발급기 계약으로 유지한다.

## Selector·Web·전리품 연결

sequence 기반 local numbering은 state가 바뀌거나 inventory↔equipment↔inside를 이동해도 후보가 남으면 유지한다. UUID/global integer는 사용자 표시·입력에 쓰지 않는다. 정규화는 공백·`.`·`-`·`_`를 무시하고 digit/mm는 보존한다. 5.56과556의 점 처리 충돌은 사용자의 명시적 답변에 따라 Decision Log를 따랐다. stable ID/display name/alias의 전역 충돌은 integrity가 검사한다. 탄창·탄약에는 권총표준/카빈표준/중량표준·권총탄/카빈탄/중량탄 등 한글 alias가 있다.

상태/장비/소지품/Web은 같은 equipment snapshot의 주무기 instance와 state summary를 사용한다. inside 탄창은 [장전]으로 표시하며 firearm은 loaded magazine/rounds, 탄창은 rounds/capacity를 표시한다. Web 버튼은 같은 서버 명령을 보내고 새 stateful 행만 줄바꿈한다.

Firearm tree의 corpse/world 이동·pickup·decay는 root LootClaim 권리로 보호되고 child magazine은 별도 claim/selector로 노출하지 않는다. 실물·화폐·storage·Credential·shop·소각·명시적 full-world migration은 현재 구현되어 있다. [전리품](loot-claims.md), [migration](item-migration.md)을 따른다.

Historical Phase 3의 순수/domain·격리 DB targeted·최소 Desktop/390px 검증과 실패/재검증 내역은 [playtest](playtest.md#phase-3-lighting--firearm-검증)와 [작업 상태](CODEX_TASK_STATE.md)에 기록한다. Chrome desktop/좁은 viewport·SQLite single-server의 1~4인 session·Canonical Legacy Migration Corpus와 사용자 수동 확인 Windows/Chrome OS IME는 [Phase 7B](phase7b-integration-validation.md)에서 검증했다. 대표 build balance와 fresh light/firearm gameplay·restart/relogin은 Phase 7C에서 검증했으며 [Phase 7 audit](phase7-final-integration-audit.md)을 따른다. 실제 mobile device matrix는 후속 검증이고 PostgreSQL 경쟁·multi-server는 별도 infrastructure다. 실제 플레이 DB migration 대상은 없다.

## Historical Phase 3 implementation boundary

아래 미연결·후속 구현 설명은 당시 범위다. 당시 targeted/browser 실행 사실은 [Phase 3 validation](phase3-validation.md)에 보존한다. 현재 검증 기준선은 [Phase 7 audit](phase7-final-integration-audit.md)을 따른다.

기존 캐릭터의 inventory/equipment/storage/light_sources와 Container·Corpse·DroppedLoot 저장은 Phase 6까지 legacy SSOT다. 기존의 명시적 `equipment_backend="item_entities"` 선택이 Lighting/Firearm backend도 결정한다. 빈 신규/fixture의 신뢰된 선택만 지원하고 사용자 명령이 backend를 바꾸지 않는다. lazy migration, 임시 Entity, fake UUID, profile과 Entity dual-write는 없다. profile version은 10이다.

기존 carbine/heavy_carbine에는 family metadata만 추가하며 ID·이름·공격력·가격은 유지한다. 정찰권총/전술권총/경비카빈/중량소총 등의 최종 V1 이름·수치·modifier·상품 적용은 Phase 6 콘텐츠 범위다. 이번 단계는 세 family 구조를 지원하고 pistol은 테스트 fixture로 검증한다. 탄창8종·탄약3종은 registry에 구조용 정의로 등록했으며 현재 상점·적 드롭·보상에 연결하지 않았다.

`create_firearm()`은 no_mag/empty/partial/full_standard 획득 형태를 제공한다. 표준 탄창 생성·rounds·inside 배치와 ItemSequence 발급을 같은 transaction에 묶는다. partial은 0<rounds<capacity를 요구한다. 실제 shop/quest/enemy drop/migration wiring은 없고 호출자가 content-defined 획득 형태를 선택한다.

삽입 탄창이 있는 총기의 sell/burn은 변경 전에 구조적으로 거절한다. give/drop/store는 허용 policy에 따라 tree를 그대로 이동한다. 잔탄 있는 탄창 자체의 sell/burn은 허용하며 rounds는 child ammo가 아니다. `magazine_resale(rounds, empty_resale, ammo_resale)`는 empty+rounds×ammo resale 계산만 제공한다. 실제 상점·소각 연결이나 가격 변경은 없다.

Phase 4는 firearm tree를 world_loot/corpse_loot에 그대로 운반하고 LootClaim을 별도 모델로 붙일 수 있다. rounds는 magazine state이고 loose ammo는 stack이므로 partial stack claim은 후속 claim contract로 연결한다. 기존 전리품·상자·drop/give/storage 사용자 경로 전체의 Entity cutover는 하지 않았다. legacy transfer는 기존 profile/Container/loot blob을 계속 사용하고 native 외부 이동은 공통 ItemEntity API에서 검증한다. 실제 claim·화폐 모델/상점/credential/소각·전체 migration·balance는 이번 단계에 없다.
