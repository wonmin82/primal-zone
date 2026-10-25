# 통합 Actor Phase 1 구현과 검증 기록

## 기준선과 실행 범위

- 기준 main: `4288e0556aa6cd8cca8ab4bb3c4023d33d9608dc` (2026-10-25 확인).
- [설계 원문](actor-unification-design-v1.md)과 [확정 계획](https://github.com/wonmin82/primal-zone/issues/83#issuecomment-6396602387)을 적용한다. 이번 실행은 PR-A → PR-B Stacked PR의 병합 전 리뷰까지이며 PR-C·병합·Issue 종료·소스 브랜치 삭제는 수행하지 않는다.
- 변경 전 [main CI 40182627829 Attempt 1](https://github.com/wonmin82/primal-zone/actions/runs/40182627829)은 정확한 기준 SHA에서 test·smoke·contracts·browser-e2e 4/4 SUCCESS였다. 이전 작업에서 확인한 실행 결과이며 이번 구현에서 새로 실행한 결과가 아니다. 기존 게임 소스와 테스트가 이 SHA에서 동일하므로 변경 전 기능 기준선으로 재사용한다. 이후 PR HEAD의 검사·CI를 대신하지 않는다.
- 기존 수치·고정 RNG·출력·Spawn·임무 기대값은 아래 테스트의 실제 assertion을 기준선으로 사용한다. 새로운 Level은 기존 HP·공격·방어·드롭·보상 수치를 다시 계산하는 입력이 아니다.

## 실제 책임과 PR-B 이전 목록

| 영역 | 기준선의 실제 소유자 | Cutover에서 보존하거나 이전할 책임 |
| --- | --- | --- |
| Enemy 정의·Spawn | content/starter.py·deep_jungle.py → content.ENEMIES, ROOMS의 enemies·spawn_id_for, bootstrap._build_world | ACTORS·ACTOR_SPAWNS로 단일화, 기존 표시·별칭·배치·현재 상태 보존 |
| NPC·시설 | typeclasses/interactables.py의 INTERACTABLES와 각 Typeclass, bootstrap | Actor와 WorldObject를 구별하고 독립 Door·Storage 도메인 재사용 |
| Action | world/actions의 schema·registry·resolver·gateway·manifest | 기존 단일 Index·명시 Manifest·동기 완료·등록 검증 유지, Global/Entity Source 확장 |
| Combat | Enemy engage/receive_attack/enemy_tick/_finish_death와 Explorer combat_tick/resolve_combat_round | 공통 Domain Service·Combatant로 이전, 순수 rules와 무기·기술 도메인 규칙 유지 |
| Reward·Quest·Corpse | Enemy._finish_death, Explorer profile quests, Corpse.from_enemy, loot_service·native LootClaim | 하나의 종료·정산 경계와 영속 완료 근거, XP·칩·Quest·Corpse·Loot·Respawn 원자성 |
| Timer·Recovery | Enemy의 next_attack_at·respawn_at·state, Explorer profile recovery, lifecycle.reconcile_world, 서버 시작 Hook | 메모리 delay와 영속 시각 구별. 기존 재시작 전투 종료 정책과 Respawn 복구를 혼동하지 않음 |
| Speech·Dialogue | commands/social, npc_dialogue, dialogue_intents, primal_inputfuncs, interactable_services·credential_service | 공개 발언과 영속 Intent 효과 분리, 180초 문맥·Session 토큰·Quest SSOT 보존 |
| Item·Equipment·Loot | ItemEntity·LootClaim·CurrencyLoot, equipment_service·item_inventory·loot_service | Native 실물 원본과 계산 context 보존, 실제 소비자 이전 후 공식 legacy fallback 제거 |
| World·Format | bootstrap.build_world, item_runtime.initialize_fresh/require_runtime, Door 설치·lifecycle | Fresh/기존/부분/손상 구별, 전체 READY와 ItemRuntime 도메인 버전 구별 |
| 선택·표현 | selection_numbers, targets, state, zone_rooms, observation, 웹 client | ACTOR typed reference, Scope·B-1·실물 ID·가시성·오래된 요청 안전성 |
| 전달 | ActionResult·after_change·Prompt lifecycle·Web push | 확정 결과와 수신 범위·순서 보존, 전송 실패로 효과 재실행 금지 |

Enemy 직접 참조자는 Explorer·Party·lifecycle·selection_numbers의 api/signals·targets·state·zone_rooms·loot·smoke_startstop 및 테스트에 걸쳐 있다. 이름만 바꿔 구형 실행 경로를 남기지 않고 등록과 실제 호출을 함께 대조한다. NPC Dialogue의 Typeclass 이름 기반 Intent 판정도 Capability/Profile 연결로 이전한다. 사용자 Shortcut의 데이터 변환 책임은 Dialogue Dispatcher 제거와 별개다.

`world/item_migration/`의 scan·convert·audit·workflow·ledger는 명시적 과거 데이터 유지보수 계약이다. Runtime의 Native-only 전환을 이유로 운영 DB·백업을 변환하거나 삭제하지 않는다. 해당 도구의 지원 범위는 새 Runtime과 역사적 운영 경계를 구별해 설명한다.

## 기준선 회귀 매핑

| 보존할 의미 | 기존 검증 근거 |
| --- | --- |
| Enemy 종류·Spawn·반복 bootstrap | test_enemies·test_regions·test_headquarters·test_bootstrap_exits |
| 고정 RNG·공유 HP·Boss Scaling·기술·정신력 | test_combat·world/test_progression·world/test_final_content |
| Party·Claim·Threat·참여 보상·XP·칩·Corpse·Loot | test_rewards·test_loot·test_party_overhaul·test_loot_entities·test_currency_loot |
| Quest·Dialogue·상점·의료·훈련 | test_npc_dialogue·world/test_dialogue_intents·test_hq_services·test_medical·test_shops·test_growth |
| ItemEntity·Equipment·Storage·Credential | test_item_entities·test_equipment_entities·test_storage_actions·test_credentials |
| Door·Movement·출입권한 | test_doors·test_door_schema·test_bootstrap_exits·test_credentials |
| B-1·Target·Web Action | test_selection_numbers·test_targets·test_action_runtime·test_web_state·브라우저 통합 시나리오 |
| Recovery·Respawn·재시작 | test_lifecycle·test_recovery·기존 격리 gameplay smoke |

## 실행 결과 기록 원칙

검사마다 고정 HEAD와 미커밋 범위·명령·환경·결과·Job ID를 기록한다. READY/RUNNING은 성공이 아니며 최종 PASSED·원래 종료 코드·SHA/Fingerprint를 확인한다. 성능은 같은 Fixture·Clock·RNG·환경에서 측정하고 수치를 추정하지 않는다. 자동 브라우저와 실제 Windows/Chrome IME 수동 검증을 구별한다. 미실행·미완료 Gate는 PASS로 기록하지 않는다.

PR-A/G1 및 PR-B/B1~B5/G2의 실제 결과는 완료되는 대로 이 문서와 각 PR Validation에 추가한다.

## PR-A 로컬 구현·검증

Actor/WorldObject·불변 Definition·Sparse Capability·Spawn, 기존 단일 Registry의 Global/Entity Source와 명시 Root, 효과별 정책·결과·Completion, 내부 Principal, Combatant·Encounter·영속 지연 근거, Commit 후 Delivery와 Fresh World Format 기반을 구현했다. 운영 ACTORS/Spawn은 빈 등록이며 기존 NPC/Enemy·Bootstrap·전투·Dialogue·Item 공식 경로는 유지한다. 명시 EntitySource는 Provider 등록이 필요하고, 기존 positional 선언의 Entity Source 호환은 보존한다. 내부 Principal은 웹 Payload로 받지 않는다.

| 검사 | 실제 결과 |
| --- | --- |
| `.venv/Scripts/python.exe scripts/dev.py check` | PASS |
| 신규 Actor/참조/Action/Domain 및 기존 Registry/Runtime/B-1 직접 영향 검사 | 최초 Fixture ID·동기 완료 표현 오류와 Encounter Identity 결함을 확인하고 실패 범위부터 수정·재검증 |
| Action 모듈 최종 재검증 | `1e8c8f1df0cb458d937b89e3dd481428`, 12개 PASS, exit 0, 18.375초 |
| `.venv/Scripts/python.exe scripts/codex_wait.py local --command test --parallel 4` | `6f8bb94d5efa465fa096530ca500201f`, 순수 규칙 255개·Evennia 통합 1,158개 PASS, 원래 exit 0, 1021.109초 |
| 전체 검증 기준 | HEAD `4288e0556aa6cd8cca8ab4bb3c4023d33d9608dc` + PR-A 미커밋 코드, 시작/종료 Fingerprint `760f2a0e6e4d43b24199100358f4561f2083a94021f20c470b56e296c9da803b` 일치, 소유 자원 정리 확인 |
| 설계 문서 검사 | 27장·부록 A~D·P1 8건/P2 5건·확정 일정·상대 링크 확인 PASS |
| 독립 Reviewer | `reviewer_julia`: 실제 Diff·원문·실패/재검증 근거 검토. 보완 확인 후 A — Ready for Review, 잔여 P0/P1/P2 없음. 전체 검사와 원격 CI는 부모가 별도 확인 |

리뷰에서 Native EquipmentProfile metadata 유실, 완료 Operation 재예약, Global ROLE Root 의존 계산, 명시 Provider 누락 검증 및 수직 Fixture 공백을 발견해 수정했다. Native 장비·선택 UUID 소비, 동일 회차/Operation 멱등성, 복합 Actor 실제 Gateway, Global Actor/Item 이동·가시성·소유권·오래된 참조, World Format의 잘못된 버전을 검증한다. 실패 로그는 각 ignored 감시 Job에 보존한다.

최종 코드 검사 이후 문서 안내와 실행 기록만 갱신하므로 동일 Python 전체 검사는 반복하지 않는다. 로컬 실브라우저·OS IME·운영 DB 복구·실제 운영 Seed는 PR-A에서 미실행이다. 새 Foundation Fixture와 기존 운영 경로 보존 검증을 실제 Actor Cutover 완료로 표현하지 않는다. 최신 PR HEAD의 필수 CI와 G1 최종 상태는 PR Validation에 별도 기록하며, PR-B/G2는 아직 미착수다.

## 변경 전 순수 규칙 표본

2026-10-25 Windows Native / Python 3.13에서 기준 main의 rules.py·starter.py·deep_jungle.py·progression.py와 작업 트리 파일의 정규화된 원문 동일성을 대조한 뒤, Enemy 8종·Spawn 15개와 고정 RNG seed 84의 player_attack/enemy_attack 결과를 `work/actor-v16/baseline-rules.json`에 보존했다. DB·개발 서버는 사용하지 않았다.

같은 프로세스에서 5회, 회당 Enemy별 400회 `new_profile`+기본 공격 계산의 실제 경과는 0.420650·0.429629·0.423189·0.378274·0.465905초였다. 이는 순수 규칙 계산 표본이며 Resolver SQL·world_change 잠금·실제 Combat Tick·Bootstrap·Delivery 성능 측정으로 확대 해석하지 않는다. PR-B 최종 상태에서 같은 조건의 후속 비교와 DB 경계 측정이 필요하다.
