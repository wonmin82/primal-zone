"""환경 영속성, 조회 경계와 기존 월드/명령/UI의 일관성 검증."""

import json
from copy import deepcopy
from random import Random
from unittest.mock import Mock, patch

from django.template.loader import render_to_string
from django.test import SimpleTestCase
from evennia import create_object, create_script
from evennia.utils.dbserialize import deserialize
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from typeclasses.interactables import INTERACTABLES, Container
from typeclasses.loot import Corpse
from typeclasses.scripts import WorldLifecycle
from world import environment as env
from world.content import REGIONS, ROOMS
from world.content.environment import WEATHERS
from world.content.integrity import errors
from world.distant_presentation import DistantViewContext
from world.environment_state import reconcile_environment, snapshot_for
from world.lifecycle import reconcile_world
from world.multiplayer import world_change
from world.state import multiplayer_state

from tests.base import WorldCommandTest


class EnvironmentTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        for module in ("typeclasses.enemies", "typeclasses.explorers", "typeclasses.loot"):
            self.enterContext(patch(module + ".delay"))
        self.enterContext(patch("commands.character.time", return_value=100))
        self.rooms = self.world_rooms()
        self.script = create_script(WorldLifecycle, autostart=False)
        self.state = env.new_environment(100, Random(3))
        self.script.db.environment = self.state
        for player in (self.char1, self.char2):
            player.location = self.rooms["dock"]
            player.push_state = Mock()
        self.char1.location = self.rooms["grass"]

    def command(self, value):
        with patch.object(self.char1, "msg") as message:
            self.char1.execute_cmd(value)
        output = (
            message.call_args.args[0]
            if message.call_args.args
            else message.call_args.kwargs["text"]
        )
        return output[0] if isinstance(output, tuple) else output

    def test_clock_and_weather_persist_without_tick_writes_or_restart_events(self):
        before = deserialize(self.script.db.environment)
        with patch.object(
            self.script.attributes, "add", wraps=self.script.attributes.add
        ) as writes:
            reconcile_environment(105)
        writes.assert_not_called()
        with patch("world.environment_state.publish_changes") as publish:
            reconcile_environment(30000, restart=True)
            saved = deserialize(self.script.db.environment)
            reconcile_environment(30000, restart=True)
        self.assertEqual(saved, env.reconcile(before, 30000))
        self.assertEqual(saved, deserialize(self.script.db.environment))
        self.assertEqual(saved["clock"], before["clock"])
        publish.assert_not_called()
        self.script.attributes.reset_cache()
        self.assertEqual(
            snapshot_for(self.rooms["dock"], 30000).weather, saved["zones"]["island"]["weather"]
        )

    def test_initialization_is_once_and_does_not_reset_existing_epoch(self):
        self.script.attributes.remove("environment")
        reconcile_environment(100, restart=True)
        first = deserialize(self.script.db.environment)
        reconcile_environment(105, restart=True)
        self.assertEqual(deserialize(self.script.db.environment), first)
        self.assertEqual(first["clock"]["real_epoch"], 100)

    def test_period_change_emits_once_only_to_connected_zone_players(self):
        self.state["clock"]["game_epoch"] = 18 * 3600 - 4
        self.script.db.environment = self.state
        with (
            patch.object(self.char1.sessions, "count", return_value=1),
            patch.object(self.char2.sessions, "count", return_value=0),
            patch.object(self.char1, "msg") as connected,
            patch.object(self.char2, "msg") as offline,
        ):
            reconcile_world(101)
            connected.assert_called_once()
            offline.assert_not_called()
            self.char1.push_state.assert_called_once_with(observed_at=101)
            reconcile_world(106)
            connected.assert_called_once()
        self.assertEqual(deserialize(self.script.db.environment)["period"], "dusk")

    def test_weather_change_and_unchanged_weather_renewal_do_not_spam(self):
        self.state["zones"]["island"]["next_change_at"] = 101
        self.script.db.environment = self.state
        with (
            patch.object(self.char1.sessions, "count", return_value=1),
            patch.object(self.char2.sessions, "count", return_value=1),
            patch.object(self.char1, "msg") as first,
            patch.object(self.char2, "msg") as second,
        ):
            with patch.dict(WEATHERS["clear"], transitions={"cloudy": 1}):
                reconcile_world(101)
            first.assert_called_once()
            second.assert_called_once()
            for message in (first.call_args.args[0], second.call_args.args[0]):
                self.assertIn(WEATHERS["cloudy"]["presence"]["outdoor"], message)
            first.reset_mock()
            second.reset_mock()
            renewed = deserialize(self.script.db.environment)
            deadline = renewed["zones"]["island"]["next_change_at"]
            with patch.dict(WEATHERS["cloudy"], transitions={"cloudy": 1}):
                reconcile_world(deadline)
            first.assert_not_called()
            second.assert_not_called()

    def test_notifications_exclude_other_weather_zone(self):
        with (
            patch.dict(REGIONS["deep_jungle"], weather_zone="other"),
            patch.object(self.char1.sessions, "count", return_value=1),
            patch.object(self.char2.sessions, "count", return_value=1),
            patch.object(self.char1, "msg") as first,
            patch.object(self.char2, "msg") as second,
        ):
            self.char2.location = self.rooms["jungle_edge"]
            from world.environment_state import publish_changes

            after = deepcopy(self.state)
            after["zones"]["island"]["weather"] = "cloudy"
            publish_changes(self.state, after, {"island"}, 100)
            first.assert_called_once()
            second.assert_not_called()

    def test_failed_environment_save_rolls_back_and_publishes_nothing(self):
        self.state["clock"]["game_epoch"] = 18 * 3600 - 4
        self.script.db.environment = self.state
        before = deepcopy(self.char1.profile())
        original_add = self.script.attributes.add

        def fail_after_save(*args, **kwargs):
            original_add(*args, **kwargs)
            raise RuntimeError("environment save failed")

        with (
            patch.object(self.script.attributes, "add", side_effect=fail_after_save),
            patch("world.environment_state.publish_changes") as publish,
            self.assertRaises(RuntimeError),
        ):
            reconcile_environment(101)
        self.assertEqual(deserialize(self.script.db.environment), self.state)
        self.assertEqual(self.char1.profile(), before)
        publish.assert_not_called()
        with patch("world.environment_state.publish_changes") as publish:
            reconcile_environment(101)
        publish.assert_called_once()

    def test_nested_transaction_failure_discards_notifications_and_environment(self):
        before = deserialize(self.script.db.environment)
        with patch("world.environment_state.publish_changes") as publish:
            with self.assertRaises(RuntimeError), world_change():
                reconcile_environment(30000)
                raise RuntimeError("outer mutation failed")
        self.script.attributes.reset_cache()
        self.assertEqual(deserialize(self.script.db.environment), before)
        publish.assert_not_called()

    def test_local_remote_command_and_web_use_same_observed_at_without_profile_write(self):
        before = deepcopy(self.char1.profile())
        state_before = deserialize(self.script.db.environment)
        local = self.command("보기")
        snapshot = snapshot_for(self.char1.location, 100)
        self.assertIn(env.description(snapshot), local)
        self.char1.push_state.assert_called_with(observed_at=100)
        distant = self.command("북 봐")
        target = self.rooms["trail"]
        self.assertIn(env.description(snapshot_for(target, 100)), distant)
        self.assertEqual(self.command("날씨"), self.command("환경"))
        self.assertIn("08:00", self.command("날씨"))
        self.assertIn("날씨", self.command("이동 도움말"))
        with (
            patch.object(self.char1.sessions, "count", return_value=1),
            patch.object(self.char1, "msg") as message,
        ):
            Explorer.push_state(self.char1, observed_at=100)
        payload = message.call_args.kwargs["pz_state"][0][0]
        self.assertEqual(payload["environment"], env.display(snapshot))
        json.dumps(payload)
        self.assertEqual(deserialize(self.script.db.environment), state_before)
        self.assertEqual(self.char1.profile(), before)
        self.assertEqual(self.char1.location, self.rooms["grass"])

    def test_weather_command_and_push_do_not_migrate_legacy_profile_in_db(self):
        legacy = deepcopy(self.char1.profile())
        legacy.update(version=4)
        legacy.pop("storage")
        self.char1.db.profile = legacy
        with patch.object(self.char1, "profile", side_effect=AssertionError("migration write")):
            for zone in ("grass", "dock"):
                self.char1.location = self.rooms[zone]
                self.command("날씨")
                with (
                    patch.object(self.char1.sessions, "count", return_value=1),
                    patch.object(self.char1, "msg"),
                ):
                    Explorer.push_state(self.char1, observed_at=100)
        self.assertEqual(deserialize(self.char1.db.profile), legacy)

    def test_weather_and_darkness_filter_targets_without_changing_claim_permissions(self):
        player = self.char1
        before_state = multiplayer_state(player, now=100)
        self.state["clock"]["game_epoch"] = 22 * 3600
        self.state["zones"]["island"].update(weather="storm", next_change_at=100000)
        self.script.db.environment = self.state
        self.assertEqual(snapshot_for(player.location, 100).visibility, "poor")
        self.assertEqual(multiplayer_state(player, now=100)["enemies"], [])
        self.assertNotIn("어린청소룡", self.command("보기"))
        from world import lighting

        profile = player.profile()
        profile["inventory"].update(flashlight=1, battery=1)
        lighting.insert_power(profile, "flashlight", "battery", 100)
        lighting.switch(profile, "flashlight", True, 100)
        player.save_profile(profile)
        self.assertEqual(multiplayer_state(player, now=100)["enemies"], before_state["enemies"])
        self.assertIn("어린청소룡", self.command("보기"))

    def test_blocked_exit_never_queries_environment_or_hidden_target(self):
        self.char1.location = self.rooms["marsh"]
        before = deepcopy(self.char1.profile())
        with patch(
            "world.environment_state.snapshot_for",
            side_effect=AssertionError("blocked environment read"),
        ):
            self.assertIn("진입문", self.command("북 봐"))
        self.assertEqual(self.char1.profile(), before)
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(generator_fixed=True))
        self.assertIn("통신탑 능선", self.command("북 봐"))

    def test_remote_environment_reads_no_contents_and_does_not_reconcile_lifecycle(self):
        target = self.rooms["trail"]
        corpse = create_object(Corpse, key="검증시체", location=target)
        corpse.db.decay_at = 90
        corpse.db.entries = []
        enemy = room_enemies(target)[0]
        enemy.db.state = "respawning"
        enemy.db.respawn_at = 90
        box = create_object(Container, key="검증상자", location=target)
        box.db.items = {"water": 3}
        before = {
            obj.id: [(a.key, deserialize(a.value)) for a in obj.attributes.all()]
            for obj in target.contents
        }
        context = DistantViewContext(self.char1, self.char1.location, target, observed_at=100)
        with patch(
            "world.lifecycle.reconcile_room", side_effect=AssertionError("remote lifecycle")
        ):
            output = target.return_distant_appearance(context)
        self.assertIn(env.description(snapshot_for(target, 100)), output)
        for secret in (corpse.key, enemy.key, "정제수", "시체 1", "갈퀴사냥룡 1"):
            self.assertNotIn(secret, output)
        self.assertEqual(
            before,
            {
                obj.id: [(a.key, deserialize(a.value)) for a in obj.attributes.all()]
                for obj in target.contents
            },
        )

    def test_environment_content_integrity_requires_explicit_room_metadata(self):
        self.assertEqual(errors(INTERACTABLES), [])
        for key in ("exposure", "light_profile"):
            room = dict(ROOMS["dock"])
            room.pop(key)
            with patch.dict(ROOMS, dock=room):
                self.assertTrue(any(key in issue for issue in errors(INTERACTABLES)))
        with patch.dict(REGIONS["outpost"], weather_zone="unknown"):
            self.assertTrue(any("Weather Zone" in issue for issue in errors(INTERACTABLES)))
        with patch.dict(WEATHERS["clear"], transitions={"unknown": 1}):
            self.assertTrue(any("전이" in issue for issue in errors(INTERACTABLES)))
        with patch.dict(WEATHERS["clear"], transitions={"cloudy": 0}):
            self.assertTrue(any("가중치" in issue for issue in errors(INTERACTABLES)))
        with patch.dict(WEATHERS["clear"], duration=(50, 10)):
            self.assertTrue(any("지속 시간" in issue for issue in errors(INTERACTABLES)))

    def test_fixed_light_period_change_skips_ambient_but_pushes_latest_state(self):
        self.char1.location = self.rooms["generator"]
        before_profile = deserialize(self.char1.db.profile)
        for light_profile in ("dim", "artificial"):
            self.state["clock"]["game_epoch"] = 18 * 3600 - 4
            self.script.db.environment = self.state
            with (
                patch.dict(ROOMS["generator"], light_profile=light_profile),
                patch.object(self.char1.sessions, "count", return_value=1),
                patch.object(self.char2.sessions, "count", return_value=0),
                patch.object(self.char1, "msg") as message,
            ):
                before = env.state_snapshot(self.state, "generator", 101)
                reconcile_world(101)
                after = snapshot_for(self.char1.location, 101)
                self.assertEqual(env.description(before), env.description(after))
                message.assert_not_called()
                self.char1.push_state.assert_called_with(observed_at=101)
                self.assertEqual(after.period, "dusk")
                # 실제 웹 발행 경로도 최신 period/time을 전달하며 profile을 쓰지 않는다.
                Explorer.push_state(self.char1, observed_at=101)
                payload = message.call_args.kwargs["pz_state"][0][0]
                self.assertEqual(payload["environment"]["period"]["id"], "dusk")
                self.assertEqual(payload["environment"]["time"], "18:00")
        self.assertEqual(deserialize(self.char1.db.profile), before_profile)

    def test_indoor_weather_change_emits_once_even_with_fixed_light(self):
        self.char1.location = self.rooms["generator"]
        self.state["zones"]["island"].update(weather="rain", next_change_at=101)
        self.script.db.environment = self.state
        with (
            patch.dict(WEATHERS["rain"], transitions={"storm": 1}),
            patch.object(self.char1.sessions, "count", return_value=1),
            patch.object(self.char2.sessions, "count", return_value=0),
            patch.object(self.char1, "msg") as message,
        ):
            reconcile_world(101)
            message.assert_called_once()
            self.assertIn("거센 빗소리", message.call_args.args[0])
            self.char1.push_state.assert_called_once_with(observed_at=101)
            reconcile_world(106)
            message.assert_called_once()

    def test_legacy_state_migrates_once_without_reset_or_read_side_effects(self):
        legacy = deepcopy(self.state)
        legacy.pop("version")
        self.script.db.environment = legacy
        snapshot_for(self.rooms["dock"], 100)
        self.assertEqual(deserialize(self.script.db.environment), legacy)
        with (
            patch.object(self.script.attributes, "add", wraps=self.script.attributes.add) as writes,
            patch("world.environment_state.publish_changes") as publish,
        ):
            reconcile_environment(100)
            writes.assert_called_once()
            saved = deserialize(self.script.db.environment)
            self.assertEqual(saved, env.normalize_state(legacy))
            reconcile_environment(105)
            writes.assert_called_once()
            publish.assert_not_called()

    def test_future_state_remains_intact_when_reconciliation_fails(self):
        future = deepcopy(self.state)
        future["version"] = env.ENVIRONMENT_VERSION + 1
        self.script.db.environment = future
        with (
            patch("world.environment_state.publish_changes") as publish,
            self.assertRaisesRegex(ValueError, "저장 버전"),
        ):
            reconcile_environment(100)
        self.assertEqual(deserialize(self.script.db.environment), future)
        publish.assert_not_called()

    def test_local_static_and_object_presence_stay_equal_across_weather_changes(self):
        from world import lighting

        profile = self.char1.profile()
        profile["inventory"].update(flashlight=1, battery=1)
        lighting.insert_power(profile, "flashlight", "battery", 100)
        lighting.switch(profile, "flashlight", True, 100)
        self.char1.save_profile(profile)
        for zone, weathers in (
            ("dock", ("clear", "fog")),
            ("office", ("clear", "rain", "storm")),
            ("marsh", ("clear", "fog")),
        ):
            room = self.rooms[zone]
            self.char1.location = room
            static = ROOMS[zone]["desc"]
            outputs, descriptions = [], []
            for weather in weathers:
                self.state["zones"]["island"]["weather"] = weather
                self.script.db.environment = self.state
                output = room.return_appearance(self.char1, observed_at=100)
                description = env.description(snapshot_for(room, 100))
                self.assertIn(static, output)
                self.assertIn(description, output)
                self.assertEqual(ROOMS[zone]["desc"], static)
                outputs.append(output.replace(description, ""))
                descriptions.append(description)
                if weather == "clear":
                    self.assertNotIn("안개가", output)
                    self.assertNotIn("비가 새는", output)
                elif weather == "fog":
                    self.assertEqual(output.count("낮게 깔린 안개가"), 1)
            self.assertEqual(len(set(outputs)), 1)  # 환경 외 방향도·객체 묘사는 동일하다.
            self.assertEqual(len(set(descriptions)), len(weathers))


class EnvironmentWebTemplateTests(SimpleTestCase):
    def test_fresh_assets_and_field_guide_weather_entry_use_existing_command(self):
        html = render_to_string("webclient/webclient.html")
        self.assertIn("webclient/css/primal.css?v=supply-chip-review", html)
        self.assertIn("webclient/js/primal.js?v=supply-chip-review", html)
        self.assertNotIn("webclient/js/primal.js?v=elevator", html)
        self.assertNotIn("webclient/js/primal.js?v=lighting", html)
        self.assertNotIn("?v=compact", html)
        self.assertNotIn("?v=item-interactions", html)
        self.assertIn('data-command="날씨">환경 확인', html)
        self.assertIn('id="environment-status"', html)
