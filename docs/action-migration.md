# Action 기능 전환 진행표 (Issue #66)

규범은 [#44 v4.3](https://github.com/wonmin82/primal-zone/issues/44), 공통 API는 [Action 아키텍처](action-architecture.md)다. Phase 1 인수 기준은 `e93e6c70c88653c4695d065c3d82a15813379643`이다. 아래 표는 §10의 전체 범위를 추적하며, 아직 구현하지 않은 ID는 계획임을 구분한다. Phase 2 전체 Gate는 PR A~D의 승인 병합과 해당 main CI 전까지 미완료다.

| 기능·공개 동사/별칭 | 이전 공개 경로 | 신규 Action / Service / Provider·Role | Baseline | PR / 상태 |
| --- | --- | --- | --- | --- |
| 문 열어·닫아·잠궈·풀어 | commands/doors.DoorCommand → world.doors.operate | door.open/close/lock/unlock → room_npc.door → operate_endpoint / 실제 Exit 안정 참조 | test_doors, test_door_schema | A / 구현·로컬 검증 완료, 병합 대기 |
| 조사·수리 | commands/world_actions.TargetAction → ActionObject.perform_action/act | world.<시설 종류> → room_npc.effect → interactable_services / 필수 World Object Provider | test_command_overhaul, test_regions, test_phase6_runtime | A / 구현·로컬 검증 완료, 병합 대기 |
| 소각·소각 확정 | commands/incinerator.Burn → incinerator_service.incinerate | incinerator.burn normal/confirmed → room_npc.burn → incinerate_selected / 소각기 Provider + Root Item Subject | test_incinerator, test_credentials | A / 구현·로컬 검증 완료, 병합 대기 |
| 목록·품목·품·목·메뉴 | inventory.Shop → Shopkeeper.act | shop.menu.<상점> → room_npc.effect / Shop Provider | test_shops | A / 구현·로컬 검증 완료, 병합 대기 |
| 사·구입 | inventory.Buy → Shopkeeper.act | shop.buy.<품목> → room_npc.buy → shop_service.buy / 품목 제공 상인 + 선언 인자 | test_shops, test_shop_entities | A / 구현·로컬 검증 완료, 병합 대기 |
| 가치·얼마 | inventory.Value → Shopkeeper.act | shop.value.<품목> → room_npc.value / 취급 상인 + 품목 인자 | test_shops, test_shop_entities | A / 구현·로컬 검증 완료, 병합 대기 |
| 팔아·팔·판 | inventory.Sell → Shopkeeper.act | shop.sell.<상점> → room_npc.sell → shop_service.sell / 상인 + Root Item Subject + 별도 수량 | test_shops, test_shop_entities | A / 구현·로컬 검증 완료, 병합 대기 |
| 회복 | world_actions.Treat → Doctor.act | medical.treat → room_npc.effect → interactable_services.doctor / 의료 Provider + 요청 HP | test_medical | A / 구현·로컬 검증 완료, 병합 대기 |
| 휴식·rest | world_actions.Rest → Bed.act | medical.rest → room_npc.effect → interactable_services.bed / 침대 Provider | test_medical, test_prompt | A / 구현·로컬 검증 완료, 병합 대기 |
| 배워 | skills.Learn → GrowthTrainer.act/train | training.skill.<기술> → room_npc.effect / 담당 Skill Provider + 기술 인자 | test_growth, test_growth_review | A / 구현·로컬 검증 완료, 병합 대기 |
| 배분 | skills.Allocate → GrowthTrainer.act/train | training.attribute.<특성> → room_npc.effect / 담당 Attribute Provider + 양 | test_growth | A / 구현·로컬 검증 완료, 병합 대기 |
| 재분배·재훈련 | skills.Retrain → GrowthTrainer.act/train | training.reset.attributes/skills/all → room_npc.effect / 관리관 Provider | test_growth | A / 구현·로컬 검증 완료, 병합 대기 |
| 교환·exchange / 환율·rate | commands/settlement → SettlementOfficer.act | settlement.exchange/all/rate → room_npc.effect / 정산관 Provider | test_settlement | A / 구현·로컬 검증 완료, 병합 대기 |
| 임무·보급·Credential 연계 | NPC 대화 및 시설 act | 조사/수리 효과는 도메인으로 이전, 전역 말/pz_dialogue는 유지 | test_npc_dialogue, test_regions, test_integration | A / 구현·로컬 검증 완료, 병합 대기 |
| 사용·먹어·eat·마셔·drink | combat.Use / items.Eat/Drink | 계획: Item 자기 Provider → 공통 Gateway → 기존 소비·지원 서비스 | test_item_interactions, test_combat, test_item_entities | B / 미착수 |
| 착용·입어·입·무장·wield·벗어·벗·해제·unwield·주무기·정보 | inventory/items 장비 명령 | 계획: Root Item Subject=Provider, 장비 도메인 API | test_equipment, test_equipment_entities, test_item_interactions | B / 미착수 |
| 넣어·꺼내 / 보관 | items.Store/Retrieve → Container.act | 계획: Container Provider + CURRENT/STORAGE Item 역할 | test_item_entities, test_phase6_runtime | B / 미착수 |
| 재장전·장전·채워·넣어·꺼내 / 총기·탄창 | commands/firearms, items | 계획: Root/Inside 역할 → firearm_service | test_firearms, test_equipment_entities | B / 미착수 |
| 켜·꺼·확인·넣어 / 광원 | items.LightOn/Off/Status | 계획: Root Item/시설 Provider → lighting_service | test_lighting, test_lighting_entities | B / 미착수 |
| 가져·집·시·시2~시5·다중 Source·부분/화폐 | inventory.Take → typeclasses/loot.take_loot | 계획: Corpse/Ground Source + 안정 Loot/Currency ID → loot_service | test_loot_entities, test_currency_loot, test_parties, test_targets | C / 미착수 |
| 전역 봐·말·도움 / 객체 상세·Help·Web | character.Help/Look, social.Say, state/web_actions | 전역 진입점 유지, 객체 Action 표시를 Compiled Index로 통합. A는 소유 기능만 동기화 | test_web_state, test_web_prompt, test_text, test_npc_dialogue | D / 전체 교차 검사 미착수 |

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
- `perform_action`의 제품 호출자는 후속 PR B의 Container 넣어/꺼내뿐이다. 기존 `incinerate(value)` 같은 자료형 호환 API는 격리된 역사적 도메인 회귀에서만 사용하며 신규 실행 진입점이 호출하지 않는다.
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

플레이 DB의 크기·mtime·SHA256은 검사 전후 동일했다. 운영 migration/seed/복원은 실행하지 않았다. 수동 브라우저·Windows IME·Full Smoke·38개 종합 검증은 #67의 후속 범위이며 PostgreSQL/다중 서버는 미검증이다. M01/M02 로컬 검증 성공과 Phase 2 전체 Migration Gate를 구분한다. PR A 승인 병합 및 main CI 전에는 다음 PR을 시작하지 않는다.
