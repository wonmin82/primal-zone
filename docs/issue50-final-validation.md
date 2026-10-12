# Issue #50 최종 검증 — Pre-merge

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
