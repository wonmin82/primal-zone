> [Issue #83의 확정 원문](https://github.com/wonmin82/primal-zone/issues/83#issuecomment-6396602387)
>
> 아키텍처 계약에는 [공통 원칙 P-01~P-12](architecture-principles.md)와 [통합 Actor 설계 v1.6 FINAL](actor-unification-design-v1.md)을 적용한다. 실행 순서와 Gate에는 이 문서 v1.0을 적용한다. 실제 구현 및 검증 상태는 [Phase 1 기록](actor-phase1-validation.md)에서 확인한다.

## 구현 기준 원문 2/2 — 2 Phase / 3 PR 구현 계획 v1.0

Issue #83의 **실행 계획 원문 고정본**입니다. Phase/PR 구성은 이 문서가 v1.6 설계 문서 내 과거의 3 Phase / 4 PR 초안을 대체합니다.

---

# Primal Zone — 통합 Actor v1.6 구현 실행 계획

**계획 버전:** v1.0<br>
**작성일:** 2026-10-25<br>
**대상:** Primal Zone 통합 Actor 아키텍처 v1.6<br>
**기준 브랜치:** `main`<br>
**확인된 기준 SHA:** `4288e0556aa6cd8cca8ab4bb3c4023d33d9608dc`<br>
**상위 규범:** `docs/architecture-principles.md`, P-01~P-12<br>
**구현 구성:** 2 Phase / 3 PR<br>
**병합 정책:** 사용자 승인 후 Merge Commit

---

## 1. 구현 전략

이번 작업은 다음 세 가지 결과를 순차적으로 확보한다.

1. **공통 계약 확립:** 새로운 구조를 수용할 수 있도록 Registry, Gateway, Actor, Combatant, Encounter의 최소 계약을 확정한다.
2. **기존 게임 완전 이전:** 기존 NPC·Enemy·Action·전투·대화·시설을 신규 구조로 이전하고 레거시 공식 실행 경로를 제거한다.
3. **신규 기능 및 최종 검증:** Exclusive Duel을 구현하고 아키텍처·기능·성능·복구 검증을 완료한다.

각 PR은 다음 조건을 충족해야 한다.

- 단일한 변경 목적을 가진다.
- 현재 `main`에서 실제 게임을 정상 실행할 수 있다.
- 동일 기능의 공식 실행 경로를 중복 활성화하지 않는다.
- 필요한 검증이 완료된 상태에서 독립 리뷰가 가능하다.
- 후속 PR 없이도 이미 병합한 기능이 손상되지 않는다.

## 2. 전체 구성

| Phase | PR | 핵심 목표 | 병합 완료 시 상태 |
|---|---|---|---|
| Phase 1 — 통합 아키텍처와 기존 기능 이전 | PR-A | 공통 계약·최소 Runtime 기반 | 기존 게임 정상 + 신규 계약 검증 |
| Phase 1 — 통합 아키텍처와 기존 기능 이전 | PR-B | NPC·Enemy 및 전체 기존 게임 기능 Cutover | 기존 게임의 신규 아키텍처 완전 이전 |
| Phase 2 — 확장 기능과 최종 마감 | PR-C | Exclusive Duel·확장 계약·Closeout | 통합 Actor v1.0 완료 |

의존 관계:

```text id="uxbnah"
최신 main / v1.6 설계 확정
              │
              ▼
PR-A: Architecture Foundation
              │
              ▼
PR-B: Full Native Cutover
              │
              ▼
PR-C: Duel & Final Closeout
              │
              ▼
최종 main CI 및 완료 감사
```

PR-A와 PR-B는 하나의 Phase에 속하지만 별도의 병합 Gate를 가진다.

**Phase 1 완료 시 PR-C가 없어도 기존 게임 전체를 정상 플레이할 수 있어야 한다.**

---

# Phase 1 — 통합 아키텍처 및 기존 게임 완전 이전

## 3. PR-A — Architecture Foundation

### 3.1 목적

기존 게임을 변경하지 않으면서 Actor 통합에 필요한 핵심 계약을 확보한다.

이 PR에서는 새로운 Actor 아키텍처를 실제 게임의 공식 실행 경로로 전면 전환하지 않는다.

**목표는 재사용 가능한 계약을 실제 코드와 작은 수직 테스트로 입증하는 것**이다.

### 3.2 작업 범위

| 영역 | 작업 |
|---|---|
| 설계 문서 | 통합 Actor v1.6을 저장소 기준 문서로 반영 |
| Actor | 단일 Typeclass, Definition, Spawn 계약 |
| WorldObject | 공통 시설 정의 및 기존 시설 모델과의 경계 |
| Capability | 경량 Descriptor, Sparse Composition |
| ActionBinding | 단일 Binding + 명시적 Global/Entity Source |
| Resolver | Global Scope Root 및 역할 검증 |
| Registry | 복수 Capability 및 정적 충돌 검사 |
| Gateway | READ_ONLY/STATE_CHANGE 및 복합 효과 계약 |
| ActionResult | COMPLETED/ACCEPTED 및 효과별 결과 표현 |
| Context | PlayerActionContext / DomainExecutionContext |
| Combatant | Explorer·Actor 최소 공통 인터페이스 |
| Encounter | Identity·Generation·종료·정산 계약 |
| Timer | 영속 복구 근거와 내부 이벤트 계약 |
| Delivery | 최소 공통 결과·수신자 계약 |
| World Format | 신규 Format의 검증·초기화 계약 |
| 테스트 | 경량 Fixture 및 핵심 불변식 테스트 |

### 3.3 구현 원칙

새 추상화를 추가할 때 실제 사용 사례로 필요성을 입증한다.

예를 들어 ActionBinding은 별도의 GlobalBinding과 EntityBinding 실행 엔진으로 분리하지 않는다.

Capability 역시 자체 Action Dispatcher를 보유하지 않는다.

Encounter는 공통 계약을 제공하지만 이 단계에서 모든 Encounter를 저장하는 범용 테이블을 생성하지 않는다.

### 3.4 최소 수직 검증

실제 운영 콘텐츠에 영향을 주지 않는 격리 Fixture를 작성한다.

**Fixture A — 복합 Actor**

- Dialogue Capability
- Combat Capability
- 두 Capability의 독립적인 활성 상태
- 기존 Action Registry 연결
- 정상·중복·충돌 선언 검증

**Fixture B — Global Action**

- Provider가 없는 Action
- 명시적 Scope Root
- 정상적인 Target Resolution
- 오래된 대상·권한 상실 거부

**Fixture C — 실행 계약**

- READ_ONLY와 STATE_CHANGE 구분
- 복합 효과의 독립적 결과
- 사용자 Session과 내부 Principal 구별
- 동기 완료·ACCEPTED 결과
- 원자성·Rollback

**Fixture D — Encounter**

- 안정 ID와 Generation
- 완료 결과의 중복 처리 방지
- 미지원 Encounter 실행 거부

### 3.5 기존 Runtime 보호

새 구조는 PR-A에서 기존 기능을 가로채지 않는다.

- 기존 Enemy/ NPC의 공식 실행 경로 유지
- 기존 전투·Quest·Item 규칙 유지
- 중복 사용자 CmdSet 미등록
- 기존 게임 데이터 자동 변환 금지
- 실험용 Actor는 테스트 DB에서 격리

이 단계에서 레거시 저장·실행 경로를 조사하고 제거 대상을 확정하지만, 다음 PR에서 필요한 책임까지 조기에 삭제하지 않는다.

### 3.6 PR-A 검증 Gate

**G1 — Foundation Gate**

다음 조건을 모두 만족해야 한다.

- 신규 공통 계약 검증 통과
- 기존 게임 회귀 통과
- 기존 공식 실행 경로 손상 없음
- Global/Entity Binding의 정적 검증 통과
- 복합 Action의 효과 경계 테스트 통과
- 경량 Actor의 Capability 조합 테스트 통과
- 불필요한 중복 Registry·Dispatcher 없음
- 독립 Reviewer 승인 가능한 상태
- 필수 PR CI 통과

**병합 완료 상태:** 기존 게임은 그대로 정상 동작하고, PR-B가 사용할 공통 계약이 검증되어 있다.

---

## 4. PR-B — Full Native Actor Cutover

### 4.1 목적

PR-A의 계약을 사용하여 **기존 게임 전체를 새로운 Actor 아키텍처로 이전**한다.

이 PR은 구현 규모가 가장 크므로 하나의 PR 안에서 여러 내부 체크포인트로 관리한다.

별도의 새로운 아키텍처 Phase는 만들지 않는다.

### 4.2 내부 구현 순서

| Checkpoint | 작업 | 주요 검증 |
|---|---|---|
| B1 | Actor·WorldObject·Spawn 실제 이전 | 실물 생성·위치·참조 |
| B2 | Shared Combat·Lifecycle·Reward | 전투·보상·타이머 |
| B3 | Dialogue·NPC Service·Quest | 발언·임무·거래 |
| B4 | Global Action·Movement·Observation·Web | 입력 동등성·권한·B-1 |
| B5 | World Format·Legacy 제거·최종 회귀 | Fresh-only·구조 감사 |

Checkpoint는 PR이 아니라 **구현 및 검증 단위**다.

각 단계가 검증되면 논리적인 Commit을 생성할 수 있다.

작은 수정마다 Push하여 CI를 반복 실행하지 않는다.

### 4.3 B1 — Actor 및 Spawn Cutover

- 기존 NPC·Enemy Definition을 `ACTORS`로 통합
- `ACTOR_SPAWNS` 적용
- 기존 NPC와 Enemy 실물을 Actor로 전환
- 시설을 WorldObject 또는 기존 독립 도메인 모델에 연결
- 현재 Spawn·Presentation·별칭·가시성 보존
- 기존 Enemy Level과 능력치 보존
- Typeclass 기반 NPC 구분 제거
- Bootstrap의 중복 생성·현재 상태 덮어쓰기 방지

기존 NPC와 Enemy가 서로 다른 공개 실행 경로로 남지 않도록 이후 체크포인트와 연결한다.

### 4.4 B2 — Shared Combat Cutover

- Explorer·Actor Combatant 연결
- 기존 Enemy 전투 규칙의 공통 Service 이전
- 참가자·기여도·위협도 유지
- Boss Scaling 유지
- Party·Claim·Loot 유지
- Corpse·Respawn 유지
- Combat Generation 및 정산 완료 근거 적용
- 서버 Combat Timer와 공통 Domain Service 연결
- Commit 이후 콜백 누락 복구
- 오래된 Timer와 중복 보상 거부
- 기존 Narration 유지

현재 기존 전투 결과와 비교하여 고정 RNG 기준선의 의미 있는 차이가 없어야 한다.

### 4.5 B3 — Dialogue 및 Service Cutover

- 일반 Speech Action
- NPC Dialogue Intent
- 개인 대화 문맥·토큰
- 상점·의료·훈련
- Quest 수락·진행·보고
- 자격증명·보상 지급
- 복합 Action 효과별 결과
- 공개 발언과 Quest 변경의 독립적 성공·실패
- 중복 요청과 보상 지급 방지

기존 NPC Dialogue Dispatcher를 제거하고 공통 Action Architecture로 이전한다.

### 4.6 B4 — Global Action·입력 및 웹 이전

- 이동·관찰·상태·도움말·일반 발언의 Gateway 연결
- 기존 Evennia 이동 및 안전 Hook 재사용
- Global/Entity 동사의 충돌 검사
- 기존 CmdSet의 중복 등록 제거
- Typed Reference의 `ACTOR` 전환
- B-1 번호 안정성 유지
- 웹 Action Payload와 Target 재검증
- Help·SURROUNDINGS·Action Presentation 정합성
- 오래된 웹 Reference 안전 거부
- 재접속·화면 갱신 검증

Gateway를 새로운 게임 규칙 엔진으로 만들지 않는다.

### 4.7 B5 — Native-only·Legacy 제거

실제 호출 관계와 현재 영속 모델을 감사하여 제거 대상을 확정한다.

- NPC·Enemy 중복 Typeclass
- 중복 정적 Definition
- 구형 NPC Dispatcher
- Enemy 전용 Combat Dispatcher
- 구형 Dialogue Dispatcher
- Legacy Item/Equipment/Loot Backend
- 불필요한 Legacy Mapping
- 공식 Runtime의 Legacy Fallback
- 과거 Cutover 코드의 지원·보존 범위 정리

기존 유지보수용 마이그레이션 도구처럼 현재 명시적 운영 계약이 있는 구성 요소는 삭제 전에 그 계약의 변경 범위를 검토한다.

삭제하더라도 기존 개발 DB를 자동으로 삭제하거나 변환하지 않는다.

World Format의 Fresh 판정과 지원하지 않는 DB의 안전한 차단을 검증한다.

### 4.8 PR-B 핵심 테스트

다음을 포함한다.

- 모든 기존 Enemy 전투
- 보스·Shared Combat·Party
- Corpse·Loot·보급칩
- NPC 서비스·상점·의료·훈련
- Quest 진행·보상
- Door·Movement·접근 권한
- Global Action
- Typed Reference·B-1
- 웹·텍스트 명령 동등성
- 서버 재시작·Timer 복구
- Fresh Bootstrap 반복 실행
- 주요 솔로 진행
- 구조적 Legacy 제거 감사

### 4.9 PR-B 완료 Gate

**G2 — Full Cutover Gate**

- 모든 기존 NPC·Enemy가 Actor Runtime으로 실행
- 모든 기존 사용자 게임 기능 정상
- 사용자 Action Gateway 및 내부 Domain Service 경계 정상
- 현재 게임 밸런스 유지
- 중복 보상·오래된 Timer·Rollback 회귀 통과
- 레거시 공식 실행 경로 제거
- Fresh-only World Format 정상
- 코드·도움말·웹·설계 문서 일치
- 주요 브라우저 검증 완료
- 독립 Reviewer의 해결되지 않은 P0/P1 없음
- 최종 PR HEAD의 필수 CI 통과

**병합 완료 상태:** 기존 원시구역 게임이 신규 Actor 아키텍처로 완전히 이전되어 있다.

Exclusive Duel은 아직 없어도 된다.

---

# Phase 2 — 확장 기능 및 최종 Closeout

## 5. PR-C — Exclusive Duel & Final Closeout

### 5.1 목적

Phase 1의 완전 이전 상태를 기반으로 Exclusive Duel을 구현한다.

새로운 복합 Actor와 향후 확장 계약을 검증하고 최종 릴리스 수준의 Closeout을 완료한다.

### 5.2 구현 범위

| 영역 | 작업 |
|---|---|
| Exclusive Duel | 참가·독점권·비살상 전투 |
| Duel Lifecycle | 승리·패배·기권·Timeout·Abort |
| 영속 상태 | 참가자·활동 시각·종료·Cooldown |
| 재시작 | 대련 복구·안전 종료·중복 실행 방지 |
| Reward/Quest | 대련 결과와 일반 처치 분리 |
| 복합 Actor | Dialogue+Combat+Service 구성 |
| Behavior | 기본 Policy 재사용 검증 |
| Narration | 수신자별 대련 결과 표현 |
| 미지원 기능 | Simulation/World Event 실행 거부 |
| 최종 정리 | 문서·도움말·테스트·구조 감사 |

### 5.3 확정된 Duel 정책

| 항목 | 정책 |
|---|---|
| Actor별 동시 대련 | 1건 |
| 참가자 | 명시적으로 허용된 참가자 |
| 최대 대련 | 10분 |
| 무행동 | 60초 |
| 연결 종료 유예 | 30초 |
| 재신청 제한 | 30초 |
| 일반 사망 패널티 | 없음 |
| Corpse·일반 Loot | 없음 |

대련 상태는 자신이 소유한 필드만 복원한다.

Actor 전체 Attribute Snapshot을 일괄 복원하지 않는다.

### 5.4 확장성 검증

다음 복합 Actor를 테스트한다.

**대련 교관**

- Dialogue
- Training
- Combat
- Exclusive Duel

**자율 경비로봇**

- Combat
- Interaction
- 상태별 Capability 활성화

두 Fixture는 기존 Capability와 Profile을 조합하는 방식으로 구현한다.

새로운 Actor ID를 처리하기 위한 중앙 Parser·Gateway 분기를 추가하지 않는다.

### 5.5 최종 성능 검증

현재 Main에서 확보한 기준선과 최종 Runtime을 비교한다.

- Action 처리 지연
- Resolver SQL 조회량
- `world_change()` 잠금 점유 시간
- Combat Tick 처리 비용
- Actor가 다수 존재하는 Room의 조회 비용
- Bootstrap 소요 비용
- 상태 갱신·Delivery 비용

측정 환경과 데이터를 동일하게 유지한다.

성능 저하가 발견되면 원인을 분석하고 필요한 수정 또는 승인된 트레이드오프를 기록한다.

단순히 PR 수를 줄이기 위해 성능 검증을 생략하지 않는다.

### 5.6 최종 Gate

**G3 — Release Closeout Gate**

- Exclusive Duel 전체 기능 완료
- 기존 기능 회귀 없음
- 재접속·재시작·무행동·중복 종료 검증
- 선언형 Actor 확장성 검증
- 불필요한 추상화·중복 상태 감사
- 성능 회귀 분석
- 최종 문서·도움말 정합성
- 실브라우저 검증 및 필요한 수동 IME 검증
- 해결되지 않은 P0/P1 없음
- 필수 PR CI 성공

병합 후 `main`의 필수 CI 성공까지 확인해야 최종 Closeout으로 판정한다.

---

# 6. 테스트 효율화

## 6.1 기본 원칙

테스트는 Commit 횟수가 아니라 실제 변경 영향에 따라 선택한다.

각 체크포인트마다 전체 테스트를 반복하지 않는다.

기존 `AGENTS.md`의 테스트 선택 정책을 우선한다.

| 시점 | 검사 |
|---|---|
| PR-A 내부 개발 | Registry·Gateway·Actor Fixture 중심 |
| PR-A 최종 | 직접 영향 + 공통 계약과 기존 게임 회귀 |
| PR-B B1~B4 | 해당 도메인 테스트 |
| PR-B B5 최종 | 전체 관련 게임 회귀·CI 수준 로컬 검사 |
| PR-C 내부 개발 | Duel·Recovery·Lifecycle 중심 |
| PR-C 최종 | 전체 관련 회귀 + 성능·브라우저 검증 |
| PR 병합 전 | 최종 PR HEAD의 필수 CI |
| PR 병합 후 | 해당 Merge Commit이 포함된 main CI |

## 6.2 비용을 줄이는 방법

- 고정 RNG와 가상 Clock Fixture 재사용
- DB가 필요 없는 규칙 테스트 우선
- 실패 시 직접 영향 테스트부터 재실행
- 동일한 전체 테스트의 불필요한 반복 방지
- 변경되지 않은 영역의 이전 검증 근거 재사용 가능성 평가
- 브라우저는 변경된 입력·화면 중심으로 확인
- 기존 CI 보호 규칙 유지

30초 이상 소요되는 검사와 CI 대기는 저장소의 비동기 감시 규칙을 따른다.

검증하지 않은 결과를 PASS로 보고하지 않는다.

---

# 7. PR 개수 최소화의 정당성

## 7.1 기존 4개 PR과의 비교

| 기존 | 신규 | 판단 근거 |
|---|---|---|
| PR-A Native Cleanup | PR-A Foundation에 감사·사전 정리 포함, 실제 제거는 PR-B Cutover에 통합 | 데이터 소유권 변경과 소비자 전환을 검증 가능한 순서로 묶음 |
| PR-B Architecture Foundation | 신규 PR-A | 독립적인 공통 계약 검증 Gate 유지 |
| PR-C Full Cutover | 신규 PR-B | 기존 게임 이전과 레거시 제거를 함께 완료 |
| PR-D Duel/Closeout | 신규 PR-C | 신규 기능을 기존 게임 전환과 분리 |

Native Cleanup을 별도 PR로 먼저 병합할 필요는 없다.

현재 게임이 아직 참조하는 레거시 기능은 소비자 전환과 함께 제거하는 편이 안전하다.

반대로 기반 계약과 대규모 Runtime 변경은 분리하는 것이 적절하다.

## 7.2 왜 2개 PR로 줄이지 않는가?

2개 PR로 구성한다면 다음 중 하나가 필요하다.

**대안 A:** Foundation + Full Cutover / Duel + Closeout

첫 번째 PR에 Registry, Gateway, Actor, Combat, Dialogue, 웹, Bootstrap 및 Legacy 제거가 전부 포함된다.

이는 코드의 결합도가 높고 독립 리뷰가 어려워진다.

**대안 B:** Foundation / Full Cutover + Duel + Closeout

두 번째 PR에 모든 기존 게임 이전과 새로운 대련 기능이 포함된다.

기존 기능 회귀와 신규 기능 결함을 구별하기 어렵다.

따라서 두 방식 모두 P-03, P-09, P-12의 관점에서 권장하지 않는다.

**3개 PR이 검증 가능한 구조적 경계를 유지하면서 줄일 수 있는 합리적인 최소치다.**

## 7.3 예외적인 추가 분할

PR-B의 범위가 실제 구현 중 독립 리뷰 불가능할 정도로 커지는 경우에만 분할을 검토한다.

다음 중 하나가 충족되면 추가 PR이 정당화된다.

- 하나의 변경이 다른 도메인의 검증 결과를 반복적으로 무효화
- 리뷰에서 중요한 데이터 소유권·전투·권한 변경을 독립적으로 검증하기 어려움
- 변경을 두 개의 정상 실행 가능한 수직 기능 단위로 분리할 수 있음
- 현재 상태에서 이중 공식 실행 경로 없이 안전한 중간 병합 가능

단순히 수정 파일 수나 코드 줄 수가 많다는 이유만으로 자동 분할하지 않는다.

반대로 PR 숫자를 3개로 고정하기 위해 안전한 병합 경계를 희생하지 않는다.

---

# 8. 주요 위험과 대응

| 위험 | 예상 영향 | 대응 |
|---|---|---|
| Actor 전환 중 기존 NPC 중복 | 잘못된 대상·중복 서비스 | 기능별 공식 실행 경로 단일화 |
| Action Gateway 범위 확대 | 명령 충돌·성능 회귀 | PR-A 정적 계약, PR-B 직접 영향 검증 |
| Global Action Provider 제거 | Scope·권한 오류 | 명시적 Scope Root·Runtime 재검증 |
| Speech와 Quest 결합 | 부분 보상·중복 처리 | 효과별 정책과 영속 정산 |
| Combat Generation 오류 | 중복 보상·잘못된 Tick | 안정 ID·완료 근거·원자성 |
| 타이머 등록 누락 | Respawn·전투 중단 | 영속 근거·재시작 정합화 |
| Legacy Cleanup | 필요한 Runtime 책임 삭제 | 실제 호출 감사 후 Cutover |
| Typed Reference 변경 | 오래된 웹 Action 오실행 | 이전 참조 안전 거부 |
| World Format 전환 | 기존 DB 손상·초기화 오류 | Fresh 검증·Fail Closed |
| 대련 상태 복원 | NPC 실제 상태 손실 | Duel 소유 필드만 복원 |
| PR-B 범위 과대 | 리뷰·통합 실패 | 내부 체크포인트 및 예외 분할 |

---

# 9. 작업 시작 전 준비

구현 착수 전에 다음 작업을 수행한다.

1. 최신 `origin/main`과 `AGENTS.md` 확인
2. 통합 Actor v1.6 기획안 저장소 반영
3. 현재 코드의 명령·대상·NPC·Enemy·영속 구조 인벤토리 확정
4. 기존 게임의 Fresh 실행 기준선 확보
5. P-01~P-12 관련 불변식과 기존 Issue #44 계약 교차 검증
6. 새로운 설계와 기존 유지보수 데이터 정책의 충돌 감사
7. 3개 PR의 예상 변경 파일 및 테스트 소유권 확인

준비 과정 자체를 별도 Phase나 PR로 만들지 않는다.

설계 문서와 직접 관련된 정리 내용은 PR-A에 포함한다.

---

# 10. 최종 완료 조건

다음이 모두 충족되어야 통합 Actor v1.0을 완료한 것으로 판단한다.

- [ ] 단일 Actor 및 Capability 구성
- [ ] 중복 Action 정의·Dispatcher 제거
- [ ] 기존 사용자 명령 및 게임 경험 보존
- [ ] 모든 사용자 게임 Action의 공식 Gateway 이전
- [ ] 공통 Combatant 및 Domain Service
- [ ] Shared Combat·보상·Quest 정상
- [ ] Encounter Generation·종료·정산 멱등성
- [ ] 타이머 영속 복구 및 중복 실행 방지
- [ ] Exclusive Duel
- [ ] B-1·Typed Reference 안전성
- [ ] Native-only Fresh Bootstrap
- [ ] 공식 Legacy 실행 경로 제거
- [ ] 선언형 콘텐츠 확장성 검증
- [ ] 성능 및 사용자 경험 회귀 검증
- [ ] 프로젝트 P-01~P-12 준수 감사
- [ ] 실제 소스·도움말·문서 일치
- [ ] 최종 PR 및 Main CI 성공

각 PR은 별도 사용자 승인 후 Merge Commit 방식으로 병합한다.

최종 Merge 후 Main CI 성공을 마지막 Gate로 사용한다.

---

# 최종 권장안

**Phase 1 — Unified Architecture & Full Cutover**

- PR-A: Architecture Foundation
- PR-B: Full Native Actor Cutover

**Phase 2 — Duel & Final Closeout**

- PR-C: Exclusive Duel / Regression / Closeout

이 구성은 Phase 수를 3개에서 2개로, PR 수를 4개에서 3개로 줄인다.

동시에 다음의 세 가지 중요한 품질 경계를 유지한다.

1. 공통 아키텍처 계약 검증
2. 기존 게임 전체 이전 완료
3. 신규 기능과 최종 품질 검증

**2 Phase / 3 PR을 통합 Actor v1.6의 권장 구현 계획으로 한다.**
