# 장비·Modifier·Defense V1

Phase 6 현재 상태: cutover 후 일반 gameplay는 native ItemEntity만 사용한다. 아래 legacy adapter/Phase 6 예정 설명은 Phase 1~5의 설계·검증 기록이며 maintenance migration과 historical audit fixture의 호환 경계로 남는다. 최신 저장·운영 정책은 [item-migration](item-migration.md), 최종 콘텐츠·가격은 [final-content](final-content.md)를 따른다.

## 계산과 저장 경계

`world.equipment_service`가 ItemEntity/Explorer Attribute를 조회하고, frozen `EquipmentItem`·`EquipmentSnapshot`을 제공한다. `world.equipment`, `world.modifiers`, `world.rules`, `world.progression`, `world.recovery`는 ORM·Evennia·네트워크를 import하지 않는다. `EquipmentProfile`은 한 작업에서 같은 snapshot을 사용하는 일시적인 dict context이며 저장할 때 일반 dict로 바꾼다. 현재 profile version은 13이며 [v13 NPC 대화 이전](command-shortcuts.md#프로필-v13의-npc-대화-이전)이 추가되었다. [v12 명령 어휘 이전](command-shortcuts.md#프로필-v12의-명령-어휘-이전)은 과거 명령 의미를 보존한다. [v11 줄임말 이전](command-shortcuts.md#프로필-v11과-구형-데이터)은 장비 저장 구조를 바꾸지 않는다. 장비 Phase 2 당시의 profile은 v10이었고 해당 단계에는 profile schema migration이 없었다. Phase 3의 ItemEntity magazine socket 제약 migration은 [영속 기반](item-entities.md)에 별도로 기록한다.

현재 장비 authority는 native ItemEntity의 equipment 위치다. `equipment_snapshot()`과 active weapon UUID를 stats/combat/recovery/presentation/Web이 함께 사용한다. Archive profile equipment는 gameplay에서 읽거나 쓰지 않는다. 새 Explorer는 native로 직접 생성하고 기존 DB는 explicit maintenance migration 후에만 시작한다. Legacy adapter는 historical fixture/audit용이며 사용자 backend 전환·자동 변환·dual-write는 없다.

## 슬롯과 손 조합

| slot | 표시 | capacity |
| --- | --- | --- |
| hands | 손 | 2 (손 사용량) |
| head / neck / body / gloves / waist / legs / feet | 머리 / 목 / 몸 / 장갑 / 허리 / 다리 / 발 | 각각 1 |
| ring | 반지 | 2 |
| accessory | 장신구 | 1 |

정의의 `equipment_properties`에는 slot을 기록한다. hands는 role=`weapon/shield/offhand`, hands_required=`1/2`가 필요하고 weapon은 weapon_type=`melee/firearm`와 0 이상의 weapon_attack을 가진다. shield/offhand는 1H다. 일반 슬롯의 개별 장비 수량은 1이다. 손이나 반지의 내부 위치 번호를 만들거나 표시하지 않는다.

단독 1H weapon/shield/offhand, 단독 2H weapon, weapon+weapon/shield/offhand를 허용한다. 2H+다른 손 장비, shield+shield, offhand+offhand, shield+offhand는 거절한다. 자동 교체는 없으며 사용자가 먼저 해제해야 한다. 정의 오류는 Phase 1 `definition_errors()`에 통합해 integrity 검사와 모델 저장에서 검사한다. 장비 위치의 정의 slot·capacity·손 조합은 모델 clean과 공통 서비스에서 검사한다.

`equip_item()`은 inventory root를 equipment/Explorer/정의 slot로, `unequip_item()`은 같은 Explorer의 inventory/slot=None으로 원자적으로 옮긴다. `move_item_tree()`를 사용하며 contained child의 inside/parent/socket/sequence를 유지한다. equip·unequip은 root policy만 검사하고 give/drop/store/sell/burn/loot/consume은 모든 후손도 검사한다. 사용자 명령은 operation=None을 사용하지 않는다.

## Selector와 주무기

inventory와 equipment root 및 그 inside 후손을 sequence 순으로 한 번 정렬한다. 같은 definition의 후보는 이름/이름 2처럼 표시하고 `world.targets`의 parse/matching/select를 재사용한다. 장착/삽입 위치가 바뀌어도 후보가 남아 있으면 번호는 유지된다. UUID와 큰 global sequence를 사용자에게 표시하지 않는다. 무장/착용/해제/벗어/주무기는 ItemEntity instance를 선택한다.

Entity 주무기는 `Explorer.db.active_weapon_item_id`에 UUID 문자열을 저장한다. 무기 하나/2H는 자동 선택하고 두 번째 1H는 기존 선택을 유지한다. `<무기> 주무기`로 바꿀 수 있다. 선택한 무기가 장비에서 사라지면 sequence가 가장 작은 남은 weapon으로 승계하고 없으면 None이다. inventory·다른 소유자·삭제된 UUID를 가리키는 stale 참조는 주무기로 인정하지 않는다. 읽기에서는 수리·쓰기하지 않고 domain 변경에서 reconcile한다.

### 공통 정보 조회와 Entity row 조회

| API | 반환과 사용 경계 |
| --- | --- |
| equipment_snapshot(character, profile=None) | backend-neutral EquipmentSnapshot. gameplay/domain은 이 snapshot을 사용한다. |
| active_weapon(character, profile=None) | 공통 snapshot의 active EquipmentItem 또는 None. weapon_type·hands_required·base attack 등 gameplay 정보 조회용이다. |
| hand_usage(character, profile=None) | 공통 snapshot의 손 사용량. legacy 1H도 1로 계산한다. |
| equipped_items(character) | ItemEntity 장비 row QuerySet. backend-neutral 장비 목록은 equipment_snapshot().items를 사용한다. |
| active_weapon_item(character) | ItemEntity backend의 실제 row 또는 None. legacy에는 대응 row가 없어 None이며 영속 작업 전용이다. 조회가 operation의 lock/권한 검증을 대신하지 않는다. |

Historical adapter는 legacy의 단일 weapon slot에 장착한 아이템을 명시적으로 active로 간주한다. 그 EquipmentItem.identity는 None이며 fake UUID·임시 Entity·profile 참조를 만들지 않는다. Entity snapshot의 active는 실제 선택 UUID로 구분한다. 기존 active_weapon()의 Entity row 반환은 리뷰 수정에서 active_weapon_item()으로 분리했으며 row가 필요한 호출은 새 helper를 사용한다. Phase 3은 equipment_snapshot().active 또는 공통 active_weapon()의 정보를 읽고 raw profile 장비를 다시 해석하지 않는다. 한 작업에서 이미 만든 snapshot은 그대로 전달해 사용한다.

상태와 장비 출력은 같은 formatting helper에서 stable selector에 `[주무기]`를 붙인다. 소지품·Web도 같은 snapshot의 selected instance를 표시하며 definition ID로 주무기를 결정하지 않는다.

ItemEntity create/move/delete의 `before_item_change`/`after_item_change`가 같은 world_change 안에서 장비·주무기 참조·자원을 정리한다. owner ID 오름차순 row lock으로 빈 슬롯 경쟁을 직렬화하고 관련 소유 아이템과 이동 트리/조상을 한 집합에 모아 UUID 정렬 lock을 얻는다. 조회와 lock 사이의 위치·소유자·parent 변경은 거절한다. move_item_tree의 선택적 expected_source는 사용자 장비 서비스가 기대하는 출발 위치·소유자를 잠근 row와 대조한다. reconcile 실패면 이동/삭제·참조·자원·회복·순번·unique scope도 rollback된다. 신규 사용자 기능은 이 API를 사용해야 하며 raw QuerySet update/delete로 domain 검증과 참조 정리를 우회하지 않는다. Phase 3은 이 경계에 inventory active light 참조 정리를 연결했다.

Phase 3 firearm은 기존 equipment root이고 삽입 탄창은 inside child다. equip/unequip에서 child의 parent/socket/state/sequence를 보존하고 child의 equip/unequip permission을 요구하지 않는다. EquipmentItem의 firearm_family/state_summary는 표시·domain 정보이며 잔탄을 별도로 저장하지 않는다. active_weapon() 정보 조회와 active_weapon_item() row 조회 경계를 유지한다. 상세 reload·발사·광원 계약은 [광원·총기](lighting-firearms.md)를 따른다.

## Modifier와 자원

modifier는 `{target, op, value, scope}`의 numeric metadata다. op는 add/multiply, scope는 equipped/active_weapon이며 유한한 숫자만 허용하고 multiply는 0 이상이다. 계산은 base+모든 add 합산 후 multiply를 각각 곱하고 target별 clamp한다. `+4%`는 multiply 1.04, `+3%p`는 add .03이다. UI 문자열을 계산 입력으로 해석하지 않는다.

초기 target 15개는 `weapon.attack`, `stat.attack/defense/max_hp/max_mental`, `recovery.hp_per_minute/mental_per_minute`, `skill.heavy.damage`, `skill.shooting.damage/penetration`, `skill.insight.penetration/damage`, `skill.suppress.reduction`, `skill.heal.amount`, `skill.breathing.amount`다. 관통·견제 감소율은 0~1, 최대 자원은 최소 1, 나머지는 최소 0으로 clamp한다. 최대 자원과 회복량은 기존 정수 자원 경계에서 내림한다.

character_attack은 레벨 base+힘 보정에 stat.attack modifier를 적용한 값이다. 여기에 active weapon의 base weapon_attack과 weapon.attack modifier 결과만 더한다. secondary의 base attack은 합산하지 않지만 scope=equipped passive는 적용한다. 기존 기술 Rank 공식 결과에 modifier를 적용한다. heavy/shooting은 기존 배율로 구한 피해, insight.damage는 기존 간파 피해 계수(1+bonus), penetration/reduction은 기존 비율, heal/breathing은 기존 회복량을 base로 사용한다. 공격 passive·간파 계수는 기존처럼 최종 물리 피해에 곱하고 견제의 기존 source/Rank/전체 cap·소비 규칙을 유지한다.

장비 변경은 옛 snapshot으로 회복 구간을 accrue/commit한 뒤 위치·주무기를 바꾸고 새 snapshot으로 max/rate를 계산한다. max 증가로 current HP/mental을 늘리지 않고 감소 시 새 max로 clamp한다. 옛 시간 구간에 새 recovery bonus를 소급 적용하지 않는다. 레벨업의 기존 max 증가분 지급은 장비 증가와 구분한다. 장비 명령은 prompt의 사전 회복 저장을 생략하고 자신의 transaction에서 정산해 실패 시 회복도 원래 상태를 유지한다.

Historical Phase 2 adapter mapping은 한 곳에 모았다. 현재 final definition 변환은 content/item_mapping.py를 따른다. 당시 mapping은 weapon→hands/weapon, armor→body이며 machete/blade/jungle_blade는 1H melee, spear는 2H melee, carbine/heavy_carbine은 2H firearm이다. 기존 weapon attack은 weapon base, 비무기 attack은 stat.attack add, defense는 stat.defense add, recovery_bonus는 recovery target add로 연결한다. ID·이름·수치를 바꾸지 않는다.

## Defense V1

`rules.apply_defense(raw_damage, defense, penetration, defense_skill_reduction)`를 플레이어→적과 적→플레이어에서 공통으로 사용한다.

```text
effective_defense = defense * (1 - penetration)
damage_after_defense = raw_damage * 20 / (20 + effective_defense)
final_damage = damage_after_defense * (1 - defense_skill_reduction)
```

강공격·견제·공격 기술 계수는 raw_damage에 먼저 적용한다. helper에서 모든 float 계산 뒤 한 번 int로 버림하고 최소 1을 적용한다. 한쪽 경로만 flat subtraction을 남기거나 강공격 전후에 중간 정수 변환을 하지 않는다. Defense 계산과 성장 공식은 유지하며 현재 적·장비·보상 확정값은 [final-content](final-content.md)를 따른다.

## 검증과 legacy compatibility 경계

Archive inventory/equipment/storage/light_sources·Container items·loot blob은 보존 가능하지만 정상 gameplay는 native service만 사용한다. 명시적 legacy upgrade와 marker/integrity 검증은 [item-migration](item-migration.md)을 따른다.

`world.test_equipment_engine`은 순수 계산/metadata/기술/양방향 Defense, `tests.test_equipment_entities`는 슬롯/손/UUID 주무기/중복 selector/nested 이동/회복 경계/실패 원자성/단일 쓰기/Web payload를 검사한다. Phase 1 invariant는 `tests.test_item_entities`로 보호한다. 실제 실행 명령·개수·실패와 재검증·미실행 범위는 [작업 상태](CODEX_TASK_STATE.md)에 구분한다. PostgreSQL 실제 경쟁과 multi-server concurrency는 아직 검증하지 않았다.

## Historical Phase 2 backend boundary

아래 문단은 Phase 2 당시의 범위다. 현재 장비 authority와 legacy no-fallback 정책은 위 현재 계약을 따른다.

현재 플레이어는 `profile["equipment"]`가 runtime SSOT다. 단일 `equipment_legacy` adapter가 legacy 정의와 장비를 같은 snapshot으로 변환한다. 빈 신규/테스트 캐릭터에만 신뢰된 `use_item_entities()`로 `equipment_backend="item_entities"`를 명시적으로 지정할 수 있다. 사용자 명령이 이 설정을 바꾸거나 데이터를 자동 변환하지 않는다. 한 명령은 선택한 저장소 한 곳만 갱신하며 profile 장비와 ItemEntity에 dual-write하지 않는다. 기존 캐릭터 전체 변환과 runtime cutover는 Phase 6이다.

legacy inventory/equipment/storage, Container.db.items, Corpse/DroppedLoot blob, light_sources는 유지한다. legacy inventory 이전·판매의 장착 복사본 예약을 위해 `rules.sell`, `world.item_transfers.transfer`, `Container.perform_action`의 장비 direct-read는 의도적으로 남는다. combat·stats·recovery·presentation·Web는 adapter/snapshot을 사용한다. Phase 6에서 전체 변환 검증과 runtime SSOT cutover 뒤 legacy adapter·backend 선택·장착 복사본 예약 경계를 제거한다.
