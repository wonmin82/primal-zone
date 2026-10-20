# Action 기능 전환 진행표 (Issue #66)

규범은 [#44 v4.3](https://github.com/wonmin82/primal-zone/issues/44), 공통 API는 [Action 아키텍처](action-architecture.md)다. Phase 1 인수 기준은 `e93e6c70c88653c4695d065c3d82a15813379643`이다. 아래 표는 §10의 전체 범위를 추적하며, 아직 구현하지 않은 ID는 계획임을 구분한다. Phase 2 전체 Gate는 PR A~D의 승인 병합과 해당 main CI 전까지 미완료다.

| 기능·공개 동사/별칭 | 이전 공개 경로 | 신규 Action / Service / Provider·Role | Baseline | PR / 상태 |
| --- | --- | --- | --- | --- |
| 문 열어·닫아·잠궈·풀어 | commands/doors.DoorCommand → world.doors.operate | door.open/close/lock/unlock → room_npc.door → operate_endpoint / 실제 Exit 안정 참조 | test_doors, test_door_schema | A / PR #70 병합·main CI 완료 |
| 조사·수리 | commands/world_actions.TargetAction → ActionObject.perform_action/act | world.<시설 종류> → room_npc.effect → interactable_services / 필수 World Object Provider | test_command_overhaul, test_regions, test_phase6_runtime | A / PR #70 병합·main CI 완료 |
| 소각·소각 확정 | commands/incinerator.Burn → incinerator_service.incinerate | incinerator.burn normal/confirmed → room_npc.burn → incinerate_selected / 소각기 Provider + Root Item Subject | test_incinerator, test_credentials | A / PR #70 병합·main CI 완료 |
| 목록·품목·품·목·메뉴 | inventory.Shop → Shopkeeper.act | shop.menu.<상점> → room_npc.effect / Shop Provider | test_shops | A / PR #70 병합·main CI 완료 |
| 사·구입 | inventory.Buy → Shopkeeper.act | shop.buy.<품목> → room_npc.buy → shop_service.buy / 품목 제공 상인 + 선언 인자 | test_shops, test_shop_entities | A / PR #70 병합·main CI 완료 |
| 가치·얼마 | inventory.Value → Shopkeeper.act | shop.value.<품목> → room_npc.value / 취급 상인 + 품목 인자 | test_shops, test_shop_entities | A / PR #70 병합·main CI 완료 |
| 팔아·팔·판 | inventory.Sell → Shopkeeper.act | shop.sell.<상점> → room_npc.sell → shop_service.sell / 상인 + Root Item Subject + 별도 수량 | test_shops, test_shop_entities | A / PR #70 병합·main CI 완료 |
| 회복 | world_actions.Treat → Doctor.act | medical.treat → room_npc.effect → interactable_services.doctor / 의료 Provider + 요청 HP | test_medical | A / PR #70 병합·main CI 완료 |
| 휴식·rest | world_actions.Rest → Bed.act | medical.rest → room_npc.effect → interactable_services.bed / 침대 Provider | test_medical, test_prompt | A / PR #70 병합·main CI 완료 |
| 배워 | skills.Learn → GrowthTrainer.act/train | training.skill.<기술> → room_npc.effect / 담당 Skill Provider + 기술 인자 | test_growth, test_growth_review | A / PR #70 병합·main CI 완료 |
| 배분 | skills.Allocate → GrowthTrainer.act/train | training.attribute.<특성> → room_npc.effect / 담당 Attribute Provider + 양 | test_growth | A / PR #70 병합·main CI 완료 |
| 재분배·재훈련 | skills.Retrain → GrowthTrainer.act/train | training.reset.attributes/skills/all → room_npc.effect / 관리관 Provider | test_growth | A / PR #70 병합·main CI 완료 |
| 교환·exchange / 환율·rate | commands/settlement → SettlementOfficer.act | settlement.exchange/all → room_npc.settle / settlement.rate → room_npc.effect / 정산관 Provider | test_settlement | A / PR #70 병합·main CI 완료 |
| 임무·보급·Credential 연계 | NPC 대화 및 시설 act | 조사/수리 효과는 도메인으로 이전, 전역 말/pz_dialogue는 유지 | test_npc_dialogue, test_regions, test_integration | A / PR #70 병합·main CI 완료 |
| 사용·먹어·eat·마셔·drink | combat.Use / items.Eat/Drink | item.<정의>.use/eat/drink → item_equipment.execute → skill_services.use_support / rules.eat_or_drink + UUID 소비 바인딩 | test_item_interactions, test_combat, test_item_entities | B / PR #71 병합·main CI 완료 |
| 착용·입어·입·무장·wield·벗어·벗·해제·unwield·주무기·정보 | inventory/items 장비 명령 | item.<정의>.equip/wield/remove/unwield/active_weapon/information → item_equipment.execute → equipment_service / information_for_item | test_equipment, test_equipment_entities, test_item_interactions | B / PR #71 병합·main CI 완료 |
| 넣어·꺼내 / 보관 | items.Store/Retrieve → Container.act | storage.store/retrieve → storage.transfer → item_transfer_native.transfer_selected / Container + CURRENT/STORAGE Subject | test_item_entities, test_phase6_runtime | B / PR #71 병합·main CI 완료 |
| 재장전·장전·채워·넣어·꺼내 / 총기·탄창 | commands/firearms, items | item_ops.reload/load/fill/inside_fill/ammo_insert/magazine_remove/ammo_remove → item_ops.execute → firearm_service / Root Provider·Inside Subject·Source | test_firearms, test_equipment_entities | B / PR #71 병합·main CI 완료 |
| 켜·꺼·확인·넣어 / 광원 | items.LightOn/Off/Status | item_ops.light_on/light_off/light_status/power_insert → item_ops.execute → lighting_service / Root 광원 Provider·전원 Source | test_lighting, test_lighting_entities | B / PR #71 병합·main CI 완료 |
| 가져·집·시·시2~시5·다중 Source·부분/화폐 | inventory.Take → typeclasses/loot.take_loot | loot.take → loot.pickup → loot_service.pickup / Corpse·Ground Source + 안정 ItemEntity/Currency ID | test_loot_actions, test_loot_action_invariants, 기존 Loot·Currency·Party 회귀 | C / PR #73 병합·main CI 완료 |
| 전역 봐·말·도움 / 객체 상세·Help·Web | character.Help/Look, social.Say, state/web_actions | 전역 진입점 유지, 객체 Action 표시를 Compiled Index로 통합. A는 소유 기능만 동기화 | test_web_state, test_web_prompt, test_text, test_npc_dialogue | D / M06 통합·기술 검증 진행 |

## 전환과 데이터 경계

- 기능별 운영 Manifest 등록과 기존 COMMANDS 해제를 같은 PR에서 수행한다. 신규 Service는 기존 Command/act/train을 재호출하지 않는다. 도메인 함수는 기존 효과를 보존하며 대상의 이름·번호를 다시 파싱하지 않는다.
- Root Item Subject의 `definition_ids`는 상점 취급 등 선언된 콘텐츠 범위다. 현재 Scope·소유·권한 검사는 기존 Resolver/Gateway를 그대로 사용한다. 콘텐츠 제한은 번호 그룹이나 번호 발급에 영향을 주지 않는다.
- B-1·UUID·quantity는 별개다. 신규 Action은 B-1을 사용하고 아직 미전환인 Player/Party/기능 선택 경로는 다음 PR의 명시 cutover 전까지 유지한다.
- 플레이 DB migration/seed/복원은 이 개발 작업에서 실행하지 않는다. 배포 절차는 [Action 아키텍처](action-architecture.md)의 기존 데이터 절차를 따른다.
- 전역 말/pz_dialogue, 이동·Engine/Exit·Player/Party·개인 줄임말/묶음은 승인된 유지 경로다. Legacy 문자열이 남는다는 이유만으로 제거하지 않는다.

## PR A의 사용자 동작 Baseline

| 기능 | 입력·대상 | 효과·비용·권한 | 출력·웹·영속성 | 직접 회귀 |
| --- | --- | --- | --- | --- |
| 문 | 정식 이름·방향 Alias·B-1 번호 → 실제 Door Endpoint | 기존 열쇠·래치·출입·전투 조건, OPEN 60초, 통과 시 연장, 중복 열기 미연장 | 공개 명령과 Typed Endpoint Action이 같은 도메인 실행. 원격·권한 변경 요청은 원래 Endpoint에서 거절 | test_doors, test_room_npc_actions |
| 조사·수리·임무 시설 | 실제 Object Provider를 명시, 복수 제공자를 임의 선택하지 않음 | 기존 read_record/claim_cache/restore_outpost_power/표식·신호 규칙과 개인 진행·보상 1회 보존 | 기존 문구·semantic 출력은 커밋 뒤 전달. 전역 말/pz_dialogue와 임무 발급 경로 유지 | test_integration, test_regions, test_phase6_runtime, test_room_npc_actions |
| 상점 | 구입/팔/판/얼마 및 기존 이름 정규화. 구매 품목은 고정 선언, 판매는 Root UUID와 별도 수량 | 55칩 구매·27칩 매입 예시, 탄창 잔탄 가치, 재고 source/sink·소유·장착·거래 원자성 유지 | B-1 번호와 가격·총액 표시. 실제 UUID 판매 후 재전송 지급 0회. 광원 잔여 상태와 마지막 활성 참조 보존 | test_shops, test_shop_entities, test_economy, Quick Smoke |
| 의료·휴식 | 의무관에게 20 회복, 숫자 단독 요청, 침대 휴식/rest | 실제 20 HP/5칩 예시, 요청 상한·안전 지대·전투·시설 조건과 기존 회복 계산 유지 | 실제 인증 Session·Prompt·중복 요청 0회, 멀리 있는 시설·비공개 객체 정보 미노출 | test_medical, test_room_npc_actions |
| 교관·성장 | 기술/특성 이름·ID와 담당 Provider, +1 수량, 재분배/재훈련 | 기존 XP 기반 예산·포인트·상한·분야·전투 조건. 특성/기술/전체 재분배 구분 | 버튼은 배열 순서가 아닌 선언된 scope를 전송. 실제 특성 재분배 후 기술 Rank 불변 | test_growth, test_growth_review, Node 계약, TEST-66A-01 |
| 정산 | 회수 부품/scrap, 기본 1개·N개·모두, 환율/rate | 기존 1개 10칩 지급·수량 감소·안전 지대·제공자 유일성. 현재 Inventory Source의 UUID·수량 집합을 잠금 후 재검증 | 33개 스택도 웹 제한 확대 없이 전체 정산. 다른 소유자·삭제/교체/수량 변경의 오래된 요청은 거절 | test_settlement, test_room_npc_actions, test_economy |
| 소각 | 소지 Root ItemEntity UUID·수량. 출입증은 별도 확정 Variant | 일반 스택 부분 소각은 UUID 유지. 출입증 수량 명시 거절, 원래 대상·Session에 결합된 서버 확인 토큰, 내부 보호 규칙 유지 | 실제 웹 요청의 권한 소실·UUID 삭제·재발급 및 중복 효과 0회, 실패 시 프로필/행/참조 Rollback | test_incinerator, test_credentials, test_room_npc_actions |

기존 임시 후보 인덱스와 달라지는 것은 승인된 B-1 고정 번호와 독립 Provider 유일성이다. 결번은 다른 대상으로 대체하지 않는다. 비스택 장비는 각각의 UUID에 단일 판매 Action을 제공하며 Legacy 수량 집계 버튼을 병행하지 않는다. 과거 Legacy 자료형의 도메인 호환 검사는 명시적으로 유지하지만 운영 Action이 실패했을 때 해당 Handler로 돌아가는 경로는 없다.

## Legacy 활성 경로 점검

- 전환한 공개 동사는 `COMMANDS` 및 과거 gameplay 재노출에서 제거했다. `ActionObject.perform_action`과 해당 클래스의 `act/train` 효과는 도메인 함수로 이동했다.
- PR B는 Container의 기존 `perform_action/act` 보관 진입점도 제거한다. 기존 `incinerate(value)` 같은 자료형 호환 API는 격리된 역사적 도메인 회귀에서만 사용하며 신규 실행 진입점이 호출하지 않는다.
- 객체 Action 버튼은 실제 Action ID/Variant/Typed Reference/인자를 전송한다. 이동·전역 봐·말 및 승인된 대화 버튼은 기존 텍스트/대화 Protocol을 유지한다.
- Help는 공개 Compiled Verb 메타데이터를 기존 renderer에 합치고, 문서의 역사적 명령 스냅샷은 수정하지 않는다. 등록·Help 조회는 게임 Service를 실행하지 않는다.
- 운영 DB migration/seed/복원은 미실행이다. 이 PR의 Inventory Source는 논리 참조이며 신규 Schema나 번호 재할당을 추가하지 않는다. 기존 Phase 1 Schema/번호 초기화 적용은 별도 승인된 운영 절차다.

## 검증 기록

Windows Native / Python 3.13.15 / Evennia 6.1.0의 격리 SQLite에서 다음을 실행했다. 기준은 main `e93e6c70c88653c4695d065c3d82a15813379643` 이후 PR A 작업 트리이며, 최종 Commit SHA와 원격 CI는 PR의 Validation에 기록한다.

- `scripts/dev.py check`: PASS.
- `scripts/dev.py test --parallel 4`: 순수 Python 232개 및 Evennia/Django 946개 PASS, 전체 764.699초.
- `scripts/dev.py smoke`: PASS, 199.082초. 실제 인증·WebSocket·Action 판매·중복 지급 방지·재접속·프로세스 정리 확인.
- `scripts/browser_e2e.py`: 실제 Chromium 10개 PASS. 구조화된 성장 재분배, HTTP/세션/Prompt/리소스 확인. 이후 Door 방향 Alias 보완은 전체 테스트와 최종 Smoke로 확인했다.
- `npm run test:contracts`: 55개 PASS. JavaScript 두 파일 syntax 및 `git diff --check`: PASS.
- Registry 직접 회귀 40개 PASS. 운영 Manifest 정적 컴파일은 SQL 접근 금지 조건에서 5.041초였으며 서비스 효과를 실행하지 않는다.

플레이 DB의 크기·mtime·SHA256은 검사 전후 동일했다. 운영 migration/seed/복원은 실행하지 않았다. 수동 브라우저·Windows IME·Full Smoke·38개 종합 검증은 #67의 후속 범위이며 PostgreSQL/다중 서버는 미검증이다. M01/M02 로컬 검증 성공과 Phase 2 전체 Migration Gate를 구분한다. PR A는 아래 병합 근거를 확인한 뒤 PR B를 시작했다. PR B 승인 병합 및 해당 main CI 전에는 PR C를 시작하지 않는다.


## PR A 병합 확인과 PR B 진행

PR A [#70](https://github.com/wonmin82/primal-zone/pull/70)은 Merge Commit `d33e3ef5b12001eb84b41ff875c04122ffdcd851`로 병합했고, 정확한 병합 main의 [CI run 38871494369](https://github.com/wonmin82/primal-zone/actions/runs/38871494369)에서 test/smoke/contracts/browser-e2e 네 Job SUCCESS를 확인한 뒤 소스 브랜치를 정리했다. 위 PR A 로컬 검증은 당시 작업 트리의 기록이며 이번 PR B에서 새로 실행한 결과가 아니다. PR B는 이 병합 기준선에서 M03/M04를 구현·통합 검증 중이다.

| PR B 기능 | 실제 경로와 단일 효과 | 권한·영속성 비교 | 직접 회귀 |
| --- | --- | --- | --- |
| 붕대·식음료 | item.<정의>.use/eat/drink → item_equipment.execute → 지원/소비 도메인 | Root UUID를 저장 delta까지 고정, 부분 소비 번호 유지, 한 번에 하나, 전투 예약 UUID 재검증 | test_item_equipment_actions, 기존 소비·전투 회귀 |
| 장비·주무기·정보 | item.<정의>.* / item.inside_information.<탄창 정의> → item_equipment.execute → equip_item/unequip_item/set_active_weapon/information_for_item | 기존 슬롯·손·Unique·비전투·능력치·회복 유지, 총기 Root Provider의 Inside 탄창 정보 조회 효과 0회 | test_equipment, test_item_equipment_actions, test_equipment_entities |
| 개인·공용 보관 | storage.store/retrieve → storage.transfer → transfer_selected | 현재 시설 view/call·소유·위치 재검증, 부분 분할·병합·Scope 이동, 텍스트 전체 스택/웹 단일 UUID 전량 구분 | test_storage_actions, 기존 ItemEntity/Storage 회귀 |
| 총기·탄창·탄약 | item_ops.* → item_ops.execute → reload/load_ammo/unload_magazine/unload_ammo | 기존 탄종·장착·잔탄·전투 기회, 실제 Root/Inside UUID, stale Source 대체 없음 | test_firearm_lighting_actions, 기존 총기 회귀 |
| 광원·전원 | item_ops.light_*/power_insert → item_ops.execute → switch/status/insert_power | 기존 시간·잔량·시야·소지·부모·배터리 정책, 조회는 추가 자원 소모 없음 | test_firearm_lighting_actions, 기존 광원 회귀 |

소비·착탈·주무기·정보·Store/Retrieve·총기·광원의 기존 공개 Command 등록을 해제하고, 운영 Manifest와 Help/Web을 같은 ContentPackage 선언에 연결한다. 자동 재장전·채워의 텍스트 정책은 도메인에 보존한다. 웹 재장전 추천은 실제 탄창 Source를 가진 명시 장전 요청이며 웹 채워는 Inventory Source·snapshot 기반 전체 호환 탄약 집계를 잠금 아래 재검증하여 한 번 실행한다. 한 스택의 넣어 요청만으로 전체 채워와 동등하다고 간주하지 않는다. 신규 Action이 과거 Command로 돌아가는 fallback은 두지 않는다. M05 가져/집, 버려/줘, 전역 봐·말·도움·pz_dialogue와 Engine/Exit·Player/Party 선택은 이번 PR에서 제거하지 않는다.

소유 총기의 내부 탄창도 기존처럼 `카빈표준 정보`로 조회할 수 있다. 같은 이름의 소지 탄창·다른 부모가 있으면 모호성을 거절하고 `경비카빈의 카빈표준 1 정보`처럼 부모를 명시한다. 웹은 부모 Provider와 자식 Subject의 실제 UUID·Inside Scope를 함께 전송한다. 내부 자식 자체는 독립 Provider가 아니며 분리·소유권 이동 후 오래된 요청은 다른 대상으로 바뀌지 않는다. 잘못된 장비 동사는 선언된 거절 Action에서 정확한 기존 동사를 안내하고 효과를 실행하지 않는다. 이 진단 Action은 웹 조작 목록에 표시하지 않는다.

### PR B 관련 회귀와 최종 검증 진행

다음 결과는 Windows Native / Python 3.13.15 / Evennia 6.1.0 / 격리 SQLite에서 실행한 개발 검증이다. 기준은 `codex/issue66-item-equipment-actions`의 base `d33e3ef5b12001eb84b41ff875c04122ffdcd851` 이후 미커밋 구현이며 최종 Commit SHA의 원격 검증과 구분한다. 로컬 로그는 실행 증거이며 저장소에 포함하지 않는다.

| 검사·실행 근거 | 실제 결과 | 범위와 제한 |
| --- | --- | --- |
| `scripts/dev.py test tests.test_equipment tests.test_item_equipment_actions --parallel 1` / `prb-equipment-native-final.log` | 17개 PASS, 테스트 172.884초 | Native 공개 명령·모든 장비 정의·슬롯과 다른 row 불변·정확한 동사 안내·B-1·소비 UUID·전투 예약·Inside 정보·웹 성공/거절/중복 요청 |
| 도메인 Fixture 관련 검사 / `prb-domain-fixtures.log` | 13개 PASS, 테스트 93.261초 | 변경 기능의 Native 공개 실행 경로와 기존 도메인 기대를 검증. 전체 테스트의 대체 근거는 아님 |
| 교차 회귀 / `prb-cross-resume.log` | 152개 중 151개 PASS, 1개 FAIL | `tests.test_text.SemanticTextTests.test_target_appearance_actions_and_spaced_lookup`의 대상 표시 기대 불일치를 확인했으며 이 실행 전체를 PASS로 집계하지 않음 |
| 위 실패 테스트 재검증 / `prb-text-final.log` | 1개 PASS, 테스트 16.455초 | 표시 label 보정 후 실제 semantic 출력 재검증 |
| `npm run test:contracts` / `prb-contracts-final.log` | 56개 PASS, FAIL 0 | 같은 표시 이름이어도 버튼의 실제 UUID Action을 보존하는 계약 포함 |
| `scripts/dev.py check` / `prb-check-resume.log` | PASS | 코드 검사 결과. 게임 효과·브라우저 검증을 대신하지 않음 |
| `scripts/dev.py test --parallel 4` / `prb-full-final.log` | 순수 Python 232개 PASS + Evennia/Django 996개 PASS | 최종 소스의 전체 1,228개 검사 성공. 통합 테스트 963.757초, 통합 실행 전체 978.188초. 소유 작업자와 격리 DB 정리 확인 |
| 실제 Chromium / `.venv/Scripts/python.exe scripts/browser_e2e.py` | 11개 PASS, 212.515초 | `TEST-66B-01`의 실제 UUID 버튼·정보·장비 해제/재장착 포함. 소유 프로세스·인증정보 정리와 운영 DB 불변 확인. `npm run test:browser`의 uv 공용 캐시 접근 오류 후 기존 가상환경으로 같은 스크립트를 실행 |
| `scripts/dev.py smoke` / `prb-smoke-alone.log` | 단독 재검증 PASS, 154.433초 | 일행 전투·참여 보상·전리품 권리·생명주기·구매/판매/재구매·회복/재로그인·Prompt/영속성 확인. 소유 프로세스·임시 환경 정리와 운영 DB 불변 확인. 첫 병행 실행은 일행 공격 대기 시간 초과로 FAIL이며 그 기록은 보존한다. 단독 통과만으로 첫 실패 원인을 지연으로 확정하지 않음 |
| 독립 최종 리뷰·PR HEAD CI | 결과 미확정 | 각각 완료한 실제 결과와 정확한 SHA를 후속 기록 |

첫 전체 검사는 순수 Python 232개 PASS, Evennia/Django 988개에서 실패 111건·오류 4건을 보고했다. 이후 실제 공개 Action 경로로 Fixture를 이전하고 발견한 제품·표시 문제를 수정했다. 위 관련 재검증과 새 최종 전체 실행을 구분하며 초기 실패를 성공 결과로 바꾸어 기록하지 않는다. 코드 갱신 전에 중단한 검사는 NOT COMPLETED이며 완료 테스트 수에 더하지 않는다.

조회 비용은 같은 텍스트 Invocation 안에서만 Scope 레코드와 definition 필터의 참조 조회를 재사용한다. Gateway는 실행 직전 새 조회를 유지하고 명령 사이의 권한·대상 캐시는 추가하지 않는다. 교차 회귀의 무관한 월드 증가 검사에서는 다른 범위 80행을 추가해도 SQL 수 367→367, 무관한 대상 resolve 0을 확인했다. 이는 현재 fixture의 Query 범위 근거이며 운영 DB·PostgreSQL·다중 서버 성능 보장을 뜻하지 않는다.

PR B의 최종 테스트 개수·실행 SHA·독립 리뷰·원격 CI는 코드 확정 후 실제 결과로 기록한다. 현재 문서 정리를 테스트 PASS로 간주하지 않는다. 운영 DB migration/seed/복원은 미실행이며 운영 UUID·수량·상태를 무단 변환하지 않는다. 전체 38개 종합 검증·수동 브라우저/Windows IME·Full Smoke는 #67의 후속 범위이고 PostgreSQL·다중 서버는 미검증이다. M03/M04 완료와 PR B 제출만으로 M05/M06이나 Phase 2 전체 Migration Gate를 PASS 처리하지 않는다.

## PR C — M05 전리품 전환

기준은 PR B와 운영 정책 PR #72가 병합된 main `28117016e56f762fd2a91c99798971e738d3457d`다. 아래는 M05 구현 범위이며, PR C 병합 전 Final Closeout과 Phase 2 Migration Gate를 의미하지 않는다.

| 기존 입력·경로 | 신규 선택·실행 | 보존할 효과와 경계 |
| --- | --- | --- |
| Take.run → parse_loot → take_loot | 명시 Manifest의 Loot ContentPackage → DynamicActionCommand → 선언된 문법 Resolver → loot.take → Gateway → loot_service.pickup | 가져/집·후치 문법·고정 단축어·Session/Prompt를 같은 공개 진입점으로 이전 |
| 시체에서 모두/품목 가져 | 기본 Source 하나 먼저 선택 → 해당 Source Binding | 복수 시체만으로 모호성 거절하지 않으며 실패 Source를 바꾸지 않음 |
| 시체 N에서 / 시N | Room의 실제 Corpse B-1 번호 → 안정 Source ID | 2 삭제 후 3 유지·새 4·그룹 전체 소멸 후 1, 결번 대체 없음 |
| 모든 시체에서 ... 모두 | 여러 Corpse Source와 확정 Entry 집합 | 다중 Source와 단일 출처의 전체 수량 구분, 한 변경 단위의 지급 |
| 출처 없는 품목/칩/모두 가져 | Ground의 Room 공통 번호와 실제 owner Source | 동일 이름·번호로 새 객체가 생겨도 과거 UUID/ID 요청은 실패 |
| 칩 N / 20칩 / 칩 모두 | CurrencyLoot 안정 ID와 명시 금액/전체 인자 | 기존 CurrencyShare eligibility·가중 정수 분배·부분 회수·만료 후 caller 지급 |
| loot_controls의 peers.index / take_command 버튼 | 영속 SelectionNumber 표시와 Source/Subject typed Action | 권한 필터와 번호 발급 분리, 보호 내용 비공개, 문자열 재파싱 실행 제거 |

Corpse 번호 Scope는 Room/`world:corpse`, 내부 Item/Currency는 `corpse_loot:<Source ID>`, Ground는 `ground:<Room ID>`다. ItemEntity UUID와 CurrencyLoot ID는 표시 번호와 별개이며 Ground의 Room 공통 Scope에서도 실제 owner Source를 재검증한다. 플레이어별 권리·파티·보호 만료는 번호를 재발급하지 않는다.

새 어댑터는 LootClaim·Party 분배를 계산하지 않고 기존 `loot_service.lock_sources()`와 `pickup()`을 재사용한다. Object 소유자/Source → Item → Claim → Currency → Share → 번호 finalizer 순서와 최상위 `world_change()` 커밋 경계를 유지한다. 웹 선택의 Source·Entry·수량·권리·지분은 서버 서명 snapshot으로 고정하고 실행 시 현재 상태와 비교한다. 서명은 획득 권한이 아니며 현재 Session·시야·Scope·권리도 다시 확인한다.

Legacy 공개 Take 등록과 재노출을 제거하고 웹 회수를 Typed Action으로 바꾼다. 구형 blob 회귀·데이터 감사 호환은 운영 fallback과 구분한다. 버려/줘, 기존 M01~M04 Action, 전역 봐·말·도움·pz_dialogue·Engine/Exit 및 전투/생명주기는 유지한다. 운영 DB migration/seed/복원은 실행하지 않는다. 기존 번호 데이터가 필요한 배포 환경은 기존 명시적 백업·번호 seed·verify·복구 절차를 따른다.

Historical audit 모드의 구형 blob은 기존 권리 검사 후 품목·수량을 읽기 전용으로 표시한다. 실제 Entry ID가 없으므로 Action과 실행 명령을 제공하거나 배열 위치로 ID·정규 번호를 만들지 않는다. 운영 native runtime은 기존 migration 검증을 요구하며, 조회가 데이터 변환을 실행하지 않는다. 공개 회수 회귀는 Native ItemEntity/CurrencyLoot Fixture로 실행하고 구형 데이터의 무변경 조회 검사는 별도로 유지한다.

### PR C 검증 상태

검증 기준은 위 main SHA와 PR C 미커밋 Diff다. Windows Native Python 3.13.15, SQLite와 단일 Evennia Server의 격리 환경에서 실행했다. 과거 PR A/B 결과를 이번 성공 근거로 합산하지 않는다.

| 검사·실행 근거 | 실제 결과 | 범위와 제한 |
| --- | --- | --- |
| 신규 `test_loot_actions`와 `test_loot_action_invariants` 직접 회귀 | 개발 중 관련 검사 PASS | 가져/집 실제 공개 실행, Source·Entry B-1, A/B 권리·파티·0 지분·부분 회수, stale UUID/수량/owner, Unique·수령자 오류, Rollback과 커밋 후 알림을 검증. 개별 실행의 중복 개수를 합산하지 않음 |
| 보호 수량 추측 회귀 2개와 기존 Item 경계 2개 | 4개 PASS | 외부인의 작은/큰 요청이 같은 권한 거절, 권리자의 수량 부족은 유지. 수정 전 신규 2개 FAIL 재현 후 권리 검사를 수량 비교 앞으로 이동 |
| 후속 조회·Legacy 호환·일반 Provider 기본 정책 | 4개 PASS | 기본 시체 조회·명시 번호, 구형 blob 무변경 읽기와 Action 없음, 기존 구형 Currency read/decay, 비Loot 유일 대상 정책 유지 |
| `test_targets test_text test_distant_view` | 48개 중 43 PASS / 5 FAIL 후 해당 5개 PASS | 공개 회수 Fixture를 Native로 이전하고 B-1 결번 유지·정규 번호 표시·보호 정보 필터 기대를 반영. Historical 도메인 검사는 유지 |
| 경제·명령 Overhaul·개인 줄임말 직접 회귀 | 4개 PASS | Native 지급/버리기/회수의 지갑 총량 보존, 시/시2 실제 지급, D02 동명 집 저장·활성 Action 우선·Provider 소멸 후 개인 정의 복귀 |
| `scripts/dev.py check`, Node syntax, `git diff --check` | PASS | 코드·웹 문법 검사. 최종 JS 정적 수집 후 실제 Chromium 실행 |
| `scripts/dev.py smoke` / `prc-smoke-final.log` | PASS, 193.877초 | 실제 WebSocket·scheduler·일행 보상·보호/부분 화폐 회수·TTL·리스폰·보호 만료·상점·재로그인. 소유 프로세스/임시 환경 정리, 운영 DB hash/mtime/size 불변 |
| `.venv/Scripts/python.exe scripts/browser_e2e.py` | Chromium 12개 PASS, 오류 0, 146.880초 | TEST-66C-01 실제 UUID 버튼·동일 요청 재전송·삭제 후 새 Source에 stale 요청 거절·텍스트 동등 지급 포함. 브라우저/서버 프로세스·자격 증명 정리와 운영 DB 불변 확인 |
| 독립 Auditor | 지정 소스 감사 A, 잔여 P0/P1/P2 0 | 전체 권리/잠금/영속/실패 경계 감사와 후속 수량 비공개·Legacy 읽기/기본 선택의 별도 좁은 감사를 수행. 감사자는 테스트를 실행하지 않음 |
| 독립 Reviewer | 일반 검토 A, P0/P1/P2 0 | 고위험 감사와 구분해 공개 문법·Help·웹 Typed 버튼·운영 Manifest·Legacy 중복 제거와 유지 경로를 확인. 테스트 실행 없음 |
| `scripts/dev.py test --parallel 4` / `prc-full-frozen.log` | 규칙 232 PASS, 통합 1,043개 중 2 FAIL / ERROR 0 | 통합 893.319초. 실패는 아래 Legacy 표시 기대 2개이며 전체 실행을 PASS로 집계하지 않음. 격리 clone DB와 소유 프로세스 정리 확인 |
| 위 경제 테스트 2개 보완 후 직접 재검증 | 2개 PASS, 12.605초 | Legacy 읽기 전용 UI, Native CurrencyLoot/Source 실제 ID·B-1·8칩/1칩 표시·정규 명령과 칩 별칭 지급·삭제/잔량·번호 유지. 독립 Reviewer가 실제 보완 Diff 재확인, 새 지적 0 |
| 정확한 PR HEAD 필수 CI | 제출 후 확인 | `test`·`smoke`·`contracts`·`browser-e2e`의 정확한 SHA/실행 URL/결과는 PR Validation에 기록 |

첫 전체 검사는 순수 Python 232개 PASS, 통합 1,033개에서 6 FAIL/12 ERROR였다. 실행 도중 코드가 변경되어 최종 코드 근거로 사용하지 않는다. 구형 blob 조회의 안정 참조 오류와 기본 시체 조회 회귀를 수정하고, 공개 실행 Fixture·시각·B-1 기대를 보완한 뒤 위 직접 검사를 수행했다. 최초 실패를 성공 결과로 덮어쓰지 않는다.

동결 후 전체 검사에 남은 2개는 `test_currency_display_and_indexed_take_target_are_independent`의 구형 blob 임시 번호·실행 명령 기대와 `test_legacy_read_take_and_decay_and_web_use_common_assets`의 구형 실행 명령 기대였다. 구형 데이터의 읽기·Decay·historical 지급 검사는 유지하고, 실행 번호 검사는 실제 Native CurrencyLoot ID·Source·B-1·공개 지급으로 이전하여 위 2개 직접 재검증을 통과했다. 이 테스트 Fixture 보완만으로 제품 코드가 바뀌지 않으므로 로컬 전체 검사를 반복하지 않으며, 필수 CI의 전체 검사는 생략하지 않는다. 최종 CI는 PR Validation에서 확인한다.

운영 DB migration/seed/복원은 미실행이다. Full Smoke·전체 38개 종합/수동 검증·Windows OS IME·실제 모바일·PostgreSQL·다중 서버는 이번 PASS 범위에 포함하지 않는다. M06과 Phase 2 전체 Migration Gate는 미완료이며, PR C 병합 전 M05 Final Closeout을 선언하지 않는다.

### PR #73의 통합 Fixture 보완

최초 제출 HEAD `2bacd60c874ae6272e4ae2f9a96e62f3080c82f6`의 [CI 실행](https://github.com/wonmin82/primal-zone/actions/runs/39206621935)에서 기본 Chromium 12개와 E2E-01~06은 성공했으나 E2E-07이 실패했다. E2E-07/13의 기존 Fixture가 Legacy 플레이어와 blob을 공개 회수하는 경로를 요구했기 때문이다. 두 시나리오는 Native A/B의 실제 ItemEntity·CurrencyLoot 지급과 상위 Rollback으로 이전하고, E2E-12의 Legacy 데이터 읽기·동일 DB 재시작 보존 검사는 유지한다. 제품 코드·권한 예외·Legacy 실행 fallback은 추가하지 않는다.

E2E-07은 외부인 요청의 화폐·지분 불변, A/B의 정확한 6칩/14칩 지급과 잔여 권리 제거를 추가한다. 일행 해체는 권리를 정상 변환하므로 외부인 요청의 불변 기준은 해체 직후 상태다. 보완 중 해체 이전 상태와 비교해 발생한 검사 실패도 별도 보존하며, 독립 Reviewer가 이 경계를 재확인했다. 실행 중 파일이 바뀐 최초 로컬 시도는 고정 기준 재현이나 성공 근거로 집계하지 않는다.

고정된 보완 Diff에서 `.venv/Scripts/python.exe scripts/integration_e2e.py --scenario E2E-07 --scenario E2E-12 --scenario E2E-13`을 순차 실행해 3개 모두 PASS했다. 각각 123.639초·166.128초·91.519초이며 전체 381.649초다. 각 환경의 운영 DB 불변·서버/브라우저 프로세스 정리·자격 증명 제거를 확인했다. 통합 Runner 단위 검사 9개, Ruff·Node syntax·공백 검사도 PASS했다. 제품 코드가 동일하므로 로컬 전체 게임·Quick Smoke·기본 Chromium을 반복하지 않는다. 최초 HEAD의 `test`·`smoke`·`contracts` 성공과 `browser-e2e` 실패는 그대로 보존하며, 보완 커밋의 필수 네 Job 결과는 PR Validation에서 정확한 HEAD로 확인한다.

### PR #73의 비공개 Loot 오류 계약

보호된 Entry의 실제 이름·번호·Typed Reference와 존재하지 않는 Entry를 구분하는 공개 거절은 전리품의 존재를 노출할 수 있다. Loot Action은 이 대상 선택·권한 거절을 같은 공개 오류로 처리한다. 문법·Session·입력 모드 오류와 권리자의 수량 부족·전투·Unique 제한은 해당 오류를 유지한다.

이 계약은 번호 저장이나 지급 권한을 바꾸지 않는다. 관찰용 공통 레코드와 B-1 번호·Scope·ID는 유지하고, 기본 선택에서 보호된 첫 항목을 건너뛰어 다른 항목을 대신 지급하지 않는다. 실제 Gateway와 잠금 이후 Service의 LootClaim·CurrencyShare 검증도 유지한다. 수정 전 재현과 수정 후 회귀·독립 감사·정확한 최신 HEAD CI의 실행 결과는 PR Validation에 기록한다.


## PR D — M06 최종 통합과 운영 경로

PR D의 기준선은 PR C의 실제 Merge Commit `62635d985a2d27ccfb25d8ecd49374292aa24398`다. PR A [#70](https://github.com/wonmin82/primal-zone/pull/70), PR B [#71](https://github.com/wonmin82/primal-zone/pull/71), PR C [#73](https://github.com/wonmin82/primal-zone/pull/73)은 병합됐고, 기준 main의 [push CI](https://github.com/wonmin82/primal-zone/actions/runs/39397778596)는 필수 네 Job SUCCESS다. 이 사실은 위 개발 중 상태와 실패 기록을 소급하여 바꾸지 않는다. 아래는 현재 실행 매핑이며 PR D 자체의 리뷰·테스트·정확한 HEAD CI는 별도 기록한다.

모든 전환 동사의 텍스트 경로는 Dynamic Command → `dispatch_text()` → 안정 Invocation → Gateway `execute()`다. 웹은 표시 이름·배열 인덱스 대신 Action ID·Variant·실제 Typed Role Reference·인자를 `pz_action`으로 전달한다. Gateway가 현재 Session·Prompt·Provider·Scope·권한을 다시 검사하며 실패 후 Legacy Command로 돌아가지 않는다.

| 범위·공개 동사/별칭 | 이전 Handler | 현재 Action / Binding → Service | Provider·Role → Domain API | Help·Web·회귀 및 Cutover |
| --- | --- | --- | --- | --- |
| M01 문: 열어·닫아·잠궈·풀어 | `commands.doors.DoorCommand` | `door.open/close/lock/unlock` / `<Action>.binding` → `room_npc.door` | `world.door` 실제 Endpoint → `doors.operate_endpoint()` | Compiled Verb Help·Typed Endpoint, `test_doors`·`test_room_npc_actions`; 고정 Command 제거 |
| M01 시설: 조사·수리 | `world_actions.TargetAction`, `ActionObject.perform_action/act` | `world.<시설 종류>` / `<Action>.binding` → `room_npc.effect` | 실제 World Object Provider → `interactable_services`의 시설별 함수 | 현재 Binding 기반 표현, `test_regions`·`test_room_npc_actions`; 기존 효과 Handler는 도메인으로 이동 |
| M01 소각·소각 확정 | `incinerator.Burn` | `incinerator.burn` / `incinerator.burn.binding` → `room_npc.burn` | `world.incinerator` + Root Subject → `incinerator_service.incinerate_selected()` | 별도 확인 Variant·서버 토큰, `test_incinerator`·`test_credentials`; Legacy 공개 등록 제거 |
| M02 상점: 목록/품목/품/목/메뉴·사/구입·가치/얼마·팔아/팔/판 | `inventory.Shop/Buy/Value/Sell`, `Shopkeeper.act` | `shop.menu.<상점>`, `shop.buy.<품목>`, `shop.value.<품목>`, `shop.sell.<상점>` / 각 상점 Binding → `room_npc.effect/buy/value/sell` | `shop.<상점>` + 고정 품목 인자 또는 Root Subject → `interactable_services.shopkeeper()` → `shop_service` | 선언 Help·상점 전용 Typed Presenter, `test_shops`·`test_shop_entities`; 고정 Command 제거 |
| M02 의료: 회복·휴식/rest | `world_actions.Treat/Rest`, Doctor/Bed `act` | `medical.treat/rest` / `<Action>.binding` → `room_npc.effect` | `world.doctor/bed` + 회복 요청량 → `interactable_services.doctor/bed()` | 현재 Provider·기존 비용·전투 제한, `test_medical`·`test_prompt`; 고정 Command 제거 |
| M02 성장: 배워·배분·재분배/재훈련 | `skills.Learn/Allocate/Retrain`, 교관 `act/train` | `training.skill.<기술>`, `training.attribute.<특성>`, `training.reset.attributes/skills/all` / `<Action>.binding` → `room_npc.effect` | `skill.<기술>`·`attribute.<특성>`·`world.trainingmanager` → `interactable_services` → 기존 성장 규칙 | 선언된 담당·범위와 Typed 인자, `test_growth`·`test_growth_review`; 고정 Command 제거 |
| M02 정산: 교환/exchange·환율/rate | `commands.settlement`, `SettlementOfficer.act` | `settlement.exchange/all` → `room_npc.settle`, `settlement.rate` → `room_npc.effect`; `<Action>.binding` | `world.settlementofficer` + 안정 Inventory Source → `interactable_services.settlementofficer()`·기존 정산 규칙 | 집계 UUID/수량 snapshot, `test_settlement`·`test_economy`; 고정 Command 제거 |
| M03 소비: 사용·먹어/eat·마셔/drink | `combat.Use`, `items.Eat/Drink` | `item.<정의>.use/eat/drink` / `<Action>.binding` → `item_equipment.execute` | 실제 Root UUID Subject가 Provider → `skill_services.use_support()` 또는 `rules.eat_or_drink()` + `bind_consumption()` | 한 번 소비·예약 UUID, `test_item_equipment_actions`·`test_combat`; 고정 Command 제거 |
| M03 장비: 착용/입어/입·무장/wield·벗어/벗·해제/unwield·주무기·정보 | inventory/items 장비 Command | `item.<정의>.*`, `item.inside_information.<탄창>` / 정의별 Binding → `item_equipment.execute` | Root Provider·Subject 또는 명시 Inside Subject → `equipment_service`·`item_information` | 진단 Variant는 버튼 제외, `test_equipment`·`test_equipment_entities`; 고정 Command 제거 |
| M03 보관: 넣어/store·꺼내/retrieve | `items.Store/Retrieve`, `Container.act/perform_action` | `storage.store/retrieve` / `<Action>.<Provider>` → `storage.transfer` | `world.container/personal_locker` + CURRENT/STORAGE Subject → `item_transfer_native.transfer_selected()` | 공유 Verb·현재 부모 Scope, `test_storage_actions`·`test_item_entities`; 기존 보관 실행 제거 |
| M04 총기: 재장전·장전·채워·넣어·꺼내 | `commands.firearms`, items Command | `item_ops.reload/load/fill/inside_fill/ammo_insert/inside_ammo_insert/magazine_remove/ammo_remove.*/inside_ammo_remove.*` / `<Action>.<정의>` → `item_ops.execute` | Root Provider·Inside Subject·Root/Inventory Source → `firearm_service` | 명시 UUID·집계 snapshot, `test_firearm_lighting_actions`·`test_firearms`; 고정 Command 제거 |
| M04 광원: 켜·꺼·확인·넣어 | `items.LightOn/Off/Status` | `item_ops.light_on/light_off/light_status/power_insert` / `<Action>.<정의>` → `item_ops.execute` | Root 광원 Provider·전원 Source → `lighting_service` | 시간 투영과 추가 소비 분리, `test_firearm_lighting_actions`·`test_lighting`; 고정 Command 제거 |
| M05 전리품: 가져/집·시/시2~시5 | `inventory.Take.run` → `typeclasses.loot.take_loot` | `loot.take` / `loot.take.corpse/ground` → `loot.pickup` | Corpse/Ground Provider·Source + ItemEntity/Currency Subject → `loot_service.lock_sources/pickup()` | 영속 번호·권리 분리·LootUnavailable, `test_loot_actions`·`test_loot_action_invariants`; 공개 Take 제거·구형 blob 읽기만 유지 |
| M06 표현: 봐/본/보/백틱·말/say/작은따옴표·도움/도움말 | `character.Look/Help`, `social.Say` | 전역 Command 유지, 현재 Compiled Index/Binding을 읽는 표현으로 통합 | 실제 관찰 문맥·Provider → 순수 Presenter, 대화는 `npc_dialogue` | 객체 상세·Contextual Help·웹은 현재 행동과 일치; 이 전역 명령을 새 Action으로 중복 등록하지 않음 |

### 승인된 유지 경로와 Historical API

| 분류 | 경로 | 유지 이유와 실행 경계 |
| --- | --- | --- |
| 승인된 전역 | `Look`, `Say`, `Help` | 관찰·공개 발화·정적 도움말의 기존 사용자 계약. Action 효과를 재실행하는 fallback이 아님 |
| 승인된 대화 | `pz_dialogue` → `npc_dialogue.select_keyword()` | 수신자·Session·NPC·Intent에 결합된 대화 토큰, 기존 임무 Intent와 공개/개인 출력 경계 유지 |
| 승인된 비전환 | Engine/Exit·이동·Player/Party·전투·`버려`/`줘` | M01~M05 Action 전환 대상 밖. 기존 권한·경제·동시성 규칙 유지 |
| 비활성 과거 분기 | `commands.items.Drop.run()`의 `counterpart.perform_action()` | 과거 Store/Retrieve의 잔여 분기다. 현재 등록된 `Drop`은 `particle=None`으로 counterpart를 선택하지 않고, `Give`는 `isinstance(self, Give)`여서 해당 분기 조건이 거짓이다. 두 공개 클래스에서 도달하지 않으므로 활성 보관 실행 경로로 집계하지 않는다. `버려`/`줘` 자체의 transfer는 승인된 비전환 경로로 유지한다. 실제 조건과 등록을 독립 Reviewer가 확인했다 |
| 입력 확장 | 전역 단축어·개인 줄임말·묶음 | 실제 Command/Exit 우선순위와 단계별 최신 입력 검증 유지. 별도 Service나 Legacy fallback을 만들지 않음 |
| 표현용 호환 API | `ActionObject.web_actions()` 등 | 호출자가 필요한 현재 Typed Action 투영을 반환하는 표현 어댑터. 독립 비용·권리·지급 실행 없음 |
| Domain API | `interactable_services`, `equipment_service`, `item_transfer_native`, `firearm_service`, `lighting_service`, `loot_service` | 기존 정책과 원자적 게임 효과의 소유자. 선택된 안정 참조를 받으며 Legacy 공개 Command 재호출 없음 |
| Historical API·데이터 | 구형 blob·명시 audit 전용 `take_loot` 및 아이템 호환 함수 | 운영 fallback과 분리. 실제 호출자와 audit 설정으로 한정하며 구형 Loot 표시에는 가짜 ID·번호·실행 버튼을 만들지 않음 |

문자열 `act`·`web_actions`의 존재만으로 활성 중복이라고 판정하지 않는다. Registry/CmdSet 등록, 버튼 payload와 실제 호출자를 함께 확인하고 전환 동사는 신규 Gateway 한 곳으로 실행하는지를 검증한다.

### Migration Gate 기술 사전 검증

| Gate | 현재 판정 | 확보할 증거와 제한 |
| --- | --- | --- |
| G01 단일 Action 경로 | PASS — 기술 사전 검증 | 최종 직접 회귀 34개에서 실제 Command/Typed Web의 Service 효과 1회·거절 0회와 등록 단일 경로 확인. 최종 Quick과 기존 Chromium의 실제 게임 효과를 함께 확인 |
| G02 기존 행동 동등성 | PASS — 기술 사전 검증 | Help 별칭·6개 섹션·단축어·B-1 직접 회귀, 대화 25개와 Session/Help 추가 검사, 최종 Quick의 구매/판매·회복·재로그인·대화·Prompt 동작. 과거 실패와 의도된 개인 진행 비공개 보완은 아래에 별도 기록 |
| G03 핵심 영속·권리 | PASS — 기술 사전 검증 | PR A/B/C에서 병합 검증한 변경 없는 도메인·잠금·지급·Door 60초/통과 연장 계약을 재사용. M06의 Corpse B-1 직접 회귀와 대화 보상/Rollback 검사, 최종 Quick의 일행·Loot·보호 만료·TTL/리스폰·영속성으로 변경 영향을 검증. 로컬 전체 검사의 2개 Fixture 실패는 아래 보존하며 전체 성공으로 대체하지 않음 |
| G04 활성 Legacy·중복 UI/Help 0 | PASS — 기술 사전 검증 | 실제 Registry/CmdSet·Compiled Verb·웹 Typed payload와 신규 효과 1회 회귀를 교차 확인. 독립 Reviewer가 승인 유지 목록·Drop/Give 비활성 분기·Legacy fallback 부재를 확인. 전환 범위의 활성 중복 0건 |
| G05 Help/Web/문서 | PASS — 기술 사전 검증 | 현재 Provider/가용성·Help 6개 섹션·Typed 투영·조회 무부작용 직접 회귀, Session/Prompt·개인 진행 보호, Chromium 12개·Contracts 57개와 문서 12개 대조/상대 링크·공백 검사. 독립 Reviewer가 최종 문서·로그를 대조해 A로 판정했다. 최종 Source HEAD CI는 제출 Gate로 별도 대기 |
| G06 승인 병합/main CI | PENDING | PR A/B/C 병합과 main CI는 확인. PR D 사용자 승인 병합 및 정확한 병합 main CI는 아직 대기 |

이 표의 PASS는 아래 실제 직접 회귀·최종 Quick·브라우저·독립 소스 검토와 변경 없는 도메인의 기존 병합 검증을 근거로 한 기술적 사전 판정이다. 로컬 전체 검사 성공이나 PR D의 최종 승인·병합을 의미하지 않는다. 최종 Source HEAD·CI URL은 제출 후 별도로 기록한다. PR D의 구현·리뷰·Source HEAD CI가 성공해도 Phase 2 전체 Migration Gate는 G06 완료 전 최종 PASS가 아니다.

운영 DB Migration/Seed/복원·Full Smoke는 NOT RUN이다. 38개 종합 회귀·Windows 실제 한글 IME는 Phase 3, 실제 모바일 브라우저는 별도 검증이며 PostgreSQL/다중 서버는 미검증이다. 이번 작업은 SQLite·단일 Evennia Server의 격리 자원만 사용하고 Issue #67의 실행 범위를 시작하지 않는다.


### PR D 개발 검증과 실패·보완 기록

아래는 base `62635d985a2d27ccfb25d8ecd49374292aa24398`와 PR D 미커밋 Diff의 Windows Native / Python 3.13.15 / Evennia 6.1.0 / SQLite 단일 서버 검증이다. 중복 실행 건수를 합산하지 않으며 이후 제품 변경의 영향을 따로 적는다. 최종 Source HEAD CI는 이 로컬 기록과 별도다.

| 실제 검사·근거 | 결과 | 확인한 범위·후속 상태 |
| --- | --- | --- |
| `scripts/dev.py check`, `git diff --check` | PASS | 최종 통합 코드·공백 검사. Service 효과 검증을 대신하지 않음 |
| `scripts/dev.py test tests.test_action_cutover tests.test_targets tests.test_shortcut_help --parallel 1` | 최종 제품 34개 PASS, 75.828초 | Compiled Binding·현재 Provider·Help 별칭/6개 섹션·등록 단일 경로·Typed 투영·조회 무부작용·Corpse B-1·힌트 동사 필터. 이전 동일 범위 33개 PASS와 합산하지 않음 |
| `tests.test_action_cutover`의 G04 보강 시점 | 당시 6개 PASS, 16.966초 | Legacy 등록·Historical Provider 속성·실제 Command/Web Service 효과·중복 UI 점검. 이후 힌트 보완을 포함한 위 34개 검사로 직접 영향을 재검증 |
| `tests.test_npc_dialogue`의 공개 명령·웹 재현 | 수정 전 개인 진행 1개 테스트의 4개 subcase FAIL, 다른 Session·Prompt 2개 FAIL | Commander/Pathfinder 각각의 `execute_cmd()`·`pz_dialogue`에서 개인 Quest 진행 방송, 같은 캐릭터 다른 Session 토큰 재사용, Prompt 중 임무 수락을 실제 재현 |
| 위 대화 수정 후 모듈 검사 | 당시 25개 PASS, 270.551초 | 개인 진행은 요청자만 수신, 원래 질문과 공개 대사는 유지. Session 바인딩과 공통 입력 모드 검사, 권한·보상·Rollback 회귀 |
| `test_rendered_dialogue_tokens_are_separate_for_each_session_and_character` 직접 검사 | 1개 PASS, 12.970초 | 실제 Session별 독립 토큰·수신 대상, 다른 Session/캐릭터·로그아웃 거절, 원본 Session 성공 1회·재전송 중복 0회 |
| `test_say_help_describes_private_progress_and_session_prompt_boundaries` 직접 검사 | 1개 PASS, 12.064초 | `말`/`say` 실제 Help의 개인 진행 예외·Session/Prompt 보호 설명. 위 대화 보안 제품 코드와 동일 |
| `scripts/dev.py test --parallel 4` / `prd-full.log` | 규칙 232개 PASS, 통합 1,061개 중 1,059 PASS·2 FAIL·ERROR 0, 통합 927.185초 | 전체 실행은 FAIL로 보존. 실패는 훈련 가능한 예산 없는 교관 Fixture와 Native 실물이 없는 Container Fixture의 과거 행동 안내 기대 |
| 위 Fixture 보완 후 실패 2개와 분리한 Legacy 의미 1개 직접 검사 | 3개 PASS, 37.353초 | 실제 훈련 예산·Native UUID 조건에서 안내와 비가용 숨김을 검증. 기존 띄어쓰기 조회·무장 token 검사를 별도 보존. 제품 변경 없이 Fixture를 보완했으며 로컬 전체 PASS로 표현하지 않음 |
| 최초 `scripts/dev.py smoke` / `prd-smoke.log` | FAIL — 상점 구매 응답 타임아웃 | 이전 단계 성공과 별개로 전체 Quick은 실패. 실패 자원·로그 보존 |
| 원본 Smoke 판정·제한을 유지한 진단 1회 / `prd-smoke-diagnostic.log` | FAIL — 같은 상점 구매 타임아웃 | 구매 응답·잔액 변화 없이 종료. 서버 예외가 없다는 사실만으로 원인을 확정하지 않음. 운영 DB 불변과 소유 listener 정리 확인 |
| 방 힌트 성능 진단·직접 회귀 / `prd-presentation-hint-red/green.log` | 불필요한 구매 Presenter 호출 12회 RED → 0회 GREEN | 힌트의 정규 동사 Binding만 기존 권한·가용성·Presenter 검증으로 통과. 측정 Fixture에서 힌트 1.319초/1,846 queries → 0.0478초/73 queries, 상태 전송 3.3216초 → 1.7615초. 이는 타임아웃의 단독 원인을 확정한 결과가 아님 |
| 보완 후 표준 `.venv/Scripts/python.exe -u scripts/dev.py smoke` / `prd-smoke-final.log` | PASS, 종료 0, 172.971초 | 인증·Prompt·대화·일행·전투·Loot·TTL·리스폰·보호 만료·상점 가치/구매/판매/재구매·회복·재로그인 영속성 성공. 운영 DB 크기/mtime/SHA256 불변, 소유 프로세스 종료와 임시 환경 정리 확인 |
| `.venv/Scripts/python.exe scripts/browser_e2e.py` / `prd-browser.log` | Chromium 12개 PASS, 오류 0, 196.714초 | 힌트 성능 필터 직전 제품에서 실제 화면·Typed Web 경로 확인. 운영 DB 불변, 서버/브라우저 종료와 자격 증명 제거 확인. 웹 전체 투영은 후속 필터에서 유지하며 필터 자체는 위 34개 검사로 검증. 최신 HEAD CI는 별도 필요 |
| `npm run test:contracts` / `prd-contracts.log` | 57개 PASS | 기존 JavaScript·Typed 요청 계약. 웹 JavaScript 제품 변경 없음 |
| 독립 Auditor의 대화 권한·출력 감사 | A, 잔여 P0/P1/P2 0 | 개인 진행·Session·Prompt·출력·기존 보상/커밋 경계 검토. 감사자가 테스트를 실행한 것으로 집계하지 않음 |
| 독립 Reviewer의 전체 Diff·Fixture·Legacy·힌트 보완 검토 | A — Ready for Review, 잔여 P0/P1/P2 0 | 최종 문서·표준 Quick·직접 회귀·성능 비교와 기존 브라우저/Contracts 로그를 독립 대조했다. 파일·Git·DB 쓰기와 추가 테스트 실행 없음. 최종 Source HEAD CI는 별도 제출 Gate |
| 최종 PR Source HEAD 필수 CI | 제출 후 확인 대기 | `test`·`smoke`·`contracts`·`browser-e2e` 정확한 HEAD·실행 URL·결과 필요 |

전체 검사 실패 뒤 Assertion을 제거하거나 권한·지급 정책을 완화하지 않았다. 현재 가용 상태에 맞는 실제 Fixture를 제공하고 숨김 조건과 기존 Legacy 조회 의미를 함께 검증했다. 힌트 비용 보완은 게임 효과나 대상 선택을 바꾸지 않고 이미 필요했던 Binding 조회 범위를 요청한 동사로 좁힌다. 기존 Smoke 두 실패와 성능 측정 사실을 구분하며 최소 범위 보완 뒤 최종 표준 Smoke가 성공했다. 타임아웃의 단독 원인은 확정하지 않는다. Reviewer가 최종 문서·로그를 대조해 A로 판정했으며 정확한 Source HEAD CI는 별도 확인한다.
