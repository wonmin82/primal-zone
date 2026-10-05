# 전리품 권리와 보급칩 영속 구조

Phase 4는 기존 ItemEntity·장비·광원·총기를 유지하며 권리와 화폐를 분리한다. 실제 검증은 [playtest](playtest.md#phase-4-lootclaim--currencyloot-검증), 인계는 [CODEX_TASK_STATE](CODEX_TASK_STATE.md)를 따른다. Phase 5 콘텐츠와 Phase 6 월드 변환은 수행하지 않는다.

## legacy entry 의미와 모델 대응

| legacy 필드 | 기존 의미 | native 대응 |
| --- | --- | --- |
| kind | 실물 또는 보급칩 | ItemEntity 또는 CurrencyLoot |
| id | 아이템 정의 또는 credits | definition_id 또는 화폐 domain ID |
| quantity | 잔여 수량 | ItemEntity/CurrencyLoot.quantity |
| reserved_party | 보호 중 요청 가능한 파티 | LootClaim/CurrencyLoot.reserved_party |
| reserved_player | 개인 보호권 | LootClaim/CurrencyLoot.reserved_player |
| assigned_player | 실물 순번의 실제 지급 대상 | LootClaim.assigned_player |
| protection_until | now가 기한 이상이면 자유 획득 | 모델의 동일 timestamp |
| eligible_players | 자기 몫과 무관한 원래 화폐 참여 자격 | 모든 share player, 0인 행 포함 |
| remaining_shares | 아직 지급할 양과 부분 분배 weight | 양수 remaining_amount |

기존 `build_entries()`의 기여 비중·round_robin_cursor, `recipient_for_item()`/`can_take_entry()`/`currency_payouts()`를 재사용한다. 실물 stack entry 하나는 배정 단위 하나이며 파티 인원수대로 자동 분할하지 않는다. XP는 기존 처치 보상으로 즉시 지급하고 전리품 row를 만들지 않는다.

## 모델과 deletion safety

별도 Django app `world.loot_entities`의 `0001_initial`은 schema만 만든다. data migration은 없다.

- `LootClaim`: ItemEntity OneToOne, reserved_party/player, assigned_player, protection_until. DB의 실제 root가 corpse_loot/world_loot일 때만 허용한다. state에 권리를 복제하지 않는다. inventory/equipment/storage/inside에는 claim을 남길 수 없다.
- `CurrencyLoot`: Corpse/DroppedLoot owner, 양의 정수 quantity, reserved_party/player, protection_until. 보급칩은 ItemEntity가 아니다. 출처 내 생성 PK 순서를 사용하며 사용자에게 PK를 표시하지 않는다.
- `CurrencyLootShare`: currency_loot/player unique, 정수 remaining_amount≥0. 잔여 지분 합≤quantity를 검사하고 보호 상태 생성 시 합=quantity를 요구한다. eligible_players 저장 필드는 없다.

실물·공간 owner·탐사자·share parent는 PROTECT이며 domain에서 관계를 먼저 정리한다. reserved_party만 SET_NULL이다. 기존 Party는 마지막 멤버 탈퇴로 삭제되므로 파티 참조만 비우고 assigned_player·share·보호 기한은 유지한다. 파티 해산으로 전리품이 삭제되거나 자유 획득으로 바뀌지 않는다.

## 조회와 명시적 native 생성

`loot_service.loot_snapshot(source)`는 frozen `LootSourceSnapshot`/`LootEntrySnapshot`을 반환한다. `as_entry()`/`source_entries()`는 기존 pure helper와 presentation용 값만 제공한다. UUID/화폐 row ID는 Web payload에 보내지 않는다. 단순 조회는 DB를 바꾸지 않는다.

`source.db.loot_backend="item_entities"`는 신뢰된 생성 경계다. `populate_source(source, entries)`는 비어 있는 Corpse/DroppedLoot를 명시적으로 선택해 모델을 만든다. 기존 blob을 조회하거나 명령을 실행한다고 변환하지 않는다. 비어 있지 않은 source는 거절한다. `create_claim()`/`create_currency()`는 이미 선택한 native 공간에만 쓴다.

생성 전 emptiness 검사는 presentation의 backend 분기에 의존하지 않는다. owner lock 후 legacy db.entries와 `has_native_assets(source)`의 실제 ItemEntity/CurrencyLoot 존재 여부를 모두 검사한다. ItemEntity는 위치 필터 없이 직접 owner 연결을 검사해 잘못된 위치의 asset도 숨기지 않는다. inside child의 직접 owner는 canonical constraint상 NULL이고 정상 subtree는 source 소유 root를 통해 감지된다. 하나라도 있으면 generation을 거절하며 marker·기존 rows·sequence는 바뀌지 않는다.

`integrity_errors(source)`는 native marker+legacy entries와 legacy/non-native marker+native rows 양쪽 불일치를 보고한다. 빈 native marker 자체는 정상이다. 불일치를 자동 복구하거나 lazy migration하지 않는다.

`Corpse.from_enemy(..., backend="item_entities")`는 기존 drop/allocation 결과를 모델로 생성한다. 관련 player/party owner를 먼저 잠그고 같은 world_change에서 cursor와 rows를 처리한다. 기본 backend는 legacy여서 현재 일반 사냥을 강제로 전환하지 않는다. native 생성 실패는 rows·sequence·party cursor·새 공간을 rollback한다. 총기 drop에 full 탄창을 자동 생성하지 않으며 기존 콘텐츠·가격·보상 수치를 유지한다.

## 실물 pickup와 claim-aware merge

`pickup(source, selected_snapshot, caller, quantity, now=...)`는 lock 후 출처·권리·수량·지분을 재검증한다. 이미 회수/decay되었거나 선택 후 변경된 snapshot은 거절한다. command의 기존 시야/광원 검사를 유지하며 domain도 같은 장소의 source만 허용한다.

전체 회수는 split 없이 claim을 먼저 삭제한 뒤 source ItemEntity 자체를 inventory로 옮겨 UUID·sequence를 유지한다. 부분 회수는 pickup의 transaction 안에서 `split_stack(..., allow_claimed=True)`로 새 row를 만들고 source quantity·claim·sequence를 유지한다. 분할 destination에 claim을 복사하지 않으며 사용자 이동은 기존 operation="loot"를 사용한다. 즉시 inventory로 옮긴 뒤 호환 stack에 merge할 수 있고 destination ID·sequence를 유지한다. split/move/merge/claim 정리 실패는 전체 rollback한다.

일반 `split_stack()`은 잠근 현재 DB row의 LootClaim을 확인하고 corpse/world claimed stack을 새 row 생성 전에 거절한다. stale Python 입력으로 우회할 수 없으며 source·claim·sequence 발급기도 불변이다. `allow_claimed=True`는 claim 없는 fragment를 즉시 inventory로 옮기는 loot partial pickup의 trusted 경계 전용이다. 같은 source에 보호 없는 fragment를 남기는 일반 split이나 permission 우회 용도로 사용하지 않는다. claim 없는 inventory split은 기존 의미를 유지한다.

generic `same_merge_context()`도 `merge_state()`와 `ClaimContext`를 비교한다. ClaimContext는 root UUID를 배정 단위로 삼고 reserved_party/player·assigned_player·protection_until을 함께 비교한다. claim DB PK가 기준은 아니다. 같은 root와 권리로 claim row를 다시 만들어도 context는 같다. 독립 entry의 root는 권리 필드가 같아도 서로 다른 배정 단위이므로 병합하지 않는다. claim 없는 호환 inventory stack은 기존대로 merge한다.

Firearm root에만 claim이 있고 magazine child에는 없다. 전체 tree 회수/decay에서 inside/parent/socket/state.rounds를 유지한다. child를 시체 목록의 별도 대상으로 노출하지 않는다. non-stack tree는 전체로만 회수한다.

## 화폐 eligibility와 원자적 지급

원래 참여자는 자기 share가 0이어도 다른 참여자의 지급을 요청할 수 있다. 따라서 0인 share 행을 보존한다. 이는 Decision Log의 share 기반 eligibility와 PR #25의 기존 의미를 함께 만족시키는 해석이다. 프롬프트의 양수 share 문구는 후속 zero-share 보존 요구에 따라 nonnegative로 구현하며 지급 weight에는 양수 몫만 사용한다.

부분 지급은 기존 `currency_payouts()`/weighted_split의 정수 배분을 사용한다. 보호 중 수령자는 share player이며 offline Explorer도 profile credits를 저장한다. quantity·share·모든 recipient credits를 하나의 world_change에서 변경한다. 두 번째 recipient 조회/저장이나 share 변경이 실패하면 첫 지급도 rollback한다. 완전 회수는 share를 먼저 삭제하고 CurrencyLoot를 삭제한다.

만료 이후는 기존처럼 요청자에게 지급한다. 이전 보호 지분을 free loot weight로 쓰지 않는다. 자유 획득으로 일부 회수할 때 과거 잔여 share를 0으로 정리하고 quantity 잔여량을 유지해 합 불변조건을 지킨다. 조회만으로 share를 바꾸지 않는다.

## 만료·corpse decay·cleanup

`reconcile_claims(source, now=...)`는 해당 native source의 expired claim만 삭제하며 ItemEntity는 같은 위치에 남긴다. room/world lifecycle이 각 Corpse/DroppedLoot를 처리한다. 조회 경로에서 전체 claim table을 스캔하지 않는다. legacy는 기존 timestamp 해석을 유지한다.

`decay_source()`/`Corpse.reconcile()`은 기존처럼 entry마다 DroppedLoot 공간 하나를 만든다. 실물 root는 corpse_loot→world_loot이며 tree·sequence·claim·배정·보호 기한을 유지한다. CurrencyLoot는 owner만 옮기고 quantity·share·보호권을 보존한다. 이미 만료된 claim은 먼저 정리하지만 decay 자체가 보호를 해제하지 않는다. 중간 transfer 실패 시 새 공간과 앞서 이동한 rows도 rollback한다.

빈 시체는 기존 TTL까지 남고 회수로 빈 DroppedLoot는 정리한다. 실물/화폐가 남은 공간의 암묵적 삭제는 PROTECT다.

## transaction과 lock

기존 world_change/transaction과 ItemEntity API를 사용한다. `lock_sources()`는 공간·caller·party·reserved/assigned/share recipient의 ObjectDB ID를 정렬해 먼저 잠근다. source tree와 recipient 소지품 UUID 집합을 모아 기존 deterministic lock을 사용한다. 다음으로 claim(item UUID), currency(PK), share(currency/player ID)를 잠근다. owner 대기 중 지급 대상이 추가되면 lock 순서를 뒤집지 않고 fresh 선택을 요청한다.

여러 source를 회수하는 command는 전체 집합을 먼저 잠근다. before/after_item_change·active weapon/light reconciliation·recovery 경계를 유지한다. 신뢰된 decay만 operation=None이고 사용자 회수는 operation="loot"다. raw QuerySet.update/bulk_create로 검증을 우회하지 않는다. `integrity_errors(source)`는 출처 단위 모델/권리/지분을 검사한다.

## Phase 6 boundary와 known gaps

legacy Corpse/DroppedLoot.db.entries는 기존 생성·회수·decay의 SSOT다. native는 새 모델만 갱신하고 같은 unit을 blob에 쓰지 않는다. profile inventory/equipment/storage/light_sources와 Container.db.items는 유지한다. native 실물은 native recipient에게, legacy 실물은 legacy recipient에게만 회수한다. backend 사이의 자동 변환·임시 Entity·dual-write는 거절한다. 화폐 wallet은 기존 profile credits다.

Phase 6에서 명시적 전리품 변환·marker/integrity 검증 후 cutover하고 facade의 legacy 부분을 제거한다. 이번 generation helper는 full-world conversion이나 자동 migration이 아니다. Credential/access는 현재 root/tree/권리를 바꾸지 않고 추가할 수 있다.

targeted 검증은 protected/free·부분 회수·지급·tree·merge·offline·rollback·stale 선택·legacy·selector/Web payload를 포함한다. 실제 PostgreSQL contention·multi-server race·full-world migration·전체 browser/multiplayer matrix·OS IME·balance simulation은 미검증이다. local full suite와 smoke-full은 Phase 7로 남긴다.
