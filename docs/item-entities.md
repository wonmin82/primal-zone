# ItemEntity 기반·장비·상태형 아이템

새 아이템 row의 SSOT는 `world.item_entities.models.ItemEntity`다. Phase 2 장비와 Phase 3 광원·총기 서비스는 명시적으로 선택한 ItemEntity 또는 legacy 저장소를 공통 snapshot으로 계산한다. 기존 캐릭터의 runtime SSOT는 legacy profile이며 상점·전리품·전체 저장 전환은 후속 단계다. 새 row와 자동 동기화하거나 dual-write하지 않는다. 상세 계약은 [장비·Modifier·Defense V1](equipment.md)과 [광원·총기](lighting-firearms.md)를 따른다. profile version은 10이다.

## 정의와 모델

정적 정의는 기존 `world.content.ITEMS`에 유지한다. `stackable`, `max_stack`, `unique_per_owner`, `operation_policy`, `item_type`을 추가하며 가격·기존 ID·표시명·전투 수치를 바꾸지 않는다. 무기·방어구·상태형 도구는 비스택, 일반 소비품·재료는 스택이다. 현재 모든 정의의 `max_stack`은 None이다. 기존 `transferable`에서 이동 policy를 파생해 현재 명령과의 호환성을 유지한다. 후속 단계에서 실제 명령을 새 domain으로 전환할 때 해당 필드도 정리한다.

`ItemEntity`는 UUID PK, definition_id, quantity, location_kind, owner_object, parent_item, slot, socket, JSON state, sequence, nullable unique_scope_key를 저장한다. `definition_id`는 DB FK가 아니라 registry key다. 소유 위치·정의별 순번과 부모/socket에 index를 둔다.

| 위치 | owner_object | parent_item | slot | socket |
| --- | --- | --- | --- | --- |
| inventory | Explorer | 없음 | 없음 | 없음 |
| equipment | Explorer | 없음 | 정의의 최종 장비 slot | 없음 |
| personal_storage | Explorer | 없음 | 없음 | 없음 |
| shared_storage | 공용 Container | 없음 | 없음 | 없음 |
| world_loot | DroppedLoot | 없음 | 없음 | 없음 |
| corpse_loot | Corpse | 없음 | 없음 | 없음 |
| inside | 없음 | ItemEntity | 없음 | 비어 있지 않은 값 |

DB CheckConstraint는 위 필드 조합, quantity≥1, sequence≥1, 자기 자신을 parent로 참조하지 않는 조건을 강제한다. sequence와 non-null unique_scope_key는 DB unique다. owner와 parent FK는 PROTECT로 연결한다. 내부 아이템이나 소유 물품이 남은 부모/Evennia Object를 암묵적으로 삭제할 수 없다.

Object type, 정의 존재·metadata, 비스택 quantity=1, max_stack, JSON 객체 state, 다단계 부모 순환, 생성 후 정의·순번 불변은 application validation에서 검사한다. 정적 registry를 SQL constraint에 복제하지 않는다. `save()`는 full_clean을 수행하고 Django의 필드 변환 전에 수량의 실제 정수 여부를 확인한다. QuerySet.update/bulk_create와 raw SQL은 이 검증을 우회하므로 게임 서비스의 쓰기는 아래 API를 사용한다.

## API

Phase 4 실물 권리는 별도 `LootClaim`이며 ItemEntity.state가 아니다. corpse_loot/world_loot root에만 연결하고 inside child는 root 권리를 따른다. claim이 남은 inventory/equipment/storage 이동은 save validation으로 거절한다. 전체 pickup은 claim 제거 후 같은 Entity 이동, 부분 pickup은 source claim 유지와 claim 없는 split destination 이동/merge다. `same_merge_context()`는 merge_state와 root 배정 단위·권리의 ClaimContext를 함께 비교한다. 다른 claim/allocation unit은 권리 필드가 같아도 병합하지 않는다. generic split은 claim을 자동 복사하지 않는다. 자세한 API·expiry/decay·화폐 모델은 [전리품 권리](loot-claims.md)를 따른다.

`world.item_entities.api`가 다음 연산을 제공한다. 변경 함수의 item/parent 인자는 저장된 ItemEntity 또는 UUID를 받는다. owner_object는 영속 Evennia Object다.

