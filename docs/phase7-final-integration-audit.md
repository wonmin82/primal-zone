# Phase 7 Final Integration & Audit

## Scope

Phase 1~6 기능 구현은 PR #34에서 완료됐다. Phase 7은 현재 계약의 통합·호환성·밸런스·운영 마감이며 새 gameplay 기능 단계가 아니다. 현재 보존·전환할 실제 플레이 DB는 없다. 기존 개발 SQLite는 보호하며 실제 production migration/cutover/rollback rehearsal은 필수 작업이 아니다.

현재 계약은 [architecture](architecture.md), 확정 콘텐츠·경제는 [final-content](final-content.md), 구버전 호환은 [item-migration](item-migration.md)을 따른다. 작업 시점별 실행 이력은 [playtest](playtest.md)와 [CODEX_TASK_STATE](CODEX_TASK_STATE.md)에 보존한다.

## Supported V1 topology

| 항목 | 완료 대상으로 지원하는 계약 |
| --- | --- |
| Database | SQLite |
| Server | single Evennia server |
| Fresh install | 빈 DB에 schema 생성 → native runtime 초기화 → ItemEntity world bootstrap |
| Legacy DB | explicit maintenance migration tooling을 통한 호환 |
| PostgreSQL | [향후 infrastructure](postgresql-transition.md), Phase 7 exit criterion 아님 |

## Phase 7A

Baseline & Documentation Closeout. 현재 문서와 historical 기록을 분리하고 자동 기준선의 안정성을 확인한다. 문서 오류에 코드를 맞추거나 확정 balance를 tuning하지 않는다.

