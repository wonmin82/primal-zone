# Issue #50 통합 검증 추적

[v1.2 DESIGN FREEZE](https://github.com/wonmin82/primal-zone/issues/50)의 D01~D28 및 P-01/P-02를 유지한다. 이 PR은 **50-A만** 구현한다. 일반 PR CI는 test/smoke/browser-e2e/contracts이며 최종 RELEASE와 구분한다.

## 기준선 감사

착수 main: `7afc09d064ea0e45dc68f77ab7ede6c5e7237202`. #45/#50 OPEN, #46~#49/#54 CLOSED 및 아래 PR MERGED를 GitHub에서 재조회했다. 기존 기록을 새 실행으로 표현하지 않는다.

| 선행 | 최종 PR HEAD | Merge Commit | PR CI / 병합 main CI |
| --- | --- | --- | --- |
| #46 / #51 | `261cf95952ac409e2dcee97433d4b06b5793efb5` | `06c90ac92974dfcaf7ef6c2564ed9207e8dee8e8` | [성공](https://github.com/wonmin82/primal-zone/actions/runs/38045483861) / [성공](https://github.com/wonmin82/primal-zone/actions/runs/38046992168) |
| #47 / #52 | `37b70f22b4cc73a42d9aac8330c7cfc7b9f27b6b` | `49669e24ebccfc7d876a6027e175a2e4e3d85382` | [성공](https://github.com/wonmin82/primal-zone/actions/runs/38093587658) / [성공](https://github.com/wonmin82/primal-zone/actions/runs/38094190782) |
| #48 / #53 | `119272247d2e0e4936d447a9c5554e562fcd74d9` | `f48a632a1dd6a56b283f3864d6a4ace7e0f3b355` | [성공](https://github.com/wonmin82/primal-zone/actions/runs/38111536068) / [성공](https://github.com/wonmin82/primal-zone/actions/runs/38112582794) |
| #54 / #55 | `d68995287a1d6b10753a06a4aa06f487c074cbb3` | `bd18e6ff4e9f1d2e345015eba805353be0e1cae1` | [성공](https://github.com/wonmin82/primal-zone/actions/runs/38114034353) / [성공](https://github.com/wonmin82/primal-zone/actions/runs/38115248134) |
| #49 / #56 | `c80a14ba0b2316901da1adae2e81cd3a0da7fba3` | `7afc09d064ea0e45dc68f77ab7ede6c5e7237202` | [성공](https://github.com/wonmin82/primal-zone/actions/runs/38134927725) / [성공](https://github.com/wonmin82/primal-zone/actions/runs/38146739731) |

선행 로컬 전체/Quick 결과와 실패 이력은 기존 `docs/playtest.md` 및 각 PR/Issue 검증 기록을 보존한다. #46의 당시 전체 검사와 이후 정확한 Push HEAD Quick/Smoke는 같은 종류의 검증으로 합산하지 않는다.

## 50-A 수용 테스트

실행: `npm run test:browser`. 실제 테스트 경로: `scripts/browser/phase50a.spec.cjs`의 아래 제목. 상태는 다음 실행 기록과 연결한다. CI 링크는 [Issue #50 Phase 50-A 진행 구역](https://github.com/wonmin82/primal-zone/issues/50)의 연결 PR에서 **실제 최신 SHA**로 갱신한다.

| 테스트 | Decision | 검증 Assertion | 후속 연결 |
| --- | --- | --- | --- |
| TEST-50A-01 | D06/D07/D12/D13 | Chromium HTTP 200, 실제 WS, 인증·초기 상태·이름·입력·차단 Console 오류 없음 | 50-C / T50-WEB |
| TEST-50A-02 | D03/D11 | 점수 Enter 실제 전송 1회, 서버 sheet·상태·새 Prompt | 50-B/C / CMD·WEB |
| TEST-50A-03 | D10/D12 | 서로 다른 Account/Context/WS, 실제 Puppet 각 1, 이름 혼동 없음 | 50-D |
| TEST-50A-04 | D10/D11 | 같은 방 공개 원문 동일, 두 화면 각 1회, HTML 문자열 비실행 | 50-C/D / MSG |
| TEST-50A-05 | D10/D12 | 실제 종료·재연결·재인증, Puppet 1→0→1, 새 ID | 50-D / DATA |
| TEST-50A-06 | D08/D09/D11/P-01 | 두 Viewport, 가로 overflow 없음, 입력/출력·접근 가능한 버튼·PNG | 50-C |

Runner 회귀: `scripts/tests/test_browser_runner.py`의 비밀번호 제거, 외부 DB 거절, 실제 SQLite 읽기 전용 세션 조회 3개. Node 계약은 기존 `scripts/tests/test_web_prompt.cjs` 16개를 유지한다. 기존 Harness 회귀는 `world.test_smoke` 및 `tests.test_smoke_infrastructure` 18개다.

### 실행 증거와 제출 Gate

2026-10-12 Windows 실행 HEAD는 `7afc09d064ea0e45dc68f77ab7ede6c5e7237202` + 미커밋 인프라였으며 이후 코드 커밋 `f63a12756346aae5dc841b208bacc3113267436d`와 실행 코드가 동일하다. 이를 커밋 후 새 실행으로 표현하지 않는다. 이후 변경은 문서이며 동일 브라우저 회귀를 반복하지 않는다. 최종 Push HEAD의 Quick/Smoke 및 원격 네 Job은 연결 PR/Issue에 실제 SHA와 URL로 별도 확정한다.

| 테스트 | 상태 | 실제 시간 | 근거 |
| --- | --- | --- | --- |
| TEST-50A-01 | PASS | 3.972초 | 실제 Chromium 156.0.8078.4 인증·초기 상태 |
| TEST-50A-02 | PASS | 3.481초 | 점수 1회 전송·새 Prompt·서버 sheet |
| TEST-50A-03 | PASS | 8.063초 | 서로 다른 두 Account/Context/WS·Puppet 각 1 |
| TEST-50A-04 | PASS | 8.269초 | 두 세션 동일 공개 원문·각 1회·HTML 비실행 |
| TEST-50A-05 | PASS | 8.477초 | Puppet 1→0→1·새 세션 ID |
| TEST-50A-06 | PASS | 7.708초 | 두 Viewport·입력/버튼/overflow·리뷰용 PNG |

로컬 `run-8m2ki8dx/results.json` 및 `run.json`: 6개 성공, 건너뜀/예상치 못한 실패/Flaky 0, Playwright 41.921초 / 준비·종료 포함 89.154초, 플레이 DB 불변·소유 프로세스 종료. 이 ignored 증거 경로는 영구 배포물이 아니며 최종 CI Artifact가 원격 증거다. [실패 이력](playtest.md#issue-50-phase-50-a)을 함께 보존한다.

| Gate | 로컬 근거 / 제출 확인 |
| --- | --- |
| A-01~02 | 최신 main·선행 5개 PR/CI 감사, 기존 Harness 재사용, 게임 파일 diff 없음 |
| A-03~07 | TEST-50A-01/02 실제 서버·Chromium·HTTP/WS·UI 인증·명령·Prompt PASS |
| A-08~10 | TEST-50A-03/04/05 독립 두 플레이어·공개 메시지·재접속 PASS |
| A-11~13 | TEST-50A-06 두 Viewport·PNG 및 실패 결과/로그 수집 PASS. 이미지 승인 미실행 |
| A-14~15 | DB hash/mtime/size 불변, 서버 종료, 기존 Node 16개/Python 18개 및 신규 격리 3개 PASS |
| A-16~17 | 이 문서 작성 시 NOT RUN. 최종 Push HEAD Quick 및 최신 원격 test/smoke/browser-e2e/contracts 결과는 PR/Issue에서 확정 |
| A-18~19 | 매트릭스·브라우저·성능·실행/실패 기록 작성, 50-B~F NOT RUN |
| A-20 | 이 문서 작성 시 PR 제출 전. 실제 Ready PR 링크는 Issue #50 진행 구역에 추가 |

## PR #57 리뷰 보완

마지막 리뷰 HEAD `7ddf8d5de5d2437de14d06f91a4cc38c5e1fda22`의 P2-01~03을 테스트 인프라에서 보완했다. 위 최초 제출·당시 NOT RUN 기록은 보존한다. 아래 실행은 해당 HEAD + 수정 diff 기준이며 코드 커밋 `b0fd1b2a4fe776d6d173793854eddc54ac352f42`와 연결한다. 커밋 이후 새 실행으로 표현하지 않는다. 정확한 최종 Push HEAD Quick/Smoke와 최신 원격 네 Job은 [PR #57 Review Fixes](https://github.com/wonmin82/primal-zone/pull/57) 및 Issue #50 진행 기록에서 실제 SHA·Run URL로 확정한다.

| 리뷰 ID | 원인 | 수정 파일 | 신규·보강 회귀 | 결과 |
| --- | --- | --- | --- | --- |
| P2-01 | Popen 이전 인증 파일 정리 영역 부족 | scripts/browser_e2e.py | BrowserCredentialTests의 Popen/OSError·비정상 종료·정상 완료·stop/unlink 오류·Timeout/취소 | PASS |
| P2-02 | lastCommand·오류 context·임의 보고서/로그에 입력 원문 복제 가능 | fixtures/safety/reporter.cjs, browser_e2e.py | TEST-P2-02-A~D, BrowserIsolationTests의 엄격한 export·마스킹 PNG digest, 삭제 실패 회귀 | PASS |
| P2-03 | Context 종료 후 실제 Puppet 해제 확인 없음 | fixtures/safety.cjs, phase50a.spec.cjs | TEST-50A-03/05/06·TEST-P2-03-D·helper 소유 ID/타 세션/첨부 실패 검사 | PASS |

실제 경로는 `scripts/browser/`, `scripts/tests/test_browser_runner.py`, `scripts/tests/test_browser_helpers.cjs`다. 기존 TEST-50A-01~06·Node 16개·Python 격리 3개를 유지했다. 신규 메서드/테스트는 Python 9개 + Node 10개 + 실제 E2E 3개다. Mock은 외부 프로세스 실패·첨부·Probe 오류 주입에만 사용하며 실제 정상 서버/로그인/게임 명령/Puppet 관측은 대체하지 않는다.

| 수용 기준 | 실제 근거 | 상태 |
| --- | --- | --- |
| RF-01~03 | Python 12개: Popen 실패에서도 파일 삭제, 원래 오류+정리 오류 보존, 비정상 종료/Timeout/Interrupt | PASS |
| RF-04~07 | 개인·공개 원문 비수집, 비밀번호/토큰/URL 보호, 실제 음성 실패 보고서·자동 context 폐기·마스킹 PNG 검사 | PASS |
| RF-08~12 | 소유 Puppet ID 해제, A 종료/B 유지, Desktop 종료 후 Narrow, 1→0→1·새 ID, Probe/첨부/Timeout 오류 명시 | PASS |
| RF-13~15 | Runner 12·Node 26·기존 Harness 18, 정상 Chromium 9개 3회 연속 + 최종 보안 경계 재검사, DB/게임/Harness 불변 | PASS |
| RF-16~17 | 이 기록 커밋 시 정확한 최종 Push HEAD Quick/원격 CI는 실행 전이다. PR/Issue에서 최신 SHA의 실제 결과를 확정한다. | PENDING |
| RF-18~20 | 리뷰 추적/실행·실패 기록 보존, 코드 자체 리뷰에서 새 차단 P0/P1 없음, PR·Issue OPEN/Source 유지 | PR/Issue 갱신 후 최종 확인 |

3회 정상 브라우저 실행은 동일한 Fixture/시나리오를 사용했다. 이후 변화는 업로드 PNG 명명 규칙, 별도 음성 검사 선택 옵션, 자동 오류 context 비수집 및 보고서 정리 실패 판정이며 각 경계와 최종 정상 실행을 추가로 검사했다. 실패 재시도로 성공을 숨기거나 이전 HEAD CI를 새 HEAD 결과로 대신하지 않는다. 실행 시간·개발 중 실패는 [실행 이력](playtest.md#pr-57-p2-리뷰-보완)을 따른다.

## 후속 미실행 상태

| Phase / 검증 그룹 | 상태 | 남은 작업 |
| --- | --- | --- |
| 50-B / T50-CMD·ALIAS·GAME·NPC·MSG·PARTY·DOOR·HELP·DATA 전수 | NOT RUN | 현행 테스트 연결·공백 및 교차 계약 추가 |
| 50-C / E2E-01~14 및 T50-WEB 전수 | NOT RUN | 실제 역할별 기능·버튼·Focus·승인 이미지·접근성 확대 |
| 50-D / 전체 동시성·600초·60초·정상 서버 Restart | NOT RUN | 실제 시간·다중 세션·영속 비교 / RELEASE |
| 50-E / 기능 결함 Closeout | NOT RUN | 별도 재현·영향 평가·수정 PR 및 사용자 승인 |
| 50-F / 최종 main RELEASE·G-01~15·상위 #45 종료 | NOT RUN | 최종 병합 main 별도 검증·5개 산출물·승인 |
| OS 한국어 IME | PRIOR VERIFIED | 기존 사용자 Windows 수동 성공, 신규 PASS 합산 제외 |

50-A 성공을 Issue #50 전체 구현/통합 검증 완료로 해석하지 않는다. PR/Issue는 OPEN 유지하며 자동 Merge·브랜치 삭제·Close를 수행하지 않는다.


## P2-04 최종 프로세스 수명 보완

기준은 리뷰 HEAD `9651918018517527cdfa96fb694ab09bc66f298e`와 이 보완 diff다. 부모 종료 뒤에도 소유 자식을 정리하도록 `scripts/browser_processes.py`, `scripts/browser_e2e.py`, `scripts/tests/test_browser_runner.py`를 보완했다. 게임·Harness·WebSocket·운영 타이머 변경은 없다.

| 수용 기준 | 실제 회귀 경로 | 상태 |
| --- | --- | --- |
| TEST-P2-04-A / F-04 | test_p204_a_normal_parent_no_child_needs_no_forced_termination, 기존 정상 수령/인증 파일 정리 | Windows PASS |
| TEST-P2-04-B / F-01·05 | test_p204_b_abnormal_parent_leaves_real_child_then_cleanup_removes_it: 실제 부모 종료·자식 STILL_ACTIVE/그룹 잔류 → 실제 종료 | Windows PASS / Linux CI 확인 예정 |
| TEST-P2-04-C / F-06 | test_p204_c_live_parent_and_child_timeout_cleanup, test_p204_c_stubborn_child_requires_owned_forced_termination | Windows PASS / Linux CI 확인 예정 |
| TEST-P2-04-D / F-07 | test_p204_d_repeated_cleanup_is_safe | Windows PASS |
| TEST-P2-04-E / F-09 | test_p204_e_termination_error_is_reported_and_not_marked_stopped, 기존 원래 오류+stop/unlink 오류 보존 | Windows PASS |
| TEST-P2-04-F / F-08 | test_p204_f_non_owned_process_remains_alive | Windows PASS |
| 소유권·등록·최후 핸들 / F-02·03 | test_p204_launch_failure_still_cleans_ownership_container, test_p204_job_assignment_failure_never_creates_child, test_p204_windows_last_job_handle_close_kills_owned_child, test_p204_lost_posix_guardian_does_not_signal_unproven_group | Windows 해당 항목 PASS / POSIX 전용 CI 확인 예정 / macOS NOT RUN |
| TEST-P2-04-G / F-10~16 | 기존 Chromium 9개 및 P2-01~03, run.json의 브라우저·Evennia 각각 정리·자격 증명·DB 불변 | Windows 연속 3회 9개 PASS·각 정리 true (성능/실행 이력 참조) |
| F-17~24 | 정확한 Push HEAD Quick → 최신 PR 네 Job → Merge Commit → 실제 main 네 Job → 정확한 Source 정리 | 커밋 후 PR/Issue 실제 SHA·URL로 확정 |
| F-25~27 | Issue #50의 Phase 50-A 완료 기록, #50/#45 OPEN 유지, 50-B~F/RELEASE NOT RUN | 병합 후 Issue 기록에서 확정 |

Python Runner는 기존 12개를 유지하고 P2-04 메서드 11개를 추가해 총 23개다. Windows에서는 22개 성공·POSIX 전용 1개 제외, Linux에서는 Windows 전용 마지막 Job 핸들 항목 1개를 제외하고 나머지 22개를 실행한다. 플랫폼 제외를 실패 재시도나 flaky 은폐로 해석하지 않으며 macOS 실행 성공을 주장하지 않는다. Windows Job 등록 실패는 자식 생성 이전에 차단하고, POSIX 보호 프로세스 소실은 미확인 그룹에 신호를 보내지 않는다.

기존 P2-01~03·최초 제출 기록은 위에 보존한다. 이번 사용자 요청은 필수 검증 성공 후 조건부 Merge Commit 및 Source 삭제를 승인했지만, Issue #50 전체 종료나 50-B~F 완료는 승인/검증 범위가 아니다. 최종 병합/CI/정리 결과는 [PR #57](https://github.com/wonmin82/primal-zone/pull/57) 및 [Issue #50](https://github.com/wonmin82/primal-zone/issues/50)에 남긴다.

### P2-04 시작 실패 제어 파이프 회귀

최초 Ubuntu CI Runner FAIL을 [실행 이력](playtest.md#p2-04-최초-ubuntu-ci-실패-및-수정)에 연결한다. TEST-P2-04-E/F-09에 test_p204_closed_control_pipe_requires_verified_cleanup_proof를 추가해 정리 증거가 있을 때만 닫힌 파이프를 처리하고, 증거가 없으면 실패하는 것을 검증한다. 기존 실제 OS launch-failure 검사를 유지한다. Runner는 정의 24개/Windows 해당 23개 PASS·POSIX 1개 N/A, 새 Linux CI는 확인 전이다.


## Phase 50-B — 실제 계약 추적 (2026-10-12)

착수 Base `82641de0ea66898676b0b29194d7918489443def`, Source `codex/issue-50-integrated-qa`. Issue #50 v1.2 D01~D28/P-01/P-02는 변경하지 않는다. 아래 그룹 내부 번호는 동결된 그룹 요구를 구체적인 검증 책임에 연결하며 정책을 추가하지 않는다.

`scripts/issue50_contracts.py --labels`가 제공하는 70개 고유 실제 테스트를 `uv run python scripts/dev.py test <labels> --parallel 4`로 실행했다. **70 PASS / 186.579초**, 종료0. 신규 `IntegratedContractTests` 2개는 별도 직접 실행에서도 PASS / 28.887초(전체43.114초). 실행은 Base + 이번 50-B 코드/테스트 diff에서 수행했다. 이후 브라우저 테스트 인프라는 별도 단계이며 이번 실행을 새 커밋 이후 실행으로 표현하지 않는다.

정적 감사는 테스트 경로와 Assertion 연결만 확인하며 그 자체로 기능 PASS가 아니다. 아래 PASS는 실제 70개 테스트 실행 결과에 근거한다. 스키마/Legacy 롤백 위임 함수의 실제 Assertion도 확인했다. 모든 변경 명령의 6절 Help, 전체 Registry/Alias의 실제 `도움`/`도움말` dispatcher, 의료 Lv1/99/100/MAX·부족 금액 불변을 새로 보강했다. 첫 두 개발 실행은 무관한 기존 명령과 `휴식`까지 신규 6절 형식으로 잘못 분류하여 실패했다. 게임 출력/정책을 바꾸지 않고 #46~49의 명시적 신규/변경 명령 범위를 고정했다. 기존 Alias/dispatcher 전수 검사는 유지했다.

| T50 | 계약 | 실제 테스트 | 결과 |
| --- | --- | --- | --- |
| T50-CMD-01 | 전체 Command/Alias/실제 Help | [tests.test_issue50_contracts.IntegratedContractTests.test_all_registry_aliases_actual_help_dispatch_and_semantics](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_issue50_contracts.py#L18) | PASS |
| T50-CMD-02 | 제거 이름·인벤토리 Alias | [tests.test_vocabulary.VocabularyTests.test_inventory_aliases_and_removed_commands_are_not_active](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_vocabulary.py#L40) | PASS |
| T50-CMD-03 | 방향 및 시체 단축어 실제 이동/권리 | [tests.test_command_overhaul.CommandOverhaulSmoke.test_phase_a](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_command_overhaul.py#L33) | PASS |
| T50-CMD-04 | 이름·번호·모두·조사 | [tests.test_targets.TargetIntegrationTests.test_default_index_all_look_and_attack_ordering](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_targets.py#L133) | PASS |
| T50-CMD-05 | 실제 잠긴 CmdSet 개인 fallback 금지 | [tests.test_command_shortcuts.CommandShortcutsTests.test_locked_actual_commands_never_fall_back_to_personal](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_command_shortcuts.py#L728) | PASS |
| T50-CMD-06 | 묶음 이동 뒤 실제 CmdSet | [tests.test_command_shortcuts.CommandShortcutsTests.test_dynamic_room_cmdsets_override_snapshot_only_when_actually_selected](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_command_shortcuts.py#L710) | PASS |
| T50-ALIAS-01 | v11~v14 호환 및 읽기 전용 | [world.test_command_shortcuts.ShortcutMigrationV11Tests.test_every_supported_version_preserves_gameplay_and_only_safe_lists_convert](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/world/test_command_shortcuts.py#L134) | PASS |
| T50-ALIAS-02 | 예약 충돌·원본 보존 | [tests.test_command_overhaul.CommandOverhaulSmoke.test_phase_a](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_command_overhaul.py#L33) | PASS |
| T50-ALIAS-03 | 변수 $1~9/$*/$$ | [world.test_command_shortcuts.CommandShortcutRulesTests.test_variable_binding_and_single_pass_literals](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/world/test_command_shortcuts.py#L51) | PASS |
| T50-ALIAS-04 | 깊이5/6 실제 선택 | [tests.test_command_shortcuts.CommandShortcutsTests.test_depth_five_and_six_are_checked_on_actual_selected_path](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_command_shortcuts.py#L799) | PASS |
| T50-ALIAS-05 | 하위10/11 | [tests.test_command_shortcuts.CommandShortcutsTests.test_attempts_include_every_leaf_and_stop_before_eleventh](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_command_shortcuts.py#L809) | PASS |
| T50-ALIAS-06 | 1000자·부분 실행 | [tests.test_command_shortcuts.CommandShortcutsTests.test_final_character_sum_and_direct_bundle_input_length_boundaries](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_command_shortcuts.py#L827) | PASS |
| T50-ALIAS-07 | 전체 삭제 직접 2단계·간접 금지 | [tests.test_command_shortcuts.CommandShortcutsTests.test_sequence_cannot_request_and_confirm_all_deletion](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_command_shortcuts.py#L417) | PASS |
| T50-GAME-01 | Native 정보 불변 | [tests.test_command_overhaul.CommandOverhaulSmoke.test_phase_b](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_command_overhaul.py#L110) | PASS |
| T50-GAME-02 | 장비·UUID·웹 | [tests.test_equipment_entities.EquipmentEntityTests.test_command_selector_and_presentation_agree_with_web](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_equipment_entities.py#L262) | PASS |
| T50-GAME-03 | 탄창·잔탄·소유 권리 | [tests.test_firearms.FirearmTests.test_reload_empty_missing_incompatible_foreign_and_explicit](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_firearms.py#L110) | PASS |
| T50-GAME-04 | 열쇠 정보 읽기·Credential 별개 | [tests.test_doors.DoorKeyTests.test_information_inventory_and_credential_are_separate_read_only](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_doors.py#L847) | PASS |
| T50-GAME-05 | Lv1/99/100/MAX 정확 의료 산식 | [tests.test_issue50_contracts.IntegratedContractTests.test_medical_level_boundaries_exact_formula_and_failure_invariance](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_issue50_contracts.py#L58) | PASS |
| T50-GAME-06 | 회복 저장 실패 rollback | [tests.test_command_overhaul.CommandOverhaulSmoke.test_phase_c](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_command_overhaul.py#L210) | PASS |
| T50-GAME-07 | 무료 침대 실제 정책 | [tests.test_doors.DoorTest.test_recovery_room_both_sides_free_reopen_and_original_bed](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_doors.py#L708) | PASS |
| T50-GAME-08 | 쏴 즉시 타격 없음 | [tests.test_command_overhaul.CommandOverhaulSmoke.test_phase_a](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_command_overhaul.py#L33) | PASS |
| T50-GAME-09 | 실제 총기 전투·탄약 rollback | [tests.test_firearms.FirearmTests.test_live_enemy_path_commits_shot_and_rolls_back_ammo_failure](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_firearms.py#L346) | PASS |
| T50-NPC-01 | 22 NPC 실제 객체·조회 불변 | [tests.test_npc_dialogue.NPCDialogueTests.test_content_22_discovery_and_no_legacy_action](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_npc_dialogue.py#L428) | PASS |
| T50-NPC-02 | 말/작은따옴표 원문 | [tests.test_npc_dialogue.NPCDialogueTests.test_say_quote_equivalence_and_original](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_npc_dialogue.py#L213) | PASS |
| T50-NPC-03 | NPC 대상 모호성/번호 | [tests.test_npc_dialogue.NPCDialogueTests.test_fallback_ambiguity_and_numbers](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_npc_dialogue.py#L229) | PASS |
| T50-NPC-04 | 공개 같은 원문·개인 강조 | [tests.test_npc_dialogue.NPCDialogueTests.test_public_same_raw_independent_highlights_and_context](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_npc_dialogue.py#L278) | PASS |
| T50-NPC-05 | 개인 활성 키워드 | [tests.test_npc_dialogue.NPCDialogueTests.test_personal_guides_semantics_keep_plain_text_and_separate_chat](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_npc_dialogue.py#L313) | PASS |
| T50-NPC-06 | 실제 임무·보상 rollback | [tests.test_npc_dialogue.NPCDialogueTests.test_exact_transitions_private_reward_and_rollback](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_npc_dialogue.py#L340) | PASS |
| T50-NPC-07 | 실제 버튼 토큰·중복 지급 | [tests.test_npc_dialogue.NPCDialogueTests.test_stale_action_tokens_cannot_report_twice_before_commit](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_npc_dialogue.py#L384) | PASS |
| T50-NPC-08 | 세션·소유권·조회 토큰 | [tests.test_npc_dialogue.NPCDialogueTests.test_structured_input_checks_puppet_and_readonly_tokens](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_npc_dialogue.py#L470) | PASS |
| T50-MSG-01 | 개인/답장/공개와 최근상대 | [tests.test_private_messaging.PrivateMessagingTests.test_private_accept_reply_and_public_does_not_change_peer](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_private_messaging.py#L24) | PASS |
| T50-MSG-02 | 오프라인/차단 영속·실패불변 | [tests.test_private_messaging.PrivateMessagingTests.test_offline_block_persistent_and_failed_send_unchanged](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_private_messaging.py#L45) | PASS |
| T50-MSG-03 | 300자/ANSI/제어/동명이인 | [tests.test_private_messaging.PrivateMessagingTests.test_input_offline_ambiguity_and_limits](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_private_messaging.py#L60) | PASS |
| T50-MSG-04 | 실패 전송 부재·rollback | [tests.test_private_messaging.PrivateMessagingTests.test_transaction_failure_sends_nothing](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_private_messaging.py#L81) | PASS |
| T50-MSG-05 | CmdSet page/whisper 우회 금지 | [tests.test_private_messaging.PrivateMessagingTests.test_actual_cmdset_no_page_alias_and_help_dispatch](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_private_messaging.py#L90) | PASS |
| T50-MSG-06 | 일행대화와 제삼자/다른방 | [tests.test_party_overhaul.PartyChatTests.test_rt28_rt29_private_members_cross_rooms_and_validation](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_party_overhaul.py#L560) | PASS |
| T50-PARTY-01 | 16개 정식 명령·Alias·Help | [tests.test_party_overhaul.PartyCommandContractTests.test_rt01_all_sixteen_commands_aliases_help_and_old_verbs_absent](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_party_overhaul.py#L23) | PASS |
| T50-PARTY-02 | 초청·요청60초 | [tests.test_party_overhaul.PartyMembershipTests.test_rt05_rt07_rt08_rt09_rt10_ttl_and_independent_requests](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_party_overhaul.py#L121) | PASS |
| T50-PARTY-03 | 4인 제한·재검증 | [tests.test_party_overhaul.PartyMembershipTests.test_rt04_rt07_capacity_rechecked_and_requests_single](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_party_overhaul.py#L154) | PASS |
| T50-PARTY-04 | 리더 위임·오프라인 초청 | [tests.test_party_overhaul.PartyMembershipTests.test_rt06_rt11_rt27_invite_survives_offline_and_transfer](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_party_overhaul.py#L143) | PASS |
| T50-PARTY-05 | 마지막 Puppet·다중세션·즉시승계 | [tests.test_party_overhaul.PartySuccessionTests.test_rt23_reload_multisession_and_unpuppet_event](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_party_overhaul.py#L663) | PASS |
| T50-PARTY-06 | 600초 정확 tick·오래된 요청 | [tests.test_party_overhaul.PartySuccessionTests.test_rt19_rt20_rt25_tick_boundary_order_and_stale_recheck](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_party_overhaul.py#L632) | PASS |
| T50-PARTY-07 | 해체확인 snapshot·만료 | [tests.test_party_overhaul.PartyMembershipTests.test_rt13_rt14_dissolve_snapshot_ttl_and_stale_target](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_party_overhaul.py#L173) | PASS |
| T50-PARTY-08 | 일행 비공개 재검증 | [tests.test_party_overhaul.PartyChatTests.test_rt30_delivery_rechecks_departed_recipient_and_sender](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_party_overhaul.py#L580) | PASS |
| T50-PARTY-09 | 공동 공격 기존 예약 유지 | [tests.test_party_overhaul.PartyAttackTests.test_rt31_rt32_rt34_partial_attack_preserves_existing_schedule](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_party_overhaul.py#L759) | PASS |
| T50-PARTY-10 | 영속 방어·실제 tick | [tests.test_party_overhaul.PartyDefenseTests.test_rt38_enemy_tick_redirects_without_threat_damage_or_interval_change](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_party_overhaul.py#L845) | PASS |
| T50-PARTY-11 | Native/Legacy 해체후 실지급 | [tests.test_party_overhaul.PartyLootRightsTests.test_rt15_rt16_native_item_actual_pickup_after_dissolve_and_rollback](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_party_overhaul.py#L345) | PASS |
| T50-PARTY-12 | 다수 개인 화폐 및 postcommit | [tests.test_loot_entities.NativeLootNotificationTests.test_test05_test07_native_nested_multiple_recipients_commit_once](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_loot_entities.py#L461) | PASS |
| T50-DOOR-01 | 첫 설치·양방향 PK/SSOT | [tests.test_doors.DoorTest.test_single_state_fixed_contents_and_real_exit_pk](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_doors.py#L40) | PASS |
| T50-DOOR-02 | 열쇠·래치·잠금불가 상태전이 | [tests.test_doors.DoorTest.test_all_state_transitions_key_latch_and_nonlockable](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_doors.py#L392) | PASS |
| T50-DOOR-03 | 열쇠 발급/재발급/개인 유일성 | [tests.test_doors.DoorKeyTests.test_actual_cabinet_free_issue_duplicate_reissue_and_per_owner](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_doors.py#L795) | PASS |
| T50-DOOR-04 | 열쇠 금지 하위API | [tests.test_doors.DoorKeyTests.test_every_operation_blocked_at_actual_api_and_state_preserved](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_doors.py#L821) | PASS |
| T50-DOOR-05 | 59.999/60 만료 조회 불변 | [tests.test_doors.DoorTest.test_logical_expiry_readonly_boundary_and_sweep](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_doors.py#L447) | PASS |
| T50-DOOR-06 | 실제 통과 완료기준 연장 | [tests.test_doors.DoorTest.test_real_traversal_extends_at_completion_and_consecutive_crossings](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_doors.py#L457) | PASS |
| T50-DOOR-07 | 실패통과 위치/알림rollback | [tests.test_doors.DoorTest.test_traversal_expiry_at_completion_rolls_back_location_visited_and_messages](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_doors.py#L508) | PASS |
| T50-DOOR-08 | 실시간 정보보호 모든경로 | [tests.test_doors.DoorTest.test_closed_locked_expired_corrupt_block_all_live_observation_paths](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_doors.py#L589) | PASS |
| T50-DOOR-09 | 나침반/지도 공개 불변 | [tests.test_doors.DoorTest.test_visited_map_is_structural_unchanged_across_door_states](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_doors.py#L659) | PASS |
| T50-DOOR-10 | D13 장애 국소·정상 Door/Exit | [tests.test_doors.DoorTest.test_p1_01_installed_typeclass_damage_is_local_after_bootstrap](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_doors.py#L133) | PASS |
| T50-HELP-01 | 전수 실제 alias Help dispatcher | [tests.test_issue50_contracts.IntegratedContractTests.test_all_registry_aliases_actual_help_dispatch_and_semantics](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_issue50_contracts.py#L18) | PASS |
| T50-HELP-02 | 줄임말 6절·Semantic Text | [tests.test_shortcut_help.ShortcutHelpTests.test_four_pages_have_same_sections_order_semantics_and_no_double_frame](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_shortcut_help.py#L31) | PASS |
| T50-HELP-03 | 변수/한도/우선순위 안내 | [tests.test_shortcut_help.ShortcutHelpTests.test_personal_help_contains_management_variables_limits_and_priority](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_shortcut_help.py#L55) | PASS |
| T50-HELP-04 | 전역/개인 삭제 정책 안내 | [tests.test_shortcut_help.ShortcutHelpTests.test_deletion_and_global_help_do_not_confuse_personal_and_system](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_shortcut_help.py#L65) | PASS |
| T50-HELP-05 | Registry로부터 생성·관련 Help | [tests.test_text.SemanticTextTests.test_help_uses_registry_not_a_separate_command_list](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_text.py#L135) | PASS |
| T50-HELP-06 | 웹/실제 객체·권한 | [tests.test_doors.DoorTest.test_web_existing_interactables_protocol_stale_buttons_and_expired_state](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_doors.py#L678) | PASS |
| T50-HELP-07 | 사용법 역할은 실제metadata | [tests.test_text.SemanticTextTests.test_usage_styles_only_declared_action_metadata](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_text.py#L264) | PASS |
| T50-DATA-01 | Fresh DB·기존 스키마 설치 | [tests.test_door_schema.DoorSchemaTests.test_existing_schema_preserves_profile_native_items_and_all_old_rows](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_door_schema.py#L187) | PASS |
| T50-DATA-02 | v11~14 전체 프로필 보존 | [world.test_command_shortcuts.ShortcutMigrationV11Tests.test_every_supported_version_preserves_gameplay_and_only_safe_lists_convert](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/world/test_command_shortcuts.py#L134) | PASS |
| T50-DATA-03 | Item UUID/양/sequence | [tests.test_item_entities.ItemEntityTests.test_creation_persists_opaque_identity_and_definition_state](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_item_entities.py#L63) | PASS |
| T50-DATA-04 | 중첩 전리품 상위rollback | [tests.test_loot.LootNotificationTests.test_test01_legacy_item_outer_rollback_has_no_success_effects](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_loot.py#L247) | PASS |
| T50-DATA-05 | Native 저장/Claim/화폐 상위rollback | [tests.test_loot_entities.NativeLootNotificationTests.test_test03_native_common_command_outer_rollback_preserves_all_assets](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_loot_entities.py#L446) | PASS |
| T50-DATA-06 | Savepoint 콜백 폐기 | [tests.test_loot_entities.NativeLootNotificationTests.test_test06_native_failed_savepoint_has_no_callbacks_after_outer_success](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_loot_entities.py#L486) | PASS |
| T50-DATA-07 | 네트워크 오류 뒤 Commit 유지 | [tests.test_doors.DoorTest.test_postcommit_push_failure_does_not_undo_state_or_move](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_doors.py#L694) | PASS |
| T50-DATA-08 | Door 손상/설치이력·독립 새프로세스 | [tests.test_door_schema.DoorSchemaTests.test_p1_08_damaged_door_survives_new_process_server_start](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_door_schema.py#L190) | PASS |
| T50-DATA-09 | 세계 Bootstrap DB/캐시 원자성 | [tests.test_doors.DoorTest.test_bootstrap_failure_rolls_back_database_and_evennia_cache](https://github.com/wonmin82/primal-zone/blob/46b1903c4ca46fe2af881e61963407a4677d2b9a/game/tests/test_doors.py#L313) | PASS |

T50-WEB-01~12, E2E-01~14 전체, 정상 재시작, Wall Clock 60/600초 및 최종 main RELEASE는 후속 단계다. 일부 Chromium 개발 성공을 전체 완료로 합산하지 않는다. 전체 Python 회귀 G-04, 최종 main CI/RELEASE G-14는 아직 NOT RUN이다. OS IME PRIOR VERIFIED, Visual Baseline PENDING REVIEW 유지.


## 50-C~E 및 50-F 준비 — Pre-merge 제출 근거

Base `82641de0ea66898676b0b29194d7918489443def`, Source `codex/issue-50-integrated-qa`.
현재 구현 코드 `45d1a27a388e483e72913743c978e583b952510b`. 코드/테스트 실행은 단계 커밋 + 해당 개발 diff에서 수행했고, 이후 구현과 일치함을 검토했다. 정확한 최종 문서 포함 HEAD의 Quick/PR CI는 PR/Issue #50 기록으로 확정한다.

- 명령 metadata86개(내부 nomatch 포함)·Alias75개·입력 방식 고정. 실제 Help/Alias·관련 페이지·docs 명시 표·의료 경계 신규3개 PASS.
- 순수229 PASS/3.139초, 통합814 PASS/659.195초(전체671.907초). 최초814 중1 신규 Alias 순서 FAIL은 원인 수정/재검증 이력으로 보존한다.
- 기존 Runner 정의24 중 Windows23 PASS/POSIX1 N/A(5.060초), 새6 PASS(1.068초), Harness18 PASS(10.930초), Node28 PASS(0.182초). 전체와 직접 영향 부분집합을 합산하지 않는다.
- 실제50-A9개 및 E2E-01~14 PASS. 다음 표는 각 직접 영향 개발 성공 실행이며 같은 단독 전체 실행이나 최종 PR HEAD CI로 오인하지 않는다. Shadow 입력/프로토콜/서비스 Mock 없음, retries0.

| E2E | 결과 | 준비~정리 실제 시간 | 안전한 로컬 실행 증거 |
| --- | --- | --- | --- |
| E2E-01 | PASS | 83.015초 | `run-oskmcnn3`의 results/run.json |
| E2E-02 | PASS | 152.005초 | `run-28dd70c6`의 results/run.json |
| E2E-03 | PASS | 92.905초 | `run-pnflmmf2`의 results/run.json |
| E2E-04 | PASS | 148.089초 | `run-e1dm0wvg`의 results/run.json |
| E2E-05 | PASS | 144.714초 | `run-otmfwrrq`의 results/run.json |
| E2E-06 | PASS | 142.665초 | `run-1trkhh5t`의 results/run.json |
| E2E-07 | PASS | 121.022초 | `run-5mqvw0ax`의 results/run.json |
| E2E-08 | PASS | 170.889초 | `run-bq7zp46e`의 results/run.json |
| E2E-09 | PASS | 133.066초 | `run-tosc7219`의 results/run.json |
| E2E-10 | PASS | 70.517초 | `run-3ousjgxx`의 results/run.json |
| E2E-11 | PASS | 131.311초 | `run-56_at7vd`의 results/run.json |
| E2E-12 | PASS | 128.467초 | `run-nswdx25l`의 results/run.json |
| E2E-13 | PASS | 75.318초 | `run-e1nvp6vj`의 results/run.json |
| E2E-14 | PASS | 112.447초 | `run-s2km6s2v`의 results/run.json |

모든 위 실행은 Context/소유 Puppet·Node/Chromium/Evennia 종료·인증 파일 삭제·실제 플레이 DB 불변을 확인했다. Root Probe를 초기화 전 DB 소유 경계와 query_only로 보강한 뒤 실제 E2E-13(75.318초) 및 외부 DB 거절 음성 회귀를 확인했다. Console 차단 오류는 원문 없이 실패하며 정리는 계속한다. 신규 Metadata/Console 정리 경계는 Node 회귀와 기존 관측의 오류0을 근거로 검토했다.

### T50-WEB-01~12

| ID | 실제 검증 책임/위치 | 현재 결과 |
| --- | --- | --- |
| T50-WEB-01 |50-A01/03·모든 actors.create 실제 HTTP/WS/인증 | PASS (로컬), PR CI PENDING |
| T50-WEB-02 | Player.command·E2E01/14 정확한 Enter/단일 전송 | PASS (로컬), PR CI PENDING |
| T50-WEB-03 | E2E14 History/Backspace/실제 clipboard paste | PASS (로컬), PR CI PENDING |
| T50-WEB-04 | E2E02 실제 NPC 키보드/클릭·E2E04 이동 버튼·Node Actions | PASS (로컬), PR CI PENDING |
| T50-WEB-05 | E2E06/08/14 Prompt·실제 WS 최신 상태 | PASS (로컬), PR CI PENDING |
| T50-WEB-06 |50-A06/E2E14 Desktop1366×768 | PASS (객관적 DOM), 이미지 PENDING REVIEW |
| T50-WEB-07 |50-A06/E2E14 Narrow390×844·overflow/viewport | PASS (객관적 DOM), 이미지 PENDING REVIEW |
| T50-WEB-08 | E2E02/14 Focus/접근 이름/Enter/hit-test | PASS (로컬), PR CI PENDING |
| T50-WEB-09 | E2E02 NPC 키워드·보상/재발급, 실제 역할별 NPC | PASS (로컬), PR CI PENDING |
| T50-WEB-10 | E2E05/06/07/08/11 실제2~3계정/Context/수신 범위 | PASS (로컬), PR CI PENDING |
| T50-WEB-11 | E2E14 HTML/Semantic Text·Console 강제 실패·Node28 | PASS (로컬), PR CI PENDING |
| T50-WEB-12 | E2E11/12 재접속/Puppet·P2 회귀·엄격 export | PASS (로컬), PR CI PENDING |

### Decision·원칙 적용

| Decision | 실제 근거/상태 |
| --- | --- |
| D01 | T50 계약74+WEB12, 기존 변경 범위 실제70/전체814 및 Chromium14 연결 |
| D02 | 실제 E2E01~14 로컬 PASS, 최신 PR CI는 PENDING |
| D03 | Registry86 metadata·Alias75·Help/문서 전수, 실제 대표 흐름 |
| D04 |22 NPC/16 일행 Python 전수·훈련/정산/임무/상인/의료/길잡이 실제 브라우저 |
| D05 | v11~14·Native/Legacy·권리·Quest·Credential·Door/Exit 검증 |
| D06 | 실제 Playwright Chromium, Firefox/WebKit 비필수 |
| D07 | 기존 Ubuntu PR/RELEASE CI, Windows 로컬 실제 검증. macOS 미지원/NOT RUN |
| D08 |1366×768/390×844 실제 수용 |
| D09 | 객관적 DOM/접근성, 최초 Visual Baseline PENDING REVIEW |
| D10 | 독립2~3 Account/Context/WS, 다른 세션 보호 |
| D11 | Focus/비색상/Semantic/HTML/수신 범위 실제/Node 검증 |
| D12 | 각 Job/시나리오 새 Harness DB·동적 포트·소유 정리 |
| D13 | 일반3개 계정 fixture, 공개 가입/610초 대기 없음 |
| D14 | PR599.999/600 서비스 경계 PASS. 실제60/600 RELEASE NOT RUN |
| D15 | 운영 상수 불변, RELEASE timing과 다른 Job 병렬 |
| D16 | 실제 정상 Portal/Server stop·동일 DB·재인증 PASS. crash 비범위 |
| D17 | Fresh/Legacy/Corrupt·Rollback·Fail-closed 실제 Python/DB/브라우저 |
| D18 | QUICK/PR/RELEASE 진입점 분리 |
| D19 | test/smoke/browser-e2e/contracts 유지·확장. 최신 원격 결과 PENDING |
| D20 | main SHA/ref/event/input/checkout guard·독립 dispatch 준비, 실제 RELEASE NOT RUN |
| D21 | 실제 개발 실측 보존, 최종 CI/RELEASE 시간은 실행 후 확정 |
| D22 | 개발 FAIL과 수정 원인 보존, retries0·skip/flaky 은폐 없음 |
| D23 | 새 미해결 P0/P1 없음. 비차단 favicon P2는 [#59](https://github.com/wonmin82/primal-zone/issues/59) 이관 |
| D24 | 로컬 PASS와 CI PENDING/RELEASE NOT RUN 구분, IME PRIOR VERIFIED |
| D25 | QA만 변경, 별도 게임 기능 수정/무승인 Merge 없음 |
| D26 | 필수5문서 준비 완료, 최종 main Closeout은 후속 |
| D27 | 입력/인증/DB/Trace/Video 비수집·엄격 export·성공14일/실패30일 |
| D28 | Issue50/45 OPEN, 최종 리뷰/병합/RELEASE/Closeout 승인 대기 |
| P-01 | 시각 품질 자동 승인 없음 |
| P-02 | 개발/실패 수정 시간과 성공1회 시간 예산 구분 |

### 선행 Merge/CI 감사

GitHub에서 PR51/52/53/55/56 MERGED와 각 실제 Merge SHA의 push test/smoke SUCCESS를 새로 확인했다. PR57은 main82641de의 네 Job SUCCESS이며 이번 신규 HEAD의 CI로 재사용하지 않는다.

| 선행 PR | Merge SHA | 실제 main CI |
| --- | --- | --- |
|51 |06c90ac92974dfcaf7ef6c2564ed9207e8dee8e8 |[38046992168](https://github.com/wonmin82/primal-zone/actions/runs/38046992168) |
|52 |49669e24ebccfc7d876a6027e175a2e4e3d85382 |[38094190782](https://github.com/wonmin82/primal-zone/actions/runs/38094190782) |
|53 |f48a632a1dd6a56b283f3864d6a4ace7e0f3b355 |[38112582794](https://github.com/wonmin82/primal-zone/actions/runs/38112582794) |
|55 |bd18e6ff4e9f1d2e345015eba805353be0e1cae1 |[38115248134](https://github.com/wonmin82/primal-zone/actions/runs/38115248134) |
|56 |7afc09d064ea0e45dc68f77ab7ede6c5e7237202 |[38146739731](https://github.com/wonmin82/primal-zone/actions/runs/38146739731) |
|57 |82641de0ea66898676b0b29194d7918489443def |[38188294387](https://github.com/wonmin82/primal-zone/actions/runs/38188294387) |

G-01~15의 현재 판정은 [Pre-merge 최종 문서](issue50-final-validation.md)에 있다. 실제60/600·Full·최종main CI/RELEASE·Issue Closeout은 NOT RUN이다.