| API | 동작 |
| --- | --- |
| create_item(definition_id, location_kind=..., ...) | 검증 후 새 row·순번 생성 |
| move_item(item, location_kind=..., ...) | 자식 없는 단일 물품의 위치 변경 |
| move_item_tree(item, location_kind=..., ...) | 루트 이동, 내부 위치 유지, 모든 후손의 고유 소유 범위 갱신 |
| split_stack(item, quantity) | 0보다 크고 현재 수량보다 작은 수량을 새 row로 분리 |
| merge_stack(source, destination) | 호환 스택 합산 후 source 삭제, destination ID·sequence 유지 |
| delete_item(item, operation=None) | 단일 row 삭제, 자식이 남아 있으면 PROTECT |
| update_item_state(item, state) | 상위 서비스가 권한·결합 lock을 확보한 뒤 full_clean/save로 상태 변경 |
| items_owned_by(owner_object) | 직접 소유 물품과 inside 후손을 sequence 순으로 조회 |
| items_in_location(location_kind, owner_object=..., parent_item=...) | 정확한 canonical 위치를 sequence 순으로 조회 |
| children_of(item) | 바로 아래 자식을 sequence 순으로 조회 |

생성·이동 시 location 필드를 모두 명시적으로 구성한다. 이동에서 생략한 owner/parent/slot/socket은 None으로 지우므로 이전 위치의 값이 남지 않는다. query는 UUID를 번호 정렬에 사용하지 않는다. Phase 2는 기존 `world.targets` parsing/matching/select를 재사용하며 inventory/equipment 후보의 sequence 순서로 instance selector를 만든다.

스택 병합은 동일 정의·canonical 위치·merge 관련 상태와 max_stack을 요구하고 자식 있는 스택은 거절한다. `same_merge_context()`는 raw JSON을 직접 비교하지 않고 `merge_state(item)` 계약의 결과를 비교한다. 현재 기본 계약은 전체 state의 복사본이므로 기존과 같이 모든 state 값이 같아야 한다. 향후 정의별 계약에서 provenance·UI/debug·migration metadata 등 병합과 무관한 값을 제외할 수 있으며, 이번 단계에는 새 state schema나 정의별 선택 규칙을 추가하지 않는다. destination의 ID·sequence·state는 유지하고 수량만 합산한다. 분할 source 순번은 유지되고 새 row만 새 순번을 얻는다.

Phase 4는 `same_merge_context()`에서 merge 상태와 별도로 ClaimContext의 root 배정 단위와 권리를 비교한다. 같은 아이템 유형·merge 관련 상태여도 다른 LootClaim/allocation unit이면 병합할 수 없다. 별도 loot_entities app의 모델과 loot_service가 회수·부분 회수·만료·decay를 처리한다.

`world.item_entities.policy.can_item_operation(item_or_definition_id, operation)`은 중앙 policy API다. 정의에 허용되지 않은 행동과 알 수 없는 정의는 False다. move/delete의 operation을 명시하면 해당 아이템의 policy를 검사한다. 이동 API는 중앙 `TREE_OPERATION_SCOPES`에 트리 적용 범위까지 정의된 행동만 허용하며, 범위가 없는 행동은 fail-closed로 거절한다.

operation은 호출자가 직접 조작하는 root의 행동이다. contained child는 root를 따라 수동적으로 이동하며 `inside`·같은 parent·socket을 유지한다. root의 장착은 child 자체의 장착과 다르므로 child의 `equip=false`를 허용한다. 이전·처분에서는 내부 물품의 보호도 유지한다. `_check_tree_operation()`은 모든 policy 검사를 row 변경 전에 수행한다.

| operation | policy 검사 범위 | 의미 |
| --- | --- | --- |
| equip, unequip | root만 | root를 장착/해제하고 내부 물품은 따라 이동한다. child에 equip/unequip 허용을 요구하지 않는다. |
| load, unload | root만 | 탄창 삽입/분리 또는 탄약 처리의 직접 조작 물품을 검사한다. 상위 서비스가 호환성·소유권·전투 제한을 검증한다. |
| give, drop, store | root와 모든 descendants | 소유권·바닥/보관 위치 이전에서 내부 물품의 이동 제한도 유지한다. |
| sell, burn, consume | root와 모든 descendants | 처분·소비를 통한 내부 물품 보호 우회를 막는다. 실제 판매·소각·소비 기능이나 재귀 삭제는 이번 단계에서 구현하지 않는다. |
| loot | root와 모든 descendants | 획득으로 소유권을 이전할 때 내부 물품의 policy도 검사한다. 실제 LootClaim 권한은 loot_service에서 lock 후 검증한다. |

