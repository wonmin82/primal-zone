# ItemEntity 기반 1단계

이번 단계는 기존 수량 딕셔너리를 이후 단계에서 대체할 영속 domain을 추가한다. 새 아이템 row의 SSOT는 `world.item_entities.models.ItemEntity`다. 기존 게임 명령·전투·상점·광원·전리품은 아직 기존 profile/Attribute를 사용하며 새 row와 자동 동기화하지 않는다. profile version은 10이다.

## 정의와 모델

정적 정의는 기존 `world.content.ITEMS`에 유지한다. `stackable`, `max_stack`, `unique_per_owner`, `operation_policy`, `item_type`을 추가하며 가격·기존 ID·표시명·전투 수치를 바꾸지 않는다. 무기·방어구·상태형 도구는 비스택, 일반 소비품·재료는 스택이다. 현재 모든 정의의 `max_stack`은 None이다. 기존 `transferable`에서 이동 policy를 파생해 현재 명령과의 호환성을 유지한다. 후속 단계에서 실제 명령을 새 domain으로 전환할 때 해당 필드도 정리한다.

`ItemEntity`는 UUID PK, definition_id, quantity, location_kind, owner_object, parent_item, slot, socket, JSON state, sequence, nullable unique_scope_key를 저장한다. `definition_id`는 DB FK가 아니라 registry key다. 소유 위치·정의별 순번과 부모/socket에 index를 둔다.

| 위치 | owner_object | parent_item | slot | socket |
| --- | --- | --- | --- | --- |
| inventory | Explorer | 없음 | 없음 | 없음 |
| equipment | Explorer | 없음 | 비어 있지 않은 값 | 없음 |
| personal_storage | Explorer | 없음 | 없음 | 없음 |
| shared_storage | 공용 Container | 없음 | 없음 | 없음 |
| world_loot | DroppedLoot | 없음 | 없음 | 없음 |
| corpse_loot | Corpse | 없음 | 없음 | 없음 |
| inside | 없음 | ItemEntity | 없음 | 비어 있지 않은 값 |

DB CheckConstraint는 위 필드 조합, quantity≥1, sequence≥1, 자기 자신을 parent로 참조하지 않는 조건을 강제한다. sequence와 non-null unique_scope_key는 DB unique다. owner와 parent FK는 PROTECT로 연결한다. 내부 아이템이나 소유 물품이 남은 부모/Evennia Object를 암묵적으로 삭제할 수 없다.

Object type, 정의 존재·metadata, 비스택 quantity=1, max_stack, JSON 객체 state, 다단계 부모 순환, 생성 후 정의·순번 불변은 application validation에서 검사한다. 정적 registry를 SQL constraint에 복제하지 않는다. `save()`는 full_clean을 수행하고 Django의 필드 변환 전에 수량의 실제 정수 여부를 확인한다. QuerySet.update/bulk_create와 raw SQL은 이 검증을 우회하므로 게임 서비스의 쓰기는 아래 API를 사용한다.

## API

`world.item_entities.api`가 다음 연산을 제공한다. 변경 함수의 item/parent 인자는 저장된 ItemEntity 또는 UUID를 받는다. owner_object는 영속 Evennia Object다.

| API | 동작 |
| --- | --- |
| create_item(definition_id, location_kind=..., ...) | 검증 후 새 row·순번 생성 |
| move_item(item, location_kind=..., ...) | 자식 없는 단일 물품의 위치 변경 |
| move_item_tree(item, location_kind=..., ...) | 루트 이동, 내부 위치 유지, 모든 후손의 고유 소유 범위 갱신 |
| split_stack(item, quantity) | 0보다 크고 현재 수량보다 작은 수량을 새 row로 분리 |
| merge_stack(source, destination) | 호환 스택 합산 후 source 삭제, destination ID·sequence 유지 |
| delete_item(item, operation=None) | 단일 row 삭제, 자식이 남아 있으면 PROTECT |
| items_owned_by(owner_object) | 직접 소유 물품과 inside 후손을 sequence 순으로 조회 |
| items_in_location(location_kind, owner_object=..., parent_item=...) | 정확한 canonical 위치를 sequence 순으로 조회 |
| children_of(item) | 바로 아래 자식을 sequence 순으로 조회 |

생성·이동 시 location 필드를 모두 명시적으로 구성한다. 이동에서 생략한 owner/parent/slot/socket은 None으로 지우므로 이전 위치의 값이 남지 않는다. query는 UUID를 번호 정렬에 사용하지 않는다. 기존 `world.targets` selector parsing은 변경하지 않았으며 후속 명령 연결에서 해당 공통 문법과 새 sequence 순서를 함께 사용한다.

