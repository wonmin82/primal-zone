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
- [ ] PR 생성·latest HEAD CI 성공 (병합하지 않음)

실행 결과는 완료 시 [작업 상태](CODEX_TASK_STATE.md)에 기록한다. 원인 불명 Quick timeout이 반복되면 7A를 닫지 않는다.

## Phase 7B

Integration & Legacy Compatibility Validation. 실제 browser/입력/멀티플레이와 격리 Canonical Legacy Migration Corpus를 검증한다. 아래 항목은 7A에서 수행하지 않는다.

- [ ] desktop browser
- [ ] narrow/mobile browser
- [ ] actual OS Korean IME
- [ ] 1-player Boss
- [ ] 2-player Boss
- [ ] 3-player Boss
- [ ] 4-player Boss
- [ ] late join
- [ ] participant leave
- [ ] party lifecycle
- [ ] LootClaim E2E
- [ ] CurrencyLoot/Share E2E
- [ ] corpse → ground
- [ ] protection expiry
- [ ] Canonical Legacy Migration Corpus
- [ ] valid corpus
- [ ] warning corpus
- [ ] invalid corpus
- [ ] dry-run
- [ ] apply
- [ ] verify
- [ ] cutover
- [ ] post-cutover smoke
- [ ] idempotency/retry/error behavior

실제 production DB migration은 checklist에 넣지 않는다. 기존 자동 migration fixture 성공이 corpus closeout을 대신하지 않는다.

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
