"""공용 환경 계산: epoch, 경계, 기상 복구와 표현을 DB 없이 검증한다."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
from random import Random
from unittest import TestCase
from unittest.mock import Mock, patch

from world import environment as env
from world.content import REGIONS, ROOMS
from world.content.environment import WEATHERS


class EnvironmentRulesTests(TestCase):
    def state(self, hour=8, day=1, weather="clear"):
        state = env.new_environment(100, Random(7))
        state["clock"]["game_epoch"] = (day - 1) * 86400 + hour * 3600
        state["zones"]["island"].update(weather=weather, next_change_at=1000000)
        return state

    def test_accelerated_clock_epoch_and_midnight(self):
        state = self.state(hour=23)
        before = deepcopy(state)
        result = env.snapshot(state, "dock", 100 + 900)
        self.assertEqual((result.game_day, result.game_hour, result.game_minute), (2, 0, 0))
        self.assertEqual(
            env.game_seconds(state["clock"], 160) - env.game_seconds(state["clock"], 100), 240
        )
        self.assertEqual(state, before)
        self.assertEqual(set(state["clock"]), {"real_epoch", "game_epoch", "time_scale"})

    def test_period_boundaries_on_both_sides(self):
        for hour, old, new in (
            (5, "night", "dawn"),
            (7, "dawn", "day"),
            (18, "day", "dusk"),
            (20, "dusk", "night"),
        ):
            with self.subTest(hour=hour):
                self.assertEqual(env.period_at(hour * 3600 - 1), old)
                self.assertEqual(env.period_at(hour * 3600), new)
        self.assertEqual(env.period_at(86400), "night")

    def test_moon_cycles_and_only_changes_night_light(self):
        self.assertEqual(env.moon_at(1), env.moon_at(29))
        self.assertEqual(env.moon_at(14), "full")
        day_new = env.snapshot(self.state(day=1), "dock", 100)
        day_full = env.snapshot(self.state(day=14), "dock", 100)
        self.assertEqual(day_new.ambient_light, day_full.ambient_light)
        self.assertEqual(day_full.moon_light, 0)
        new = env.snapshot(self.state(hour=22), "dock", 100)
        full = env.snapshot(self.state(hour=22, day=14), "dock", 100)
        self.assertEqual((new.ambient_light, full.ambient_light), ("dark", "dim"))
        self.assertGreater(full.moon_light, new.moon_light)

    def test_light_and_visibility_matrix(self):
        for hour, day, weather, room, light, visibility in (
            (8, 1, "clear", "dock", "bright", "clear"),
            (8, 1, "storm", "dock", "dim", "poor"),
            (18, 1, "cloudy", "dock", "dim", "reduced"),
            (22, 14, "clear", "dock", "dim", "reduced"),
            (22, 1, "storm", "dock", "dark", "poor"),
            (8, 1, "clear", "generator", "dim", "reduced"),
            (8, 1, "fog", "dock", "normal", "poor"),
            (8, 1, "fog", "office", "dim", "reduced"),
        ):
            with self.subTest(hour=hour, weather=weather, room=room):
                snapshot = env.snapshot(self.state(hour, day, weather), room, 100)
                self.assertEqual((snapshot.ambient_light, snapshot.visibility), (light, visibility))
        with patch.dict(ROOMS["generator"], light_profile="artificial"):
            snapshot = env.snapshot(self.state(22, 1, "storm"), "generator", 100)
            self.assertEqual((snapshot.ambient_light, snapshot.visibility), ("normal", "clear"))

    def test_snapshot_immutable_and_zone_shared_with_independent_room_exposure(self):
        state = self.state(weather="rain")
        outdoor = env.snapshot(state, "dock", 100)
        indoor = env.snapshot(state, "office", 100)
        jungle = env.snapshot(state, "jungle_watch", 100)
        self.assertEqual({v.weather_zone for v in (outdoor, indoor, jungle)}, {"island"})
        self.assertEqual({v.weather for v in (outdoor, indoor, jungle)}, {"rain"})
        self.assertEqual(REGIONS["deep_jungle"]["weather_zone"], REGIONS["outpost"]["weather_zone"])
        self.assertIn("주변을 적시", env.description(outdoor))
        self.assertIn("바깥에서 빗소리", env.description(indoor))
        self.assertIn("지붕과 나뭇잎", env.description(jungle))
        with self.assertRaises(FrozenInstanceError):
            outdoor.weather = "storm"

    def test_deadline_no_early_transition_and_exact_boundary_transition(self):
        state = self.state()
        state["zones"]["island"]["next_change_at"] = 200
        rng = Mock()
        rng.choices.return_value = ["cloudy"]
        rng.uniform.return_value = 900
        self.assertEqual(env.reconcile(state, 199)["zones"], state["zones"])
        result = env.reconcile(state, 200, rng)["zones"]["island"]
        self.assertEqual(
            (result["weather"], result["started_at"], result["next_change_at"]),
            ("cloudy", 200, 1100),
        )
        self.assertEqual(state["zones"]["island"]["weather"], "clear")

    def test_seeded_transitions_follow_adjacency_and_durations(self):
        state = env.new_environment(100, Random(3))
        for _ in range(30):
            old = state["zones"]["island"]
            state = env.reconcile(state, old["next_change_at"])
            new = state["zones"]["island"]
            self.assertIn(new["weather"], WEATHERS[old["weather"]]["transitions"])
            minimum, maximum = WEATHERS[new["weather"]]["duration"]
            self.assertGreaterEqual(new["next_change_at"] - new["started_at"], minimum)
            self.assertLessEqual(new["next_change_at"] - new["started_at"], maximum)

    def test_restart_catchup_equals_frequent_reconciliation(self):
        original = env.new_environment(100, Random(3))
        regular = deepcopy(original)
        for now in range(100, 30001, 100):
            regular = env.reconcile(regular, now)
        self.assertEqual(env.reconcile(original, 30000), regular)
        self.assertEqual(env.reconcile(regular, 30000), regular)
        self.assertEqual(original["zones"]["island"]["step"], 0)
        self.assertEqual(regular["clock"], original["clock"])

    def test_very_long_outage_has_bounded_work_and_future_deadline(self):
        state = env.new_environment(0, Random(5))
        result = env.reconcile(state, 10**10)
        self.assertEqual(result["zones"]["island"]["step"], env.MAX_CATCHUP_TRANSITIONS)
        self.assertGreater(result["zones"]["island"]["next_change_at"], 10**10)
        self.assertEqual(env.reconcile(result, 10**10), result)

    def test_snapshot_projects_overdue_without_writing_or_resetting_clock(self):
        state = env.new_environment(100, Random(8))
        before = deepcopy(state)
        now = state["zones"]["island"]["next_change_at"] + 1
        projected = env.snapshot(state, "dock", now)
        expected = env.reconcile(state, now)
        self.assertEqual(projected.weather, expected["zones"]["island"]["weather"])
        self.assertEqual(projected.observed_at, now)
        self.assertEqual(state, before)

    def test_display_has_stable_ids_and_server_names_and_night_moon_sentence(self):
        snapshot = env.snapshot(self.state(22, 14), "dock", 100)
        display = env.display(snapshot)
        self.assertEqual(display["weather"], {"id": "clear", "name": "맑음"})
        self.assertEqual(display["time"], "22:00")
        self.assertEqual(display["moon"]["id"], "full")
        self.assertIn("보름달", env.description(snapshot))
        self.assertNotIn("보름달", env.description(env.snapshot(self.state(8, 14), "dock", 100)))
