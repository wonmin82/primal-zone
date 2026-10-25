# Codex Windows 멀티 에이전트 운영

[Issue #68](https://github.com/wonmin82/primal-zone/issues/68)의 현행 운영 정책이다. [Issue #58](https://github.com/wonmin82/primal-zone/issues/58)의 실제 실행·실패 기록은 아래 역사 자료로 보존한다. 게임 코드·DB·CI·글로벌 설정은 바꾸지 않는다. 모델/Effort 지원은 **USER VERIFIED**이며 설정값과 실제 로딩·라우팅·권한 관측은 구분한다.

같은 부모 대화에서 **역할 지시·파일 소유권·Orchestrator의 Diff 검사**로 책임을 분리한다. `sandbox_mode = "read-only"`는 OS 강제 쓰기 차단의 증명이 아니다. 최초 MA-07 FAIL과 Reviewer 강제 쓰기 차단 NOT RUN은 유지한다. 강제 격리가 필요한 작업에는 이 구성을 사용하지 않는다.

## 역할과 책임

| 역할 / agent_type | 모델 | Effort | 설정 Sandbox | 담당 |
| --- | --- | --- | --- | --- |
| Orchestrator (부모) | `gpt-6.1-sol` | `low` | 부모 정책 유지 | 전체 계획·자율 위임·파일 소유권·생명주기·Git·최종 통합 |
| Scout / `scout` | `gpt-6-luna` | `high` | `read-only` | 소스·문서·의존성·영향 조사, 파일·Git 쓰기 금지 |
| Implementer / `implementer` | `gpt-6.1-sol` | `medium` | `workspace-write` | 할당된 파일 구현·직접 영향 테스트 |
| Reviewer / `reviewer` | `gpt-6.1-sol` | `high` | `read-only` | 일반 코드 정확성·회귀·예외·테스트 공백 독립 리뷰, 파일·Git 쓰기 금지 |
| Auditor / `auditor` | `gpt-6.1-sol` | `high` | `read-only` | 고위험 불변조건·동시성·권한·영속성·실패/복구 감사, 파일·Git 쓰기 금지 |
| Verifier / `verifier` | `gpt-6-luna` | `high` | `workspace-write` | 필요한 테스트 실행·재현성·CI 근거 검증, 제품 코드·Git 쓰기 금지 |

설정은 [config.toml](../.codex/config.toml), [scout.toml](../.codex/agents/scout.toml), [implementer.toml](../.codex/agents/implementer.toml), [reviewer.toml](../.codex/agents/reviewer.toml), [auditor.toml](../.codex/agents/auditor.toml), [verifier.toml](../.codex/agents/verifier.toml)에 있다. Verifier의 쓰기는 사전 허용된 격리 DB·소유 프로세스·테스트 산출물로 제한한다. 운영 DB·다른 에이전트 자원·제품 코드 수정 승인이 아니다.

메인은 Sol/Low, `[agents] enabled = true`, `max_concurrent_threads_per_session = 3`을 유지한다. 역할은 다섯 개지만 메인을 제외한 동시 실행 상한은 **3개**다. 모든 서브 에이전트의 중첩 위임을 금지한다. 메인의 Sandbox·승인 모드는 새로 강제하지 않는다.

공식 근거: [서브에이전트 설정](https://developers.openai.com/codex/multi-agent), [설정 Reference](https://developers.openai.com/codex/config-reference), [Windows 앱](https://developers.openai.com/codex/app/windows). 프로젝트 Trust와 세션 override를 고려하며 현재 인터페이스에 없는 기능을 가정하지 않는다.

## 작업 이름과 실제 역할 선택

TOML의 `name`은 고정 역할명이다. `agent_type`은 실제 역할 선택, `task_name`은 내부 작업 식별용 이름이며 서로 대체할 수 없다. 작업명만 붙이거나 메인이 역할을 흉내 낸 것은 커스텀 역할 로딩의 증거가 아니다.

새 `task_name`은 `<role>_<random_name>`으로 지정한다. 이름은 짧고 읽기 쉬운 영문 사람 이름(given name)을 역할·작업 내용·Issue/PR 번호와 무관하게 무작위로 선택한다. 내부 작업명은 소문자 영문과 밑줄만 사용한다. 예: `scout_emma`, `implementer_daniel`, `reviewer_alice`, `auditor_sophia`, `verifier_oliver`. 이 예시는 반복 사용하는 고정 목록이 아니며, 역할 TOML의 고정 `name`과 모델·Effort는 변경하지 않는다.

1. 지원되는 조회 기능으로 기존 이름·상태를 확인하고 같은 부모 세션에서 이미 사용한 이름과 비교한다. 닫힌 작업 이름도 새 작업에 재사용하지 않는다.
2. 충돌하면 다른 사람 이름을 선택하고 `_2`, `_3` 같은 순차 번호를 붙이지 않는다. 후보가 부족하면 사용 가능한 사람 이름 후보를 확장한다.
3. Orchestrator가 생성과 사용 이름 관리를 순차 조율한다. 같은 에이전트의 후속 재사용은 기존 작업 이름을 유지한다.
4. 복구된 이력 누락·조회 불가·동시 생성 시 보장할 수 없는 중복 확인 범위를 기록한다. 지침만으로 원자적 중복 방지나 세션 간 전역 고유성을 보장하지 않는다.

현재 도구에 `spawn_agent`의 `agent_type`/`task_name`, `list_agents`, `followup_task`, `send_message`가 노출되면 생성·조회·후속 전달에 사용한다. 이 인터페이스의 예시이며 모든 앱에 동일 API가 있다는 보장은 아니다. 기존 작업 이름 강제 변경·Windows/모바일 UI 표시 일치·스레드 복원은 별도 관측이 없으면 UNVERIFIED다. 숨은 API나 별도 자동화로 보장하지 않는다.

### 내부 작업명과 UI 표시명

내부 `task_name`과 Windows 앱 UI 표시명은 별개다. Issue #77에 기록된 사용자 화면에서는 `Reviewer wisteria`처럼 역할·공백·소문자 별칭이 관찰됐다. 따라서 내부 `reviewer_alice`가 화면에 `Reviewer alice`처럼 표시될 수 있지만, 해당 사람 이름의 실제 표시나 공백·대문자 변환 규칙은 이번 문서 검증에서 확인하지 않았다.

`Reviewer Alice`는 희망하는 표시 예시일 뿐이며 저장소 설정으로 보장하거나 구현 완료 조건으로 삼지 않는다. 현재 런타임에 노출되지 않은 표시명 API를 가정하지 않고, UI 대문자화를 위해 내부 작업명의 소문자 제약을 우회하지 않는다.

## 자율 위임과 파일 소유권

사용자가 작업을 요청하면 Orchestrator는 별도 에이전트 사용 지시 없이 요청 범위 안에서 **자율 위임**할 수 있다. 위임은 강제가 아니며 단순 질문·작은 문서/설정 수정은 직접 처리할 수 있다. 사용자의 에이전트 사용 금지·특정 역할 지정이 우선한다. 요청 없이 새 과제나 백그라운드 작업을 시작하지 않는다.

| 작업 | 기본 선택 |
| --- | --- |
| 작은 설명·문서·독립 수정 | Orchestrator 직접 처리 가능 |
| 영향 범위가 불명확한 조사 | Scout |
| 복잡한 구현 | Scout → Implementer → Reviewer, 필요 시 Verifier |
| 고위험 구현·중요 감사 | Scout → Implementer → Auditor, 필요 시 Verifier |
| 일반 PR 리뷰 | Reviewer, 필요 시 Scout |
| 테스트·CI 실패 재현 | Verifier, 필요 시 Scout |

표는 기계적인 분류나 추가 승인 절차가 아니다. 복잡도·위험도·독립성·검증 부담에 맞춰 필요한 역할만 선택한다. 자율 위임으로 범위·설계/게임 정책·DB 접근·대규모 검증·외부 조치·파괴적인 Git 작업을 확대하지 않는다. Commit/Push/PR 생성은 요청 범위를 따르고 **PR Merge·브랜치 삭제·Issue 종료는 사용자 명시 승인**이 있어야 한다.

- 전체 계획·파일/자원 소유권·생명주기·Git·최종 통합은 Orchestrator가 담당한다. 각 위임에 목적·요구사항·기준 HEAD/Diff·허용 파일·금지 작업·완료 조건·검증/보고 형식을 명시한다.
- 한 파일에는 동시에 한 명만 쓴다. 담당 외 파일·새 파일이 필요하면 먼저 조율한다. 기존 사용자 변경과 다른 에이전트 변경을 보존한다.
- 위임 전후 `git status --short`·Diff·미추적 파일을 비교한다. Scout/Reviewer/Auditor 쓰기, Verifier 제품 파일 쓰기, Implementer 담당 외 수정이 발견되면 멈추고 영향을 확인한다. Diff 확인은 예방적인 쓰기 차단 장치가 아니다.
- 운영 DB·플레이 데이터·실행 중 서비스·비밀 설정·글로벌 설정을 건드리지 않는다. 테스트 경로·소유 프로세스·산출물·정리 책임을 사전에 배정하며 허용된 소유 자원만 변경·정리한다.

### 리뷰·감사·검증 분업

Reviewer는 일반 코드의 정확성·회귀·예외·테스트 공백을, Auditor는 타이머·중복 보상·Loot 권리·인증·권한·영속 DB·트랜잭션·동시성과 실패/복구 불변조건을 독립 확인한다. 같은 Sol/High라도 **서로 다른 에이전트와 독립 컨텍스트·검토 목적**을 유지한다. Auditor를 상위 성능 역할로 단정하지 않는다.

기본적으로 위험도에 따라 Reviewer **또는** Auditor를 선택한다. 상이한 관점이 꼭 필요한 경우에만 교차 검토한다. 실제 Diff·소스·테스트 근거를 확인하며 구현자 보고만 신뢰하지 않는다. 지적은 코드 위치·발생 조건·영향·반례·수정 방향과 P0/P1/P2를 포함한다. 판정은 A=Ready for Review, B=Minor Follow-up, C=Hold이며 Issue #58 환경 판정 B=Partial과 구분한다.

Verifier는 코드 리뷰를 대신하지 않고 필요한 테스트 실행·실패 재현·CI HEAD/이벤트·재현성을 확인한다. Implementer의 직접 영향 테스트나 유효한 기존 성공 근거를 불필요하게 반복하지 않는다. 넓은 검증의 최종 소유자는 Orchestrator다. Reviewer/Auditor와 Verifier를 같은 **고정 HEAD 및 미커밋 Diff**에서 병렬 실행할 수 있으나 이후 코드 변경 시 영향받는 리뷰·검증만 갱신한다.

유효 결함·오탐·수정 불필요 판정·추가 수정·미검증 사항은 실제 업무 근거가 있을 때만 보고한다. 별도 모델 비교·형식적 이중 리뷰·평가 보고서·수치 집계를 만들지 않는다. 실제 사용한 역할·담당 범위·검증 근거를 구분하고 미사용 에이전트가 검증한 것처럼 표현하지 않는다.

## 제한적 재사용(Bounded Reuse)과 생명주기

같은 목적의 연속 작업은 컨텍스트가 유효하면 재사용하고 목적·단계·전제가 바뀌거나 독립 검토가 필요하면 신규 생성한다. 같은 Issue라는 이유로 장기 유지하거나 매 프롬프트마다 일괄 재생성하지 않는다. 고정 토큰 수·프롬프트 수·경과 시간이 아닌 관련성·전제 변경·재조사 범위·독립성으로 판단한다.

| 역할 | 재사용 범위 | 종료·신규 생성 |
| --- | --- | --- |
| Scout | 같은 조사 직후 추가 질문·근거 확인 | 조사/보완 후 종료, 새 주제는 신규 생성 |
| Implementer | 하나의 할당 구현·직접 영향 검사·관련 결함 수정 | 구현/보완 후 종료, 새 기능·범위 확대·전제 무효화 시 교체 |
| Reviewer | 같은 리뷰 회차의 좁은 수정 확인 | 회차 후 종료, 새 PR·범위 확대·최종 독립 전체 재리뷰는 신규 생성 |
| Auditor | 원칙적으로 재사용하지 않음 | 감사마다 신규 생성, 결과 수집 후 종료 |
| Verifier | 같은 검증과 직접 관련된 실패 재현·재검증 | 결과 확정 후 종료, 다른 범위·환경은 신규 생성 |
| Orchestrator | 하나의 Issue/독립 Phase 계획·통합 | 단계 상태 정리, 컨텍스트 과다 시 최소 인계 후 새 부모 대화 |

결과 반환 **Done**, 지원되는 명시적 종료 **Close**, 실제 활성 스레드, 앱 UI의 완료/히스토리 기록은 서로 다른 개념이다. 완료 기록이 목록에 남아 있다는 사실만으로 실행 중이거나 Close에 실패했다고 판단하지 않는다. 결과·근거를 수집하고 후속 보완이 없으면 지원되는 종료 기능으로 닫고 가능하면 상태를 확인한다. 실제 활성 상태와 슬롯 사용은 지원되는 조회로 확인 가능한 범위에서만 판단한다. 현재 `interrupt_agent`는 실행 중 턴의 중단이며 스레드 Close와 동일하지 않다. 전용 Close 도구가 없으면 종료·슬롯 해제를 보장하지 않고 한계를 기록한다.

완료 기록이 장기간 한 부모 대화에 누적되면 독립 Issue/Phase별 새 부모 대화를 시작하고 이전 대화를 보관하는 운영 방안을 사용한다. 보관은 자식 Close·슬롯 해제나 UI 기록 삭제를 보장하지 않는다. 강제 전체 Close, 활성 0개 Gate, 완료 기록 자동 삭제·일괄 Clear 또는 새로운 종료 승인 절차를 추가하지 않는다. UI 기록 정리를 위해 비공식 API·앱 내부 DB·JSONL·렌더러를 수정하지 않는다.

다른 Issue/PR/역할 전환, 요구사항·설계·파일 범위의 큰 변경, 오래된 가설·실패 로그 누적, 독립 판단 필요 시 결과를 수집하고 교체한다. 최소 인계는 **확정 요구사항·최신 Issue/PR 상태·기준 브랜치/HEAD/Diff·담당 파일·해결/미해결 결함·실제 테스트 결과·검증 공백** 중 필요한 정보만 제공한다. 과거 대화·폐기된 가설을 통째로 전달하지 않는다. 부모 대화도 Issue/독립 Phase 단위로 정리하며 강제 종료로 진행 중 결과를 잃지 않는다. 재사용·신규 생성 어느 쪽도 토큰 절약이나 품질 향상을 자동 보장하지 않는다.

## 중단 후 통합 재개

Stop·실행 오류·연결 문제 뒤의 재개 요청은 **기존 작업의 연속**이다.

1. 지원되는 조회로 기존 역할의 실행 중/Done/중단/접근 불가 여부와 Git 작업 트리·HEAD/Diff·미완료 단계·실제 검증 결과를 확인한다.
2. 부모 중단 후에도 자식이 실행 중일 수 있다. 쓰기·소유권이 불명확하면 같은 파일을 재배정하거나 덮어쓰지 않는다. 완료된 구현·검증은 반복하지 않는다.
3. 연결 가능하고 컨텍스트가 유효하면 후속 전달로 재사용한다. 복원 불가·컨텍스트 부적합이면 충돌이 없음을 확인한 뒤 **미완료 작업에 필요한 역할만** 신규 생성한다. 모든 역할을 일괄 호출하지 않는다.
4. 재개 요청을 자율 위임 해제나 Orchestrator 단독 실행 지시로 해석하지 않는다. 기존 분담과 승인·보안 경계를 유지한다. 단순 보고·결과 정리만 남았다면 직접 처리할 수 있다.
5. 상태·소유권을 신뢰할 수 없거나 재위임에 실패하면 충돌 가능한 작업을 멈추고 오류·완료/미완료 범위·복구 제약을 보고한다. 복잡한 구현·독립 리뷰를 조용히 단독 수행으로 바꾸지 않는다.
6. 재개 후에도 제한적 재사용·최소 인계·결과 수집 후 종료를 적용한다. 특정 API·기존 스레드 복원을 가정하지 않으며 미관측 기능은 UNVERIFIED 또는 NOT RUN으로 기록한다.

## Windows Native 사용 절차

1. 실제 경로·브랜치·Worktree·미커밋 변경과 Trust·Windows Native 환경을 확인한다. 글로벌 설정을 출력하거나 수정하지 않는다.
2. 설정 변경은 새 대화에서 확인한다. 기존 세션의 재로딩을 가정하지 않는다. 필요한 정상 앱 재시작은 사용자에게 맡기고 강제 종료하지 않는다.
3. 메인 Sol/Low와 세션 override를 구분한다. 지원 모델 재조사 없이 제공된 런타임 값만 대조하고 없으면 UNVERIFIED다.
4. 사용자 작업 요청 안에서 필요에 따라 자율 위임한다. 파일/자원 소유권과 랜덤 작업명을 배정하고 실제 역할 `scout`/`implementer`/`reviewer`/`auditor`/`verifier`를 지원되는 선택 수단으로 호출한다. 전원을 호출할 필요는 없다.
5. 역할 인식 실패 시 오류·경로·Trust·로딩을 확인하고 일반 에이전트나 다른 모델로 대체하지 않는다. 읽기 전용 선언과 실제 권한을 구분한다.
6. 위임 전후 Git 상태·Diff·새 파일을 확인하고 결과를 수집한다. 필요한 검사·최신 HEAD CI를 확인하며 기존 승인 범위 안에서 Git/PR/Issue 작업을 수행한다.
7. 같은 목적의 보완만 재사용하고 완료 후 지원되는 Close와 상태 확인을 적용한다. 기능 부재·모델 관측 불가·UI 표시 미확인은 사실대로 남긴다.


## Windows와 WSL

Windows Native는 Windows의 프로젝트 `.codex/`와 사용자 Codex Home을 사용하고 PowerShell·Windows Git으로 작업한다. WSL2는 Linux 환경의 경로·Shell·Codex Home을 사용하므로 Windows 글로벌 설정과 같다고 가정하지 않는다. WSL1은 이 가이드의 대상이 아니다.

같은 저장소를 WSL에서 열면 추적된 프로젝트 설정 파일은 공유할 수 있지만 Trust·경로·개인 설정·실행 중 권한은 다시 확인한다. `CODEX_HOME`을 명시적으로 지정했다면 그 위치가 사용자 설정 기준이 된다. Windows와 WSL의 Home을 자동 동기화하거나 Windows의 개인 설정을 WSL에 복사하지 않는다. Agent Environment 전환은 공식 Windows 안내에 따라 앱 재시작이 필요할 수 있으며, 사용자 작업을 보호한 정상 재시작으로 진행한다.

## 문제 해결

| 증상 | 대응 |
| --- | --- |
| 역할 호출·새 설정 반영 실패 | cwd·Trust·고정 name·필수 필드·실제 호출 인터페이스 확인. 기존 세션의 재로딩을 가정하거나 다른 역할/모델로 대체하지 않음 |
| 부모 권한이 역할 정책을 덮어씀 | 설정값·실제 권한·지시 준수 각각 기록. MA-07 FAIL 보존, 글로벌 정책 임의 수정 금지 |
| 파일 소유권 충돌 | 쓰기를 멈추고 메인이 기준 Diff와 담당 파일 재배정, 기존 사용자 변경 보존 |
| 이름 이력·중단 스레드 확인 불가 | 중복 방지·복원 보장 불가를 보고, 충돌 가능한 작업은 중단 |
| Close·재개 기능 또는 모델 메타데이터 없음 | Done/중단을 Close로 오인하지 않고 NOT RUN/UNVERIFIED 기록 |

## 최소 자동 검증

Issue #68은 T01~T03 PASS를 필수 완료 조건으로 사용한다. 새 외부 의존성·별도 영구 검증 스크립트는 추가하지 않는다.

### T01 — 설정 정합성

저장소 루트에서 Python 표준 `tomllib`으로 설정 6개를 검사한다.

```powershell
@'
import pathlib, tomllib
root = pathlib.Path(".codex")
main = tomllib.loads((root / "config.toml").read_text(encoding="utf-8"))
assert main == {"model": "gpt-6.1-sol", "model_reasoning_effort": "low",
                "agents": {"enabled": True, "max_concurrent_threads_per_session": 3}}
expected = {
    "scout": ("gpt-6-luna", "high", "read-only"),
    "implementer": ("gpt-6.1-sol", "medium", "workspace-write"),
    "reviewer": ("gpt-6.1-sol", "high", "read-only"),
    "auditor": ("gpt-6.1-sol", "high", "read-only"),
    "verifier": ("gpt-6-luna", "high", "workspace-write"),
}
assert {p.stem for p in (root / "agents").glob("*.toml")} == set(expected)
for name, values in expected.items():
    cfg = tomllib.loads((root / "agents" / f"{name}.toml").read_text(encoding="utf-8"))
    assert cfg["name"] == name
    assert (cfg["model"], cfg["model_reasoning_effort"], cfg["sandbox_mode"]) == values
    assert cfg["description"].strip() and cfg["developer_instructions"].strip()
print("T01: PASS (6 TOML)")
'@ | .\.venv\Scripts\python.exe -
```

T01은 설정 선언만 확인하며 실제 모델 적용·역할 선택·권한 분리를 증명하지 않는다.

### T02 — 문서 정합성

`AGENTS.md`와 이 가이드의 역할·작업명·자율 위임·제한적 재사용·종료·중단 후 재개·승인/안전·상대 참조를 간단한 자동 문자열/구조 검사로 확인한다. 정책이 문서에 존재한다는 것과 실제 동작 보장은 구분한다.

### T03 — Git 변경 검증

`git diff --check`와 Stage 후 `git diff --cached --check`·`git diff --cached`를 확인한다. `git status --short`와 미추적 파일을 포함해 허용 범위와 기존 사용자 변경의 비혼입을 확인한다.

### T04 — 선택적 경량 Smoke

수동 조작·추가 승인 없이 안전하게 자동 호출할 수 있을 때만 읽기 전용 서브 에이전트 1개를 짧게 실행해 역할 지정·응답을 확인한다. 불가능하면 NOT RUN과 이유를 기록한다. 모델/Effort·UI 표시·재사용·Close·재개처럼 호출로 관측되지 않는 기능은 UNVERIFIED다.

게임 테스트·Full Smoke·브라우저 E2E·모델 비교·다수 에이전트 생성·반복 종료 시험·인위적인 중단/오류/충돌 재현은 하지 않는다. Windows/모바일 UI 수동 확인을 필수로 요구하지 않는다. 자동 CI는 변경·비활성화하지 않고 최신 PR HEAD 결과를 확인한다. 결과는 PASS / FAIL / NOT RUN / UNVERIFIED로 구분해 PR Validation에 간결히 남긴다. 아래 역사 자료의 Issue #58 권한 시험은 이번에 반복하지 않는다.


## Phase 58-A~E 실행 기록

2026-10-13, Windows Native PowerShell, Base `f6ab3e733a30b6077d4977ede90272045bf153e7`. 시작 시 main과 작업 트리는 깨끗했고 Worktree는 하나, Trust는 trusted였다. 새 작업 브랜치는 `codex/issue-58-multi-agent-setup`이다. 모델 지원은 USER VERIFIED다. 개인 경로나 원본 세션 내용은 공개 기록에 넣지 않는다.

| Phase | 상태 | 근거 |
| --- | --- | --- |
| 58-A | PASS | Windows Native·Git/GH·Trust·최신 Base·기존 설정 없음·사용자 변경 없음 확인 |
| 58-B | PASS | 4 TOML 문법·지정값·이름·범위 검사. CLI 0.162.0의 독립 app-server `--strict-config`와 `config/read`가 프로젝트 모델/Effort/agents를 해석 |
| 58-C | 최초 FAIL / 운영 재판정 | 세 역할 실행·라우팅·병렬 작업 완료. 강제 격리는 실패했고, 이후 사용자가 같은 부모 대화의 역할 지시 기반 운영을 승인 |
| 58-D | PASS | 운영·재현·실패 대응 절차와 실제 권한 실패 기록 |
| 58-E | 진행 | 정적 검사·최종 안전성 확인. Commit/PR·최신 CI는 PR Validation에 실행 후 확정 |

CLI의 별도 app-server 검사는 설정 Schema/유효 설정 확인이며 Windows 앱 역할 Smoke의 대체가 아니다. 독립 진단에서 `model=Sol Low`와 `agents`의 프로젝트 설정 적용을 확인했다. 메인 Sandbox/승인은 기존 개인 설정에서 해석됐으며 프로젝트에서 추가하지 않았다.

실제 앱 Smoke의 runtime 버전은 세션 메타데이터의 `0.162.0-alpha.17.2`로 관측했고, 별도 CLI 검사 버전은 `0.162.0`이었다. 앱 UI의 설치 버전을 이 값으로 추정하지 않는다. 최초 실행 중 app-server proxy의 읽기 전용 설정 조회는 20초 응답 대기 실패로 중단하고 소유한 진단 프로세스만 종료했다. 이후 독립 strict-config 검사와 실제 새 앱 대화의 역할 호출을 각각 검증했다.

세 역할 Smoke 대화는 `01a132de-cab7-7063-a3f3-b88ce7cd4837`이다. 실제 호출은 모델 수동 override 없이 `agent_type=scout/implementer/reviewer`로 수락됐다. 각 역할의 파일 지침 적용과 결과 반환을 확인했고, 메인은 각 child의 세션 기록에서 모델·Effort·승인·Sandbox 필드만 읽었다. 인증정보나 원본 대화는 수집·공개하지 않았다. 작업 이름만 지정해 네 TOML을 만든 최초 구현 위임은 별도의 구현 작업이며, 커스텀 역할 로딩 성공으로 합산하지 않았다.

MA-07에서 새로 만든 임시 폴더의 Scout 쓰기는 exit 0으로 성공했으며 승인 요청은 관측되지 않았다. Reviewer는 쓰기 금지 지침을 따라 시도하지 않았다. 검증자가 만든 Scout 파일만 제거하고 폴더 부재를 확인했다. 최초 강제 격리 수용 기준에서는 이 결과로 C — HOLD였고, 독립 Reviewer도 같은 차단 판정을 내렸다. 이는 게임 결함이 아니며, 현재 운영 승인으로 실패가 해결되거나 쓰기 차단에 성공한 것은 아니다.

이후 사용자는 세션 분리 대신 같은 대화의 역할 지시·파일 소유권 분리 방식을 선택했다. 지정 모델/Effort·동시 상한·역할별 Sandbox 선언은 보존한다. 최초 MA-01~06/08의 실제 실행 근거는 역할 동작이 동일하므로 유지하며 이번에 새로 실행한 것으로 표현하지 않는다. 추가 검토는 변경한 운영 지침과 실제 diff에 집중한다. `default_permissions`로 교체하거나 글로벌 `sandbox_mode`를 수정하지 않는다.

| 최초 Smoke | 실행 결과 | 관측·제한 |
| --- | --- | --- |
| MA-01 | PASS | 새 Windows 앱 대화 Sol Low, custom 세 이름 호출 수락 |
| MA-02 | PASS | 실제 Scout가 명령 등록·처리·테스트·AGENTS 근거 제시. 저장소 수정 없음 |
| MA-03 | PASS | 실제 Implementer가 #59 요청 URL·정적 리소스·최소 제공·Chromium 확인 계획만 작성. 구현 없음 |
| MA-04 | PASS | 실제 Reviewer가 #50 최종 댓글과 QA 코드를 독립 확인. 제한된 검토에서 새 P0/P1 없음, 기존 P2 #59 추적 유지 |
| MA-05 | PASS | 독립 child thread 세 개의 실제 시작·동시 실행. 설정상 상한 3이며 네 번째 호출의 거부 검사는 미실행 |
| MA-06 | PASS | 각 child의 최신 turn_context에서 Scout Luna High / Implementer Sol Medium / Reviewer Astra Medium. 메인 Sol Low. 모델 지원 재조사 없음 |
| MA-07 | FAIL | 세 child가 부모와 동일한 workspace-write / on-request로 관측됨. Scout 임시 파일 생성 exit 0. Reviewer 쓰기 시도는 역할 지시로 NOT RUN이므로 거부 성공으로 취급하지 않음. 정확한 내부 권한 적용 경로는 UNVERIFIED |
| MA-08 | PASS | 역할 작업에서 저장소·Git·DB·글로벌·CI·Issue 쓰기 없음. 생성한 임시 파일·폴더 정리 확인. 메인은 글로벌/DB 지문과 변경 범위를 재확인 |

역할 설정값 적용과 읽기 전용 강제 분리는 별개의 결론이다. 최초 판정은 **C — HOLD**였다. 현재 판정은 사용자 승인된 운영 기준으로 별도 검토하며, MA-07 자체는 계속 FAIL이다. 글로벌 설정이나 부모 권한을 임의로 바꾸어 성공 처리하지 않는다.

설정/문서만 바꾸므로 로컬 게임·Python/Evennia·브라우저·Full Smoke를 재실행하지 않는다. Push 후 필수 CI는 변경하지 않고 최신 PR HEAD 결과를 PR Validation에 기록한다. 완료된 #50/#45를 재검증하거나 재오픈하지 않는다. #59는 읽기 전용 계획 대상이며 수정하지 않는다.

### 최초 완료 Gate 기록

| Gate | 상태 | 근거 |
| --- | --- | --- |
| G58-01 | PASS | Windows Native 기준선 |
| G58-02 | USER VERIFIED | 지정 모델/Effort 지원은 사용자 확인 완료 |
| G58-03 | PASS | 네 설정의 TOML·지정값·필수 필드 |
| G58-04 | PASS | 새 앱 custom agent_type 호출·실제 모델/Effort |
| G58-05 | FAIL | Scout/Reviewer에 부모 workspace-write 적용 |
| G58-06 | PASS | 구현 담당만 할당 파일 작성, 실제 커스텀 Implementer Smoke에서는 계획만 |
| G58-07 | PASS | 실제 세 역할 병렬 실행 |
| G58-08 | PASS | 글로벌·DB 지문·기존 Worktree·완료 Issue 보존, 허용한 다섯 파일만 변경 |
| G58-09 | PASS | Windows/WSL·권한 주의·사용·재현 가이드 |
| G58-10 | NOT RUN | 이 기록은 Commit 전 검사. 최신 PR와 필수 CI 결과는 실행 후 PR Validation에서 확정 |

### 사용자 승인 후 현재 운영 Gate

동일한 Smoke 부모 대화에서 수정된 역할 파일로 `policy_scout`, `policy_implementer`, `policy_reviewer`를 실제 custom agent_type으로 다시 생성했다. 세 역할은 동시에 실행됐고, 최신 운영 문단이 역할 developer 지침에 주입됐음을 확인했다. Scout의 설정/가이드 조사, Implementer의 할당 범위 확인, Reviewer의 실제 전체 diff 독립 검토를 완료했으며 저장소 수정·새 파일 생성은 없었다. 메인은 작업 전후 설정 네 파일과 가이드의 내용 해시가 같음을 확인했다.

메인이 허용된 runtime 필드만 대조한 결과 새 역할도 Scout Luna High, Implementer Sol Medium, Reviewer Astra Medium이었다. 부모 Sol Low와 자식의 실제 권한은 모두 workspace-write / on-request였다. 강제 격리 보장은 추가되지 않았다. Reviewer는 사용자 승인된 현재 운영 기준에서 A — Ready for Review, 새 P0/P1/P2 지적 없음으로 보고했다. 이는 최초 강제 격리 실패의 해소 판정이 아니다.

| Gate | 현재 기준 | 상태 및 근거 |
| --- | --- | --- |
| G58-01~04 | Windows 기준선·USER VERIFIED·설정·실제 역할과 라우팅 | PASS: 최초 검사와 동일한 모델/Effort/이름/설정 문법 |
| G58-05 | Scout/Reviewer의 쓰기 금지 지시와 역할 준수 | PASS: 최초 일반 역할 작업에서 저장소 수정 없음. 강제 격리 기준을 사용자가 변경했으며 최초 MA-07 FAIL은 별도 보존 |
| G58-06~07 | 할당 파일 수정 책임·동시 세 역할 실행 | PASS: 구현 위임의 소유권 분리와 실제 세 역할 병렬 실행 근거 유지 |
| G58-08 | 글로벌·게임·DB·사용자 Worktree 보호 | PASS: 글로벌/DB 내용 해시 동일, 기존 Worktree와 #50/#45/#59 본문·상태 보존, 허용된 다섯 파일만 변경 |
| G58-09 | 같은 대화의 운영 가이드와 제한 명시 | PASS: TOML·문서 상대 링크·diff 검사와 실제 custom Reviewer 독립 리뷰 |
| G58-10 | 새 PR와 최신 HEAD 필수 CI | 제출 후 PR Validation에 실제 SHA/URL/결과 기록 |

이 표는 강제 권한 격리의 성공 표가 아니다. 역할 지시 기반 운영의 검증과 최신 CI가 통과하면 해당 범위에서 Ready for Review로 제출한다. PR을 자동 병합하지 않으며 Issue #58과 Source는 유지한다.
