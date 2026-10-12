"""동결 T50 ID → 실제 Assertion 위치. 존재 감사와 실행 PASS를 혼동하지 않는다."""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 이슈는 그룹 범위를 정의한다. 그룹 내부 번호는 아래 세부 검증 책임에 고정한다.
# 한 항목의 추가 경계는 해당 모듈 전체 회귀 및 브라우저 E2E에서 검증한다.
GROUPS = {
    'CMD': [
        ('전체 Command/Alias/실제 Help', 'all_registry_aliases_actual_help_dispatch_and_semantics'),
        ('제거 이름·인벤토리 Alias', 'inventory_aliases_and_removed_commands_are_not_active'),
        ('방향 및 시체 단축어 실제 이동/권리', 'phase_a'),
        ('이름·번호·모두·조사', 'default_index_all_look_and_attack_ordering'),
        ('실제 잠긴 CmdSet 개인 fallback 금지', 'locked_actual_commands_never_fall_back_to_personal'),
        ('묶음 이동 뒤 실제 CmdSet', 'dynamic_room_cmdsets_override_snapshot_only_when_actually_selected')],
    'ALIAS': [
        ('v11~v14 호환 및 읽기 전용', 'every_supported_version_preserves_gameplay_and_only_safe_lists_convert'),
        ('예약 충돌·원본 보존', 'phase_a'),
        ('변수 $1~9/$*/$$', 'variable_binding_and_single_pass_literals'),
        ('깊이5/6 실제 선택', 'depth_five_and_six_are_checked_on_actual_selected_path'),
        ('하위10/11', 'attempts_include_every_leaf_and_stop_before_eleventh'),
        ('1000자·부분 실행', 'final_character_sum_and_direct_bundle_input_length_boundaries'),
        ('전체 삭제 직접 2단계·간접 금지', 'sequence_cannot_request_and_confirm_all_deletion')],
    'GAME': [
        ('Native 정보 불변', 'phase_b'),
        ('장비·UUID·웹', 'command_selector_and_presentation_agree_with_web'),
        ('탄창·잔탄·소유 권리', 'reload_empty_missing_incompatible_foreign_and_explicit'),
        ('열쇠 정보 읽기·Credential 별개', 'information_inventory_and_credential_are_separate_read_only'),
        ('Lv1/99/100/MAX 정확 의료 산식', 'medical_level_boundaries_exact_formula_and_failure_invariance'),
        ('회복 저장 실패 rollback', 'phase_c'),
        ('무료 침대 실제 정책', 'recovery_room_both_sides_free_reopen_and_original_bed'),
        ('쏴 즉시 타격 없음', 'phase_a'),
        ('실제 총기 전투·탄약 rollback', 'live_enemy_path_commits_shot_and_rolls_back_ammo_failure')],
    'NPC': [
        ('22 NPC 실제 객체·조회 불변', 'content_22_discovery_and_no_legacy_action'),
        ('말/작은따옴표 원문', 'say_quote_equivalence_and_original'),
        ('NPC 대상 모호성/번호', 'fallback_ambiguity_and_numbers'),
        ('공개 같은 원문·개인 강조', 'public_same_raw_independent_highlights_and_context'),
        ('개인 활성 키워드', 'personal_guides_semantics_keep_plain_text_and_separate_chat'),
        ('실제 임무·보상 rollback', 'exact_transitions_private_reward_and_rollback'),
        ('실제 버튼 토큰·중복 지급', 'stale_action_tokens_cannot_report_twice_before_commit'),
        ('세션·소유권·조회 토큰', 'structured_input_checks_puppet_and_readonly_tokens')],
    'MSG': [
        ('개인/답장/공개와 최근상대', 'private_accept_reply_and_public_does_not_change_peer'),
        ('오프라인/차단 영속·실패불변', 'offline_block_persistent_and_failed_send_unchanged'),
        ('300자/ANSI/제어/동명이인', 'input_offline_ambiguity_and_limits'),
        ('실패 전송 부재·rollback', 'transaction_failure_sends_nothing'),
        ('CmdSet page/whisper 우회 금지', 'actual_cmdset_no_page_alias_and_help_dispatch'),
        ('일행대화와 제삼자/다른방', 'rt28_rt29_private_members_cross_rooms_and_validation')],
    'PARTY': [
        ('16개 정식 명령·Alias·Help', 'rt01_all_sixteen_commands_aliases_help_and_old_verbs_absent'),
        ('초청·요청60초', 'rt05_rt07_rt08_rt09_rt10_ttl_and_independent_requests'),
        ('4인 제한·재검증', 'rt04_rt07_capacity_rechecked_and_requests_single'),
        ('리더 위임·오프라인 초청', 'rt06_rt11_rt27_invite_survives_offline_and_transfer'),
        ('마지막 Puppet·다중세션·즉시승계', 'rt23_reload_multisession_and_unpuppet_event'),
        ('600초 정확 tick·오래된 요청', 'rt19_rt20_rt25_tick_boundary_order_and_stale_recheck'),
        ('해체확인 snapshot·만료', 'rt13_rt14_dissolve_snapshot_ttl_and_stale_target'),
        ('일행 비공개 재검증', 'rt30_delivery_rechecks_departed_recipient_and_sender'),
        ('공동 공격 기존 예약 유지', 'rt31_rt32_rt34_partial_attack_preserves_existing_schedule'),
        ('영속 방어·실제 tick', 'rt38_enemy_tick_redirects_without_threat_damage_or_interval_change'),
        ('Native/Legacy 해체후 실지급', 'rt15_rt16_native_item_actual_pickup_after_dissolve_and_rollback'),
        ('다수 개인 화폐 및 postcommit', 'test05_test07_native_nested_multiple_recipients_commit_once')],
    'DOOR': [
        ('첫 설치·양방향 PK/SSOT', 'single_state_fixed_contents_and_real_exit_pk'),
        ('열쇠·래치·잠금불가 상태전이', 'all_state_transitions_key_latch_and_nonlockable'),
        ('열쇠 발급/재발급/개인 유일성', 'actual_cabinet_free_issue_duplicate_reissue_and_per_owner'),
        ('열쇠 금지 하위API', 'every_operation_blocked_at_actual_api_and_state_preserved'),
        ('59.999/60 만료 조회 불변', 'logical_expiry_readonly_boundary_and_sweep'),
        ('실제 통과 완료기준 연장', 'real_traversal_extends_at_completion_and_consecutive_crossings'),
        ('실패통과 위치/알림rollback', 'traversal_expiry_at_completion_rolls_back_location_visited_and_messages'),
        ('실시간 정보보호 모든경로', 'closed_locked_expired_corrupt_block_all_live_observation_paths'),
        ('나침반/지도 공개 불변', 'visited_map_is_structural_unchanged_across_door_states'),
        ('D13 장애 국소·정상 Door/Exit', 'p1_01_installed_typeclass_damage_is_local_after_bootstrap')],
    'HELP': [
        ('전수 실제 alias Help dispatcher', 'all_registry_aliases_actual_help_dispatch_and_semantics'),
        ('줄임말 6절·Semantic Text', 'four_pages_have_same_sections_order_semantics_and_no_double_frame'),
        ('변수/한도/우선순위 안내', 'personal_help_contains_management_variables_limits_and_priority'),
        ('전역/개인 삭제 정책 안내', 'deletion_and_global_help_do_not_confuse_personal_and_system'),
        ('Registry로부터 생성·관련 Help', 'help_uses_registry_not_a_separate_command_list'),
        ('웹/실제 객체·권한', 'web_existing_interactables_protocol_stale_buttons_and_expired_state'),
        ('사용법 역할은 실제metadata', 'usage_styles_only_declared_action_metadata')],
    'DATA': [
        ('Fresh DB·기존 스키마 설치', 'existing_schema_preserves_profile_native_items_and_all_old_rows'),
        ('v11~14 전체 프로필 보존', 'every_supported_version_preserves_gameplay_and_only_safe_lists_convert'),
        ('Item UUID/양/sequence', 'creation_persists_opaque_identity_and_definition_state'),
        ('중첩 전리품 상위rollback', 'test01_legacy_item_outer_rollback_has_no_success_effects'),
        ('Native 저장/Claim/화폐 상위rollback', 'test03_native_common_command_outer_rollback_preserves_all_assets'),
        ('Savepoint 콜백 폐기', 'test06_native_failed_savepoint_has_no_callbacks_after_outer_success'),
        ('네트워크 오류 뒤 Commit 유지', 'postcommit_push_failure_does_not_undo_state_or_move'),
        ('Door 손상/설치이력·독립 새프로세스', 'p1_08_damaged_door_survives_new_process_server_start'),
        ('세계 Bootstrap DB/캐시 원자성', 'bootstrap_failure_rolls_back_database_and_evennia_cache')],
}


