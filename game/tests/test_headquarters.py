"""본부의 실제 입력·접속·월드 동기화와 기존 서비스 보존을 검증한다."""

from copy import deepcopy
from random import Random
from unittest.mock import Mock, patch

from evennia import create_object, search_tag
from evennia.objects.models import ObjectDB
from evennia.objects.objects import DefaultCharacter
from typeclasses.enemies import room_enemies
from typeclasses.exits import Exit
from typeclasses.explorers import Explorer
from typeclasses.interactables import INTERACTABLES, action_objects, instructor_for
from world.bootstrap import CATEGORY, EXIT_CATEGORY, build_world, stale_definitions
from world.content import ROOMS
from world.content.directions import DIRECTION_ALIASES
from world.content.headquarters import ROOMS as HQ_ROOMS

from tests.base import GameCommandTest


class HeadquartersTests(GameCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        super().setUp()
        self.rooms = build_world()
        for player in (self.char1, self.char2):
            player.home = self.rooms["dock"]
            player.push_state = Mock()
            self.enterContext(patch.object(player.sessions, "count", return_value=1))
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))

    def test_first_puppet_uses_staging_and_keeps_dock_as_home(self):
        with patch.object(DefaultCharacter, "at_post_puppet"):
            self.char1.at_post_puppet()
        self.assertEqual(self.char1.zone, "staging_room")
        self.assertEqual(self.char1.home, self.rooms["dock"])
        for command, target in (("남", "hq_concourse"), ("동", "hq_admin_office"),
                                ("서", "hq_concourse"), ("남", "hq_lounge"),
                                ("북", "hq_concourse"), ("서", "dock"), ("북", "grass")):
            self.char1.execute_cmd(command)
            self.assertEqual(self.char1.zone, target)

    def test_logout_and_reconnect_stage_preserving_progress(self):
        self.char1.location = self.rooms["support_5f_c"]
        self.char1.change(lambda profile: profile.update(credits=77, storage={"bandage": 2}))
        before = deepcopy(self.char1.profile())
        with patch.object(self.char1.sessions, "count", return_value=0):
            self.char1.at_post_unpuppet(account=self.account, session=self.session)
        self.assertIsNone(self.char1.location)
        self.assertEqual(self.char1.db.prelogout_location, self.rooms["support_5f_c"])
        self.char1.at_pre_puppet(self.account, session=self.session)
        with patch.object(DefaultCharacter, "at_post_puppet"):
            self.char1.at_post_puppet()
        self.assertEqual(self.char1.location, self.rooms["staging_room"])
        self.assertEqual(self.char1.profile(), before)
        self.assertEqual(self.char1.home, self.rooms["dock"])
        self.char1.location = self.rooms["grass"]
        with patch.object(DefaultCharacter, "at_post_puppet"):
            self.char1.at_post_puppet()
        self.assertEqual(self.char1.zone, "grass")

    def test_real_graph_directions_and_aliases_traverse_to_exact_targets(self):
        for zone, definition in HQ_ROOMS.items():
            for direction, destination in definition["exits"].items():
                for command in dict.fromkeys((direction, DIRECTION_ALIASES.get(direction, direction))):
                    with self.subTest(zone=zone, command=command):
                        self.char1.location = self.rooms[zone]
                        self.char1.execute_cmd(command)
                        if ROOMS[destination].get("access"):
                            self.assertEqual(self.char1.location, self.rooms[zone])
                        else:
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
        self.char1.location = self.rooms["support_5f_c"]
        for command in ("s", "S", "ㄴ", "남 봐", "s 봐"):
            with self.subTest(command=command), patch.object(self.char1, "msg") as output:
                self.char1.execute_cmd(command)
                self.assertIn("남쪽 출입문은 현재 폐쇄되어 있다.", str(output.call_args_list))
                self.assertEqual(self.char1.zone, "support_5f_c")
        self.char1.execute_cmd("ㅅ")
        self.assertEqual(self.char1.zone, "support_5f_w1")

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
        source = self.rooms["support_5f_c"]
        old = create_object(Exit, key="남", aliases=["s"], location=source, destination=self.rooms["infirmary"])
        old.tags.add("support_5f_c:남", category=EXIT_CATEGORY)
        identity = old.id
        self.char1.location = source
        with patch.object(self.rooms["infirmary"], "return_distant_appearance") as appearance:
            self.char1.execute_cmd("남")
            self.assertEqual(self.char1.location, source)
            self.char1.execute_cmd("남 봐")
            appearance.assert_not_called()
        build_world()
        build_world()
        self.assertFalse(ObjectDB.objects.filter(pk=identity).exists())
        self.assertFalse(search_tag("support_5f_c:남", category=EXIT_CATEGORY))
        self.assertEqual({obj.key for obj in source.exits}, {"서", "동", "계단", "승강기"})

    def test_retired_corridors_preserve_objects_native_loot_and_history(self):
        from typeclasses.loot import DroppedLoot
        from typeclasses.zone_rooms import ZoneRoom
        from world.content.headquarters import RETIRED_ROOMS
        from world.item_entities import api
        from world.item_entities.models import ItemEntity, ItemSequence

        originals = {}
        for zone, replacement in RETIRED_ROOMS.items():
            old = create_object(ZoneRoom, key="이전 복도")
            old.db.zone_id = zone
            old.tags.add(zone, category=CATEGORY)
            managed = create_object(Exit, key="북", location=old, destination=self.rooms["infirmary"])
            managed.tags.add(f"{zone}:북", category=EXIT_CATEGORY)
            custom = create_object(Exit, key="사용자 통로", location=old, destination=self.rooms["dock"])
            loot = create_object(DroppedLoot, key="남은 물건", location=old)
            item = api.create_item("bandage", quantity=2, location_kind="world_loot", owner_object=loot)
            originals[zone] = (old, managed.id, custom.id, loot, item.pk, replacement)
        old = originals["support_1f_c"][0]
        self.char1.location = old
        self.char1.home = old
        self.char1.db.prelogout_location = old
        self.char1.change(lambda p: p.update(visited=list(RETIRED_ROOMS), credits=77))
        profile = deepcopy(self.char1.profile_snapshot())
        snapshot = list(ItemEntity.objects.values())
        sequence = ItemSequence.objects.get(pk=1).last_value
        for _ in range(2):
            build_world()
            self.assertEqual(self.char1.zone, "hq_concourse")
            self.assertEqual(self.char1.home, old)
            self.assertEqual(self.char1.db.prelogout_location, old)
            self.assertEqual(self.char1.profile_snapshot(), profile)
            self.assertEqual(list(ItemEntity.objects.values()), snapshot)
            self.assertEqual(ItemSequence.objects.get(pk=1).last_value, sequence)
            for zone, (retired, exit_id, custom_id, loot, item_id, replacement) in originals.items():
                self.assertTrue(ObjectDB.objects.filter(pk=retired.id).exists())
                self.assertFalse(search_tag(zone, category=CATEGORY))
                self.assertEqual(search_tag(zone, category="primal_retired_room")[0], retired)
                self.assertFalse(ObjectDB.objects.filter(pk=exit_id).exists())
                self.assertTrue(ObjectDB.objects.filter(pk=custom_id).exists())
                loot.refresh_from_db()
                self.assertEqual(loot.location, self.rooms[replacement])
                self.assertEqual(ItemEntity.objects.get(pk=item_id).owner_object, loot)
            self.assertEqual(stale_definitions(), [])

    def test_npc_distribution_keeps_21_hq_npcs_and_13_training_roles(self):
        expected = {
            "training_room": {"trainer_attack", "trainer_heavy", "trainer_strength"},
            "survival_training_room": {"trainer_defense", "trainer_constitution", "trainer_breathing"},
            "training_office": {"instructor"}, "tactics_room": {"trainer_suppress", "trainer_wisdom"},
            "shooting_range": {"trainer_shooting", "trainer_insight", "trainer_agility"},
            "medical_training_room": {"trainer_heal"},
        }
        for zone, identities in expected.items():
            self.assertEqual({key for key, definition in INTERACTABLES.items() if definition["room"] == zone}, identities)
            for key in identities:
                self.assertEqual(search_tag(key, category="primal_interactable")[0].location, self.rooms[zone])
        npcs = [obj for room in [self.rooms[z] for z in HQ_ROOMS] + [self.rooms["dock"]]
                for obj in action_objects(room) if obj.semantic_role == "npc"]
        self.assertEqual(len(npcs), 21)

    def test_room_map_and_web_state_use_current_layout_and_stairs(self):
        from world.state import multiplayer_state
        self.char1.location = self.rooms["hq_concourse"]
        self.char1.db.profile = {**self.char1.profile(), "visited": list(HQ_ROOMS)}
        with patch.object(self.char1, "msg") as output:
            self.char1.execute_cmd("지도")
        text = str(output.call_args_list)
        self.assertIn("본부 중앙 로비", text)
        self.assertIn("본부 5층 중앙 복도", text)
        self.assertNotIn("지원동 1층", text)
        state = multiplayer_state(self.char1)
        self.assertNotIn("stairs", state)
        self.assertIn("계단", {obj.key for obj in self.char1.location.exits})
        self.assertEqual(ROOMS["hq_concourse"]["exits"], {"북":"staging_room", "서":"dock", "동":"hq_admin_office", "남":"hq_lounge", "계단":"hq_stairs_1f", "승강기":"support_elevator"})

    def test_dock_keeps_commander_without_support_services(self):
        self.char1.location = self.rooms["dock"]
        self.assertEqual(search_tag("commander", category="primal_interactable")[0].location, self.rooms["dock"])
        for key in ("instructor", "personal_locker", "shared_container"):
            self.assertNotEqual(search_tag(key, category="primal_interactable")[0].location, self.rooms["dock"])
        self.assertIsNone(instructor_for(self.char1))
        before = self.char1.profile()
        for raw in ("목록", "붕대 사", "절단마체테 사", "강화방호조끼 사"):
            self.char1.execute_cmd(raw)
            self.assertEqual(self.char1.profile(), before)
        self.char1.execute_cmd("개인 보관함에 붕대 넣어")
        self.assertEqual(self.char1.profile()["storage"], {})
        self.char1.change(lambda profile: profile.update(hp=1))
        self.char1.execute_cmd("휴식")
        self.assertEqual(self.char1.profile()["hp"], 1)
        self.char1.execute_cmd("윤대장에게 수락 말")
        self.assertTrue(self.char1.profile()["quests"]["radio_tower"]["started"])
        for zone in HQ_ROOMS:
            expected = [key for key, definition in INTERACTABLES.items() if definition["room"] == zone]
            self.assertEqual(len(action_objects(self.rooms[zone])), len(expected))

    def test_return_and_defeat_have_separate_support_destinations(self):
        self.char1.location = self.rooms["grass"]
        self.char1.execute_cmd("귀환")
        self.assertEqual(self.char1.zone, "support_roof")
        self.assertEqual(self.char1.home, self.rooms["dock"])
        self.char1.location = self.rooms["grass"]
        self.char1.change(lambda profile: profile.update(hp=1))
        enemy = room_enemies(self.char1.location)[0]
        enemy.engage(self.char1, now=100)
        enemy.enemy_tick(now=102.5, rng=Random(1))
        self.assertEqual(self.char1.location, self.rooms["infirmary"])
        self.assertEqual(self.char1.profile()["hp"], 1)
        self.assertEqual(self.char1.home, self.rooms["dock"])
