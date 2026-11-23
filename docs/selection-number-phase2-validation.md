# Selection Number v1.5 Phase 2 검증

[Issue #109](https://github.com/wonmin82/primal-zone/issues/109)과 [v1.5 FINAL 설계](selection-number-display-design-v1.5.md)를 기준으로 측정했다. 비교 기준은 Phase 1 병합 커밋 `f810ceb135be3df94744b5ab97e185d7e029c140`이다.

## 실행과 계측

macOS arm64, Python 3.13.18, SQLite 3.53.1의 동일 머신에서 격리 `settings_test` DB와 같은 Fixture를 사용했다. 각 경로의 워밍업 1회 뒤 5회 중앙값을 기록했다. SQL 수는 타이밍과 별도의 실행에서 `execute_wrapper`로 집계했다. Enemy·NPC·Door와 Corpse·Ground 혼합 경로의 대상 수는 각 유형별 개수다. 예를 들어 100에서 전자는 300개, 후자는 200개다. 실측값은 대표 Fixture의 결과다.

```sh
.venv/bin/python scripts/dev.py test tests.bench_selection_phase2 --parallel 1
```

표의 각 셀은 1 / 10 / 100개 순서다.

| 경로 | SQL 전 → 후 | 처리 시간 전 → 후 (ms) | B-1 SELECT 후 |
| --- | --- | --- | --- |
| Room 공개 Snapshot | 12 / 12 / 12 → 12 / 12 / 12 | 2.144 / 2.723 / 9.567 → 1.933 / 2.566 / 9.307 | 1 / 1 / 1 |
| Enemy·NPC·Door 웹 상태 | 190 / 1612 / 15832 → 130 / 949 / 9139 | 24.548 / 197.034 / 7661.286 → 15.101 / 91.517 / 869.424 | 2 / 2 / 2 |
| Inventory·Equipment | 5 / 5 / 5 → 5 / 5 / 5 | 0.625 / 0.803 / 2.561 → 0.631 / 0.777 / 2.439 | 1 / 1 / 1 |
| Storage 버튼 | 70 / 88 / 268 → 70 / 70 / 70 | 9.354 / 14.015 / 54.478 → 9.493 / 11.894 / 32.711 | 9 / 9 / 9 |
| Inside 표시 | 5 / 5 / 5 → 5 / 5 / 5 | 0.563 / 0.753 / 2.589 → 0.524 / 0.77 / 2.545 | 1 / 1 / 1 |
| Corpse·바닥 전리품 표시 | 17 / 17 / 17 → 17 / 17 / 17 | 3.413 / 5.94 / 68.346 → 3.232 / 5.724 / 66.543 | 2 / 2 / 2 |
| Action Control | 97 / 115 / 295 → 97 / 97 / 97 | 12.733 / 17.986 / 64.298 → 12.888 / 15.904 / 42.811 | 12 / 12 / 12 |
| Native 명시 번호 선택 | 5 / 5 / 5 → 5 / 5 / 5 | 0.535 / 0.634 / 1.778 → 0.525 / 0.636 / 1.636 | 1 / 1 / 1 |
| Source+Entry 복합 선택 | 62 / 512 / 5012 → 35 / 233 / 2213 | 8.545 / 59.528 / 573.507 → 4.467 / 25.401 / 237.53 | 3 / 3 / 3 |

Room 공개 번호 조회는 1회, Inventory·Equipment와 Inside는 각 1회, Loot 표시의 번호 조회는 2회로 유지됐다. 순수 표시 경로의 SQL 쓰기는 0회였다. 개별 실물 복원 비용을 배치로 바꿔 Native 번호 후보 검사의 1·10·100개 실물 조회는 SQL 2·11·101회에서 2·2·2회로 줄었다.

전체 웹 상태와 복합 선택은 기존 월드 생명주기 정합화를 포함한다. 전체 웹 상태의 Enemy 정합화가 일으키는 기존 쓰기 14·140·1,400회는 유지된다. Door는 관찰 요청의 출구 목록과 조작 가능 상태를 재사용하되 실행 시에는 현재 조건을 다시 검사한다. 만료 전리품 권리가 없는 출처는 기존 월드 잠금 경계에서 조기 종료하고, 처리할 권리가 있으면 기존 잠금과 조건 검사를 사용한다. 두 전체 경로의 남은 SQL 증가에는 이 생명주기 처리와 개별 도메인 관찰이 포함된다.

## 기능과 권한 테스트 근거

| 영역 | 관련 자동 테스트 |
| --- | --- |
| 공개 범위, 이름·숫자 충돌, 결번, 조회 전용 번호 API | `test_selection_numbers`, `test_selection_exact` |
| 정확 인용 텍스트와 Typed UUID, Inside·Door·NPC·Corpse, 접근·순환·이동·삭제 거절 | `test_selection_observation` |
| Native ItemEntity 장비·이동·보관·스택 및 오래된 요청 | `test_storage_actions`, `test_item_interactions`, `test_item_equipment_actions` |
| Source+Entry, 보호·배정·노출, 재전송, 경합과 롤백 | `test_loot_actions`, `test_loot_entities`, `test_loot_action_invariants` |
| Gateway, 세션 및 제공 상태, Door 자동 닫힘·요청별 캐시 | `test_action_runtime`, `test_action_presentation_cache`, `test_room_npc_actions`, `test_doors` |
| 전투·Duel·Narration, 웹 동작 | 전체 Python 검사, Smoke, Contracts, Chromium E2E |

벤치마크는 Inside 관찰 버튼의 실제 UUID 집합과 Source+Entry가 선택한 원래 전리품 UUID를 비교한다. 동일 Session의 재전송, 다른 Session/Puppet, 권한 변경 및 stale 참조의 실행 효과는 기존 Gateway·도메인 회귀에서 검증한다. 다중 서버 동시 쓰기와 운영 DB 검증은 이 작업에서 실행하지 않았다. 실제 OS 한글 IME는 기존 사용자 확인 기록을 사용한다.
