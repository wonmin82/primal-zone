# Phase 3 실제 검증 기록 (2026-10-06)

기준은 `b2ec5f5c0fc0e511a580d04891d655d7babc0cb3`에서 시작한 `codex/lighting-firearm`의 미커밋 구현이다. 최종 성공 이후 실행 코드 변경이 없으면 문서·Git 작업만으로 같은 검사를 반복하지 않는다. 각 실행 개수는 서로 합산하지 않는다.

## 최종 로컬 성공

| 실행 | 결과 |
| --- | --- |
| `.venv/Scripts/python.exe scripts/dev.py check` | Ruff 성공 |
| game에서 `../.venv/Scripts/python.exe -m unittest world.test_firearms world.test_lighting_state world.test_lighting world.test_item_definitions world.test_equipment_engine world.test_progression world.test_rules world.test_environment` | 103개 / 0.597초 성공 |
| `.venv/Scripts/python.exe scripts/dev.py test tests.test_lighting_entities tests.test_firearms tests.test_item_entities tests.test_equipment_entities tests.test_equipment tests.test_combat tests.test_environment tests.test_item_interactions tests.test_text tests.test_integration tests.test_recovery --parallel 2 --reverse` | 167개 / 69.968초, runner80.106초 성공 |
| CI 시간 의존 수정 후 `.venv/Scripts/python.exe scripts/dev.py test tests.test_environment tests.test_lighting_entities --parallel 2 --reverse` | 31개 / 21.013초, runner39.524초 성공. 앞선167개와 중복 합산하지 않는다. |
| `node --check game/web/static/webclient/js/primal.js` | 성공 |
| `git diff --check` | 성공 |

Lighting 12개와 Firearm 17개 method가 여러 행동 계약을 묶어 검사한다. Phase 1/2 UUID·sequence·split/merge·canonical 위치·parent/owner PROTECT·nested unique·lock·rollback·root/tree policy·merge_state·장비/주무기·자원/회복 회귀를 위 통합 실행에 포함한다. loaded firearm fixture의 child equip/unequip=false도 유지한다.

## 개발 중 실패와 재검증

- 최초 63개 통합 실행에서 UUID parent hook 입력과 알 수 없는 정의 default_state 처리 2곳이 실패했다. 최신 row 조회와 ValidationError 경계를 고쳐 이후 통합 성공에 포함했다.
- 신규 native 26개 실행에서 acquisition rollback 테스트의 mock이 자기 자신을 호출해 1곳 실패했다. 원본 함수를 patch 전에 보관한 뒤 재검증했다.
- 149개 실행에서 새 명령의 잘못된 도움말 category 2곳이 실패했다. 기존 `전투·회복` category로 정리했다.
- 순수103개 첫 실행은 registry category 기대값에 새 magazine/ammo가 빠져 1곳 실패했다. 정의 category 검사에 두 유형을 포함한 뒤 103개를 성공했다. 기존 world.test_lighting의 legacy 검사는 보존했다.
- 72개 실행에서 옛 JS cache query의 부정 검사가 새 query의 접두사까지 잘못 매칭해 1곳 실패했다. exact query 검사로 수정한 뒤 관련58개를 성공했다. 이는 마지막 reload/광원/owner lock 보완 이전의 중간 결과다.
- 167개 첫 실행은 새 광원 command test의 기대 메시지가 실제 전체 문구와 달라 1곳 실패했다. 기대값과 상태 검증을 고쳐 위 최종167개를 성공했다. 개발 중 check의 import·테스트 method 삽입 위치 오류도 최종 check에서 해결했다.

성공한 중간 개수를 최종167개/103개에 더하지 않는다. 과거 Phase 1/2 결과도 이번 실행 수로 계산하지 않는다.

## 최소 Web 확인

