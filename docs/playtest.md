# 원시구역 테스트 안내

## Phase 6 targeted validation (2026-10-06)

시작 main `94bc1e788fec5547841fb5f87e105854a69cc92b`, branch `codex/content-balance-full-migration`에서 실행했다. 아래 개수는 각 실행의 결과이며 서로 합산하지 않는다. 실제 플레이 DB에는 migration apply/cutover를 실행하지 않았다.

```powershell
.\.venv\Scripts\python.exe scripts/dev.py test tests.test_item_migration tests.test_phase6_runtime tests.test_item_entities tests.test_equipment_entities tests.test_firearms tests.test_shop_entities tests.test_rewards tests.test_regions tests.test_loot_entities tests.test_currency_loot tests.test_credentials tests.test_lighting_entities tests.test_item_interactions tests.test_incinerator tests.test_recovery --parallel 2 --reverse
```

위 integration targeted227개/123.185초(runner132.233초)는 성공했다. 이후 raw flashlight preflight와 profile 누락 방어선을 포함한 dedicated `scripts/dev.py test tests.test_item_migration tests.test_phase6_runtime --parallel 2 --reverse`는23개/21.810초(runner31.514초) 성공했다. 최신 PR HEAD의 CI run/SHA는 PR Validation에 별도로 기록한다. CI의 전체 자동 suite/Quick smoke와 로컬 targeted 검사를 구분한다.

- 개발 중 초기 migration6개는 in-memory SQLite URI를 offline override가 거절해5건 오류가 있었다. test override를 SQLite memory URI로 제한해 보완한 뒤6개/8.002초 성공했다. 초기 content pure5개는0.024초 성공했다.
- 초기 영향 범위 통합175개는8실패/7오류였다. raw loot entry 정규화 순서, unknown definition 오류 형태와 ordinary enemy bootstrap의 잘못된 HP 복원을 고쳤다. 최종 stable ID/가격/drop/structured modifier로 기존 fixture를 갱신한 뒤 관련108개/64.061초(runner73.590초)가 성공했다.
- pure94개는 이전 definition/가격·numeric column fixture에서10실패/61오류가 있었고, 이후2실패/1오류→1실패를 보정해94개/0.915초 성공했다. unittest를 저장소 루트에서 실행한 import 오류는 game cwd로 수정했다. production fallback이나 확정 수치 변경으로 해결하지 않았다.
- 추가 integration113개는5실패/4오류였다. native Credential 파생 inventory 기대값·명칭 substring·recovery 시각·partial pickup 인자·Boss scaling 기대값과 기존 Lv4 준비 fixture를 수정했다. 관련87개에서 준비 fixture 한 건이 추가 실패했고, 최종 Lv4 평균 장비/기술/소비품 준비로 보정한 뒤 migration/runtime/combat/shops36개/36.468초(runner46.315초)가 성공했다. 이후 runtime version과 profile 누락 방어선은 위 최종 targeted에서 별도 검증한다.
- 최종 pure 확장 명령(game cwd): `..\.venv\Scripts\python.exe -X utf8 -m unittest world.test_final_content world.test_item_definitions world.test_shop_rules world.test_equipment_engine world.test_firearms world.test_economy world.test_recovery world.test_rules world.test_shops world.test_settlement world.test_progression`은113개/0.706초 성공했다. 첫113개는 이전 Boss DEF를 전제한 penetration 피해 기대값 한 건에서 실패했고, 최종 carbine 공격8/shooting+2%/Boss DEF6에 맞춰 기대값을105/150으로 보정했다.
- 격리 Quick smoke 첫 세 실행은 party claim outsider 거절 단계에서 실패했고 각각 play DB fingerprint 불변과 own process 종료를 확인했다. native profile binding의 동일 snapshot 중복 조회와 수량 delta가 없는 저장의 불필요한 item lock/query를 줄여 재검증한다. 실제 item delta는 기존 owner→UUID lock과 stale quantity 재검증을 유지한다. production combat/recovery/protection 타이머는 변경하지 않는다.
- `scripts/dev.py check`: 최종 코드 검사 성공. `git diff --check`: 공백/EOF 오류를 수정한 뒤 성공. settings_test의 `makemigrations item_entities --check --dry-run`: 미생성 schema 변경 없음.
- `world.balance_sanity.report()`: Lv4 능선 Boss basic12/heavy9, Lv7 밀림 Boss13/10 opportunities. DEF10에서 raw30의0/30% penetration은20/22 피해다. 대표2H/1H+shield/1H+offhand/dual 조합은21/4,19/6,19/4,19/4 ATK/DEF다. 경비카빈 vs 경비기4발 비용12칩은 loot EV26.905의44.6%로 목표보다 높아 Phase 7 검토로 남긴다. EV와 모든 acquisition/가격은 [final-content.md](final-content.md)를 따른다.
- local full suite·smoke-full·전체 browser/multiplayer·OS IME·PostgreSQL contention·multi-server stress·full balance simulation은 미실행이다. JS/CSS/template 변경이 없어 browser/node/정적 asset 수집을 추가하지 않았다. Web shop/action 및 native state는 서버 payload 테스트로 검사한다. Full smoke helper의 최종 장비명과 이미 해제된 fixture를 맞췄으나 full closeout은 실행하지 않았다.
- 운영 backup/offline/dry-run/apply/verify/cutover 절차는 [item-migration.md](item-migration.md)에 문서로만 작성했다. 테스트는 격리 DB를 사용한다. 작업 중 플레이 DB SHA256은 `B1318296F505B9B7522FCBDEDFF7642A06CF055E9DE72802198C70E6B8A7F700`, size733184, UTC mtime2026-09-22 12:29:13으로 유지됨을 대조한다.

Phase 6 후속 검증: 중복 snapshot/query와 수량 변화 없는 저장의 lock 비용을 줄인 뒤 관련 `tests.test_phase6_runtime tests.test_item_migration tests.test_shop_entities tests.test_credentials --parallel 2 --reverse`는43개/36.212초(runner45.304초) 성공했다. native 기존 Boss unique 보존·복수 ON fixture를 추가한 dedicated25개/23.130초(runner32.440초)도 성공했다. 네 번째 Windows Quick smoke는 파티 공동 전투·outsider 거절을 성공했으나1초 corpse/2초 protection 경계를 지나 보호된 시체 회수 검사에서 실패했다. 플레이 DB 불변과 own process 종료는 모두 확인했다. Ubuntu의 최신 HEAD CI Quick 결과는 별도로 기록한다.

Decision interpretation: 최종 T1 drop에 회수부품이 없어 발전기 수리가 불가능한 점을 사용자에게 확인했다. 승인에 따라 수송차 보급상자에서 회수부품3개를 기존 보상과 함께 한 번 지급한다. drop 확률·수리 비용·one-time flag는 유지한다.

승인된 수송차 보급상자 보완 이후 관련73개/57.427초 실행에서 기존 보급상자 출력 기대값 한 건이 실패했다. 새 보상 출력과 일치하도록 fixture를 보정했으며 실제 native 발전기 제출은 수송차 보급상자의3개를 사용하도록 연결했다. 후속 재검증 결과는 마감 기록에 남긴다.


최종 보완 검증: cache 보상 안내의 이전 기대값으로 관련73개 중1건 실패한 뒤 기대값을 새 보상으로 맞췄다. 이후46개 실행에서 tests.test_text의 이전 시작 장비/숫자 column/단일 scrap drop 기대값3건이 실패했다. 실제 최종 장비와 독립 resource/special roll 계약에 맞춘 후 `scripts/dev.py test tests.test_text tests.test_phase6_runtime tests.test_item_migration tests.test_integration.GameplayIntegrationTests.test_cache_reward_is_personal_and_once_only --parallel 2 --reverse`는38개/35.987초(runner50.940초) 성공했다. 승인된 cache를 실제 generator 재료로 제출하는 native 경로도 포함한다. 추가 maintenance 방어선 전용1개는0.651초(runner11.125초) 성공했고 apply/cutover 거절 시 profile/rows/ledger/sequence/marker 불변을 확인했다. game cwd의 `..\.venv\Scripts\python.exe -X utf8 -m unittest world.test_rules world.test_final_content`는43개/0.500초 성공했다. 최신 check/diff도 성공했다. 실행별 개수는 합산하지 않는다.

### PR #34 최초 CI와 package import 보정

