# 아이템 월드 migration과 runtime cutover

## Phase 7B Canonical corpus 검증

[Canonical Legacy Migration Corpus](phase7-legacy-migration-corpus.md)의 코드 builder와 격리 file SQLite에서 valid/warning/invalid CLI를 실행했다. Dry-run/verify 파일 불변, source atomic apply, 재실행 row/sequence/ledger 불변, unknown source 정상화 후 retry, 수량 손상 verify/cutover 거절, warning 미승인/승인 경계를 확인했다. Valid cutover 뒤 네 실제 session의 native gameplay와 archived item blob 불변도 확인했다. 상세 fixture·명령·실행 디렉터리·실패 이력은 corpus 문서와 playtest를 따른다.

초기 file DB 검증에서 `SESSIONS.count()` AttributeError를 정식 API로 보정했지만, PR #36 리뷰에서 management-command process의 session singleton이 다른 Server process의 상태를 증명하지 못함을 확인했다. 현재 guard는 아래 cross-process offline 계약을 사용하며 그 이전 검증은 historical record다. Migration ledger·source transaction·global cutover 계약은 그대로이며 실제 production DB migration이나 PostgreSQL concurrency 검증을 의미하지 않는다.

## 현재 용도: legacy compatibility

현재 전환할 실제 production/play DB는 없다. 최종 운영 시작은 [fresh installation](installation.md#fresh-installation과-legacy-upgrade)의 빈 SQLite → schema → 첫 서버 시작의 native initialization/world bootstrap 경로다. Fresh DB에 apply/cutover를 실행하지 않는다.

아래 workflow는 과거 개발 DB·구버전 설치본 업그레이드·오래된 백업 복원을 위한 별도 호환 경로이며 migration 구현의 regression 대상이다. 실제 production migration/cutover/rollback rehearsal은 Phase 7 필수 조건이 아니다. [Phase 7B](phase7-final-integration-audit.md#phase-7b)에서 Canonical Legacy Migration Corpus의 valid/warning/invalid 흐름을 검증했다. PostgreSQL DB engine 이관은 이 도구의 역할이 아니며 [future infrastructure](postgresql-transition.md)다.

## 목적과 version

migration version 1은 기존 profile/blob 아이템을 최종 ItemEntity·LootClaim·CurrencyLoot/Share로 변환한다. ItemMigrationLedger는 `(migration_version, source_kind, source_identity)` DB unique와 completed/completed_at, 원본 source_digest, expected_state, created_counts, warnings를 저장한다. global `ItemRuntime(id=1).version=1`은 모든 대상 verify가 성공한 뒤 별도로 설정한다. Explorer에도 item_runtime_version=1을 기록한다.

실제 플레이 DB에 이번 개발 작업으로 apply/cutover를 실행하지 않았다. 아래 명령은 운영자가 backup과 서버 정지를 확인한 뒤 수행하는 절차다. schema migration 0004는 ledger/marker만 추가하며 월드 데이터를 자동 변환하지 않는다.

## source와 변환

| source | legacy 원본 | native 결과 |
| --- | --- | --- |
| Explorer | inventory/equipment | 총 보유 수량 중 장착분을 equipment로 배치 |
| Explorer | storage | owner=Explorer, personal_storage |
| Explorer | light_sources | instance state와 active_light UUID |
| Explorer | claimed quest | Credential·Boss unique 누락분 |
| 공용 Container | db.items | owner=Container, shared_storage |
| Corpse | db.entries physical | corpse_loot root·LootClaim |
| DroppedLoot | db.entries physical | world_loot root·LootClaim |
| Corpse/DroppedLoot | currency/eligible/remaining_shares | CurrencyLoot/Share, 0인 eligible share 포함 |

inventory count가 총 수량이다. inventory blade=2와 equipment weapon=blade는 Entity 두 개이며 하나만 장착한다. 가장 앞선 sequence의 inventory root를 선택한다. equipment만 있고 inventory count가 0이면 한 개를 복원하고 warning을 남긴다. firearm의 legacy 신규 변환은 full 표준 호환 탄창을 포함하며 loose ammo를 별도로 지급하지 않는다. 기존 native firearm은 UUID·sequence·탄창·잔탄을 그대로 보존한다.

광원은 migration 시각으로 elapsed power를 먼저 투영한다. legacy 정의별 첫 instance에 잔량을 보존하고 추가 복사본은 OFF/empty로 생성한다. 복수 ON은 legacy 순서의 첫 유효 광원 하나를 선택하고 warning을 기록한다. stale UUID를 복사하지 않고 실제 row UUID로 active reference를 생성한다. 기존 native active reference/state는 보존하고 verify에서 검증한다.

claimed radio_tower는 outpost_supply_pass/ridge_predator_mark, claimed deep_jungle은 special_supply_pass/predator_scale_charm을 누락 시 한 번 생성한다. 이미 보유한 entitlement는 owner scope 전체에서 찾아 UUID·sequence를 유지한다. XP·credits·기존 보상·quest claimed를 반복 지급하지 않는다. 구버전의 flat quest_claimed도 별도 저장 변경 없이 읽는다.

## 중앙 legacy mapping

`world/content/item_mapping.py`가 유일한 source → final ID 매핑이다.

| legacy | final |
| --- | --- |
| machete | explorer_machete |
| vest | expedition_workwear |
| blade | cutting_machete |
| spear | pioneer_spear |
| jungle_blade | jungle_longblade |
| carbine | guard_carbine |
| heavy_carbine | heavy_rifle |
| leather_suit | light_protective_suit |
| armor | reinforced_vest |
| tactical_vest | tactical_protective_suit |
| heavy_suit | heavy_protective_suit |

소비품·재료·quest trophy·flashlight·탄창·탄약·Credential의 기존 유효 ID는 유지한다. unknown ID/잘못된 수량/불일치 marker를 silently drop·자동 repair하지 않는다. 기존 native 장비의 이전 definition ID는 maintenance context에서 중앙 매핑에 정확히 일치할 때만 in-place 변경할 수 있다. 일반 gameplay의 definition_id/sequence 불변 계약은 유지한다.

## 명령과 의미

저장소 루트에서 실행한다. uv 환경은 동일하게 `uv run python scripts/dev.py ...`를 사용할 수 있다.

```powershell
.\.venv\Scripts\python.exe scripts/dev.py migrate-items --dry-run
.\.venv\Scripts\python.exe scripts/dev.py migrate-items --apply
.\.venv\Scripts\python.exe scripts/dev.py migrate-items --verify
.\.venv\Scripts\python.exe scripts/dev.py migrate-items --cutover
```

- dry-run: read-only source 계획·unknown mapping·수량·marker/원본 충돌·수신자·shares·light validation·예상 생성량/warning/error를 JSON으로 출력한다. Entity/sequence/ledger/profile/marker를 변경하지 않는다.
- apply: source 하나를 owner lock과 world_change transaction으로 변환하고 끝에 completed ledger를 기록한다. source 실패는 해당 source의 모든 row·sequence·Attribute를 rollback하고 오류를 수집한다. 다른 완료 source는 유지한다. global cutover는 수행하지 않는다.
- verify: read-only source 완료/digest/native snapshot, 독립 legacy/native 수량·equipment/storage·claim 권리·currency/shares·full migration magazine·광원 상태 대조와 전체 model full_clean/unique scope/active reference/entitlement를 검사한다. 오류가 있으면 cutover할 수 없다.
- cutover: source 완료와 verify error=0을 확인하고 marker만 설정한다. warning이 있으면 운영자가 보고서를 검토한 후 `--cutover --accept-warnings`로 명시적으로 수락한다. 데이터 재생성은 없다.

apply/cutover는 `ITEM_MAINTENANCE=True`만으로 허용되지 않는다. 실제 Portal과 Server가 모두 정지된 상태를 cross-process로 확인해야 한다. 현재 Python·GAME_DIR·environment·DJANGO settings를 그대로 사용하는 별도 process에서 Evennia 6.1 launcher의 AMP status API를 조회한다. CLI-local `SESSIONS`는 다른 process의 session 상태가 아니므로 offline 판정에 사용하지 않는다.

Windows launcher는 PID 파일을 만들지 않을 수 있다. Unix PID 검사는 보조 방어선이며 PID 없음은 정지 증명이 아니다. Portal-only·Server-only·둘 다 실행 중이면 거절한다. Status timeout·launcher 실행 실패·잘못되거나 알 수 없는 응답도 fail closed로 거절한다. Upstream `evennia status`는 모든 AMP errback을 NOT RUNNING으로 출력하므로 그 문자열만 신뢰하지 않는다. 명시적인 connection refusal과 timeout/프로토콜 오류를 구분하며, 정지 후보도 Windows CIM/Unix process 목록에서 orphan Evennia가 없음을 확인한다. 목록을 읽을 수 없거나 Python command line이 불명확하면 차단하고, 다른 world의 실행 중 Evennia도 보수적으로 차단한다.

Read-only status probe의 연결 제한은10초, AMP 응답 deadline은12초, 전체 child 제한은30초다. 연결 후 응답이 없는 경우도 probe 자체의 reactor를 종료해 Windows venv launcher의 child를 남기지 않는다. Windows에서 upstream 기본2초가 실제 연결 거절 통지보다 먼저 끝난 실패를 보존하며 gameplay timer/settings는 바꾸지 않았다. Windows actual owned Portal/Server가 PID 파일 없이 실행 중일 때 별도 apply/cutover 거절 및 DB snapshot 불변, 정상 종료 후 같은 settings의 guard 통과를 확인했다. 재현 명령은 `python scripts/phase7b.py offline-guard`다.

`ITEM_MIGRATION_TEST_OVERRIDE=True`는 SQLite의 실제 in-memory DB에서만 허용한다. Canonical file SQLite CLI는 override를 사용하지 않는다. 운영 설정에 test audit/override를 사용하지 않는다.

## 운영 순서

1. DB와 필요한 운영 파일을 backup하고 복원 가능성을 확인한다.
2. Server와 Portal을 정지한다. 기존 PID 파일·온라인 세션이 남아 있으면 원인을 확인한다.
3. 운영자의 local 설정에서 `ITEM_MAINTENANCE=True`를 설정한다. 비밀 설정은 소스에 커밋하지 않는다.
4. 서버를 켜지 않은 상태에서 정상 Django schema migration을 적용한다(`python -m evennia migrate --noinput`, cwd=game).
5. dry-run JSON의 source별 생성 예상량·warning/error를 검토한다. unknown/marker mismatch를 임의로 덮어쓰지 않는다.
6. apply를 실행한다. 오류 source를 명시적으로 처리한 후 재실행한다.
7. verify error=0을 확인한다. 원본 digest 또는 native snapshot mismatch는 자동 repair하지 않는다.
8. 필요한 warning을 검토하고 cutover를 실행한다.
9. maintenance 설정을 해제한 뒤 서버를 시작한다. 해당 DB의 운영 smoke와 사용자 상태를 확인한다.

completed source는 digest/snapshot을 다시 검증하고 skip한다. 중단 후 A/B 완료·C 실패이면 A/B는 중복 생성하지 않고 C부터 안전하게 재시도한다. cutover 완료 후 apply는 거절한다. 원본 재변경·native 손상·추가 legacy source가 있으면 verify가 실패한다. verify의 strict snapshot은 gameplay 시작 전 maintenance closeout용이며 이후 정상 gameplay mutation을 migration 손상으로 오인하지 않는다. 이미 서비스가 시작된 DB에 apply로 되돌리거나 ledger snapshot을 덮어쓰지 않는다.

## runtime 정책

cutover 이후 일반 gameplay는 ItemEntity/LootClaim/CurrencyLoot/Share만 읽고 변경한다. legacy inventory/equipment/storage/light_sources, Container.db.items, Corpse/DroppedLoot blob은 archive로 보존할 수 있으나 fallback·dual-write·lazy conversion은 없다. archive loot blob은 completed ledger의 원본 digest와 일치할 때만 보존 원본으로 인정하며 새 native source는 빈 db.entries를 갖는다.

EquipmentProfile.inventory는 Entity에서 파생한 일시적 pure rule 계산 수량이다. 보상/소모 delta는 item_inventory가 Entity API에 적용하고 저장할 때 archive 필드는 원형을 유지한다. raw profile shape를 gameplay SSOT로 쓰지 않는다. 신규 캐릭터는 native starter equipment와 bandage Entity를 직접 생성하며 처음부터 authoritative legacy item 필드를 저장하지 않는다. 실제 빈 DB만 직접 global native marker를 초기화한다. 기존 world는 migration-required로 fail-fast한다.

## 검증과 공백

격리 tests.test_item_migration/tests.test_phase6_runtime에서 source 전체 범위, 수량/equipment 포함, native tree·identity 보존, read-only dry-run, source 실패·retry, missing/corrupt verify, cutover guard, fresh player, archive 불변을 검증한다. 실행별 결과와 실패 이력은 [playtest](playtest.md)를 따른다.

기존 자동 fixture의 실행 이력과 현재 smoke/자동 기준선은 [playtest](playtest.md)를 따른다. Canonical Legacy Migration Corpus, Chrome desktop/좁은 viewport, SQLite single-server의 1~4인 session, 실제 Windows/Chrome OS IME 검증은 [Phase 7B](phase7b-integration-validation.md)에서 완료했다. 대표 build의 [밸런스 simulation](phase7c-balance-analysis.md)과 empty SQLite에서 시작하는 [fresh native 운영 경로 검증](phase7c-fresh-operational-validation.md)은 Phase 7C에서 완료했다. 실제 mobile device matrix와 모든 multiplayer race를 검증했다는 뜻은 아니다. PostgreSQL 경쟁·multi-server는 별도 infrastructure다. 실제 play DB 변환은 현재 대상이 없으며 Phase 7 필수 작업이 아니다.


## PR #34 리뷰 추가 entitlement

Explorer raw source/digest에는 discoveries도 포함한다. `radio_tower.generator_fixed=false`이면 owner tree의 정비용 회수부품 총량을3개로 채우며 기존 scrap은 변환하거나 차감하지 않는다. Inventory/equipment/personal_storage/inside 후손은 같은 owner scope이며 shared Container/다른 owner의 수량은 제외한다. 총량3 초과는 preflight 오류다. 수리 완료 source에 남은 부품은 자동 삭제하지 않고 warning으로 보고한다.

`supply_cache=true`이고 owner scope에 탐사인식표가 없으면1개, `jungle_cache=true`이고 정신안정모듈이 없으면1개를 생성한다. 기존 row는 위치와 무관하게 중복 생성하지 않는다. Dry-run의 source별 entitlement_grants는 필요한 stable ID/수량을 표시하며 읽기 전용이다.

이 보정은 기존 inventory/storage/light/Credential/Boss reward와 같은 Explorer transaction에 포함된다. 생성 실패 시 ItemSequence/rows/profile/marker/ledger가 rollback된다. Completed source는 digest/native snapshot 검증 후 skip하고 verify는 진행·발견 entitlement를 독립적으로 대조한다. Apply/verify/cutover 및 global marker 구조는 유지하며 실제 플레이 DB에는 실행하지 않았다.


## PR #34 최종 cache 호환 보정

Profile version<4의 `cache_claimed`는 `discoveries.supply_cache`로 정규화해 raw source와 기존 digest에 포함한다. 기존 discoveries의 다른 key(예: jungle_cache)는 보존하며 `rules.migrate_profile()`도 같은 해석을 사용한다. 오래된 cache 완료 캐릭터는 탐사인식표 entitlement 대상이며 owner scope에 이미 존재하면 UUID/sequence를 유지하고 중복 생성하지 않는다. Archived legacy profile은 현재 형식으로 다시 저장하지 않는다. 완료 후 원본 cache_claimed가 바뀌면 digest mismatch로 verify가 거절한다.

수송차 보급상자는 캐릭터당 한 번 붕대2개·탐사인식표1개를 지급한다. 발전기 미수리 상태에서만 정비부품이 총3개가 되도록 부족분을 보충하며 수리 완료 상태에서는 지급하지 않는다. Migration entitlement로 먼저 받은 부품을 사용한 뒤 cache를 열어도 부품이 재생성되지 않는다. 이는 정상 gameplay의 pure rule 보정이며 lazy entitlement나 legacy runtime fallback을 추가하지 않는다.