기존 Quick harness 기반의 별도 SQLite·fixture 계정·owned Portal/Server에서 정적 파일을 수집하고 computer-use로 확인했다. 일반 플레이 DB는 실행 전후 fingerprint가 같았으며 종료 후 owned process와 성공 임시 DB/로그를 정리했다. 이 실행은 browser fixture 확인이며 Quick/full smoke 성공으로 기록하지 않는다.

- `손전등 2` 버튼으로 두 번째만 ON, 직접 첫 손전등 명령으로 전환·옛 광원 OFF·독립 잔량을 확인했다.
- 재장전 버튼으로 25/30 확장 탄창을 삽입하고 기존20/20 표준 탄창이 inventory로 돌아오는 것을 확인했다. 삽입 탄창 채우기는 loose5를 소비해30/30이 됐다.
- 탄창 분리 버튼과 재장전, 재접속 후 잔탄/잔량 보존·logout 광원 OFF를 확인했다.
- Desktop1280×900과390×844의 새 stateful 행/버튼 줄바꿈을 확인했다. 390px에서 document scrollWidth375로 가로 overflow가 없었고 console warning/error는 없었다. 실제 OS IME 조합 입력은 미검증이다.
- CSS/JS cache query를 함께 갱신했다. 전체 browser matrix·다인 E2E를 실행하지 않았다.

## CI와 미실행

push/pull_request 자동 workflow의 최신 HEAD test/smoke는 PR Validation과 작업 상태에 run/SHA를 별도로 기록한다. 시작 main의 성공 run37315480927은 과거 baseline이며 새 HEAD 결과를 대신하지 않는다.

