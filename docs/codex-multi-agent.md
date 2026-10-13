# Codex Windows 멀티 에이전트 운영

[Issue #58](https://github.com/wonmin82/primal-zone/issues/58)의 프로젝트 설정이다. 게임 코드·DB·CI·사용자 글로벌 설정을 바꾸지 않는다. 모델과 Reasoning Effort 지원은 **USER VERIFIED**이며, 지원 여부와 실제 역할 로딩·라우팅·권한 검증을 구분한다.

현재 운영 기준은 사용자가 2026-10-13 승인한 **같은 부모 대화 안의 역할 지시·파일 소유권 기반 분리**다. Scout/Reviewer의 파일 쓰기 금지와 Implementer의 할당 파일 수정 책임을 유지하고 메인이 변경 범위를 확인한다. OS/Sandbox가 역할마다 쓰기를 강제로 거부한다는 보장은 이 운영 방식의 완료 조건으로 사용하지 않는다. 최초 강제 격리 검사 실패는 아래 역사 기록으로 보존하며 PASS로 바꾸지 않는다.

## 역할과 책임

| 역할 | 모델 | Effort | 설정한 Sandbox | 담당 |
| --- | --- | --- | --- | --- |
| Orchestrator | `gpt-6.1-sol` | `low` | 부모 세션 정책 유지 | 요구사항·위임·Gate·Git 작업·최종 통합 |
| Scout | `gpt-6-luna` | `high` | `read-only` | 소스·문서·호출 관계·검증 공백 조사 |
| Implementer | `gpt-6.1-sol` | `medium` | `workspace-write` | 할당된 파일의 최소 구현·직접 영향 검사 |
| Reviewer | `gpt-6-astra` | `medium` | `read-only` | 실제 diff·소스·검증 근거의 독립 리뷰 |

설정 파일은 [config.toml](../.codex/config.toml), [scout.toml](../.codex/agents/scout.toml), [implementer.toml](../.codex/agents/implementer.toml), [reviewer.toml](../.codex/agents/reviewer.toml)이다. 커스텀 역할은 파일의 `name`으로 호출한다. 단순히 작업 이름이나 프롬프트에 역할 이름을 넣은 것은 커스텀 설정 로딩의 증거가 아니다.

메인 설정은 다음과 같다. 서브에이전트 동시 제한 3은 메인 스레드를 제외한 수다. 메인의 Sandbox·승인 모드를 프로젝트 설정에서 새로 강제하지 않는다.

```toml
model = "gpt-6.1-sol"
model_reasoning_effort = "low"

[agents]
enabled = true
max_concurrent_threads_per_session = 3
```

공식 근거: [서브에이전트 설정](https://developers.openai.com/codex/multi-agent), [설정 Reference](https://developers.openai.com/codex/config-reference), [Windows 앱](https://developers.openai.com/codex/app/windows). 프로젝트 설정은 신뢰된 프로젝트에서 적용된다. 앱에서 선택한 모델과 실행 중 권한 override가 파일의 기본값보다 우선할 수 있다.

**권한 주의:** `sandbox_mode = "read-only"`와 역할의 쓰기 금지 지시는 서로 다른 보호다. 부모의 실행 중 권한 override가 자식에도 재적용되면 실제 Sandbox가 `workspace-write` 또는 Full Access가 될 수 있다. 이 상태에서 파일 수정이 없었다는 사실만으로 읽기 전용 강제 격리를 PASS로 판정하지 않는다. 현재 구성은 역할 지시 준수에 의존한다. 강제 격리가 필요한 작업에는 사용하지 않는다.

## Windows Native 사용 절차

1. Codex Windows 앱에서 원시구역 프로젝트를 연다. 실제 저장소와 작업 브랜치·Worktree·미커밋 변경을 확인한다.
2. 프로젝트 Trust와 Windows Native Agent Environment를 확인한다. 글로벌 `%USERPROFILE%\.codex` 설정을 자동 수정하지 않는다.
3. 설정을 만든 뒤 새 대화를 시작한다. 기존 대화에 설정이 다시 로딩됐다고 가정하지 않는다.
4. 메인 모델 `gpt-6.1-sol`, Effort `low`를 확인한다. 앱 UI의 선택값이 프로젝트 기본값을 재정의할 수 있다.
5. 앱의 제한된 권한 모드를 사용한다. Full Access는 기본 운영으로 권장하지 않는다. 제한된 모드도 작업 공간 쓰기를 허용할 수 있으므로 Scout/Reviewer의 강제 읽기 전용 보장으로 해석하지 않는다. 이 프로젝트 설정은 앱이나 글로벌 권한을 자동 변경하지 않는다.
6. 사용할 역할과 파일 소유권을 명시적으로 배정한다. 현재 운영은 사용자 요청이 있을 때 위임하며, 역할별 하위 위임은 금지한다.
7. 실제 `scout`, `implementer`, `reviewer` 호출 수락과 각 결과를 확인한다. 이름을 인식하지 못하면 실행을 멈추고 설정 경로·Trust·로딩을 점검한다.
8. 런타임 모델·Effort·Sandbox가 제공되면 실제 값과 설정값을 대조한다. 제공되지 않는 값은 `UNVERIFIED`로 남긴다.
9. 메인은 시작 시점과 역할 작업 이후의 `git status --short`, diff와 새 파일을 비교한다. Scout/Reviewer의 저장소 수정 또는 Implementer의 담당 외 수정이 발견되면 다음 작업을 멈추고 원인과 영향 범위를 확인한다. Git diff 확인은 예방적인 쓰기 차단 장치가 아니다.
10. 메인이 결과를 통합한다. 필요한 검사와 최신 CI를 확인한 뒤 사용자에게 결과와 제한을 보고한다.

앱 재시작이 꼭 필요하면 진행 중인 작업을 저장하고 사용자가 정상적으로 재시작한다. 자동 강제 종료하지 않는다. 이 구성은 앱 UI에 세 개의 선택 버튼이 반드시 생긴다는 의미가 아니다. 실제 커스텀 역할 호출을 기준으로 확인한다.

## 작업 분해와 파일 소유권

메인은 Scout 조사 결과로 영향 범위를 정리하고 Implementer에게 파일과 완료 조건을 배정한다. Reviewer는 구현 완료 diff와 실제 검증 결과를 직접 읽는다. 독립 탐색은 병렬로 수행할 수 있지만 최종 리뷰는 구현이 끝난 기준을 고정한 뒤 한다.

- 한 파일에는 동시에 한 명만 쓴다. 새 파일이나 담당 외 수정이 필요하면 메인이 소유권을 다시 배정한다.
- 메인은 기존 사용자 변경을 보존하고 에이전트별 변경을 확인한다. 다른 에이전트의 변경을 되돌리지 않는다.
- Implementer는 직접 영향 검사부터 실행하고 넓은 검증 책임은 메인과 조율한다. 같은 전체 검사와 Smoke를 역할마다 반복하지 않는다.
- Git 스테이징·Commit·Push·PR 작업은 메인이 통합한다. 역할의 보고만으로 검증 완료를 단정하지 않는다.
- Reviewer는 P0/P1/P2와 근거·발생 조건·수정 방향을 보고한다. 코드 리뷰 판정 A=Ready for Review, B=Minor Follow-up, C=Hold를 사용한다. Issue #58 환경 판정의 B=Partial과 구분한다.
- PR Merge·Issue Close·브랜치 삭제는 별도 사용자 승인 범위 안에서만 메인이 수행한다. 이 설정 자체는 승인이나 자동 실행 요청이 아니다.
- 운영 DB·게임 서비스·비밀 설정은 작업 대상에 넣지 않는다. 게임 정책 변경은 사용자 승인과 [AGENTS.md](../AGENTS.md)를 따른다.

### 일반 기능 구현

> Scout에게 요구사항과 영향을 받는 파일을 분석하도록 위임해 주세요. 결과를 바탕으로 Implementer에게 최소 구현과 직접 영향 테스트를 맡기고, 완료된 Diff는 Reviewer가 독립적으로 리뷰하도록 해 주세요. 마지막으로 전체 결과와 미해결 문제를 정리해 주세요.

### PR 독립 리뷰

> Scout에게 변경 경로와 의존성을 조사하게 하고, Reviewer에게 실제 Diff·테스트 근거·권한·영속성·동시성 위험을 독립 검토하도록 위임해 주세요. 결과를 P0/P1/P2로 분류하고 병합 가능 여부를 판정해 주세요. 코드는 수정하지 마세요.

### 조사 전용

> Scout를 사용해 해당 기능의 실제 구현 위치와 호출 관계를 조사해 주세요. 관련 파일과 함수, 기존 테스트, 잠재적 검증 공백을 보고해 주세요. 다른 에이전트는 호출하지 말고 코드를 수정하지 마세요.

## Windows와 WSL

Windows Native는 Windows의 프로젝트 `.codex/`와 사용자 Codex Home을 사용하고 PowerShell·Windows Git으로 작업한다. WSL2는 Linux 환경의 경로·Shell·Codex Home을 사용하므로 Windows 글로벌 설정과 같다고 가정하지 않는다. WSL1은 이 가이드의 대상이 아니다.

같은 저장소를 WSL에서 열면 추적된 프로젝트 설정 파일은 공유할 수 있지만 Trust·경로·개인 설정·실행 중 권한은 다시 확인한다. `CODEX_HOME`을 명시적으로 지정했다면 그 위치가 사용자 설정 기준이 된다. Windows와 WSL의 Home을 자동 동기화하거나 Windows의 개인 설정을 WSL에 복사하지 않는다. Agent Environment 전환은 공식 Windows 안내에 따라 앱 재시작이 필요할 수 있으며, 사용자 작업을 보호한 정상 재시작으로 진행한다.

## 문제 해결

| 증상 | 확인 및 대응 |
| --- | --- |
| 커스텀 에이전트가 인식되지 않음 | 현재 cwd·Trust·`.codex/agents/*.toml`·고유 `name`·필수 필드·앱이 제공하는 호출 방식 확인. 수동 모델 지정으로 로딩 성공을 대체하지 않음 |
| 새 설정이 반영되지 않음 | 새 대화로 확인. 필요한 정상 앱 재시작은 사용자에게 맡김 |
| 앱 모델과 프로젝트 기본값이 다름 | UI 선택 또는 세션 override 확인. 요청한 모델을 다른 모델로 자동 대체하지 않음 |
| 부모 권한이 자식 정책을 덮어씀 | 실제 자식 Sandbox와 역할 지시 준수를 각각 기록. 강제 격리는 FAIL/UNVERIFIED로 남기며 현재 운영에서는 지시·소유권·diff 확인을 적용. 글로벌 정책을 임의 수정하지 않음 |
| 역할 호출 실패 | 오류와 호출 역할을 기록. 모델 지원은 USER VERIFIED이며 접근 권한 재조사를 기본 복구로 수행하지 않음 |
| 같은 파일 편집 충돌 | 쓰기를 중단하고 메인이 소유권·기준 diff 재배정. 사용자 변경을 덮어쓰지 않음 |
| 글로벌/프로젝트 설정 충돌 | 유효 설정과 출처를 확인. 글로벌 파일을 출력·수정하지 않고 필요한 키만 비교 |
| 모델 실행 기록을 볼 수 없음 | 설정값과 지원 여부는 기록하되 런타임 값은 UNVERIFIED. 실제 모델을 추정하지 않음 |

## 검증 방법

TOML 문법과 지정값을 검사한다. Python 표준 `tomllib`만 사용하며 새 의존성을 추가하지 않는다.

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
    "reviewer": ("gpt-6-astra", "medium", "read-only"),
}
names = set()
assert {p.stem for p in (root / "agents").glob("*.toml")} == set(expected)
for name, values in expected.items():
    cfg = tomllib.loads((root / "agents" / f"{name}.toml").read_text(encoding="utf-8"))
    assert cfg["name"] == name and name not in names
    assert (cfg["model"], cfg["model_reasoning_effort"], cfg["sandbox_mode"]) == values
    assert cfg["description"].strip() and cfg["developer_instructions"].strip()
    names.add(name)
print("4 TOML: PASS")
'@ | .\.venv\Scripts\python.exe -

git diff --check
```

이 검사는 정적 검증이며 실행 중 권한 분리를 증명하지 않는다.

### 안전한 권한 검증

게임 저장 영역 대신 검증자가 새로 만들고 소유한 폐기 가능한 공간을 사용한다. Scout/Reviewer의 실제 권한으로 무해한 파일 생성을 시도하고 Sandbox 또는 OS의 거부와 승인 요청 여부를 기록한다. 역할 지시에 따라 시도하지 않은 것만으로 강제 격리를 PASS로 판정하지 않는다.

쓰기가 성공하면 MA-07 FAIL이다. 검증자가 만든 파일과 디렉터리만 경로를 확인한 뒤 정리한다. 게임 Worktree·DB·다른 프로세스·사용자의 기존 파일에 시도하지 않는다. 실행 중 권한을 관측할 수 없고 안전한 시도도 불가능하면 NOT RUN/UNVERIFIED로 남긴다.

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