`operation=None`은 migration/bootstrap 등 신뢰된 내부 작업의 policy 생략용이다. canonical 위치·순환·고유 범위·트랜잭션 검증은 그대로 적용된다. 사용자 action에서 거절을 피하는 일반 해법으로 사용하지 않는다. 실제 명령 서비스가 같은 방·지각·전투·전리품 권리·소유자 등 권한과 목적지를 검증한 뒤 정확한 operation을 전달해야 한다. 이 표는 policy 적용 범위다. Phase 2의 실제 장비/해제 명령도 동일한 root contract를 사용한다.

## 순번·트랜잭션·고유 범위

`ItemSequence`는 migration에서 만드는 id=1 발급기다. transaction 안에서 F update로 증가한 뒤 발급 값을 읽는다. 삭제된 아이템의 순번은 재사용하지 않으며, rollback으로 저장되지 않은 발급은 같이 취소된다. 전역 순번은 성공적으로 생성된 모든 Entity에 걸쳐 증가한다.

변경 API는 기존 `world_change()`에 통합한다. 다중 lock은 대상 ID를 먼저 모아 중복 제거·정렬한 뒤 그 순서로 select_for_update를 수행한다. 트리 이동은 루트·후손·목적지의 조상도 수집한다. UUID 정렬은 lock 순서에만 사용한다. SQLite에서는 select_for_update가 별도 row lock을 제공하지 않으므로 현재 단일 Evennia 서버의 RLock·atomic 경계를 유지한다. 다중 게임 서버 운영과 PostgreSQL 동시 요청은 이번 검증 범위가 아니다.

`unique_per_owner`의 key는 `<실제 root owner ID>:<definition ID>`다. 개인 보관·장착·inside도 같은 소유자로 계산하며 이동 시 트리 전체 key를 같은 transaction에서 갱신한다. 중복 충돌 시 루트 이동을 포함한 변경 전체를 rollback한다. 일반 아이템의 key는 None이어서 중복 소유를 허용한다. Credential 콘텐츠나 지급은 후속 단계다.

새 모델은 Django 일반 모델이므로 실패한 transaction에서 얻었던 Entity 인스턴스는 다시 조회한다. API는 전달된 객체의 stale 필드를 신뢰하지 않고 ID로 잠근 row를 읽는다. 기존 Evennia profile·Attribute·location 캐시와 after_change callback의 rollback은 기존 world_change를 사용한다.

## Migration과 후속 단계

앱은 `world.item_entities.apps.ItemEntitiesConfig`다. `0001_initial`은 Evennia objects migration에 의존하는 두 테이블·constraint·index를 만들고 `0002_initialize_sequence`는 get_or_create로 발급기를 준비한다. 반복 초기화는 이미 사용한 순번을 초기화하지 않는다. Phase 3의 `0003_magazine_socket`은 socket="magazine"인 parent/socket에만 조건부 unique를 추가한다. generic 다른 socket은 제한하지 않는다. 이번 개발에서는 격리 테스트 DB에만 migration을 적용했으며 플레이 DB를 변경하지 않았다.

이 코드를 실행 환경에 반영할 때 정상 DB 백업·운영 절차에 따라 game에서 migration을 적용한 후 새 Entity API를 사용한다.

```powershell
..\.venv\Scripts\python.exe -m evennia migrate --noinput
```

ItemEntity migration과 Phase 4 loot_entities schema는 profile·공용 상자·기존 시체·바닥 물품을 읽거나 옮기지 않는다. 기존 캐릭터는 legacy에만 쓰고, 명시적으로 Entity backend를 선택한 빈 신규/fixture 캐릭터의 장비·광원·총기와 native 전리품은 새 모델에만 쓴다. 이중 쓰기는 없다. Phase 6에서 범위별 legacy migration·검증·cutover를 구현한다. Phase 2 장비·modifier·Defense, Phase 3 활성 광원·총기/탄창, Phase 4 LootClaim·CurrencyLoot를 연결했다. Credential·신규 상점·최종 콘텐츠·밸런스는 후속 단계다.

## 검증 범위