최초 [CI37332786078](https://github.com/wonmin82/primal-zone/actions/runs/37332786078)는 code HEAD `4ba72c875e288e9c385bbef5fa51e48280d3f02a`에서 순수185개 성공·통합434개 중 환경 조회 테스트1개 실패·Quick smoke35.032초 성공이었다. observation 시각은 고정했지만 command lifecycle의 회복 시계가 실제 10초 경계를 넘은 경우였다. 해당 조회 불변 테스트의 Explorer 시계를 저장된 recovery.updated_at으로 고정해 외부 시간 경과를 분리했고 profile 불변 단언은 유지했다. 수정 이후 관련31개를 성공했다. 새 HEAD CI는 별도 기록하며 이 실패 실행을 성공으로 표현하지 않는다.

수정 code/test HEAD `c7cfcf50d7e5e4c0c8a210adb02681f512182b7c`의 [CI37333508233](https://github.com/wonmin82/primal-zone/actions/runs/37333508233)는 test/smoke 모두 success다. 자동 순수185개/1.117초·통합434개/194.770초·Quick34.557초를 성공했다. 이후 마감은 문서만 변경하며 동일 코드의 로컬 테스트를 반복하지 않는다. 문서 마감 최종 HEAD의 CI는 [PR #31 Validation](https://github.com/wonmin82/primal-zone/pull/31)의 새 run/SHA로 별도 확인한다. 이 code HEAD 성공을 문서 HEAD CI로 대체하지 않는다.

요청한 단계별 전략에 따라 local full suite와 smoke-full은 미실행이다. Phase 7 전체 browser/multiplayer matrix, OS IME, 실제 PostgreSQL row-lock contention, multi-server concurrency, full-world migration과 balance simulation도 미실행이다. LootClaim/CurrencyLoot/Credential/shop V2/incinerator와 Phase 6 콘텐츠·cutover는 구현하지 않았다.

## PR #31 리뷰 수정 (2026-10-06)

이번 수정은 clean인 `codex/lighting-firearm`의 `17823459c81bbf866a7d308b29039b36ecddc97e`에서 시작했다. fetch 후 PR/local/remote HEAD가 같고 origin/main은 `b2ec5f5c0fc0e511a580d04891d655d7babc0cb3` 그대로였다. 시작 HEAD의 [CI37334226733](https://github.com/wonmin82/primal-zone/actions/runs/37334226733) test/smoke 성공은 과거 baseline이며 리뷰 수정 결과로 대신하지 않는다.

- P1: Store/Retrieve·LightOn/Off·Reload/LoadMagazine/FillMagazine에서 장비 변경 전용 recovery bypass를 제거했다. 실제 dispatcher의 일반 회복 정산을 사용하며 Phase 2 착탈/주무기 특별 lifecycle과 combat reload service의 기존 정산/기회 소비는 유지한다.
- P2: 날씨/환경은 ObservationContext.lights를 재사용해 native/legacy 광원 이름·켜짐·전원·잔량과 실제 시야를 같은 observed_at으로 표시한다. 상세를 위한 새 snapshot 조회가 없고 저장 상태도 바뀌지 않는다.
- P2: invalid/missing/None active-light 참조의 owned inventory orphan ON을 경과 정산/OFF/started_at=None으로 정규화한다. 유효 active의 추가 orphan도 OFF로 정리한다. 기존 owner/UUID lock 안에서 처리하고 foreign/storage 광원은 탐색·변경하지 않는다.
- firearm/reload/combat domain, ItemEntity API/model·transaction framework, 회복 공식·interval·저장 schema, normalization·콘텐츠·밸런스·migration은 변경하지 않았다.

| 이번 리뷰에서 실제 실행한 명령 | 결과 |
| --- | --- |
| `.venv/Scripts/python.exe scripts/dev.py check` | 최종 성공. 첫 개발 실행의 unused import/fixture 변수·import 순서 오류 4개는 수정했다. |
| game에서 `../.venv/Scripts/python.exe -m unittest world.test_lighting_state world.test_lighting world.test_firearms` | 18개 / 0.199초 성공 |
| `.venv/Scripts/python.exe scripts/dev.py test tests.test_environment tests.test_lighting_entities tests.test_firearms tests.test_item_interactions tests.test_recovery --parallel 2 --reverse` | 최종 86개 / 32.495초·runner41.471초 성공 |
| 실패 모듈 재검증: `.venv/Scripts/python.exe scripts/dev.py test tests.test_environment tests.test_lighting_entities --parallel 2 --reverse` | 36개 / 14.841초·runner23.752초 성공. 최종86개에 더하지 않는다. |
| `git diff --check` | 성공 |

첫86개 실행(36.578초·runner51.120초)은 새 Weather 기대 문구2곳과 orphan fixture1곳에서 실패했다. 실제 clear의 표시 이름은 `좋음`이며 canonical VISIBILITIES를 사용하도록 바로잡았다. 충전된 Entity의 오래된 입력 객체를 refresh한 뒤 orphan state를 구성했다. runtime 의미와 저장 검증을 완화하지 않았고 해당36개부터 재검증 후 위86개를 성공했다. 이전 실패/성공 기록과 개수를 합산하지 않는다.

새8개 method는 RECOVERY_INTERVAL을 실제로 넘긴 legacy 보관·전원/ON/OFF, native ON/OFF와 비전투 reload, native/legacy Weather의 단일 snapshot·시야·저장 불변, malformed/missing/None orphan과 유효 active/추가 orphan/storage 보호를 검사한다. 기존 foreign-owner 및 이동/삭제/rollback·combat reload·실제 발사/빈 총기 회귀도 유지한다.

최신 리뷰 HEAD의 Game checks/test/Quick smoke는 [PR #31 Review fixes 및 Validation](https://github.com/wonmin82/primal-zone/pull/31)에 정확한 HEAD SHA·run ID·결과를 별도로 기록한다. 이 링크의 최신 결과가 CI 근거이며 위 시작 HEAD 성공을 재사용하지 않는다. local full suite·smoke-full·전체 browser matrix는 이번 리뷰 요청에 따라 미실행이다. JS/CSS/template 변경이 없어 node·브라우저·정적 파일 수집도 반복하지 않았다. 실제 PostgreSQL 경쟁·multi-server·OS IME·Phase 6 migration·balance simulation 공백은 그대로다.
