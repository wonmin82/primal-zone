"""공용 Room/개별 Exit 이동. 과거 current_stop은 읽거나 바꾸지 않는다."""
from copy import deepcopy
from unittest.mock import Mock, patch

from evennia import search_tag
from typeclasses.explorers import Explorer
from world.bootstrap import EXIT_CATEGORY, build_world
from world.content.headquarters import ELEVATOR_ROOM, HQ_LANDINGS

from tests.base import WorldCommandTest


class ElevatorTests(WorldCommandTest):
    character_typeclass = Explorer
    def setUp(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        super().setUp()
        self.rooms = self.world_rooms()
        self.lift = self.rooms[ELEVATOR_ROOM]
        for player in (self.char1, self.char2):
            player.location = self.rooms["hq_concourse"]
            player.push_state = Mock()

    def test_six_landings_and_destinations_are_actual_exits(self):
        for label, landing, _ in HQ_LANDINGS:
            self.char1.location = self.rooms[landing]
            self.char1.execute_cmd("승강기")
            self.assertEqual(self.char1.location, self.lift)
            self.char1.execute_cmd(label)
            self.assertEqual(self.char1.zone, landing)
        self.assertEqual([obj.key for obj in self.lift.exits], [label for label, _, _ in HQ_LANDINGS])

    def test_two_passengers_choose_independent_destinations(self):
        for player in (self.char1, self.char2):
            player.execute_cmd("승강기")
        self.char1.execute_cmd("5층")
        self.assertEqual(self.char1.zone, "support_5f_c")
        self.assertEqual(self.char2.location, self.lift)
        self.char2.execute_cmd("2층")
        self.assertEqual(self.char2.zone, "support_2f_c")
        self.assertEqual(self.char1.zone, "support_5f_c")

    def test_combat_and_wrong_arguments_do_not_move_or_mutate_profile(self):
        self.char1.change(lambda p: p.update(combat_target=123))
        before = deepcopy(self.char1.profile_snapshot())
        self.char1.execute_cmd("승강기")
        self.assertEqual(self.char1.zone, "hq_concourse")
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.char1.change(lambda p: p.update(combat_target=None))
        for command in ("승강기 3층", "계단 올라", "계단 내려"):
            before = deepcopy(self.char1.profile_snapshot())
            self.char1.execute_cmd(command)
            self.assertEqual(self.char1.zone, "hq_concourse")
            self.assertEqual(self.char1.profile_snapshot(), before)
        self.char1.execute_cmd("승강기")
        for command in ("5층 잘못된인자", "내려"):
            before = deepcopy(self.char1.profile_snapshot())
            self.char1.execute_cmd(command)
            self.assertEqual(self.char1.location, self.lift)
            self.assertEqual(self.char1.profile_snapshot(), before)

    def test_bootstrap_preserves_room_exit_identity_legacy_attribute_and_items(self):
        from world.item_entities.api import create_item
        from world.item_entities.models import ItemEntity
        self.lift.db.current_stop = {"historical": "untouched"}
        item = create_item("bandage", quantity=2, location_kind="inventory", owner_object=self.char1)
        item.state = {"test": 1}
        item.save()
        before = list(ItemEntity.objects.values())
        ids = {obj.tags.get(category=EXIT_CATEGORY): obj.id for room in self.rooms.values() for obj in room.exits}
        for _ in range(2):
            rebuilt = build_world()
            self.assertEqual(rebuilt[ELEVATOR_ROOM].id, self.lift.id)
            self.assertEqual(self.lift.db.current_stop, {"historical": "untouched"})
            self.assertEqual(list(ItemEntity.objects.values()), before)
            for identity, obj_id in ids.items():
                self.assertEqual([obj.id for obj in search_tag(identity, category=EXIT_CATEGORY)], [obj_id])
        self.char1.execute_cmd("승강기")
        self.char1.execute_cmd("3층")
        self.assertEqual(self.lift.db.current_stop, {"historical": "untouched"})

    def test_native_web_exit_list_has_no_transport_state(self):
        for zone in ("hq_concourse", ELEVATOR_ROOM):
            self.char1.location = self.rooms[zone]
            with patch.object(self.char1, "msg") as output:
                Explorer.push_state(self.char1)
            state = output.call_args.kwargs["pz_state"][0][0]
            self.assertNotIn("elevator", state)
            self.assertNotIn("stairs", state)
            self.assertEqual(set(state["exits"]), {obj.key for obj in self.rooms[zone].exits})
