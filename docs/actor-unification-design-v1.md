> 출처: [Issue #83 설계 원문](https://github.com/wonmin82/primal-zone/issues/83#issuecomment-6396578807), [확정 실행 계획](https://github.com/wonmin82/primal-zone/issues/83#issuecomment-6396602387).
> 설계 계약 27장과 부록 A~C를 보존하고 일정만 후속 계획에 맞췄다. 아래 원문의 기준 SHA·구현 미착수·PR #82 도입 중 표기는 설계 작성 당시의 역사적 맥락이다. 현재 상위 규범은 병합된 [architecture-principles.md](architecture-principles.md)이며 구현·검증 진행은 별도 기록을 따른다. 상위 원칙을 이 문서에서 재정의하지 않는다.

# Primal Zone — 통합 Actor 아키텍처 최종 기획안

**문서 버전:** v1.6 FINAL — Project Architecture Principles Aligned<br>
**개정일:** 2026-10-25<br>
**대상 저장소:** `wonmin82/primal-zone`<br>
**검토 기준 Main:** `3f070365a7ef4e570671a6d512407e078a3c6334`<br>
**기본 원칙 참조:** PR #82, HEAD `545ddb262b20436fc891c60a1ac5431475690eff`<br>
**권장 저장 경로:** `docs/actor-unification-design-v1.md`<br>
**상태:** 통합 설계 기준선 / 구현 미착수<br>
**대체 버전:** v1.0~v1.5

---

# 1. 목적과 범위

## 1.1 목표

Primal Zone의 기존 NPC와 Enemy를 하나의 Actor 아키텍처로 통합한다.

NPC와 Enemy의 영속 Typeclass, 콘텐츠 정의, 행동 제공, 전투, 대화, 서비스, 임무 연동, 대상 식별 및 생명주기를 공통 구조로 이전한다.

동시에 사용자 게임 행동의 Action Architecture를 확장하고, AI·타이머 등 서버 내부 실행도 같은 도메인 규칙을 사용하도록 정리한다.

이 작업은 기존 게임 기능을 보존하는 **아키텍처 전환**이다.

새로운 게임 콘텐츠를 대량으로 추가하거나 전투 밸런스를 다시 설계하는 작업이 아니다.

## 1.2 목표 상태

- NPC·Enemy의 단일 Actor Definition 및 Typeclass
- 선언형 Capability 조합
- 사용자 게임 행동의 단일 Action Gateway
- 서버 내부 이벤트와 사용자가 공유하는 Domain Service
- Explorer·Actor의 공통 Combatant 계약
- Shared·Exclusive Duel의 공통 Encounter 의미 계약
- 기존 게임 규칙·보상·사용자 명령 보존
- Native-only 영속 저장
- Fresh-only World Format
- Legacy 실행 경로 제거
- 새로운 Actor의 콘텐츠 중심 확장

## 1.3 기존 게임 보존

다음 항목은 별도 승인 없이 변경하지 않는다.

- 현재 한국어 사용자 명령의 의미
- 사냥·성장·장비 수집의 게임 흐름
- 주요 임무·보스의 솔로 진행 가능성
- Shared Combat 및 Party 규칙
- 공격 간격과 전투 계산
- 기술·정신력·자원 소비
- XP·보급칩·전리품 밸런스
- Corpse·Respawn·Recovery
- NPC 대화와 임무 지급
- B-1 대상 선택 정책
- 웹 버튼과 직접 명령의 동등한 동작

신규 Exclusive Duel은 별도의 신규 기능으로 취급한다.

---

# 2. 프로젝트 기본 아키텍처 원칙과의 관계

## 2.1 상위 규범

이 문서는 프로젝트 공통 아키텍처 원칙 P-01~P-12를 재정의하지 않는다.

공통 원칙의 규범적 소유자는 다음 문서다.

`docs/architecture-principles.md`

해당 문서는 PR #82에서 도입 중이며, 본 기획안은 검토된 최신 원칙을 기준으로 작성한다.

구현 착수 시 PR #82의 병합 여부와 실제 `main`의 규범 버전을 다시 확인한다.

## 2.2 적용 원칙

| 원칙 | 통합 Actor에서의 적용 |
|---|---|
| P-01 Player-First Design | 기존 플레이 경험·솔로 진행·밸런스 보존 |
| P-02 Server Authority & Security | 사용자·AI·Timer의 권한과 신뢰 경계 검증 |
| P-03 Correctness & Consistency | 원자성·멱등성·복합 효과·재시작 복구 |
| P-04 Single Source of Truth | Actor·Capability·Action·Item·Encounter의 사실별 소유권 |
| P-05 Clear Responsibility & Dependency | 입력·실행 조정·도메인·영속화·표현 분리 |
| P-06 Single Authoritative Domain Execution | 동일 게임 효과의 공식 규칙 통합 |
| P-07 Explicit & Verifiable Contracts | Binding·Target·Action·Result·Encounter 계약 |
| P-08 Declarative & Composable Content | 기존 기능의 Actor별 선언형 조합 |
| P-09 Minimal Sufficient Design | 검증 가능한 최소 충분 추상화·영속 상태 |
| P-10 Stable Identity & Controlled Evolution | Actor Reference·B-1·웹 계약의 관리된 전환 |
| P-11 Recoverability & Operability | Timer·Encounter·Bootstrap 재시작 복구 |
| P-12 Evidence-Driven Quality | 기능·성능·장애·확장성의 실제 검증 |

## 2.3 설계 판단 기준

다음 순서로 검토한다.

1. 서버 권위·권한·데이터 안전·게임 효과의 정확성
2. 기존 게임 경험 및 승인된 공개 계약
3. 단일 SSOT·명시적 경계·안정 정체성
4. 장애 복구 가능성과 검증 가능성
5. 단순성·확장성·성능·유지보수 비용

단순성을 위해 안전성이나 필수 영속 상태를 제거하지 않는다.

확장성을 위해 현재 필요 없는 범용 실행 엔진을 미리 만들지 않는다.

---

# 3. 핵심 아키텍처

## 3.1 논리 구조

```text id="latt88"
사용자 게임 입력
  ├─ Text
  ├─ Web
  └─ Dialogue / Movement / Combat
                │
                ▼
           Input Adapter
                │
                ▼
       Action Registry / Resolver
                │
                ▼
        Unified Action Gateway
        - Session / Principal
        - Target / Permission
        - Invocation / Result
        - Effect Boundary
                │
                ▼
           Domain Services ◀──── Internal Events
        - Combat                    AI
        - Dialogue                  Combat Tick
        - Quest                     Recovery
        - Movement                  Respawn
        - Item / Loot               Lifecycle
        - Interaction
                │
                ▼
          Entity / Policy
        - Actor / Explorer
        - WorldObject
        - ItemEntity
        - Combatant
        - Encounter
        - Behavior / Narration
                │
                ▼
       Native Persistence / Evennia
```

## 3.2 실행의 단일성

**하나의 게임 효과는 하나의 권위 있는 도메인 규칙으로 확정한다.**

이는 모든 호출이 동일 Gateway를 반드시 사용해야 한다는 의미가 아니다.

- 사용자 게임 입력은 Action Gateway를 사용한다.
- 서버 AI·Timer는 신뢰된 내부 진입점을 사용한다.
- 실제 게임 효과는 동일 Domain Service가 소유한다.
- 각 진입점에서 공통 불변식을 우회할 수 없다.

## 3.3 책임 소유권

| 계층 | 책임 |
|---|---|
| Input Adapter | 입력 형식과 인증 문맥 구성 |
| Action Registry | Action·Syntax·Role·Binding·Service 선언 |
| Resolver | 현재 Scope에서 안정적인 대상 식별 |
| Gateway | 사용자 요청 인증·검증·효과 실행 조정 |
| Domain Service | 실제 게임 효과·상태 전이 |
| Entity Runtime | 실물 정체성·영속 상태 |
| Capability Descriptor | 기능 구성·설정·참조 검증 |
| Combatant | 전투 참가자 상태 접근 |
| Encounter | 참가·전투 회차·종료 결과 |
| Domain Policy | 계산·행동·보상·생명주기 규칙 |
| Delivery | 확정된 결과의 수신자별 전달 |

이 표는 논리적 책임 구분이며 구성 요소마다 별도 프레임워크를 생성하라는 요구가 아니다.

---

# 4. 엔티티 구조

## 4.1 주요 엔티티

| 엔티티 | 정적 SSOT | 영속 실물 |
|---|---|---|
| NPC·Enemy | `ACTORS` | `Actor` |
| 고정 시설 | `WORLD_OBJECTS` | `WorldObject` |
| 아이템·장비 | `ITEMS` | `ItemEntity` |

다음 독립 도메인은 유지한다.

- Explorer
- Room / Exit
- Door / DoorInstallation
- Corpse / DroppedLoot
- Party
- LootClaim
- CurrencyLoot / CurrencyLootShare

이들을 하나의 범용 Entity Typeclass로 통합하지 않는다.

## 4.2 Actor

Actor는 비플레이어 개체의 공통 영속 Typeclass다.

NPC와 Enemy는 별도 Typeclass로 구분하지 않는다.

Actor는 다음을 담당한다.

- 정체성
- 현재 위치
- Spawn 연결
- 기본 영속 상태
- Capability 구성 조회
- 상태·가시성·생명주기 연결

전투 계산, 임무 변경, 상점 거래를 Actor Typeclass의 거대한 조건문으로 구현하지 않는다.

## 4.3 WorldObject

WorldObject는 시설의 관찰·선택·상호작용을 제공한다.

실제 시설 상태는 해당 Domain Model 또는 Service가 소유한다.

기존 Door, Storage 등 독립적인 도메인 모델을 불필요하게 다시 구현하지 않는다.

## 4.4 Explorer

기존 Explorer Typeclass 및 플레이어 영속 모델을 유지한다.

Actor와 공통 Combatant 계약을 공유하지만 같은 Typeclass로 통합하지 않는다.

---

# 5. Actor Definition 및 Spawn

## 5.1 정적 정의

모든 NPC·Enemy 정의는 `ACTORS`로 통합한다.

기존 `ENEMIES` 및 NPC별 중복 콘텐츠 정의는 최종 제거한다.

| 필드 | 정책 |
|---|---|
| Actor ID | 안정된 정적 ID |
| `name` | 필수 |
| `aliases` | 선택 |
| `level` | 1 이상의 정수 |
| `classification` | 필수 |
| `subtype` | 선택 |
| `faction` | 선택 |
| `presentation` | 필수 |
| `capabilities` | 필요한 기능만 선언 |
| `profiles` | 필요한 설정만 선언 |
| `defaults` | 필요한 초기 상태 |

## 5.2 Classification

허용 값은 다음과 같다.

- `human`
- `creature`
- `machine`
- `hybrid`
- `other`

Classification은 정체성 분류다.

전투 밸런스와 행동 정책을 자동으로 결정하지 않는다.

## 5.3 기존 Enemy Level

| Actor ID | 표시 이름 | Level |
|---|---|---:|
| `scavenger` | 어린청소룡 | 1 |
| `hunter` | 갈퀴사냥룡 | 2 |
| `sentinel` | 고장난경비기 | 3 |
| `alpha` | 능선의우두머리 | 4 |
| `dartclaw` | 날쌘발톱룡 | 5 |
| `shellback` | 철갑등짐승 | 6 |
| `stalker` | 그늘추적룡 | 7 |
| `jungle_apex` | 밀림의포식자 | 10 |

기존 일반 비전투 NPC는 초기 Level 1을 적용한다.

레벨 추가로 HP·공격력·보상 수치를 자동 변경하지 않는다.

## 5.4 Spawn

다음 식별자를 구별한다.

| 식별자 | 의미 |
|---|---|
| Actor ID | 개체 종류 |
| Spawn ID | 콘텐츠 배치 |
| Object PK | 실제 영속 객체 |
| Encounter ID | 실제 전투 회차 |
| Selection Number | 사용자 선택 번호 |

`ACTOR_SPAWNS`는 정적 배치 정의를 소유한다.

하나의 Actor Definition이 여러 Spawn을 가질 수 있다.

동일 Spawn의 반복 Bootstrap은 새 객체를 중복 생성하지 않는다.

---

# 6. Capability와 선언형 콘텐츠

## 6.1 Sparse Composition

Actor는 필요한 Capability만 가진다.

| 유형 | 구성 예시 |
|---|---|
| 일반 NPC | Presentation + Dialogue |
| 상점 NPC | Presentation + Dialogue + Shop |
| 일반 Enemy | Presentation + Combat + Behavior |
| Boss | Presentation + Combat + Behavior + Narration |
| 대련 교관 | Presentation + Dialogue + Combat + Encounter |
| 경비로봇 | Presentation + Combat + Interaction + Behavior |

비전투 Actor에 빈 Combat Profile이나 전투 타이머를 강제하지 않는다.

## 6.2 Capability Descriptor

Descriptor의 책임은 다음으로 제한한다.

1. Capability의 안정 ID
2. 필수 Profile 및 설정 Schema
3. 기존 Action/Binding에 대한 참조·유효성 검증

자체 Action Executor, 별도 Scheduler, 중복 Service Handler를 갖지 않는다.

## 6.3 단일 선언 소유권

| 정보 | SSOT |
|---|---|
| Actor의 보유 Capability | Actor Definition |
| Capability 설정 Schema | Capability Descriptor |
| 실제 Profile 값 | Actor 콘텐츠 Profile |
| Action 문법·Role | Action Registry |
| Action과 Service 연결 | ActionBinding |
| Service Handler | ServiceDefinition |
| 현재 제공되는 행동 | Compiled Index + 현재 Entity 상태 |
| 실제 실행 가능성 | Gateway·Domain 검증 |

**Capability Descriptor와 ActionBinding이 동일한 Service 연결을 각각 독립적으로 정의하지 않는다.**

Capability Descriptor는 필요한 경우 기존 Action/Binding의 ID를 참조한다.

Actor별로 같은 Binding을 복제하지 않는다.

## 6.4 선언형 확장의 완료 기준

이미 구현된 기능을 새 Actor에 추가할 때 원칙적으로 다음만 변경한다.

- Actor Definition
- Spawn Definition
- 필요한 Profile

기존 기능을 조합했다는 이유로 공통 Parser·Resolver·Gateway·Service에 해당 Actor ID를 추가하는 경우는 실패로 판단한다.

다만 새로운 기능 종류·문법·도메인 규칙을 추가하는 경우에는 관련 공통 계층의 확장이 허용된다.

---

# 7. 단일 Action Registry 및 Binding

## 7.1 기존 Architecture 유지

기존 구성 요소를 재사용한다.

- ContentPackage
- PackageManifest
- VerbDefinition
- SyntaxVariant
- RoleDefinition
- ActionDefinition
- ActionBinding
- ServiceDefinition
- ProviderDefinition
- CompiledActionIndex

두 번째 Registry나 별도의 Actor Action Executor를 만들지 않는다.

## 7.2 단일 ActionBinding

ActionBinding은 하나의 자료형을 유지한다.

Binding Source는 명시적으로 구분한다.

```text id="me3mng"
ActionBinding
  ├─ id
  ├─ action_id
  ├─ service_id
  ├─ source
  │   ├─ Global
  │   └─ Entity(provider_definition)
  └─ config
```

Source는 식별된 타입 계약이다.

단순한 Null 값만으로 정상 Global Binding과 잘못된 Entity Binding을 구별하지 않는다.

## 7.3 Global Source

Global Source는 실물 Provider가 없는 사용자 행동을 제공한다.

예시:

- 일반 발언
- 상태 확인
- 도움말
- 플레이어 자기 행동

Global Action도 Registered / Provided / Executable을 구분한다.

항상 실행 가능하다는 의미가 아니다.

## 7.4 명시적 Scope Root

기존 RoleDefinition은 Provider를 Scope의 기본 출처로 사용하는 경우가 있다.

Global Action에서 존재하지 않는 Provider를 암묵적으로 참조하지 않도록 Scope Root를 명시한다.

| Scope Root | 의미 |
|---|---|
| `caller` | 현재 인증된 Explorer |
| `current_room` | 현재 Explorer의 위치 |
| `role:<name>` | 먼저 확정된 다른 Role |
| Entity Provider | 실제 제공 개체의 Scope |

Scope의 실제 표현은 기존 Schema를 최소한으로 확장해 구현한다.

임의 문자열을 무제한 허용하지 않는다.

## 7.5 정적 검증

Registry는 다음을 검증한다.

- Global Source의 유효한 Scope Root
- Entity Source의 Provider 참조
- Provider가 없는 Action의 필수 역할
- Source와 Target Role의 일관성
- Scope 참조 순환
- 등록된 Capability·Service 의존성
- Global/Entity 간 동사·문법 충돌
- 동일 Actor의 여러 Capability 충돌
- 보호된 명령 이름
- 필수 인자·Target의 유효성

명령어 우선순위나 등록 순서로 모호성을 해결하지 않는다.

## 7.6 제공·실행 검증

텍스트와 웹은 동일 Compiled Index를 사용한다.

실행 시점에는 다음을 다시 검사한다.

- Session 제어권
- 현재 위치
- 대상 실물의 존재
- Scope
- 가시성
- Capability 활성 상태
- 소유권·권한
- 현재 행동 가능 여부

사전 표시된 버튼은 권한의 증거가 아니다.

명시적으로 선택된 대상이 무효라면 다른 대상으로 자동 대체하지 않는다.

---

# 8. 사용자 Action Gateway

## 8.1 책임

Gateway는 사용자 게임 Action의 단일 신뢰 경계다.

게임 규칙 자체를 소유하지 않는다.

담당 기능:

- Session 인증
- Input Mode
- Action/Binding 확정
- Typed Target Resolution
- 권한·Scope 검증
- 실행 정책 결정
- Domain Effect 조정
- 결과 확정
- Delivery 후처리

## 8.2 상태 처리 정책

| 정책 | 의미 |
|---|---|
| `READ_ONLY` | 해당 효과에서 영속 게임 상태 변경 금지 |
| `STATE_CHANGE` | 해당 효과에서 영속 변경 가능 |

이 정책은 **효과 실행 경계**에 적용된다.

하나의 사용자 입력이 여러 효과를 포함하는 경우 각 효과의 정책을 명시적으로 구분할 수 있다.

READ_ONLY 효과의 내부에서 임의로 상태 변경 작업을 수행하지 않는다.

## 8.3 완료 의미

| 결과 | 의미 |
|---|---|
| `COMPLETED` | 요청된 효과가 현재 호출에서 확정 |
| `ACCEPTED` | 후속 실행을 위한 예약·참여가 현재 호출에서 확정 |

기존 SUCCESS / REFUSED / ERROR / CONFIRMATION 상태는 유지한다.

완료 의미는 성공·실패 Status와 별개다.

예를 들어 공격 명령은 SUCCESS + ACCEPTED이고, 실제 피해 확정은 이후 Combat Result가 나타낸다.

Gateway에 범용 Deferred Scheduler를 만들지 않는다.

## 8.4 복합 Action의 실행 계약

하나의 사용자 입력이 복수의 도메인 효과를 발생시킬 수 있다.

이 경우 다음을 반드시 명시한다.

1. 각 효과의 이름과 실행 정책
2. 효과 간 의존성
3. 원자적으로 함께 확정해야 하는 효과
4. 서로 독립적으로 성공·실패할 수 있는 효과
5. 전체 사용자 요청과 개별 효과의 결과 표현
6. 재전송 시 중복 실행 방지 기준

이것은 새 범용 Workflow Engine을 만들라는 의미가 아니다.

복합 행동이 필요한 도메인 서비스의 실행 계약으로 표현한다.

## 8.5 복합 실행 정책 결정

실행 가능한 효과 조합은 Registry 또는 등록된 Service 계약에서 허용돼야 한다.

효과를 실행하면서 READ_ONLY 경계에서 암묵적으로 STATE_CHANGE로 승격하지 않는다.

사전 단계에서 허용된 효과와 정책을 결정하고, 실제 실행 경계에서 현재 조건을 재검증한다.

조건이 변경되었으면 해당 효과를 거부하거나 안전하게 재판정한다.

재판정 때문에 미선언 상태 변경이 발생해서는 안 된다.

## 8.6 단일 실행 경계

Gateway가 사용자 행동을 수락한 뒤 같은 효과를 기존 Command Handler에서 다시 실행하지 않는다.

Domain Service를 직접 사용하는 Evennia Hook은 중복 명령 Handler가 아니라 엔진의 안전 경계여야 한다.

---

# 9. Speech·Dialogue 복합 실행

## 9.1 필수 구분

일반 공개 발언과 NPC의 임무·서비스 효과는 별도 도메인 효과다.

하나의 `말` 입력이 다음을 포함할 수 있다.

```text id="u8648f"
사용자 발언
    │
    ├─ Speech Effect
    │   └─ 공개 메시지
    │
    └─ Dialogue Effect
        ├─ NPC 응답
        └─ 임무·서비스 상태 변경
```

## 9.2 실행 정책

| 효과 | 처리 정책 | 확정 단위 |
|---|---|---|
| 일반 Speech | READ_ONLY | 공개 발언 수락·전달 |
| 정보성 Dialogue | READ_ONLY | NPC 안내 |
| 임무·거래 Dialogue | STATE_CHANGE | 도메인 상태 전이·보상 |
| NPC 상태 변경 결과 안내 | 전달 이벤트 | 성공 Commit 이후 |

하나의 사용자 명령을 처리하더라도 각 효과의 상태 처리 계약은 독립적이다.

## 9.3 정상 처리 흐름

1. 인증·문자열·입력 모드를 검증한다.
2. 공개 발언을 수락할 수 있는지 검사한다.
3. Speech Effect를 확정한다.
4. 현재 Actor와 Dialogue Intent를 판정한다.
5. 관련 Capability 및 현재 권한을 검증한다.
6. 상태 변경 Intent는 명시적인 STATE_CHANGE 경계에서 실행한다.
7. Commit 후 NPC 응답·보상 결과를 전달한다.

대상 Intent가 거절되더라도 정상 수락된 일반 공개 발언을 취소하지 않는다.

공개 발언이 거절됐다면 이를 우회해 NPC 효과를 실행하지 않는다.

## 9.4 결과 계약

복합 입력에는 요청 전체의 처리 결과와 각 효과의 결과를 구분할 수 있어야 한다.

예시:

```text id="k60f0x"
요청: "대장에게 임무 완료를 보고한다"

Speech:
  ACCEPTED / DELIVERED-BEST-EFFORT

Dialogue Intent:
  COMPLETED / SUCCESS

Quest:
  COMMITTED / REWARD GRANTED
```

임무 조건이 충족되지 않았다면 다음과 같이 구분한다.

```text id="67tp66"
Speech:
  ACCEPTED

Dialogue Intent:
  REFUSED

Quest:
  NO CHANGE
```

상위 ActionResult의 SUCCESS가 모든 하위 효과의 성공을 암묵적으로 의미해서는 안 된다.

기존 ResultStatus를 무리하게 늘리기보다는 복합 효과의 결과 정보로 개별 효과 상태를 명시한다.

## 9.5 원자성

하나의 Dialogue Intent에서 다음 효과는 원자적으로 확정한다.

- 임무 진행 상태 변경
- 보상 지급
- ItemEntity·보급칩 변경
- 보상 지급 완료 표시

부분 지급을 허용하지 않는다.

Speech 공개 전달과 Quest 보상은 하나의 DB 트랜잭션으로 묶지 않는다.

이미 정상 전달된 공개 발언이 후속 Quest 거절로 Rollback되지 않는다.

## 9.6 중복 요청

동일 사용자 요청은 안정된 요청 식별자로 가능한 범위에서 재전송을 판별한다.

단, 일반 채팅의 네트워크 Exactly-Once Delivery는 보장하지 않는다.

영속 상태 변경 효과는 해당 Quest·Reward 도메인의 확정 상태와 안정 Operation ID를 사용해 중복 지급을 거부한다.

메모리의 Request ID 기록이 사라져도 이미 완료된 보상을 다시 지급하지 않아야 한다.

## 9.7 기존 대화 기능 보존

- 명시 NPC 및 화제 선택
- 180초 대화 문맥
- 후속 질문
- 개인별 활성 화제
- 확인 토큰의 Session 결합
- 토큰 만료·재사용 거부
- 위치·시야·전투 조건
- 공개 대사와 개인 안내 분리

토큰은 권한의 유일한 근거가 아니다.

실제 상태 변경 직전에 최신 조건을 확인한다.

---

# 10. PlayerActionContext 및 DomainExecutionContext

## 10.1 PlayerActionContext

사용자 인증 및 입력에 관한 데이터다.

- Explorer
- Account / Session
- Input Origin
- ActionInvocation
- Request ID
- Confirmation Token
- 요청 시각

Session의 제어권은 실행 직전에도 재검증한다.

## 10.2 DomainExecutionContext

서버 내부 실행과 사용자 실행이 공유하는 최소 도메인 문맥이다.

| 항목 | 의미 |
|---|---|
| Origin | Player, AI, Timer, Lifecycle |
| Principal | 해당 실행을 허용하는 권한의 근거 |
| Actor | 실제 게임 행동 주체 |
| Target | 효과 대상 |
| Operation ID | 안정된 실행 식별자 |
| Domain Scope | Encounter, Room 등 실행 범위 |
| Clock | 검증에 사용할 기준 시각 |

실제 도메인에 필요하지 않은 정보를 전부 강제하지 않는다.

## 10.3 Principal의 신뢰 계약

Origin이 Timer라는 이유만으로 임의의 도메인 권한을 부여하지 않는다.

신뢰된 서버 내부 Principal은 인증된 서버 실행 경계에서만 생성한다.

사용자 입력이나 웹 Payload는 Principal을 직접 지정할 수 없다.

예를 들어 Combat Timer는 해당 Encounter의 예정된 공격을 수행할 수 있지만 다른 Actor의 보상을 임의 지급할 수 없다.

## 10.4 내부 실행의 최소 검증

서버 내부 이벤트도 다음을 검증한다.

- 현재 대상의 존재·동일성
- Operation ID와 현재 Generation
- 현재 도메인 상태
- 허용된 실행 원인
- 실제 효과 범위
- 중복 실행 여부
- 원자적 상태 변경 조건

서버 내부 실행은 Session 검증을 요구하지 않지만 도메인 불변식은 우회하지 않는다.

---

# 11. 최소 Combatant 계약

## 11.1 목적

Explorer와 Actor의 영속 구조를 유지하며 공통 Combat Service를 사용할 수 있도록 한다.

Combatant는 별도 영속 Typeclass가 아니다.

## 11.2 최소 계약

- Identity
- Snapshot
- Participation Validation
- Effect Application

실제 Python 자료형과 메서드명은 구현에서 결정할 수 있다.

## 11.3 Combatant의 책임 제한

Combatant Adapter는 다음을 소유하지 않는다.

- 공격 계산식
- 무기·탄창·기술 소비 정책
- 참가자 전체 관리
- 기여도·위협도 규칙
- 사망·리스폰
- 보상·전리품
- 임무 변경

이들은 공통 Combat Runtime과 관련 Domain Service가 소유한다.

## 11.4 변경의 원자성

Combatant Adapter는 독자적으로 Commit하지 않는다.

피해·회복·효과 적용은 공통 상태 변경 경계에서 수행한다.

참가자 상태와 Encounter 결과가 서로 다른 기준으로 확정되지 않도록 한다.

---

# 12. Combat Runtime

## 12.1 이전 대상

기존 Enemy 전용 전투 실행 구조를 다음 공통 서비스로 이전한다.

- 전투 시작
- 참가자 검증
- 공격·피격
- 기술 및 자원 소비
- 자동 Tick
- 기여도·위협도
- Boss Scaling
- 전투 종료
- Reward / Loot
- Recovery / Respawn

## 12.2 공식 전투 실행 흐름

1. 현재 Encounter·Generation 검증
2. 참가자·대상·Principal 검증
3. 필요한 도메인 잠금 확보
4. Combatant Snapshot 확보
5. 행동 시각·자원·기술 유효성 확인
6. 기존 순수 전투 규칙으로 결과 계산
7. 자원·피해·상태 변경 적용
8. 기여도·위협도 갱신
9. 필요한 Lifecycle·Reward·Quest 변경 확정
10. Combat Result 생성
11. Commit
12. Narration·Delivery 및 Timer 후처리

이 단계는 논리적 순서다.

단계마다 별도 Service 객체나 트랜잭션을 만들지 않는다.

## 12.3 기존 전투 규칙

| 항목 | 결정 |
|---|---|
| 기본 공격 간격 | 2.5초 유지 |
| HP·공격·방어 | 기존 값 |
| 기술·정신력 | 기존 규칙 |
| Boss Scaling | 기존 공식 |
| Claim | 기존 보호 규칙 |
| Party | 기존 참여·분배 |
| XP·칩 | 기존 값 |
| Corpse·Loot | 기존 생성·보호 |
| Respawn | 기존 시간 |
| 새로운 명중·회피 확률 | 도입하지 않음 |

## 12.4 결과의 소유권

Combat Service는 확정된 Combat Result를 생성한다.

Narration은 해당 결과를 표현한다.

표시 메시지에서 피해량·상태·보상 결과를 다시 계산하지 않는다.

---

# 13. Encounter 및 영속 정산

## 13.1 공통 Encounter 계약

Encounter는 실제 전투의 참가·정체성·종료를 나타낸다.

| 계약 | 의미 |
|---|---|
| Identity | 전투 회차의 안정 식별 |
| Policy | 참가·독점 방식 |
| Participants | 참가자·권한 |
| State | 현재 진행 상태 |
| Final Result | 단일 종료 결과 |
| Settlement | 보상 정산 완료 여부를 판정하는 근거 |

모든 Encounter에 동일한 영속 테이블을 강제하지 않는다.

## 13.2 Encounter 저장 전략

| 정책 | 실제 지원 | 저장 전략 |
|---|---|---|
| Shared | v1.0 | Actor Combat Runtime |
| Exclusive Duel | v1.0 | 영속 Duel State |
| Simulation | 스키마·검증만 | 미래 결정 |
| World Event | 스키마·검증만 | 미래 결정 |

미지원 정책은 실행하지 않고 명시적으로 거부한다.

Shared Encounter로 자동 대체하지 않는다.

## 13.3 Shared Encounter Identity

동일 Actor가 연속해서 전투하는 경우 다른 전투 회차로 구분한다.

안정 ID는 다음 정보를 기반으로 할 수 있다.

```text id="lz5nn6"
Actor Spawn / Object Identity
        +
Persistent Combat Generation
```

Generation은 재시작 후에도 유지되는 단조 증가 값이다.

전투 시작·종료·재생성 과정에서 회차 식별이 모호해지지 않아야 한다.

Object PK 재생성 등으로 충돌 가능성이 있다면 Spawn/World Format의 정체성을 포함하거나 동등한 안정 식별 방식을 사용한다.

## 13.4 종료와 보상 원자성

Shared Encounter의 정상 사망 종료에서 다음을 하나의 논리적 정산 단위로 처리한다.

- 종료 가능 여부 확인
- 해당 Generation의 종료 확정
- 기여도·참가자 정산
- XP·보급칩 반영
- Quest 진행 반영
- Corpse·Loot 생성
- 부활 예정 상태·시각 기록
- 정산 완료 판정 근거 확정

이 과정에서 필수 영속 효과가 실패하면 전체 관련 변경을 Rollback한다.

종료 완료 메시지는 Commit 이후 전달한다.

## 13.5 멱등성 계약

같은 Encounter 종료 처리가 다시 호출되면 다음을 보장한다.

1. 현재 Generation이 같은지 확인한다.
2. 이미 완료된 종료인지 확인한다.
3. 정산 완료된 보상을 다시 지급하지 않는다.
4. Corpse를 중복 생성하지 않는다.
5. Quest 이벤트를 중복 적용하지 않는다.
6. 이전 Generation의 Timer가 새 Generation에 영향을 주지 않는다.

Generation ID만으로 지급 완료 여부가 증명된다고 가정하지 않는다.

기존 상태 모델만으로 구별할 수 없다면 종료·정산의 최소 영속 완료 근거를 추가한다.

별도 범용 Event Store는 도입하지 않는다.

## 13.6 도메인별 SSOT

| 상태 | 권위 있는 소유자 |
|---|---|
| Actor 실제 HP | Actor Runtime |
| 전투 참가·기여도·위협도 | Combat Runtime |
| Encounter 종료·정산 | 해당 Encounter Runtime |
| Quest 진행 | Explorer Quest State |
| 아이템 실물 | ItemEntity |
| 전리품 권리 | LootClaim |
| 보급칩 | 기존 화폐·플레이어 상태 |

Combat Result와 Quest Event는 필요 이상으로 같은 정보를 영속 복제하지 않는다.

---

# 14. Exclusive Duel

## 14.1 기본 정책

- 실제 공용 Actor를 사용한다.
- Actor당 동시에 한 건의 대련만 허용한다.
- 명시적으로 허용된 참가자만 전투한다.
- 외부 플레이어는 관찰 가능하되 개입할 수 없다.
- 일반 사망 패널티를 적용하지 않는다.
- 일반 Corpse·Loot를 생성하지 않는다.
- 비살상 종료를 기본으로 한다.

핵심 상점·의료·임무 NPC의 대련은 기본적으로 비활성화한다.

v1.0은 테스트 전용 Actor를 사용한다.

## 14.2 시간 정책

| 항목 | 값 |
|---|---:|
| 최대 대련 시간 | 10분 |
| 참가자 무행동 | 60초 |
| 연결 종료 유예 | 30초 |
| 기권·시간 초과 재신청 제한 | 30초 |
| 대기열 | 없음 |

## 14.3 무행동 시각

명시적으로 성공한 참가자의 유효 전투 행동만 활동 시각을 갱신한다.

다음은 갱신하지 않는다.

- 자동 공격 Tick
- 자동 Recovery
- 단순 상태 조회
- 서버 출력 수신
- 관찰자 입력

서버가 자동 전투를 계속하더라도 명시적 행동이 없으면 60초 제한을 적용한다.

## 14.4 사용자 경험

P-01에 따라 무행동 종료 시각을 플레이어가 이해할 수 있어야 한다.

대련 시작 안내 및 시간 제한 표시를 제공한다.

종료 전 안내는 불필요한 채팅 스팸을 만들지 않는 최소 수준으로 구현한다.

실제 대련 테스트에서 60초 정책이 기존 자동 전투 경험과 충돌하는지를 확인한다.

정책 값의 변경은 별도 게임 규칙 결정으로 처리한다.

## 14.5 상태 소유권

대련은 자신이 소유한 전투 상태만 변경·복원한다.

가능하면 실제 Actor의 공용 HP와 대련용 Combat State를 구별한다.

Actor 전체 Attribute Snapshot을 복원하지 않는다.

다른 도메인의 정상 변경을 덮어쓰지 않는다.

실제 아이템·기술 자원 소비는 유지한다.

## 14.6 종료

승리·패배·기권·시간 초과·연결 종료·복구 실패는 모두 단일 Final Result로 확정한다.

대련 종료는 한 번만 처리한다.

일반 처치 횟수·Corpse·일반 Reward를 발생시키지 않는다.

대련 결과를 임무와 연결하는 경우 명시적으로 허용된 Quest Policy만 사용한다.

---

# 15. Behavior·Narration·미래 기능

## 15.1 Behavior

Behavior는 Actor의 행동 선택과 대상 선택을 담당한다.

Combat Service가 실제 피해·자원·보상을 계산한다.

기본값은 `passive`로 한다.

- 현재 위치·시야·안전 지역 확인
- Claim 및 참가 권한 준수
- 중복 이벤트 방지
- 상태에 따라 허용 행동 결정

새로운 자동 선공·추적·순찰 콘텐츠는 이번 범위가 아니다.

## 15.2 Narration

Narration은 확정된 Domain Result의 표현 책임을 가진다.

다음 결과 유형을 모델링할 수 있다.

- `engage`
- `attack_hit`
- `attack_miss`
- `damage_taken`
- `special_telegraph`
- `special_hit`
- `status_applied`
- `death`
- `surrender`
- `capture`
- `disabled`

공격자·피해자·관찰자별 표현을 지원한다.

기존 게임 출력 의미를 유지한다.

`attack_miss` 타입의 존재는 신규 명중·회피 확률을 도입한다는 의미가 아니다.

## 15.3 미래 기능의 계약 수준

| 기능 | 이번 작업 |
|---|---|
| Shared Death | 실제 실행 |
| Exclusive Duel 승패·Abort | 실제 실행 |
| Surrender | 결과 Schema 및 유효성 검증 |
| Capture | 결과 Schema 및 유효성 검증 |
| Disabled | 결과 Schema 및 유효성 검증 |
| Simulation | 미지원 정책 선언·실행 거부 |
| World Event | 미지원 정책 선언·실행 거부 |
| NPC 동료 | 향후 확장 고려, 실제 콘텐츠 제외 |
| 자율 순찰·추적 | 향후 확장 고려, 실제 콘텐츠 제외 |

실제 구현되지 않은 기능을 실행 가능한 기능으로 노출하지 않는다.

미래 기능의 세부 상태 머신·영속 모델을 지금 과도하게 확정하지 않는다.

---

# 16. 지연 작업·타이머·재시작 복구

## 16.1 최상위 불변식

게임 상태의 정확성에 필수적인 지연 작업은 **재시작 후 실행 필요 여부를 판정할 영속 근거**가 있어야 한다.

메모리 Timer나 `after_change()` 콜백은 실행을 촉발하는 수단이다.

영속 작업 상태의 유일한 SSOT가 아니다.

## 16.2 영속 실행 근거

| 도메인 | 필수 복구 근거 |
|---|---|
| Combat | Encounter Generation, 예약 상태·시각 |
| Respawn | Actor 생명주기 상태·예정 시각 |
| Recovery | 마지막 확정 시각·회복 계산 상태 |
| Exclusive Duel | 참가자·종료 시각·활동 시각·완료 상태 |
| Bootstrap | World Format·초기화 완료 근거 |

일부 값은 기존 영속 모델에서 제공할 수 있다.

필요 없는 범용 작업 테이블은 추가하지 않는다.

## 16.3 Commit 이후 콜백 누락

다음 시나리오를 정상 복구 가능 상태로 설계한다.

```text id="lbxz5c"
DB 변경 Commit 성공
       ↓
서버 프로세스 종료
       ↓
after_change 콜백 미실행
       ↓
서버 재시작
       ↓
영속 상태·예정 시각 검사
       ↓
필요한 작업 재예약 또는 정합화
```

이미 확정된 효과를 다시 적용하지 않는다.

## 16.4 재시작 정합화

서버 시작 또는 관련 도메인 활성화 시 다음을 구분한다.

- 미완료 작업
- 이미 완료된 작업
- 예정 시각이 지난 작업
- 중복 등록된 작업
- 이전 Generation의 오래된 작업
- 현재 상태에서 무효화된 작업

처리 방식은 해당 Domain Policy가 소유한다.

시간이 지난 Tick을 무조건 순차 재실행하지 않는다.

기존 게임 규칙에 맞게 결과를 정합화한다.

## 16.5 실패 시나리오

다음을 테스트한다.

1. Commit 직후 종료
2. 동일 Timer 중복 호출
3. 실행 예정 시각 경과 후 재시작
4. 대상 Actor 소멸 후 오래된 Timer 호출
5. Encounter 종료 후 공격 Tick 호출
6. Respawn 후 이전 Generation 이벤트 호출
7. Duel 종료 직전 재시작
8. 예약된 작업의 취소·무효화
9. 콜백 실행 실패와 재시도
10. 도메인 상태 변경 실패 시 예약의 불일치

## 16.6 구현 제한

다음은 도입하지 않는다.

- 범용 Scheduler
- 범용 Event Bus
- 별도 Message Queue
- 모든 타이머용 공통 영속 테이블

실제 도메인 요구가 확인되는 경우에만 별도 설계 변경을 검토한다.

---

# 17. 경량 Delivery 계약

## 17.1 목적

상태 변경의 확정과 사용자 메시지 전달을 분리한다.

별도의 메시지 브로커는 만들지 않는다.

기존 ActionResult, CombatResult, Presentation, `after_change()`를 활용한다.

## 17.2 전달 이벤트

각 전달 이벤트는 필요한 다음 정보를 포함한다.

- 원래 Action/Combat Result 식별자
- 메시지 종류
- 수신자 또는 수신 범위
- 공개·비공개·가시성 정책
- 표현 데이터
- 전달 시점 조건
- 동일 결과 내 순서

## 17.3 상태와 전달 보장 구분

| 대상 | 필요한 보장 |
|---|---|
| 영속 상태 변경 | 원자성·Rollback |
| 게임 보상 | 영속적인 중복 지급 방지 |
| 일반 공개 발언 | 정상 연결에서 순서·수신 범위 |
| 전투 Narration | 확정 결과 기준 표현 |
| 화면 상태 갱신 | 현재 서버 상태와 일관성 |
| 네트워크 전송 | 실패해도 게임 효과 재실행 금지 |

Exactly-Once Network Delivery를 보장한다고 주장하지 않는다.

## 17.4 Commit 이후 전달

STATE_CHANGE의 성공 메시지는 Commit 이전에 전송하지 않는다.

실패한 변경에 대한 성공 결과는 전송하지 않는다.

메시지 전송 실패로 이미 Commit된 게임 변경을 다시 적용하지 않는다.

## 17.5 잠금 범위

현재 `world_change()`의 후처리는 RLock 범위 안에서 실행될 수 있다.

따라서 다음을 구현·검증한다.

- 영속 변경 경계의 불필요한 출력 최소화
- 수신자별 변경 영향 범위 축소
- 후처리 실패가 다음 게임 변경을 손상하지 않음
- 동일 Result 메시지 순서 유지
- 잠금 밖 전달 최적화 시 동시성·순서 보장

이번 전환에서 잠금 밖 전달을 필수로 강제하지 않는다.

측정된 성능 문제와 올바른 순서 보장을 함께 만족할 때 도입한다.

## 17.6 최신 상태 전달

전투·Party·Inventory 등 변경 영향을 받는 사용자를 기준으로 갱신 범위를 계산한다.

전체 Explorer 무조건 갱신은 필요한 범위에서 단계적으로 축소한다.

다만 최적화로 인해 관찰자·수신자의 UI가 잘못된 상태에 머무르지 않아야 한다.

---

# 18. Movement·Observation·Recovery

## 18.1 Gateway 전환

기존 v1.5의 **사용자 게임 Action 단일 Gateway** 결정을 유지한다.

이는 프로젝트 전역 P-06에서 자동으로 도출되는 원칙이 아니라 이번 Action Architecture 확장의 명시적 결정이다.

도입 이유:

- 텍스트·웹의 동일 행동 계약
- 일관된 대상·권한 검증
- 명령별 중복 실행 경로 제거
- 사용자 게임 Action의 명시적 결과 처리

## 18.2 Gateway 이전의 경계

모든 사용자 게임 Action이 Gateway를 사용하더라도 기존 Evennia 기능을 중복 구현하지 않는다.

이동은 기존 `move_to()`와 엔진 Hook을 재사용한다.

관찰은 기존 관찰·가시성 서비스를 사용한다.

상태·도움말도 기존 Projection·Renderer를 재사용한다.

Gateway는 실제 도메인 규칙을 복제하지 않는다.

## 18.3 Evennia 안전 Hook

다음을 유지한다.

- `move_to()`
- `at_pre_move()`
- `at_post_move()`
- Typeclass Lifecycle Hook
- Session/Puppet Hook

사용자 명령의 공식 실행 경로와 엔진 안전 Hook은 역할이 다르다.

서로 독립적인 정책을 중복 구현하지 않고 공통 Movement/Access Service를 사용한다.

## 18.4 명령 전환 정책

각 게임 명령을 전환할 때 다음을 검증한다.

- 기존 CmdSet의 중복 등록 제거
- 보호된 명령 이름의 명시적 이전
- 신규 Action 등록의 모호성 거부
- 실제 실행 결과의 동등성
- 직접 명령과 웹 버튼의 동등성
- 실행 시점의 권한 검사
- 불필요한 쓰기 트랜잭션 증가 여부
- 기존 Engine Hook의 안전성 보존

이전이 완료되지 않은 명령을 무리하게 신규 Gateway로 우회시키지 않는다.

Phase 1 PR-B 완료 시에는 사용자 게임 명령 전체의 공식 이전을 완료한다.

## 18.5 Recovery

READ_ONLY Action은 현재 시각 기준의 계산용 Snapshot을 사용한다.

실제 영속 Recovery 확정은 Domain Service의 STATE_CHANGE 경계에서 수행한다.

조회와 실제 행동의 회복 계산 기준 시각은 일치해야 한다.

---

# 19. Typed Reference 및 B-1

## 19.1 최종 ReferenceKind

| 대상 | Kind |
|---|---|
| 모든 NPC·Enemy | `ACTOR` |
| WorldObject | `OBJECT` |
| ItemEntity | `ITEM` |
| Corpse | `CORPSE` |
| Loot | `LOOT` |
| CurrencyLoot | `CURRENCY` |
| Room | `ROOM` |
| Door | `DOOR` |

Player/Party 및 다른 내부 Reference 종류는 각 도메인 계약에 따라 유지한다.

## 19.2 Actor 번호 그룹

기본 그룹은 다음과 같다.

```text id="f6qlse"
actor:<actor_id>
```

동일 Actor 종류의 여러 Spawn은 동일 선택 그룹을 사용할 수 있다.

실제 선택은 안정된 Object Reference로 확정한다.

같은 장소에서 서로 다른 Actor ID가 같은 표시 이름을 갖는다면 선택 그룹과 이름의 모호성을 정적 검증한다.

## 19.3 B-1 불변식

- Scope별 영속 번호
- 동일 실물의 번호 안정성
- 결번 비재사용
- 기존 그룹 초기화 정책 유지
- 가시성·권한 변화로 재번호 금지
- 실물 이동 시 기존 Scope 정책 적용
- 오래된 번호를 다른 대상으로 대체 금지
- 대상 소유·권한을 실행 직전 재검증

## 19.4 ReferenceKind 변경 계약

기존 `ENEMY` 및 NPC-as-`OBJECT`를 `ACTOR`로 전환한다.

이때 다음을 구분한다.

- 내부 Python ReferenceKind
- 웹 직렬화 Payload
- 사용자에게 보이는 선택 번호
- 실제 Object Identity
- 기존 명령 Alias

웹에서 오래된 ReferenceKind를 전달하더라도 이를 임의로 다른 Kind나 Actor로 재해석하지 않는다.

지원하지 않는 참조는 안전하게 거부한다.

## 19.5 클라이언트 호환

전환 시 다음 정책을 적용한다.

1. 서버는 현재 지원하는 Typed Reference만 수락한다.
2. 연결 중인 클라이언트의 오래된 선택 토큰은 재검증한다.
3. 이전 버전 참조로는 다른 대상을 실행하지 않는다.
4. 필요한 경우 클라이언트 상태 재조회·화면 갱신을 안내한다.
5. 기존 한국어 명령 의미와 B-1 선택 정책은 보존한다.

Fresh-only 정책이 웹의 오래된 요청을 무조건 안전하게 만들어 주지는 않는다.

---

# 20. Native-only 저장과 World Format

## 20.1 Native SSOT

| 데이터 | SSOT |
|---|---|
| 인벤토리·장비 | ItemEntity |
| 총기·탄창 | ItemEntity State |
| 광원 | ItemEntity State 또는 시설 상태 |
| 전리품 | ItemEntity·LootClaim |
| 보급칩 전리품 | CurrencyLoot |
| 성장·HP·정신력 | Explorer Profile |
| 임무 | Explorer Quest State |
| Actor | Actor Runtime |
| WorldObject | 해당 Domain Runtime |

계산용 Snapshot과 Cache는 허용한다.

독립적인 두 번째 저장 원본을 만들지 않는다.

## 20.2 공식 지원 구성

- Fresh Empty SQLite
- Single Evennia Server
- Native ItemEntity Runtime
- Native Actor/WorldObject Runtime

과거 게임 DB의 자동 업그레이드는 이번 전환에서 지원하지 않는다.

기존 개발 DB·백업은 자동 삭제·변환하지 않는다.

## 20.3 World Format

World Format Version은 전체 월드가 현재 Runtime을 실행할 수 있는지 판단한다.

ItemRuntime Version은 아이템 도메인의 내부 무결성을 판단한다.

두 값이 전체 월드의 READY 판정을 각각 독립적으로 소유하지 않는다.

## 20.4 Fresh 판정

단순히 Format Marker가 없다는 이유로 Fresh DB라고 판정하지 않는다.

다음을 확인한다.

- 현재 Schema
- 기존 월드 데이터의 존재
- 관리 대상 Object·Tag
- 기존 Explorer·게임 진행 데이터
- Native Runtime 정보
- 부분 초기화 흔적
- 무결성 오류

지원하지 않는 기존 DB와 손상된 DB는 안전하게 차단한다.

## 20.5 Bootstrap

초기화는 다음 단계를 수행한다.

1. Schema 준비
2. Fresh World 여부 검사
3. 필요한 진행 상태 기록
4. Native Item Runtime 준비
5. Room·Exit·Door 구성
6. Actor·WorldObject Spawn 생성
7. 참조 및 B-1 무결성 검사
8. 전체 World Audit
9. READY 확정

전체 초기화를 원자적으로 확정할 수 있다면 최소한의 Format Marker를 사용한다.

여러 트랜잭션을 필요로 하면 실제 복구에 필요한 진행 상태를 기록한다.

## 20.6 반복 실행

Bootstrap을 반복해도 다음을 변경하지 않는다.

- 기존 플레이어 진행
- Actor의 유효한 현재 HP·전투 상태
- 임무 진행
- 아이템 소유
- Door 상태
- B-1 번호
- 유효한 Encounter·LootClaim

현재 World Format이 지원되더라도 실제 무결성이 깨져 있으면 READY로 취급하지 않는다.

## 20.7 전환·운영 경계

Fresh-only는 승인된 신규 Runtime의 데이터 지원 범위다.

기존 설치 문서에 기록된 과거 Legacy Maintenance 절차는 역사적·기존 버전 운영 경계로 구분한다.

신규 Runtime에서 Legacy Fallback을 제공하지 않는다.

과거 DB를 신규 DB로 자동 변환하지 않는다.

---

# 21. 레거시 제거

## 21.1 최종 제거 대상

- NPC·Enemy 개별 Typeclass
- 구형 NPC/Enemy 정적 정의
- NPC별 직접 실행 Dispatcher
- 독립 Dialogue Dispatcher
- Enemy 전용 Combat Handler
- Enemy Typed Reference
- Legacy Item Backend
- Legacy Equipment Backend
- Legacy Loot Backend
- 구형 DB Cutover 실행 경로
- 사용하지 않는 Mapping·Alias

## 21.2 유지할 책임

- 기존 사용자 명령 의미
- 기존 순수 전투 계산
- Native ItemEntity API
- Equipment·Inventory Snapshot
- LootClaim·CurrencyLoot
- Room·Door 독립 모델
- B-1 번호 SSOT
- Evennia 안전 Hook
- 필요한 Django Schema Migration

이름만으로 코드를 삭제하지 않는다.

실제 호출 관계를 확인하고 필요한 책임을 이전한 뒤 Legacy 실행 경로를 제거한다.

## 21.3 전환 중 단일성

단계별 PR을 개발하는 동안 기존 기능과 신규 기능이 일시적으로 공존할 수 있다.

그러나 동일한 실제 게임 효과에 두 개의 공식 실행 경로를 활성화하지 않는다.

전환된 기능은 신규 공식 경로로 실행하고 구형 경로의 공개 등록을 해제한다.

Phase 1 PR-B 완료 후에는 NPC·Enemy·Dialogue·Combat의 구형 공식 실행 경로가 남아 있으면 안 된다.

---

# 22. 구현 계획

**현재 실행 계획은 이후 확정된 [2 Phase / 3 PR 구현 계획 v1.0](https://github.com/wonmin82/primal-zone/issues/83#issuecomment-6396602387)이다.** 아래 부록 D에 전체 계획을 보존한다. 과거 3 Phase / 4 PR 일정은 이 계획으로 대체하며 기능·불변식·검증 계약은 삭제하지 않는다.

| Phase | PR | 범위 | Gate |
| --- | --- | --- | --- |
| Phase 1 | PR-A Architecture Foundation | Actor/WorldObject/Spawn, Capability, 단일 Binding Source/Scope, 효과 경계·결과, Context, Combatant/Encounter, Delivery·Timer·World Format 기반 및 격리 수직 Fixture. 기존 Runtime/Legacy 호출 감사와 기준선 확보 | G1 Foundation |
| Phase 1 | PR-B Full Native Actor Cutover | B1 Actor·Spawn, B2 Shared Combat·Lifecycle·Reward, B3 Speech·Dialogue·Quest·Service, B4 Global Action·Movement·Observation·Web·B-1, B5 World Format·Native-only·Legacy 제거·문서 정합성 | G2 Full Cutover |
| Phase 2 | PR-C Exclusive Duel & Final Closeout | Duel·독점권·무행동·재접속·영속 복구·복합 Actor·확장성·성능·브라우저·최종 감사 | G3 Release Closeout |

PR-A는 기존 공식 게임 경로를 유지하고 신규 계약만 격리 Fixture에서 검증한다. 실제 Item/Equipment/Loot Native 정리·Canonical Profile·과거 Backend/Cutover 제거는 필요한 소비자 전환과 함께 PR-B에서 수행하며 계산용 Snapshot과 기존 데이터 보호를 유지한다. PR-B 뒤에는 Duel 없이 기존 게임 전체가 동작해야 한다.

현재 사용자 요청은 두 PR의 병합 전 리뷰까지다. PR-B는 PR-A 소스 브랜치를 base로 하는 Stacked PR로 구현하며 G1의 구현·리뷰·최종 HEAD CI 성공 뒤 진행한다. 병합·Issue 종료·소스 브랜치 삭제 및 Phase 2 구현은 승인 범위 밖이다. 계획 원문의 일반적인 병합 후 진행 순서와 이 요청의 병합 전 Stacked 실행을 구별한다.

---

# 23. 검증 전략

## 23.1 기존 동작 동등성

변경 전 Main의 Fresh Runtime에서 다음 기준을 확보한다.

- Actor·Enemy·NPC 콘텐츠 ID와 Spawn
- 전투 고정 RNG 결과
- 공격 간격
- Boss Scaling
- Party Claim·기여도·위협도
- XP·보급칩·드롭
- Quest 진행·보상
- NPC 대화·공개 발언
- ItemEntity·Equipment·Storage
- Door·Movement
- B-1 번호
- Recovery
- 웹 명령 동등성
- 재시작·Bootstrap

## 23.2 실패·동시성 검증

| ID | 시나리오 | 완료 조건 |
|---|---|---|
| T01 | Speech 성공·Dialogue 거부 | 발언 유지, Quest 변경 없음 |
| T02 | Speech 성공·Quest 지급 성공 | 보상 1회 |
| T03 | 동일 Quest 요청 재전송 | 중복 지급 없음 |
| T04 | Global Action의 잘못된 Scope | 정적 또는 실행 경계에서 거부 |
| T05 | Actor의 중복 Capability 문법 | 모호성 거부 |
| T06 | 오래된 웹 Target Reference | 다른 대상 실행 금지 |
| T07 | Session 권한 상실 | 사용자 효과 거부 |
| T08 | 신뢰되지 않은 내부 Principal | 내부 효과 거부 |
| T09 | 동일 Combat Generation 중복 종료 | 보상·Corpse 1회 |
| T10 | 이전 Generation Timer 실행 | 현재 전투 영향 없음 |
| T11 | Commit 직후 서버 종료 | 영속 상태에서 작업 복구 |
| T12 | Recovery·Respawn 재시작 | 시간·상태 정합성 |
| T13 | Duel 중복 종료 | 단일 Final Result |
| T14 | Duel 중 연결 종료·재접속 | 유예·복원 정책 준수 |
| T15 | Bootstrap 중단·반복 | 중복 객체 및 데이터 파괴 없음 |
| T16 | READ_ONLY 실행 | 부당한 영속 변경 없음 |
| T17 | 상태 변경 Rollback | DB·Cache·번호 일관성 |
| T18 | Delivery 실패 | 보상 재실행·상태 불일치 없음 |
| T19 | Engine Hook 직접 이동 | 공통 출입 정책 우회 없음 |
| T20 | Actor Capability만 변경 | 공통 Parser 수정 없이 정상 구성 |

## 23.3 선언형 확장성 검증

새 Actor 두 종류를 Fixture로 구성한다.

- 기존 Dialogue+Combat 기능을 그대로 조합한 Actor
- 기존 Interaction+Combat 기능을 그대로 조합한 Actor

이 Fixture를 추가하는 과정에서 공통 Parser·Gateway·Domain Service에 Actor ID별 분기 추가가 없어야 한다.

필수 Profile이 누락되면 정적 검증에서 거부해야 한다.

현재 상태에 따라 한 Capability가 비활성화되어도 다른 Capability가 정상 제공되어야 한다.

## 23.4 성능 기준선

기존 Main과 신규 Runtime의 동일 조건에서 다음을 측정한다.

| 항목 | 측정 대상 |
|---|---|
| Action 지연 | 대표 명령의 처리 시간 |
| Resolver DB 비용 | SQL 실행 횟수와 대상 검색 범위 |
| Registry 비용 | 컴파일·초기 로딩 |
| 잠금 점유 | `world_change()` 소요 시간 |
| 다중 Actor 조회 | Room 내 Actor 증가에 따른 비용 |
| State Delivery | 영향받는 사용자 수별 갱신 비용 |
| Bootstrap | 초기화·재실행 시간 |
| Combat Timer | 다수 참가자에서 Tick 처리 시간 |

동일한 환경·Fixture·테스트 기준으로 전후를 비교한다.

근거 없는 고정 성능 목표를 사전에 발명하지 않는다.

측정 결과에 의미 있는 회귀가 발생하면 원인과 비용을 평가하고, 수정하거나 승인된 트레이드오프로 기록한다.

## 23.5 게임 경험 검증

다음을 확인한다.

- 기존 주요 임무·보스 솔로 진행
- 기존 공개 발언 및 NPC 대화
- 직접 명령과 웹 버튼 동등성
- 좁은 화면과 실제 한국어 IME
- 전투·보상 메시지 가독성
- 대련 무행동 제한 이해 가능성
- 대련 중단·기권 안내
- 신규 기능이 기존 서비스 이용을 방해하지 않는지

자동 테스트 통과를 실제 OS IME 수동 검증 완료로 표현하지 않는다.

---

# 24. 범위 제외

다음은 이번 통합의 필수 구현 범위가 아니다.

- 기존 플레이 DB 업그레이드
- 과거 B-1 번호 데이터 이관
- Legacy Runtime Fallback
- 새로운 자동 선공 콘텐츠
- 신규 명중·회피 확률
- 새로운 Boss 전투 패턴
- 전투 밸런스 변경
- NPC 동료 콘텐츠
- PvP
- 완성형 NPC 순찰·추적 AI
- 정식 대련 콘텐츠 공개
- 완성형 항복·포획 콘텐츠
- Simulation 실행 엔진
- World Event 실행 엔진
- 범용 Scheduler
- 범용 Event Bus
- 영속 Message Queue
- 모든 Encounter 공통 저장 테이블
- Explorer Typeclass 통합
- PostgreSQL 전환

위 기능의 미래 확장 가능성을 보존하되 당장 실행 엔진을 구현하지 않는다.

---

# 25. 변경 관리 및 승인 정책

## 25.1 변경 가능한 사항

다음은 원칙을 지키는 범위에서 구현 중 결정할 수 있다.

- 모듈 및 파일 배치
- 내부 클래스·함수 구조
- Python 타입·Protocol 표현
- Compiled Index의 물리적 구성
- Encounter ID의 저장 형식
- Delivery 이벤트 자료형
- World Format Marker의 저장 방식
- 테스트 Fixture 구조
- 성능 최적화

## 25.2 별도 승인이 필요한 변경

- 기존 게임 명령 의미 변경
- 솔로 진행 가능성 변경
- 전투·보상 밸런스 변경
- B-1 번호 정책 변경
- Actor/WorldObject 경계 변경
- Explorer 영속 모델 통합
- 공통 Encounter 계약 제거
- 중요한 Registry 검증 제거
- 사용자 게임 Action Gateway 적용 범위 축소
- Fresh-only 지원 정책 변경
- 기존 데이터의 자동 삭제·변환
- 신규 콘텐츠 범위 확대
- Legacy와 신규 Runtime의 영구 공존

## 25.3 설계 충돌 해결

구현 중 정책 충돌이 발견되면 다음을 보고한다.

1. 관련 P-ID
2. 현재 결정과 불변식
3. 충돌 원인
4. 가능한 대안
5. 각 대안이 포기하는 보장
6. 게임 경험·데이터·복구·성능 영향
7. 권장안
8. 필요한 승인·검증

기존 Domain Design Freeze를 조용히 변경하지 않는다.

---

# 26. Design Freeze 결정표

| 영역 | 최종 결정 |
|---|---|
| NPC·Enemy | 단일 Actor |
| 시설 | WorldObject |
| 아이템 | Native ItemEntity |
| 플레이어 | Explorer 유지 |
| Capability | 경량 Descriptor + Sparse Composition |
| Action Registry | 기존 단일 Registry |
| Binding | 단일 ActionBinding + 명시적 Source |
| Global Action | 명시적 Scope Root |
| Gateway | 사용자 Action의 단일 신뢰 경계 |
| 상태 처리 | READ_ONLY / STATE_CHANGE |
| 완료 의미 | COMPLETED / ACCEPTED |
| 복합 Action | 효과별 명시적 정책·결과 |
| Speech | 일반 발언과 Dialogue 상태 변경 분리 |
| 서버 내부 이벤트 | 신뢰된 DomainExecutionContext |
| Combatant | 최소 공통 인터페이스 |
| Combat Runtime | 공통 Domain Service |
| Encounter | 공통 계약 + Policy별 저장 |
| Shared 보상 | Generation·종료·정산 멱등성 |
| Exclusive Duel | 비살상·독점·영속 복구 |
| Behavior | 행동 결정 |
| Narration | 확정 결과 표현 |
| Delivery | 경량 계약 + Commit 이후 전달 |
| Timer | 영속 복구 근거 + 재시작 정합화 |
| B-1 | 기존 안정 번호 정책 보존 |
| Typed Reference | Actor로 통합, 오래된 요청 안전 거부 |
| World Format | Fresh-only, 손상·기존 DB 차단 |
| 기존 밸런스 | 유지 |
| 구현 계획 | 2 Phase / 3 PR — §22·부록 D |
| 기본 원칙 | 프로젝트 P-01~P-12 참조 |

---

# 27. 최종 완료 정의

Primal Zone 통합 Actor v1.0은 다음 조건을 모두 충족해야 한다.

1. NPC·Enemy가 단일 Actor Definition과 Typeclass를 사용한다.
2. Actor Capability는 선언형으로 구성되고 중복 Service 정의가 없다.
3. 기존 기능을 새 Actor에 조합할 때 중앙 Parser·Gateway를 수정하지 않는다.
4. Global/Entity Action이 동일 Registry와 명시적 Scope 계약을 사용한다.
5. 사용자 게임 Action이 공식 Gateway를 통과한다.
6. 서버 내부 AI·Timer는 공통 Domain Service를 사용한다.
7. 복합 Speech·Dialogue 효과가 정확한 원자성·결과 경계를 가진다.
8. Explorer와 Actor가 공통 Combatant 계약을 사용한다.
9. Shared Combat의 기존 규칙과 보상이 보존된다.
10. Encounter 종료와 정산이 중복 실행되지 않는다.
11. Exclusive Duel의 참가·종료·복구가 정상 동작한다.
12. 필수 지연 작업이 Commit 이후 콜백 누락에도 복구 가능하다.
13. Quest·Loot·Item의 SSOT와 원자성이 보존된다.
14. Typed Reference와 B-1 선택 번호가 안정적으로 동작한다.
15. 기존 웹·텍스트 명령의 의미가 보존된다.
16. Fresh-only Bootstrap 및 반복·실패·재시작 복구가 안전하다.
17. Legacy 공식 실행 경로가 제거된다.
18. 선언형 확장성 Fixture가 실제 테스트를 통과한다.
19. 주요 기능·성능·사용자 경험 회귀가 검증된다.
20. 최종 코드·문서·CI 및 실제 Runtime이 일치한다.

---

# 부록 A. v1.5 리뷰 지적 반영 추적

## P1

| ID | 문제 | 반영 위치 | 조치 |
|---|---|---|---|
| P1-01 | Speech와 Dialogue의 상태 처리 | §8~§9 | 효과별 실행 정책·부분 결과·원자성 |
| P1-02 | Timer의 Commit 후 복구 | §12, §16 | 영속 복구 근거·재시작 정합화 |
| P1-03 | Global Action Scope | §7 | 명시적 Scope Root·정적 검증 |
| P1-04 | Capability와 Binding SSOT | §6~§7 | 사실별 소유권·파생 Index |
| P1-05 | Encounter 정산 멱등성 | §13 | Generation·종료·정산 계약 |
| P1-06 | Typed Reference와 Fresh-only | §19~§20 | 공개 계약·호환성·안전 거부 |
| P1-07 | 사용자 Gateway 전환 범위 | §3, §8, §18 | 아키텍처 결정 근거와 검증 |
| P1-08 | 내부 Context 권한 | §10 | Principal·Origin·Scope 구분 |

## P2

| ID | 문제 | 반영 위치 | 조치 |
|---|---|---|---|
| P2-01 | 미래 기능 과도한 고정 | §14~§15, §24 | 실행·Schema·미지원 정책 구분 |
| P2-02 | Delivery 보장·잠금 | §17 | Commit·순서·잠금·Exactly-Once 구분 |
| P2-03 | 선언형 확장성 검증 | §6, §23 | 신규 Actor 조합 Fixture |
| P2-04 | 성능·복잡성 기준 | §23 | 기존 Main 대비 동등 조건 측정 |
| P2-05 | 대련 UX | §14, §23 | 무행동 정책 안내 및 실제 플레이 검증 |

---

# 부록 B. 아키텍처 논리 교차 검증

| 검증 질문 | 설계상 결론 |
|---|---|
| READ_ONLY에서 상태 변경이 가능한가? | 불가. 복합 효과의 STATE_CHANGE는 별도 경계로 선언 |
| 공개 발언 성공 후 임무 거부가 가능한가? | 가능. 효과 결과를 독립적으로 표현 |
| 같은 요청이 재전송되어 보상이 중복될 수 있는가? | 도메인 정산 근거로 거부 |
| Global Action에 Provider가 없어도 Scope를 확정할 수 있는가? | 명시적 Root 사용 |
| Actor에 여러 Capability가 있어도 Binding이 중복되는가? | 기존 Registry 선언을 재사용 |
| Timer가 사용자 Session 없이 실행 가능한가? | 신뢰된 내부 Principal로 실행 |
| Timer가 모든 도메인 권한을 갖게 되는가? | 불가. Operation·Scope·현재 상태 검증 |
| Actor가 재생성된 뒤 오래된 전투 이벤트가 실행되는가? | 안정 Identity·Generation 검사로 거부 |
| 전투 종료와 보상 지급이 따로 확정되는가? | 아니오. 동일 논리적 정산 경계 |
| 서버 종료로 콜백이 사라져도 복구 가능한가? | 영속 예약·상태·시각으로 재구성 |
| Delivery 실패가 보상을 재실행하는가? | 불가 |
| Encounter 저장을 줄여도 멱등성이 유지되는가? | 완료 근거가 충분한 경우에만 허용 |
| 기존 Door Hook을 제거해야 하는가? | 아니오. 엔진 안전 경계 유지 |
| 기존 클라이언트의 잘못된 Reference가 다른 Actor를 가리키는가? | 불가. 안전 거부 |
| Capability가 없는 NPC에 전투 상태를 강제하는가? | 아니오. Sparse Composition |
| Simulation이 실행 가능한 것처럼 노출되는가? | 아니오. 미지원 실행 거부 |
| Fresh Marker가 없는 기존 DB를 초기화하는가? | 아니오. 기존 데이터 검사 후 차단 |
| 기존 게임 기능의 동등성을 어떻게 판정하는가? | 변경 전 기준선·회귀·실브라우저·CI |
| 구조 단순화가 필수 불변식을 제거하는가? | 제거 불가. 최소 충분 설계 적용 |
| 새 Actor 추가 시 공통 코드 수정이 필요한가? | 기존 Capability 조합이면 불필요해야 함 |

이 표는 **설계 계약 사이의 논리적 일관성 검토 결과**다. 실제 구현의 정확성이나 모든 운영 장애에서의 성공이 이미 입증되었다는 뜻은 아니다.

---

# 부록 C. 참조 자료

- 프로젝트 공통 아키텍처 원칙 — PR #82
- `AGENTS.md`
- `docs/architecture.md`
- `docs/action-architecture.md`
- `docs/action-migration.md`
- `docs/installation.md`
- Issue #44 — Action Architecture Design Freeze
- `game/world/actions/schema.py`
- `game/world/actions/registry.py`
- `game/world/actions/resolver.py`
- `game/world/actions/gateway.py`
- `game/world/npc_dialogue.py`
- `game/world/multiplayer.py`
- `game/world/bootstrap.py`
- `game/world/item_runtime.py`
- `game/world/selection_numbers/`
- `game/typeclasses/enemies.py`
- `game/typeclasses/explorers.py`

---

# 최종 결론

Primal Zone 통합 Actor 아키텍처는 프로젝트 공통 원칙 P-01~P-12를 준수한다.

핵심 설계 방향은 다음과 같다.

1. NPC와 Enemy의 영속 정체성을 Actor로 통합한다.
2. 기존 기능을 선언형 Capability로 조합한다.
3. 사용자 Action은 하나의 신뢰 경계를 사용한다.
4. 실제 게임 효과는 공통 Domain Service가 소유한다.
5. 전투·보상·임무·아이템 변경은 원자성과 멱등성을 보장한다.
6. 서버 내부 이벤트는 명시적 권한과 영속 복구 근거를 갖는다.
7. Encounter는 공통 의미 계약을 유지하면서 필요한 만큼만 저장한다.
8. 기존 게임 경험과 데이터 안전성을 보존한다.
9. 확장성은 실제 콘텐츠 조합 테스트로, 성능은 실제 측정으로 입증한다.
10. 새로운 구조의 도입보다 **책임·계약·상태 소유권의 명확성**을 우선한다.

**본 문서를 Primal Zone 통합 Actor 아키텍처 v1.6 FINAL — Project Architecture Principles Aligned의 구현 기준선으로 정의한다.**

**문서 끝.**


# 부록 D. 확정 실행 계획 전체 원문

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
