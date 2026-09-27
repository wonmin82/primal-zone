"""환경 시야, 명령, 공용 조명과 광원 수명주기의 실제 영속 경계."""

from copy import deepcopy
from random import Random
from unittest.mock import Mock, patch

from evennia import create_object, create_script
from evennia.utils.dbserialize import deserialize
from evennia.utils.test_resources import EvenniaCommandTest
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from typeclasses.interactables import Container, EmergencyLightCache, MaintenanceLog
from typeclasses.loot import Corpse, create_dropped_loot, take_loot
from typeclasses.scripts import WorldLifecycle
from world import environment, lighting, rules
from world.bootstrap import build_world
from world.content import ITEMS, ROOMS
from world.distant_presentation import DistantViewContext
from world.environment_state import snapshot_for
from world.facilities import restore_outpost_power
from world.item_transfers import transfer
from world.multiplayer import world_change
from world.observation import can_perceive, context_for
from world.state import multiplayer_state
from world.targets import TargetSelector, resolve, room_objects


class LightingTests(EvenniaCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        for module in ("typeclasses.enemies", "typeclasses.explorers", "typeclasses.loot"):
            self.enterContext(patch(module + ".delay"))
        for module in ("world.observation", "commands.character", "typeclasses.explorers",
                       "typeclasses.enemies", "world.item_transfers", "typeclasses.loot"):
            self.enterContext(patch(module + ".time", return_value=100))
        self.enterContext(patch("commands.items.time", create=True, return_value=100))
        self.rooms = build_world()
        self.script = create_script(WorldLifecycle, autostart=False)
        self.state = environment.new_environment(100, Random(3))
        self.state["clock"]["game_epoch"] = 22 * 3600
        self.state["zones"]["island"].update(weather="storm", next_change_at=1000000)
        self.script.db.environment = self.state
        for player in (self.char1, self.char2):
            player.location = self.rooms["grass"]
            player.push_state = Mock()

    def command(self, value):
        with patch.object(self.char1, "msg") as message:
            self.char1.execute_cmd(value)
        return "\n".join(str(call.args[0]) for call in message.call_args_list if call.args)

    def powered(self, player=None):
        player = player or self.char1
        profile = player.profile()
        profile["inventory"].update(flashlight=1, battery=3)
        lighting.insert_power(profile, "flashlight", "battery", 100)
        lighting.switch(profile, "flashlight", True, 100)
        player.save_profile(profile)

    def clear(self):
        self.state["clock"]["game_epoch"] = 8 * 3600
        self.state["zones"]["island"]["weather"] = "clear"
        self.script.db.environment = self.state

    def test_distant_poor_clear_and_flashlight_with_unchanged_environment(self):
        target = self.rooms["trail"]
        context = DistantViewContext(self.char1, self.char1.location, target, observed_at=100)
        before = snapshot_for(target, 100)
        hidden = target.return_distant_appearance(context)
        self.assertIn(target.key, hidden)
        self.assertIn(ROOMS["trail"]["desc"], hidden)
        self.assertNotIn("갈퀴사냥룡", hidden)
        self.powered()
        lit = target.return_distant_appearance(context)
        self.assertIn("갈퀴사냥룡", lit)
        self.assertNotIn("갈퀴사냥룡 1", lit)
        self.assertEqual(snapshot_for(target, 100), before)
        self.assertEqual(context_for(self.char1, target, 100, 1).snapshot.effective_visibility, "reduced")
        self.clear()
        self.assertIn("갈퀴사냥룡", target.return_distant_appearance(context))

    def test_local_prose_selector_web_and_attack_share_perception(self):
        enemy = room_enemies(self.char1.location)[0]
        self.assertNotIn(enemy, room_objects(self.char1, observed_at=100))
        self.assertNotIn(enemy.key, self.command("보기"))
        self.assertEqual(multiplayer_state(self.char1, 100)["enemies"], [])
        with self.assertRaises(rules.RuleError):
            resolve([enemy], TargetSelector(enemy.key), self.char1, "공격")
        before = deepcopy(self.char1.profile())
        with self.assertRaises(rules.RuleError), world_change():
            enemy.engage(self.char1, 100)
        self.assertEqual(self.char1.profile(), before)
        self.assertFalse(enemy.db.claim)
        self.powered()
        self.assertIn(enemy, room_objects(self.char1, observed_at=100))
        self.assertEqual(multiplayer_state(self.char1, 100)["enemies"][0]["id"], enemy.id)
        enemy.engage(self.char1, 100)
        # 기존 전투 상대는 광원이 꺼져도 추적한다.
        self.char1.change(lambda p: lighting.switch(p, "flashlight", False, 100))
        enemy.engage(self.char1, 101)
        self.assertEqual(self.char1.combat_target(), enemy)
        self.assertIsNotNone(multiplayer_state(self.char1, 100)["combat_target"])

    def test_other_viewer_remains_dark_and_view_locks_cannot_be_bypassed(self):
        self.powered()
        a = context_for(self.char1, observed_at=100)
        b = context_for(self.char2, observed_at=100)
        self.assertEqual(a.environment, b.environment)
        self.assertEqual((a.snapshot.effective_visibility, b.snapshot.effective_visibility), ("clear", "poor"))
        enemy = room_enemies(self.char1.location)[0]
        enemy.locks.add("view:false()")
        self.assertFalse(can_perceive(enemy, a))
        self.assertNotIn(enemy, room_objects(self.char1, observed_at=100))

    def test_exit_navigation_and_locked_privacy_before_observation(self):
        self.char1.location = self.rooms["marsh"]
        north = next(exit for exit in self.char1.location.exits if exit.key == "북")
        self.assertIn(north, room_objects(self.char1, observed_at=100))
        with patch("world.environment_state.snapshot_for", side_effect=AssertionError("blocked environment read")):
            output = self.command("북 봐")
        self.assertIn("진입문", output)
        self.assertNotIn(self.rooms["ridge"].key, output)
        self.assertEqual(self.char1.location, self.rooms["marsh"])

    def test_small_interaction_hidden_opt_in_remains_and_emergency_cache_is_guaranteed(self):
        self.char1.location = self.rooms["wreck"]
        cache = next(obj for obj in self.char1.location.contents if isinstance(obj, EmergencyLightCache))
        self.assertIn(cache, room_objects(self.char1, observed_at=100))
        self.assertIn("탐사용손전등", self.command("비상장비함 조사"))
        self.assertEqual(self.char1.profile()["inventory"]["battery"], 2)
        before = deepcopy(self.char1.profile())
        self.command("비상장비함 조사")
        self.assertEqual(self.char1.profile(), before)
        self.char1.location = self.rooms["office"]
        record = next(obj for obj in self.char1.location.contents if isinstance(obj, MaintenanceLog))
        self.assertNotIn(record, room_objects(self.char1, observed_at=100))
        with self.assertRaises(rules.RuleError):
            record.perform_action(self.char1, "조사")
        self.powered()
        self.assertIn(record, room_objects(self.char1, observed_at=100))
        remote = self.rooms["office"].return_distant_appearance(DistantViewContext(self.char1, self.rooms["grass"], self.rooms["office"], observed_at=100))
        self.assertNotIn(record.key, remote)

    def test_store_parser_accepts_alias_and_future_capacity_without_changes(self):
        self.clear()
        self.char1.change(lambda p: p["inventory"].update(flashlight=1, battery=2))
        self.assertIn("전원이 없습니다", self.command("손전등 켜"))
        self.command("손전등에 건전지 넣어")
        self.assertEqual(self.char1.profile()["inventory"]["battery"], 1)
        self.assertEqual(self.char1.profile()["light_sources"]["flashlight"]["charge_seconds"], 1800)
        self.assertIn("건전지", self.command("손전등 확인"))
        before = deepcopy(self.char1.profile())
        self.command("탐사용손전등에 건전지 넣어")
        self.assertEqual(self.char1.profile(), before)
        self.char1.change(lambda p: p["light_sources"].clear())
        future = {"name": "고용량건전지", "slot": "consumable", "power_source": {"type": "flashlight_battery", "capacity_seconds": 3600}}
        with patch.dict(ITEMS, high_capacity_battery=future):
            self.char1.change(lambda p: p["inventory"].update(high_capacity_battery=1))
            self.command("탐사용손전등에 고용량건전지 넣어")
            self.assertEqual(self.char1.profile()["light_sources"]["flashlight"]["charge_seconds"], 3600)
            self.assertIn("고용량건전지", self.command("손전등 확인"))

    def test_power_insertion_transaction_failure_rolls_back_item_and_device(self):
        self.char1.change(lambda p: p["inventory"].update(flashlight=1, battery=2))
        before = deepcopy(self.char1.profile())
        with self.assertRaises(RuntimeError), world_change():
            self.char1.change(lambda p: lighting.insert_power(p, "flashlight", "battery", 100))
            raise RuntimeError("destination save failed")
        self.assertEqual(self.char1.profile(), before)

    def test_last_flashlight_transfer_discards_state_but_spare_copy_preserves_it(self):
        self.clear()
        for destination in ("ground", "player", "container"):
            with self.subTest(destination=destination):
                self.powered()
                self.char1.change(lambda p: p["inventory"].update(flashlight=2))
                kwargs = {}
                if destination == "player":
                    kwargs["recipient"] = self.char2
                elif destination == "container":
                    kwargs["container"] = create_object(Container, key="보관상자", location=self.char1.location)
                transfer(self.char1, "flashlight", **kwargs)
                self.assertTrue(self.char1.profile()["light_sources"]["flashlight"]["on"])
                transfer(self.char1, "flashlight", **kwargs)
                self.assertEqual(self.char1.profile()["light_sources"], {})

    def test_lifecycle_depletion_once_and_logout_freeze_persist(self):
        self.powered()
        with patch.object(self.char1, "save_profile", wraps=self.char1.save_profile) as save:
            self.char1.reconcile_lights(200)
            save.assert_not_called()
            self.char1.reconcile_lights(1900)
            save.assert_called_once()
            self.char1.reconcile_lights(1905)
            save.assert_called_once()
        self.assertFalse(self.char1.profile()["light_sources"]["flashlight"]["on"])
        self.powered()
        with patch.object(self.char1.sessions, "count", return_value=0):
            self.char1.at_post_unpuppet()
        saved = deserialize(self.char1.db.profile)
        self.assertFalse(saved["light_sources"]["flashlight"]["on"])
        self.assertEqual(lighting.projected(saved, "flashlight", 5000)["charge_seconds"], 1800)

    def test_shared_generator_light_is_independent_of_other_player_quest(self):
        self.char1.location = self.char2.location = self.rooms["generator"]
        self.assertEqual(snapshot_for(self.char1.location, 100).ambient_light, "dim")
        self.char1.change(lambda p: (p["quests"]["radio_tower"].update(started=True, record_read=True), p["inventory"].update(scrap=3)))
        restore_outpost_power(self.char1)
        self.assertTrue(self.char1.profile()["quests"]["radio_tower"]["generator_fixed"])
        self.assertFalse(self.char2.profile()["quests"]["radio_tower"]["generator_fixed"])
        self.assertEqual(snapshot_for(self.char1.location, 100).ambient_light, "bright")
        self.assertEqual(context_for(self.char1, observed_at=100).environment, context_for(self.char2, observed_at=100).environment)
        saved = deserialize(self.script.db.facilities)
        build_world()
        self.assertEqual(deserialize(self.script.db.facilities), saved)

    def test_generator_failure_rolls_back_shared_power_and_personal_progress(self):
        self.char1.change(lambda p: (p["quests"]["radio_tower"].update(started=True, record_read=True), p["inventory"].update(scrap=3)))
        before = deepcopy(self.char1.profile())
        with self.assertRaises(RuntimeError), world_change():
            restore_outpost_power(self.char1)
            raise RuntimeError("outer failure")
        self.assertEqual(self.char1.profile(), before)
        self.assertFalse(self.script.db.facilities)

    def test_existing_repaired_character_can_activate_new_facility_without_duplicate_reward(self):
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(generator_fixed=True))
        before = deepcopy(self.char1.profile())
        restore_outpost_power(self.char1)
        self.assertTrue(self.script.db.facilities["outpost_power"])
        self.assertEqual(self.char1.profile(), before)
        with self.assertRaises(rules.RuleError):
            restore_outpost_power(self.char1)
        self.assertEqual(self.char1.profile(), before)

    def test_dock_safe_lighting_and_normal_containers_visible_in_dark(self):
        self.char1.location = self.rooms["dock"]
        self.assertEqual(snapshot_for(self.char1.location, 100).ambient_light, "bright")
        self.assertIn("윤대장", self.command("보기"))
        self.assertTrue(any(isinstance(obj, Container) for obj in room_objects(self.char1, observed_at=100)))

    def test_loot_details_and_known_item_take_are_hidden_until_lit(self):
        corpse = create_object(Corpse, key="갈퀴사냥룡의 시체", location=self.char1.location)
        corpse.db.decay_at = 1000000
        corpse.db.entries = [{"item": "scrap", "quantity": 3, "reserved_party": None, "reserved_player": None, "assigned_player": None, "protection_until": 0}]
        create_dropped_loot(self.char1.location, deepcopy(corpse.db.entries))
        before = deepcopy(self.char1.profile())
        with self.assertRaises(rules.RuleError):
            take_loot(self.char1, item="scrap", now=100)
        self.assertEqual(self.char1.profile(), before)
        self.assertEqual(multiplayer_state(self.char1, 100)["ground_loot"], [])
        self.powered()
        take_loot(self.char1, item="scrap", now=100)
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 1)

    def test_push_state_keeps_environment_and_observation_separate(self):
        self.powered()
        with patch.object(self.char1.sessions, "count", return_value=1), patch.object(self.char1, "msg") as msg:
            Explorer.push_state(self.char1, observed_at=100)
        payload = msg.call_args.kwargs["pz_state"][0][0]
        self.assertEqual(payload["environment"]["visibility"]["id"], "poor")
        self.assertEqual(payload["observation"]["effective_visibility"]["id"], "clear")
        self.assertEqual(payload["observation"]["light_source"]["power_source"]["id"], "battery")
        self.assertEqual(payload["observation"]["light_source"]["remaining_minutes"], 30)