def records():
    methods = {}
    for folder in ('game/tests', 'game/world'):
        for path in (ROOT/folder).glob('test_*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for cls in tree.body:
                if isinstance(cls, ast.ClassDef):
                    for method in cls.body:
                        if isinstance(method, ast.FunctionDef) and method.name.startswith('test_'):
                            methods.setdefault(method.name[5:], []).append((path, cls.name, method))
    result = []
    for group, entries in GROUPS.items():
        for number, (requirement, name) in enumerate(entries, 1):
            found = methods.get(name, [])
            if len(found) != 1:
                raise ValueError(f'유일하지 않은 실제 테스트 {name}')
            path, cls, method = found[0]
            assertions = [node for node in ast.walk(method) if isinstance(node, ast.Call)
                          and isinstance(node.func, ast.Attribute) and node.func.attr.startswith('assert')]
            # 스키마 테스트는 격리 subprocess의 assert를 호출하는 helper에 위임한다.
            delegated = name in ('existing_schema_preserves_profile_native_items_and_all_old_rows',
                                 'p1_08_damaged_door_survives_new_process_server_start',
                                 'test01_legacy_item_outer_rollback_has_no_success_effects')
            if not assertions and not delegated:
                raise ValueError(f'Assertion 없는 검증 {name}')
            module = str(path.relative_to(ROOT/'game')).replace('\\', '/').removesuffix('.py').replace('/', '.')
            result.append({'id': f'T50-{group}-{number:02}', 'requirement': requirement,
                           'test': f'{module}.{cls}.test_{name}', 'source': path.relative_to(ROOT).as_posix(),
                           'line': method.lineno, 'assertions': len(assertions), 'delegated': delegated, 'execution': 'NOT RUN'})
    return result


if __name__ == '__main__':
    # 이 감사는 경로/Assertion 연결만 검사한다. 게임 기능 PASS는 실제 Suite 결과다.
    if sys.argv[1:] == ['--labels']:
        print('\n'.join(sorted({row['test'] for row in records()})))
    else:
        print(json.dumps({'mapped': len(records()), 'execution': 'NOT RUN — 실제 test Job 근거 필요'}, ensure_ascii=False))
