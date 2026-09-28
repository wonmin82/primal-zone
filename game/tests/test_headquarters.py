"""본부의 실제 입력·접속·월드 동기화와 기존 서비스 보존을 검증한다."""

from copy import deepcopy
from random import Random
from unittest.mock import Mock, patch

from evennia import create_object, search_tag
from evennia.objects.models import ObjectDB
from evennia.objects.objects import DefaultCharacter
from evennia.utils.test_resources import EvenniaCommandTest
from typeclasses.enemies import room_enemies
from typeclasses.exits import Exit
from typeclasses.explorers import Explorer
from typeclasses.interactables import INTERACTABLES, action_objects, instructor_for
from world.bootstrap import CATEGORY, EXIT_CATEGORY, build_world, stale_definitions
from world.content import OPPOSITES, ROOMS
from world.content.headquarters import ROOMS as HQ_ROOMS


class HeadquartersTests(EvenniaCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = build_world()
        for player in (self.char1, self.char2):
            player.home = self.rooms["dock"]
            player.push_state = Mock()
            self.enterContext(patch.object(player.sessions, "count", return_value=1))
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))

    def test_first_puppet_uses_staging_and_keeps_dock_as_home(self):
        self.assertNotIn(self.char1.zone, ROOMS)
        with patch.object(DefaultCharacter, "at_post_puppet"):
            self.char1.at_post_puppet()
        self.assertEqual(self.char1.location, self.rooms["staging_room"])
        self.assertEqual(self.char1.home, self.rooms["dock"])
        self.assertEqual(self.char1.profile()["visited"], ["staging_room"])
        self.char1.execute_cmd("남")
        self.assertEqual(self.char1.zone, "hq_concourse")
        self.char1.execute_cmd("서")
        self.assertEqual(self.char1.zone, "dock")
        self.char1.execute_cmd("북")
        self.assertEqual(self.char1.zone, "grass")

    def test_logout_and_reconnect_restore_existing_location_and_progress(self):
        self.char1.location = self.rooms["support_1f_c"]
        self.char1.change(lambda profile: profile.update(credits=77, storage={"bandage": 2}))
        before = deepcopy(self.char1.profile())
        with patch.object(self.char1.sessions, "count", return_value=0):
            self.char1.at_post_unpuppet(account=self.account, session=self.session)
        self.assertIsNone(self.char1.location)
        self.assertEqual(self.char1.db.prelogout_location, self.rooms["support_1f_c"])
        self.char1.at_pre_puppet(self.account, session=self.session)
        with patch.object(DefaultCharacter, "at_post_puppet"):
            self.char1.at_post_puppet()
        self.assertEqual(self.char1.location, self.rooms["support_1f_c"])
        self.assertEqual(self.char1.profile(), before)
        self.assertEqual(self.char1.home, self.rooms["dock"])
        self.char1.location = self.rooms["grass"]
        with patch.object(DefaultCharacter, "at_post_puppet"):
            self.char1.at_post_puppet()
        self.assertEqual(self.char1.zone, "grass")

    def test_real_graph_directions_and_aliases_traverse_to_exact_targets(self):
        for zone, definition in HQ_ROOMS.items():
            for direction, destination in definition["exits"].items():
                for command in (direction, OPPOSITES[direction]):
                    with self.subTest(zone=zone, command=command):
                        self.char1.location = self.rooms[zone]
                        self.char1.execute_cmd(command)
                        self.assertEqual(self.char1.location, self.rooms[destination])
        self.char1.location = self.rooms["dock"]
        self.char1.execute_cmd("동")
        self.assertEqual(self.char1.zone, "hq_concourse")

    def test_blocked_inputs_keep_room_profile_and_world_unchanged(self):
        for zone, definition in HQ_ROOMS.items():
            for direction, message in definition.get("blocked_exits", {}).items():
                self.char1.location = self.rooms[zone]
                before = deepcopy(self.char1.profile())
                with patch.object(self.char1, "msg") as output:
                    self.char1.execute_cmd(direction)
                self.assertIn(message, str(output.call_args_list))
                self.assertEqual(self.char1.location, self.rooms[zone])
                self.assertEqual(self.char1.profile(), before)
                self.assertNotIn(direction, {exit_obj.key for exit_obj in self.rooms[zone].exits})
        self.char1.location = self.rooms["support_1f_c"]
        for command in ("n", "N", "ㅂ", "북 보기", "n 봐"):
            with self.subTest(command=command), patch.object(self.char1, "msg") as output:
                self.char1.execute_cmd(command)
                self.assertIn("북쪽 출입문은 현재 폐쇄되어 있다.", str(output.call_args_list))
                self.assertEqual(self.char1.zone, "support_1f_c")
        self.char1.execute_cmd("ㅅ")
        self.assertEqual(self.char1.zone, "support_1f_w1")

    def test_bootstrap_reuses_rooms_exits_services_and_preserves_player(self):
        rooms = {zone: room.id for zone, room in self.rooms.items()}
        exits = {(zone, exit_obj.key): exit_obj.id for zone, room in self.rooms.items() for exit_obj in room.exits}
        services = {key: search_tag(key, category="primal_interactable")[0].id for key in INTERACTABLES}
        self.char1.location = self.rooms["storage_room"]
        before = deepcopy(self.char1.profile())
        count = ObjectDB.objects.count()
        for _ in range(2):
            rebuilt = build_world()
            self.assertEqual({zone: room.id for zone, room in rebuilt.items()}, rooms)
            self.assertEqual({(zone, obj.key): obj.id for zone, room in rebuilt.items() for obj in room.exits}, exits)
            self.assertEqual(ObjectDB.objects.count(), count)
        self.assertEqual(self.char1.location, self.rooms["storage_room"])
        self.assertEqual(self.char1.profile(), before)
        for key, identity in services.items():
            obj = search_tag(key, category="primal_interactable")[0]
            self.assertEqual(obj.id, identity)
            self.assertEqual(obj.location, self.rooms[INTERACTABLES[key]["room"]])
        self.assertEqual(stale_definitions(), [])
        for zone in HQ_ROOMS:
            self.assertEqual(len(search_tag(zone, category=CATEGORY)), 1)

    def test_preexisting_managed_closed_exit_cannot_traverse_or_reveal_then_is_removed(self):
        source = self.rooms["support_1f_c"]
        old = create_object(Exit, key="북", aliases=["n"], location=source, destination=self.rooms["infirmary"])
        old.tags.add("support_1f_c:북", category=EXIT_CATEGORY)
        identity = old.id
        self.char1.location = source
        with patch.object(self.rooms["infirmary"], "return_distant_appearance") as appearance:
            self.char1.execute_cmd("북")
            self.assertEqual(self.char1.location, source)
            self.char1.execute_cmd("북 보기")
            appearance.assert_not_called()
        build_world()
        build_world()
        self.assertFalse(ObjectDB.objects.filter(pk=identity).exists())
        self.assertFalse(search_tag("support_1f_c:북", category=EXIT_CATEGORY))
        self.assertEqual({obj.key for obj in source.exits}, {"서", "동", "남"})

    def test_presentation_map_and_web_expose_only_current_rooms_and_real_controls(self):
        self.char1.location = self.rooms["support_1f_c"]
        local = self.char1.location.return_appearance(self.char1)
        self.assertIn("북쪽 출입문은 현재 폐쇄되어 있다.", local)
        self.char1.db.profile = {**self.char1.profile(), "visited": list(HQ_ROOMS)}
        with patch.object(self.char1, "msg") as output:
            self.char1.execute_cmd("지도")
        map_text = str(output.call_args_list)
        self.assertIn("[탐사대 본부]", map_text)
        self.assertIn("북: 폐쇄", map_text)
        self.assertIn("지원동 옥상", map_text)
        self.assertNotIn("특수장비점", map_text)
        self.assertNotIn("공사 중", map_text)
        with patch.object(self.char1, "msg") as output:
            Explorer.push_state(self.char1)
        state = output.call_args.kwargs["pz_state"][0][0]
        self.assertEqual(state["exits"], ["서", "동", "남"])
        self.assertEqual(state["region"], "headquarters")
        self.assertEqual(state["interactables"], [])
        self.assertEqual(state["hint"], "")
        self.assertFalse(state["training_available"])
        self.char1.location = self.rooms["hq_concourse"]
        east = next(obj for obj in self.char1.location.exits if obj.key == "동")
        self.assertIn("북쪽 출입문은 현재 폐쇄되어 있다.", east.return_appearance(self.char1))

    def test_dock_services_return_and_defeat_destinations_remain_available(self):
        self.char1.location = self.rooms["support_1f_c"]
        self.char1.execute_cmd("귀환")
        self.assertEqual(self.char1.zone, "dock")
        for key in ("commander", "instructor", "personal_locker", "shared_container"):
            self.assertEqual(search_tag(key, category="primal_interactable")[0].location, self.rooms["dock"])
        self.assertTrue(instructor_for(self.char1).available(self.char1))
        self.char1.execute_cmd("붕대 구매")
        self.assertEqual(self.char1.profile()["inventory"]["bandage"], 4)
        self.char1.execute_cmd("개인 보관함에 붕대 넣어")
        self.assertEqual(self.char1.profile()["storage"]["bandage"], 1)
        self.char1.change(lambda profile: profile.update(hp=1))
        self.char1.execute_cmd("휴식")
        self.assertEqual(self.char1.profile()["hp"], 60)
        self.char1.execute_cmd("윤대장 대화")
        self.assertTrue(self.char1.profile()["quests"]["radio_tower"]["started"])
        self.char1.location = self.rooms["grass"]
        self.char1.change(lambda profile: profile.update(hp=1))
        enemy = room_enemies(self.char1.location)[0]
        enemy.engage(self.char1, now=100)
        enemy.enemy_tick(now=102.5, rng=Random(1))
        self.assertEqual(self.char1.location, self.rooms["dock"])
        for zone in HQ_ROOMS:
            self.assertEqual(action_objects(self.rooms[zone]), [])
