"""Issue #49 실제 영속 설치·권한·이동·관찰의 결정론적 회귀."""

from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from evennia import search_tag
from typeclasses.explorers import Explorer
from world import doors, rules
from world.bootstrap import build_world
from world.door_entities.models import Door, DoorInstallation
from world.multiplayer import world_change

from tests.base import WorldCommandTest
from tests.item_entity_fixture import NativeItemTest


class DoorTest(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        self.char1.location = self.rooms["hq_concourse"]
        self.char2.location = self.rooms["hq_admin_office"]
        for player in (self.char1, self.char2):
            player.db.profile = rules.new_profile()
            player.msg = Mock()
            player.push_state = Mock()
        self.enterContext(patch("typeclasses.explorers.delay"))
        self.enterContext(patch("world.doors.time", return_value=100))

    def door(self, identity="hq_admin_door"):
        return Door.objects.get(door_id=identity)

    def opened(self, identity="hq_admin_door", deadline=160):
        Door.objects.filter(door_id=identity).update(state="OPEN", auto_close_at=deadline)
        return self.door(identity)

    def test_single_state_fixed_contents_and_real_exit_pk(self):
        from typeclasses.interactables import INTERACTABLES
        self.assertEqual(Door.objects.count(), 2)
        for identity in doors.DOORS:
            door = self.door(identity)
            for obj in (door.exit_a, door.exit_b):
                self.assertEqual(obj.db.door_id, identity)
                self.assertEqual(doors.state_for_exit(obj, 100), doors.effective_door_state(identity, 100))
            self.assertEqual(doors.installation_errors(identity), [])
        self.assertEqual(self.door().state, "LOCKED")
        self.assertEqual(self.door("recovery_room_door").state, "OPEN")
        self.assertEqual(INTERACTABLES["hq_admin_key_cabinet"]["room"], "hq_lounge")

    def test_first_install_clock_and_repeat_bootstrap_preserves_state_and_pk(self):
        door = self.door("recovery_room_door")
        journal = DoorInstallation.objects.get(door_id=door.door_id)
        self.assertEqual(door.auto_close_at, journal.installed_at + 60)
        before = list(Door.objects.order_by("door_id").values())
        with patch("world.doors.time", return_value=999):
            build_world()
        self.assertEqual(list(Door.objects.order_by("door_id").values()), before)

    def test_uniqueness_and_endpoint_conflict_rejected(self):
        door = self.door()
        with self.assertRaises(IntegrityError), transaction.atomic():
            door.pk = None
            door.save(force_insert=True)
        self.assertEqual(Door.objects.count(), 2)
        record = Door.objects.get(door_id="hq_admin_door")
        data = Door.objects.values().get(pk=record.pk)
        data.pop("id")
        data.update(door_id="conflicting_fixture", exit_a_id=record.exit_b_id, exit_b_id=record.exit_a_id)
        Door.objects.create(**data)  # 반대 FK 열에 중복 결부된 비정상 데이터도 검사한다.
        self.assertEqual(doors.effective_door_state("hq_admin_door", 100), doors.UNAVAILABLE)
        build_world()
        self.assertEqual(Door.objects.count(), 3)  # 임의 선택/삭제 금지
        self.assertEqual(doors.effective_door_state("recovery_room_door", 100), "OPEN")

    def test_missing_installed_door_not_recreated_other_door_works(self):
        self.door().delete()
        self.assertTrue(DoorInstallation.objects.filter(door_id="hq_admin_door").exists())
        build_world()
        self.assertFalse(Door.objects.filter(door_id="hq_admin_door").exists())
        self.assertEqual(doors.effective_door_state("hq_admin_door", 100), doors.UNAVAILABLE)
        self.opened("recovery_room_door")
        self.assertEqual(doors.effective_door_state("recovery_room_door", 100), "OPEN")

    def test_original_exit_reference_repaired_without_state_reset(self):
        door = self.opened()
        before = (door.pk, door.exit_a_id, door.exit_b_id, door.state, door.auto_close_at)
        door.exit_a.attributes.remove("door_id")
        self.assertEqual(doors.effective_door_state(door.door_id, 100), doors.UNAVAILABLE)
        build_world()
        self.assertEqual(doors.effective_door_state(door.door_id, 100), "OPEN")
        after = self.door()
        self.assertEqual((after.pk, after.exit_a_id, after.exit_b_id, after.state, after.auto_close_at), before)

    def test_cosmetic_sync_and_lost_endpoint_never_recreated(self):
        door = self.opened()
        Door.objects.filter(pk=door.pk).update(name="옛 표시", aliases=["옛 별칭"])
        build_world()
        after = self.door()
        self.assertEqual((after.name, after.aliases), (doors.DOORS[door.door_id]["name"], doors.DOORS[door.door_id]["aliases"]))
        self.assertEqual((after.pk, after.auto_close_at), (door.pk, 160))
        original_exit = after.exit_a
        after.delete()
        original_exit.delete()
        build_world()
        self.assertFalse(any(obj.key == "동" for obj in self.rooms["hq_concourse"].exits))
        self.assertEqual(doors.effective_door_state(door.door_id, 100), doors.UNAVAILABLE)
        self.assertEqual(doors.effective_door_state("recovery_room_door", 100), "OPEN")

    def test_endpoint_destination_damage_not_reconnected(self):
        door = self.door()
        door.exit_a.destination = self.rooms["dock"]
        build_world()
        self.assertEqual(door.exit_a.destination, self.rooms["dock"])
        self.assertEqual(doors.state_for_exit(door.exit_a, 100), doors.UNAVAILABLE)
        self.assertEqual(self.door("recovery_room_door").state, "OPEN")

    def test_damaged_exit_typeclass_cannot_bypass_guard_with_engine_traverse(self):
        from world.distant_presentation import DistantViewContext, distant_appearance
        obj = self.door().exit_a
        obj.swap_typeclass("evennia.objects.objects.DefaultExit", clean_attributes=False, run_start_hooks=None)
        before = self.char1.profile_snapshot()
        self.char1.present_destination = Mock()
        obj.at_traverse(self.char1, self.rooms["hq_admin_office"])
        self.assertEqual(self.char1.zone, "hq_concourse")
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.char1.present_destination.assert_not_called()
        context = DistantViewContext(self.char1, self.char1.location, self.rooms["hq_admin_office"], obj, "동", observed_at=100)
        self.assertEqual(str(distant_appearance(context)), "그 너머는 살펴볼 수 없다.")

    def test_invalid_states_and_expiry_are_read_only(self):
        for fields in (dict(state="INVALID"), dict(state="OPEN", auto_close_at=None),
                       dict(state="CLOSED", auto_close_at=160), dict(state="LOCKED", lockable=False)):
            with self.subTest(fields=fields), world_change():
                original = list(Door.objects.values())
                Door.objects.filter(door_id="hq_admin_door").update(**fields)
                snapshot = list(Door.objects.values())
                self.assertEqual(doors.effective_door_state("hq_admin_door", 100), doors.UNAVAILABLE)
                self.assertEqual(list(Door.objects.values()), snapshot)
                for record in original:
                    Door.objects.filter(pk=record["id"]).update(**record)

    def test_bootstrap_failure_rolls_back_database_and_evennia_cache(self):
        original = (self.rooms["hq_concourse"].key, list(Door.objects.values()))
        with patch("world.doors.install_doors", side_effect=RuntimeError("fixture failure")):
            with self.assertRaises(RuntimeError):
                build_world()
        self.assertEqual((self.rooms["hq_concourse"].key, list(Door.objects.values())), original)
        self.assertEqual(doors.installation_errors("hq_admin_door"), [])

    def test_install_without_journal_does_not_adopt_or_reset_existing_record(self):
        door = self.opened()
        DoorInstallation.objects.filter(door_id=door.door_id).delete()
        before = list(Door.objects.values())
        build_world()
        self.assertEqual(list(Door.objects.values()), before)
        self.assertEqual(doors.effective_door_state(door.door_id, 100), doors.UNAVAILABLE)

    def test_no_door_exit_unchanged(self):
        obj = next(obj for obj in self.rooms["dock"].exits if obj.key == "동")
        self.assertIsNone(doors.state_for_exit(obj, 100))
        self.assertIsNone(doors.exit_block(obj, self.char1, 100))
        self.assertEqual(obj.destination, self.rooms["hq_concourse"])

    def test_doorless_room_original_snapshot(self):
        self.char1.location = self.rooms["dock"]
        expected = ("────────────────────────\n탐사대 부두\n────────────────────────\n\n"
                    "낡은 선착장 너머로 섬의 해안과 숲이 이어진다. 밧줄과 장비가 가지런히 놓여 있다.\n"
                    "정박한 배 사이로 잔물결이 일고, 먼 숲에서 새소리가 들려온다.\n\n"
                    "하늘이 맑게 개어 있다. 낮빛이 주변을 밝히고 있다.\n\n"
                    ".|.\n.o-  갈 수 있는 곳은 북, 동이다.\n...\n\n"
                    "윤대장이 낡은 지도를 펼쳐 놓고 탐사대를 기다리고 있다.")
        self.assertEqual(str(self.char1.location.return_appearance(self.char1, observed_at=100)), expected)

    def raw(self, command):
        completed = []
        self.char1.execute_cmd(command).addCallback(lambda _: completed.append(True))
        self.assertEqual(completed, [True])
        return "\n".join(str(call.args[0]) for call in self.char1.msg.call_args_list if call.args)

    def key_for(self, caller):
        from world import equipment_service
        from world.item_entities import api
        profile = caller.profile_snapshot()
        profile.update(inventory={}, equipment={slot: None for slot in profile["equipment"]})
        caller.db.profile = profile
        equipment_service.use_item_entities(caller)
        return api.create_item("hq_admin_key", owner_object=caller, location_kind="inventory")

    def test_four_registry_commands_actual_postfix_parser_and_help(self):
        from commands.doors import DOOR_COMMANDS
        from commands.help_pages import help_page
        from commands.registry import COMMANDS
        self.assertEqual([command.key for command in DOOR_COMMANDS], ["열어", "닫아", "잠궈", "풀어"])
        for command in DOOR_COMMANDS:
            self.assertIn(command, COMMANDS)
            self.assertEqual(command.aliases, [])
            self.assertEqual(len(command.help_sections), 5)
            for suffix in ("도움", "도움말"):
                output = self.raw(f"{command.key} {suffix}")
                self.assertIn("사용법", output)
                self.assertIn("실행 규칙", output)
            self.assertIsNotNone(help_page(command.key, COMMANDS))
        self.char1.location = self.rooms["hq_admin_office"]
        self.assertIn("의 잠금을 풀었다.", self.raw("서 문 풀어"))  # 내부 래치, 열쇠 없이 해제
        self.assertEqual(self.door().state, "CLOSED")
        self.assertIn("을 열었다.", self.raw("관리실문 열어"))
        self.assertEqual((self.door().state, self.door().auto_close_at), ("OPEN", 160))
        self.assertIn("을 닫았다.", self.raw("문 1 닫아"))
        self.assertEqual((self.door().state, self.door().auto_close_at), ("CLOSED", None))

    def test_target_required_index_all_hidden_and_wrong_room(self):
        for name in ("", "문 2", "문 모두", "회복실 문"):
            with self.subTest(name=name), self.assertRaises(rules.RuleError):
                doors.operate(self.char1, name, "열어", 100)
        with patch("world.observation.perceives", return_value=False):
            self.assertEqual(doors.current_doors(self.char1, 100), [])
            with self.assertRaises(rules.RuleError):
                doors.operate(self.char1, "문", "풀어", 100)
        self.assertEqual(self.door().state, "LOCKED")

    def test_all_state_transitions_key_latch_and_nonlockable(self):
        with self.assertRaises(rules.RuleError):
            doors.operate(self.char1, "문", "풀어", 100)
        self.key_for(self.char1)
        for action, state in (("풀어", "CLOSED"), ("열어", "OPEN"), ("닫아", "CLOSED"), ("잠궈", "LOCKED")):
            self.assertTrue(doors.operate(self.char1, "동 문", action, 100))
            self.assertEqual(self.door().state, state)
        doors.operate(self.char2, "문", "풀어", 100)
        with self.assertRaises(rules.RuleError):
            doors.operate(self.char2, "문", "잠궈", 100)  # 내부 잠금에도 열쇠 필수
        doors.operate(self.char2, "문", "열어", 100)
        with self.assertRaises(rules.RuleError):
            doors.operate(self.char1, "문", "잠궈", 100)
        self.char1.location = self.rooms["support_3f_e1"]
        for action in ("잠궈", "풀어"):
            with self.assertRaises(rules.RuleError):
                doors.operate(self.char1, "문", action, 100)

    def test_idempotence_failed_commands_and_peace_leave_timer_and_key_unchanged(self):
        key = self.key_for(self.char1)
        self.opened()
        original = (list(Door.objects.values()), key.pk, list(key.__class__.objects.values()))
        self.assertFalse(doors.operate(self.char1, "문", "열어", 130))
        with self.assertRaises(rules.RuleError):
            doors.operate(self.char1, "문", "잠궈", 130)
        self.char1.db.profile = {**self.char1.profile_snapshot(), "combat_target": 999}
        for action in ("열어", "닫아", "잠궈", "풀어"):
            with self.assertRaises(rules.RuleError):
                doors.operate(self.char1, "없는 문", action, 130)
        self.assertEqual((list(Door.objects.values()), key.pk, list(key.__class__.objects.values())), original)

    def test_operation_outer_savepoint_rollback_and_postcommit_both_endpoints(self):
        self.connect_character(self.char1)
        self.connect_character(self.char2)
        with self.assertRaises(RuntimeError), world_change():
            doors.operate(self.char2, "문", "풀어", 100)
            self.char2.msg.assert_not_called()
            self.char1.push_state.assert_not_called()
            raise RuntimeError("rollback")
        self.assertEqual(self.door().state, "LOCKED")
        with world_change():
            try:
                with world_change():
                    doors.operate(self.char2, "문", "풀어", 100)
                    raise RuntimeError("savepoint")
            except RuntimeError:
                pass
        self.char2.msg.assert_not_called()
        with world_change():
            doors.operate(self.char2, "문", "풀어", 100)
            self.char2.msg.assert_not_called()
        self.char2.msg.assert_called_once()
        self.char1.push_state.assert_called_once()
        self.char2.push_state.assert_called_once()

    def test_logical_expiry_readonly_boundary_and_sweep(self):
        self.opened()
        before = list(Door.objects.values())
        self.assertEqual(doors.effective_door_state("hq_admin_door", 159.999), "OPEN")
        self.assertEqual(doors.effective_door_state("hq_admin_door", 160), "CLOSED")
        self.assertEqual(doors.effective_door_state("hq_admin_door", 200), "CLOSED")
        self.assertEqual(list(Door.objects.values()), before)
        doors.reconcile_doors(160)
        self.assertEqual((self.door().state, self.door().auto_close_at), ("CLOSED", None))

    def test_real_traversal_extends_at_completion_and_consecutive_crossings(self):
        door = self.opened()
        self.char1.present_destination = Mock()
        clock = {"now": 100}
        original = self.char1.at_post_move
        def completed(*args, **kwargs):
            original(*args, **kwargs)
            clock["now"] = 110
        with patch("world.doors.time", side_effect=lambda: clock["now"]), patch.object(self.char1, "at_post_move", side_effect=completed):
            self.assertTrue(doors.traverse(door.exit_a, self.char1, self.rooms["hq_admin_office"]))
        self.assertEqual(self.char1.location, self.rooms["hq_admin_office"])
        self.assertIn("hq_admin_office", self.char1.profile_snapshot()["visited"])
        self.assertEqual(self.door().auto_close_at, 170)
        with patch("world.doors.time", return_value=150):
            self.assertTrue(door.exit_b.at_traverse(self.char1, self.rooms["hq_concourse"]))
        self.assertEqual(self.door().auto_close_at, 210)
        self.assertEqual(self.char1.present_destination.call_count, 2)

    def test_multiple_players_direction_aliases_share_completion_timer(self):
        self.opened()
        for player in (self.char1, self.char2):
            player.present_destination = Mock()
        with patch("world.doors.time", return_value=110):
            self.raw("e")
        self.assertEqual(self.char1.zone, "hq_admin_office")
        self.assertEqual(self.door().auto_close_at, 170)
        completed = []
        with patch("world.doors.time", return_value=120):
            self.char2.execute_cmd("w").addCallback(lambda _: completed.append(True))
        self.assertEqual(completed, [True])
        self.assertEqual(self.char2.zone, "hq_concourse")
        self.assertEqual(self.door().auto_close_at, 180)
        self.assertEqual(self.char1.present_destination.call_count, 1)
        self.assertEqual(self.char2.present_destination.call_count, 1)

    def test_real_post_move_hook_error_rolls_back_visited_and_callbacks(self):
        door = self.opened()
        original = self.char1.at_post_move
        before = self.char1.profile_snapshot()
        self.char1.present_destination = Mock()
        def failed_hook(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("post-move fixture failure")
        with patch.object(self.char1, "at_post_move", side_effect=failed_hook), self.assertRaises(rules.RuleError):
            doors.traverse(door.exit_a, self.char1, self.rooms["hq_admin_office"])
        self.assertEqual(self.char1.zone, "hq_concourse")
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertEqual(self.door().auto_close_at, 160)
        self.char1.present_destination.assert_not_called()
        self.char1.push_state.assert_not_called()

    def test_traversal_expiry_at_completion_rolls_back_location_visited_and_messages(self):
        door = self.opened()
        before = self.char1.profile_snapshot()
        self.char1.present_destination = Mock()
        clock = {"now": 159}
        original = self.char1.at_post_move
        def completed(*args, **kwargs):
            original(*args, **kwargs)
            clock["now"] = 160
        with patch("world.doors.time", side_effect=lambda: clock["now"]), patch.object(self.char1, "at_post_move", side_effect=completed), self.assertRaises(rules.RuleError):
            doors.traverse(door.exit_a, self.char1, self.rooms["hq_admin_office"])
        self.assertEqual(self.char1.location, self.rooms["hq_concourse"])
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertEqual(self.door().auto_close_at, 160)
        self.char1.present_destination.assert_not_called()

    def test_move_false_hook_exception_and_wrong_destination_rollback(self):
        door = self.opened()
        for hook in (Mock(return_value=False), Mock(side_effect=RuntimeError("hook"))):
            with patch.object(self.char1, "move_to", hook), self.assertRaises((rules.RuleError, RuntimeError)):
                doors.traverse(door.exit_a, self.char1, self.rooms["hq_admin_office"])
            self.assertEqual(self.char1.zone, "hq_concourse")
            self.assertEqual(self.door().auto_close_at, 160)
        original = self.char1.at_post_move
        def wrong_destination(*args, **kwargs):
            original(*args, **kwargs)
            self.char1.location = self.rooms["dock"]
        with patch.object(self.char1, "at_post_move", side_effect=wrong_destination), self.assertRaises(rules.RuleError):
            doors.traverse(door.exit_a, self.char1, self.rooms["hq_admin_office"])
        self.assertEqual(self.char1.zone, "hq_concourse")
        self.char1.msg.assert_not_called()

    def test_actual_exit_locks_combat_closed_and_target_mismatch_rejected(self):
        door = self.opened()
        for lock in ("cmd:false()", "traverse:false()"):
            door.exit_a.locks.add(lock)
            self.assertFalse(door.exit_a.at_traverse(self.char1, self.rooms["hq_admin_office"]))
            self.assertEqual(self.char1.zone, "hq_concourse")
            door.exit_a.locks.add(lock.split(":")[0] + ":all()")
        self.char1.db.profile = {**self.char1.profile_snapshot(), "combat_target": 999}
        self.assertFalse(door.exit_a.at_traverse(self.char1, self.rooms["hq_admin_office"]))
        self.char1.db.profile = rules.new_profile()
        with self.assertRaises(rules.RuleError):
            doors.traverse(door.exit_a, self.char1, self.rooms["dock"])
        doors.operate(self.char1, "문", "닫아", 100)
        self.assertFalse(door.exit_a.at_traverse(self.char1, self.rooms["hq_admin_office"]))
        self.assertIsNone(self.door().auto_close_at)

    def test_move_outer_savepoint_rollback_and_postcommit_only(self):
        door = self.opened()
        self.char1.present_destination = Mock()
        with self.assertRaises(RuntimeError), world_change():
            doors.traverse(door.exit_a, self.char1, self.rooms["hq_admin_office"])
            self.char1.present_destination.assert_not_called()
            raise RuntimeError("outer")
        with world_change():
            try:
                with world_change():
                    doors.traverse(door.exit_a, self.char1, self.rooms["hq_admin_office"])
                    self.char1.present_destination.assert_not_called()
                    raise RuntimeError("nested")
            except RuntimeError:
                pass
        self.assertEqual(self.char1.zone, "hq_concourse")
        self.char1.present_destination.assert_not_called()
        with world_change():
            doors.traverse(door.exit_a, self.char1, self.rooms["hq_admin_office"])
            self.char1.present_destination.assert_not_called()
        self.char1.present_destination.assert_called_once()

    def test_late_sweep_restart_and_close_then_move_are_serial(self):
        from world.lifecycle import reconcile_world
        self.opened(deadline=300)
        doors.reconcile_doors(160)  # 이전 예약 시각의 늦은 tick은 새 예약을 지우지 않는다.
        self.assertEqual(self.door().auto_close_at, 300)
        reconcile_world(restart=True, now=200)
        self.assertEqual((self.door().state, self.door().auto_close_at), ("OPEN", 300))
        doors.operate(self.char1, "문", "닫아", 210)
        self.assertFalse(self.door().exit_a.at_traverse(self.char1, self.rooms["hq_admin_office"]))
        self.assertEqual(self.char1.zone, "hq_concourse")

    def test_closed_locked_expired_corrupt_block_all_live_observation_paths(self):
        from world.distant_presentation import DistantViewContext, distant_appearance
        from world.exit_presentation import exit_entries
        from world.state import multiplayer_state
        self.char2.key = "내부전용정보"
        self.char2.db.distant_visible = True
        door = self.door()
        context = DistantViewContext(self.char1, self.char1.location, self.char2.location, door.exit_a, "동", observed_at=160)
        for state, deadline in (("CLOSED", None), ("LOCKED", None), ("OPEN", 160), ("BROKEN", None)):
            Door.objects.filter(pk=door.pk).update(state=state, auto_close_at=deadline)
            before = list(Door.objects.values())
            self.assertFalse(door.exit_a.can_observe_through(context))
            for output in (door.exit_a.return_appearance(self.char1, observed_at=160), distant_appearance(context),
                           context.target_room.return_distant_appearance(context)):
                self.assertNotIn(self.char2.key, str(output))
                self.assertNotIn("책상", str(output))
            entries = exit_entries(self.char1, observed_at=160)
            entry = next(e for e in entries if e["name"] == "동")
            self.assertFalse(entry["can_move"])
            self.assertEqual(entry["destination_name"], "미탐사")
            self.assertNotIn(self.char2.key, str(multiplayer_state(self.char1, 160)))
            self.assertEqual(list(Door.objects.values()), before)
        self.opened(deadline=300)
        self.assertTrue(door.exit_a.can_observe_through(context))
        self.assertIn("탐사자 한 명", str(distant_appearance(context)))  # 기존 원거리 익명 표시는 유지한다.

    def test_room_sentence_position_compass_preserved_and_hidden_door(self):
        from world.content import ROOMS
        from world.exit_presentation import exit_diagram, exit_entries
        output = str(self.char1.location.return_appearance(self.char1, observed_at=100))
        self.assertEqual(output.count("동쪽 관리실 문은 잠겨 있다."), 1)
        self.assertIn(ROOMS[self.char1.zone]["desc"] + "\n동쪽 관리실 문은 잠겨 있다.\n\n", output)
        self.assertIn(str(exit_diagram(exit_entries(self.char1, observed_at=100))), output)
        with patch("world.observation.perceives", return_value=False):
            hidden = str(self.char1.location.return_appearance(self.char1, observed_at=100))
        self.assertNotIn("관리실 문", hidden)

    def test_individual_look_direction_actual_exit_and_object_collision(self):
        from evennia import create_object
        self.enterContext(patch("commands.character.time", return_value=100))
        for raw in ("관리실 문 봐", "관리실문 봐", "동 문 봐", "문 1 봐", "문 봐"):
            self.char1.msg.reset_mock()
            self.assertIn("동쪽 관리실 문은 잠겨 있다.", self.raw(raw))
        self.char1.msg.reset_mock()
        self.assertIn("잠겨", self.raw("동 봐"))
        other = create_object("typeclasses.objects.Object", key="관리실 문", location=self.char1.location)
        self.char1.msg.reset_mock()
        self.assertIn("모호", self.raw("관리실 문 봐"))
        self.char1.msg.reset_mock()
        self.assertIn("관리실 문", self.raw("동 문 봐"))
        other.delete()
        self.char1.location = self.rooms["dock"]
        ordinary = create_object("typeclasses.objects.Object", key="관리실 문", location=self.char1.location)
        ordinary.db.desc = "문 이름을 가진 일반 물건이다."
        self.char1.msg.reset_mock()
        self.assertIn(ordinary.db.desc, self.raw("관리실 문 봐"))  # 실제 Door가 없으면 기존 객체 조회를 보존한다.

    def test_multiple_door_selector_direction_order_and_ambiguity(self):
        # 구조 손상으로 같은 Room에 옮겨진 endpoint도 감지/정렬은 안전하게 처리하고 조작은 차단한다.
        recovery = self.door("recovery_room_door")
        recovery.exit_a.location = self.char1.location
        targets = doors.current_doors(self.char1, 100)
        self.assertEqual([target.direction for target in targets], ["북", "동"])
        with self.assertRaises(rules.RuleError):
            doors.resolve_door(self.char1, "문", "열어", 100)
        self.assertEqual(doors.resolve_door(self.char1, "문 2", "닫아", 100).identity, "hq_admin_door")
        self.assertEqual(doors.resolve_door(self.char1, "북 문", "닫아", 100).identity, "recovery_room_door")
        with self.assertRaises(rules.RuleError):
            doors.operate(self.char1, "북 문", "닫아", 100)

    def test_visited_map_is_structural_unchanged_across_door_states(self):
        from commands.character import Map
        from world.exit_presentation import exit_entries
        self.char1.db.profile = {**self.char1.profile_snapshot(), "visited": ["hq_concourse", "hq_admin_office"]}
        command = Map()
        command.caller = self.char1
        outputs = []
        for state, deadline in (("LOCKED", None), ("OPEN", 300), ("CLOSED", None)):
            Door.objects.filter(door_id="hq_admin_door").update(state=state, auto_close_at=deadline)
            self.char1.msg.reset_mock()
            with patch("commands.character.time", return_value=100):
                command.run()
            outputs.append(str(self.char1.msg.call_args.args[0]))
            self.assertEqual(next(e for e in exit_entries(self.char1, observed_at=100) if e["name"] == "동")["destination_name"], "본부 관리실")
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[1], outputs[2])
        self.assertNotIn("잠겨", outputs[0])
        self.assertNotIn("300", outputs[0])

    def test_web_existing_interactables_protocol_stale_buttons_and_expired_state(self):
        from world.exit_presentation import exit_entries
        from world.state import multiplayer_state
        self.opened()
        row = next(row for row in multiplayer_state(self.char1, 100)["interactables"] if row["name"] == "관리실 문")
        self.assertEqual(row["actions"], [{"label": "닫아", "command": "동 문 닫아"}])
        before = list(Door.objects.values())
        expired = next(row for row in multiplayer_state(self.char1, 160)["interactables"] if row["name"] == "관리실 문")
        self.assertEqual(expired["actions"], [{"label": "열어", "command": "동 문 열어"}])
        self.assertFalse(next(e for e in exit_entries(self.char1, observed_at=160) if e["name"] == "동")["can_move"])
        self.assertEqual(list(Door.objects.values()), before)
        doors.operate(self.char1, "문", "닫아", 100)
        self.assertFalse(self.door().exit_a.at_traverse(self.char1, self.rooms["hq_admin_office"]))
        with patch("world.observation.perceives", return_value=False):
            self.assertNotIn("관리실 문", str(multiplayer_state(self.char1, 100)["interactables"]))

    def test_postcommit_push_failure_does_not_undo_state_or_move(self):
        self.connect_character(self.char1)
        self.char1.push_state.side_effect = RuntimeError("wire failure")
        with self.assertLogs("world.doors", level="ERROR"):
            doors.operate(self.char2, "문", "풀어", 100)
        self.assertEqual(self.door().state, "CLOSED")
        with self.assertLogs("world.doors", level="ERROR"):
            doors.operate(self.char1, "문", "열어", 100)
        self.char1.present_destination = Mock()
        with self.assertRaises(RuntimeError):  # 기존 이동 callback의 전송 실패도 이미 커밋된 DB를 되돌리지 않는다.
            doors.traverse(self.door().exit_a, self.char1, self.rooms["hq_admin_office"])
        self.assertEqual(self.char1.zone, "hq_admin_office")
        self.assertEqual(self.door().auto_close_at, 160)

    def test_recovery_room_both_sides_free_reopen_and_original_bed(self):
        bed = search_tag("infirmary_bed", category="primal_interactable")[0]
        original = bed.pk, bed.location.pk
        self.char1.location = self.rooms["support_3f_e1"]
        doors.operate(self.char1, "북 문", "닫아", 100)
        for origin, direction, target in (("support_3f_e1", "북", "recovery_room"), ("recovery_room", "남", "support_3f_e1")):
            self.char1.location = self.rooms[origin]
            doors.operate(self.char1, direction + " 문", "열어", 100)
            self.char1.present_destination = Mock()
            obj = next(obj for obj in self.char1.location.exits if obj.key == direction)
            self.assertTrue(obj.at_traverse(self.char1, self.rooms[target]))
            doors.operate(self.char1, "문", "닫아", 100)
        self.assertEqual((bed.pk, bed.location.pk), original)
        self.char1.location = bed.location
        profile = self.char1.profile_snapshot()
        self.char1.db.profile = {**profile, "hp": 1, "mental": 1}
        bed.perform_action(self.char1, "휴식")
        recovered = self.char1.profile_snapshot()
        self.assertGreater(recovered["hp"], 1)
        self.assertGreater(recovered["mental"], 1)

    def test_gate_and_credential_and_open_door_do_not_bypass_each_other(self):
        from world.access import can_enter
        self.opened()
        with patch("world.access.can_enter", return_value=False), patch("world.access.entry_message", return_value="출입할 수 없습니다."):
            self.assertFalse(self.door().exit_a.at_traverse(self.char1, self.rooms["hq_admin_office"]))
        self.assertEqual(self.door().auto_close_at, 160)
        self.assertFalse(can_enter(self.char1, self.rooms["outpost_weapon"]))
        from world.content import ROOMS
        admin = {**ROOMS["hq_admin_office"], "requires": {"quest": "tower", "flag": "completed", "observe_message": "그 너머는 살펴볼 수 없다."}}
        from world.distant_presentation import DistantViewContext
        with patch.dict(ROOMS, {"hq_admin_office": admin}):
            context = DistantViewContext(self.char1, self.char1.location, self.rooms["hq_admin_office"], self.door().exit_a, "동", observed_at=100)
            self.assertFalse(self.door().exit_a.can_observe_through(context))

    def test_help_existing_five_and_v14_personal_commands_party_registry(self):
        from commands.help_pages import help_page
        from commands.party import PARTY_COMMANDS
        from commands.registry import COMMANDS
        for key in ("조사", "봐", "출구", "지도", "정보"):
            output = str(help_page(key, COMMANDS))
            for title in ("사용법", "예시", "실행 규칙", "제한", "관련 도움말"):
                self.assertIn(title, output)
        self.assertTrue(all(command in COMMANDS for command in PARTY_COMMANDS))
        self.assertEqual(len(PARTY_COMMANDS), 16)
        self.assertEqual(rules.PROFILE_VERSION, 14)
        self.char1.location = self.rooms["hq_admin_office"]
        self.raw("문준비 서 문 풀어, 서 문 열어 해 줄임말")
        self.raw("문준비")
        self.assertEqual(self.door().state, "OPEN")

    def test_party_member_movement_preserves_tactics_and_combat_restriction(self):
        from typeclasses.parties import invite, respond
        self.connect_character(self.char1)
        self.connect_character(self.char2)
        party = invite(self.char1, self.char2, now=100)
        respond(self.char2, True, now=101)
        party.set_defender(self.char1, self.char2)
        before = party.state()
        self.opened()
        for player, obj, destination in ((self.char1, self.door().exit_a, "hq_admin_office"),
                                         (self.char2, self.door().exit_b, "hq_concourse")):
            player.present_destination = Mock()
            self.assertTrue(obj.at_traverse(player, self.rooms[destination]))
        self.assertEqual(party.state(), before)
        self.char2.db.profile = {**self.char2.profile_snapshot(), "combat_target": 999}
        profile = self.char2.profile_snapshot()
        self.assertFalse(self.door().exit_a.at_traverse(self.char2, self.rooms["hq_admin_office"]))
        self.assertEqual(self.char2.zone, "hq_concourse")
        self.assertEqual(self.char2.profile_snapshot(), profile)
        self.assertEqual(party.state(), before)


class DoorKeyTests(NativeItemTest):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        build_world()

    def setUp(self):
        super().setUp()
        from world.bootstrap import get_room
        self.cabinet = search_tag("hq_admin_key_cabinet", category="primal_interactable")[0]
        for player in (self.char1, self.char2):
            player.location = get_room("hq_lounge")
            player.msg = Mock()

    def test_actual_cabinet_free_issue_duplicate_reissue_and_per_owner(self):
        from world.door_keys import owned_key
        credits = self.char1.profile_snapshot()["credits"]
        key = self.cabinet.perform_action(self.char1, "조사")
        self.assertEqual((key.definition_id, key.quantity, key.location_kind, key.unique_scope_key),
                         ("hq_admin_key", 1, "inventory", f"{self.char1.pk}:hq_admin_key"))
        self.assertEqual(owned_key(self.char1).pk, key.pk)
        self.assertEqual(self.char1.profile_snapshot()["credits"], credits)
        with self.assertRaises(rules.RuleError):
            self.cabinet.perform_action(self.char1, "조사")
        other = self.cabinet.perform_action(self.char2, "조사")
        self.assertNotEqual(other.pk, key.pk)
        key.delete()  # 관리자/실제 소실 이후 재발급 경로; 사용자 소각은 허용하지 않는다.
        self.assertNotEqual(self.cabinet.perform_action(self.char1, "조사").pk, key.pk)

    def test_unique_scope_and_repeated_session_request(self):
        from world.item_entities import api
        from world.item_entities.models import ItemEntity
        first = self.cabinet.perform_action(self.char1, "조사")
        with self.assertRaises((ValidationError, IntegrityError)), world_change():
            api.create_item("hq_admin_key", location_kind="inventory", owner_object=self.char1)
        for _ in range(2):
            with self.assertRaises(rules.RuleError):
                self.cabinet.perform_action(self.char1, "조사")
        self.assertEqual(list(ItemEntity.objects.filter(definition_id="hq_admin_key").values_list("pk", flat=True)), [first.pk])

    def test_every_operation_blocked_at_actual_api_and_state_preserved(self):
        from world.item_entities import api
        from world.item_entities.policy import TREE_OPERATION_SCOPES, can_item_operation
        key = self.cabinet.perform_action(self.char1, "조사")
        snapshot = self.atomic_state()
        for operation in TREE_OPERATION_SCOPES:
            with self.subTest(operation=operation):
                self.assertFalse(can_item_operation(key, operation))
                with self.assertRaises(ValidationError):
                    api.move_item(key, location_kind="inventory", owner_object=self.char2, operation=operation)
                self.assertEqual(self.atomic_state(), snapshot)

    def test_corrupt_ownership_not_duplicated_and_combat_or_remote_denied(self):
        from world.item_entities.models import ItemEntity
        key = self.cabinet.perform_action(self.char1, "조사")
        ItemEntity.objects.filter(pk=key.pk).update(unique_scope_key=None)
        with self.assertRaises(rules.RuleError):
            self.cabinet.perform_action(self.char1, "조사")
        self.assertEqual(ItemEntity.objects.filter(definition_id="hq_admin_key").count(), 1)
        self.char2.db.profile = {**self.char2.profile_snapshot(), "combat_target": 999}
        with self.assertRaises(rules.RuleError):
            self.cabinet.perform_action(self.char2, "조사")
        self.char2.location = self.room1
        with self.assertRaises(rules.RuleError):
            self.cabinet.perform_action(self.char2, "조사")

    def test_information_inventory_and_credential_are_separate_read_only(self):
        from world.access import can_enter
        from world.bootstrap import get_room
        from world.door_keys import owned_key
        from world.item_information import item_information
        self.cabinet.perform_action(self.char1, "조사")
        self.assertIsNotNone(owned_key(self.char1))
        snapshot = self.atomic_state()
        output = str(item_information(self.char1, "관리실 열쇠", 100))
        self.assertIn("종류: 열쇠", output)
        self.assertIn("소유자별 하나", output)
        self.assertIn("보관: 제한", output)
        self.assertEqual(self.char1.profile_snapshot()["inventory"]["hq_admin_key"], 1)
        self.assertFalse(can_enter(self.char1, get_room("outpost_weapon")))
        self.assertEqual(self.atomic_state(), snapshot)

    def test_key_issue_outer_and_savepoint_rollback_discard_notifications(self):
        from world.item_entities.models import ItemEntity
        self.char1.msg.reset_mock()
        self.char1.push_state.reset_mock()
        with self.assertRaises(RuntimeError), world_change():
            self.cabinet.perform_action(self.char1, "조사")
            self.char1.msg.assert_not_called()
            self.char1.push_state.assert_not_called()
            raise RuntimeError("outer rollback")
        self.assertFalse(ItemEntity.objects.filter(definition_id="hq_admin_key").exists())
        with world_change():
            try:
                with world_change():
                    self.cabinet.perform_action(self.char1, "조사")
                    raise RuntimeError("inner rollback")
            except RuntimeError:
                pass
        self.char1.msg.assert_not_called()
        self.assertFalse(ItemEntity.objects.filter(definition_id="hq_admin_key").exists())

    def test_actual_investigate_command_defers_all_web_updates_until_commit(self):
        from commands.world_actions import Investigate
        from world.item_entities.models import ItemEntity
        for player in (self.char1, self.char2):
            self.connect_character(player)
            player.msg.reset_mock()
            player.push_state.reset_mock()
        command = Investigate()
        command.caller, command.args = self.char1, "관리실 열쇠함"
        with self.assertRaises(RuntimeError), world_change():
            command.func()
            self.char1.msg.assert_not_called()
            self.char1.push_state.assert_not_called()
            self.char2.push_state.assert_not_called()
            raise RuntimeError("outer command rollback")
        self.assertFalse(ItemEntity.objects.filter(definition_id="hq_admin_key").exists())
        with world_change():
            command.func()
            self.char1.msg.assert_not_called()
            self.char1.push_state.assert_not_called()
            self.char2.push_state.assert_not_called()
        self.char1.msg.assert_called_once()
        self.assertTrue(self.char1.push_state.called)
        self.char2.push_state.assert_called_once()
