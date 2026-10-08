"""실제 출구 공유 목록·목적지 공개·읽기 전용 명령 및 웹 상태 경계."""

from copy import deepcopy
from unittest.mock import Mock, patch

from evennia import create_object
from evennia.objects.models import ObjectDB
from evennia.typeclasses.models import Attribute
from typeclasses.exits import Exit
from typeclasses.explorers import Explorer
from world.content import ROOMS
from world.exit_presentation import exit_diagram, exit_entries
from world.item_entities.models import ItemEntity, ItemRuntime, ItemSequence

from tests.base import WorldCommandTest


class ExitPresentationTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        super().setUp()
        self.rooms = self.world_rooms()
        self.char1.location = self.rooms["hq_stairs_4f"]
        self.char1.push_state = Mock()
        self.enterContext(patch("commands.character.time", return_value=160))

    def snapshot(self):
        return {model._meta.label: list(model.objects.order_by("pk").values())
                for model in (ObjectDB, Attribute, ItemEntity, ItemSequence, ItemRuntime)}

    def output(self, command):
        with patch.object(self.char1, "msg") as output:
            self.char1.execute_cmd(command)
        return "\n".join(str(call.args[0]) for call in output.call_args_list if call.args)

    def test_readonly_query_and_alias_keep_all_database_rows_even_at_recovery_boundary(self):
        self.char1.change(lambda p: p.update(hp=1))
        self.char1.push_state.reset_mock()
        before = self.snapshot()
        profile = deepcopy(self.char1.profile_snapshot())
        with patch("typeclasses.explorers.time", return_value=160):
            for command in ("출구", "exits", "출구 잘못된인자"):
                text = self.output(command)
                if command != "출구 잘못된인자":
                    self.assertIn("[출구] 본부 4층 계단", text)
                    self.assertIn("본부 5층 계단", text)
                    self.assertIn("이동 가능", text)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.char1.profile_snapshot(), profile)
                self.assertEqual(self.char1.zone, "hq_stairs_4f")
        self.char1.push_state.assert_not_called()

    def test_combat_and_access_status_priority_matches_traversal(self):
        self.char1.change(lambda p: p.update(combat_target=123))
        entries = exit_entries(self.char1, observed_at=100)
        self.assertTrue(all(entry["status"] == "전투 중 이동 불가" for entry in entries))
        self.assertIn("전투 중 이동 불가", self.output("출구"))
        self.assertEqual(next(p["role"] for p in exit_diagram(entries).segments if p["text"] == "X"), "warning")
        self.char1.location = self.rooms["support_5f_w2"]
        entries = {entry["name"]: entry for entry in exit_entries(self.char1, observed_at=100)}
        self.assertEqual(entries["북"]["status"], "출입증 필요")
        self.assertEqual(entries["남"]["status"], "시설 폐쇄")
        self.assertEqual(entries["동"]["status"], "전투 중 이동 불가")
        self.char1.location = self.rooms["support_5f_c"]
        entries = {entry["name"]: entry for entry in exit_entries(self.char1, observed_at=100)}
        self.assertEqual(entries["북"]["status"], "폐쇄")
        self.assertFalse(entries["북"]["exists"])
        # 실제 임무 gate 중 하나를 선택한다. 보상/진행 fixture를 직접 완료하지 않는다.
        gate = next((zone, name, target) for zone, data in ROOMS.items()
                    for name, target in data["exits"].items() if ROOMS[target].get("requires"))
        self.char1.location = self.rooms[gate[0]]
        entry = next(entry for entry in exit_entries(self.char1) if entry["name"] == gate[1])
        self.assertEqual(entry["status"], "임무 조건 미충족")
        self.assertEqual(entry["destination_name"], "미탐사")

    def test_name_disclosure_uses_view_lock_access_visited_and_observation_without_hooks(self):
        source = self.rooms["hq_stairs_4f"]
        obj = next(obj for obj in source.exits if obj.key == "위")
        target = obj.destination
        with patch.object(target, "return_distant_appearance") as hook:
            with patch.object(obj, "can_observe_through", return_value=False):
                self.assertEqual(exit_entries(self.char1)[0]["destination_name"], "미탐사")
            self.assertEqual(exit_entries(self.char1)[0]["destination_name"], target.key)
            self.assertEqual(exit_entries(self.char1, reveal_observed=False)[0]["destination_name"], "미탐사")
            self.char1.change(lambda p: p.update(visited=[target.db.zone_id]))
            self.assertEqual(exit_entries(self.char1, reveal_observed=False)[0]["destination_name"], target.key)
            target.locks.add("view:false()")
            self.assertEqual(exit_entries(self.char1)[0]["destination_name"], "미탐사")
            target.locks.add("view:all()")
            obj.locks.add("traverse:false()")
            entry = exit_entries(self.char1)[0]
            self.assertEqual(entry["destination_name"], target.key)
            self.assertFalse(entry["can_move"])
            obj.locks.add("view:false()")
            self.assertNotIn("위", [entry["name"] for entry in exit_entries(self.char1)])
            hook.assert_not_called()
        self.char1.location = self.rooms["support_5f_w2"]
        self.char1.change(lambda p: p.update(visited=["outpost_equipment", "reserved_equipment"]))
        entries = exit_entries(self.char1)
        self.assertEqual([entry["destination_name"] for entry in entries if entry["name"] in ("북", "남")],
                         [self.rooms["outpost_equipment"].key, self.rooms["reserved_equipment"].key])

    def test_actual_objects_override_definition_and_special_order_stays_stable(self):
        extra = create_object(Exit, key="사유 문", location=self.char1.location, destination=self.rooms["dock"])
        up = next(obj for obj in self.char1.location.exits if obj.key == "위")
        up.destination = self.rooms["hq_stairs_2f"]
        entries = exit_entries(self.char1)
        self.assertEqual([entry["name"] for entry in entries], ["위", "아래", "나가기", "사유 문"])
        self.assertEqual(entries[0]["destination_name"], self.rooms["hq_stairs_2f"].key)
        extra.delete()
        up.delete()
        self.assertNotIn("위", [entry["name"] for entry in exit_entries(self.char1)])
        self.assertEqual(exit_diagram(exit_entries(self.char1)).splitlines()[1][1], "v")

    def test_web_state_and_compass_share_actual_restrictions_and_no_hidden_target_ids(self):
        self.char1.location = self.rooms["support_5f_w2"]
        with patch.object(self.char1, "msg") as output:
            Explorer.push_state(self.char1, observed_at=100)
        state = output.call_args.kwargs["pz_state"][0][0]
        expected = exit_entries(self.char1, observed_at=100)
        self.assertEqual(state["exit_details"], expected)
        self.assertEqual(state["exits"], [entry["name"] for entry in expected if entry["exists"]])
        self.assertNotIn("outpost_equipment", str(state["exit_details"]))
        self.assertNotIn("reserved_equipment", str(state["exit_details"]))
        self.assertNotIn("elevator", state)
        self.assertNotIn("stairs", state)
        self.assertIn("출구", self.output("출구 도움말"))

    def test_visited_name_survives_credential_loss_and_quest_gate_without_query_writes(self):
        from world.credential_service import grant_credential

        self.char1.location = self.rooms["support_5f_w2"]
        credential = grant_credential(self.char1, "outpost_supply_pass")
        self.char1.execute_cmd("북")
        self.assertIn("outpost_equipment", self.char1.profile_snapshot()["visited"])
        self.char1.execute_cmd("남")
        credential.delete()
        before = self.snapshot()
        entry = next(entry for entry in exit_entries(self.char1) if entry["name"] == "북")
        self.assertEqual(entry["destination_name"], self.rooms["outpost_equipment"].key)
        self.assertEqual(entry["status"], "출입증 필요")
        self.assertIn(self.rooms["outpost_equipment"].key, self.output("출구"))
        self.assertIn("북: " + self.rooms["outpost_equipment"].key, self.output("지도"))
        self.assertEqual(self.snapshot(), before)

        zone, name, target = next((zone, name, target) for zone, data in ROOMS.items()
                                 for name, target in data["exits"].items() if ROOMS[target].get("requires"))
        self.char1.location = self.rooms[zone]
        self.char1.change(lambda p: p.update(visited=[zone, target]))
        before = self.snapshot()
        entry = next(entry for entry in exit_entries(self.char1) if entry["name"] == name)
        self.assertEqual(entry["destination_name"], self.rooms[target].key)
        self.assertEqual(entry["status"], "임무 조건 미충족")
        self.assertIn(name + ": " + self.rooms[target].key, self.output("지도"))
        self.output("출구")
        self.assertEqual(self.snapshot(), before)

    def test_exit_command_permissions_match_dispatch_and_vertical_web_restrictions(self):
        from evennia.commands import cmdhandler

        obj = next(obj for obj in self.char1.location.exits if obj.key == "위")
        self.char1.change(lambda p: p.update(visited=[obj.destination.db.zone_id]))
        for lock in ("cmd:false();traverse:all()", "cmd:all();traverse:false()"):
            for combat in (None, 123):
                with self.subTest(lock=lock, combat=combat):
                    self.char1.change(lambda p: p.update(combat_target=combat))
                    obj.locks.add(lock)
                    obj.at_cmdset_get(force_init=True)
                    # 한 fixture에서 lock 조합을 바꾸므로 이전 합성 CmdSet을 재사용하지 않는다.
                    cmdhandler._CMDSET_MERGE_CACHE.clear()
                    before = self.snapshot()
                    entry = next(entry for entry in exit_entries(self.char1) if entry["name"] == "위")
                    self.assertEqual(entry["status"], "시설 폐쇄")
                    self.assertFalse(entry["can_move"])
                    self.assertEqual(entry["destination_name"], obj.destination.key)
                    self.char1.execute_cmd("위")
                    self.assertEqual(self.char1.zone, "hq_stairs_4f")
                    self.assertEqual(self.snapshot(), before)
                    with patch.object(self.char1, "msg") as output:
                        Explorer.push_state(self.char1, observed_at=100)
                    state = output.call_args.kwargs["pz_state"][0][0]
                    self.assertFalse(next(e for e in state["exit_details"] if e["name"] == "위")["can_move"])
                    diagram = exit_diagram(state["exit_details"])
                    self.assertEqual(next(p["role"] for p in diagram.segments if p["text"] == "X"), "warning")
        obj.locks.add("cmd:all();traverse:all()")
        obj.at_cmdset_get(force_init=True)
        cmdhandler._CMDSET_MERGE_CACHE.clear()
        self.char1.change(lambda p: p.update(combat_target=None))
        self.assertTrue(next(e for e in exit_entries(self.char1) if e["name"] == "위")["can_move"])
        self.char1.execute_cmd("위")
        self.assertEqual(self.char1.zone, "hq_stairs_5f")
