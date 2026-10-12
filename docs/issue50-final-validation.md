# Issue #50 최종 검증 및 Closeout 기록

## 2026-10-12 최초 성공 RELEASE 및 최종 Closeout 준비

[PR #60](https://github.com/wonmin82/primal-zone/pull/60)은 Merge Commit `855ada380e5276334f0744797a86a5aef300297c`으로 병합됐다. 첫 부모는 `82641de0ea66898676b0b29194d7918489443def`, 둘째 부모는 검토 Source `26da18221f890f3405aca84b746741e3da7f747b`이며 임시 병합 결과와 Tree가 같고 원본 이력이 보존됐다. [당시 main CI](https://github.com/wonmin82/primal-zone/actions/runs/38239786496)의 네 Job은 모두 SUCCESS다.

[최초 RELEASE 실패](https://github.com/wonmin82/primal-zone/actions/runs/38241057595)는 삭제하지 않는다. 8개 중 7개 Job은 SUCCESS였지만 Full Smoke가 60초 후 정상 닫힌 회복실 문을 열지 않고 이동해 실패했다. 이는 QA 이동 경로의 누락이며 게임의 차단은 정상이다. [최소 수정 PR #61](https://github.com/wonmin82/primal-zone/pull/61)의 `0a03b44612822796f703e4d077916330e909a4fb`는 실제 `회복실 문 열어`를 양쪽 이동 전에 실행한다. 정상·실패·비관련 출구 회귀3개를 추가했으며 게임 정책·타이머·프로토콜·저장 형식은 바꾸지 않았다. 수정 Merge는 `11a1c6bce91a5499292f8fbabff3e308663814fe`이고 부모는 `855ada380e5276334f0744797a86a5aef300297c`와 `0a03b44612822796f703e4d077916330e909a4fb`다.

**최초 성공 RELEASE SHA: `11a1c6bce91a5499292f8fbabff3e308663814fe`.** [main CI](https://github.com/wonmin82/primal-zone/actions/runs/38244636657) 네 Job SUCCESS, [RELEASE](https://github.com/wonmin82/primal-zone/actions/runs/38251167392) 8개 Job SUCCESS, main/workflow_dispatch/attempt1 및 입력·GITHUB_SHA·실제 Checkout SHA 일치를 모든 Job의 Guard8개로 확인했다. RELEASE 전체 병렬 경과는 819초다. Job 로그·Assertion 및 안전한 Artifact를 직접 검토했다. 아래 최초 실패/성공과 과거 로컬 검증을 서로 다른 실행으로 보존한다.

**최종 SHA Closeout은 아직 대기 중이다.** 이 문서 PR을 Merge Commit으로 병합한 뒤 새 `FINAL_MAIN_SHA`의 push CI 네 Job과 RELEASE8개 Job을 다시 실행한다. 같은 SHA의 성공으로 대체하지 않는다. 최종 실행 증거는 [Issue #50 공식 Final Closeout 기록](https://github.com/wonmin82/primal-zone/issues/50#issuecomment-6124806608)에 추가하고, 결과 때문에 새 Git Commit을 만들어 SHA를 다시 바꾸지 않는다. 최종 Gate를 확인한 뒤에만 #50·#45를 종료하고 병합된 작업 브랜치를 안전하게 정리한다.

### 최초 성공 RELEASE의 1차 Gate 감사

| Gate | 1차 감사 | 실제 근거와 최종 절차 | 실행 증거 |
| --- | --- | --- | --- |
| G-01 | PASS | 선행 PR51/52/53/55/56/57 Merge·main CI 및60/61 부모·Tree 감사 | [baseline](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817552240) |
| G-02 | PASS | T50-CMD/ALIAS·Registry86/Alias75·프로필v11~14·제한/권한 실제 회귀 | [test](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597631) |
| G-03 | PASS | 기능별 문서·Alias·Help6섹션·웹 Action 및 문서 오류 음성 계약 | [contracts](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597752) |
| G-04 | PASS | Python 순수232·Evennia 통합816 전체 | [test](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597631) |
| G-05 | PASS | 실제 E2E-01~14 전부 | [browser-e2e-full](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597895) |
| G-06 | PASS | Chromium 실제 UI/WS·50-A9+통합14 | [browser-e2e-full](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597895) |
| G-07 | PASS (객관적) | Desktop1366×768/Narrow390×844·Focus/이름/overflow/입력. 이미지 승인 별도 | [browser-e2e-full](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597895) |
| G-08 | PASS | 독립2~3 Account/Context/WS·수신자·실제 Puppet 해제 | [browser-e2e-full](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597895) |
| G-09 | PASS | 실제 Door60초·통과연장·중간/직전/최종 완료 창·만료후 차단 | [timing-e2e](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597684) |
| G-10 | PASS | 실제 마지막 Puppet 해제·600초·조기승계 없음·재접속/권리 보존 | [timing-e2e](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597684) |
| G-11 | PASS | 동일DB 정상 Restart·실제 Exit PK/위치/목적지/Typeclass·설치·Rollback | [persistence-e2e](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597853) |
| G-12 | PASS | 실제 Quick 및 production Full Gameplay Smoke | [smoke-full](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597957) |
| G-13 | PASS | 차단 P0/P1 없음·최초 Full 실패 최소 수정61. 기존P2#59 추적 | [test](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597631) |
| G-14 | 최종 NOT RUN | 최초 성공 SHA의 CI/RELEASE는 PASS. 문서 Merge 후 새 최종 SHA CI/RELEASE 필요 | [baseline](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817552240) |
| G-15 | 최종 대기 | 필수5문서 작성. 최종 공식 댓글·Issue/브랜치 정리 이후 확정 | [baseline](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817552240) |

| Job | 실제 결과 | 경과 시간 | 실행 증거 |
| --- | --- | --- | --- |
| baseline | SUCCESS | 5초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817552240) |
| test | SUCCESS | 426초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597631) |
| timing-e2e | SUCCESS | 808초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597684) |
| contracts | SUCCESS | 13초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597752) |
| smoke | SUCCESS | 74초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597770) |
| persistence-e2e | SUCCESS | 132초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597853) |
| browser-e2e-full | SUCCESS | 718초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597895) |
| smoke-full | SUCCESS | 514초 | [Job](https://github.com/wonmin82/primal-zone/actions/runs/38251167392/job/114817597957) |

### 실제 시간과 정상 재시작

- TEST-TIMING-DOOR **PASS/100.737초**: 실제 열기/양방향OPEN·통과 완료 기준+60초·중복 열기/실패 통과 예약 불변·중간 관측·만료4초 전 이후 최대500ms 목표 반복·최종 `deadline-1.0 <= end <= deadline-0.5` 완료·만료후 실제 이동 거절·정상 Tick CLOSED·웹 양쪽 동기화. 단위 Clock 주입으로 대체하지 않았다.
- TEST-TIMING-PARTY **PASS/640.504초**: A 마지막 소유 Puppet 종료·실제 offline_since·B온라인·300초 부근/직전/최종 완료 창까지 A 유지·실제600초 이후 정상 Tick 승계·A재접속 권한 자동복원 없음·구성/전술/아이템/Claim 보존.
- 같은 RELEASE Helper의 Node 시간16개는30/58초 CLOSED·58초LOCKED·예약변경·300/598초승계·필수관측 누락/지연/조회오류를 실제로 거절한다. 조회 상한2초/최종 유효 창은 완화하지 않았고 누락 시FAIL이다. E2E11의599.999/600 서비스 주입과 실제 시간 검사를 별도로 기록한다.
- 독립 persistence 재검증 E2E12 **45.936초**, E2E13 **16.846초**: 실제 Exit 및 DoorInstallation·Profile/줄임말·Item UUID/장착/수량·Party·Quest/Credential·Native/Legacy/Claim·정상 만료와 데이터 손실 구분·상위 Rollback/알림 차단. 일반 Exit의 독립성도 비교한다.


### 안전성과 별도 검증 상태

시나리오/Job마다 새 marker·SQLite·동적 포트·합성 일반 계정·독립 Browser Context/실제 WS를 사용한다. 공개 증거의 run.json은 SHA·자격 증명 제거·Node/Chromium 및 Evennia 소유 프로세스 종료·플레이 DB 불변을 모두 true로 확인한다. observations의 모든 Context가 종료되고 소유 Puppet ID가 해제됐다. Artifact는 허용된 JSON/HTML·원문 비수집 로그 요약과 명시 마스킹 PNG2개만 포함하며 인증·개인 메시지·임의 입력·DB·원본 Snapshot·Trace/Video는 없다. 성공14일/실패30일 정책을 유지하고 실제 성공 Artifact의 만료 시각도 대조했다. 실패 원본 DB/로그는 운영 DB와 구분된 소유 로컬 경로에만 보존한다.

실제 플레이 DB의 SHA256은 `a33b102000a62dfe761fc8db5a90f1c4c4ffa012d9aec14a716c1d3784a592c3`이며 size/mtime/hash 불변이다. 운영 서버·운영 데이터 적용/마이그레이션은 수행하지 않았다. 신규 미해결 P0/P1은 없고 비차단 favicon P2는 [#59](https://github.com/wonmin82/primal-zone/issues/59)에서 OPEN 추적한다. #58은 변경하지 않았다. OS 한글 IME는 **PRIOR VERIFIED**, 최초 Visual Baseline은 **PENDING REVIEW**이며 객관적 DOM·접근성 PASS와 주관적 이미지 승인은 구분한다. Ubuntu는 실제 RELEASE, Windows는 보존된 실제 로컬 증거이며 macOS는 미지원/NOT RUN이다.

### 최종 완료 절차와 공식 기록

문서 Closeout PR은 문서만 변경하고 한국어 Commit·정확한 HEAD 로컬Quick·네 PR CI·Merge 부모/Tree를 확인한다. 새 최종 main의 네 push CI와8개 RELEASE가 모두 성공해야 한다. 최종 실행SHA/RunID/8Job/테스트수·실시간/모든Gates는 Issue50의 공식 Final Closeout 댓글에 남기며 추가 Commit은 하지 않는다. 그 후 Issue50 Completed, 실제 선행자식 상태/CI/체크리스트 감사 후 Issue45 Completed, PR60·최소수정61·문서PR의 소스만 안전하게 삭제한다. Gate미충족 시IssueOPEN·브랜치보존하고HOLD로 보고한다.

PR60의 종료 링크가2026-10-12T10:59:40Z에 Issue50을 조기 CLOSED로 변경한 사실을 확인해2026-10-12T12:48:36Z에 OPEN으로 복원했다. DESIGN FREEZE를 포함한 전체 원문과 과거 이력을 바꾸지 않았다. 이 자동 종료는 완료 근거로 사용하지 않는다.


## 아래 기록의 시점

아래 기존 NOT RUN·PENDING·OPEN·Pre-merge 및 Phase 범위 표기는 해당 구현·리뷰 당시의 역사적 기록이다. 삭제하거나 새 SHA의 실행 결과로 재작성하지 않는다. 현재 결과와 최종 확인 절차는 위 기록 및 연결된 Final Closeout 기록을 따른다.

## 현재 판정

**50-B~E 및50-F 준비 로컬 완료 / PR CI PENDING. 최종 RELEASE PASS는 아직 선언하지 않는다.**

위 PENDING은 이 문서 커밋 시점이다. 정확한 최종 제출 HEAD·Quick·PR URL·네 CI 결과는 [Issue #50 최신 구현 진행 기록](https://github.com/wonmin82/primal-zone/issues/50)과 연결 PR Validation에서 실제 완료 후 확정한다. 과거 CI를 새 HEAD의 성공으로 재사용하지 않는다.

착수 Base `82641de0ea66898676b0b29194d7918489443def`, Source `codex/issue-50-integrated-qa`. Issue #50 v1.2 D01~D28/P-01/P-02 보존. Issue #50/#45 OPEN 유지, Issue #58 비범위. PR Merge/Source 삭제/Issue Close/실제 운영 적용은 이번 제출 작업에서 수행하지 않는다.

## 단계

| 단계 | 현재 구현 | 실행 상태 |
| --- | --- | --- |
| 50-B | T50 계약74개/실제70개 테스트 연결, Registry/Alias/Help·문서·의료 경계 |70 PASS/186.579초, 신규3 PASS/23.133초, 순수229/통합814 전체 PASS. 첫 Alias 순서 FAIL은 수정·보존 |
| 50-C | 실제14 E2E·독립 Context/WS·UI/DB Assertion | 전체14·역할별 NPC·두 화면/입력·실제50-A9 로컬 PASS. 최신PR CI는 문서 커밋 시점 PENDING |
| 50-D | 실제 정상 재시작·영속 비교·PR 시각 주입·실제 RELEASE 시간 실행기 | 실제60/600 RELEASE는 NOT RUN |
| 50-E | 테스트 인프라의 keepalive 관측 결함 및 초기 fixture/metadata 가정 보완 | 게임 정책 변경 없음, 새 차단P0/P1 없음. favicon P2 #59 이관 |
| 50-F 준비 | 별도 dispatch Workflow·main SHA guard·독립 Job·안전한 Artifact | 실행 준비와 최종 main RELEASE PASS를 구분, 실제 RELEASE NOT RUN |

## Gate G-01~G-15

| Gate | Pre-merge 상태 | 근거·남은 작업 |
| --- | --- | --- |
| G-01 | PASS (착수 감사) | 선행 PR51/52/53/55/56/57 MERGED·해당 main CI SUCCESS. 최종 main SHA의 감사는 후속 |
| G-02 | PASS (직접 영향) | 명령/전체 Alias·줄임말 경계의 실제 T50 테스트 및 고정 metadata |
| G-03 | PASS (직접 영향) | 실제 Help/Alias dispatcher·관련 페이지·명시된 docs 명령표 비교·Node 웹 Action 계약 |
| G-04 | PASS (로컬) | 순수229/통합814 새 전체 실행 PASS. 원격 최신HEAD는 PENDING |
| G-05 | PASS (로컬) | 실제E2E01~14 및 NPC 역할 보강 PASS. 원격 최신HEAD는 PENDING |
| G-06 | PASS (로컬) | 실제 Chromium 기존9+전체14. 원격 최신HEAD는 PENDING |
| G-07 | PASS (객관적 로컬) | 두 Viewport/Focus/이름/DOM/overflow, 이미지 PENDING REVIEW·IME PRIOR VERIFIED |
| G-08 | PASS (로컬) | 독립2~3 Account/Context/WS·수신 범위·실제 소유 Puppet 해제 |
| G-09 | NOT RUN | 실제 Door60초 RELEASE |
| G-10 | NOT RUN | 실제 리더600초 RELEASE |
| G-11 | PASS (로컬) | 실제 정상 restart·동일DB·영속 비교/상위/Savepoint/전송 실패 경계 |
| G-12 | NOT RUN (최종) | 최종 Push HEAD Quick, 최종 main의 Full은 병합 후 |
| G-13 | PASS (이번 범위) | 새 차단P0/P1 없음, favicon P2 #59 이관 |
| G-14 | NOT RUN | 실제 병합된 main 네 CI 및 RELEASE 필요 |
| G-15 | 준비 완료 / 최종 Closeout NOT RUN | 필수5문서·로컬 증거 준비, main SHA/RELEASE/Closeout은 후속 |

## RELEASE 실행 방법

최종 통합 PR을 사용자가 리뷰하고 Merge를 승인한 뒤 실제 Merge SHA의 main CI를 확인한다. `.github/workflows/release-validation.yml`을 main에서 dispatch하며 `target_sha`에 해당40자리 SHA를 명시한다. `release_guard.py`가 event/ref/GITHUB_SHA/checkout HEAD/입력 SHA 전부 일치를 요구한다. Source PR에서 RELEASE 완료를 주장하지 않는다.

독립 Job: 전체 test, Quick smoke, smoke-full, contracts, browser-e2e-full, 실제 timing-e2e, persistence-e2e. DB/포트/계정/프로세스는 Job 및 시나리오별 격리. 전체 test와600초 시간 Job은 병렬이다. 성공 Artifact14일/실패30일, 엄격한 비수집/허용목록 유지. 실행 후 각 Job URL·SHA·개수·시간 및 안전한 증거를 기록하고 G-01~15를 새로 감사한다.

이 문서를 작성했다고 50-F/RELEASE/G-15 Closeout을 완료한 것으로 처리하지 않는다. Merge·Issue 종료는 별도 사용자 승인 범위를 따른다.

## 최종 로컬 실행

- 코드/역할/영속 보강 커밋은 통합 매트릭스와 Git 이력에 연결한다. 최종 문서 포함 제출HEAD·Quick·GitHub CI는 실제 완료 후 PR/Issue50에 기록한다.
- 최초 전체의 Alias 순서 FAIL은 수정 후 새 전체 순수229/3.139초·통합814/659.195초 PASS로 재검증했다. 전체671.907초. 이후 게임/Python 테스트 코드 변경 없음.
- 새 Snapshot의 초기화 전 소유 DB 거절·query_only·Console 강제 실패·버전 기록은 Runner/Node/실제 직접 영향/기존 관측 오류0으로 검토했다. 동일 전체를 단순 커밋/문서 수정 때문에 반복하지 않는다.
- 운영 DB SHA256 a33b102000a62dfe761fc8db5a90f1c4c4ffa012d9aec14a716c1d3784a592c3, hash/mtime/size 불변을 실행기마다 확인했다. 성공 격리 DB 삭제, 실패 DB/로그만 소유 로컬 경로 보존·인증 제거·프로세스 종료.
- 비차단 favicon404는 [후속Issue59](https://github.com/wonmin82/primal-zone/issues/59). P0/P1 없음. Issue50/45 OPEN, Source 유지, Merge/Close 미수행.


## PR #60 리뷰 보완 — Pre-merge

P1-01 시간 조기 실행 검출, P1-02 실제 Exit 영속 데이터, P2-01 오래된 실제 버튼 요청, P2-02 기능별 문서/Metadata 계약을 보완했다. 실제 코드와 정상/음성 검출 근거는 [리뷰 추적표](issue50-integration-matrix.md#pr-60-독립-리뷰-보완--p1-0102-p2-0102)에 연결한다. 최초 CI SUCCESS는 당시 결과이며 새로운 HEAD의 성공을 대신하지 않는다.

게임 정책·영속 형식·프로토콜·운영 타이머/DB 변경 없음. 테스트 인프라의 Windows checkpoint UTF-8 디코딩을 최소 보완했고 실제 Unicode 자식·정상 재시작으로 검증했다. 문서의 현행 Profile v13 표기2곳은 실제 v14로 정정하되 과거 v10/마이그레이션 기록은 보존했다.

최종 제출HEAD/Quick/네 CI 및 안전한 Artifact는 실제 완료 후 PR60/Issue50의 Review Fixes에 기록한다. 이 절 작성만으로 새 HEAD CI PASS를 주장하지 않는다. G09 실제60초·G10 실제600초·G12 Full·G14 최종main/RELEASE·G15 FinalCloseout은 NOT RUN. PR60 OPEN/Ready, Source 유지, Issue50/45 OPEN. Issue58 변경 없음, 비차단 favicon #59 추적 유지.


## PR #60 P2-03 — 최종 시간 경계 관측 보완

리뷰 기준 `5193aa2fd3232976eecf2a0f362cd4ec3e013fb5`, 수정 코드 `653340465930e9782a80aa6dde9154fddd71455a`, Base `82641de0ea66898676b0b29194d7918489443def`. 기존 4건 리뷰/실패/성공 이력은 당시 기록으로 보존한다. 이 보완은 게임·운영 타이머·프로토콜·영속 형식을 변경하지 않는다. 최종 문서 포함 Source HEAD의 Quick/새 네 CI는 실제 완료 후 [PR #60](https://github.com/wonmin82/primal-zone/pull/60)과 [Issue #50](https://github.com/wonmin82/primal-zone/issues/50)에 기록한다. 이 문서 커밋 시점에는 해당 게이트 PENDING이다.

`review-contracts.cjs::monitorBeforeDeadline()`은 더 이상 만료4초 전에 반환하지 않는다. 시작~중간~만료4초 전은 최대5초, 마지막 구간은 최대500ms의 시작 간격을 목표로 하며 직전 monotonic 조회 비용을 대기에서 뺀다. 조회가500ms보다 오래 걸리면 추가 대기 없이 다음 조회를 시작한다. 개별 조회 전체 비용 상한은 기존2,000ms다. 스케줄러 지연·2초 초과 조회·서버/세션 오류·필수 체크포인트 누락은 FAIL이며 창을 넓히거나 재시도로 숨기지 않는다.

중간 완료는 중간 시각부터7초 이내(5초 간격+최대2초 조회), 직전 반복 관측은 만료4~2초 전 구간에 실제 조회가 완료되어야 한다. **최종 유효 창은 `deadline - 1.0 <= observation.end <= deadline - 0.5`**다. 완료를 만료0.75초 전으로 맞추도록 직전 조회 비용을 고려한다. 관측 시작만 유효하거나 만료 직전 조회가 늦게 완료된 경우는 실패한다. 반환하는 `middleSeen/nearSeen/finalSeen`은 상태 원문을 포함하지 않으며 두 RELEASE 시나리오가 세 값 모두 true를 요구한다.

`integration_probe.py --timing`은 소유 경로/marker/명시 DB 검사를 거친 후 SQLite `mode=ro`·`query_only`·읽기 트랜잭션으로 실제 Door/일행/위치/Puppet/아이템/Claim을 읽는다. Attribute는 현재 내장 데이터만 복원하며 전역 객체/global·중복/소실은 거절한다. 기존 전체 Snapshot의 실제 Exit/설치/Room 영속 검사는 그대로 유지한다. 시간 검사와 E2E-11의 실제 DB projection 대조만 이 경량 조회를 사용한다. 원본 Snapshot/DB·사용자 입력·인증정보는 Artifact에 포함하지 않는다.

- 수정 전58초 CLOSED/598초 승계 음성2개는 `Missing expected rejection`으로 FAIL(0.149초)하여 기존 관측 공백을 재현했다. 수정 후 같은 Helper의 P203-01~12와 추가 중간/직전 누락을 모두 거절/수용한다. 기존30초/300초·2초 조회 지연 회귀를 유지한다.
- 최종 Node 계약 **52 PASS/0.399초**, 기존43+신규9, fail/skip0. 시간 회귀16개와 Exit 회귀8개, 기존 웹/보호28개를 포함한다. Python 통합 Runner **9 PASS/2.393초**, 기존8+실제 SQLite projection/해시·mtime 비변경·손상 거절1개. 기존 Browser Runner Windows23 PASS·POSIX1 N/A/5.724초(정의24).
- 실제 Chromium E2E-11 **PASS/80.126초**, 서버 준비~정리119.703초(명령 진입점 전체120.619초). 실제599.999/600 서비스 주입·재접속·projection과 정상 실제 DB·소유 Puppet3관측 해제 확인. Node/Chromium/Evennia 종료·인증 삭제·성공DB 삭제·실제 플레이DB hash/mtime/size 불변 true.
- `npm run test:browser:timing`→TIMING-DOOR/PARTY→동일 관측 Helper 연결 및 RELEASE Workflow 호출을 Runner가 확인했다. 정상/조기 회귀는 주입 Clock 검증이며 **실제60초/600초 Wall Clock PASS로 합산하지 않는다**.
- check·변경JS 구문·diff PASS. 게임/Python 전체 구현 및 의존성은 변경하지 않았다. 기존 로컬 전체229/816 성공(이전 리뷰 SHA의 기록)을 새 실행으로 표현하지 않고, 이번 직접 영향 QA 회귀와 새 HEAD의 원격 전체 Suite로 확인한다.

RF-33~46은 관측 구현/검출 회귀/실제 서비스 주입/RELEASE 연결/안전성으로 확인한다. RF-47~50 최종 Quick·새 네 CI·기록·차단 결함 감사는 실제 완료 후 PR/Issue에서 확정한다. RF-51~52: **실제 Door60초·리더600초 RELEASE NOT RUN**, PR60 OPEN/Ready·Source 유지·Issue50/45 OPEN. G-12 Full·G-14 최종main CI/RELEASE·G-15 FinalCloseout NOT RUN, IME PRIOR VERIFIED, Visual Baseline PENDING REVIEW, Issue58 비범위, 기존 favicon P2 #59 추적 유지. Merge/브랜치 삭제/Issue Close는 수행하지 않는다.
