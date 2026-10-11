# Issue #49 구현·수용 검사 추적

설계 기준은 [Issue #49 v1.3 FREEZE](https://github.com/wonmin82/primal-zone/issues/49)다. 원본 수용 조건·Decision·역사적 NOT RUN을 변경하지 않고 별도 실행 증거를 연결한다. 구현 계약은 [문과 열쇠](doors-and-keys.md), 실행 환경·실패 보정·미실행은 [playtest](playtest.md#issue-49-문과-열쇠-검증)에 있다.

## 실행 명령과 근거

- **T**: 저장소 루트 `uv run python scripts/dev.py test --parallel 4`. 순수 world 검사와 전체 Evennia 통합을 포함한다.
- **S**: T에 포함된 `tests.test_door_schema`: 빈 DB 및 기존 저장 데이터를 가진 격리 SQLite 복제본의 migration·설치·재Bootstrap·원본 Exit PK 보존.
- **W**: `node --check game/web/static/webclient/js/primal.js`, `node --test scripts/tests/test_web_prompt.cjs`. 기존 DOM·WebSocket text 전달·한글 조합 이벤트 자동 계약과 Door 버튼 상태 교체. T의 `tests.test_web_prompt`도 실제 Node 검사를 연결한다.
- **G**: 실제 커밋 HEAD의 `uv run python scripts/dev.py smoke`와 그 SHA의 GitHub test/smoke. 커밋의 자체 SHA는 문서에 미리 추정하지 않고 PR Validation·Issue 진행 기록에서 실제 결과를 확정한다.

아래 자동 검사는 최종 전체 실행에서 순수 229개(2.665초) + 통합 803개(474.796초) PASS·종료 0으로 확인했다. 멀티세션 발급은 같은 영속 캐릭터 요청의 world_change 직렬 처리 및 DB unique 거절로 검증한다. 실제 네트워크 세션 경쟁·브라우저·OS IME·장기 운영은 #50의 별도 범위다. 순서 경합은 주입 시각과 직렬 순서/Savepoint로 검사하며 실제 60초 sleep은 없다.

## RT-01~RT-66

표의 최초 구현 실행 이력은 보존한다. PR #56 D13 P1 리뷰 후의 추가 근거와 최신 실행은 아래 [장애 격리 추가 검사](#pr-56-d13-p1-추가-검사) 및 [playtest](playtest.md#pr-56-d13-장애-격리-p1-보완)를 따른다.

| RT | 원래 정책 | 실제 테스트 파일/메서드 | 명령 | 결과 | 추가 근거 |
| --- | --- | --- | --- | --- | --- |
| RT-01 | Door SSOT | `tests.test_doors.DoorTest.test_single_state_fixed_contents_and_real_exit_pk` | T | PASS | 실제 상태/출력 assertion |
| RT-02 | Door SSOT | `tests.test_doors.DoorTest.test_single_state_fixed_contents_and_real_exit_pk` | T | PASS | 실제 상태/출력 assertion |
| RT-03 | 설치 | `tests.test_doors.DoorTest.test_first_install_clock_and_repeat_bootstrap_preserves_state_and_pk` | T | PASS | 실제 상태/출력 assertion |
| RT-04 | 부트스트랩 | `tests.test_doors.DoorTest.test_first_install_clock_and_repeat_bootstrap_preserves_state_and_pk` | T | PASS | 실제 상태/출력 assertion |
| RT-05 | 콘텐츠 | `tests.test_doors.DoorTest.test_single_state_fixed_contents_and_real_exit_pk` | T | PASS | 실제 상태/출력 assertion |
| RT-06 | 일반 Exit | `tests.test_doors.DoorTest.test_no_door_exit_unchanged` | T | PASS | 기존 exit_policy/exit_presentation/distant_view 및 bootstrap_exits 전체 회귀 |
| RT-07 | D13 | `tests.test_doors.DoorTest.test_uniqueness_and_endpoint_conflict_rejected` | T | PASS | 실제 상태/출력 assertion |
| RT-08 | D13 | `tests.test_doors.DoorTest.test_missing_installed_door_not_recreated_other_door_works` | T | PASS | 실제 상태/출력 assertion |
| RT-09 | D13 | `tests.test_doors.DoorTest.test_original_exit_reference_repaired_without_state_reset` | T | PASS | cosmetic_sync_and_lost_endpoint_never_recreated: 표시/Alias와 원래 예약 보존 |
| RT-10 | D13 | `tests.test_doors.DoorTest.test_endpoint_destination_damage_not_reconnected` | T | PASS | invalid_states_and_expiry_are_read_only 및 damaged_exit_typeclass_cannot_bypass_guard_with_engine_traverse: 손상된 enum·예약·실제 엔진 Exit 우회 차단 |
| RT-11 | D13 | `tests.test_doors.DoorTest.test_bootstrap_failure_rolls_back_database_and_evennia_cache` | T | PASS | 실제 상태/출력 assertion |
| RT-12 | D08/D09 | `tests.test_doors.DoorKeyTests.test_actual_cabinet_free_issue_duplicate_reissue_and_per_owner` | T | PASS | 실제 상태/출력 assertion |
| RT-13 | D09 | `tests.test_doors.DoorKeyTests.test_actual_cabinet_free_issue_duplicate_reissue_and_per_owner` | T | PASS | 실제 상태/출력 assertion |
| RT-14 | D08 | `tests.test_doors.DoorKeyTests.test_corrupt_ownership_not_duplicated_and_combat_or_remote_denied` | T | PASS | 실제 상태/출력 assertion |
| RT-15 | D09 | `tests.test_doors.DoorKeyTests.test_actual_cabinet_free_issue_duplicate_reissue_and_per_owner` | T | PASS | 실제 상태/출력 assertion |
| RT-16 | 키 정책 | `tests.test_doors.DoorKeyTests.test_every_operation_blocked_at_actual_api_and_state_preserved` | T | PASS | 전체 TREE_OPERATION_SCOPES 실제 move_item 거절·수량/소유 상태 불변 |
| RT-17 | 키 정의 | `tests.test_doors.DoorKeyTests.test_information_inventory_and_credential_are_separate_read_only` | T | PASS | 실제 상태/출력 assertion |
| RT-18 | 동시 발급 | `tests.test_doors.DoorKeyTests.test_unique_scope_and_repeated_session_request` | T | PASS | DB unique 및 반복 동일 캐릭터 요청; 실제 세션 동시 요청은 #50 |
| RT-19 | 명령 | `tests.test_doors.DoorTest.test_four_registry_commands_actual_postfix_parser_and_help` | T | PASS | 실제 상태/출력 assertion |
| RT-20 | D06 | `tests.test_doors.DoorTest.test_multiple_door_selector_direction_order_and_ambiguity` | T | PASS | 단일 문은 실제 문 1/문 입력, 복수는 임의 선택 거절 |
| RT-21 | D07 | `tests.test_doors.DoorTest.test_target_required_index_all_hidden_and_wrong_room` | T | PASS | 실제 상태/출력 assertion |
| RT-22 | 대상 선택 | `tests.test_doors.DoorTest.test_multiple_door_selector_direction_order_and_ambiguity` | T | PASS | 실제 상태/출력 assertion |
| RT-23 | 대상 감지 | `tests.test_doors.DoorTest.test_target_required_index_all_hidden_and_wrong_room` | T | PASS | 실제 상태/출력 assertion |
| RT-24 | 상태 전이 | `tests.test_doors.DoorTest.test_all_state_transitions_key_latch_and_nonlockable` | T | PASS | 실제 상태/출력 assertion |
| RT-25 | D05 | `tests.test_doors.DoorTest.test_idempotence_failed_commands_and_peace_leave_timer_and_key_unchanged` | T | PASS | 실제 상태/출력 assertion |
| RT-26 | 실패 전이 | `tests.test_doors.DoorTest.test_all_state_transitions_key_latch_and_nonlockable` | T | PASS | idempotence_failed_commands_and_peace_leave_timer_and_key_unchanged |
| RT-27 | D01/D02 | `tests.test_doors.DoorTest.test_all_state_transitions_key_latch_and_nonlockable` | T | PASS | 실제 상태/출력 assertion |
| RT-28 | D01 | `tests.test_doors.DoorTest.test_all_state_transitions_key_latch_and_nonlockable` | T | PASS | 실제 상태/출력 assertion |
| RT-29 | 내부 래치 | `tests.test_doors.DoorTest.test_all_state_transitions_key_latch_and_nonlockable` | T | PASS | 실제 상태/출력 assertion |
| RT-30 | D03/D14 | `tests.test_doors.DoorTest.test_recovery_room_both_sides_free_reopen_and_original_bed` | T | PASS | 실제 상태/출력 assertion |
| RT-31 | D10 | `tests.test_doors.DoorTest.test_idempotence_failed_commands_and_peace_leave_timer_and_key_unchanged` | T | PASS | 실제 상태/출력 assertion |
| RT-32 | D04 | `tests.test_doors.DoorTest.test_four_registry_commands_actual_postfix_parser_and_help` | T | PASS | 실제 상태/출력 assertion |
| RT-33 | D04 | `tests.test_doors.DoorTest.test_real_traversal_extends_at_completion_and_consecutive_crossings` | T | PASS | 실제 상태/출력 assertion |
| RT-34 | D04 | `tests.test_doors.DoorTest.test_multiple_players_direction_aliases_share_completion_timer` | T | PASS | 실제 상태/출력 assertion |
| RT-35 | D04 | `tests.test_doors.DoorTest.test_actual_exit_locks_combat_closed_and_target_mismatch_rejected` | T | PASS | gate_and_credential_and_open_door_do_not_bypass_each_other 및 완료 만료 롤백 |
| RT-36 | D04 | `tests.test_doors.DoorTest.test_logical_expiry_readonly_boundary_and_sweep` | T | PASS | traversal_expiry_at_completion_rolls_back_location_visited_and_messages: tick 전 차단 |
| RT-37 | D04 | `tests.test_doors.DoorTest.test_logical_expiry_readonly_boundary_and_sweep` | T | PASS | 실제 상태/출력 assertion |
| RT-38 | D04 | `tests.test_doors.DoorTest.test_late_sweep_restart_and_close_then_move_are_serial` | T | PASS | 실제 상태/출력 assertion |
| RT-39 | D04/D12 | `tests.test_doors.DoorTest.test_late_sweep_restart_and_close_then_move_are_serial` | T | PASS | 실제 상태/출력 assertion |
| RT-40 | D12 | `tests.test_doors.DoorTest.test_late_sweep_restart_and_close_then_move_are_serial` | T | PASS | 실제 상태/출력 assertion |
| RT-41 | D12 | `tests.test_doors.DoorTest.test_move_outer_savepoint_rollback_and_postcommit_only` | T | PASS | operation_outer_savepoint_rollback_and_postcommit_both_endpoints |
| RT-42 | 이동 | `tests.test_doors.DoorTest.test_multiple_players_direction_aliases_share_completion_timer` | T | PASS | e/w 실제 execute_cmd 및 직접 at_traverse; 기존 exit_policy Alias 검사 |
| RT-43 | Gate | `tests.test_doors.DoorTest.test_gate_and_credential_and_open_door_do_not_bypass_each_other` | T | PASS | 실제 Credential 부재, Quest 관찰 조건, Exit cmd/traverse 및 combat 개별 차단 |
| RT-44 | D11 | `tests.test_doors.DoorTest.test_closed_locked_expired_corrupt_block_all_live_observation_paths` | T | PASS | 실제 상태/출력 assertion |
| RT-45 | D11 | `tests.test_doors.DoorTest.test_visited_map_is_structural_unchanged_across_door_states` | T | PASS | 실제 상태/출력 assertion |
| RT-46 | VIEW-01/04 | `tests.test_doors.DoorTest.test_room_sentence_position_compass_preserved_and_hidden_door` | T | PASS | 실제 상태/출력 assertion |
| RT-47 | VIEW-02/03/08 | `tests.test_doors.DoorTest.test_doorless_room_original_snapshot` | T | PASS | 실제 상태/출력 assertion |
| RT-48 | VIEW-06 | `tests.test_doors.DoorTest.test_individual_look_direction_actual_exit_and_object_collision` | T | PASS | multiple_door_selector_direction_order_and_ambiguity: 문 2·방향 순서 |
| RT-49 | VIEW-07/09 | `tests.test_doors.DoorTest.test_multiple_door_selector_direction_order_and_ambiguity` | T | PASS | 실제 상태/출력 assertion |
| RT-50 | D11/VIEW-09 | `tests.test_doors.DoorTest.test_gate_and_credential_and_open_door_do_not_bypass_each_other` | T | PASS | 기존 tests.test_distant_view·lighting 전체: 광원/Quest/익명/권한 유지 |
| RT-51 | 출구/지도 | `tests.test_doors.DoorTest.test_visited_map_is_structural_unchanged_across_door_states` | T | PASS | 기존 tests.test_exit_presentation 표/도식/공개 범위 및 지도 동일 문자열 |
| RT-52 | 웹 | `tests.test_doors.DoorTest.test_web_existing_interactables_protocol_stale_buttons_and_expired_state` | T | PASS | W: 기존 조작 버튼 click→text 명령·새 payload 반영; 양 endpoint post-commit |
| RT-53 | D14 | `tests.test_doors.DoorTest.test_recovery_room_both_sides_free_reopen_and_original_bed` | T | PASS | 실제 상태/출력 assertion |
| RT-54 | 도움말 | `tests.test_doors.DoorTest.test_help_existing_five_and_v14_personal_commands_party_registry` | T | PASS | four_registry_commands_actual_postfix_parser_and_help: 신규 4개 도움/도움말 동일 규약 |
| RT-55 | 릴리즈 게이트 | `정확한 최종 HEAD의 Quick/Smoke·GitHub test/smoke` | G | PR 제출 게이트에서 확정 | 실제 상태/출력 assertion |
| RT-56 | D04/설치 | `tests.test_doors.DoorTest.test_first_install_clock_and_repeat_bootstrap_preserves_state_and_pk` | T | PASS | 실제 상태/출력 assertion |
| RT-57 | D04/D12 | `tests.test_doors.DoorTest.test_real_post_move_hook_error_rolls_back_visited_and_callbacks` | T | PASS | move_false_hook_exception_and_wrong_destination_rollback 및 완료 시각 만료·Savepoint |
| RT-58 | D06/VIEW-06/09 | `tests.test_doors.DoorTest.test_individual_look_direction_actual_exit_and_object_collision` | T | PASS | target_required_index_all_hidden_and_wrong_room 및 v14 실제 개인 묶음·e/w |
| RT-59 | D13 | `tests.test_doors.DoorTest.test_cosmetic_sync_and_lost_endpoint_never_recreated` | T | PASS | 원본 참조 복원·소실·다른 목적지·설치 증거 없는 레코드·교차 컬럼 중복·손상 Typeclass·S 기존 스키마 보존 |
| RT-60 | D08/D09 | `tests.test_doors.DoorKeyTests.test_every_operation_blocked_at_actual_api_and_state_preserved` | T | PASS | DoorKeyTests 전체 및 actual_investigate_command_defers_all_web_updates_until_commit: 실제 명령·발급·정보·unique·소유 손상·금지 Operation·상위 커밋 경계 |
| RT-61 | D11/VIEW-09 | `tests.test_doors.DoorTest.test_closed_locked_expired_corrupt_block_all_live_observation_paths` | T | PASS | Exit/context/Room 원거리 API 및 exit_entries/웹, 기본 Exit Typeclass 손상 시 직접 관찰 차단, 출력 전후 DB 불변 |
| RT-62 | VIEW-02~05 | `tests.test_doors.DoorTest.test_doorless_room_original_snapshot` | T | PASS | room_sentence_position_compass_preserved_and_hidden_door 및 실제 조작/오류 문체 |
| RT-63 | VIEW-02/03/09/지도 | `tests.test_doors.DoorTest.test_visited_map_is_structural_unchanged_across_door_states` | T | PASS | 실제 상태/출력 assertion |
| RT-64 | D10~12 | `tests.test_doors.DoorTest.test_actual_exit_locks_combat_closed_and_target_mismatch_rejected` | T | PASS | Gate/Combat/Lock을 모두 검사하는 이동 경계, 사용자 실패에 내부 PK 미노출 |
| RT-65 | VIEW-08/웹 | `tests.test_doors.DoorTest.test_operation_outer_savepoint_rollback_and_postcommit_both_endpoints` | T | PASS | postcommit_push_failure_does_not_undo_state_or_move: 전송 실패에도 DB 커밋 유지 |
| RT-66 | #48 선행/#50 연동 | `tests.test_doors.DoorTest.test_party_member_movement_preserves_tactics_and_combat_restriction` | T | PASS | help_existing_five_and_v14_personal_commands_party_registry + 기존 Party/전투/loot/NPC 전체 |

## CV-01~CV-18

설계 문서의 명문화 상태와 구현 실행 결과를 구분한다. 아래는 실제 코드와 위 RT의 자동 근거 연결이며 최종 전체 실행 결과를 따른다.

| CV | 실제 구현 경로 | 연결 RT | 자동 검증 |
| --- | --- | --- | --- |
| CV-01 | world/doors.py effective_door_state·state_for_exit, 모든 소비 경로 | 32/36/56 | PASS (T) |
| CV-02 | world/doors.py traverse, Explorer.move_to, world_change/after_change | 33~35/41/57 | PASS (T) |
| CV-03 | doors.resolve_door/look_door, commands/character.py, 공통 targets | 20~23/48/58 | PASS (T) |
| CV-04 | door_entities.models Door/DoorInstallation·install_doors | 01~05/59 | PASS (T) |
| CV-05 | install_doors 최초 시각·bootstrap preserved_endpoint | 03~04/56 | PASS (T) |
| CV-06 | content/items·item_entities.policy·door_keys | 12~18/60 | PASS (T) |
| CV-07 | Exit.can_observe_through/return_appearance·distant_appearance | 44~45/50/61 | PASS (T) |
| CV-08 | installation_errors·install_doors·bootstrap 원본 보존 | 07~11/59 | PASS (T) |
| CV-09 | ZoneRoom.return_appearance·description·기존 exit_diagram | 46~47/62 | PASS (T) |
| CV-10 | lifecycle.reconcile_world→reconcile_doors·기존 WorldLifecycle 5초 tick | 36~39/56 | PASS (T) |
| CV-11 | 기존 Map.run·exit_entries 공개 목적지 이름 | 51/63 | PASS (T) |
| CV-12 | current_doors 일반 지각·Exit 방향 조회 분리 | 23/49/58 | PASS (T) |
| CV-13 | 논리 만료·sweep·restart 주입 시간 | 36~39/56 | PASS (T) |
| CV-14 | traverse 기존 locks/access/combat AND·안전한 RuleError | 35/43/64 | PASS (T) |
| CV-15 | AdminKeyCabinet.perform_action→issue_key·실제 Entity API | 12~18/60 | PASS (T) |
| CV-16 | registry·help_contracts·기존 v14 parser/Party 회귀 | 54~55/66 | PASS (T) |
| CV-17 | 정적 content.integrity와 DB installation_errors 분리·S | 05/07~11/59 | PASS (T) |
| CV-18 | doors.publish·양쪽 접속자 after_change·기존 웹 버튼 | 42/52/65 | PASS (T) |

## 확정 D/VIEW 정책과 수용 검사 연결

정책의 원문은 Issue #49에 보존하며 이 표는 위 실제 테스트에 대한 연결이다. 결과는 RT의 자동 실행 결과를 따르고 RT-55의 제출 게이트와 #50 수동 범위는 별도로 확인한다.

| 정책 | 연결 RT |
| --- | --- |
| D01 | 28/29 |
| D02 | 27 |
| D03 | 30 |
| D04 | 32~39/56 |
| D05 | 25 |
| D06 | 20 |
| D07 | 21 |
| D08 | 12/14/60 |
| D09 | 13/15/18 |
| D10 | 31/64 |
| D11 | 44/45/50/61 |
| D12 | 40/41/57/65 |
| D13 | 07~11/59 |
| D14 | 30/53 |
| VIEW-01 | 46 |
| VIEW-02 | 47/62 |
| VIEW-03 | 47/62/63 |
| VIEW-04 | 46/62 |
| VIEW-05 | 62 |
| VIEW-06 | 48/58 |
| VIEW-07 | 49 |
| VIEW-08 | 52/65 |
| VIEW-09 | 23/45/49/50/61/63 |

## PR #56 D13 P1 추가 검사

번호와 원래 수용 조건을 변경하지 않고, 설치된 문 손상 시 전체 Bootstrap 중단에 대한 추가 실행 증거를 연결한다. `DoorTest`는 `tests.test_doors`, `DoorSchemaTests`는 `tests.test_door_schema`, `BootstrapExitTests`는 `tests.test_bootstrap_exits`의 실제 클래스다.

| 추가 검사 | 실제 메서드 | 기존 RT/CV | 확인하는 계약 |
| --- | --- | --- | --- |
| TEST-P1-01 | `tests.test_doors.DoorTest.test_p1_01_installed_typeclass_damage_is_local_after_bootstrap` | RT-10/59, CV-08/17 | 수정 전 ValueError 재현, 수정 후 원본 상태 보존·양쪽 실제 이동/조작/관찰 차단·정상 이동 |
| TEST-P1-02 | `tests.test_doors.DoorTest.test_p1_02_actual_server_start_keeps_damage_local` | RT-10/59, CV-08/17 | 실제 at_server_start의 Bootstrap·runtime·restart reconcile, 정상 조작/통과 |
| TEST-P1-03 | `tests.test_doors.DoorTest.test_p1_03_repeated_bootstrap_never_replaces_quarantined_objects` | RT-07/08/59, CV-08 | 반복 후 Door/설치 이력/모든 객체 PK·관계·Typeclass 불변 |
| TEST-P1-04 | `tests.test_doors.DoorTest.test_p1_04_normal_door_both_sides_extend_and_sweep_independently` | RT-59, D04, CV-08/10 | 회복실 양쪽 닫기/열기·실제 통과 완료+60초·경계 sweep·일반 Exit |
| TEST-P1-05/07 | `tests.test_bootstrap_exits.BootstrapExitTests.test_p1_05_p1_07_quarantined_door_does_not_bypass_global_conflicts` | RT-07/11/59, CV-08/17 | identity·Tag·Alias·미입증 endpoint 충돌 차단, 모든 DB 행·Door/이력·객체 cache·profile 보존 |
| TEST-P1-06 | `tests.test_doors.DoorTest.test_p1_06_local_relation_damage_and_unique_reference_repair` | RT-09/10/59, CV-08/17 | 목적지/위치 손상 국소 격리, 폐지 방 이전 금지, 유일 원본 속성 참조만 복원 |
| TEST-P1-06 | `tests.test_doors.DoorTest.test_p1_06_ambiguous_or_missing_installation_cannot_bypass_preflight` | RT-07/08/10/11, CV-08/17 | 원본 PK 불일치·이력 소실·이력 간 중복 소유는 전역 차단, 기존 상태 보존 |
| TEST-P1-08 | `tests.test_door_schema.DoorSchemaTests.test_p1_08_damaged_door_survives_new_process_server_start` | RT-08/10/59, CV-08/17 | 두 OS 프로세스에서 동일 격리 DB 재오픈·실제 서버 시작·영속 손상 보존·진단·정상/차단 이동 |

수정 전 재현 실패와 수정 후 결과, 경량/확장/전체 검사의 실제 명령·건수는 playtest에 기록한다. 기존 Bootstrap Typeclass·identity·Tag·방향/Alias·비관리 충돌 검사의 assertion은 유지하며 DB 스냅샷에 Door와 DoorInstallation을 추가했다. 기존 D11/D12·VIEW·Gate/Credential·일행/전투/전리품 회귀는 전체 검사로 확인한다. JavaScript는 이번 수정에서 변경하지 않는다.

## 남은 통합 게이트

RT-55는 로컬 전체 검사만으로 완료하지 않는다. 최종 커밋 Quick/Smoke·원격 CI·Ready PR·Issue 본문 PR 연결까지 실제 확인해 PR/Issue에 기록한다. 수동 실 브라우저·OS IME·복수 실세션·비색상 터미널·장기 restart 및 Cross-Issue E2E는 Issue #50에 이관한다. PR 생성은 Merge 승인이나 Issue 종료를 뜻하지 않는다.
