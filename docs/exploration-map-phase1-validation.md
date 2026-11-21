# 탐사 지도 Phase 1 검증

[범용 탐사 지도 설계 v2.2 FINAL](exploration-map-design-v2.2.md)은 [Epic #102](https://github.com/wonmin82/primal-zone/issues/102)의 규범적 본문 전체를 옮긴 문서다. 설계 시점의 상태와 체크리스트는 원본 그대로 기록되어 있다. 문서가 병합되면 지도 계약은 저장소 설계 문서를 기준으로 삼고, 승인과 변경 이력은 Epic에서 추적한다. 이 문서는 [Phase 1 #103](https://github.com/wonmin82/primal-zone/issues/103)의 실행 근거를 기록한다.

## 실제 월드

macOS 27.2.1 arm64, Python 3.13.18, Evennia 6.1.0, SQLite 3.53.1. 기준 `main`은 `01aaf8882824b8e34b76ad20d362af6cd4b31f61`이다. 테스트는 격리 DB에 실제 월드를 설치하고 각 Room에서 현재 지도 또는 Connector 출구를 조회한다.

| 대상 | Room 수 | 결과 |
|---|---:|---|
| 본부 1·2·3층 | 4 / 6 / 6 | 실제 Exit에서 자동 배치 |
| 본부 4·5층·옥상 | 9 / 11 / 9 | 실제 Exit에서 자동 배치. 옥상 8방향 포함 |
| 본부 계단·공용 승강기 | 6 / 1 | Connector의 실제 공개 출구 조회 |
| 탐사대 전초구역 | 8 | 자동 기본 Sheet, 지도 메타데이터 0건 |
| 깊은 밀림 | 7 | 자동 기본 Sheet, 지도 메타데이터 0건 |
| 합계 | 67 | 평면 60, Connector 7. Layout Hint 0건 |

일반 Region은 기존 Region과 Room·Exit만 등록하여 지도 엔진 변경과 지도 전용 선언 없이 처리한다. 합성 테스트에서 방향 순환, 두 경로가 만나는 Room, 분리 성분, 다층·Connector, 상대 Position·Route, 허용되지 않는 교차와 Room 관통을 검증한다. 동쪽으로만 이어져 출발점에 돌아오는 순환과 격자의 연결선이 가로지르는 구조는 일반적인 표현 불가 사례다.

## 재현 명령

```sh
.venv/bin/python scripts/dev.py check
.venv/bin/python scripts/dev.py test tests.test_exploration_map tests.bench_exploration_map --parallel 1
.venv/bin/python scripts/dev.py test --parallel 4
.venv/bin/python scripts/dev.py smoke
npm run test:contracts
.venv/bin/python scripts/browser_e2e.py
```

지도 통합 테스트는 Room 방문·이름 공개·Exit 공개의 독립 판정, 비공개 Hint 변경 시 공개 메시지 동일성, 원격 정적 Exit과 동적 Exit 구분, Door, 실제 대상 불일치, 동명 장소와 대형 허브, 조회 SQL의 쓰기 0을 검증한다. 명령 dispatcher에서 기존 Recovery와 Prompt를 유지하고 전역 상태 갱신을 추가하지 않는 것도 별도 검사한다. Quick Smoke는 실제 서버·WebSocket·스케줄러의 보조 회귀 검사다. 브라우저에서는 `TEST-103-01`로 기존 로그의 지도와 일반 출력의 줄바꿈을 각각 확인한다.

## 성능

명시적으로 실행하는 `tests.bench_exploration_map`은 서로 다른 10·100·1,000 Room 규모의 직선 Sheet에 실제 Evennia Room/Exit와 관리 태그를 구성한다. 원격 공개 범위의 그래프 구성·배치·렌더 각 단계를 계측한다. 시간은 추적을 끈 두 번째 단일 조회 한 번의 결과이며, 메모리는 별도의 추적 실행에서 Python 할당 피크를 기록한다. 동시 비용은 복제한 격리 SQLite에 독립 연결을 연 네 요청 묶음의 벽시계 시간이다. 이 측정은 실제 게임 서버의 이벤트 루프나 왕복 응답시간을 포함하지 않는다.

| Room | 그래프 ms | 배치 ms | 렌더 ms | SQL | Python 피크 바이트 | 본문 UTF-8 바이트 | 동시 4건 ms |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 1.364 | 0.074 | 0.051 | 5 | 136,217 | 37 | 7.882 |
| 100 | 6.888 | 0.585 | 0.301 | 5 | 1,093,244 | 119 | 31.422 |
| 1,000 | 209.475 | 6.941 | 1.719 | 5 | 11,182,241 | 119 | 416.638 |

## 운영 및 범위

- 관리 Exit을 찾을 수 없고 기존 공개 정책을 판정할 실제 객체도 없으면 운영 로그에 불일치를 남기고 경계를 숨긴다. 공개된 방문 목적지와 관리 Exit이 불일치하면 안전 실패 안내를 표시한다.
- 현재 구조의 Unicode 선문자는 기존 표시 폭 정책으로 1셀을 사용한다. 단말이 동아시아 모호 폭 문자를 2셀로 설정한 경우 `지도 ascii`로 확인할 수 있다.
- 전용 웹 미니맵은 [Phase 2 #104](https://github.com/wonmin82/primal-zone/issues/104) 범위다. Phase 1 PR 제출 시 G5의 병합·병합된 `main` CI 단계는 미완료다.