핵심 검사는 `tests.test_item_entities`, 정의 검사는 `world.test_item_definitions`다. 생성·DB location 제약·비스택/최대 수량·split/merge·순번·트리 순환/이동/PROTECT·profile/cache/callback rollback·정렬 lock·개인 보관 owner·DB 고유 키·nested 고유 범위·발급기 반복 초기화를 검사한다. 테스트 전용 비스택 root/child로 장착 시 내부 socket 보존을 재현하며 Phase 3에서는 실제 family/탄창 metadata fixture를 사용한다. tree-wide 행동의 descendant 거절 시 모든 row·고유 범위·순번 발급기 불변, unknown operation 거절·None 내부 작업, 전체 state 기본 비교와 merge 관련 상태 계약도 검사한다. 기존 `tests.test_item_interactions`, `tests.test_loot`와 정의/이동 순수 규칙 검사는 직접 영향 범위에 따라 선택한다. 실제 실행과 과거 결과는 [작업 상태](CODEX_TASK_STATE.md)에 구분해 기록한다.

## Phase 3 상태·중첩·참조 확장

손전등은 power_type/remaining_power(초)/enabled/started_at, 탄창은 rounds를 state에 저장한다. default_state와 모델 validation이 구조·범위를 검사하며 총기 rounds/ammo_count 중복 저장을 거절한다. inside/socket=magazine은 firearm parent와 compatible magazine child만 허용한다. state mutation은 update_item_state를 사용하고 서비스에서 owner→전체 UUID lock을 확보한다. 정상 광원 관찰은 projection만 사용하며 OFF·소진·외부 이동·logout/shutdown에 저장한다.

before/after_item_change는 equipment뿐 아니라 inventory source/destination/parent root 소유자도 잠그고 active weapon/light를 같은 transaction에서 reconcile한다. split/merge도 owner→UUID 순서를 유지한다. 조회와 lock 사이 parent 변경도 거절하며 stale 입력은 ID로 최신 row를 확인한다. loaded firearm의 sell/burn은 row 변경 전에 구조적으로 거절하고 loaded magazine 자체의 sell/burn은 definition policy를 따른다. 일반 tree 이전은 내부 magazine state와 sequence를 보존한다. 중앙 merge_state·claim 확장 지점과 UUID/sequence/PROTECT/unique_scope 발급 계약은 유지한다.

전체 suite·Web/browser 전체 회귀·다인 전체 시나리오·전체 저장 변환·balance simulation의 종합 matrix는 7단계 범위다. Phase 1 구현/리뷰에서는 로컬 Full을 생략했지만, Phase 2 리뷰의 명시적 요청으로 수정한 closeout를 포함한 smoke-full을 실제438.541초에 통과했다. 이 단일 Full 시나리오가 Phase 7 전체 검증을 대신하지 않는다. 기존 GitHub workflow의 자동 전체 suite·Quick smoke는 그대로 실행하며 로컬 targeted 결과와 구분한다. Phase 1 마감·Phase 2 구현/리뷰·문서 마감의 실행 결과는 작업 상태에서 구분한다. 최신 HEAD와 병합된 main의 CI는 각각 해당 SHA로 확인한다. 실제 PostgreSQL row-lock 경쟁과 다중 서버 동시성은 아직 검증하지 않았다. 상세 회귀 절차는 [Phase 1 테스트 안내](playtest.md#pr-29-리뷰-수정의-검증-기준)와 [Phase 2 리뷰 테스트 안내](playtest.md#pr-30-phase-2-리뷰의-검증-기준)를 따른다.

## Phase 2 연결

최종 장비 slot·capacity·손 조합은 모델 clean과 서비스에서 검증한다. equipment root의 create/move/delete는 owner lock과 기존 UUID 정렬 lock을 사용하고 같은 world_change 안에서 주무기 참조와 max/rate/회복을 reconcile한다. 실패 시 전체 변경을 rollback한다. raw QuerySet 쓰기는 사용자 domain 경로가 아니며 참조 정리를 우회해 사용하지 않는다. UUID·sequence·canonical 위치 DB constraint·parent/owner PROTECT·nested unique scope·split/merge·merge_state 계약과 ItemSequence migration은 변경하지 않았다. equipment에 임의 main_hand/비장비 정의를 넣는 Phase 1 fixture는 최종 hands/장비 정의로 갱신했다.
