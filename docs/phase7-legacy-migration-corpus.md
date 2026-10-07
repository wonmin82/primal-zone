# Phase 7B Canonical Legacy Migration Corpus

이 corpus는 `TEST / LEGACY CORPUS`다. 실제 플레이·운영 데이터가 아니며 production migration rehearsal로 취급하지 않는다. SQLite + single Evennia server의 구버전 호환 경로를 재현한다. PostgreSQL row-lock·multi-server race 검증은 포함하지 않는다.

## PR #36 review fix: offline guard와 최종 evidence

Windows의 PID 부재와 CLI-local session singleton은 offline 증명이 아니다. 현재 guard는 [cross-process offline 계약](item-migration.md#명령과-의미)을 사용한다. `python scripts/phase7b.py offline-guard`는 격리 native DB의 실제 Portal/Server를 시작하여 별도 apply/cutover가 running guard에서 실패하고 item/ledger/sequence/runtime/legacy snapshot이 불변인지 검사한다. 정상 Evennia stop 뒤 같은 settings의 guard가 통과해야 한다. Test override를 사용하지 않는다. 첫 성공 실행 `full-0awmg6e5`는69.828초이며 PID 파일 없는 Windows에서 두 process RUNNING을 AMP로 확인했다. Final bounded probe 재실행 `full-v88bfgea`도71.831초 성공했고, same-settings normal stop 뒤 acceptance·DB 불변·owned cleanup을 재확인했다.

`corpus-after.json`은 항상 해당 coordinator run의 마지막 successful cutover snapshot이다. Invalid의 초기 안전 실패(runtime0, 해당 source 미완료)는 `corpus-invalid-failure.json`으로 별도 보존한다. Unknown 항목 제거→repair/retry→verify→cutover 뒤 runtime1 결과를 after 파일에 쓰고, 파일 전체와 최종 inspect의 runtime/ledger/sequence/sources/players equality를 검사한다. Binary DB를 Git에 넣지 않는다. 이전 invalid 성공 로그와 당시 잘못된 after 파일은 historical evidence이며 새 파일의 의미로 소급 바꾸지 않는다.

## 생성과 실행

저장소 루트의 기존 Python 환경에서 다음을 실행한다. 각 명령이 별도 작업 디렉터리·SQLite·fixture account·owned Portal/Server를 만들고 종료한다. 개발 DB는 읽기 fingerprint 외에 사용하지 않는다.

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/phase7b.py valid
.\.venv\Scripts\python.exe -X utf8 scripts/phase7b.py warning
.\.venv\Scripts\python.exe -X utf8 scripts/phase7b.py invalid
.\.venv\Scripts\python.exe -X utf8 scripts/phase7b.py offline-guard
```

`scripts/phase7b_fixture.py`가 historical state를 코드로 구성하며 `game/tests/test_legacy_corpus.py`가 같은 builder의 의미를 regression으로 보존한다. 생성된 binary DB는 Git에 넣지 않는다. ObjectDB identity와 UUID는 새 DB마다 달라지므로 expected result는 identity 관계·수량·mapping·policy로 비교한다. 광원과 보호 기한에는 해당 실행의 관찰 시각을 사용한다.

작업 디렉터리는 `work/smoke/full-*`다. `.primal-smoke` marker, 전용 settings와 DB 환경 guard가 있어 일반 개발 설정에서는 builder를 실행할 수 없다. 결과는 `corpus-before.json`, `corpus-after.json`, 순번이 붙은 `migration-*.log`와 `post-cutover-evidence.json`에 남는다. 비밀번호는 검증 로그에 기록하지 않는다. 실패 디렉터리는 분석용으로 보존하고 성공 실행은 비밀 없는 결과를 `work/phase7b/evidence/<run-id>/`에 export한 뒤 같은 Harness의 소유권 검사에 따라 DB를 정리한다. 수동 조사 중에만 `--keep-fixture`를 사용할 수 있다. 아래 최종 성공 디렉터리는 모두 증거 export/owned process 종료 후 정리했다.

Coordinator가 각 격리 DB에서 실제 실행하는 management command는 다음이다. 테스트 override를 사용하지 않고 `ITEM_MAINTENANCE=True`와 정지된 서버 상태에서 실행한다. 일반 사용자의 명령은 [item-migration](item-migration.md)의 `scripts/dev.py migrate-items` 경로를 따른다.

```powershell
python -m evennia migrate_items --settings settings_smoke --dry-run
python -m evennia migrate_items --settings settings_smoke --apply
python -m evennia migrate_items --settings settings_smoke --verify
python -m evennia migrate_items --settings settings_smoke --cutover
python -m evennia migrate_items --settings settings_smoke --cutover --accept-warnings
```

## Valid

Explorer 7개, Container 2개, Corpse 1개, DroppedLoot 1개가 source다. 네 독립 fixture account 외에 bootstrap admin, 기존 native tree 보존용 Explorer, pre-v4 Explorer가 포함된다. 기존 관리 공용함과 별도 historical 공용함을 함께 검사한다.

| Source | Historical state와 expected result |
| --- | --- |
| 검증가 | inventory 총량·blade 2개 중 equipment 1개·개인 storage·복수 손전등·켜진 광원 state·scrap 20개 보존, 발전기 정비부품 총 3개 |
| 검증나 | 통신탑 claimed·supply cache claimed, 기존 출입증과 개인 storage의 탐사인식표 UUID 보존, missing 능선 고유 보상만 지급 |
| 검증다 | 깊은 밀림 claimed·jungle cache claimed, 기존 개인 storage 고유 보상 보존, missing 특수 출입증·정신안정모듈 지급 |
| 검증라 | carbine 2개·heavy_carbine 1개·armor/heavy_suit, equipment copy를 총량에 추가하지 않음, firearm마다 호환 full standard magazine |
| 보존검증 | 기존 native firearm/magazine UUID·sequence·tree·state 보존. 별도 미수리 entitlement의 새 정비부품은 기존 tree 재생성이 아님 |
| 구형탐사 | version 3/cache_claimed=true를 supply discovery로 정규화, 기존 jungle discovery 보존, missing fixed reward 지급, 원래 profile version/blob 보존 |
| Container | 개인 storage owner는 Explorer, 공용 storage owner는 Container이며 수량 정확 |
| Corpse | 보호·배정된 legacy carbine을 native tree/LootClaim으로 변환 |
| DroppedLoot | 20칩과 eligible 0/20 share, 절대 보호 기한 보존 |

중앙 legacy mapping의 11개 장비 변환을 모두 포함한다. dry-run과 verify는 파일 fingerprint 및 의미 snapshot이 불변이다. Apply만으로 global runtime은 0이며 ledger가 완료된다. 같은 apply의 두 번째 실행은 row·sequence·ledger를 늘리지 않는다. 수량을 일부러 4→5로 훼손하면 verify와 cutover가 거절되고, 원상 복구 후 verify/cutover가 성공한다.

Valid cutover 뒤 실제 Portal/Server와 네 독립 WebSocket session에서 로그인·소지품·장비·보관·광원·출입증·상점·총기를 실행한다. 일반 물품의 공용 보관 양도, 고유 보상 개인 보관과 공용 보관 거절, 출입증 소각→진입 차단→issuer 재발급→진입 복구, package 구매·탄창 회수/충전·잔탄 resale·body 판매를 확인한다. 이 과정에서 archived inventory/equipment/storage/light_sources는 갱신되지 않는다.

## Warning

검증가의 `equipment.weapon=spear`, `inventory.spear=0` 상태를 사용한다. 현재 계약의 `장착 수량 누락 복원: spear` warning과 recovery Entity를 기대한다. Apply/verify는 성공하지만 warning 미승인 cutover는 거절되고 모든 상태가 불변이다. `--accept-warnings` 뒤에만 runtime version 1로 전환된다. 새로운 warning 정책을 만들지 않는다.

## Invalid

검증라 inventory에 `unknown_historical_item`을 넣는다. Dry-run/apply/verify/cutover는 실패한다. 다른 source는 atomic하게 완료되지만 검증라에는 partial ItemEntity·completed ledger가 생기지 않고 archived profile이 그대로다. 재실행으로 성공 source의 row·sequence를 늘리지 않는다. Fixture에서 unknown 항목만 제거하면 검증라만 변환되고 verify/cutover가 성공한다.

별도 integration regression은 source 생성 실패의 transaction/ItemSequence rollback, ledger 미완료와 retry를 검사한다. Corpus의 실제 CLI 검증을 in-memory test만으로 대신하지 않는다.

## Phase 7B 실행 결과

2026-10-07, base main `52fa4d5813dffcfd6fed08013c69001e62a9b0d0`에서 실행했다.

| Corpus | 실행 디렉터리 | 결과 |
| --- | --- | --- |
| valid | `full-iltr18_o` | 11 source/11 ledger, sequence 55, version 1. Post-cutover 실제 명령 48.015초 성공 |
| warning | `full-d8yk431t` | 예상 recovery warning, 미승인 거절·승인 성공, 11 ledger/version 1 |
| invalid | `full-z5g9k59_` | unknown source 안전 실패·성공 source 보존·정상화 후 retry/verify/cutover 성공 |

고유 보상 폐기 거절과 migrated loot·발전기/cache를 보강한 최종 valid 재실행(`full-bawmbrl8`)도 CLI 전체 workflow가 성공했다. Post-cutover 실제 명령9개 시나리오는58.696초 성공했다. 고유 보상 개인 보관/공유·give·drop·sell·burn 거절 후 UUID/sequence/state를 보존하며, migrated firearm loot의 동일 tree 회수·zero-share trigger의2칩 지급을 확인했다. Migration 정비부품3개를 실제 발전기 수리에 제출한 뒤 최초 cache에서 정비부품0개 유지·붕대2개/탐사인식표1개 지급·일반 scrap20개 보존과 archived item blob 불변도 성공했다. 첫 거절 응답 기대 mismatch와 후속 성공은 playtest에 구분했다.

처음 실제 file DB apply에서 `ServerSessionHandler.count` AttributeError가 재현됐다. 정식 `get_sessions(include_unloggedin=True)` API로 수정하고 anonymous session을 포함한 offline guard regression을 추가했다. Ledger/cutover/transaction 구조는 변경하지 않았다.

초기 fixture 준비 실패와 잘못된 expected snapshot도 [playtest](playtest.md)에 보존한다. 위 성공은 그 실패를 삭제하거나 성공으로 바꾼 결과가 아니다. 이번 작업에서 실제 개발 DB migration이나 PostgreSQL 실행, balance tuning은 하지 않았다.

## PR #36 review fix 재실행 결과

- Valid `full-9kankv09`: 모든 실제 CLI 계약과 source11/ledger11/sequence55/runtime1 성공. Cutover 후 네 session의 기존9개 native gameplay·archived item blob 불변은73.100초 성공이다.
- Warning `full-1p_hwaom`: 기존 recovery warning, 승인 없는 cutover 거절/state 불변과 accept-warnings 성공. 최종 runtime1이다.
- Invalid `full-sfk13ydz`: unknown source initial safe failure와 다른10 source 보존·실패 source 부분 row 없음, repair/retry/verify/cutover 성공. `corpus-invalid-failure.json`은 runtime0/ledger10/sequence46, `corpus-after.json`은 runtime1/ledger11/sequence55와 실패 player의 최종 native9개다. Coordinator가 저장 파일 전체와 마지막 inspect를 실제 비교했다.
- 세 DB는 재생성 가능하므로 cleanup했고 `work/phase7b/evidence/<run-id>/`에 비밀 없는 JSON/CLI log만 남긴다. 실제 개발 DB는 불변이며 test override·PostgreSQL·production migration을 사용하지 않았다.