스택 병합은 동일 정의·canonical 위치·전체 state와 max_stack을 요구하고 자식 있는 스택은 거절한다. 분할 source 순번은 유지되고 새 row만 새 순번을 얻는다. `same_merge_context()`가 향후 LootClaim의 일치 여부도 검사할 확장 경계다. 현재는 LootClaim 모델·전리품 회수 동작을 추가하지 않는다.

`world.item_entities.policy.can_item_operation(item_or_definition_id, operation)`은 중앙 policy API다. 알 수 없는 행동과 정의는 False다. move/delete의 operation을 명시하면 policy를 검사하고, 트리 이동에서는 내부 물품도 검사한다. operation=None은 신뢰하는 내부 배치·migration용이며 사용자 명령의 권한 우회 수단으로 사용하지 않는다. 실제 명령 서비스가 같은 방·지각·전투·전리품 권리 등을 검증한 뒤 적절한 operation을 전달해야 한다.

## 순번·트랜잭션·고유 범위

`ItemSequence`는 migration에서 만드는 id=1 발급기다. transaction 안에서 F update로 증가한 뒤 발급 값을 읽는다. 삭제된 아이템의 순번은 재사용하지 않으며, rollback으로 저장되지 않은 발급은 같이 취소된다. 전역 순번은 성공적으로 생성된 모든 Entity에 걸쳐 증가한다.

변경 API는 기존 `world_change()`에 통합한다. 다중 lock은 대상 ID를 먼저 모아 중복 제거·정렬한 뒤 그 순서로 select_for_update를 수행한다. 트리 이동은 루트·후손·목적지의 조상도 수집한다. UUID 정렬은 lock 순서에만 사용한다. SQLite에서는 select_for_update가 별도 row lock을 제공하지 않으므로 현재 단일 Evennia 서버의 RLock·atomic 경계를 유지한다. 다중 게임 서버 운영과 PostgreSQL 동시 요청은 이번 검증 범위가 아니다.

`unique_per_owner`의 key는 `<실제 root owner ID>:<definition ID>`다. 개인 보관·장착·inside도 같은 소유자로 계산하며 이동 시 트리 전체 key를 같은 transaction에서 갱신한다. 중복 충돌 시 루트 이동을 포함한 변경 전체를 rollback한다. 일반 아이템의 key는 None이어서 중복 소유를 허용한다. Credential 콘텐츠나 지급은 후속 단계다.

새 모델은 Django 일반 모델이므로 실패한 transaction에서 얻었던 Entity 인스턴스는 다시 조회한다. API는 전달된 객체의 stale 필드를 신뢰하지 않고 ID로 잠근 row를 읽는다. 기존 Evennia profile·Attribute·location 캐시와 after_change callback의 rollback은 기존 world_change를 사용한다.

## Migration과 후속 단계

앱은 `world.item_entities.apps.ItemEntitiesConfig`다. `0001_initial`은 Evennia objects migration에 의존하는 두 테이블·constraint·index를 만들고 `0002_initialize_sequence`는 get_or_create로 발급기를 준비한다. 반복 초기화는 이미 사용한 순번을 초기화하지 않는다. 이번 개발에서는 테스트 DB에만 migration을 적용했으며 플레이 DB를 변경하지 않았다.

이 코드를 실행 환경에 반영할 때 정상 DB 백업·운영 절차에 따라 game에서 migration을 적용한 후 새 Entity API를 사용한다.

```powershell
..\.venv\Scripts\python.exe -m evennia migrate --noinput
```

이번 migration은 profile·공용 상자·시체·바닥 물품을 읽거나 옮기지 않는다. 따라서 기존 명령이 새 테이블에 쓰지 않고, 이중 쓰기도 없다. 후속 단계에서는 범위별 legacy migration·검증·cutover를 같은 transaction에서 구현하고 영구적인 두 SSOT를 만들지 않는다. 장비 슬롯 수용량·주무기/활성 광원 참조·총기·LootClaim·CurrencyLoot·Credential·상점·콘텐츠·밸런스는 각 후속 단계에서 연결한다.

## 검증 범위

핵심 검사는 `tests.test_item_entities`, 정의 검사는 `world.test_item_definitions`다. 생성·DB location 제약·비스택/최대 수량·split/merge·순번·트리 순환/이동/PROTECT·profile/cache/callback rollback·정렬 lock·개인 보관 owner·DB 고유 키·nested 고유 범위·발급기 반복 초기화를 검사한다. 직접 영향받는 기존 `tests.test_item_interactions`, `tests.test_loot`와 정의/이동 순수 규칙 검사를 함께 실행한다. 실제 결과는 [작업 상태](CODEX_TASK_STATE.md)에 기록한다.

단계별 계획에 따라 전체 suite·smoke-full·Web/browser 전체 회귀·다인 전체 시나리오·전체 저장 변환·balance simulation은 7단계에서 수행한다. 이번 단계에서 gameplay cutover·정적 파일 변경이 없어 서버/브라우저 검사를 실행하지 않는다.