문서 HEAD `0d80f64a23a1b7fb202fd044cb042b7dfa1e20b3`의 [Game checks37433325751](https://github.com/wonmin82/primal-zone/actions/runs/37433325751)는 check 성공, 순수198개 중 discovery import1건 오류로 test 실패이며 통합은 시작하지 않았다. 새 item_migration package가 workflow/ORM을 eager import하여 Django 설정 없는 pure discovery에 영향을 줬다. package entry point에서 실제 호출 시 workflow를 import하도록 제한하고 Django가 미설정인 독립 프로세스에서 package import 성공을 확인했다. 관련 world.test_final_content 5개/0.017초와 migration/runtime targeted26개/26.267초(runner36.351초)가 성공했다. check/diff도 성공했다.

같은 HEAD의 Linux Quick smoke는21.718초 성공했다. 실제 first round0.643초, corpse→ground0.786초, respawn/protection1.782초와 공동 전투·부분 currency·권리·shop·relogin을 확인했다. 이는 Windows의 실패4회를 성공으로 바꾸는 근거가 아니며 서로 별도 기록이다. 보정 후 최신 HEAD CI는 별도 run/SHA로 PR Validation에 기록한다.

### PR #34 최종 콘텐츠에 따른 기존 회귀 fixture 보정

HEAD `dde2a6068761f3f5b9de63a2fc19ca3defd03309`의 [CI37433581120](https://github.com/wonmin82/primal-zone/actions/runs/37433581120)는 check·순수197개/1.143초·Quick26.295초 성공이며 통합552개/270.759초(runner276.931초)는12실패/11오류다. 이전 가격·scrap/weapon drop·armor ID·단순 slot column 기대값과 공유 suppress fixture의 HP 전제를 보정한다. trophy 한 entry가 하나의 allocation unit이라는 확정 규칙은 유지하며 currency의 각 group 권리를 함께 검사한다. historical legacy fixture는 별도 shield/offhand hands 배치를 표현하지 못하므로 해당 5종은 실제 native 착용·해제 명령/active reference/archive 불변 전용 회귀로 검사했다(1개/4.601초, runner14.957초 성공). production gameplay·가격·drop·allocation·scaling은 이 보정에서 바꾸지 않는다.

`tests.test_economy tests.test_equipment tests.test_growth_review tests.test_lifecycle tests.test_loot tests.test_targets tests.test_settlement tests.test_command_shortcuts --parallel 2 --reverse`의 관련97개/68.413초(runner77.772초)는 장비 화면의 이전 공격력 기대값1건에서 실패했다. 최종 정글장도+기본 공격은14, 전술방호복 방어는4로 기대값을 보정한 뒤 실패 method 전용1개/4.157초(runner13.109초)가 성공했다. 나머지96개는 첫 실행에서 통과했고 이후 해당 기대값과 native 전용 추가 회귀 외의 production/test 변경이 없어 재실행하지 않는다. check/diff도 성공했다. 실행별 수와 subcase 실패 수는 합산하지 않는다.

## PR #33 문서 마감 및 병합 검증

2026-10-06 문서 마감·병합 요청의 시작 HEAD는 `0e5be5e4fe162f993adc92db459cbeeeabb41bf8`, main은 `248c849470bb709259902bd7f35780894a4c7b78`다. 리뷰 HEAD의 [Game checks37411748278](https://github.com/wonmin82/primal-zone/actions/runs/37411748278)는 check·순수192개/1.055초·통합526개/242.912초·Quick smoke30.882초 성공이며 로컬21개와 합산하지 않는다.

마감 변경은 Task State와 이 검증 기록뿐이다. 실행 코드·테스트·설정·UI asset이 리뷰 검증 당시와 같아 아래 targeted21개/check 성공을 재사용하고 로컬 게임 검사·smoke·browser·node를 반복하지 않는다. 문서 경로·링크·명령과 과거 결과를 대조하고 git diff --check를 실행한다. 문서 HEAD 및 병합 commit의 자동 test/Quick smoke는 각각 새 run/SHA로 [PR #33 Validation/병합 마감 기록](https://github.com/wonmin82/primal-zone/pull/33)에 남긴다. 아래 병합 금지 설명은 이전 요청 시점의 범위이며 이번 명시적 병합 요청이 우선한다. 기존 PostgreSQL/multi-server·OS IME·전체 browser·migration·balance 공백은 유지한다.

## PR #33 출입증 소각 확정 문법 리뷰 검증

시작 HEAD `f60c6c5c08d0486aa49961bc4458651254f6e6ab`의 incinerator_service·tests.test_incinerator만 수정하고 아래 명령을 격리 settings_test DB에서 실행한다. 기존 Phase 5 결과와 재실행 개수를 합산하지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts/dev.py test tests.test_incinerator tests.test_credentials --parallel 2 --reverse
.\.venv\Scripts\python.exe scripts/dev.py check
git diff --check
```

- 수정 전 새 confirmation regression2개(legacy/native)는10.026초, runner24.577초에 실패했다. 두 출입증의 1개 confirmation이 삭제되어 후속 불변 비교까지 실패 subcase16개가 발생했다. 이는 각각 별도 test16개를 실행한 숫자가 아니다.
- 첫 수정 후 관련20개/24.264초, runner34.269초 성공했다. 이후 숫자 이름의 ammo9mm/556/762를 실제 command로 1/N개/모두 소각하는 회귀를 추가했다. 공통 parser와 ammo 정의는 변경하지 않았다.
- 추가 회귀를 포함한 첫21개/23.908초, runner33.831초는9mm fixture의 잘못된 stable ID ammo_9mm로 생성 단계1건이 실패했다. 실제 정의 ID ammo_9로 fixture만 바로잡았고 production 정의는 변경하지 않았다.
- 최종 같은 targeted 명령은21개/23.191초, runner34.609초 성공했다. check와 git diff --check도 성공했다. 이전20개나 실패 실행과 합산하지 않는다. 최종 코드 검사 이후 문서만 마감하므로 게임 검사를 반복하지 않는다.
- malformed confirmed command와 service 직접 호출에서 profile·ItemEntity rows·ItemSequence·active refs·access 불변을 확인한다. 두 출입증 정상 확인/삭제·stable ID/local index·기존 재발급, 일반 붕대 수량/모두 및 일반 물품의 소각 확정 거절도 포함한다.
- local full suite·smoke-full·전체 browser regression은 요청 범위에 따라 미실행이다. JS/CSS/template 변경이 없어 browser/node/정적 수집을 수행하지 않는다. 이전 CI37406457142 성공으로 대신하지 않고 최신 PR HEAD의 test/Quick smoke를 새 run/SHA로 PR Validation에 기록한다. 기존 PostgreSQL/multi-server·OS IME·full migration·balance 공백은 유지한다.

## Phase 5 출입증·접근·상점·소각 검증

시작 main은 `248c849470bb709259902bd7f35780894a4c7b78`, branch는 `codex/credential-access-shops-incinerator`다. 아래는 Phase 5 미커밋 diff의 격리 settings_test DB 검사이며 Phase 1~4 결과나 재실행 개수를 합산하지 않는다. 실제 구조/명령은 [출입증·접근·상점](credentials-access-shops.md)을 따른다.

```powershell
.\.venv\Scripts\python.exe scripts/dev.py check
.\.venv\Scripts\python.exe scripts/dev.py test tests.test_credentials tests.test_access tests.test_shop_entities tests.test_incinerator tests.test_item_entities tests.test_item_interactions tests.test_headquarters tests.test_parties tests.test_integration tests.test_shops tests.test_equipment tests.test_firearms tests.test_settlement tests.test_text tests.test_rewards tests.test_regions tests.test_lifecycle tests.test_economy tests.test_command_shortcuts --parallel 2 --reverse
git diff --check
```

관련 pure 검사는 game 디렉터리에서 `../.venv/Scripts/python.exe -X utf8 -m unittest world.test_shop_rules world.test_shops world.test_settlement world.test_headquarters world.test_rules world.test_economy`를 실행한다. 최종 순수71개/0.661초 성공이다. 위 통합 명령은223개/156.765초, runner166.067초 성공이며 실패/skip은 없다. check/diff도 성공했다. 로그는 Git 제외 work/phase5-closeout-targeted.log다. 마지막 코드 검증 이후 문서만 갱신하므로 게임 검사를 반복하지 않는다.

회귀는 실제 임무 보고/출입증 재발급/고유 DB constraint·모든 operation 거절·숨겨진 owner scope·보상/profile/sequence 전체 rollback, 개인 access/예약 시설/제한실 퇴장/기존 ridge/방향·직접 이동, 실제 bootstrap 재실행, legacy/native 거래와 source/sink, 1/N개/모두·duplicate selector·장착 복사본 보호·loaded firearm 거절, fixture 탄창 잔탄 매입, 소각 same-room/perception/정확한 확정·burn→access loss→reissue, active-light 삭제 및 실패 원복을 포함한다. Web 서버 payload와 공통 후치 parser/개인 줄임말 회귀도 검사한다.

### 개발 중 실패와 재검증

- 최초 pure 명령을 저장소 root에서 실행해 world import 오류5개가 났으며 실제 test body는 실행되지 않았다. game에서 다시 실행했다. 초기 순수69개는 기존 catalog/방 개수/NPC 전제에서15개 실패, 보정 후69개는 전초 방 hint 기대값1개 실패했다. 최종 관련 순수71개는 위 명령으로 성공했다.
- 초기 통합61개/75.686초는 기존 본부 traversal이 모든 새 방에 무조건 입장할 수 있다고 가정한 subcase8개가 실패했다. 권한 없는 새 목적지의 거절을 기대하도록 해당 fixture를 맞췄다. 새 Phase 5 module의 첫30개/29.875초(runner38.796초)는 성공했다. 이는 이후 보완된 최종 전체 관련 검사와 별도다.
- 확대161개/114.461초(runner123.776초)는 정산소의 첫 객체가 정산관이라는 기존 fixture2개가 실패했다. 소각기가 함께 배치되므로 정산관을 이름으로 선택하고 hidden NPC 검사는 해당 정산관만 검사하도록 보정했다.
- 확대201개/143.536초(runner152.658초)는 legacy 여분 무기의 모두 판매 Web action 누락1개와 기존 총 방 수52 기대값1개가 실패했다. snapshot의 legacy 장착 복사본만 제외하고 기존 모두 판매 동작을 유지하며 새 방4개를 포함해 기대값56으로 맞췄다.
- 수정 영향4개 module의51개/39.894초(runner49.008초)는 경제 실패 비교 중 actual wall-clock 회복 경계가 넘어1개 실패했다. 해당 원자성 method의 Explorer 시각만100으로 고정했다. 나머지 검사와 출입증의 잘못된 확정 순서 거절은 통과했다. 이후 `tests.test_economy tests.test_command_shortcuts --parallel 2 --reverse`는40개/17.459초(runner26.800초) 성공했다. gameplay recovery 주기/공식은 변경하지 않았다.

최신 PR HEAD의 자동 Game checks/test/Quick smoke는 push 후 별도 run/SHA로 기록하며 baseline main CI37390803018 성공으로 대신하지 않는다. PR을 병합하지 않는다. 로컬 full suite·smoke-full·전체 browser/multiplayer matrix·OS IME·PostgreSQL contention·multi-server race·full-world migration·balance simulation은 요청의 단계별 전략에 따라 미실행이다. JS/CSS/template를 수정하지 않아 browser/node/정적 수집은 미실행이고 Web action은 서버 payload test로 검사한다. production 가격/수치/profile schema와 플레이 DB·비밀 설정을 변경하지 않았다.

### PR #33 최초 CI와 정의 fixture 보정

구현 HEAD `ed79f48dfce2df74d8774e7babaa1f2c7f336bed`의 [Game checks37406287020](https://github.com/wonmin82/primal-zone/actions/runs/37406287020)는 check와 Quick smoke30.118초 성공, test 실패다. 순수192개 중 출입증2개에서 기존 모든 max_stack=None 기대값이 실패했고 통합 suite는 시작하지 않았다. 출입증의 max_stack1/non-stack/unique_per_owner/burn 허용을 명시적으로 검사하도록 해당 순수 fixture만 보정했다. 일반 아이템의 max_stack=None/legacy transfer 정책 검사는 유지하며 실행 코드와 가격·규칙은 바꾸지 않았다.

game에서 `../.venv/Scripts/python.exe -X utf8 -m unittest world.test_item_definitions world.test_shop_rules world.test_shops world.test_settlement world.test_headquarters world.test_rules world.test_economy`는73개/0.808초 성공했고 check/diff도 성공했다. 마지막 production 코드가 같아 targeted223개를 다시 실행하지 않는다. 로컬71개와73개를 합산하지 않으며 최초 CI 실패를 성공으로 덮어쓰지 않는다. 이후 최신 HEAD의 전체 자동 test/Quick smoke 결과는 [PR #33 Validation](https://github.com/wonmin82/primal-zone/pull/33)에 새 run/SHA로 기록한다.

## PR #32 Phase 4 리뷰 수정 검증

기준 HEAD `13cb330eb5a28784bab48688a8afa11291582d14` 위 리뷰2건만 수정한 diff를 격리 settings_test DB로 검사했다. 기존 Phase 4 검증과 아래 결과를 합산하지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts/dev.py check
.\.venv\Scripts\python.exe scripts/dev.py test tests.test_loot_entities tests.test_currency_loot tests.test_item_entities tests.test_loot tests.test_item_interactions --parallel 2 --reverse
git diff --check
```

- 최종 targeted97개/34.030초, runner43.880초 성공. check/diff 성공.
- 수정 전 generation 실물/화폐·claimed split 재현3개는 실패 subcase5개로 두 이슈를 확인했다. corpse/world split, hidden asset generation이 기존 구현에서 거절되지 않았다.
- 첫97개는 삭제 보호 fixture2개에서 실패했다(35.058초, runner45.424초). Evennia 직접 delete가 PROTECT 전에 marker Attribute를 제거해 새 integrity 검사에서 불일치를 감지했다. 실제 domain의 world_change 경계로 fixture를 보정한 뒤 해당2개는5.445초(runner14.993초) 성공했고 전체 관련97개도 위와 같이 성공했다. production 삭제나 화폐 semantics를 변경하지 않았다.
- 새 회귀는 marker 없는 실제 실물/화폐·잘못된 source owner 위치 row·양방향 integrity·빈 generation·reject 후 rows/quantity/state/claim/sequence/marker 불변, stale 입력의 corpse/world claimed split 거절, claim 없는 inventory split, partial pickup/merge와 full pickup의 split 미사용을 확인한다. 기존 legacy partial/권리·CurrencyLoot·ItemEntity rollback 회귀도 포함했다.
- 최신 리뷰 HEAD CI run/SHA·test/Quick smoke 결과는 [PR #32 Review fixes/Validation](https://github.com/wonmin82/primal-zone/pull/32)에 별도로 기록한다. 시작 HEAD의 CI37385084401 성공은 과거 기준이며 이번 HEAD 성공으로 대신하지 않는다.

리뷰 HEAD `f33ad30464088cb6b9bbb74e699590de94c29a40`의 [Game checks37389067401](https://github.com/wonmin82/primal-zone/actions/runs/37389067401)는 자동 check·순수190개/0.679초·통합487개/155.726초·Quick29.217초 성공이다. 로컬97개와 합산하지 않는다. 2026-10-06 후속 문서 마감/병합 요청에서는 실행 코드가 같아 로컬 검사를 반복하지 않는다. 문서 HEAD와 merge commit의 CI는 각각 새 run/SHA를 PR Validation/마감 기록에서 확인한다. 이전 실패 이력과 PostgreSQL/multi-server·IME·migration·balance 공백은 유지한다.

ClaimContext/payout pure helper·UI asset은 그대로여서 pure test와 browser/node를 반복하지 않았다. 요청 범위에 따라 local full suite·smoke-full·전체 browser/multiplayer matrix·OS IME·실제 PostgreSQL/multi-server 경쟁·full-world migration·balance simulation은 미실행이다. 자동 복구·legacy conversion·Phase 5+ 구현도 없다.

## Phase 4 LootClaim + CurrencyLoot 검증

새 구조와 legacy 대응은 [전리품 권리](loot-claims.md)를 따른다. 현재 작업은 시작 main `4d6a3057dbae08003cae8b5a082882135b31837b` 위 미커밋 Phase 4 diff로 격리 테스트 DB를 사용했다. 플레이 DB/schema에는 migration을 실행하지 않는다.

| 실행 | 실제 결과 |
| --- | --- |
| `.venv/Scripts/python.exe scripts/dev.py check` | 최종 성공 |
| game에서 `../.venv/Scripts/python.exe -m unittest world.test_loot_claims world.test_currency_loot` | 순수5개/0.001초 성공 |
| `.venv/Scripts/python.exe scripts/dev.py test tests.test_loot_entities tests.test_currency_loot tests.test_loot tests.test_combat tests.test_parties tests.test_item_entities tests.test_item_interactions tests.test_economy tests.test_lifecycle tests.test_targets tests.test_web_state tests.test_integration --parallel 2 --reverse` | 관련168개/60.964초, runner69.961초 성공 |
| 이후 native 생성 guard/owner lock·추가 rollback 테스트 보완 후 `scripts/dev.py test tests.test_loot_entities tests.test_currency_loot --parallel 2 --reverse` | 최종40개/13.991초, runner22.960초 성공. 168개와 중복 합산하지 않는다. |
| 격리 settings_test의 `makemigrations loot_entities item_entities --check --dry-run` | 해당 두 app에 model/schema 차이 없음 |
| `git diff --check` | 성공 |

개발 중 실물18개는 성공했다. 이어34개는 기존 금액+번호 혼용 금지 문법을 잘못 쓴 새 fixture1개에서 실패했다. 예시 이름 tests.test_multiplayer/test_party를 넣은106개 실행은 로더 오류2개, 실제 shared combat module을 잘못 tests.test_shared_combat으로 지정한112개 실행도 로더 오류1개였다. 실제 module은 test_combat/test_parties/test_economy로 확인해 위168개를 성공했다. 마지막 native38개는13.252초(runner22.306초) 성공했고 추가 rollback case의 메서드 배치 오류로 첫40개는 NameError1개에서 실패했다. 이력과 성공 개수를 섞거나 누적하지 않는다. 개발 check의 import 정렬4개와 테스트 블록의 unused/undefined 변수2개도 수정했다.

최종40개는 해당 메서드 배치를 복구한 뒤 성공했다. 그 뒤에는 문서만 마감했으며 같은 실행 코드를 반복 검사하지 않는다. 도메인 두 app의 schema 검사 전 전체 앱 dry-run에서 Evennia 기존 Tag index rename 제안이 출력됐지만 파일을 생성하거나 외부 패키지를 변경하지 않았다. 이번 schema와 ItemEntity app을 지정한 위 검사는 차이 없음을 확인했다.

회귀는 claim cardinality/location·PROTECT·party 해산·보호/자유·partial/full pickup·inventory merge·root 배정 단위·firearm tree·sequence rollback·source/claim/quantity stale·double pickup·corpse delete 후 rollback·부분/전량 화폐·0 share eligibility·offline/missing recipient·다중 payout rollback·currency decay·legacy no-lazy-conversion·selector/Web payload를 포함한다. UUID·sequence·canonical location·unique scope·tree policy·unknown operation·merge_state와 기존 공유 전투/파티/경제/명령 회귀도168개에 포함했다.

### 최소 Web 확인

기존 Quick harness로 별도 SQLite·fixture 계정·owned Portal/Server와 정적 파일을 준비해 기존 UI를 확인했다. full/Quick smoke scenario는 실행하지 않았으며 smoke 성공으로 기록하지 않는다. JS/CSS/template은 바꾸지 않았다.

- 보호된 강철마체테의 배정 대상 검증나 표시와 회수 버튼 비활성화를 확인했다.
- 자유 ammo×10의 회수 버튼은 native inventory×1/ground×9로 반영됐다.
- share0인 검증가의 `시체에서 3칩 가져`는 offline 검증나에게3칩을 지급하고17칩을 남겼다. 자기 wallet은 그대로였다.
- `2칩 가져`와 `칩 모두 가져`는 free6칩을2/4로 회수해 wallet150→152→156으로 표시됐다. `시체에서 칩 모두 가져`는 남은17칩을 검증나에게 지급하고 화폐 버튼을 제거했으며 보호된 실물은 남았다.
- console warning/error 없음. 임시 탭·owned process·성공 DB/로그 정리 완료, play DB fingerprint 불변. 전체 viewport/IME/multiplayer matrix는 실행하지 않았다.

### CI와 미실행

[PR #32](https://github.com/wonmin82/primal-zone/pull/32)의 구현 HEAD `8e199b6df30a649fc567ef3baee75f3353286982`에서 [Game checks37384065998](https://github.com/wonmin82/primal-zone/actions/runs/37384065998)가 test/smoke success다. 자동 check·순수190개/1.038초·통합482개/197.032초·Quick27.517초를 확인했다. 문서 마감 commit은 실행 코드가 동일하여 로컬 테스트를 반복하지 않으며, 최종 문서 HEAD의 CI run/SHA는 PR Validation에 별도로 기록한다. 시작 main CI37378988784 attempt2 success는 과거 baseline이고 이번 결과가 아니다. 자동 전체 suite의 개수와 로컬168개·native 재검증·순수5개는 합산하지 않는다.

문서 마감 HEAD `bcaf0887bce0a3d9a3a7be2581448683d18d1700`의 [CI37384558940](https://github.com/wonmin82/primal-zone/actions/runs/37384558940)는 smoke success, test failure(통합482개 중 distant-view 1개)였다. `test_gate_preview_does_not_unlock_or_traverse`의 recovery boundary가 실제 시각 1791240390→1791240400으로 넘어 profile 비교가 실패했다. Phase 4 gameplay 회귀가 아닌 기존 wall-clock flaky로 확인했고, 실행 지침74에 따라 해당 테스트의 Explorer 시각만 기존 observation fixture100에 맞췄다. gameplay/recovery 공식은 변경하지 않았다. `scripts/dev.py test tests.test_distant_view --parallel 2 --reverse`는14개/10.895초(runner23.041초) 성공했고 check/diff도 통과했다. 최종 수정 HEAD CI는 PR Validation에서 별도로 확인하며 실패 이력을 성공으로 바꾸지 않는다.

요청한 단계별 전략에 따라 local full suite·smoke-full·전체 browser/multiplayer matrix·OS IME·실제 PostgreSQL contention·multi-server concurrency·full-world migration·balance simulation은 미실행이다. Credential/access/shop V2/incinerator·drop/content/balance tuning은 구현하지 않았다.

## Phase 3 Lighting + Firearm 검증

[Phase 3 실제 검증 기록](phase3-validation.md)에 명령·개수·실패/재검증·최소 Web 확인과 미실행 범위를 구분했다. 순수/domain103개와 격리 DB targeted167개 성공을 서로 합산하지 않는다. 새 Lighting/Firearm 계약은 [광원·총기](lighting-firearms.md)를 따른다. 사용자 요청대로 이번 단계의 local full suite·smoke-full은 생략하고 최신 PR HEAD의 자동 전체 suite/Quick smoke를 별도 확인한다.

native fixture에서 두 광원의 독립 잔량/only-one-ON·readonly projection·소진·배터리 원자성·logout/shutdown·외부 이동/삭제/실패 rollback을 확인한다. 세 firearm family·한 magazine socket·acquisition 형태·자동/명시 reload·동률 sequence·no-op·combat opportunity·loose ammo 전량 unload/merge·실제 발사/빈 총기 resource ordering을 확인한다. legacy 손전등/총기와 Phase 1/2 회귀도 포함한다. 기존 플레이어를 초기화하거나 자동 Entity 변환해 검증하지 않는다.

PR #31 리뷰 회귀는 실제 dispatcher에서 `RECOVERY_INTERVAL`을 넘긴 시각으로 legacy 개인 보관 넣기/꺼내기, legacy/native 광원 켜기/끄기와 비전투 재장전의 즉시 회복을 검사한다. 별도의 시계 고정 조회 fixture로 native/legacy `날씨`의 광원 이름·켜짐·전원·잔량·현재 시야, LightSnapshot 단일 조회와 저장 불변을 검사한다. malformed/missing/None active 참조의 owned orphan OFF·경과 정산, 유효 active 보존·추가 orphan OFF와 foreign/storage 보호도 확인한다.

```powershell
.\.venv\Scripts\python.exe scripts/dev.py test tests.test_environment tests.test_lighting_entities tests.test_firearms tests.test_item_interactions tests.test_recovery --parallel 2 --reverse
```

이번 리뷰의 실제 결과·이전 실패 이력·최신 HEAD CI는 [Phase 3 실제 검증 기록](phase3-validation.md)을 따른다. JS/CSS/template 변경이 없어 이번에는 node·브라우저·정적 파일 수집을 반복하지 않으며 local full suite·smoke-full도 실행하지 않는다.

리뷰 HEAD `72fb9549e7d7def69478013e5afb31c855a30400`의 [Game checks37376220133](https://github.com/wonmin82/primal-zone/actions/runs/37376220133)는 자동 순수185개·통합442개·Quick smoke 성공이다. 로컬 리뷰18/86/36개와 합산하지 않는다. 2026-10-06 후속 병합 문서 마감은 실행 코드가 같아 로컬 검사를 반복하지 않으며 문서 HEAD와 merge commit의 CI는 각각 PR Validation의 새 run/SHA로 확인한다. 실제 PostgreSQL 경쟁·multi-server·OS IME·Phase 6 migration·balance 검증 공백은 그대로다.

## ItemEntity 1단계 검증

1단계는 gameplay cutover 없이 독립 Django domain만 추가한다. `tests.test_item_entities`로 위치·스택·순번·트리·고유 범위·rollback을, 기존 `tests.test_item_interactions tests.test_loot`로 이전/전리품 호환을 검사한다. 정의·이동 순수 검사는 game에서 `python -m unittest world.test_item_definitions world.test_rules world.test_headquarters world.test_shops`로 실행한다. 일반 플레이 DB에 테스트 fixture나 migration을 적용하지 않는다.

이번 단계의 사용자 계획은 로컬 targeted tests만 요구하고 전체 suite·smoke-full·Web/browser 전체 회귀·다인 전체 시나리오·전체 migration·balance simulation은 7단계로 미룬다. 실제 실행 결과와 기준 차이는 [작업 상태](CODEX_TASK_STATE.md), 모델/API 계약은 [ItemEntity 기반](item-entities.md)을 따른다. 아래 기존 gameplay 검증 기록은 당시 결과다.

### PR #29 리뷰 수정의 검증 기준

`tests.test_item_entities`는 테스트 전용 비스택 root/child로 root의 `equip=true`·child의 `equip=false`를 재현한다. root를 `equipment/hands`로 옮긴 뒤 child의 `inside`·같은 parent·`socket="magazine"`·sequence가 유지되는지 확인한다. 실제 firearm/magazine 콘텐츠는 fixture로도 배포하지 않는다. `give/drop/store/sell/burn/loot/consume`의 descendant 제한은 거절 후 전체 row·unique scope·발급기 불변을 검사한다. 미정의 operation 거절과 `operation=None`의 신뢰된 내부 이전도 구분한다.

merge는 현재 기본 계약의 전체 state 동일/차이와 테스트 안에서만 선택한 merge 관련 state 동일/차이를 각각 검사한다. LootClaim은 후속 단계이며 다른 claim의 병합 금지 계약만 유지한다. UUID·전역 sequence·split/merge identity·canonical 위치·cycle·PROTECT·개인 보관 owner·nested uniqueness·lock 순서·outer rollback·stale 입력은 같은 핵심 suite의 회귀 대상이다.

```powershell
.\.venv\Scripts\python.exe scripts/dev.py check
.\.venv\Scripts\python.exe scripts/dev.py test tests.test_item_entities --parallel 2 --reverse
git diff --check
```

2026-10-05 리뷰 구현 `8cfd14caaed33e5dd2789fe75a2fd5cc31422f92` 기준 로컬 targeted25개와 check가 성공했다. [해당 HEAD의 CI](https://github.com/wonmin82/primal-zone/actions/runs/37289716444)는 자동 전체552개·Quick smoke도 성공했다. 이는 로컬 전체 검사를 실행한 결과가 아니며 개수를 중복 합산하지 않는다. 이후 문서만 바뀐 마감에서는 링크·내용·diff를 검사하고 동일 코드의 로컬 게임 검사를 반복하지 않는다. 최종 PR HEAD와 병합된 main의 CI는 각 SHA로 별도 확인해 PR Validation에 기록한다. 실제 PostgreSQL row-lock 경쟁·multi-server concurrency·OS IME와 후속 통합 범위는 미검증이다.

문서 마감 HEAD `e3e4dff29aa198194a00f90ed9993f196d3953e3`의 CI에서는 기존 경제 실패 입력의 전체 profile 비교가 실제 자연회복10초 경계를 지나 실패했다. 해당 테스트의 시각만 고정하고 전체 비교·전리품 불변 검사를 유지했다. 후속 `scripts/dev.py test tests.test_economy --parallel 2 --reverse`의18개와 check는 성공했으며 실제 기록은 Task State를 따른다. gameplay 원자성 검사를 약화하거나 회복 규칙을 변경하지 않았고 이전 CI 실패를 최종 HEAD의 성공 근거로 사용하지 않는다.

## PR #30 Phase 2 리뷰의 검증 기준

장비 상세 모델과 조회 API는 [장비 설계](equipment.md)를 따른다. 실제 명령으로 기본 낡은마체테 장착 상태에서 강철마체테의 즉시 무장이 거절되고, 낡은마체테를 해제한 후 무장이 성공하는지 검사한다. Full closeout도 같은 명시 해제 순서를 사용하고 해제 직후 hands=None·장착 후 새 주무기 표시를 기다린다. 자동 교체 금지나 실제 gameplay 계약을 smoke 예외로 완화하지 않는다.

공통 active_weapon()은 legacy/Entity 모두 EquipmentItem 정보를 반환하고 hand_usage()도 공통 snapshot을 사용한다. legacy 장착 무기는 identity=None의 주무기이며 임시 Entity/UUID/profile 참조를 생성하지 않는다. 영속 row가 필요한 검사는 active_weapon_item()을 사용한다. 동일1H 무기 두 개에서 두 번째를 선택하면 상태·장비·소지품·Web가 같은 instance selector에 주무기를 표시해야 한다. 조회만으로 profile·row를 변경하지 않고 Entity 자동 선택·승계·stale·nested 이동·실패 rollback을 유지한다.

```powershell
.\.venv\Scripts\python.exe scripts/dev.py check
.\.venv\Scripts\python.exe scripts/dev.py test tests.test_item_entities tests.test_equipment_entities tests.test_equipment tests.test_text tests.test_integration --parallel 2 --reverse
.\.venv\Scripts\python.exe scripts/dev.py test tests.test_combat tests.test_recovery tests.test_environment --parallel 2 --reverse
git diff --check
```

수정 closeout의 실제 서버 검증이 필요할 때 다음 격리 Full을 사용한다. production scheduler를 기다리므로 Quick CI보다 오래 걸린다.

```powershell
.\.venv\Scripts\python.exe scripts/dev.py smoke-full
```

2026-10-05 리뷰 코드 HEAD `96a8fd2b1c7d5915121f622cb2cd337fd1b1bdd4`에서 로컬 targeted82개/39개·check·diff가 성공했고 Full438.541초도 통과했다. production30/45/120초·본부의 수정 장비 교체·두 임무·실제 Portal/Server restart·진행 보존과 cleanup, 플레이 DB fingerprint 불변을 확인했다. [해당 HEAD CI](https://github.com/wonmin82/primal-zone/actions/runs/37312294397)는 순수179개·통합404개·Quick30.526초 성공이다. 로컬/CI/이전 실행 개수를 합산하지 않는다. 문서 마감에서는 같은 코드의 로컬 검사·Full을 반복하지 않고 새 문서 HEAD와 병합된 main CI를 각각 확인한다. 전체 브라우저·OS IME·PostgreSQL 경쟁·multi-server·Phase 7 전체 matrix·전체 변환·balance simulation의 성공을 의미하지 않는다.

## 기존 gameplay 절차: PR #28 견제와 교관

1. 격리 캐릭터 두 명으로 같은 적에게 견제를 적용한다. 문자열 source ID별 효과가 공존하고 각자 자신의 Rank만 교체/갱신/보존하는지 확인한다. R10 두 명34.39%, 네 명56.95%, 보스 네 명32.92%는 순수 helper로 검사한다. public 적에 두 파티8명이 참여해도 source를 모두 유지하며 최종 감소율만 네 명 기준으로 제한한다. cap 상태에서도 모든 효과를 소비한다. boss=True/quest 없음과 boss=False/quest 존재 fixture는 각각 보스/일반 수치를 사용해야 한다.
2. 적 attack event에서 모든 횟수가 각각1 줄고0은 제거되는지 확인한다. telegraph는 추가 소비하지 않는다. 도망·마지막 참가자 이탈·claim timeout·Enemy 이동·사망·respawn 후 효과가 없어야 하며 HP 유예 중에도 재교전에 남아서는 안 된다.
3. 간파/견제 실행 후10초 전 재예약을 거절한다. 실제 계정 재로그인·session 복원·서버 종료 경로·기술 재분배·전체 재훈련 이후에도 absolute deadline을 유지한다.
   정신력 부족 시 다섯 기술의 이름과 실제 레벨 비용을 안내하고 전체 profile과 대상 상태가 불변인지 확인한다. cooldown 중이면 기존처럼 cooldown 안내가 먼저다. 동료 치료는 전투 안팎 모두 실패 시 양쪽 자원·예약·cooldown·대상 HP가 불변이어야 한다.
4. 특성/기술/전체 초기화는 해당 scope만 바꾸고 결과 숫자는 실제 available 총량과 같아야 한다. HP/정신력 무료 회복과 cooldown 초기화는 없어야 한다.
5. SkillTrainer8명·AttributeTrainer4명의 보기에서 역할·담당 입력만 확인한다. 현재 Rank/특성/남은 예산/상세 효과는 없고 각 NPC의 대화가 서로 달라야 한다. 훈련관리관만 세 재분배를 안내한다. Web NPC context와 growth panel은 기존 provider 명령을 계속 제공해야 하며 Room-owned 성장 action은 없어야 한다.
6. bootstrap 반복으로 Enemy/교관 ID와 profile v10·공유 loot/파티를 보존한다. source 없는 옛 suppression은 제거하되 현재 교전의 새 suppressions는 유지한다. 최종 check/test·Quick/Full smoke와 Node client 검사 및 수집 후 대표 desktop/mobile 화면을 확인한다. 실행 결과는 Task State와 PR의 해당 HEAD Validation에 기록한다.

## 현재 절차: 정신력과 주기 회복

격리 DB의 테스트 캐릭터로 확인한다. 일반 플레이 DB를 초기화하거나 fixture 상태로 덮어쓰지 않는다.

1. 새 profile은 v10·정신력 40/40이며 Lv5/지혜 0은 60, Lv10/지혜 5는 105다. v8 이하 fixture는 기존 진행을 유지하고 현재 최대 정신력으로 migration한다. profile_snapshot만으로 저장·시계 초기화가 발생하지 않아야 한다.
2. 부족한 HP/정신력으로 9초를 보내고 이동·장비 변경·전투를 시작한다. 현재 수치는 그대로이고 다음 고정 10초 경계에서만 정수 기여가 지급돼야 한다. 짧게 여러 번 계산한 결과와 offline batch를 비교한다.
3. 비전투 HP는 2+max_hp/60, 정신력은 4+max_mental/20의 분당 기본률이다. 의무실 6/2·중앙홀 2/2·관리동 2/1·옥상 0/2를 더하고 staging에는 추가하지 않는다. 전투에서는 장소 보너스와 기본 HP만 제외한다.
4. 실제 계정 logout/login으로 의무실의 offline 회복 후 대기실 시작을 확인한다. 기간 중 만료하는 효과는 만료 전만 계산한다. live session at_sync와 서버 restart에서는 기존 위치·단일 timer를 확인하고 offline 캐릭터에 timer가 없어야 한다.
5. HP full/정신력 부족에서 진료는 거절하고 휴식은 두 자원을 채운다. 붕대·음식·진료와 패배는 정신력을 바꾸지 않으며 full 자원의 credit을 남기지 않는다. 패배의 HP 1·최대 10칩 손실과 의무실 이동은 유지한다.
6. 적에게 피해를 주고 도망한다. 15초 유예 동안 HP가 같고 이후 경계에서 일부만 회복한다. 재교전은 그 HP이며 빈 방은 tick 없이 다음 접근에서 경과를 계산한다. 죽은 적은 회복하지 않고 기존 45초에 재생성한다.
7. 최종 collectstatic 후 1440px desktop·1100px·390px에서 HP/정신력/XP meter와 메인 scrollback의 prompt, 현재 숫자의 색, 3×3 compass/SURROUNDINGS를 확인한다. 입력창 위 고정 prompt는 없어야 한다. 과거 prompt는 남고 위로 읽는 중 새 prompt가 강제로 아래로 이동시키면 안 된다. overflow/clipping·console 앱 error/warning을 확인한다.
8. 상태·잘못된 명령·이동·공격·치료·진료·휴식의 결과 뒤 prompt가 하나여야 한다. 빈 Enter와 공백 Enter는 서버 최신 값의 prompt만 추가하고 command echo/↑↓ history에는 넣지 않는다. 지난 10초 경계와 Enter 연타를 비교해 중복 회복이 없어야 한다.
9. 자동 전투 공격 메시지에는 prompt가 붙지 않으며 자연회복으로 실제 정수 자원이 바뀔 때만 추가된다. 같은 이벤트 구간의 전투 메시지가 먼저 나와야 한다. 패배는 구조/손실·의무실 화면 뒤 최종 HP 1 prompt를 하나 출력한다. 새 로그인은 방/환영 출력 뒤 하나, logout은 없음이다.
10. Telnet 실제 text-session 경로에서 결과→prompt channel 순서·blank·회복·패배·중복을 확인한다. progressive 입력 대기/완료와 blank의 비응답 경로를 확인한다. 실제 OS IME와 Telnet font 렌더링은 별도 수동 검사다.
11. 일반 명령·실패·채팅·접속자와 compass/quick/context 버튼을 실행해 `[ 자원 ] > 명령` 한 행인지 확인한다. 별도 `› 명령` 행이 없어야 한다. 자동 적 공격 뒤 상태를 입력하면 과거 prompt와 공격 메시지를 보존하고 최신 서버 값의 입력 행을 끝에 추가해야 한다. 자연회복 prompt 뒤에는 가장 최신 행에 붙는다.
12. 빈/공백 Enter는 command span/history 없이 새 서버 prompt만 추가한다. ↑/↓는 실제 명령과 버튼 명령을 되짚고 idle은 제외한다. 60초 keepalive 전후 echo/prompt/history가 없어야 한다(정상 회복 prompt는 별개). 위로 읽는 비동기 출력은 scroll-lock, 직접 제출은 bottom 이동이다. 390px에서 `어린청소룡의 시체 2에서 회수부품 모두 가져`가 같은 입력 행에서 시작해 자연스럽게 wrap되고 가로 overflow가 없어야 한다.

자동 검사는 world.test_recovery·tests.test_recovery·tests.test_prompt와 의료/전투/성장/이동 suite를 사용한다. 계정 명령(접속자/종료) 뒤에도 context가 정리되고 실제 unpuppet/puppet 재접속에서 prompt가 정상 복원되어야 한다. Quick은 실제 정신력 경계 회복과 재접속, Full은 production 시체/보호/respawn·적 점진 회복과 restart를 검증한다. 이후 실행 수치는 당시의 과거 기록으로 보존하며 새 결과는 최상단 Task State에 기록한다.

Web 입력 행 자동 회귀는 `node --test scripts/tests/test_web_prompt.cjs`로 실행한다. 별도 JS framework 없이 실제 client와 DOM/WS 경계를 검사하며 `tests.test_web_prompt`로 전체 suite에도 포함된다. Node.js가 없으면 그 검사는 skip이므로 실제 실행 여부를 결과에 기록한다.

## 네트워크 접속 기본값 검증

`tests.test_network_settings`는 다섯 서비스의 활성화·IPv4 bind·포트와 LAN IP/hostname의 HTTP Host 허용 및 자동 생성 키의 Git 제외를 검사한다. 실제 listener 검사는 설정 assertion과 별도로 수행한다.

1. 격리 DB/fixture와 새 `game/server/`에서 Portal과 Server를 cold start한다. 기존 플레이 DB를 초기화하지 않는다. 기본 TCP 8700~8704가 다른 서버에 점유돼 있으면 소유자를 확인하고 정상 종료 후 검사한다.
2. Windows `Get-NetTCPConnection -State Listen`으로 다섯 접속 포트의 `LocalAddress`가 `0.0.0.0`인지 확인한다. AMP/내부 HTTP 포트는 게임 접속 listener와 구분한다.
3. `http://127.0.0.1:8701/webclient/`와 loopback이 아닌 실제 LAN IPv4 주소의 같은 페이지를 각각 열어 HTTP 200·DisallowedHost 없음·로그인·게임 진입을 확인한다. WebSocket은 해당 접속 hostname의 8702 포트여야 하며 브라우저 console connection error가 없어야 한다.
4. Telnet greeting·SSL handshake·SSH banner를 확인하고 SSL self-signed key/cert와 SSH host key의 최초 생성을 파일 존재 여부로 검사한다. 키 내용은 출력하지 않는다. Git status/check-ignore/ls-files로 다섯 파일이 무추적·제외되는지 확인한다.
5. 테스트 프로세스를 종료하고 플레이 DB의 검증 전후 fingerprint를 비교한다. 다른 LAN 장치/외부 NAT 접속과 외부 클라이언트별 인증서 신뢰·SSH 인증은 실제 수행 여부를 따로 기록한다. 방화벽/공유기 설정을 검사 중 변경하지 않는다.

설정과 노출 정책은 [설치 안내](installation.md#네트워크와-자동-생성-키)가 기준이다. Quick/Full smoke는 loopback과 임의 포트의 격리 정책을 유지한다.

## PR #26 최종 검증 기준 (2026-10-04, 과거 기록)

실행 코드 기준은 `cf6dada2d35c79c01a5cc72e263b807e04639074`다. 문서 마감은 Markdown만 변경하므로 아래 결과를 재사용하며 새로 실행한 검사처럼 표현하지 않는다. 이후 코드가 바뀌면 실제 영향에 맞춰 재검증한다.

- 전체 pure 147 + integration 339 = 486개 성공, integration runner 132.635s. 관련 prompt/recovery/Web/text reverse·parallel 40개와 Telnet full-resource assertion 보강 뒤 recovery 14개가 성공했다. Node 표준 모듈의 실제 client 경계 9개도 실행됐다.
- Quick 51.212s와 Full 332.477s 성공. production corpse 29.903s/respawn 44.815s/protection 121.310s, 적 점진 회복·패배·두 임무/보스·Portal+Server restart와 재로그인을 확인했다.
- 1440/1100/390px browser에서 prompt 오른쪽 입력·자동 피해 뒤 과거 prompt 보존·최신 회복 행 결합·blank/history/button/Account/idle/scroll-lock·모바일 긴 명령 wrap을 확인했다. 앱 console 오류와 가로 overflow가 없었고 플레이 DB fingerprint는 불변이었다.
- [Game checks 37163420451](https://github.com/wonmin82/primal-zone/actions/runs/37163420451)의 test·smoke는 위 구현 HEAD에서 모두 success다. 문서 마감 최종 HEAD와 병합 main의 CI는 [PR #26 Validation](https://github.com/wonmin82/primal-zone/pull/26)에서 SHA와 run/job 링크를 확인한다.
- OS IME·외부 Telnet 클라이언트/font·browser의 실제 progressive 추가 응답은 수동 미검증이다. Telnet 정상 prompt 채널/ANSI·Web semantic 및 progressive/Account 완료의 자동 검증을 수동 검증으로 대신 표기하지 않는다.

## 정신력·회복 검증 기록 (2026-10-03, 프롬프트 변경 전 과거 기록)

최종 pure 145 + integration 325 = 470개, runner 152.662s 성공. 관련 recovery 14개와 전투·장비·정산·상점·지역·환경 73개를 `--parallel 2 --reverse`로 확인했다. check/node/diff 검사와 정적 파일 수집도 성공했다.

Quick 53.424s와 Full 361.952s가 성공했다. Full은 시체 29.542s·respawn 44.506s·보호 120.250s, 적 부분 회복 18→20/재교전, 실제 패배와 침대 양 자원 회복, 두 임무·보스·restart를 검증했다. 자연회복으로 달라진 패배 fixture 및 종료 전 전투 라운드 snapshot 경합의 초기 실패를 수정하고 재실행한 최종 결과다. 자세한 실패·재검증 근거는 [작업 상태](CODEX_TASK_STATE.md#완료-검증-2026-10-03)에 남겼다.

격리 browser의 desktop 1440px·중간 1100px·mobile 390px에서 정신력 meter, 별도 prompt, 자동 회복 중 로그 개수 불변, 지혜 투자 후 현재값 유지, 진료/휴식 차이를 실제 명령과 침대 버튼으로 확인했다. console 앱 error/warning과 가로 overflow는 없었다. 플레이 DB hash/mtime/size는 불변이고 성공 테스트 서버를 정리했다. OS IME와 별도 Telnet 클라이언트의 시각 검사는 수행하지 않았다.

## 현재 절차: 명령 체계·도움말·로그인

아래 절차는 최신 코드 기준이다. 이후 단계별 실행 결과는 당시 명령과 수치를 보존한 과거 기록이며 현재 어휘보다 우선하지 않는다.

1. 격리 DB의 일반 계정으로 로그인하고 출정 대기실을 확인한다. 소지품/가방/가진거/i/인벤토리/소가 같은 출력인지 확인한다. `단축어`의 이동 8개·정보 5개를 조회한다.
2. `귀환` 후 옥상의 북부터 시계방향 `ㅂ/ㅂㄷ/ㄷ/ㄴㄷ/ㄴ/ㄴㅅ/ㅅ/ㅂㅅ`와 반대 방향을 왕복한다. 영문 alias와 방향 보기, 고정 3×3 compass의 8↔1 전환도 비교한다.
3. 두 플레이어가 `승강기`에 탑승한다. A의 `2층` 이후 A만 2층 중앙, B는 승강기 내부여야 한다. B가 `내려`를 입력해 하차한다. 같은 층 선택도 자동 하차하며 내리기는 unknown이다.
4. 의무실에서 치료/힐/heal은 정신력을 사용하는 플레이어 기술, 붕대 사용은 HP20 소모품인지 확인한다. 의무관 진료/treat와 침대 휴식/rest는 시설 서비스다. 회복/응급치료/firstaid·도주·액티브 방어는 명령으로 동작하지 않아야 한다.
5. 세 판매자에게 `상품`/`무기상 상품` 및 구매를 실행한다. 상점/메뉴/shop은 command가 아니다. 다른 본부 서비스와 가격·정산율을 확인한다.
6. 도움말 root의 여섯 분류, 이동/전투/아이템/성장/교류/편의 도움말, 소·ㅂㄷ 도움말, 파티 명령 detail, 입력 도움말을 확인한다. 8방향 이동은 command 색을 사용하지 않는다.
7. v7 fixture에서 heal Rank/예약 action과 old command 정의를 저장한 뒤 최신 v10을 로드한다. 새 예약 이름 충돌은 _개인[번호]로 보존하고 nested 참조도 연결되어야 한다. 소/ㅂㄷ/치료/힐/heal 신규 이름은 거절하며 가는 개인 이름으로 등록 가능하다. v7의 힐 정의와 exact nested 참조는 힐_개인[번호]로 보존하되 채팅·대상 문자열은 유지한다. 기존 줄임말/묶음/전체 삭제의 직접 2단계 계약도 확인한다.
8. 밀림 또는 3층에서 로그아웃/로그인하면 대기실에서 시작하고 XP/보급칩/소지품/성장/임무/방문/줄임말이 유지되고 HP/정신력은 offline 회복만큼 증가할 수 있다. live-session reload 복원은 기존 위치를 보존한다.
9. 최종 collectstatic 이후 desktop·중간 breakpoint·390px browser에서 FIELD GUIDE 소지품, 치료/도망, inventory 붕대 사용, 상품/진료, 승강기 자동 하차/내려 버튼을 실행한다. compass와 SURROUNDINGS 순서, console error/warning·가로 overflow·한글 clipping을 확인한다. OS IME는 별도 실제 입력 검증이다.

자동 검사는 `world.test_vocabulary`·`tests.test_vocabulary`와 기존 parser/줄임말/의료/상점/승강기/본부 suite, 전체 check/test, Quick live smoke를 사용한다. Full은 production timer와 restart/progression의 수동 검증이며 이번 변경의 실제 실행 여부는 PR 검증 기록을 따른다.

능력·경험치·Web 성장 화면에 숙련 XP/Rank가 없어야 한다. 현재 profile은 v10이며 여덟 기술은 모두 R1로 시작한다. 치료/힐/heal은 정신력 기술이고 붕대 사용은 독립 소모품이다. v7→v8의 과거 어휘 변환 이후에도 v10의 기술 환원·특성 예산 정규화가 적용되며 기존 탐사·장비·개인 줄임말 데이터는 보존되어야 한다.

## 현재 절차: 보급칩 경제

1. 상태·소지품에서 칩 잔액을 확인한다. 빈 inventory도 잔액이 표시되고 칩 보기에는 보급국 설명이 나온다.
2. 같은 방의 일반 Player 두 명으로 1칩/20칩/전액 전달, 부분/전액 버리기, 칩 2 가져와 전액 회수를 실행한다. 0·음수·소수·초과 금액·전투·자기 자신·숨은/원격 대상은 실패하며 상태가 보존되어야 한다.
3. 일반 적을 처치한다. XP·kill은 즉시 증가하지만 잔액은 그대로이고 시체에는 정확한 칩이 남아야 한다. 시체에서 칩 모두 가져 후에만 잔액이 늘어난다.
4. 파티/공용 보스에서 각 그룹 몫과 참여자 snapshot을 확인한다. 한 명의 회수로 각 참여자가 분배받고 부분 회수 후 남은 몫의 합계가 quantity와 같아야 한다. 가입/탈퇴/리더 변경/해체로 옛 몫이 바뀌면 안 된다.
5. 시체 30초 → ground와 보호 120초를 실제 Full에서 확인한다. 남은 quantity/권리는 유지되고 outsider는 만료 전 차단, 만료 후 자유 획득한다. 기존 item 순번·광원·번호 선택도 함께 본다.
6. 무기상 상품·강철마체테 가치·무기상에게 강철마체테 판매를 실행한다. 60칩 구매가/30칩 매입가이며 장착한 복사본은 남긴다. 붕대 모두 판매, 잘못된 상인·가격 없는 물품·임무 물품의 거절과 불변을 확인한다.
7. desktop/390px에서 상태·소지품 잔액, 상품 가격, 가치/판매 action, 시체/ground 화폐·기존 item·take button을 실행한다. 파티 지급 후 양쪽 state, 재로그인 잔액, console error/warning·가로 overflow를 확인한다.

후속 리뷰 검증에서는 4명에게 8칩(각 2칩)을 배정한 뒤 7칩 회수로 남은 몫이 한 명의 1칩뿐이어도 원래 참여자가 마지막 분배를 trigger하는지 확인한다. outsider는 보호 중 거절되고 offline 수령자는 DB에 지급되며, 수령 객체 누락 시 entry/모든 잔액이 그대로여야 한다. decay 전후 자격·잔여 몫·기한을 비교하고 expiry 후 outsider 자유 획득도 확인한다. 초기 shares currency와 legacy item 조회가 저장을 바꾸지 않는지 확인한다.

Web에서는 붕대 3개로 기본 판매 4칩/1개와 모두 판매 총 12칩을 구분하고, 강철마체테 3개 중 1개 착용이면 모두 판매 총액이 60칩이며 착용분이 남는지 본다. 마지막 손전등 판매 후 light_sources가 사라지고 재구매 시 전원이 없는지, 여분을 팔 때는 상태가 남는지도 확인한다. 시체/바닥 버튼은 8칩으로 표시하고 칩 8칩처럼 선택자와 금액을 중복하지 않으며 칩/칩 2 명령은 유지해야 한다.

관련 자동 검사는 world.test_economy/tests.test_economy와 기존 reward/loot/targets/shop/regions/text suite다. Quick은 처치 즉시 미지급·2칩 부분 분배·보호/decay·만료 후 회수·가치/판매·재접속을 연결하며 Full은 같은 흐름과 production timing/restart/progression을 검사한다.

## 장기 성장 현재 검증 절차

- 훈련실에서 Lv.1의 힘 4 배분은 성공, 추가 배분·강타 배워는 예산 부족으로 실패한다. Lv.2 이후 강타 배워와 타격교관에게 강타 배워는 같은 NPC validation을 사용한다.
- 의무실의 치료·체질, 전술훈련실의 견제·호흡·지혜, 사격장의 사격·간파·민첩을 확인한다. 훈련관리실의 세 재훈련은 무료이고 현재 자원·cooldown은 초기화하지 않는다.
- 능력/기술/경험치에 숙련 UI가 없고 Lv.126 특성 80점, Lv.133 추가 훈련 132회·정신력 기본 331/지혜 MAX 411을 확인한다.
- 비총기 강타·총기 사격 제한, 간파 뒤 치료/호흡으로 유지 및 공격 적중으로 소모, 견제 공유 상태·보스 절반·attack event당 한 번 소비를 검증한다.
- 치료/힐/heal은 활성 명령이다. 붕대 사용은 HP 20·정신력 소비 없음이며 가득 차면 소비하지 않는다. 전투 지원 행동은 다음 공격 한 번을 대신한다.
- 기존 v9 캐릭터는 v10에서 기술 R1·레벨만큼 재투자 가능한 훈련, cap/예산 내 특성, 기존 진행 보존을 확인한다. 재실행·read-only snapshot과 개인 줄임말 collision/nested 참조도 검사한다.
- Web desktop/mobile의 실제 NPC action과 성장 패널 버튼은 텍스트와 같은 명령을 사용한다. room-owned 성장 action·액티브 방어·숙련·응급처치 기술 버튼은 없어야 한다. 실제 OS 한글 IME는 별도 수동 확인한다.

## 과거 단계별 검증 기록과 당시 절차

## 당시 기준: 8방향과 고정 방향 인터페이스

1. 비전투 `귀환` 또는 승강기 `옥상` → `내리기`로 지원동 옥상 중앙에 간다. 지도와 Web에 북부터 시계방향의 여덟 실제 Exit가 보여야 한다.
2. `북동 보기`·`ne 보기`·`남서 봐`·`sw 봐`로 정찰한다. 현재 위치와 방문 기록은 바뀌지 않아야 한다.
3. 북/남, 북동/남서, 동/서, 남동/북서를 왕복하고 n/s·ne/sw·e/w·se/nw alias도 비교한다. 각 주변 구역에는 중앙으로 돌아가는 Exit 하나만 있다. `북동, 남서 해`도 중앙에 돌아온다.
4. desktop과 390px에서 옥상의 8개 버튼을 확인하고 북동 버튼으로 설비 구역에 들어간다. 남서 버튼 하나만 남아도 3×3 공간·중앙의 panel 내 좌표는 같아야 한다. 남서로 돌아온다. 글자 잘림·가로 overflow·앱 console 오류를 확인한다.
5. 오른쪽 DOM/화면은 SURROUNDINGS → PARTY → OBJECTIVE다. 1150px 이하 grid에서는 세 panel이 같은 첫 줄, 700px 이하에서는 같은 순서의 flex column이다. compass는 hint/context 위에 있다. 승강기·상점처럼 context action 수가 다른 방에서도 compass 위치와 footprint를 비교한다.
6. Telnet 방향도는 출구 0/1/4/8개 모두 30 cells × 5줄이며 `[현재]` 시작은 12열(0 기준)이다. 북/남 fullwidth 축과 방향 semantic 색이 유지되어야 한다. 실제 terminal/font의 glyph 폭도 별도로 확인한다.

### 8방향 브라우저 검증 (2026-09-29)

별도 guarded smoke SQLite/Portal/Server와 일반 Player fixture로 확인했다. setup의 `collectstatic --noinput`은 격리된 game 디렉터리에서 실행됐고 CSS/JS의 `?v=eight-directions`를 실제 로드했다. Chrome desktop 1424px에서 옥상 8개 → 북동 구역 1개 → 옥상, 승강기 0개 → 3층 중앙/복도 → 무기점을 이동했다. grid 높이 148px와 중앙 좌표는 출구·context 수에 따라 변하지 않았다. 승강기 층 선택/하차와 상점 상품 버튼도 실제 실행해 100C→40C·강철마체테 +1을 확인했다.

701px에서는 SURROUNDINGS/PARTY/OBJECTIVE가 같은 첫 줄이며 390px에서는 같은 순서의 flex column이고 3×3 compass를 유지했다. mobile 8↔1 전환에서도 중앙의 panel 내 좌표는 같았다(클릭 시 브라우저 자동 스크롤은 문서 내 배치를 바꾸지 않는다). 가로 overflow·대각선 text clipping·앱 console error/warning은 없었다. viewport를 복원하고 탭/owned server/temp DB를 정리했으며 일반 play SQLite SHA256·mtime_ns·size는 불변이었다. 검증 screenshot/log는 Git 제외 work에만 보관한다. 실제 OS IME·Telnet 클라이언트/font 렌더링은 미실행이며 텍스트 폭/semantic은 자동 검증한다. Full은 production gameplay timing 변경이 없어 반복하지 않는다.

최종 자동 검증은 check/node/diff 검사 통과, pure 115 / 1.975초·integration 282 / 139.278초·total 397·통합 runner 151.385초다. Quick smoke 68.232초는 기존 파티/점유/전리품·실제 timer·옥상/승강기/상점·재접속 흐름을 성공했다. 이 결과는 이번 branch의 새 실행이며 아래 과거 closeout 수치를 재사용하지 않는다.

## 현재 기준: 본부 전체 연결 검증

아래 절차가 1~7단계 완료 후 현재 상태다. 뒤의 단계별 실행 수치·PR OPEN·부두 서비스 기록은 당시의 검증 이력이며 현재 기능의 기준이 아니다. 각 과거 기록은 삭제하지 않는다.

1. 새 캐릭터는 출정 대기실에서 `남`으로 중앙홀에 들어간다. 재로그인은 저장 위치를 유지한다.
2. 중앙홀 `남` → 1층 중앙 `서` → `북`으로 보관실. 두 보기 버튼과 공용/개인 `붕대 넣어`·`꺼내`를 확인한다.
3. 보관실 `남` → `서` → `북`으로 정산소. 정산관 환율, 1개/N개/모두 정산과 Credits/resource 구분을 확인한다. 수리용 3개를 남기면 발전기에서도 사용할 수 있다.
4. 정산소 `남` → `동` → `동`으로 1층 중앙, `승강기` → `2층` → `내리기` → `동` → `북`으로 훈련실. TRAINING에서 기술 disclosure를 열어 학습·배분·재훈련 control을 확인한다.
5. 훈련실 `남` → `서` → `서` → `북`으로 의무실. HP 감소 상태에서 실제 의무관 치료와 침대 휴식 버튼을 확인한다. 둘 다 무료 full HP이며 패배 자동 회복 HP 1과 별개다.
6. `귀환` → 옥상, `승강기` → `1층` → `내리기` → `동` → `북`은 보급관. 3층 중앙 `동` → `북`은 무기상, `서` → `북`은 방어구상. 메뉴는 각 catalog만, 구매는 Credits만 사용한다.
7. 1층 중앙 `북` → `서`로 부두. 윤대장·탐사 동선만 남고 보관/훈련/의료/상점 서비스는 없다. `북`으로 초지에 들어가 실제 사냥·전리품 회수를 확인한다.
8. 낮은 HP에서 실제 적에게 패배하면 의무실·HP 1·최대 10C 감소·전투 종료다. 직접 치료/휴식 후 나갈 수 있다. 일반 귀환은 옥상이며 home은 부두다.
9. 데스크톱과 390px에서 SURROUNDINGS·hint·승강기·TRAINING·세 상점·resource/Credits·combat/loot control의 가로 넘침과 앱 console error/warning을 확인한다. 실제 OS IME는 별도 수동 검증이다.

자동 연결 검증은 `scripts/dev.py smoke-full`이다. 실제 restart와 두 임무/보스 최종 보고가 포함되며 production 30/45/120초도 매 실행에서 측정한다. Quick `smoke`는 빠른 CI 연결 검증으로 계속 분리한다.

### 본부 7단계 최종 로컬 검증 (2026-09-29)

시작 main `63dca1bf9366d60af06a1728f0aaefb2bfdb6526`, branch `codex/hq-final-closeout`. PR #13~#20 MERGED, 시작 시 열린 PR 없음과 main Game checks #106/run 36528666351의 test/smoke success를 확인했다. 아래 결과는 이번 최종 코드의 새 실행이며 과거 수치를 재사용하지 않는다.

| 검사 | 실제 결과 |
| --- | --- |
| `scripts/dev.py check` | 통과 |
| `scripts/dev.py test` | pure 101 / 1.875초, integration 252 / 84.920초, total 353, 통합 runner 94.315초 |
| `scripts/dev.py test world.test_smoke tests.test_hq_closeout tests.test_hq_services --parallel 2 --reverse` | 18 통과 / 14.875초, runner 23.496초 |
| `node --check game/web/static/webclient/js/primal.js` | 통과, JS 변경 없음 |
| `scripts/dev.py smoke` 즉시 연속 #1 / #2 | 45.956초 / 44.344초, 둘 다 성공·owned process 종료·temp 삭제 |
| `scripts/dev.py smoke-full` | 293.796초, 실제 restart와 두 임무/보스 최종 보고 포함, 성공·정리 완료 |
| Full 실제 첫 combat / corpse / respawn / protection | 2.835초 / 29.886초 / 44.501초 / 121.950초 |
| play SQLite 안전성 | 모든 실행에서 size 733184, mtime_ns 1790080153765082800, SHA256 `b1318296f505b9b7522fcbdedff7642a06cf055e9de72802198c70e6b8a7f700` 동일 |

전체 managed Object의 DB IDs/key/location/destination/aliases/stable tags/shop_id를 두 번 bootstrap 전후 비교했다. player profile 전체와 저장 위치, 공용 contents, 승강기 3층, facility/environment state가 같았고 integrity/stale는 비었다. malformed normalization·selector/poor/locked/distant privacy·멀티플레이 leader/leave/removal/XP/loot/한 명 패배 후 잔여 전투/rollback·동승 독립 하차는 기존 전체 integration 회귀가 유지한다.

Live Full에서는 보관상자/개인 보관함에 넣기·꺼내기와 일부 보관, 부품 7개 정산/3개 수리용 보존, 강타 Rank 2 학습, Doctor 치료, outsider 실제 패배·의무실 HP 1·최대 10C·Bed 회복, 옥상 귀환·3종 상점 구매·장착을 연결했다. 정비기록→발전기 부품 3개 소비→능선 보스→윤대장 보고, 길잡이→두 표식→신호전지 소비→두 번째 gate→밀림 보스→최종 보고가 actual 서버/명령/DB/WS로 완료됐다. 두 gate의 미충족 거절도 확인했다. RNG drop을 반복 기다리거나 결과를 fixture로 완료하지 않았다.

실제 restart 전 A는 승강기 3층에 있었고 B는 초지의 live claimed combat 중이었다. 공용 발전기와 상자·개인 보관·완료 임무·전리품이 있었다. harness가 같은 SQLite/설정/포트의 Portal+Server 두 프로세스를 실제 종료/시작한 뒤 세 계정 모두 재인증했다. DB identity/location/home=dock·XP/Credits/inventory/equipment/storage/growth/quests/discoveries/visited·파티·승강기·공용 contents·시설·환경 clock이 보존됐다. live combat/claim은 정리되고 남은 시체와 respawn은 실제 callback/sweep을 기다려 완료됐으며 모든 기존 loot entry가 ground에 유지됐다. forced OS crash 검증과 다르며 광원은 기존 off 정책을 따른다.

브라우저는 별도의 guarded 격리 SQLite/서버에서 일반 Player 권한 계정으로 진행했다. 대기실/중앙홀·보관 보기/넣기·정산 환율/모두 교환(부품 10→0, 1000C→1100C)·승강기 1/2/3층/옥상·TRAINING disclosure와 Rank 2 학습·Doctor/Bed full HP·세 판매자 메뉴/붕대·마체테·강화조끼 구매·부두 윤대장/서비스 버튼 없음·초지 실제 사냥/바닥 회수 버튼을 확인했다. DOM clientWidth/scrollWidth는 데스크톱 1234/1234, 390px override 375/375로 같았고 구매 control 시각 줄바꿈도 확인했다. 앱 console error/warning은 발견하지 않았고 Chrome extension의 async listener channel 종료 오류 3건은 구분했다. viewport override를 복원하고 탭·서버·temp DB/runtime credential 파일을 정리했다. JS/CSS asset 변경이 없어 cache version을 올리지 않았으며 fixture setup에서 격리 서버의 static을 수집했다.

근거는 Git 제외 `work/hq-closeout-tests.log`, `work/hq-closeout-quick1.log`, `work/hq-closeout-quick2.log`, `work/hq-closeout-full.log`, `work/hq-closeout-desktop.png`, `work/hq-closeout-mobile.png`다. 초기 관련 검사의 없는 모듈명/Evennia FK 필드명 기대를 바로잡고 실패한 새 검사부터 재검증했다. 개발 중 확장 Full 270.196초도 성공했지만 위 최종 Full은 restart callback 완료 polling까지 포함한다. assertion을 느슨하게 하거나 기존 테스트를 삭제하지 않았다.

실제 OS IME·강제 OS crash·Windows CI·PostgreSQL/운영 DB·모든 날씨/달 조합·모든 quest branching은 미실행이며 이 closeout의 의도된 non-scope다. live 주요 progression의 최종 보고와 production timing은 이번 Full로 새로 검증했다. test/smoke CI job은 그대로 분리하고 Full은 일반 CI에 추가하지 않았다. branch protection 설정은 수정하지 않았다. 최신 PR HEAD/CI는 PR Validation 및 완료 보고에서 직접 대조한다.

## 보기 별칭과 방향 정찰

- 현재 방의 `대상 보기`와 `대상 봐`, `대상 2 보기`와 `대상 2 봐`, `대상 모두 보기`와 `대상 모두 봐`를 비교한다. 적·시체·NPC·상자·가방 아이템과 단독 보기/봐에서 같은 정밀 정보를 제공해야 한다.
- 실제 출구가 있는 곳에서 `북 봐`/`n 봐`와 `북 보기`/`n 보기`를 비교한다. 남/s·동/e·서/w도 실제 Exit alias를 사용한다. 존재하지 않는 방향은 목적지를 임의 생성하지 않는다.
- 방향 정찰 전후 현재 위치와 `지도`를 비교한다. 관찰만으로 목적지가 방문 처리되거나 임무/발견·가방·상자·교전 상태가 바뀌어서는 안 된다. 미복구 상태의 습지→능선, 첫 보고 전 능선→밀림 입구, 신호 장치 가동 전 거목→연구구역은 차단 문장만 보이고 목적지 이름·설명·객체를 숨겨야 한다. 조건 충족 후 같은 방향 명령은 정상 정찰을 허용하고, 실제 이동도 정상이어야 한다.
- 세 경계의 `북 봐` 안내를 비교한다. 습지→능선은 잠긴 진입문, 거목→연구구역은 닫힌 출입문을 표현한다. 능선→밀림은 `북쪽으로 이어지는 길 너머는 아직 자세히 살펴볼 수 없다.`라고 안내하며 존재하지 않는 문을 묘사하지 않는다. 실제 `북` 이동은 기존 정비·윤대장 보고·신호 장치 안내를 그대로 사용한다. observe_message가 없는 검증 fixture는 `그 방향은 아직 자세히 살펴볼 수 없다.`를 사용하고, 관찰 허용 override는 이동과 view lock을 해제하지 않는다.
- 적이 있는 방은 이름·수량만 보이고 HP·정확한 번호·공격 안내는 없어야 한다. 시체는 종류·수량만 보이며 만료된 시체와 바닥 전리품은 숨긴다. 관찰 자체가 decay/respawn을 실행해서는 안 된다.
- NPC·발전기·신호 장치·공용/개인 보관함은 존재만 보인다. 새 generic ActionObject, 정비기록·탐사 표식·보급상자·늪지 보급품은 기본 원거리 숨김이다. 상자 contents·개인 storage·전리품 권한·행동은 표시하지 않는다. 플레이어는 이름 대신 탐사자 수로 표시하며 view lock이나 콘텐츠의 distant_visible=False를 존중한다.
- 살아 있는 적의 현재 방 보기는 콘텐츠의 local 문장을, 방향 보기는 distant 문장을 사용한다. 적이 respawning이 되면 양쪽에서 해당 존재 문장이 없어지고 환경 설명은 그대로여야 한다. 시체가 있으면 적 대신 시체 존재를 표시한다. 정적 환경에 적 움직임이나 hidden 객체가 중복으로 남아 있어서는 안 된다.
- 표시할 객체가 없는 방에는 `그 밖에 눈에 띄는 것은 없다.`라는 문장이 있어야 한다. 실제 방향으로 이동한 뒤 일반 보기를 실행하면 번호·시체 상세·바닥 물건 등 로컬 정밀 정보가 다시 보여야 한다. 이전 방에서 정찰한 적에게 원격 공격/회수/조사를 할 수 없어야 한다.
- 데스크톱과 약 390px에서 긴 관찰 문장의 줄바꿈과 의미별 색을 확인한다. SURROUNDINGS는 현재 방의 기존 버튼·방향도만 유지하며 원격 조작 버튼을 추가하지 않는다.

2026-09-27 후속 검증에서는 별도 DB의 웹 클라이언트에서 `북 봐`/`n 보기`의 동일 응답과 위치 유지, 중복 적·익명 탐사자 수, NPC·공용/개인 보관함·시체의 존재 요약, 작은 기록물만 있는 방의 빈 정찰 문장을 확인했다. 실제 이동 후에는 바닥 정제수·시체 전리품·상자 내용이 다시 보였으며 `시체 봐`, `원정 보관상자 봐`, `갈퀴사냥룡 2 봐`의 정밀 조회도 확인했다. 1366px와 390px에서 가로 overflow가 없었고 390px 화면 캡처로 줄바꿈·의미별 색을 확인했다. 실제 OS 한글 IME 조합은 미검증이며 한글 명령은 자동 문자열 입력으로 실행했다. 이번 후속 변경은 정적 파일이나 입력 JS를 수정하지 않았다.

2026-09-27 presentation/진행문 정책 후속 검증은 위의 초기 정찰 검증(`f3ccffa`)과 별도로 수행했다. 별도 DB에서 수몰된 도로의 환경 + 살아 있는 철갑등짐승 local 문장과 거목에서 `남 봐`의 distant 문장을 비교했다. 재생성 대기 상태를 준비한 뒤에는 같은 환경 설명에서 살아 있는 적 문장이 사라지고 시체만 표시됐다. 관측소는 원거리에서 관측 표식을 숨기고 `그 밖에 눈에 띄는 것은 없다.`로 끝나며 실제 입장 후에는 표식이 보였다. 신호 장치·NPC·공용/개인 보관함은 원거리 존재만 표시하고 내부 내용은 숨겼다.

닫힌 연구구역의 `북 봐`는 차단 문장만 표시했다. 실제 `신호 장치 조사`로 전지를 사용해 문을 연 뒤 같은 명령은 목적지 설명과 적 요약을 표시하며 현재 위치는 거목에 유지됐다. 1366px 문서 폭은 1351/1351px, 390px는 375/375px로 가로 overflow가 없었다. 390px 화면 캡처로 긴 한국어의 줄바꿈과 방향/적 시맨틱 색상을 확인했다. 콘솔 오류/경고는 없었다. 기존 플레이 DB와 정적 파일은 변경하지 않았고 검증 서버는 종료했다. 한글 명령은 자동 문자열 입력이며 실제 OS IME는 미검증이다.

2026-09-27 관찰 차단 문구 후속 검증에서는 별도 DB에서 윤대장 보고 전 능선의 `북 봐`가 `북쪽으로 이어지는 길 너머는 아직 자세히 살펴볼 수 없다.`를 표시하는지 확인했다. 물리적 문이나 목적지 내부 정보는 표시하지 않았고 현재 위치는 능선에 유지됐다. 390×844px 화면에서 문서 폭은 375/375px, 해당 메시지 폭은 303/303px로 가로 넘침 없이 줄바꿈됐으며 방향 semantic color가 유지됐다. 나머지 두 물리적 경계, 조건 충족 후 정찰, 이동 메시지와 관찰 override는 자동 테스트로 확인했다. 기존 플레이 DB는 변경하지 않았고 격리 서버는 종료했다. 실제 OS 한글 IME는 미검증이며 JS/CSS 변경이 없어 정적 파일 수집은 반복하지 않았다.

## 대상 선택과 전리품 문법

동일 이름의 Enemy 3개와 시체 3구를 **격리된 검증 DB**에 준비한다. 실제 플레이 DB를 초기화하지 않는다. 시간 경계 자동 테스트에서는 실제 sleep 대신 주입한 timestamp를 사용한다.

| 입력/상황 | 기대 결과 |
| --- | --- |
| `갈퀴사냥룡 보기`, `갈퀴사냥룡 2 보기`, `갈퀴사냥룡 모두 보기` | 기본 하나, 두 번째 하나, 같은 이름 전부를 표시한다. |
| `갈퀴사냥룡 공격` 반복 | 같은 기본 적을 선택하고 타이머를 중복 생성하지 않는다. |
| `갈퀴사냥룡 2 공격` | SURROUNDINGS의 같은 번호 버튼과 동일한 적을 선택한다. |
| `갈퀴사냥룡 모두 공격`, `갈퀴사냥룡 2 모두 보기` | 다중 공격과 배타적 선택자를 거절하고 상태를 바꾸지 않는다. |
| `시체 보기`, `시체 2 보기`, `시체 모두 보기` | 방 전체의 시체 순서에 따라 선택하며 전체 조회는 자연스러운 문장으로 설명한다. |
| 단일 시체에서 `시체 보기` | 상세에 `지정: 시체`, `회수: 시체에서 모두 가져`를 안내한다. 회수 후 빈 시체에는 회수 명령이 없다. |
| 시체 3구에서 `시체 2 보기` | 상세의 지정명·회수 명령이 SURROUNDINGS의 같은 시체와 일치한다. 안내한 명령 또는 2번 회수 버튼은 그 시체만 처리한다. |
| 바닥의 같은 아이템 2개에서 `회수부품 2 보기` | `회수: 회수부품 2 가져`를 안내하고, 실행하면 2번 entry에서 한 개만 회수한다. |
| 시체 A 만료 후 시체 B/C | B가 시체 1, C가 시체 2로 표시된다. 번호를 저장하지 않는다. |
| `시체에서 회수 부품 가져` | 기본 시체의 회수부품 한 개만 가져간다. ×3 entry는 ×2가 남는다. |
| `시체에서 회수부품 모두 가져`, `시체에서 모두 가져` | 기본 시체만 처리하며 다른 시체의 물건은 유지한다. |
| `시체 2에서 회수부품 가져`, `시체 2에서 회수부품 모두 가져`, `시체 2에서 모두 가져` | 두 번째 시체에서 각각 한 개, 같은 종류 전부, 모든 종류를 회수한다. |
| `모든 시체에서 회수부품 모두 가져`, `모든 시체에서 모두 가져` | 모든 시체의 회수 가능한 일치 물건을 배정자에게 지급한다. |
| `모든 시체에서 회수부품 가져` | 가져올 대상에도 모두를 붙이라는 안내와 함께 실패한다. |
| `회수부품 가져`, `회수부품 2 가져`, `회수부품 모두 가져`, `모두 가져` | 바닥의 첫 entry 한 개, 두 번째 entry 한 개, 같은 종류 전량, 모든 종류를 처리한다. |
| 내 파티/외부 파티의 시체가 섞인 전체 회수 | 내 파티 물건은 기존 assigned_player에게 가고 외부 보호 물건은 남는다. 일부만 회수해도 성공이다. |
| 보호 만료와 시체 TTL 경계 | 보호 만료 뒤 FFA, 시체 만료 뒤 DroppedLoot 보존, 중복 회수 없음. |
| `전체 회수부품 가져`, `시체에서 전체 붕대 가져`, `시체 모두에서 모두 가져` | 지원하지 않는 문법으로 거절한다. |

Room 본문은 `갈퀴사냥룡 두 마리가…`, `갈퀴사냥룡의 시체 두 구가…`와 지정 방법의 문장으로 표시해야 한다. SURROUNDINGS·버튼·상태/조작 control은 `시체 1 · 갈퀴사냥룡의 시체` 같은 compact 대상·번호·상태 표현을 유지한다. 시체 한 구일 때 Room 본문에 불필요한 번호가 없어야 한다. 상세 보기의 회수 안내는 단독 `가져`가 아니라 실제 출처/대상이 포함된 명령이어야 한다.

브라우저에서는 데스크톱/390px에서 위 기본·번호·전체 조회 및 회수, 번호 버튼의 실제 명령, 자연어 묘사, 긴 문장의 줄바꿈과 가로 넘침을 확인한다. 버튼과 직접 명령은 같은 서버 규칙을 적용한다. 자동 한글 문자열 입력은 실제 OS IME 조합 검증과 구분해 기록한다.

### 대상 선택 브라우저 검증 기록 (2026-09-27)

`origin/main`의 `d709890`에서 시작한 대상 선택 변경을 별도 검증 DB와 서버에서 확인했다. 기존 플레이 DB는 초기화하지 않았다. 중복 적 3개, 시체 3구, 파티원 배정 물건과 외부 탐사자 보호 물건을 준비했다. 긴 명령 비교를 위해 준비한 시체의 만료 시각만 검증 fixture에서 연장했으며 실제 사냥으로 생성한 시체는 기본 30초 만료를 사용했다.

- 직접 입력한 기본 공격과 번호 버튼의 2번 공격이 서로 다른 정확한 적의 HP를 감소시켰다. `갈퀴사냥룡 모두 보기`, 기본/2번/전체 시체 조회가 정상 출력되었으며 다중 공격은 거절되었다.
- 기본 시체의 한 개/같은 종류 전량/모든 전리품, 2번 시체의 모든 전리품, 모든 시체의 회수부품 전량과 전체 회수를 확인했다. 파티원에게 배정된 물건은 그 파티원의 가방에 지급되고 외부 보호 물건은 남았다.
- 바닥의 기본/2번 entry 한 개와 회수부품 전량 회수를 확인했다. 실제 사냥으로 생성한 시체가 만료된 뒤 `모두 가져`로 남은 회수부품과 강화조끼를 회수했다.
- 부두 귀환 후 실제 객체에서 생성된 윤대장 대화 버튼을 클릭하여 같은 텍스트 명령과 임무 수령이 동작함을 확인했다.
- 1366×900과 390×844에서 자연어 번호 안내, 시맨틱 색, 번호 버튼과 입력창을 확인했다. 문서 가로 폭/scrollWidth는 각각 1351/1351, 375/375이며 로그는 745/745, 339/339로 가로 넘침이 없었다. 브라우저 console의 warning/error도 없었다.
- 한글 명령은 자동 문자열 입력으로 검증했다. 실제 OS 한글 IME 조합, 별도 Telnet 클라이언트의 번호 서술 렌더링은 미검증이다. 보호 만료·재번호·원자적 실패와 공유 보스/전리품 회귀는 자동 테스트로 확인한다.

### 전리품 상세 안내 확인 기록 (2026-09-27)

`origin/main`의 `3c0b36c`에서 시작한 `codex/loot-detail-actions`의 상세 표시 변경을 독립 검증 DB에서 확인했다. 초지에 시체 3구와 같은 이름의 바닥 entry 2개, 수송차에 단일 시체를 준비했다. 기존 플레이 DB는 변경하지 않았으며 준비한 시체의 만료 시각만 fixture에서 연장했다.

- Room의 다중 시체 자연어와 SURROUNDINGS의 `시체 2 · 갈퀴사냥룡의 시체` compact 표기가 유지됐다. `시체 2 보기`의 지정명·회수 명령이 같은 번호 버튼과 일치하고, 회수 버튼은 파티원 배정 물건을 그 파티원에게 지급했다.
- `회수부품 2 보기`는 `회수부품 2 가져`를 안내했다. 직접 실행하면 두 번째 바닥 entry만 ×3에서 ×2로 줄고 첫 entry의 ×3은 유지됐다. 모든 시체 회수 버튼은 회수 가능한 물건만 처리하고 외부 탐사자의 보호 물건은 남겼다.
- 단일 시체에서는 번호 없이 `지정: 시체`, `회수: 시체에서 모두 가져`를 안내했다. 안내한 명령으로 회수한 뒤 상세에는 남은 전리품이 없다고 표시하고 회수 안내를 생략했다.
- 1366×900과 390×844에서 상세 명령·시맨틱 색·줄바꿈을 확인했다. 문서 폭/scrollWidth는 1351/1351px와 375/375px, 로그는 745/745px와 339/339px로 가로 넘침이 없었고 console warning/error는 0개였다. 실제 OS 한글 IME 조합과 별도 Telnet 클라이언트는 미검증이다. TTL 재번호·권한·수량 경계는 자동 테스트로 확인한다.

공유 월드 버전의 가입, 파티, 사냥, 전리품, 성장, 임무와 재시작 복구를 확인하는 문서입니다.
게임 화면에서 입력할 명령은 `이렇게` 표시합니다. 명령은 한 줄씩 실행하고 결과를 확인한 뒤 다음 단계로 진행하세요.

## 1. 테스트 준비

### 서버 실행과 접속

현재 개발 PC에는 `E:\Work\primal-zone`에 실행 환경이 구성되어 있습니다.
서버가 실행 중이면 바로 [게임 화면](http://127.0.0.1:4001/webclient/)을 엽니다.
서버가 꺼져 있다면 PowerShell에서 실행합니다.

```powershell
Set-Location -LiteralPath 'E:\Work\primal-zone'
.\.venv\Scripts\python.exe scripts/dev.py start
```

첫 시작은 초기 준비 때문에 시간이 걸릴 수 있습니다. 서버 시작이 완료된 뒤 접속합니다.
새 PC나 새로 받은 저장소에서는 [설치 안내](installation.md)에 따라 필요한 도구, 의존성과 초기 설정부터 준비합니다.

기본 주소는 서버를 실행하는 PC에서만 사용할 수 있습니다. 휴대폰의 `127.0.0.1`은 휴대폰 자신을 가리키므로 이 주소로 개발 PC에 접속할 수 없습니다.
작은 화면 배치는 개발 PC의 브라우저 창을 줄이거나 개발자 도구의 기기 화면 모드로 확인합니다.

### 테스트 계정

- 관리자 대신 새 일반 탐사자 계정을 사용합니다. 처음부터 임무를 검증하려면 아직 진행 기록이 없는 계정이 필요합니다.
- 이름은 한글·영문·숫자·밑줄 2~24자, 비밀번호는 8~128자입니다. 추가 비밀번호 검증에 걸리면 화면의 안내에 따릅니다.
- 이름과 비밀번호를 입력하고 **새 탐사자 만들기**를 누릅니다. 이후에는 같은 정보로 **접속하기**를 누릅니다.
- 같은 계정은 한 세션만 허용됩니다. 두 사람 테스트는 서로 다른 계정과 브라우저 창을 사용합니다.
- 수동 플레이와 실서버 자동 검사는 실제 로컬 DB에 계정과 진행 기록을 남깁니다.

새 계정의 정상 초기 상태는 **출정 대기실, Lv.1, 체력 60/60, 경험치 0, 크레딧 20**입니다.
낡은마체테와 탐사조끼가 착용되어 있고 붕대 3개를 보유합니다. 공격력은 9, 방어력은 1입니다.

## 2. 첫 사냥 빠르게 확인하기

새 계정으로 아래 순서대로 진행합니다. 전투 중에는 자동으로 차례가 진행되므로 명령을 한꺼번에 붙여넣지 마세요.

| 순서 | 입력 또는 조작 | 정상 결과 |
| --- | --- | --- |
| 1 | 가입 후 `상태`, `가방` | 위의 초기 상태와 장비·붕대가 표시됩니다. |
| 2 | `남` → `서` → `윤대장 대화` | 출정 대기실에서 중앙홀·부두로 이동합니다. 통신탑 복구 임무를 받고 정비기록 조사 안내가 표시됩니다. |
| 3 | `북` | 바람 부는 초지로 이동하고 어린청소룡 사냥 버튼이 표시됩니다. |
| 4 | `어린청소룡 공격` | 교전이 시작되며 약 2.5초 간격으로 기본 공격과 적의 공격이 진행됩니다. |
| 5 | `강타` 후 승리할 때까지 기다리기 | 다음 차례에 강타가 적용됩니다. 추가 공격 명령 없이 전투가 이어집니다. |
| 6 | `상태` → `시체에서 모두 가져` → `가방` | 솔로 첫 승리 기준 경험치 22, 크레딧 28입니다. 회수 후 부품 1개가 가방에 들어갑니다. 강철마체테는 확률 드롭입니다. |
| 7 | `귀환` → `승강기` → `2층` → `내리기` → `서` → `북` → `휴식` | 옥상을 거쳐 의무실의 실제 침대에서 체력을 모두 회복합니다. 이미 최대 HP면 휴식을 거절합니다. |
| 8 | `종료` 후 재연결·로그인 | 같은 캐릭터의 경험치·크레딧·소지품·임무가 유지됩니다. |

**통과 기준:** 가입부터 사냥 보상, 휴식, 재접속까지 오류 없이 진행하고 저장된 값이 유지됩니다.
한 번 사냥했는데 장비가 나오지 않는 것은 정상입니다.

### 본부 Room 구조 1단계 확인

- 신규 접속 위치는 출정 대기실이며 실제 출구는 `남` 하나뿐이다. `남`으로 중앙홀에 들어가 `북`으로 돌아온다. 기존 캐릭터 재접속은 마지막 유효한 위치를 유지한다.
- 중앙홀에서 `서`로 부두, 부두에서 `동`으로 중앙홀을 오간다. 부두의 `북`은 기존 초지로 이어지며 윤대장·상점은 기존 위치에서 작동한다. 의료·휴식은 아래 4단계 의무실에서 확인한다. 보관·훈련은 아래 3단계 절차로 지원동에서 확인한다.
- 중앙홀 `남`으로 지원동 1층 중앙에 들어간다. `북`으로 중앙홀에 돌아오고 복도의 동서 5칸, 북쪽 자원 정산소·보관실·보급품 상점의 남쪽 복귀를 확인한다. 보관실·훈련실·의무실 이외 시설은 Room만 있고 서비스나 action hint는 없다.
- 1층 중앙에서 `남`, `s`, `ㄴ`, `남 보기`는 폐쇄 안내만 표시하고 위치·방문 기록을 바꾸지 않는다. Room 본문은 북쪽 중앙홀 통로와 남쪽 폐쇄 문을 표현한다. 방문 지도에는 `북: 본부 중앙홀`, `남: 폐쇄`, 웹 이동 버튼에는 실제 `서/동/북`만 나타난다. 미래 시설 이름이나 dummy 목적지가 없어야 한다.
- 승강기로 2·3층 중앙과 옥상에 도달하고 복도를 통해 각 시설 Room을 확인한다. 보관·훈련·의료는 지원동의 실제 객체를 사용하며 `귀환`은 옥상, 패배는 의무실을 사용한다. 아래 1단계 검증 기록의 상층 접근 제한·부두 서비스 배치는 당시 상태다.
- 자동 검증은 `world.test_headquarters`의 데이터/무결성/기존 profile 보존과 `tests.test_headquarters`의 실제 명령·재접속·표시/state·bootstrap 반복·기존 서비스 회귀를 사용한다. 전체 명령은 `scripts/dev.py check`, `scripts/dev.py test`다.

**본부 브라우저 기록 (2026-09-28, 방향 수정 전):** 아래 결과는 `bef94dd`에 포함된 옛 중앙홀 동/1층 중앙 남 연결의 확인 기록이며 현재 방향 변경의 브라우저 검증으로 간주하지 않는다. `fd3e884`에서 시작한 본부 변경을 별도 SQLite DB·일반 검증 계정으로 확인했다. 최초 접속은 출정 대기실이었으며 `남` 버튼으로 중앙홀, `동` 버튼으로 지원동 1층 중앙에 진입했다. `북`과 `북 보기`는 같은 폐쇄 안내를 출력하고 현재 위치를 유지했다. 지도는 방문한 실제 Room과 `북: 폐쇄`를 표시했으며 SURROUNDINGS에는 실제 `서/동/남`만 있었다. `남` 명령으로 중앙홀에 돌아가 `서` 버튼으로 부두, `북` 명령으로 초지에 진입했고 `귀환`은 부두였다. 종료·재연결·로그인 후에도 부두 위치가 유지됐다.

1366px에서 문서/로그 clientWidth·scrollWidth는 각각 1351/1351px, 745/745px였고 390px에서는 375/375px, 339/339px로 가로 넘침이 없었다. 검증 탭의 console 오류/경고는 0개였다. 화면 캡처는 Git 제외 `work/hq-1366.png`, `work/hq-390.png`에 남겼다. 새 검증 서버의 정적 파일만 수집했고 확인 후 종료했다. 플레이 DB는 수정하지 않았다. 실제 OS IME와 기존 전체 smoke는 미실행이며 명령 parser·서비스 회귀는 자동 테스트로 확인한다.

**본부 자동 검증 (2026-09-28):** 기준 HEAD `fd3e884`와 `codex/hq-room-skeleton`의 본부 실행 코드·테스트 미커밋 변경에서 `.\.venv\Scripts\python.exe scripts/dev.py check`가 통과했다. `.\.venv\Scripts\python.exe scripts/dev.py test`는 순수 72개·Evennia 통합 198개, 총 270개를 실패 없이 통과했다. 통합 실행 시간은 1010.005초이며 근거는 `work/hq-final-full.log`다. 앞선 관련 검사 `python -m evennia test tests.test_headquarters tests.test_regions --settings settings --noinput`는 game 디렉터리에서 19개를 통과했다. 초기 개별 순수 검사에서는 존재하지 않는 두 모듈명을 지정한 실행 오류가 있었고 실제 `world/test_*.py` discovery로 정정했다. 코드 회귀 실패는 없었다. 전체 성공 이후 변경은 검증·인계 문서뿐이며 `git diff --check`를 확인한다. 이 로컬 검증 기록 작성 시점에는 미커밋 상태여서 본부 변경의 원격 CI 결과가 없었다. 이후 PR 생성 시 최신 HEAD의 CI를 별도로 확인한다.

**본부 방향 정정 브라우저 기록 (2026-09-28):** `bef94dd` 위의 방향 수정 코드로 기존 독립 검증 DB를 갱신했으며 중앙홀 동/1층 중앙 남 Exit 2개의 ID를 보존해 새 남/북 출구로 재사용했다. 새 일반 계정의 최초 위치는 대기실이었다. `남` 버튼으로 중앙홀, 다시 `남` 버튼으로 1층 중앙에 진입했다. Room 설명은 북쪽 중앙홀 통로와 남쪽 폐쇄 문을 표현했고 SURROUNDINGS 이동 버튼은 `서/동/북`뿐이었다. `남`·`남 보기`는 같은 폐쇄 안내를 출력하며 위치를 유지했고 방문 지도에는 `북: 본부 중앙홀`, `남: 폐쇄`가 표시됐다. `북` 직접 명령으로 중앙홀에 복귀하고 서쪽 부두·동쪽 중앙홀을 오갔다. 지원동에서 `귀환` 버튼의 목적지는 부두였다. 지원동에 다시 진입해 종료·재연결·로그인했을 때 지원동 위치가 유지됐다.

검증 탭의 console 오류/경고는 0개였고 화면 캡처는 Git 제외 `work/hq-direction.png`다. 검증 서버·탭을 종료했고 플레이 DB는 보존했다. JavaScript/CSS/글꼴 변경이 없어 정적 파일 수집을 반복하지 않았다. 실제 OS IME·전체 smoke는 이번에도 미실행이다.

**본부 방향 정정 자동 검증 (2026-09-28):** 기준 HEAD `bef94dd`와 위 방향 수정·bootstrap·테스트의 최종 미커밋 변경에서 `.\.venv\Scripts\python.exe scripts/dev.py check` 통과, `.\.venv\Scripts\python.exe scripts/dev.py test` 순수 72개·통합 199개, 총 271개 통과다. 통합 1153.144초, 근거 `work/hq-direction-full.log`. 본부 순수 개별 7개도 통과했다. 관련 통합 20개에서는 옛 출구 갱신 후 미사용 tag가 남는 회귀 1개를 발견했다(`work/hq-direction-related.log`). 해당 본부 tag 정리 후 실패한 bootstrap 테스트를 먼저 재실행해 1개 통과(10.257초, `work/hq-direction-migration.log`)했고, 최종 전체 검사에서 회귀가 없음을 확인했다. 테스트 실패는 이번 변경의 tag 정리 누락이었으며 환경 실패는 없었다. 전체 성공 후 실행 코드·테스트·의존성은 변경하지 않고 문서만 마무리한다. 최신 수정 커밋의 원격 CI는 푸시 후 별도로 확인하고 PR 설명에 기록한다.

### 본부 2단계 공용 승강기 확인

1. 신규 탐사자의 대기실에서 `남`으로 중앙홀, 다시 `남`으로 1층 중앙에 이동한다. 사방 이동 버튼은 서/동/북, 남쪽은 계속 폐쇄이며 주변 행동에 `승강기`가 있어야 한다.
2. 버튼 또는 `승강기`로 탑승한다. 실제 Room은 지원동 승강기, 현재 위치는 1층이다. 내부 버튼은 층 SSOT의 1층/2층/3층/옥상과 내리기이며 사방 출구는 없다.
3. `2층`과 `내리기`로 2층 중앙에 도착한다. 호출 버튼을 확인하고 같은 순서로 3층·옥상에 이동한다. 옥상에서도 호출할 수 있어야 한다. 각 층의 기존 북/남 폐쇄 문은 바뀌지 않는다.
4. 같은 층 버튼을 누르면 이미 그 층이라는 안내만 나온다. 동/서 복도·중앙홀·부두에는 호출 버튼이 없으며 승강기 밖의 `1층`/`2층`/`3층`/`옥상`/`내리기`는 일반 알 수 없는 명령으로 처리한다.
5. A를 승강기 내부에 두고 B가 다른 층에서 호출한다. A는 내부에 남고 현재 층과 웹 표시가 B의 층으로 함께 바뀌어야 한다. B도 같은 Room에 탑승한다. A의 층 선택이 양쪽 현재 위치에 반영되는지, A만 내릴 때 B가 내부에 남는지 확인한다.
6. 내부에서 접속을 끊고 다른 사용자가 층을 바꾼 후 재접속한다. 저장된 Room이 승강기이며 현재 공용 층으로 내리는지 확인한다. 서버 정상 재시작과 bootstrap 이후 현재 층을 보존해야 한다.
7. 승강기·상층·옥상 방문 후 `지도`가 오류 없이 표시되고 가짜 방향 출구가 없는지 확인한다. `귀환`은 옥상, 패배·의료·휴식은 의무실, 상점은 1층 보급품 상점·3층 무기점/방어구점이어야 한다. 보관·훈련은 3단계의 지원동 시설에 있다.
8. 데스크톱·좁은 화면에서 승강기 현재 위치와 버튼을 확인한다. 버튼과 직접 명령의 목적지·공용 층이 같고 두 사용자 상태가 갱신되는지, console 오류와 가로 넘침이 없는지 확인한다.

관련 자동 검사는 `world.test_elevator`와 `tests.test_elevator`다. `scripts/dev.py test tests.test_elevator --parallel 2 --reverse`로 실행 순서에 따른 shared attribute 누수가 없는지 확인한다. 최종 검증은 저장소 표준 `scripts/dev.py check`와 `scripts/dev.py test`를 사용한다. 아래 2단계 smoke 미실행은 당시의 판단이며, 현재 smoke의 의료·귀환 경로 변경과 검증은 4단계 기록을 따른다.

**승강기 자동 검증 (2026-09-28):** 최신 `origin/main=ada6487f254beb3a662340ce81fa75771092cce1`에서 시작한 `codex/hq-elevator`의 최종 실행 코드·테스트에서 다음을 확인했다. PR #14의 settings_test·메모리 SQLite·빠른 해시·병렬 fixture를 사용했고 인프라는 변경하지 않았다.

| 실행 명령 (저장소 루트, 별도 표시 제외) | 실제 결과 |
| --- | --- |
| `.\.venv\Scripts\python.exe scripts/dev.py check` | 통과 |
| `.\.venv\Scripts\python.exe scripts/dev.py test` | 순수 77개 0.071초·통합 213개 78.955초, 총 290개 통과. 통합 runner 88.978초, 실패/skip 없음 |
| `game`에서 `..\.venv\Scripts\python.exe -m unittest world.test_elevator world.test_headquarters world.test_rules` | 50개 통과, 0.094초 |
| `.\.venv\Scripts\python.exe scripts/dev.py test tests.test_elevator tests.test_headquarters tests.test_regions tests.test_web_state --parallel 2` | 관련 통합 31개 통과, 51.656초 (runner 65.791초) |
| `.\.venv\Scripts\python.exe scripts/dev.py test tests.test_elevator --parallel 2 --reverse` | 역순 8개 통과, 17.995초 (runner 27.391초). 한 TestCase 클래스여서 실제 worker는 하나이며 관련/전체 검사는 여러 worker 사용 |
| `scripts/dev.py test tests.test_text.SemanticTextTests.test_room_roles_come_from_objects_and_real_exits tests.test_environment.EnvironmentWebTemplateTests --parallel 2` (같은 Python) | 최초 전체에서 실패한 기존 기대값 2건을 수정한 뒤 2개 통과, 8.308초. 이후 위 최종 전체 통과 |
| `node --check game/web/static/webclient/js/primal.js`, `git diff --check` | 통과 |

최초 전체의 두 실패는 모든 Room에 명령 token이 없다는 가정과 이전 JS query 주소였다. 서버 승강기 actions와 새 `?v=elevator`를 정확히 확인하도록 갱신했으며 기존 assertion을 무관하게 느슨하게 만들거나 삭제하지 않았다. 근거는 `work/elevator-final-full.log`, `work/elevator-related.log`, `work/elevator-reverse.log`, `work/elevator-failed-recheck.log`다. 전체 성공 후 실행 코드·테스트·의존성은 고정하고 문서만 마무리했다. 최신 PR HEAD CI는 PR Validation과 인계 원격 기록에서 별도로 확인한다.

**승강기 브라우저 검증 (2026-09-28):** 플레이 DB와 분리한 SQLite·일반 계정 두 개로 대기실→중앙홀→1층, 네 정류 층 호출 버튼과 내부 층 선택/내리기를 확인했다. 직접 `3층` 입력과 버튼이 같은 공용 상태를 바꿨고 외부 1층 호출에도 기존 승객은 내부에 남았다. 두 계정의 현재 위치가 함께 갱신되며 한 명만 3층/옥상으로 하차할 수 있었다. A 로그아웃 후 B가 옥상으로 이동하고 A가 재접속했을 때 내부의 현재 위치는 옥상이었으며 옥상으로 내렸다. 방문 지도에는 승강기·2/3층·옥상이 표시되고 가짜 방향 출구는 없었다. 1층 남쪽 폐쇄, 서쪽 복도의 호출 버튼 없음/`2층` unknown 처리, `귀환`의 부두 목적지와 기존 부두 서비스 표시를 확인했다.

game과 별도 검증 서버에서 정적 파일을 수집했고 JS는 `?v=elevator`, CSS는 기존 `?v=lighting`을 사용한다. 데스크톱과 실제 390px 화면에서 현재 층·다섯 내부 버튼을 확인했다. 390px 문서 clientWidth/scrollWidth는 375/375px, 로그는 339/339px로 가로 넘침이 없었다. 근거 `work/elevator-390.png`, `work/elevator-390-actions.png`. 최초 화면 크기 설정이 반영되지 않았던 캡처는 390px 근거로 사용하지 않았다. 확인한 console에는 앱 코드 오류가 없었으나 로그인 시 암호 자동완성 확장 프로그램의 `insertBefore` 오류가 있었고 확장 UI가 조작을 일시 차단했다. 앱 오류 0과 브라우저 전체 오류 0을 구분한다.

별도 서버를 정상 종료·재시작한 뒤 B가 재접속했을 때 실제 Room은 승강기, 공용 현재 층은 종료 전과 같은 옥상이었고 `내리기`로 옥상에 도착했다. 이후 검증 서버와 임시 탭을 종료하고 DB/로그는 보존했다. 전체 smoke 미실행 — 기존 smoke의 사냥/귀환 Flow를 변경하지 않았고 승강기는 관련 자동/브라우저 검증으로 확인했다. 실제 OS 한글 IME·강제 프로세스 종료·운영 배포 검증은 미실행이다. 통합 테스트로 bootstrap 반복/invalid state 정규화·DB cache reload·재접속·실패 rollback을 확인했다. 검증 계정·DB·로그·수집 파일은 Git에 포함하지 않는다.

### 본부 3단계 보관·훈련 이전 확인

1. 부두에서 `보기`와 SURROUNDINGS를 확인한다. 윤대장·상점은 남고 보관상자·개인 보관함·훈련관·의료 객체는 없어야 한다. 기존 보관·훈련 명령은 현재 대상이 없다는 기존 오류로 실패하고 소지품·성장·크레딧이 변하지 않아야 한다.
2. 부두에서 `동` → `남` → `서` → `북`으로 1층 보관실에 도착한다. 두 보관 객체의 본문·SURROUNDINGS·보기 버튼을 확인한다. `보관상자에 붕대 넣어`, `보관상자에서 붕대 꺼내`, `개인 보관함에 붕대 넣어`, `개인 보관함에서 붕대 꺼내`는 기존 수량·권한 규칙을 따라야 한다.
3. A/B가 같은 개인 보관함을 보아도 자신의 물품만 확인한다. 공용 물품은 서로 꺼낼 수 있다. 빈 상자·장착 예약·임무 물품·실패 rollback은 관련 자동 검사에서 확인한다.
4. 보관실에서 `남` → `동` → `승강기` → `2층` → `내리기` → `동` → `북`으로 훈련실에 도착한다. 탐사대 훈련관이 실제로 보이고 웹의 특성과 기술 패널이 활성화되어야 한다.
5. `탐사대 훈련관 대화`, `힘 1 배분`, `강타 배워`, `특성 재분배`, `기술 재분배`, `전체 재훈련`을 기존 비용·포인트 규칙으로 확인한다. 버튼과 직접 명령의 결과가 같아야 한다. 전투 중·unsafe Room·NPC 없음/가시성 차단에서는 훈련 불가임을 자동 검사로 확인한다.
6. 이전 전후 bootstrap을 두 번 실행해 세 stable ID와 DB object ID·alias, 공용 contents와 A/B 개인 storage, 기존 위치·장비·성장·방문 기록이 보존되는지 확인한다. `stale_definitions()`는 빈 목록이어야 한다. 이 절차는 별도 검증 DB 또는 자동 테스트에서 수행하며 플레이 DB를 초기화하지 않는다.
7. 보관·훈련 이전은 유지하며 현재 귀환·패배·휴식은 4단계, NPC 상점은 6단계 절차를 따른다. 윤대장은 부두에 유지한다. 웹은 서버의 interactables/training_available을 사용하며 storage_room/training_room client 분기를 추가하지 않는다. console의 앱 오류도 확인한다.

자동 검사는 `tests.test_hq_services`의 실제 동선·객체 기반 권한·visibility/Web 일치·bootstrap 데이터 보존과 기존 item/growth/web/distant suite를 사용한다. 역순·병렬 검사는 `scripts/dev.py test tests.test_hq_services --parallel 2 --reverse`다. 아래 과거 1·2단계 기록은 해당 시점의 결과로 보존한다.

**서비스 이전 자동 검증 (2026-09-29):** fetch 후 `origin/main=7cf42145551ea364b5f1a1b69fa68c3e5567bee8`에서 시작한 `codex/hq-service-relocation`의 실행 코드·테스트 미커밋 변경을 검증했다. 기존 settings_test·메모리 SQLite·빠른 해시·병렬 runner와 WorldCommandTest를 유지했다. 직접 bootstrap 이전을 검증하는 한 클래스만 GameCommandTest를 사용한다.

| 실행 명령 (저장소 루트, 별도 표시 제외) | 실제 결과 |
| --- | --- |
| `.\.venv\Scripts\python.exe scripts/dev.py check` | 통과 |
| `.\.venv\Scripts\python.exe scripts/dev.py test` | 순수 78개 0.080초·통합 219개 78.633초, 총 297개 통과. 통합 runner 88.088초, 실패/skip 없음 |
| `game`에서 `..\.venv\Scripts\python.exe -m unittest world.test_headquarters world.test_elevator world.test_rules` | 관련 순수 51개 통과, 0.091초 |
| `.\.venv\Scripts\python.exe scripts/dev.py test tests.test_hq_services --parallel 2 --reverse` | 역순 통합 6개 통과, 10.204초 (runner 19.491초). 두 클래스가 별도 worker에서 실행됨 |
| `.\.venv\Scripts\python.exe scripts/dev.py test tests.test_lighting.LightingTests.test_dock_safe_lighting_and_normal_containers_visible_in_dark --parallel 2` | 이전 배치 기대값 수정 후 1개 통과, 2.557초. 이후 위 전체 검사 통과 |
| `.\.venv\Scripts\python.exe scripts/dev.py test tests.test_item_interactions.ItemInteractionTests.test_give_single_all_and_invalid_recipients_do_not_change_owners --parallel 2` | 최종 전체 이후 실제 NPC를 대상으로 계속 거절을 검증하도록 fixture 명시, 해당 1개 통과, 2.506초 (runner 11.083초) |
| `node --check game/web/static/webclient/js/primal.js`, `git diff --check` | 통과 |

첫 관련 통합 57개에서는 새 테스트의 오류 문구 기대값과 bootstrap의 다중 alias 갱신 문제가 실패했다. alias를 목록으로 전달하도록 수정해 `훈련관`/`교관`을 모두 보존하고 기존 대상 탐색 오류 semantics를 정확히 기대하도록 갱신했다. 최초 전체 검사의 조명 테스트는 옛 부두 상자 배치를 전제로 실패했다. 부두 조명·윤대장 검증을 유지하며 보관실 조명·실제 상자 가시성까지 검사하도록 바꾸고 해당 실패부터 재검증했다. 최종 전체 성공 이후 production 코드·설정·의존성은 바뀌지 않았다. 기존 전달 테스트가 실제 NPC 거절을 계속 검증하도록 부두 fixture를 명시한 뒤 해당 테스트만 추가 검증했으며 결과는 위 표와 같다. 무관한 assertion을 느슨하게 만들거나 테스트를 삭제하지 않았다. 근거는 Git 제외 `work/hq-services-related.log`, `work/hq-services-reverse.log`, `work/hq-services-lighting-recheck.log`, `work/hq-services-final-full-success.log`, `work/hq-services-give-recheck.log`다. 최신 PR HEAD CI는 PR Validation과 인계 원격 기록에서 별도로 확인한다.

**서비스 이전 브라우저 검증 (2026-09-29):** 기존 승강기 검증용 SQLite DB를 재사용했으며 플레이 DB는 읽거나 변경하지 않았다. 이전 전 부두의 세 실제 객체에 공용 붕대 4개/야전식량 2개, 두 일반 계정에 서로 다른 개인 storage를 준비했다. bootstrap을 두 번 실행한 뒤 세 DB object ID(134/135/137)·alias·전체 객체 수·공용 contents·두 profile과 기존 위치를 보존하고 새 배치와 빈 stale 감사를 확인했다. 정상 startup의 bootstrap에서도 상세 보기에 공용 물품과 A의 붕대 2개, B의 정제수 3개가 유지됐다.

Chrome에서 부두→중앙홀→1층 보관실의 실제 버튼과 명령 이동, 두 보관 객체의 본문/SURROUNDINGS/보기 버튼과 네 넣기·꺼내기 명령을 확인했다. 같은 개인 보관함에서 A/B가 자신의 물품만 보았으며 공용 상세도 정상 표시됐다. 보관실에서 승강기로 2층 훈련실에 도착해 훈련관 대화·활성 배분/학습/재훈련 버튼을 확인했다. +1 버튼과 직접 `힘 1 배분`이 각각 1점을 투자했고, `강타 배워` 버튼과 직접 명령은 각각 Rank 2/4크레딧 학습으로 같은 결과였다. 특성·기술 재분배와 전체 재훈련도 확인했다. 귀환은 부두였고 보관/훈련 대상 실패·웹 훈련 비활성, 기존 윤대장·상점·휴식은 유지됐다. 게임 명령어 기록에는 로그인 정보를 넣지 않았다.

game과 격리 서버의 정적 파일을 수집하고 실제 DOM의 JS `?v=hq-services`를 확인했다. 앱 코드 console 오류는 발견하지 않았으나 로그인 시 Chrome 확장 메시지 채널 종료 오류가 계정별 2건씩 관찰됐다. 브라우저 전체 오류 0으로 기록하지 않는다. 기존 포트 4301은 Windows 바인딩 10013 오류로 실행되지 않아 격리 서버만 5401/5402/5405/5406으로 바꿨다. 근거 화면은 `work/hq-services-storage.png`, `work/hq-services-training.png`이며 확인 후 임시 탭과 검증 서버를 종료했다. UI 레이아웃을 변경하지 않아 별도 좁은 화면 검증을 반복하지 않았다.

전체 smoke 미실행 — 현재 `scripts/smoke.py`에 보관/훈련 Flow가 없고 관련 자동/브라우저 검증으로 확인했다. 실제 OS 한글 IME·이번 변경의 서버 재시작 후 재접속·운영 플레이 DB 적용은 미실행이다. 저장 보존과 재접속 회귀는 자동 검증에 포함하며 2단계의 과거 재시작 브라우저 기록과 구분한다. 의료/귀환/사망·상점/경제와 승강기 production 코드는 이번에 개편하지 않았다.

### 본부 4단계 의료·복귀·패배 확인

1. 탐사 지역에서 비전투 `귀환` → 지원동 옥상을 확인한다. `승강기` → `2층` → `내리기` → `서` → `북`으로 의무실에 도착한다. 일반 귀환은 패배 목적지와 다르며 home은 계속 dock다.
2. HP가 부족할 때 의무관·침대가 본문/보기/SURROUNDINGS에 실제로 표시되고 `의무관 치료`/`침대 휴식` 버튼을 제공하는지 확인한다. 각 버튼과 직접 `치료`/`의무관에게 치료`/`휴식`/`침대에서 휴식`을 비교한다. 무료·즉시 full HP이며 크레딧·붕대·medicine 숙련은 그대로다. full HP에서 거절하고 상태를 저장하지 않는다.
3. 별도 DB의 낮은 HP fixture로 실제 Enemy 공격에 패배한다. 의무실로 이동, HP 1, 실제 최대 10크레딧 손실, combat 종료와 새 Web state를 확인한다. 자동 복구가 의무관/침대를 사용해 full HP를 주면 안 된다. 이후 직접 의료 서비스를 사용한다.
4. 실제 두 참가자 중 한 명만 패배할 때 다른 참가자는 사냥터에서 전투를 계속한다. move_to 실패 시 profile·location·combat membership·queued action·타이머와 DB/캐시가 이전 상태이며 구조 완료 알림이 없어야 한다. 이 경계는 자동 integration으로도 검증한다.
5. 의무실에서 `남` → `동` → `승강기` → `1층` → `내리기` → `북` → `서`로 부두에 도착한다. 윤대장은 유지하며 의료·상점 버튼은 없다. `치료`/`휴식`은 실제 대상 없음으로 실패한다. 다른 안전 Room으로 Doctor/Bed를 옮기면 서비스가 객체를 따라가며, unsafe/전투/hidden/view lock이면 Web/hint에서 사용 가능으로 표시하지 않는다.
6. 임시로 보이는 Doctor 두 명/Bed 두 개를 두고 bare 입력의 ambiguity를 확인한다. 이름·번호로 명시하면 한 대상만 쓰며 숨은 객체는 개수나 selector에 포함하지 않는다. 원거리 관찰은 의료 행동을 노출하지 않는다.

전체 smoke는 가입 rate limit의 610초 대기와 반복 실제 전투를 포함한다. production 가입 제한을 낮추지 않는다. smoke의 변경된 두 helper 경로는 위 실제 이동 integration과 별도 DB 브라우저에서 확인하고 전체 실행 여부는 시점별 결과에 따로 기록한다.

**자동 검증 (2026-09-29, 4단계 최종 코드):** 시작 기준은 `a10623ba92df9bcd412994fd3eb0a69a2f44e18b`, 브랜치는 `codex/hq-medical-lifecycle`이다. `scripts/dev.py check` 통과, `scripts/dev.py test` 순수 82개(0.069초)·통합 231개(79.003초), 총 313개 통과이며 실패/skip은 없다. 통합 runner는 88.001초다. 근거 `work/medical-final-full.log`. `scripts/dev.py test tests.test_medical --parallel 2 --reverse`도 11개 통과했다(12.440초, runner 21.135초, `work/medical-reverse.log`). 역순 검사는 마지막 presence/부두 안내 문구 조정 전이며 의료 실행 규칙은 같고 최종 전체에서 해당 조정도 확인했다. JS `node --check game/web/static/webclient/js/primal.js`, smoke AST syntax와 `git diff --check`도 통과했다. 최종 코드 이후의 문서 정리만으로 동일 게임 검사를 반복하지 않는다.

**브라우저 검증 (같은 날짜, 별도 SQLite DB):** 최종 정적 파일을 game과 별도 서버에서 수집했다. 일반 검증 계정이 HP 1/50크레딧으로 실제 어린청소룡을 공격해 패배했을 때 의무실 HP 1/40크레딧·전투 종료·구조 안내·의무관/침대 contextual 버튼을 확인했다. 의무관 버튼은 full HP 60을 주고 크레딧·붕대는 그대로였다. 직접 귀환과 웹 승강기 버튼으로 옥상→1층→부두에 도착했고 윤대장·상점이 남아 있었다. 부두에는 의료 버튼이 없고 직접 `휴식`은 대상 없음으로 실패했다. 실제 상점과 윤대장 대화도 정상 동작했다.

초지에서 실제 전투 승리 후 HP 47/60·48크레딧 상태로 직접 `귀환`하여 옥상에 도착했다. `승강기`·`2층`·`내리기`·`서`·`북`으로 의무실에 들어가 침대 버튼으로 HP 60/60 회복을 확인했고 크레딧·붕대·XP는 그대로였다. 다시 남→동→승강기 1층→북→서로 부두에 돌아갔다. 최종 객체 presence와 버튼 화면 근거는 `work/medical-final-browser.png`다. 앱 코드 console 오류는 발견하지 않았으나 Chrome의 비동기 listener 채널 종료 메시지가 2건 있었다. 서버·임시 탭은 종료하고 검증 DB/로그는 보존했으며 플레이 DB는 읽거나 수정하지 않았다.

전체 smoke 미실행 — 일반 계정 가입 rate limit의 610초 대기와 반복 실제 전투 때문에, 수정된 의료/귀환/구매 경로는 관련 자동 및 별도 DB 브라우저로 검증했다. 실제 OS 한글 IME·전체 서버 재시작 재접속·운영 DB 적용은 이번 수동 검증에서 수행하지 않았다. UI layout을 변경하지 않아 좁은 화면을 반복하지 않았다. 멀티플레이 패배·move False 및 부분 이동 rollback은 자동 integration에서 확인했으며 수동으로 확인한 결과와 구분한다.

**원격 검증 (같은 날짜, 구현 HEAD):** [PR #17](https://github.com/wonmin82/primal-zone/pull/17)의 `61c0effd4f0295394fd25daba22c3949f64f8967`과 [Game checks](https://github.com/wonmin82/primal-zone/actions/runs/36498164252)의 headSha가 같고 success임을 확인했다. 원격 `uv run python scripts/dev.py check` 통과, `uv run python scripts/dev.py test --parallel 2` 순수 82개(0.046초)·통합 231개(86.100초), 총 313개 통과·runner 92.199초다. 이 결과를 문서 전용 후속 커밋에 기록하며 최종 문서 HEAD의 CI는 별도 확인하여 PR Validation에 반영한다. 로컬 결과와 CI 시간을 구분하며 같은 코드의 로컬 전체 검사를 반복하지 않는다.

## 3. 첫 임무 끝까지 진행하기

### 3-1. 장비와 재료 준비

빠른 테스트를 마친 계정으로 이어서 진행할 수 있습니다.
부두에서 `북` → `어린청소룡 공격`으로 사냥하고, 전투가 끝난 뒤 `귀환` → `승강기` → `2층` → `내리기` → `서` → `북`으로 의무실에 가서 `휴식`으로 회복합니다. 의무실에서 `남` → `동` → `승강기` → `1층` → `내리기` → `북` → `서`로 부두, 다시 `북`으로 초지에 돌아갑니다.
경험치·크레딧은 처치 시 받습니다. 시체에서 회수부품을 가져온 뒤 귀환하세요. 같은 장소의 적은 처치 후 45초에 다시 나타납니다. 기다리는 동안 초지와 수송차를 오가며 다른 spawn을 사냥할 수 있습니다.

강철마체테를 얻으면 `강철마체테 무장`을 입력하고 `상태`에서 공격력이 증가했는지 확인합니다.
드롭을 기다리지 않고 회수부품을 지원동 1층 자원 정산소에서 크레딧으로 정산한 뒤 지원동 3층 무기점·방어구점에서 구매해도 됩니다.

| 물품 | 구매 명령과 가격 | 효과 |
| --- | --- | --- |
| 강철마체테 | `강철마체테 구매`: 60 크레딧 | 무기 공격 +6 |
| 강화조끼 | `강화조끼 구매`: 65 크레딧 | 방어구 방어 +4 |
| 탐사카빈 | `탐사카빈 구매`: 130 크레딧 | 무기 공격 +10 |
| 붕대 | `붕대 구매`: 8 크레딧 | 1개로 체력 최대 35 회복 |

구매는 크레딧으로 한 번에 1개이며, 장비를 얻은 뒤 별도로 `무기이름 무장` 또는 `방어구이름 착용`을 입력합니다.
표의 장비 효과는 해당 장비 자체의 수치입니다. 교체할 때는 기존 장비 효과를 빼고 새 효과를 적용합니다.
예를 들어 낡은마체테에서 강철마체테로 바꾸면 공격력이 4 증가합니다.
**발전기 수리에 필요한 회수부품 3개는 별도로 확보하세요.**

### 3-2. 탐험과 발전기 복구

아래 경로는 부두에서 시작합니다. 아직 임무를 받지 않았다면 먼저 `윤대장 대화`을 입력합니다.

| 순서 | 입력 또는 조작 | 정상 결과 |
| --- | --- | --- |
| 1 | `북` → `동` | 초지를 거쳐 부서진 수송차에 도착합니다. |
| 2 | `보급상자 조사` | 붕대 2개를 받습니다. 이미 받은 계정은 추가로 받지 못합니다. |
| 3 | `서` → `북` → `동` | 초지, 발톱 자국 오솔길을 거쳐 폐쇄된 관리동에 도착합니다. |
| 4 | `정비기록 조사` | 발전기 수리 방법을 읽고 임무 안내가 바뀝니다. |
| 5 | `동` | 멈춰 선 발전실에 도착합니다. |
| 6 | 회수부품 3개 이상을 가진 상태에서 `발전기 수리` | 부품 3개가 소모되고 경험치 50을 받습니다. 통신탑 능선 진입이 열립니다. |
| 7 | `임무`, `지도` | 다음 목표가 우두머리 처치로 바뀌고, 방문한 장소와 연결 방향이 표시됩니다. |

방에 적이 있어도 직접 공격하기 전에는 전투가 시작되지 않습니다.
발전실의 경비기 처치는 수리의 필수 조건이 아닙니다.

### 3-3. 솔로 보스와 임무 보상

권장 준비는 **Lv.4 이상, 탐사카빈 무장·강화조끼 착용, 체력 최대, 붕대 3개 이상**입니다.
Lv.4에 필요한 누적 경험치는 240입니다. 부족하면 사냥과 휴식을 반복합니다.
비전투 상태로 귀환하면 옥상입니다. 의무실의 치료·휴식으로 회복하고 승강기 1층→중앙홀→부두에서 장비를 준비합니다.

1. 부두에서 `북` → `북` → `북` → `북`으로 이동합니다. 초지 → 오솔길 → 물안개 습지 → 통신탑 능선 경로입니다.
2. `능선의우두머리 공격`로 보스전을 시작합니다.
3. 기본 공격은 자동으로 진행됩니다. 강타가 준비되어 있으면 `강타`를 입력합니다.
4. **“우두머리가 몸을 낮춘다”**는 예고가 나오면 다음 차례 전에 `방어`를 입력합니다. 그 차례에는 다른 행동을 덮어쓰지 않습니다.
5. 돌진 대응 외의 차례에 체력이 부족하면 `회복`합니다. 회복은 다음 차례의 기본 공격을 대신하며, 이후 적의 공격은 받습니다.
6. 솔로 승리 시 경험치 130과 크레딧 50을 받습니다. `시체에서 모두 가져`로 우두머리송곳니와 회수부품 1개를 회수합니다.
7. `귀환` → `승강기` → `1층` → `내리기` → `북` → `서` → `윤대장 대화`로 보고합니다. 추가로 경험치 100, 크레딧 100, 붕대 3개를 받습니다.
8. `임무`에 **통신탑 복구 완료**가 표시되는지 확인합니다. 다시 `윤대장 대화`을 입력해도 보상이 늘어나지 않아야 합니다.

**통과 기준:** 다른 이용자의 도움 없이 장비를 확보하고, 발전기를 복구하고, 보스를 처치하여 임무 보상을 한 번 받습니다.
완료 후에도 자유 사냥과 장비 수집을 계속할 수 있습니다.

## 4. 기능별 추가 테스트

각 행의 준비 조건을 먼저 맞춥니다. 표는 결과를 기록하기 위한 체크리스트이며, 모든 항목을 이미 통과했다는 뜻은 아닙니다.

### 전투·성장·장비

| ID | 준비와 확인 방법 | 정상 결과 |
| --- | --- | --- |
| C-01 | 초지에서 어린청소룡과 교전 중 `어린청소룡 공격`을 짧게 몇 번 반복합니다. | 적 체력·전투 차례가 초기화되지 않고, 입력 횟수만큼 공격이 추가되지 않습니다. |
| C-02 | 강타가 실제 실행된 직후, 다음 차례 전에 다시 `강타`합니다. | 준비되지 않았다는 안내가 나옵니다. 실제 강타 실행 후 7.5초가 지나면 다시 예약할 수 있습니다. |
| C-03 | 교전 중 `강타`를 예약한 뒤 같은 차례 안에 `방어`로 바꿉니다. | 마지막으로 정상 접수된 행동 하나만 다음 차례에 적용됩니다. 방어 중에도 기본 공격은 합니다. |
| C-04 | 체력이 줄고 붕대가 있는 상태에서 전투 중 `회복`합니다. | 다음 차례에 붕대 1개를 소모하고 최대 35를 회복하며, 그 차례의 기본 공격은 쉽니다. 적의 공격 피해는 별도로 적용됩니다. |
| C-05 | 비전투 상태로 의무실에서 체력을 채운 후 `회복`합니다. | 체력이 가득하다는 안내가 나오고 붕대가 소모되지 않습니다. |
| C-06 | 적 체력이 남은 전투 중 출구 방향, `귀환`, 보유한 다른 무기의 `무장`과 방어구의 `착용`을 각각 시도합니다. | 전투 중이라는 안내와 함께 이동·귀환·장비 변경이 거절됩니다. |
| C-07 | 전투 중 `도주` 후 같은 적을 다시 공격합니다. | 도주 시 보상이 없고 참여·점유가 정리됩니다. 즉시 재공격하면 남은 HP로 이어지고, 참가자가 없는 상태로 마지막 활동 후 15초가 지나면 최대 HP로 복원됩니다. |
| C-08 | 별도 테스트 계정으로 강한 적과 싸워 패배합니다. | 의무실로 구조되고 체력 1로 최소 회복됩니다. 전투 소속·예약 행동·타이머는 정리하며 다른 참가자는 유지합니다. 장비·경험치·소지품·진행은 보존하며 최대 10크레딧이 차감되고 잔액은 음수가 되지 않습니다. |
| C-09 | 레벨 상승 직전과 직후 `상태`를 비교합니다. | 레벨·최대 체력·공격력이 증가하고 화면에 반영됩니다. 방어력은 레벨에 따라 단계적으로 증가합니다. |
| C-10 | 사냥을 멈춘 상태에서 무기·방어구를 교체합니다. | 착용 표시와 공격·방어 수치가 함께 갱신됩니다. 소유하지 않은 장비는 착용할 수 없습니다. |
| C-11 | 해당 상품의 실제 상인에게 보유 크레딧보다 비싼 장비를 구매합니다. | 구매가 거절되고 크레딧·가방이 변하지 않습니다. |
| C-12 | 자원 정산소에서 보유량을 넘겨 교환한 뒤 1개·N개·모두 정산합니다. 정산한 크레딧으로 지원동 상인에게 구매합니다. | 부족/잘못된 수량은 전체 상태 불변. 정산은 부품 1개당 10C, 모두는 가방 scrap 0. 장비는 크레딧 구매로만 지급됩니다. |
| C-13 | 장비와 체력을 준비한 뒤 오솔길에서 `갈퀴사냥룡 공격`, 발전실에서 `고장난경비기 공격`로 각각 승리합니다. | 갈퀴사냥룡은 경험치 38·크레딧 14, 경비기는 경험치 55·크레딧 20을 줍니다. 각각 부품 1개를 주고 강화조끼·탐사카빈은 확률로 나옵니다. |

### 탐험·임무

| ID | 준비와 확인 방법 | 정상 결과 |
| --- | --- | --- |
| Q-01 | 발전기를 복구하지 않은 계정으로 습지에서 `북`을 입력합니다. | 능선 진입이 거절됩니다. 발전기 복구 후에는 같은 경로로 진입할 수 있습니다. |
| Q-02 | 임무를 받되 정비기록은 읽지 않고, 부품 3개를 가진 상태로 발전실에서 수리합니다. | 정비기록을 먼저 조사하라는 안내가 나오며 부품이 소모되지 않습니다. |
| Q-03 | 발전기를 복구한 뒤 같은 장소에서 다시 수리합니다. | 추가 부품 소모와 경험치 지급이 없습니다. |
| Q-04 | 수송차에서 보급상자를 두 번 조사하고, 재접속한 뒤 한 번 더 조사합니다. | 해당 캐릭터는 첫 조사 때만 붕대 2개를 받습니다. |
| Q-05 | 보스 처치 전에 부두에서 윤대장에게 보고를 시도합니다. | 남은 목표를 안내하고 완료 보상을 주지 않습니다. |
| Q-06 | 임무 보상을 받은 뒤 재접속하고 윤대장과 다시 대화합니다. | 완료 상태가 유지되며 경험치·크레딧·붕대를 중복 지급하지 않습니다. |
| Q-07 | 새 장소 방문 전후 `지도`를 확인합니다. | 방문한 장소만 이름이 표시되고, 연결된 미방문 장소는 미탐사로 표시됩니다. |

### 저장·재접속

| ID | 준비와 확인 방법 | 정상 결과 |
| --- | --- | --- |
| S-01 | 비전투 상태에서 위치·체력·경험치·크레딧·가방·착용 장비·임무를 기록합니다. `종료` 후 같은 계정으로 로그인합니다. | 기록한 상태가 유지됩니다. |
| S-02 | 적이 살아 있는 교전에서 한 차례 진행 직후 `종료`합니다. 잠시 뒤 같은 계정으로 로그인합니다. | 개인 전투 입력과 공유 적의 참여에서 빠집니다. 파티와 성장·장비는 유지됩니다. 재접속 후 살아 있는 상대를 다시 지정합니다. 적 HP는 다른 참여자 또는 유휴 회복에 따라 달라질 수 있습니다. |
| S-03 | 전투 도중 브라우저 탭을 닫고 잠시 후 다시 접속합니다. | 서버가 연결 종료를 인지한 뒤 전투가 멈춥니다. 종료 인지 전 차례가 진행될 수 있으므로 탭을 닫기 직전 값과 차이를 구분합니다. 이후 `공격` 없이 추가 보상이 쌓이지 않아야 합니다. |
| S-04 | S-02처럼 교전을 저장하고 로그아웃한 뒤 서버를 정상 종료·시작합니다. 같은 계정으로 접속합니다. | 위치·진행·파티는 복원되고 전투 참여는 해제됩니다. 시체·재생성·보호 기한은 저장된 시각으로 정리됩니다. 공격 대상을 다시 지정하기 전에는 자동 사냥하지 않습니다. |

S-04는 다른 테스트 참여자도 로그아웃한 뒤 개발 PC의 PowerShell에서 진행합니다.
아래 명령을 각각 실행하고 종료 완료, 시작 완료를 확인합니다.

```powershell
Set-Location -LiteralPath 'E:\Work\primal-zone'
.\.venv\Scripts\python.exe scripts/dev.py stop
.\.venv\Scripts\python.exe scripts/dev.py start
```

### 두 사람 접속과 웹 화면

두 사람 테스트는 개발 PC에서 일반 창과 시크릿 창 또는 서로 다른 브라우저를 사용하면 됩니다.
서로 다른 일반 계정 A와 B로 접속합니다.

| ID | 준비와 확인 방법 | 정상 결과 |
| --- | --- | --- |
| U-01 | 두 계정이 같은 장소에서 `테스트 메시지 말`과 `'테스트 메시지`를 각각 입력합니다. | 두 방식 모두 같은 장소의 두 계정에 발신자 이름과 메시지가 표시됩니다. 닫는 따옴표는 필요하지 않습니다. |
| U-02 | B가 다른 장소로 이동한 뒤 A가 다시 말합니다. | 다른 장소의 B에게 방 채팅이 전달되지 않습니다. |
| U-03 | 두 계정이 초지에서 각각 어린청소룡을 사냥합니다. | 같은 파티라면 하나의 HP를 공유하며 합동 사냥합니다. 다른 그룹이라면 먼저 점유한 그룹만 일반 적을 공격할 수 있습니다. 보스는 여러 그룹에 공개됩니다. |
| U-04 | 두 계정이 수송차에서 각각 처음 보급상자를 조사합니다. | 두 계정 모두 붕대 2개씩 받을 수 있습니다. |
| U-05 | `접속자`를 입력합니다. | 접속자 목록을 조회할 수 있습니다. |
| U-06 | 한글을 조합 중인 상태에서 Enter를 누른 뒤, 조합이 끝난 명령을 실행합니다. | 조합 중인 글자가 명령으로 조기 전송되지 않고 완성한 명령이 정상 실행됩니다. |
| U-07 | 명령을 몇 개 입력하고 입력창에서 ↑·↓를 누릅니다. | 입력했던 명령을 앞뒤로 불러올 수 있습니다. |
| U-08 | 주변 행동 버튼과 동일한 텍스트 명령을 각각 사용합니다. | 이동·사냥·조사·착용 등 같은 행동으로 처리됩니다. |
| U-09 | 브라우저 화면 폭을 약 390px로 줄입니다. | 상태, 기록, 명령 입력과 전투 버튼을 사용할 수 있고, 아래로 스크롤해 임무·장비를 볼 수 있습니다. |
| U-10 | 로그인을 잘못된 비밀번호로 시도한 뒤 올바른 정보로 접속합니다. | 실패 이유가 표시되고 재시도할 수 있습니다. 비밀번호가 게임 기록에 출력되지 않습니다. |
| U-11 | `'어린청소룡 공격`, `'안녕하세요 말`, `할 말이 있어요 말`을 입력합니다. | 각각 `어린청소룡 공격`, `안녕하세요 말`, `할 말이 있어요`가 채팅으로 전달되고 게임 행동은 실행되지 않습니다. |
| U-12 | `말`, `'`만 입력하거나 301자 채팅을 입력한 뒤 300자 채팅을 입력합니다. | 빈 내용과 301자는 안내와 함께 거부하고, 300자는 전달합니다. |
| U-13 | `공격 어린청소룡`, `구매 붕대`, `말 안녕하세요`를 입력합니다. | 새 문법 안내가 나오며 전투·구매·채팅은 실행되지 않습니다. |
| U-14 | 소유한 장비를 `강철 마체테 무장`과 `강철마체테 wield`로 무장합니다. | 공백이 있는 이름과 별칭도 대상 뒤에 행동을 쓰면 정상 처리됩니다. |
| U-15 | `connect 서버 안내 말`을 입력한 뒤 `connect 계정 시험비밀번호`를 입력합니다. 실제 비밀번호는 사용하지 않습니다. | 첫 입력은 채팅으로 전달되고, 두 번째 입력은 전용 접속창 안내만 나오며 게임 기록과 ↑·↓ 입력 기록에 남지 않습니다. |

이용자 간 거래, 장비 강화·판매, Need/Greed 분배와 외부 배포는 현재 구현 범위에 포함되지 않습니다.
해당 메뉴가 없는 것은 이 버전의 테스트 실패로 기록하지 않습니다.

## 깊은 밀림 수동 플레이

첫 임무를 완료해 윤대장에게 보고한 일반 탐사자로 통신탑 능선의 북쪽을 이동한다. 보고 전에는 밀림 입구 진입이 거절되어야 한다. 기존 캐릭터의 첫 임무·장비·방문 기록은 그대로 남아야 한다.

| 순서 | 행동 | 기대 결과 |
| --- | --- | --- |
| 1 | 능선에서 `북`, 밀림 입구에서 `선발대 길잡이 대화` | 새 지역 진입과 두 번째 임무 시작. `지도`에서 두 지역이 구분된다. |
| 2 | `북` → `관측 표식 조사` | 관측소 단서가 기록된다. 관측소에서 `동`으로 거목 군락에 이를 수 있다. |
| 3 | 거목 군락에서 `북` | 수위 표식을 아직 확인하지 않았다면 연구구역 진입이 거절된다. |
| 4 | 거목 군락에서 `남` → `수위 표식 조사` → 다시 `수위 표식 조사` → `북` → `신호 장치 조사` → `가방` | 표식을 반복 조사해도 신호전지는 한 개만 지급된다. 신호 장치가 전지 한 개를 소비하고 문을 열며, 가방에는 전지가 남지 않는다. 문이 열린 뒤 수위 표식을 다시 조사해도 전지를 지급하지 않는다. 문이 닫힌 상태에서 전지를 잃었다면 표식을 다시 조사해 한 개를 확보할 수 있다. |
| 5 | 밀림 입구에서 `서` → `늪지 보급품 조사` | 선택 분기에서 붕대 2개를 한 번만 받는다. 그늘추적룡을 사냥할 수 있다. |
| 6 | 거목 군락에서 `북` → `북` | 연구구역 외곽을 지나 포식자 둥지에 도착한다. |
| 7 | `정글도 무장`, `중장방호복 착용`, 붕대 준비 후 `밀림의포식자 공격` | 공용 보스의 공유 HP·4차례 도약·시체·보호 전리품이 기존 규칙대로 동작한다. 준비한 한 명만으로도 완료할 수 있다. |
| 8 | 밀림 입구로 돌아가 `선발대 길잡이 대화`, `임무` | XP 120·120크레딧·붕대 3개를 한 번만 받고 두 임무의 완료 상태가 보인다. |
| 9 | 종료 후 재접속, 가능하면 서버 재시작 후 재접속 | 임무·발견·가방·방문 기록과 기존 파티·월드 객체가 유지된다. |

데스크톱과 약 390px에서 신규 Room 문장, 순수 텍스트 방향도, SURROUNDINGS 이동 버튼, 적/NPC/객체 의미별 색, `지도`·`임무`, 시체·전리품을 확인한다. 클릭한 방향과 직접 입력한 같은 텍스트 방향 명령은 동일한 서버 제한을 적용해야 한다. 현재 플레이 DB를 지우지 말고 별도 일반 계정과 테스트 DB를 사용한다.

2026-09-24 격리 DB의 브라우저 검증에서는 위 경로를 따라 두 표식 조사, 신호전지 1개만 지급·문 개방 시 소비, 보스 예고·특수 공격·처치, 시체 회수, 길잡이 보고·보상 1회 지급을 확인했다. 늪지 보급품의 중복 지급 거부와 방향 버튼 이동도 확인했다. 데스크톱(1366px)에서는 수몰 도로 화면과 방향도를, 모바일(390px)에서는 탐사 동선과 지도·임무·가방·주변 행동을 확인했으며 가로 넘침은 없었다. 실제 OS 한글 IME 조합, 데스크톱의 보스 화면, 보스 예고 직후 방어 피해 감소는 이번 브라우저 실행에서 확인하지 못했다.

## 5. 멀티플레이어·생명주기 시나리오

서로 다른 일반 계정 A/B를 두 창에 만들고, 점유·전리품 거부에는 파티 밖 C도 준비합니다. 공용 보스의 두 파티 분배는 D를 추가하여 A/B와 C/D 두 파티로 진행합니다. 같은 계정의 두 창은 서로 다른 참가자를 대신하지 못합니다. 표의 시각은 처치 시각 기준이며 서버 주기 검사 때문에 화면 변경에 수 초 차이가 날 수 있습니다. 이 표는 실행 절차이며 통과 기록이 아닙니다.

| 순서 | 조작 | 기대 결과 |
| --- | --- | --- |
| M-01 | 두 캐릭터 A/B 생성·접속 | 한글 이름과 개인 초기 장비가 각각 표시됩니다. |
| M-02 | A가 `B 파티초대`, B가 `파티수락` | 두 창에 같은 파티와 두 멤버가 표시됩니다. 버튼도 같은 명령을 보냅니다. |
| M-03 | `파티` 확인, B가 C 초대·A 제외 시도 | A가 리더이며 일반 멤버의 관리 명령은 거절됩니다. |
| M-04 | 둘 다 초지에서 `어린청소룡 사냥` | 같은 적 HP가 줄고 적 공격 타이머는 하나입니다. 두 번째 탐사자는 첫 처치 전에 공격에 참여해야 합니다. |
| M-05 | 교전 중 파티 밖 C가 같은 적 공격 | 다른 파티와 교전 중이라는 안내로 거절됩니다. 공격 버튼도 비활성화됩니다. |
| M-06 | 두 명 모두 피해를 준 뒤 처치 | 각각 경험치 11·크레딧 4를 받습니다. 참여하지 않은 파티원은 받지 않습니다. |
| M-07 | 처치 직후 보기·가방 확인 | 시체가 하나 보이고 적 사냥 버튼이 사라집니다. 아이템은 아직 가방에 없습니다. |
| M-08 | B가 `시체에서 모두 가져` | 각 아이템이 배정된 탐사자에게 갑니다. 다음 아이템/처치에서도 순번이 이어집니다. 드롭 하나만 나오면 여러 처치에 걸쳐 순번을 확인합니다. |
| M-09 | 다른 처치의 시체에서 C가 가져 시도 | 처치 후 120초 보호 중에는 거부됩니다. |
| M-10 | 시체를 회수하지 않고 30초 기다리기 | 시체가 없어지고 남은 아이템만 바닥에 나타납니다. |
| M-11 | 보호 중 A/B의 `회수 부품 가져` / `모두 가져` | 지정 배정자에게 지급됩니다. C는 여전히 거부됩니다. 공백 없는 이름도 동작합니다. |
| M-12 | 다른 바닥 아이템을 처치 후 120초까지 보존하고 C가 회수 | 보호가 종료되어 C에게 지급됩니다. 시체 소멸 시각부터 120초를 다시 세지 않습니다. |
| M-13 | 처치 후 45초 보기 | 같은 spawn의 적이 최대 HP로 하나만 재생성되고 바닥 전리품은 유지됩니다. |
| M-14 | A가 `B 파티제외`, 재초대·수락 | B가 제외되며 교전 중이었다면 참여도 정리됩니다. 다시 가입할 수 있습니다. |
| M-15 | A가 `B 파티장위임`, B가 탈퇴 | B에게 리더가 넘어갔다가 가장 먼저 남아 있던 A에게 승계됩니다. 마지막 멤버 탈퇴 시 파티가 없어집니다. |
| M-16 | A/B와 C/D가 각각 파티 구성, 각자 발전기 복구 후 능선 보스 합동 공격 | 두 그룹 모두 참여하고 동일 HP·차례·돌진 예고를 봅니다. |
| M-17 | 각 그룹이 실제 피해를 준 뒤 보스 처치 | 전체 경험치 130·크레딧 50이 그룹 기여 비중으로, 그룹 내부에서는 균등 분배됩니다. 정수 나머지는 결정적 순서로 지급됩니다. |
| M-18 | 두 명 이상의 적격 참가자가 각자 임무 확인·부두 보고 | 각자 boss_defeated 조건이 충족됩니다. 미참여·이탈·오래 활동하지 않은 계정은 보스 크레딧이 없습니다. |
| M-19 | 리더 접속 종료 후 재접속 | 리더 변경 없이 파티·개인 기록이 유지됩니다. 교전 참여는 종료되며 재접속 후 새로 상대를 지정합니다. |
| M-20 | 남은 시체·초대가 있는 상태로 서버 종료, 만료 후 시작 | 초대 만료, 시체→바닥, 적 재생성, 보호 종료가 저장된 시각대로 처리됩니다. 다시 시작해도 아이템이 복제되지 않습니다. |

초대 경계도 확인합니다: 자기 자신·없는 이름·이미 소속된 탐사자·정원 4명 초과는 거절, 중복 초대는 안전, `파티거절`과 60초 만료 뒤 `파티수락`은 가입을 만들지 않아야 합니다. 재생성/시체 테스트를 위해 플레이 DB를 삭제하거나 초기화하지 않습니다.

390px에서는 파티 패널·전리품 버튼·명령 입력을 스크롤로 이용할 수 있고 가로 넘침이 없어야 합니다. 보조 안내·상태·버튼을 포함한 글씨는 최소 14px이며, 본문과 명령 입력은 16px를 유지합니다. 글꼴은 Neo둥근모 Code로 표시되고 외부 CDN 요청이 없어야 합니다. 장소 설명의 시체·바닥 아이템 행에는 이름만 표시하고 회수 명령은 주변 행동 버튼으로 제공합니다. 실제 OS 한글 IME 조합은 텍스트 붙여넣기나 가상 composition 이벤트와 별도로 검증합니다.

## 6. 자동 테스트 실행

개발 PC의 PowerShell에서 실행합니다. 명령이 끝난 직후 `$LASTEXITCODE`가 `0`이면 정상 종료입니다.

### 코드 검사와 규칙·통합 테스트

게임 서버를 켜지 않아도 실행할 수 있습니다.

```powershell
Set-Location -LiteralPath 'E:\Work\primal-zone'
.\.venv\Scripts\python.exe scripts/dev.py check
.\.venv\Scripts\python.exe scripts/dev.py test
```

| 검사 | 확인하는 내용 | 현재 정상 출력 |
| --- | --- | --- |
| `check` | Ruff 코드 검사 | `All checks passed!` |
| `test` 첫 단계 | 전투·장비·성장·보상·지도 연결·솔로 보스 등 규칙 검사 | 실제 출력의 `Ran N tests` 다음 `OK` |
| `test` 두 번째 단계 | 월드 생성, DB 저장, 실제 입력 문법·채팅·임무, 인증 입력과 명령 권한 등 통합 검사 | 실제 출력의 `Ran N tests` 다음 `OK` |

규칙 테스트와 통합 테스트를 모두 확인합니다. 첫 단계가 실패하면 다음 단계가 실행되지 않습니다.
통합 테스트는 `server.conf.settings_test`의 메모리 SQLite DB와 테스트 전용 빠른 해시를 사용합니다. 플레이 DB와 운영 인증 설정은 변경하지 않습니다. Windows 병렬 실행에서 Django가 만드는 임시 DB 복제본은 종료 시 제거됩니다.
기본 통합 실행은 CPU 수에 따라 최대 4개 프로세스를 사용합니다. 각 프로세스는 Evennia를 초기화하고 독립 DB를 사용합니다. GitHub Actions의 `Game checks`는 PR과 main push에서 동일한 검사와 2개 프로세스의 통합 테스트를 실행합니다.

```powershell
# 전체 검사를 직렬로 실행해 비교하거나 실패를 조사합니다.
.\.venv\Scripts\python.exe scripts/dev.py test --parallel 1
# 관련 통합 검사만 실행합니다. 경로를 지정하면 순수 검사 단계는 생략합니다.
.\.venv\Scripts\python.exe scripts/dev.py test tests.test_headquarters --parallel 2
# 준비 데이터와 임시 상태가 다음 테스트에 남지 않는지 역순으로도 확인합니다.
.\.venv\Scripts\python.exe scripts/dev.py test tests.test_fixtures --parallel 2 --reverse
```

적합한 통합 테스트는 `tests.base.WorldCommandTest`로 클래스마다 전체 월드를 한 번 준비합니다. Room ID만 공유하고 각 테스트는 객체를 일괄 조회합니다. DB rollback 후 Evennia 객체·명령 캐시를 정리하고 GC를 수행하므로 저장 값과 NDb 임시 상태가 다음 검사에 남지 않아야 합니다. 최초 로그인 순서가 중요한 본부 검사는 `GameCommandTest`로 기존 테스트별 월드 생성 순서를 유지합니다. 테스트 본문의 실제 bootstrap·migration·재접속 검사는 그대로 실행합니다.
인증 알고리즘 호환 검사에는 해당 해시를 명시적으로 지정합니다. `tblib` 개발 의존성은 병렬 worker의 실패 traceback을 부모 프로세스에 전달하기 위한 것입니다. 실패한 `subTest`는 이름·조건과 예외를 전달하고 Evennia 캐시·Mock를 가진 테스트 객체 전체는 전달하지 않습니다. 병렬 실패가 나오면 해당 테스트 경로와 `--parallel 1`로 재현할 수 있습니다.

**성능 개선 검증 (2026-09-28):** main `f9fcd52`에서 시작한 `codex/test-performance`의 미커밋 변경으로 `scripts/dev.py check`와 최종 기본 `scripts/dev.py test`를 통과했습니다. 순수 72개(0.075초)·통합 205개(60.975초), 총 277개이며 DB 준비 등을 포함한 통합 runner 시간은 70.112초입니다. 기존 199개 통합 테스트 본문·assertion은 그대로이며 격리·해시 호환·병렬 오류 전달 검사 6개를 추가했습니다. 실제 2개 worker의 일반 실패와 Evennia subTest 실패는 별도 의도적 실패 진단에서 원래 조건·traceback 및 종료 코드 1을 확인했습니다. 근거는 `work/test-optimization-final-full.log`와 `work/test-optimization-worker-failure-final.log`입니다.

최종 subTest 전달 검사 추가 전 직렬 전체는 통합 204개·251.349초, 4개 프로세스 전체는 204개·99.704초로 통과했습니다. 관련 역순 병렬 49개도 통과했고 최종 오류 전달 보완은 관련 직렬 검사 2개와 최종 전체 병렬로 확인했습니다. 실행 편차와 기준 차이를 고려하며 최신 직렬 전체를 205개 성공으로 표현하지 않습니다. 이전 표준 실행의 통합 199개·1153.144초는 과거 비교 기록입니다. 이 로컬 검증 시점에는 푸시 전이므로 새 구성의 CI 시간·성공은 미검증이었습니다. 최신 PR HEAD의 원격 CI는 PR Validation에서 별도로 확인합니다. 게임/UI 변경이 없어 브라우저와 smoke는 실행하지 않았습니다.

### 격리형 실제 서버 검사

개발 서버를 실행할 필요가 없다. 저장소 루트에서 실행한다.

```powershell
.\.venv\Scripts\python.exe scripts/dev.py smoke
.\.venv\Scripts\python.exe scripts/dev.py smoke-full
```

`smoke`는 Quick Live Smoke이고 `smoke-full`은 Full Gameplay E2E다. 둘 다 매 실행마다 `work/smoke/<mode>-<run-id>`에 코드 복사본·새 SQLite DB·일반 fixture 계정 3개를 준비하고 migrate→bootstrap→fixture→실제 Portal/Server 시작→HTTP/WebSocket readiness→시나리오→종료를 자동 처리한다. 외부 서버의 stop/reload/kill을 호출하지 않는다. OS가 선택한 서로 다른 loopback 포트 4개를 setup 동안 예약하고 시작 때 해제한다. 경합으로 bind가 실패하면 해당 실행만 실패한다.

`settings_smoke`의 marker, 작업 디렉터리, SQLite engine, 정확한 DB 경로를 설정 로드와 fixture 초기화 전에 확인한다. 사용자 `PRIMAL_DB_*`는 자식 환경에서 제외되며 PostgreSQL에 접속하지 않는다. 일반 `game/server/evennia.db3`는 읽기 전용 SHA256·mtime_ns·size 비교만 한다. fixture는 정상 Account/Character API로 생성하며 공개 가입을 호출하지 않는다. 무작위 비밀번호는 메모리/자식 stdin에서만 전달하고 로그에 출력하지 않는다. production 새 캐릭터 기본값·가입 throttle은 변경하지 않는다.

실제 서버/WebSocket으로 다음 단계를 확인한다.

1. fixture 로그인과 출정 대기실, 기본 파티/전투 없음
2. 중앙홀→부두, 윤대장 임무 수락, A/B 파티 초대·수락
3. 같은 적에 공동 참여, outsider C의 점유 공격 거절, 양쪽 경험치/Credits 보상
4. 실제 시체 생성, 회수부품의 순번 배정과 파티 공동 회수 권한, outsider 회수 거절
5. 그 시체를 회수하지 않고 actual delay callback으로 바닥 전리품 전환, 원래 보호 유지
6. 같은 spawn의 최대 HP 재생성, 보호 만료 뒤 outsider 실제 회수
7. 귀환→옥상→공용 승강기 3층→동·북 무기점, 무기상 메뉴와 Credits 구매
8. disconnect/logout→fixture 재인증, name/zone/hp/xp/credits/inventory/quest 비교

Quick 사냥은 1회이며 구매 자금 100C·충분한 HP만 시작 fixture에 지급한다. Full은 첫 player의 회수부품 10개와 outsider의 HP 1도 전제로 준비한다. blade·시체·전리품 결과를 미리 만들지 않는다. mock delay나 미래 시각의 직접 reconcile을 사용하지 않는다. 접속 인증은 WebSocket handshake 다음 실제 서버 연결 안내를 기다려 Portal→Server 등록 race를 피한다. timeout은 인증/상태/전투/lifecycle/readiness/setup/종료별로 구분한다. Full은 monotonic 관찰 시각으로 조기 만료와 Quick 타이머 누출도 검사한다(시간 허용 오차: lifecycle 하한 1.5초·상한 10초, 첫 combat round 하한 0.5초).

| 항목 | Production / Full | Quick |
| --- | ---: | ---: |
| combat interval | 2.5초 | 0.25초 |
| corpse TTL | 30초 | 1초 |
| respawn delay | 15초 | 1초 |
| enemy total respawn | 약 45초 | 약 2초 |
| loot protection | 120초 | 2초 |
| claim timeout | 15초 | 2초 |
| participation timeout | 15초 | 2초 |
| enemy reset | 15초 | 2초 |

Quick는 3분 이내의 연결 검증이 목적이며 PR/main CI의 별도 `smoke` job에서 실행한다. 기존 required `test` job은 유지한다. Full은 30/45/120초 production wall-clock 의미를 검증하는 수동/closeout 경로이며 일반 CI에서는 실행하지 않는다. 기존 장시간 lifecycle 검증을 Full로 이동한 것이며 deterministic integration의 시간/rollback 검사를 없애지 않는다.

성공하면 `PASS [quick/full]`과 전체 실행 시간을 출력하고 자체 프로세스·임시 디렉터리를 정리한다. 실패/KeyboardInterrupt에서도 own process를 종료하고 실패 DB·setup/server/portal/client 로그 경로를 출력한다. 실패 요약에 mode·scenario·player·revision·zone·HP/XP/Credits/combat 상태를 남긴다. CI 실패 단계는 `.log`의 마지막 80줄만 출력하며 credential/state가 담길 수 있는 DB는 출력/업로드하지 않는다. 저장소 Actions 허용 목록 때문에 별도 artifact 업로드 action은 추가하지 않는다.

공개 가입과 production signup throttle은 gameplay와 분리된 auth/registration 정책 검사다. Quick에서 fixture login/logout/relogin을 실제 검증하고, 가입·입력 검증은 기존 auth 통합/수동 절차를 따른다. 610초 정책 대기를 수행하는 공개 가입 system 검사는 필요 시 별도로 실행하며 Quick/Full의 선행 조건이 아니다. production signup 제한을 낮추거나 gameplay 실패를 가입 재시도로 숨기지 않는다.

Full은 이어 본부 전체 서비스·실제 패배/회복·통신탑/밀림 임무와 두 보스 최종 보고·같은 DB의 Portal+Server 실제 restart를 검증한다. 재로그인 후 persistent profile·party·승강기·상자·시설·환경 clock을 비교하고 live combat/claim 정리·실제 시체/respawn callback 완료·ground entry 보존을 확인한다. 브라우저 표시·OS IME와 모든 임무 branching은 smoke에 포함하지 않는다. 아래 단계별 과거 기록의 로컬 DB/610초/5회 사냥 설명은 당시 스크립트에 대한 기록이며 현재 실행 방법은 이 절을 따른다.

## 7. 막혔을 때 확인할 사항

| 증상 | 확인할 사항 |
| --- | --- |
| 게임 페이지가 열리지 않음 | 개발 PC에서 접속했는지, 서버 시작이 완료됐는지, 주소의 포트가 `4001`인지 확인합니다. |
| 페이지는 열리지만 연결되지 않음 | 화면의 재연결 버튼을 누릅니다. 계속 실패하면 WebSocket 포트 `4002`와 서버 로그를 확인합니다. |
| 가입 실패 | 이름 형식·중복, 비밀번호 안내, 최근 반복 가입 여부를 확인합니다. 이미 가입한 계정은 접속하기를 사용합니다. |
| 공격이 멈춰 있음 | `종료`·재접속 후에는 `대상이름 사냥`으로 살아 있는 상대를 다시 지정해야 합니다. 다른 그룹의 점유 또는 재생성 대기 중인지도 확인합니다. |
| 장비가 나오지 않음 | 확률 드롭은 여러 번 실패할 수 있습니다. 자원 정산소의 부품 정산과 지원동 NPC의 크레딧 구매 경로를 사용합니다. |
| 수리 또는 능선 진입 실패 | 임무 수락, 정비기록 조사, 회수부품 3개 확보, 발전기 복구 순서를 확인합니다. |
| 회복 후 체력이 기대만큼 늘지 않음 | 최대 체력 제한, 붕대 수량과 이어진 적의 공격 피해를 로그에서 확인합니다. |
| 화면 변경 사항이 반영되지 않음 | CSS·JavaScript를 수정했다면 아래 정적 파일 수집 명령을 실행한 뒤 브라우저를 새로고침합니다. |

정적 파일 수집은 다음과 같이 실행할 수 있습니다.

```powershell
Set-Location -LiteralPath 'E:\Work\primal-zone\game'
..\.venv\Scripts\python.exe -m evennia collectstatic --noinput
Set-Location -LiteralPath 'E:\Work\primal-zone'
```

서버 로그는 `game/server/logs/`에 있습니다. 오류 보고에는 발생 시각과 관련 오류 부분만 첨부하고 비밀번호나 비밀 설정 파일은 넣지 않습니다.
오류 재현을 위해 DB를 삭제할 필요는 없습니다. 새 임무 진행이 필요하면 별도 일반 테스트 계정을 사용합니다.

## 8. 결과 기록

아래 양식을 복사해 기록합니다. 수행하지 않은 항목은 **미실행**, 준비 조건을 맞추지 못한 항목은 **보류**로 적습니다.

```text
테스트 일시:
기준 커밋: (git rev-parse --short HEAD)
실행 환경: Windows / 브라우저와 버전 / 화면 폭
계정 구분: 신규 또는 기존 (비밀번호 기재 금지)
테스트 ID 또는 구간: 예) C-06, 첫 임무 전체
준비 상태: 장소 / 레벨 / 장비 / 임무 단계
입력·조작 순서:
기대 결과:
실제 결과:
판정: 통과 / 실패 / 보류 / 미실행
재현 횟수: 예) 3회 시도 중 3회
관련 게임 기록·오류·화면:
```

**기존 확인 기록:** 2026-09-14, 코드 기준 커밋 `66276bb`에서 규칙 테스트 18개, 통합 테스트 12개와 Ruff 검사를 통과했고 게임 페이지의 HTTP 200 응답을 확인했습니다.
커밋 메시지 재작성 후 동일한 코드의 커밋은 `8b50d6e`입니다. 위 결과는 재작성 전 실행 기록입니다.
해당 확인에서는 전체 브라우저 플레이와 실서버 자동 검사(`smoke.py`)를 다시 수행하지 않았습니다.
이 기록과 이후에 작성할 수동 테스트 결과를 구분해서 관리합니다.

## 9. 특성·숙련·기술과 재훈련

별도 일반 탐사자로 부두에서 G-01~03을 확인한 뒤 `동` → `남` → `승강기` → `2층` → `내리기` → `동` → `북`으로 훈련실에 이동해 G-04~11을 확인합니다. 기존 v2 캐릭터를 사용한다면 DB를 지우지 말고 서버 재시작·재접속 후 기본 특성 10, 기술 Rank 1, 현재 레벨에 따른 미사용 포인트를 확인합니다. 레벨·XP·소지품·장비·임무·파티와 월드 객체가 유지되어야 합니다.

| ID | 입력·조작 | 정상 결과 |
| --- | --- | --- |
| G-01 | `상태`, `능력`, `기술`, `경험치`, `장비`, `가방` | 서로 다른 정보를 표시. 장비에는 착용품만, 가방에는 붕대 등 전체 소지품 표시 |
| G-02 | `상`, `능`, `기`, `장`, `가`, `ㅂ`, `ㄴ` | 각각 전체 명령과 같은 동작. 북으로 이동 후 남으로 부두 복귀 |
| G-03 | `'ㅂ`, `ㅂ 말`, `강철 마체테 무장`, `공격 어린청소룡` | 채팅의 ㅂ 보존, 공백 이름 허용, prefix 공격 거부 |
| G-04 | `탐사대 훈련관 대화` | 배분·학습·무료 재훈련 안내 |
| G-05 | 신규 Lv.1에서 `체질 2 배분` | 최대 HP 60→68, 현재 HP 60 유지, 미사용 특성 4→2 |
| G-06 | `힘 3 배분`, `힘 -1 배분` | 포인트 초과/음수 거부, 이전 특성·HP·포인트 그대로 |
| G-07 | `강타 배워` | Rank 1→2, 기술점수 2→1, 크레딧 20→16 |
| G-08 | `방어 배워`, `응급치료 배워` | 방어 Rank 2 학습 후 포인트 0. 응급치료 학습 실패 시 크레딧/Rank 불변 |
| G-09 | `특성 재분배` 반복 | 투자값 0, 포인트 4 반환. 기술·숙련·크레딧 불변, HP 무료 회복 없음 |
| G-10 | `기술 재분배` 반복 | 무료 Rank 1, 포인트 2 반환. 특성과 숙련 불변, 학습 크레딧 반환 없음 |
| G-11 | 특성·기술에 다시 투자 후 `전체 재훈련` | 두 풀 한 번에 반환, 레벨·XP·숙련·가방·장비·임무·파티 보존 |
| G-12 | 전투 중/훈련관 없음·보이지 않음/unsafe Room에서 배분·학습·재분배 | 서버가 거부. 화면 버튼도 비활성, 포인트/크레딧 부분 차감 없음 |
| G-13 | 실제 적에게 공격, 같은 차례에 공격/강타 반복 입력 | HP가 깎인 개인 차례마다 무기 숙련 XP 1. 입력 횟수만큼 증가하지 않음 |
| G-14 | 방어 예약 후 적에게 맞기 / 예약만 하고 도주 | 실제 피해가 감소한 경우에만 방어 숙련 XP 1 |
| G-15 | 체력이 부족할 때 붕대 / 최대 HP에서 붕대 | 실제 HP 증가 시 응급처치 XP 1. 최대 HP에서는 붕대·XP 불변 |
| G-16 | 파티원 A만 행동 | A의 숙련만 증가. 기존 파티 처치 XP 분배와 구별 |
| G-17 | 같은 약한 적 반복 / 더 높은 적 사냥 | 어린청소룡 Rank 2 상한 이후 증가 없음. 상위 적에서 해당 상한까지 계속 성장 |
| G-18 | 체질 투자 후 옥상 귀환→의무실 휴식, 훈련실로 돌아와 특성 재분배, 다시 체질 투자 | 감소한 최대 HP에 현재 HP clamp. 다시 투자해도 현재 HP 증가 없음 |
| G-19 | 기술 Rank 3 학습 | Lv.3 이상, Rank 2에서 추가 2점/8크레딧 차감. 최고 Rank 초과·조건 부족은 전체 불변 |
| G-20 | 재접속·서버 재시작 | 투자·Rank·숙련·포인트 계산 결과 유지. 기존 파티·전리품 생명주기 검증도 반복 |
| G-21 | 390px에서 성장 패널 펼치기, +1·배워·재분배 버튼 클릭 | 직접 텍스트 입력과 같은 결과. 가로 넘침 없이 전투·파티·회수 조작 유지 |

특성 총량은 `레벨×2+2`, 기술 총량은 `레벨+1`입니다. `투자 + 미사용 = 총량`을 재훈련 전후 확인합니다. 숙련은 20 XP당 1 Rank, 최대 10이며 어린청소룡/갈퀴사냥룡/고장난경비기/우두머리의 상한은 2/4/7/10, 비전투 회복은 2입니다. 재훈련으로 숙련을 초기화하지 않습니다.

자동 검사는 실제 수면 없이 차례 시각을 주입하여 중복 callback, 개인 숙련, 공유 HP, 원자적 저장 실패, v1/v2 migration을 검증합니다. 이 결과는 실제 OS 한글 IME 조합이나 브라우저 레이아웃 검증을 대신하지 않습니다. 브라우저 붙여넣기와 실제 IME 입력은 구분해 기록합니다.

**성장 시스템 확인 기록:** 2026-09-20, 실행 코드 기준 `45f55b2`와 같은 작업 트리에서 `uv run python scripts/dev.py check`와 `uv run python scripts/dev.py test`(규칙 24개·통합 61개)가 통과했습니다. `game`에서 `python -m evennia collectstatic --noinput`으로 변경 정적 파일 2개를 수집했습니다. 기존 플레이 DB와 분리한 검증용 DB/4101번 HTTP·4102번 WebSocket에서 Chrome으로 한글 일반 계정 생성, 버튼/명령 특성 배분, 현재 HP 보존, 기술 학습, 세 가지 재훈련, 정보·이동 단축어, 공백 포함 대상 대화·공격, 사냥·시체 표시·바닥 회수, 파티 초대·재접속·수락을 확인했습니다. 재훈련 후 실제 공격으로 얻은 무기 숙련 XP 3과 탐사 기록이 유지됐습니다.

이 확인 기록은 실제 OS 한글 IME, 브라우저 전체 보스 임무, 두 동시 브라우저의 공유 HP 검증을 포함하지 않습니다. 초기 Chrome 확장 프로그램 UI 차단을 해소한 뒤 390px 실제 게임 화면에서 특성 배분·기술 학습·전체 재훈련 버튼과 기존 전투·파티·전리품 영역 배치를 확인했습니다. viewport 390px에서 document clientWidth와 scrollWidth가 모두 375px로 가로 넘침이 없었습니다. 주기적인 월드 상태 전송 중에도 성장 버튼을 유지하도록 보완하고 학습·재훈련을 재검증했습니다. 별도로 수행하는 최종 HEAD 검증과 CI 결과는 PR 본문에서 구분해 기록합니다.

## 현재 위치 방향도

- 부두(북), 초지(북/동/남), 수송차(서), 관리동(서/동), 습지(북/남), 능선(남)에서 Room 텍스트와 SURROUNDINGS 방향도를 확인합니다. 없는 방향에는 버튼과 연결선이 없어야 합니다.
- 방향 버튼 클릭과 같은 방향 직접 입력이 동일하게 이동하고, 이동 직후 새 방의 방향도가 표시되어야 합니다. 전투 중 이동과 발전기 미복구 상태의 능선 진입은 기존처럼 거절되어야 합니다.
- Tab으로 방향 버튼에 접근하고 Enter로 이동합니다. `[현재]`는 버튼이나 Tab 정지점이 아닙니다. 같은 방의 반복 상태 갱신 중 포커스가 유지되어야 합니다.
- 데스크톱·중간 폭·390px에서 버튼 겹침, 가로 넘침, 연결선 어긋남이 없는지 확인합니다. 텍스트 로그의 공백 정렬과 Neo둥근모 Code 표시도 확인합니다.
- 향후 위/아래 등 특수 출구는 `기타 출구`에 나타납니다. 로그는 클릭 없는 일반 텍스트이며 SURROUNDINGS 버튼만 기존 방향 명령을 전송합니다.

**방향도 브라우저 확인 기록:** 2026-09-21, `9438f6a`에서 시작한 `codex/room-directions` 작업 트리의 최종 방향도 구현을 검증했습니다. Chrome 확장 프로그램 연결 차단 후 자동 조작 세션을 복구하여 Codex 내장 브라우저에서 검증용 DB의 일반 탐사자로 진행했습니다. 부두·초지·수송차·관리동·습지·능선의 실제 출구와 텍스트 방향도, 버튼 이동과 즉시 갱신을 확인했습니다. 기존 명령으로 사냥·시체/바닥 전리품 회수·발전기 수리를 진행했으며 전투 중 이동과 미복구 능선 진입은 거절됐습니다. 키보드 Tab/Enter, 반복 전투 상태 전송 중 방향 버튼 포커스 유지, 1280px·768px·390px 레이아웃을 확인했습니다. 390px에서 문서 clientWidth/scrollWidth는 모두 375px, 방향 버튼은 44×44px였고 콘솔 오류/경고는 없었습니다. 실제 OS 한글 IME, 모든 파티 조합과 전체 보스 임무는 이번 방향도 검증에서 재실행하지 않았습니다.

같은 최종 구현에서 `uv run python scripts/dev.py check`, `uv run python scripts/dev.py test`(규칙 24개·통합 64개, 총 88개), `node --check game/web/static/webclient/js/primal.js`, `git diff --check`가 통과했습니다. `game`에서 `uv run python -m evennia collectstatic --noinput`도 수행했습니다. 검증용 서버는 종료했으며 플레이 DB와 이동 규칙은 변경하지 않았습니다.

## 텍스트 인터페이스 확인

1. 부두·초지·수송차·관리동·발전실에서 `보기`를 실행합니다. Room은 장소 묘사와 실제 대상의 문장으로 나타나며, 대상별 명령 목록은 나오지 않아야 합니다. NPC는 청록, 적은 따뜻한 적색, 객체는 금색, 실제 출구 방향은 연두색입니다.
2. `윤대장 보기`, `어린 청소룡 보기`, `보급상자 보기`, `발전기 보기`, `<시체 이름> 보기`, `낡은 마체테 보기`를 실행합니다. 실제 타입의 설명과 지원 행동만 표시되어야 합니다. 소지품 이름에는 공백을 넣어도 조회할 수 있습니다.
3. 일반 공격·강타·방어·회복을 사용합니다. 무기/붕대는 아이템색, 적은 적색이며 실제 피해·회복량은 기본색입니다. 마지막 일격의 표시 피해는 남은 HP를 넘지 않아야 합니다. 처치는 문장으로, 확정 XP·크레딧만 보상색으로 표시합니다.
4. 두 계정으로 파티를 만들고 같은 적을 공격합니다. 시체를 살펴 배정자와 보호 상태를 확인하고, 다른 파티원이 `시체에서 모두 가져`를 입력해도 실제 배정자에게 아이템이 들어가야 합니다. 배정 문장의 아이템/플레이어 색과 가방을 대조합니다. 바닥 전리품에도 같은 규칙이 적용되어야 합니다.
5. `상태`, `능력`, `경험치`, `기술`, `장비`, `가방`, `상점`, `임무`, `파티`, `도움말`을 조회합니다. 실제 수치·레벨 기준·Rank·포인트·가격·착용 상태와 일치하고, 제목/섹션/행을 구별할 수 있어야 합니다. 아이템 이름은 어디서나 같은 색이어야 합니다.
6. 검증용 계정 채팅에 `<img src=x onerror=alert(1)>`, `|r문자|n`, `$You()`, `어린청소룡 북 공격`을 넣습니다. HTML 실행이나 명령 실행이 없어야 하며 채팅 본문의 이름/방향을 자동 색칠하지 않아야 합니다. 웹 로그 안에 이미지·링크·script가 생성되면 실패입니다.
7. 데스크톱과 390px에서 위 화면을 확인합니다. 긴 정보는 줄바꿈하되 가로 스크롤이 없어야 하고 색 단어는 링크처럼 동작하지 않아야 합니다. 기존 방향/전투/파티 버튼, 키보드 포커스와 명령 입력을 유지해야 합니다.

자동 검사는 `tests/test_text.py`의 의미 역할·실제 결과값·정보 조회·프로토콜 리터럴 처리와 기존 전체 회귀 테스트를 함께 실행합니다. 실제 OS 한글 IME와 실제 터미널 표시 검사는 별도로 수행하고, 프로토콜 단위 테스트로 대체했다고 표현하지 않습니다.

**시맨틱 텍스트 브라우저 기록 (2026-09-22):** `c088cae`에서 시작한 이번 작업의 검증용 별도 SQLite DB에서 일반 계정 두 개를 사용했습니다. Codex 내장 브라우저의 1366px/390px 화면에서 부두·초지·수송차·관리동·발전실 Room, NPC/적/상자/발전기/시체 보기, NPC 대화, 일반 공동 전투·처치·개인 보상·파티 순번 전리품, 모든 정보 조회 화면과 도움말을 확인했습니다. 추가 솔로 사냥에서 시체 소멸 후 바닥 전리품·적 재생성·회수·붕대 회복을 확인했습니다. 상점의 교환 비용을 별도 행으로 바꾼 뒤 390px에서 다시 확인했습니다. 강타 문장의 중복 조사와 도움말 사용 예의 행동 강조를 보완한 뒤 실제 전투와 390px 도움말을 다시 확인했습니다.

390px에서 문서 clientWidth/scrollWidth는 375/375px, 로그는 339/339px였고 정보창 내부에도 가로 넘침이 없었습니다. HTML 공격 문자열은 채팅의 일반 텍스트로 표시됐으며 로그의 img/script/a 노드는 0개, 두 세션의 콘솔 오류·경고는 0개였습니다. 채팅 본문의 적 이름·방향·명령은 의미 색을 얻지 않았습니다. 현재 로그에서 가장 밝은 배경색 `#1c2d21`을 기준으로 팔레트의 계산 대비는 6.06:1 이상입니다.

실제 OS 한글 IME, 실제 Telnet 터미널, 색각 시뮬레이션/스크린리더, 전체 보스 임무, `scripts/smoke.py` 전체 실행은 이번 수동 검증에 포함하지 않았습니다. 파티·전투·성장·생명주기·솔로 임무 회귀는 별도의 최종 자동 테스트 결과로 확인하며 브라우저 확인과 구분합니다. 출력 예는 [텍스트 출력 예](text-examples.md)에 정리했습니다.

**최종 자동 검증:** 기능 커밋 `e424802`과 동일한 코드에서 `uv run python scripts/dev.py check`, `uv run python scripts/dev.py test`(규칙 24개·통합 73개, 총 97개), `node --check game/web/static/webclient/js/primal.js`가 통과했습니다. `game`에서 `uv run python -m evennia collectstatic --noinput`을 완료했고 최종 스테이징 내용의 `git diff --cached --check`도 통과했습니다. 이후 문서 커밋에는 실행 코드 변경이 없습니다. PR의 최종 HEAD CI는 PR 본문에 별도로 기록합니다.


### Compact 정보창 확인

- `상태`, `능력`, `경험치`, `기술`, `장비`, `가방`, `상점`, `임무`, `파티`, `도움말`을 1366px와 390px에서 조회한다. `[제목]` 다음에 바로 내용이 시작하고, 반복 항목 사이에 빈 줄을 넣지 않는다.
- 상태 요약과 능력의 기본값/투자값, 장비 보정의 역할이 구분되어야 한다. 최고 등급 경험치에는 다음 등급이 없고, 최고 Rank 기술에는 다음 비용 대신 최고 Rank를 표시한다.
- 가방 분류는 비어 있을 때 생략하고 착용 표시를 유지한다. 상점 크레딧 가격과 정산 수량·환율, 기술의 다음 조건은 실제 콘텐츠와 일치해야 한다. R은 Rank, C는 크레딧이다.
- 임무의 `+ / > / -`와 완료 단계 수, 파티장·멤버·전리품 순번·초대자·수락/거절 명령을 확인한다.
- `공격 도움말`, `사냥 도움말`, `능력 도움말`에서 같은 command metadata의 설명/사용법/별칭과 특성 효과를 확인한다. `도움말 공격`은 prefix 명령으로 실행되지 않아야 한다.
- 긴 이름이나 분류 행은 공백 우선으로 자연스럽게 줄바꿈하고 가로 스크롤이 생기지 않아야 한다. 글자 크기·색·입력창·SURROUNDINGS 버튼은 유지한다. 대상 보기의 설명/상태/행동과 Room·세계 사건 출력도 유지한다.

**Compact 브라우저 기록 (2026-09-22):** PR #3 `064e616`에서 이어진 compact 변경으로 별도 검증 DB의 일반 계정 두 개를 사용했다. 최종 CSS의 `word-break: keep-all` 적용을 확인한 뒤 1366px/390px에서 10개 정보 명령과 윤대장 보기를 확인했다. 상세 도움말과 특성 효과, 입력창/조회 버튼, 파티 초대·수락 후 파티장과 멤버 표시를 확인했다. 두 세션 콘솔 오류/경고는 0개였다. 390px 문서 clientWidth/scrollWidth는 375/375px, 로그는 339/339px이며 확인한 모든 정보창에서 가로 넘침이 없었다. 실제 OS IME, Telnet 클라이언트, 전체 사냥/보스 임무는 이번 compact 수동 검증에 포함하지 않았다. terminal 출력은 자동 테스트에서 ANSI 변환 후 원문 보존을 확인했다.

동일한 신규 캐릭터 기본값을 이전 formatter와 최종 formatter에 전달한 논리적 행 수(브라우저 자동 줄바꿈 전)는 다음과 같다. 과거 화면의 픽셀 높이를 재측정한 값은 아니다.

| 명령 | 이전 | compact |
| --- | ---: | ---: |
| 상태 | 19 | 5 |
| 능력 | 22 | 6 |
| 경험치 | 12 | 2 |
| 기술 | 18 | 5 |
| 장비 | 13 | 4 |
| 가방 | 10 | 3 |
| 상점 | 13 | 6 |
| 임무 | 13 | 6 |
| 파티 없음 | 5 | 1 |
| 도움말 | 147 | 12 |

최종 신규 캐릭터의 실제 정보창 높이는 상태 153px(1366/390 공통), 기술 153/281px, 가방 102/127px, 도움말 383/562px였다. 상세 수치는 위 일반 계정의 기본값에 해당하며 장비·멤버 수·이름 길이에 따라 달라진다. 실제 개행과 값은 [출력 예](text-examples.md)를 따른다.

Compact 최종 자동 검증은 PR #3의 `064e616` 이후 추가 커밋과 동일한 코드에서 수행했다. `uv run python scripts/dev.py check`, `uv run python scripts/dev.py test`(규칙 24개·통합 76개, 총 100개), `git diff --check`가 통과했고 정적 파일 수집을 완료했다. JavaScript는 변경하지 않았다. 정확한 최종 HEAD와 CI 결과는 PR 본문에 기록한다.

## 아이템 상호작용과 보관 확인

일반 계정 A/B를 같은 부두에 접속시킨다. 기존 플레이 DB를 삭제하지 않으며 별도 검증 환경을 권장한다.

1. 가방에 붕대 3개가 있을 때 `붕대 버려` 후 가방 2개/바닥 1개를 확인한다. B도 즉시 `붕대 가져`로 회수할 수 있어야 한다. `붕대 모두 버려`와 기존 `붕대 모두 가져`, `모두 가져`도 확인한다.
2. `B이름에게 붕대 줘`와 `B이름에게 붕대 모두 줘`로 A/B 수량과 두 웹 가방이 즉시 바뀌는지 확인한다. 자기 자신·NPC·다른 Room·없는 플레이어 및 전투 중 받는 대상은 거절하고 상태를 유지해야 한다.
3. `상점`, `야전식량 구매`, `정제수 구매` 후 HP가 부족할 때 `야전식량 먹어`/`정제수 마셔`로 각각 12/6만큼 회복하고 수량 하나만 줄어야 한다. 치료 숙련은 유지한다. 잘못된 행동, 최대 HP, ALL 소비, 전투 중 사용, 크레딧 부족은 상태 불변이어야 한다. 기존 `회복`은 붕대와 치료 숙련을 사용한다.
4. `강화 조끼 벗어`, `강철 마체테 해제`로 빈 슬롯을 만든다. 장비/상태/웹의 없음 표시와 가방 수량 보존을 확인한다. 초지에서 `어린청소룡 때려`로 맨손 전투, 중복 적 환경에서 `갈퀴사냥룡 2 때려`의 번호 선택과 ALL 거절을 확인한다.
5. 부두에서 `동` → `남` → `서` → `북`으로 보관실에 이동해 `보관상자에 붕대 넣어`, `보관상자에 붕대 모두 넣어`, `보관상자 보기`, `보관상자에서 붕대 꺼내`, `보관상자에서 붕대 모두 꺼내`를 확인한다. 다른 탐사자도 공용 물건을 꺼낼 수 있다. 중복 상자는 `보관상자 2`를 사용하며 마지막 물건은 한 번만 지급되어야 한다.
6. 방어구를 벗은 뒤 `개인 보관함에 강화 조끼 넣어`, `개인 보관함 보기`, `개인 보관함에서 강화 조끼 꺼내`를 확인한다. A/B는 같은 객체를 사용해도 자신의 contents만 보여야 한다. 재접속 후 해제한 슬롯과 개인 보관을 유지하고 검증 서버 재시작 후 공용 contents도 유지해야 한다.
7. 무기 하나가 장착되고 같은 identity 두 개를 소유했다면 한 개만 이동해야 한다. `모두`도 장착분을 남긴다. 유일한 장착 장비와 밀림 신호전지의 버려·줘·공용/개인 보관은 모두 거절한다. 신호전지를 이동시키고 재조사하는 복제가 없어야 한다.
8. 1366px/390px에서 해제·벗어·음식/음료 버튼, 빈 슬롯, 상자 SURROUNDINGS 보기, 긴 설명 줄바꿈과 가로 넘침을 확인한다. 버튼은 같은 서버 텍스트 명령을 보내야 한다. 자동 문자열 입력은 실제 OS 한글 IME 검증으로 기록하지 않는다.

**아이템 상호작용 브라우저 기록 (2026-09-27):** `origin/main`의 `45dbf80`에서 시작한 `codex/item-interactions` 변경을 별도 DB와 일반 계정 두 개로 확인했다. 벗어/해제 버튼, 빈 장비 표시, 음식/음료 구매와 소비(HP +12/+6), 버려 후 바닥 회수 버튼, 공용 상자 넣어/꺼내, 개인 보관함 분리, 줘 이후 양쪽 가방 갱신을 실제 웹 조작으로 확인했다. 검증 서버를 종료·재시작한 뒤에도 빈 장비 슬롯과 개인/공용 보관 내용이 유지됐다. `어린청소룡 때려`로 맨손 전투·처치 후 기존 시체 회수 버튼도 확인했다. 기존 플레이 DB는 초기화하거나 변경하지 않았다.

1366px에서 문서 clientWidth/scrollWidth는 1351/1351px, 로그는 745/745px, 가방은 228/228px였다. 별도 두 번째 탭의 실제 390px viewport에서는 문서 375/375px, 로그 339/339px, 가방 317/317px로 확인한 행의 가로 넘침은 없었다. 두 탭의 콘솔 오류/경고는 0개였고 아이템 semantic 색도 유지됐다. 화면 캡처 API가 실패하여 픽셀 단위 시각 검토는 완료하지 못했다. 한글 명령은 자동 문자열 입력으로 확인했으며 실제 OS 한글 IME 조합 검증은 미실행이다. 중복 적의 `2 때려`, 실패 시 원자성, 임무 아이템 제한과 기존 파티/전리품 회귀는 자동 테스트 근거와 구분한다.

## 슬롯별 장비 확장 확인

- 지원동 3층 무기상/방어구상의 `상점`에서 [전체 장비 표](../README.md#장비와-획득-경로)의 신규 6종과 크레딧 가격을 확인한다. 충분한 크레딧으로 각각 구매하고 정확한 비용과 수량 +1을 확인한다. 부품을 가진 것만으로 구매할 수 없고 먼저 정산소에서 크레딧으로 정산해야 한다. 자원 부족이면 전체 상태가 유지되어야 한다.
- `강철 마체테 무장`, `강화 조끼 착용` 및 `wield` / `wear` 별칭을 확인한다. `무장 강철마체테`, `착용 강화조끼`, `강철마체테 equip`은 지원하지 않는다.
- 사냥창·정글도·중량카빈은 `무장`, 가죽보호복·경량전술조끼·중장방호복은 `착용`한다. 수량과 다른 슬롯은 유지되어야 한다. 정글도+경량전술조끼의 장비 보정은 공격 +9 / 방어 +3이다.
- 무기에 `착용`, 방어구에 `무장`, 붕대·회수부품에 두 행동을 각각 시도한다. 모두 실패하고 장비·수량·HP·크레딧을 바꾸지 않아야 한다. 반대 슬롯이면 올바른 행동을 안내해야 한다. 전투 중에는 두 행동 모두 거절한다.
- `아이템이름 보기`의 아이템 색과 올바른 행동, `무장 도움말` / `착용 도움말`의 사용법·별칭, 가방의 `[착용]`, 장비의 양쪽 슬롯 합계를 확인한다.
- 웹 가방에서 미장착 무기는 `무장`, 방어구는 `착용` 버튼이어야 한다. 버튼과 직접 입력의 결과가 같고 장착 표시·공격·방어가 갱신되어야 한다. 데스크톱과 약 390px에서 긴 신규 장비 이름·버튼·상점 텍스트가 가로 넘침 없이 보여야 한다.

이번 장비 변경의 자동 검증은 순수 규칙 28개와 Evennia 통합 80개가 통과했다. 브라우저 검증은 Chrome 확장 프로그램 UI가 조작을 차단하여 미완료다. 실제 버튼 클릭·390px 표시·OS 한글 IME는 통과로 간주하지 않는다. 격리 검증 DB를 사용했고 기존 플레이 DB는 변경하지 않았다.


## 동적 환경 확인

후속 정합성 확인에는 다음을 포함한다.

- 부두 clear/fog, 관리동 clear/rain/storm, 습지 clear/fog에서 static 설명은 같고 환경 문장만 달라지는지 확인한다. 부두의 고정 안개, 관리동의 현재 강우, 습지의 안개 중복이 없어야 한다.
- 실제 CSS `?v=lighting`·JS `?v=elevator` URL과 환경 헤더를 확인한다. 데스크톱 `환경 확인` 버튼과 직접 `날씨` 입력의 정보가 같아야 한다. 모바일에서는 기존 FIELD GUIDE 숨김 정책을 유지하며 가로 넘침이 없어야 한다.
- 같은 period 경계에서 야외는 메시지 한 번, 발전실 indoor/dim은 동일 문장 메시지 없이 헤더만 갱신되어야 한다. rain→storm은 발전실에서도 바깥 빗소리 변화 메시지 한 번이어야 한다.
- 별도 DB의 version 없는 state를 읽을 때 DB를 쓰지 않고, reconcile 후 version 1만 추가되는지 확인한다. clock/현재 weather/seed/step/기한을 비교하고 다시 실행하면 migration 쓰기가 없어야 한다. 미래 version은 데이터를 보존하며 오류를 반환해야 한다.

별도 검증 DB에서 같은 Weather Zone의 일반 계정 두 개를 사용한다. 운영 DB를 초기화하거나 환경을 시험하기 위해 실제 플레이 profile을 변경하지 않는다.

1. `날씨`/`환경`의 출력이 같고 `날씨 도움말`에 alias가 표시되는지 확인한다. 4배속 시각과 웹 상단 서버 상태가 맞아야 한다.
2. 부두/초지/수몰된 도로(outdoor), 관측소(sheltered), 관리동/발전실(indoor)에서 static 설명 다음 환경 문장과 기존 방향도·객체가 유지되는지 확인한다. 비가 실내를 직접 적신다고 묘사하면 안 된다.
3. `북 봐`의 목적지 환경과 실제 이동 후 local 환경을 비교한다. selector/HP/loot는 원거리에서 숨기고 실제 이동 후에는 그대로 보인다. 잠긴 능선/밀림/연구구역은 환경도 노출하지 않는다.
4. 테스트 fixture에서 새벽/낮/해질녘/밤 경계를 확인한다. 맑은 밤 보름/삭의 밝기 차이, 낮에 달빛이 더해지지 않음, 폭우/안개의 낮은 시야를 확인한다. 시야가 나쁘면 새 일반 상대 획득과 작은 전리품 회수는 제한하며 광원 사용 후 허용되는지 확인한다. 기존 교전은 계속된다.
5. 시간대/날씨가 바뀌어 현재 장소의 환경 문장이 달라지면 같은 zone의 접속 계정에게 한 번만 안내되고 웹 상태가 갱신되어야 한다. 동일 날씨 기간 갱신과 5초 sweep는 로그를 반복하지 않는다. 로그아웃한 계정에게 과거 알림을 누적하지 않는다.
6. 검증 서버 종료/재시작 후 clock epoch와 기상 구간을 유지하며 지난 시각을 복구하는지 확인한다. 과거 변화 문장이 연속 출력되지 않아야 한다. 캐릭터 inventory/quest/visited는 환경 조회만으로 변하지 않는다.
7. 1366px/390px에서 환경 헤더·Room·방향 정찰·날씨 정보창의 줄바꿈, 가로 넘침, semantic 색과 기존 SURROUNDINGS 버튼을 확인한다. 입력 JS를 바꾸지 않았더라도 실제 OS IME와 자동 문자열 입력은 구분해 기록한다.

자동 검증은 `scripts/dev.py test`가 순수 `world/test_*.py`와 Evennia `tests`를 모두 실행한다. epoch/경계/달/빛/시야, seed 전이/기한/재시작/장기 복구, DB 실패/알림 중복 방지, local/distant/web 시각 일치, 차단된 목적지 미조회, profile 불변과 기존 selector/권한 회귀를 함께 확인한다.

**환경 브라우저 기록 (2026-09-27):** `origin/main`의 `0567810`에서 시작한 변경을 별도 SQLite DB와 일반 계정 두 개로 확인했다. 1366px/390px에서 초지의 static 설명·환경·방향도·객체 순서, `북 봐`의 제한된 정찰, `날씨` 정보창과 서버 환경 헤더를 확인했다. 낮→해질녘 전환은 당시 접속 계정에 한 번, 비→폭우 전환은 같은 zone의 두 계정에 각각 한 번 출력되었다. 반복 sweep 중 추가 알림은 없었다. 물안개 습지의 잠긴 출구는 기존 차단 문구만 표시했고 목적지 환경을 노출하지 않았다. 관리동과 발전실에서 밖의 폭우와 실내의 밝기·빗소리 묘사를 구분했다.

검증 서버를 종료·재시작한 뒤 DB의 clock epoch와 zone 날씨·시작/종료 시각·seed·step이 재시작 전 값과 같았다. 재접속 시 진행한 게임 시각과 현재 폭우가 표시되고 지나간 알림을 재생하지 않았다. 1366px의 문서 clientWidth/scrollWidth는 1351/1351px, 로그는 745/745px였다. 실제 390px viewport의 문서는 375/375px, 로그는 339/339px로 가로 넘침이 없었고 화면 캡처로 줄바꿈·색상·기존 SURROUNDINGS를 확인했다. 재접속 후 해당 탭의 콘솔 오류/경고는 0개였다. 검증 서버는 확인 후 종료했으며 기존 플레이 DB는 초기화하거나 변경하지 않았다.

**초기 구현 자동 검증 (47ffa0b):** 당시 구현 코드에서 `.\.venv\Scripts\python.exe scripts/dev.py check`, `.\.venv\Scripts\python.exe scripts/dev.py test`가 통과했다. 순수 규칙 49개와 Evennia 통합 156개, 총 205개이며 실패는 0개다. JavaScript 문법 검사와 `git diff --check`가 통과했고 `game` 및 별도 검증 환경에서 정적 파일 수집을 완료했다. 이후 변경은 이 검증 기록 문서뿐이다. 최신 PR HEAD의 CI는 PR 본문에서 별도로 확인한다.

실제 OS 한글 IME는 미검증이며 자동 한글 문자열 입력을 IME 확인으로 간주하지 않는다. 5종 전체 날씨·밤/달·sheltered 및 artificial의 모든 조합을 실제 브라우저에서 전수 확인하지는 않았고 이 경계는 자동 테스트로 검증했다. 이번 수동 확인은 환경 변경 범위에 집중했으며 전체 보스 진행이나 `scripts/smoke.py`를 반복하지 않았다.


**환경 후속 자동 검증 (2026-09-28):** 환경 표현·전환 알림·schema version·template 변경이 포함된 최종 코드에서 `scripts/dev.py check`와 `scripts/dev.py test`가 통과했다. 순수 규칙 53개와 Evennia 통합 162개, 총 215개이며 실패는 0개다. 추가된 10개 테스트는 알려진 static 기상 충돌, 날씨 변경 전후 static/객체 불변, 동일 observed_at의 before/after 비교, fixed-light period no-spam과 웹 push, 실내 weather 알림, v0→v1 보존·반복 안전·미래 version 거절, 새 asset 주소와 환경 버튼을 검증한다. JavaScript 문법 검사와 diff 검사가 통과했고 정적 파일 수집은 기존 환경 자산과 같아 213개가 unmodified였다. 실제 OS 한글 IME는 이번에도 미검증이다.


**환경 후속 브라우저 기록 (2026-09-28):** 별도 DB에서 부두 clear/fog, 관리동 clear/rain, 습지 clear/fog의 local 출력을 확인했다. static 설명은 같고 현재 안개·빗소리만 Environment에서 표시되며 안개 문장은 각 Room 출력에 한 번이었다. `북 봐`의 환경 요약·잠긴 출구 차단과 `날씨`, FIELD GUIDE의 환경 확인 버튼을 확인했다. 실제 CSS/JS 주소는 모두 `?v=environment`였으며 과거 query의 캐시가 존재하는 상황 자체는 별도로 재현하지 않았다. 1366px 문서 1351/1351px·로그 745/745px, 390px 문서 375/375px·로그 339/339px(clientWidth/scrollWidth)로 가로 넘침이 없었고 모바일 FIELD GUIDE는 기존 숨김 정책을 유지했다.

같은 경계에서 야외 부두 계정은 낮→해질녘 ambient 1회, 발전실 indoor/dim 계정은 0회였고 두 헤더 모두 해질녘으로 갱신되었다. 이후 비→폭우는 관리동과 발전실에서 각각 빗소리 변화 알림 1회였다. 확인한 두 탭의 콘솔 오류/경고는 0개다. version 없는 fixture를 실제 별도 DB에 저장한 뒤 readonly 조회는 쓰지 않고 reconcile이 version 1만 추가하며 clock epoch·weather·seed·step·기한을 보존한 것을 확인했다. 기존 플레이 DB는 수정하지 않았다. 전체 날씨/달/노출 조합·실제 OS IME는 전수 수동 검증하지 않았으며 계산·저장 경계는 자동 테스트로 검증했다.


## 환경 시야와 광원 검증

후속 정합성 확인은 별도 DB에서 다음을 추가한다.

- 맑은 낮 부두는 낮빛 문장을 유지하고, 밤 부두는 실제 밝기를 개선하는 시설 조명을 묘사한다. 관리동/발전실은 power off/on의 base/facility 표현을 비교한다.
- legacy bare facility state의 True가 version 1의 states에 유지되는지 서버 재시작과 attribute cache reload로 확인한다. 단순 light 조회는 저장하지 않으며 미래 version은 개인 진행과 공용 데이터를 변경하지 않고 오류로 중단해야 한다.
- wreck clear는 `비상장비함 조사 · 보급상자 조사`, poor는 `비상장비함 조사`, poor + 손전등으로 clear 회복 후는 두 안내가 보인다. 같은 시각의 SURROUNDINGS와 selector에서도 숨은 보급상자 이름이 새지 않아야 한다.
- 손전등 보기를 전원 없음/ON 10분 경과/OFF 잔량 있음에서 확인한다. 설명·삽입 문법과 현재 상태가 나오고 같은 시각의 확인/웹 잔량과 일치해야 한다. 일반 건전지·무기·방어구·붕대 보기도 확인한다.
- 공용 전력 False→True의 영향권 접속자는 시설 가동 사건과 state push를 받고 True→True는 사건을 반복하지 않는다. 개인 발전기 단계는 각각 부품 3개·XP 50·개인 진입 조건을 유지한다.
- 1366px/390px에서 환경 헤더·Room hint·SURROUNDINGS·가방 광원 버튼·보기/확인 출력을 확인하고 가로 넘침과 콘솔 오류/경고를 기록한다. 이 후속 수정은 JS/CSS를 변경하지 않으므로 기존 `?v=lighting` 자산을 사용한다.

**광원 후속 브라우저 기록 (2026-09-28):** 별도 SQLite 검증 DB에서 밤/폭우 wreck의 안내와 SURROUNDINGS에는 비상장비함만 나타났고, 전원 삽입·켜기 후 두 상자 안내와 버튼이 함께 나타났다. 손전등 보기의 전원 없음/ON/OFF 잔량과 확인의 상태가 맞았으며 가방 끄기 버튼도 기존 명령을 전송했다. 전력 OFF 관리동은 밤의 환경, 발전실은 고정 어스름을 표시했다. 발전기 수리 버튼으로 첫 시설 가동 사건과 밝음 state를 확인했고 ON 관리동/발전실은 시설 문장으로 바뀌었다. 밤 부두의 시설 문장과 재시작 후 맑은 낮 부두의 낮빛 문장을 구분했다. 저장 감사에서 시설 schema version 1/outpost_power=True와 A generator_fixed=True, B=False가 유지됐다. 개인 부품·보상·진입 조건과 후속 플레이어의 발전기 서사는 이번 수정에서 바꾸지 않았다.

맑은 수송차는 광원 OFF에서도 두 대상 안내가 나왔다. 1366px의 최종 문서 clientWidth/scrollWidth는 1351/1351px이며 390px은 390/390px·로그 364/364px로 가로 넘침이 없었다. 화면 캡처로 좁은 화면의 상태·삽입 문법 줄바꿈과 주변 버튼을 확인했고 최종 탭의 콘솔 오류/경고는 0개였다. CSS/JS 주소는 기존 `?v=lighting`을 유지한다. 이번 후속 변경은 정적 파일을 바꾸지 않았으므로 node 검사·collectstatic은 반복하지 않았다. 실제 OS 한글 IME와 모든 날씨/달 조합의 브라우저 전수 검사는 미실행이다. 검증 후 서버와 임시 탭을 종료하고 DB는 보존했다.

후속 순수 테스트는 65개, 통합 테스트는 187개로 총 252개다. 최종 실행 코드의 전체 로컬 검증에서 순수는 모두 통과하고 통합은 새 시설 알림보다 수리 결과가 먼저 올 것으로 가정한 기존 임무 테스트 한 건만 실패했다. 해당 테스트를 두 메시지와 부품 3개/XP 50를 확인하도록 고친 뒤 재검증이 통과했다. 이후 수정은 테스트 기대값과 문서뿐이므로 동일 실행 코드의 전체 로컬 검사는 반복하지 않았다. 최신 HEAD의 전체 CI 결과는 PR Validation에서 구분해 확인한다.

별도 DB에서 시각/날씨를 고정한다. 기존 플레이 DB를 초기화하지 않는다.

1. 신규 캐릭터로 poor 환경에서 부두의 필수 NPC와 이동 출구가 보이는지 확인한다. wreck으로 이동해 conspicuous 비상장비함을 조사하여 손전등 ×1, 건전지 ×2를 받고 재조사는 추가 지급하지 않는지 확인한다.
2. 전원 없는 `손전등 켜`는 오류다. `탐사용손전등에 건전지 넣어`와 alias `손전등에 건전지 넣어`는 건전지 하나를 소비하고 30분 charge를 만든다. `손전등 확인`, `손전등 켜`, `손전등 꺼`와 가방 버튼을 비교한다. 잔량 중 재삽입 실패 시 새 전원은 남아야 한다.
3. poor에서 normal Enemy를 local/SURROUNDINGS/정확한 이름의 보기·공격으로 식별할 수 없어야 한다. 켠 뒤 local clear, distance=1 reduced가 되어 normal 적을 식별한다. distant_visible=False나 view:false 대상은 켜도 숨긴다. poor 방향 정찰은 방 이름·환경만 제공하고 일반 적 이름/수량은 숨긴다.
4. reduced에서 normal 시체는 보이지만 내부 작은 아이템/회수 안내는 숨기고 정확한 이름의 회수도 거절한다. 광원으로 clear가 되면 기존 단일/ALL·파티 배정·보호 규칙에 따라 회수한다. 이미 전투 중이면 손전등을 꺼도 상대와 타이머는 유지된다.
5. 별도 테스트 timestamp로 10분 사용/10분 꺼짐/20분 사용 후 소진을 확인한다. 마지막 광원 이전은 off와 내부 전원 폐기 안내, 여분만 이전하면 상태 유지다. 로그아웃·재접속에서 off/잔량 보존, 정상 서버 종료 후 공용 시설/개인 광원 저장을 확인한다.
6. A만 발전기를 수리한 뒤 A의 quest flag와 공용 outpost_power가 켜지고 B의 개인 quest는 그대로인지 확인한다. A/B가 보는 관리동/발전실 밝기는 같아야 한다. 기존 개인 복구 완료 캐릭터는 새 공용 전력을 추가 보상·부품 소비 없이 가동할 수 있어야 한다. bootstrap 반복과 재시작도 shared state를 보존한다.
7. 지원동 1층 보급관에게 손전등 30/건전지 6크레딧 구매와 JungleCache의 기존 붕대 ×2 + 건전지 ×2 보급을 확인한다. compatible 60분 전원 fixture를 추가하여 같은 명령 parser가 capacity를 읽는지 자동 테스트로 검증한다.
8. collectstatic 후 1366px/390px에서 `?v=lighting` 자산, 환경과 현재 시야 헤더, 가방의 켜기/끄기/확인 및 전원별 삽입 버튼, SURROUNDINGS의 숨김/복원을 확인한다. 콘솔 오류/경고와 문서/패널의 가로 넘침을 기록한다. 실제 OS IME는 자동 문자열 입력과 구분한다.

**광원 브라우저 기록 (2026-09-28):** 별도 SQLite 검증 DB의 신규 캐릭터로 밤·폭우의 poor 시야에서 부두 필수 시설과 이동 출구, 수송차 비상장비함을 확인했다. 첫 조사로 손전등 ×1/건전지 ×2를 받았고 전원 없는 켜기는 실패했다. 가방 삽입 버튼은 `탐사용손전등에 건전지 넣어`를 전송해 하나를 소비했으며, 켜면 공용 환경은 어두움/나쁨을 유지하고 현재 시야만 좋음으로 바뀌었다. local 일반 적·바닥 전리품이 다시 표시되고, 방향 정찰에서 normal 적이 보이되 selector/HP는 노출되지 않았다.

검증 DB의 잔량 2초 fixture로 실제 sweep 소진과 자동 off/전원 없음/대상 재숨김을 확인했다. 부두에서 6크레딧에 건전지를 재구매해 같은 명령으로 삽입할 수 있었고, 접속 종료·재접속 및 정상 서버 종료 후 off/남은 잔량이 유지됐다. 두 접속자가 있는 발전실에서 A만 수리하자 두 헤더 모두 어스름/보통에서 밝음/좋음으로 갱신됐다. 종료 후 저장 상태도 A generator_fixed=True, B=False, shared outpost_power=True였다. 발전기 검증은 별도 DB에서 개인 선행 조건·부품을 준비한 fixture를 사용했다.

1366px 문서 clientWidth/scrollWidth는 1351/1351px, 390px 문서는 375/375px·로그 339/339px·가방 317/317px로 가로 넘침이 없었다. 환경/현재 시야 헤더, 광원 버튼과 줄바꿈을 화면 캡처로 확인했다. CSS/JS 주소는 모두 `?v=lighting`이었고 확인한 두 탭의 콘솔 오류/경고는 0개였다. 검증 서버와 임시 브라우저 탭은 종료했다. 이전 자산을 미리 캐시한 조건, 실제 OS 한글 IME와 모든 기상/달 조합의 수동 전수 검사는 미실행이며 계산·권한·영속 경계는 자동 테스트로 검증한다.

**광원 자동 검증 (2026-09-28):** 최종 실행 코드에서 `scripts/dev.py check`와 `scripts/dev.py test`가 통과했다. 순수 테스트 61개·Evennia 통합 177개, 총 238개이며 실패는 0개다. metadata 호환 전원 30/60분의 동일 parser, 실패 시 inventory/charge rollback, 시간 투영·소진·로그아웃, v5→v6 보존, 개인/공용 전력 분리와 기존 복구 완료 캐릭터, 읽기 전용 관찰·잠긴 목적지 미조회·공통 지각·기존 전투 추적과 loot 권한 회귀를 포함한다. JavaScript 문법 검사와 `git diff --check`가 통과했고 game 및 별도 검증 서버에서 최신 정적 파일을 수집했다. 이후 수정은 검증 기록·예시 문서뿐이다.

## 본부 5단계: 단일 화폐·회수 자원 정산 확인

별도 검증 DB의 일반 탐사자에게 가방 scrap과 크레딧을 준비한다. 플레이 DB를 초기화하지 않는다.

1. 1층 중앙에서 `서` → `서` → `북`으로 자원 정산소에 들어간다. 실제 자원 정산관·환율 버튼·크레딧과 구분된 회수부품 resource 표시를 확인한다.
2. `환율`/`정산관 환율`로 1개 = 10크레딧을 확인한다. `회수부품 교환`은 1개, `회수부품 3개 교환`은 정확히 3개, `정산관에게 회수부품 모두 교환`은 가방 전량을 정산한다. 버튼도 같은 대상 명령을 전송해야 한다.
3. 0개/-1개/abc개/보유량 초과와 부품 없이 모두를 입력한다. Credits·inventory·storage가 바뀌지 않아야 한다. `강철마체테 교환`/`강화 조끼 교환`으로 장비가 지급되어서는 안 된다.
4. 보이는 정산관을 숨기거나 다른 Room으로 옮기면 기존 위치의 명령·Web·hint가 서비스를 제공하지 않아야 한다. 실제 다른 안전 Room에서는 객체를 따라 이용하고 unsafe/전투는 거절한다. 여러 정산관이면 bare 입력은 대상 지정을 요구하며 번호로 하나를 고른다. hidden NPC는 개수에 포함하지 않는다.
5. 가방 scrap 6개/0C에서 6개 정산해 60C를 받은 뒤 `남` → `동` → `동` → `승강기` → `3층` → `내리기` → `동` → `북`으로 무기점에 들어간다. 상점 버튼·Credit 가격만 표시되는 목록·`강철마체테 구매`(60C)를 확인한다.
6. 정산하지 않은 scrap 3개로 윤대장 임무 수락·정비 기록 조사·발전기 수리를 진행한다. 부품 3개 소비와 기존 임무 진행이 유지되어야 한다. 부품의 전달·공용/개인 보관·loot도 기존 규칙을 따른다.
7. 데스크톱과 390px에서 자원 표시·정산 control의 줄바꿈과 가로 overflow, application console 오류를 확인한다. 자동 한글 문자열 입력과 실제 OS IME 검증을 구분한다.

전체 smoke에는 장비 직접 교환 전제가 없고 크레딧 구매와 4단계 의료 동선을 유지한다. 이번 정산 검증에 가입 rate limit의 610초 대기가 있는 전체 smoke를 추가하지 않는다. 실제 검증 결과는 아래에 시점별로 기록한다.

### 5단계 실제 검증 기록 (2026-09-29)

- 기준 origin/main `d1f3e54bcd7172bd11aec1a10624d4084b03e8c5`, branch `codex/hq-resource-settlement`의 최종 실행 코드·테스트에서 `scripts/dev.py check` 통과. 전체 `scripts/dev.py test`: pure 88개/0.068초, integration 239개/86.866초, total 327개 통과·실패/skip 없음, 통합 runner 95.978초(`work/settlement-final-full.log`).
- 관련 `scripts/dev.py test tests.test_text tests.test_settlement --parallel 2`: 20개/15.119초, runner 23.778초 통과. 정산 전용 `tests.test_settlement --parallel 2 --reverse`: 8개/10.815초, runner 19.337초 통과. 역순 검사는 최종 NPC 상세 보기 semantic 조정 전이며 정산 규칙은 같고 후속 관련·전체 검사가 상세 보기를 포함한다.
- 자동 테스트는 지원 문법·잘못된 resource/수량·직접 장비 교환 거절·실패 시 전체 profile 보존·hidden NPC/다중 대상·actual safe/unsafe/combat·server actions/resource push·bootstrap DB ID/alias/전체 상태 보존·6 scrap→60C→강철마체테 구매를 검증했다. 정산하지 않은 부품 3개로 실제 발전기 수리 명령이 성공하고 기존 quest가 진행된다. 부품 전달·공용/개인 보관·바닥 loot 회수와 전체 combat/loot/의료/훈련/승강기 회귀도 통과했다.
- `node --check game/web/static/webclient/js/primal.js` 및 diff 검사 통과. 최종 정적 파일을 game과 별도 검증 서버에 수집했다. 별도 SQLite 일반 계정의 웹에서 1층 중앙 서·서·북→정산소, NPC·환율 버튼·화폐/자원 표시를 확인했다. 직접 1개 정산으로 7→6/+10C, 모두 버튼이 보내는 `자원 정산관에게 회수부품 모두 교환`으로 6→0/+60C를 확인했다. 부품이 없으면 모두 버튼이 사라지고 환율은 남는다.
- 정산소 남·동·동·북·서→부두에서 보급소 버튼이 남고 Credit-only SHOP 14개 기존 가격·교환 가격/usage 제거를 확인했다. `강철마체테 구매`로 60C 차감·잔액 10C·장비 +1이 표시됐다. 데스크톱 문서 폭 1234/1234px와 390px 화면의 375/375px로 overflow가 없으며 긴 정산 버튼과 자원 행의 줄바꿈을 확인했다. 캡처는 `work/settlement-desktop.png`, `work/settlement-390.png`, `work/settlement-390-resource.png`, `work/settlement-result.png`, `work/settlement-purchase.png`다.
- 앱 코드 console 오류는 발견하지 않았고 Chrome 비동기 listener의 채널 종료 메시지 2건은 관찰했다. viewport를 원복하고 검증 서버·임시 탭을 종료했다. 플레이 DB는 읽거나 변경하지 않았다. 실제 OS IME, 서버 restart/reconnect와 운영 DB 적용은 미실행이다.
- 전체 smoke 미실행 — 현재 스크립트에 direct gear exchange/정산 전제가 없어 변경하지 않았다. 일반 가입 rate limit의 610초 대기와 반복 실제 전투 대신 이번 정산 Flow는 관련 자동 및 별도 DB 웹 검증으로 확인했다. production rate limit은 유지했다.

- 구현 HEAD `7196e58470717417319523fd9b56387731ebb83b`의 [PR #18 Game checks](https://github.com/wonmin82/primal-zone/actions/runs/36505944424)는 success다. 원격 check 통과, pure 88개(0.023초)·integration 239개(58.178초), total 327개·runner 61.265초를 실제 로그로 확인했다. PR은 OPEN이며 병합하지 않는다. 이 PR/CI 기록은 문서 전용 후속 커밋이며 이후 최종 HEAD의 CI는 따로 확인해 PR Validation에 기록한다.

## 본부 6단계: NPC 기반 상점 확인

1. 1층 중앙에서 `동` → `북`으로 보급품 상점에 들어간다. 보급관 보기·대화·상점·메뉴와 `붕대 구매`/`보급관에게 붕대 구매`를 비교한다. 보급품 5종만 표시되어야 한다.
2. `남` → `서` → `승강기` → `3층` → `내리기` → `동` → `북`으로 무기점에 들어간다. 무기상 메뉴에 무기 5종만 보이며 `강철마체테 구매`는 60C를 소비하고 1개를 지급해야 한다.
3. 무기점에서 `남` → `서` → `서` → `북`으로 방어구점에 들어간다. 방어구상 상점에는 방어구 4종만 표시하며 `방어구상에게 강화조끼 구매`는 65C를 소비해야 한다.
4. 실제 NPC를 다른 safe Room으로 옮기면 서비스가 따라가고 원래 시설에서는 사라지는지 확인한다. unsafe·전투·크레딧 부족·다른 catalog·구매 수량 모두 실패 시 profile 불변이어야 한다.
5. 같은 물품을 파는 두 상인을 두면 bare 구매/메뉴는 지정 요구, 이름·번호는 하나만 선택해야 한다. 다른 catalog 상인이 함께 있어도 상품 판매자가 하나면 자동 선택한다. hidden NPC는 후보·명령·hint·Web에 포함하지 않는다.
6. 부두에서는 상점/구매와 보급소 버튼이 없어야 한다. 윤대장·출구는 유지한다. 정산소 환율/모두 정산, 의무실 치료/휴식, 보관함 보기, 훈련실 기존 TRAINING panel도 확인한다.
7. scrap 6개/0C를 정산해 60C를 만든 뒤 승강기 3층 무기점에서 강철마체테를 산다. scrap 0·Credits 0·blade +1이어야 한다. 정산하지 않은 부품 3개로 발전기 수리도 여전히 가능해야 한다.
8. 데스크톱·390px에서 판매자 구매 버튼과 가격 목록에 가로 넘침이 없는지, 버튼/직접 명령 결과가 같은지, application console error가 없는지 확인한다.

`scripts/smoke.py`의 구매 경로는 옥상 귀환→승강기 3층→동·북 무기점이다. 구매·무장 후 남·서→승강기 1층→북·서 부두→북 초지→북 오솔길→동 관리동으로 복귀한다. 가입 rate limit·610초 대기·전투 흐름은 그대로다.

### 6단계 실제 검증 기록 (2026-09-29)

- 기준 main은 `d7141fbfd12572a19e744b36fd978fd8150c135e`이고 branch는 `codex/hq-npc-shops`다. PR #18 MERGED와 main Game checks success를 직접 확인했다. 최종 재fetch에서도 기준 main이 같아 rebase로 기존 이력을 재작성하지 않았다.
- `scripts/dev.py check`: 통과. 최종 `scripts/dev.py test`: pure 91개(0.127초)·integration 248개(82.570초), total 339개 통과, 실패/skip 없음. 통합 runner는 91.606초이며 실제 로그는 `work/shops-final-full-success.log`다. 메모리 SQLite·빠른 hash·기존 병렬 WorldCommandTest 인프라를 유지한다.
- 개발 중 관련 94개 검사는 옛 부두 구매 fixture와 누락된 rooms fixture 2곳에서 실패했다. 수정 후 실패 2개와 새 상점 suite를 역순·병렬로 재검증해 11개(15.312초, runner 26.203초) 통과했다. 첫 전체에서 옛 JS query 기대값 1개가 실패해 해당 1개부터 통과시킨 뒤 위 최종 전체를 실행했다. assertion 삭제/완화와 가격 변경은 없었다.
- `node --check game/web/static/webclient/js/primal.js`, `python -m py_compile scripts/smoke.py`, `git diff --check`: 통과. 최종 정적 파일을 game과 별도 검증 서버에서 수집했다. 이후 실행 코드·테스트 변경은 없다.
- 별도 SQLite DB의 일반 계정으로 실제 동선과 세 NPC·자기 catalog 메뉴를 확인했다. 보급관 붕대 버튼과 직접 명령은 각각 8C 차감/1개 지급, 무기상 강철마체테 버튼은 60C, 방어구상 강화조끼 버튼은 65C였다. 정산소의 환율/모두 버튼으로 scrap 6→0/+60C 후 다시 승강기 3층 무기점에서 구매해 60C 차감/장비 추가를 확인했다.
- 부두에는 윤대장만 남으며 상점 버튼이 없고 `상점`/`붕대 구매`는 상인 없음으로 실패했다. 정산 버튼·의무관 치료/침대 휴식 버튼·보관상자/개인 보관함 보기 버튼을 확인했다. 훈련실에서는 기존 TRAINING 학습/배분/재훈련이 활성화되고 SURROUNDINGS에는 대화만 표시했다. 의료/훈련 서비스를 이번 브라우저 검증에서 다시 실행하지는 않았으며 동작 회귀는 자동 테스트로 확인했다.
- 데스크톱의 document client/scroll 폭은 1234/1234px, 390px viewport에서는 375/375px였다. catalog와 구매 버튼에 가로 넘침 없이 줄바꿈이 적용됐다. 앱 JavaScript stack 오류는 관찰하지 않았고 Chrome의 비동기 listener 채널 종료 메시지 2건은 별도로 기록했다. 검증 탭·서버는 종료하고 viewport를 원복했으며 플레이 DB는 읽거나 변경하지 않았다.
- 전체 smoke 미실행 — 일반 가입 rate limit의 610초 대기와 실제 반복 전투 때문에 변경된 무기점 구매/탐사 복귀 경로를 integration·별도 DB 브라우저·syntax 검사로 검증했다. production rate limit은 변경하지 않았다. 실제 OS IME, 이번 변경의 전체 서버 restart/reconnect, 운영 DB 적용과 전체 멀티플레이 수동 검증도 미실행이다. 기존 자동 회귀는 위 전체 suite에 포함되며 7단계 closeout은 별도 요청이다.
- 구현 HEAD `117bc17beaf1c73417ecd150b2145997f2a551ef`의 [PR #19 Game checks](https://github.com/wonmin82/primal-zone/actions/runs/36518994902)는 success다. 원격 check와 pure 91개(0.045초)·integration 248개(99.501초), total 339개·runner 105.321초를 실제 로그로 확인했다. 이 PR/CI 기록은 문서 전용 후속 커밋에 포함하며 이후 최종 HEAD CI는 별도로 확인해 PR Validation에 반영한다. PR은 OPEN이며 병합하지 않는다.

## P0 live smoke 실제 검증 기록 (2026-09-29)

기준 main `e4977132206e9edc285a35773758ef989d4fb6dd`(PR #19 MERGED·main CI success), 브랜치 `codex/smoke-p0-isolation`에서 확인했다. 본부 7단계 closeout은 수행하지 않았다.

| 실제 명령 | 결과 |
| --- | --- |
| `scripts/dev.py check` | 통과 |
| `scripts/dev.py test` | pure 99개/2.030초, integration 250개/81.877초, total 349개, runner 91.526초, 실패/skip 없음 |
| `scripts/dev.py smoke` 연속 #1 | 43.486초, auth/party/combat/corpse/lifecycle/protection/respawn/shop/persistence/cleanup 통과 |
| `scripts/dev.py smoke` 즉시 연속 #2 | 43.960초, 새 DB/계정/포트로 같은 단계 통과 |
| `scripts/dev.py smoke-full` | 168.024초, production 타이머 실제 실행 통과 |
| `git diff --check` | 통과 |

Full의 actual first combat round는 2.804초, 시체→ground 29.924초, 같은 적 재생성 44.879초, 전리품 보호 만료 121.373초다. 전리품 보호는 시체 decay 시각부터 다시 세지 않는다. Quick는 같은 actual scheduler를 짧은 settings로 실행했으며 Full에 그 값이 유입되지 않았다. 전체 시간은 새 DB migration/world/fixture/static/server 준비와 인증·시나리오·프로세스 종료·디렉터리 정리를 포함한다. 근거: Git 제외 `work/smoke-final-tests.log`, `work/smoke-final-quick-1.log`, `work/smoke-final-quick-2.log`, `work/smoke-final-full.log`.

세 최종 live 실행 전후 일반 플레이 SQLite `game/server/evennia.db3`의 SHA256·mtime_ns·size가 모두 동일했다(733184 bytes). 각 실행의 성공 디렉터리와 own Portal/Server는 제거됐다. 개발 중 실패 실행은 별도 DB/로그를 보존하고 process를 종료한 뒤 새 환경에서 재실행했다. 자동 harness 검사도 주입된 실패 뒤 owned process 종료·다음 실행의 별도 디렉터리·잘못된 cleanup 경로 거절을 확인했다. 사용자 PostgreSQL에는 접속하지 않았다.

기존 339개 자동 검사를 삭제/완화하지 않았고 timing/settings/guard/CLI/failure cleanup을 위한 pure 8개와 integration 2개를 추가했다. 소스의 공개 register·610초 sleep·5회 사냥을 제거하고 production 30/45/120초 검증은 Full로 이동했다. README/architecture/AGENTS/인계에 현재 구조를 반영했으며 이전 4~6단계의 긴 smoke 미실행 기록은 해당 시점의 사실로 보존한다.

브라우저 DOM 자동화·실제 server restart E2E·OS IME·Windows CI·PostgreSQL CI·coverage·전체 boss/progression 검증과 공개 가입 610초 정책 검사는 이번 P0에서 미실행이다. JS/UI 변경이 없어 node 검사와 브라우저/정적 파일 수집을 추가하지 않았다(격리 서버 setup의 collectstatic은 수행). 일반 PR/main CI는 `test`와 Quick `smoke`만 실행하며 Full은 일반 CI에 포함하지 않는다. 최신 PR HEAD의 원격 결과는 PR Validation과 인계 원격 기록에 별도로 남긴다.

[PR #20](https://github.com/wonmin82/primal-zone/pull/20)의 CI 설정 수정 HEAD `d85d83ece5d300342c7b1a30d1fe98c5dab01220`에서 [test](https://github.com/wonmin82/primal-zone/actions/runs/36526697395/job/109271210799)와 [smoke](https://github.com/wonmin82/primal-zone/actions/runs/36526697395/job/109271210590)가 모두 success다. 실제 Ubuntu 결과는 check 통과, pure 99개/0.728초, integration 250개/95.112초, total 349개, runner 101.100초, Quick 전체 19.001초다. 최초 CI의 job 시작 전 startup_failure는 선택적 upload-artifact가 저장소 허용 목록에 없어서 발생했으며, 보안 설정을 유지하고 shell/Python 로그 tail 출력으로 해결했다. DB는 출력/업로드하지 않는다. 이 문서 기록 이후 최종 HEAD의 두 CI도 별도로 확인해 PR Validation에 남긴다. 실행 코드가 동일하므로 기록 갱신만을 위해 로컬 전체 검사를 반복하지 않았다.