- [x] README current
- [x] architecture current
- [x] Phase-specific docs current/history separated
- [x] installation fresh/legacy split
- [x] migration role clarified
- [x] PostgreSQL roadmap documented
- [x] CODEX_TASK_STATE updated
- [x] stale-text audit complete
- [x] scripts/dev.py check
- [x] full local test
- [x] Quick smoke x3 (동일 최종 code의 연속 성공)
- [x] smoke-full (production timing)
- [x] 개발 DB fingerprint 불변
- [x] no unresolved P0/P1/P2
- [x] PR 생성·실행 코드 CI 성공 ([PR #35](https://github.com/wonmin82/primal-zone/pull/35), 병합·문서 마감 CI 상태는 PR Validation 참조)

실행 결과와 검증 snapshot SHA/run은 [작업 상태](CODEX_TASK_STATE.md)에 기록했다. 문서 마감 이후 최종 HEAD의 CI는 PR Validation에서 별도로 확인하며 이전 snapshot으로 대신하지 않는다. 최종 동일 code의 Full/Quick 연속3회가 성공했으며 이전 outsider 응답 timeout1건의 정확한 원인은 미확정 이력으로 보존한다. 원인 불명 Quick timeout이 반복되면 7A를 닫지 않는다.

기존 main의 Dependabot open4건(Twisted high1, Autobahn/DRF medium3)은 별도 보안 triage 관찰 사항이다. Runtime 노출/공격 재현은 미검증이며 이번 PR은 의존성을 변경하지 않는다. 이 사항과 reliability 이력을 포함한 7B 진입 판단은 READY FOR PHASE 7B WITH NOTES다.

PR #35 restart 리뷰의 coverage 공백은 before→stopped shutdown invariant와 stopped→after strict preservation으로 보강했다. 실제 ON/active UUID 광원을 전제로 정상 shutdown의 OFF/started_at=None/시간 정산·참조 제거와 일반 item/주무기 불변을 Full E2E에서 검사했다. 재실행 Full558.589초 성공이며 첫 기존 progression 전투 실패도 playtest에 보존한다. Production·Quick timing·fixture/balance는 변경하지 않았다. 수정 HEAD의 정확한 CI는 PR Validation을 따르며 notes 판정을 유지한다.

후속 CI의 기존 vocabulary 불변 검사가 자연회복 경계를 지나 실패해 해당 테스트의 관찰 시각만 고정했다. 실패 run37545750843과 후속 검증을 playtest/PR Validation에 구분한다. Production·Full 실행 코드와 수치는 그대로다.

최종 실행 코드 HEAD `2c23c1f377e41fb2ed0332e14942da8f487124a3`의 [CI37546292732](https://github.com/wonmin82/primal-zone/actions/runs/37546292732)는 check·pure203개·integration569개·Quick 모두 성공했다. 사용자가 문서 마감·병합·소스 브랜치 삭제를 요청했으며, 문서만 변경하는 마감 HEAD와 병합 main의 CI는 PR Validation에 별도로 기록한다. READY FOR PHASE 7B WITH NOTES를 유지하며 7B/7C 작업은 시작하지 않는다.

## Phase 7B

Integration & Legacy Compatibility Validation. 실제 browser/입력/멀티플레이와 격리 Canonical Legacy Migration Corpus를 검증한다. 아래 완료 표시는 Phase 7B에서 새로 실행한 결과이며 7A의 historical 결과를 변경하지 않는다.

PR #36 review finding의 P1 offline guard는 PID + CLI-local session으로 Windows cross-process 상태를 증명하지 못했다. 현재 launcher AMP structured status와 orphan process 검사로 보완한다. Actual Windows running apply/cutover 거절·DB snapshot 불변·정상 stop 뒤 acceptance는 첫69.828초 및 final bounded probe71.831초 성공이다. Invalid evidence는 초기 안전 실패와 최종 retry/cutover snapshot을 분리한다. Final guard/corpus13개·세 actual file corpus·check·pure204개/2.724초·integration582개/470.025초(outer486.823초)가 성공했다. 앞선 concurrent test runner의 clone cleanup 실패도 playtest에 보존한다. 수정 코드 HEAD `12fe5a63d6b04e0bae71004e84c7e01db7115f39`의 [CI37610891382](https://github.com/wonmin82/primal-zone/actions/runs/37610891382)도 check·pure204개·integration582개·Quick52.696초 성공이다. Actual/local/current-code exact CI 기준 미해결 P0/P1/P2 없이 **READY FOR PHASE 7C WITH NOTES**로 복구한다. 문서 마감 최종 HEAD의 exact CI/PR 상태는 PR Validation에서 별도로 확인하며 이전 코드 HEAD로 대신하지 않는다. 아래 actual OS IME와 기존 수행 결과는 완료 상태를 유지하며 재검증으로 표현하지 않는다.

- [x] desktop browser (실제 Chrome)
- [x] narrow/mobile browser (Chrome viewport 390×844, 실제 mobile device는 미실행)
- [x] actual OS Korean IME (Windows/Chrome 격리 화면에서 사용자 수동 정상 확인)
- [x] 1-player Boss
- [x] 2-player Boss
- [x] 3-player Boss
- [x] 4-player Boss
- [x] late join
- [x] participant leave
- [x] party lifecycle
- [x] LootClaim E2E
- [x] CurrencyLoot/Share E2E
- [x] corpse → ground
- [x] protection expiry
- [x] Canonical Legacy Migration Corpus
- [x] valid corpus
- [x] warning corpus
- [x] invalid corpus
- [x] dry-run
- [x] apply
- [x] verify
- [x] cutover
- [x] post-cutover smoke
- [x] idempotency/retry/error behavior
- [x] shared storage / Boss unique ownership boundary
- [x] Credential burn/reissue/access
- [x] firearm/mag/ammo / light actual interactions
- [x] cross-process offline guard / actual running apply·cutover rejection·DB 불변·normal stop acceptance
- [x] invalid corpus final evidence / runtime1·전체 final inspect equality

실제 production DB migration은 checklist에 넣지 않는다. 기존 자동 migration fixture 성공이 corpus closeout을 대신하지 않는다.

[Canonical corpus](phase7-legacy-migration-corpus.md)는 코드로 재생성하며 실제 file SQLite와 management CLI를 사용했다. 네 독립 계정의 실제 WebSocket 명령과 Chrome UI 관찰은 [playtest](playtest.md)의 시작 상태·실행·관찰 표를 따른다. OS IME는 사용자 확인이며 synthetic composition test를 실제 IME 근거로 사용하지 않았다. SQLite single-server에서의 순차 지급·권리 검증이고 PostgreSQL race 검증은 아니다.

리뷰 전 historical 실행에서 offline guard가 존재하지 않는 `SESSIONS.count()`를 호출해 apply/cutover를 막는 P1을 발견했다. 실제 API `get_sessions(include_unloggedin=True)`로 최소 수정하고 실패 재현→회귀→전체 자동 검증을 마쳤다. 그 외 확정 수치·migration ledger/cutover·runtime 구조는 변경하지 않았다. 최종 Full 및 exact-head CI 결과와 7C 진입 판단은 최신 작업 상태와 PR Validation에서 확인한다.

Full의 기존 탐사화 drop 뒤 구매 predicate가 수량1을 고정 기대한 P3 harness defect도 확인했다. 정상 보유2개와 잔액을 실패 DB에서 확인하고 Full 전용 기대를 구매 전 수량+1로 보정했다. Fail-first pure regression을 보존하며 production 및 Quick 경로는 바꾸지 않았다.

Lv6 밀림 Boss 전투의 반복 실패는 Full 전용 실제 사냥으로 Lv7에 도달한 뒤 상점·교관·침대 재준비를 거치는 흐름으로 보완했다. Restart 전 청소룡 처치 때문에 snapshot의 전투 전제가 사라진 경우에는 실제 trail 이동/갈퀴사냥룡 교전으로 전제를 유지했다. 타이머·수치·시작 준비금이나 shutdown/startup assertion을 바꾸지 않았다. 최종 Full628.071초에서 production30/45/120초·두 Boss/보고·실제 광원 OFF 정산·일반 item/주무기 보존·startup strict preservation·relogin·cleanup·개발 DB 불변이 성공했다. 실패 이력은 playtest에 남긴다.

리뷰 전 실행 코드의 check·pure204개/2.399초·integration574개/449.634초와 Quick84.846초·Full628.071초가 성공했다. Valid post-cutover 보강9개 시나리오58.696초에서도 고유 보상 폐기 거절·migrated loot·발전기 수리 뒤 cache의 재지급 없음·legacy item archive 불변이 성공했다. 당시 지원 topology에서 미해결 P0/P1/P2는 없었으며 코드 검증 기준 판정은 **READY FOR PHASE 7C WITH NOTES**다. Fixture reliability 이력과 기존 보안 triage, 사용자 확인 IME의 세부 로그 한계는 보존한다. [PR #36](https://github.com/wonmin82/primal-zone/pull/36)의 최종 문서 HEAD·exact CI·review 상태는 PR Validation에 별도로 기록한다. 아래 7C/Infrastructure는 미실행이다.

사용자가 PR #36 문서 마감·병합·소스 브랜치 삭제를 요청했다. 직전 최종 문서 HEAD `9ad163dc4d0502337c160c3000ec6e6dfb88b74e`의 [CI37612069275](https://github.com/wonmin82/primal-zone/actions/runs/37612069275)는 check·pure204개·integration582개·Quick47.980초 성공이며 exact SHA를 확인했다. 최신 main을 포함하고 review thread0개·MERGEABLE/CLEAN이다. 문서 마감 HEAD와 병합 main의 CI·실제 병합 결과는 [PR #36 Validation](https://github.com/wonmin82/primal-zone/pull/36)에 별도로 기록한다. 판정은 READY FOR PHASE 7C WITH NOTES를 유지하며 아래 Phase 7C/Infrastructure는 미실행이다.

## Phase 7C

Balance & Fresh Native Operational Closeout. 전체 simulation과 최종 운영 시작을 준비한다. 경비카빈 ammo/gross 약 44.6%는 이 단계에서 shots-to-kill·refill cadence·melee/firearm progression과 함께 검토한다. 7A에서는 수치를 변경하지 않는다.

- [ ] minimal/untrained build
- [ ] balanced build
- [ ] 2H offense
- [ ] 1H + shield
- [ ] firearm
- [ ] support/heal
- [ ] party build
- [ ] TTK
- [ ] incoming damage
- [ ] mental economy
- [ ] recovery
- [ ] ammo economy
- [ ] loot EV
- [ ] shop progression
- [ ] T1 → T2 pacing
- [ ] Boss solo balance
- [ ] Boss party balance
- [ ] guard-carbine ammo/gross review
- [ ] final balance changes (근거 있는 필요 변경만)
- [ ] regression
- [ ] fresh empty SQLite setup
- [ ] native runtime bootstrap
- [ ] fresh account
- [ ] starter ItemEntity
- [ ] complete gameplay smoke
- [ ] restart/relogin
- [ ] Item System V1 closeout

7A의 격리 smoke setup은 최종 운영 DB 생성이나 V1 운영 시작으로 표시하지 않는다.

## Deferred Infrastructure

다음은 Phase 7 exit criteria가 아니다. 목적·전환 조건·작업 순서는 [PostgreSQL roadmap](postgresql-transition.md)을 따른다.

- [ ] PostgreSQL dependency
- [ ] PostgreSQL installation
- [ ] PostgreSQL DB/role
- [ ] 전체 DB engine migration tool
- [ ] PostgreSQL integration suite
- [ ] contention test
- [ ] backup/restore
- [ ] operational cutover
- [ ] multi-server design
- [ ] multi-server validation

## Non-Phase-7 Roadmap

양방향 안전 거래, 외부 공개 배포, HTTPS/WSS reverse proxy, macOS 실제 실행 검증, argument/conditional shortcuts, loops/delay, Lv133 이후 성장, Master/상급 기술, 직업 시스템은 별도 roadmap이다. 미구현을 Phase 7 미완료로 취급하지 않는다.

## 발견 사항과 종료 기준

P0는 데이터 손상/기동 불가, P1은 핵심 runtime blocker, P2는 일반 재현 가능한 gameplay regression, P3는 낮은 위험 UX/test reliability다. 문서 오류는 Documentation, 통합·corpus는 Deferred 7B, balance/운영 시작은 Deferred 7C, PostgreSQL은 Infrastructure로 분류한다. P0/P1/P2가 남으면 7A 종료 불가다. Quick harness 수정이 있으면 수정 후 3회 연속 성공과 smoke-full 성공이 필요하다.

## Current / Historical / Roadmap 문서 audit

`git grep -n`으로 README/docs의 `후속 단계`, `Phase 6`, `legacy SSOT`, `아직.*않`, `미구현`, `적용하지 않았다`를 검색하고 문맥을 분류한다. 모든 미래 표현을 일괄 삭제하지 않는다.

| 분류 | 처리와 예 |
| --- | --- |
| Stale current statement | README 보급품 가격·회복 장비 없음·탄약 wiring 후속 표현, 본부 37개 → 실제 41개, architecture profile equipment/storage/light와 blob loot SSOT를 현재 native 계약으로 교체 |
| Valid historical statement | architecture 끝의 Phase 1~5 notes, equipment/lighting/loot/shop 당시 backend·catalog boundary를 Historical 섹션에 유지. phase3-validation/playtest/CODEX 이전 성공·실패·미실행 이력은 소급 수정하지 않음 |
| Actual future roadmap | 범용 timed consumable buff, 예약 시설 폐쇄, 안전 거래·공개 배포, 7B 실제 browser/IME/corpus, 7C balance/운영 시작, PostgreSQL/multi-server는 미완료 상태 유지 |

문서의 현재형에서 가격·catalog 숫자를 추가 복제하지 않고 [최종 콘텐츠](final-content.md)를 연결한다. Fresh initialization은 첫 서버 시작이며 schema를 만드는 setup 자체와 구분한다. 링크·heading anchor와 Markdown fence를 함께 검사한다.
