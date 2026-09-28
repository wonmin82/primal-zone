"""전원 확장성, 실패 불변성, 시각 기반 소모와 관찰자별 시야를 DB 없이 검증한다."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from random import Random
from unittest import TestCase
from unittest.mock import patch

from world import environment, lighting, rules
from world.content import ITEMS
from world.content.facilities import FACILITIES
from world.facility_state import (
    FACILITY_STATE_VERSION,
    new_facility_state,
    normalize_facility_state,
)
from world.observation import observe, perceives
from world.targets import parse_relation, stack_selector


class LightingRulesTests(TestCase):
    def setUp(self):
        self.profile = rules.new_profile()
        self.profile["inventory"].update(flashlight=1, battery=2)
        state = environment.new_environment(100, Random(3))
        self.environment = replace(environment.snapshot(state, "grass", 100), ambient_light="dark", visibility="poor")

    def test_facility_schema_defaults_legacy_and_no_mutation(self):
        expected = {"version": FACILITY_STATE_VERSION, "states": {"outpost_power": False}}
        self.assertEqual(new_facility_state(), expected)
        for state in (None, {}):
            self.assertEqual(normalize_facility_state(state), expected)
        legacy = {"outpost_power": True}
        self.assertTrue(normalize_facility_state(legacy)["states"]["outpost_power"])
        self.assertEqual(legacy, {"outpost_power": True})
        migrated = normalize_facility_state(legacy)
        self.assertEqual(normalize_facility_state(migrated), migrated)

    def test_future_facility_version_is_rejected_without_reset(self):
        future = {"version": FACILITY_STATE_VERSION + 1, "states": {"outpost_power": True}}
        before = deepcopy(future)
        with self.assertRaisesRegex(ValueError, "지원하지 않는 시설"):
            normalize_facility_state(future)
        self.assertEqual(future, before)

    def test_facility_definitions_extend_default_state_without_id_branch(self):
        with patch.dict(FACILITIES, test_power={"default": True}):
            self.assertTrue(new_facility_state()["states"]["test_power"])
            self.assertTrue(normalize_facility_state({})["states"]["test_power"])

    def test_facility_presence_only_replaces_base_light_when_it_contributes(self):
        state = environment.new_environment(100, Random(3))
        day = environment.snapshot(state, "dock", 100, facility_light=4)
        self.assertFalse(day.facility_light_effective)
        self.assertIn("낮빛", environment.description(day))
        self.assertNotIn("시설 조명", environment.description(day))
        state["clock"]["game_epoch"] = 22 * 3600
        night = environment.snapshot(state, "dock", 100, facility_light=4)
        self.assertTrue(night.facility_light_effective)
        self.assertIn("시설 조명", environment.description(night))
        for zone in ("office", "generator"):
            off = environment.snapshot(state, zone, 100)
            on = environment.snapshot(state, zone, 100, facility_light=4)
            self.assertNotIn("시설 조명", environment.description(off))
            self.assertIn("시설 조명", environment.description(on))
            self.assertEqual(on.base_light_score, off.base_light_score)
            self.assertEqual(on.ambient_light, "bright")

    def test_timestamp_on_off_and_exact_exhaustion(self):
        lighting.insert_power(self.profile, "flashlight", "battery", 100)
        self.assertEqual(lighting.projected(self.profile, "flashlight", 100)["charge_seconds"], 1800)
        lighting.switch(self.profile, "flashlight", True, 100)
        saved = deepcopy(self.profile)
        self.assertEqual(lighting.projected(self.profile, "flashlight", 700)["charge_seconds"], 1200)
        self.assertEqual(self.profile, saved)
        lighting.switch(self.profile, "flashlight", False, 700)
        self.assertEqual(lighting.projected(self.profile, "flashlight", 1300)["charge_seconds"], 1200)
        lighting.switch(self.profile, "flashlight", True, 1300)
        self.assertFalse(lighting.normalize(self.profile, 2499))
        self.assertTrue(lighting.normalize(self.profile, 2500))
        self.assertEqual(lighting.projected(self.profile, "flashlight", 2500),
                         {"on": False, "power_source": None, "charge_seconds": 0, "started_at": None})
        self.assertFalse(lighting.normalize(self.profile, 2505))

    def test_metadata_extension_uses_same_relation_and_selector(self):
        alternate = {"name": "고용량건전지", "slot": "consumable",
                     "power_source": {"type": "flashlight_battery", "capacity_seconds": 3600}}
        with patch.dict(ITEMS, high_capacity_battery=alternate):
            self.profile["inventory"]["high_capacity_battery"] = 1
            for name in ("손전등", "탐사용손전등"):
                target, value = parse_relation(name + "에 고용량건전지", "에", lighting.source_names())
                device, _ = stack_selector(target.name, ITEMS, "넣어", allow_all=False)
                power, _ = stack_selector(value, ITEMS, "넣어", allow_all=False)
                candidate = deepcopy(self.profile)
                lighting.insert_power(candidate, device, power, 100)
                self.assertEqual(lighting.projected(candidate, device, 100)["charge_seconds"], 3600)
                self.assertEqual(candidate["light_sources"][device]["power_source"], "high_capacity_battery")

    def test_failed_insertions_preserve_every_field(self):
        incompatible = {"name": "차량배터리", "slot": "material",
                        "power_source": {"type": "vehicle", "capacity_seconds": 7200}}
        with patch.dict(ITEMS, vehicle_battery=incompatible):
            self.profile["inventory"]["vehicle_battery"] = 1
            for power in ("vehicle_battery", "bandage"):
                before = deepcopy(self.profile)
                with self.assertRaises(rules.RuleError):
                    lighting.insert_power(self.profile, "flashlight", power, 100)
                self.assertEqual(self.profile, before)
        lighting.insert_power(self.profile, "flashlight", "battery", 100)
        before = deepcopy(self.profile)
        with self.assertRaises(rules.RuleError):
            lighting.insert_power(self.profile, "flashlight", "battery", 200)
        self.assertEqual(self.profile, before)

    def test_no_power_no_possession_off_and_out_of_range_have_no_effect(self):
        self.assertEqual(observe(self.environment, self.profile, 100).effective_visibility, "poor")
        lighting.insert_power(self.profile, "flashlight", "battery", 100)
        self.assertEqual(observe(self.environment, self.profile, 100).effective_visibility, "poor")
        lighting.switch(self.profile, "flashlight", True, 100)
        self.assertEqual(observe(self.environment, self.profile, 100).effective_visibility, "clear")
        self.assertEqual(observe(self.environment, self.profile, 100, 1).effective_visibility, "reduced")
        self.assertEqual(observe(self.environment, self.profile, 100, 2).effective_visibility, "poor")
        self.profile["inventory"].pop("flashlight")
        self.assertEqual(observe(self.environment, self.profile, 100).effective_visibility, "poor")
        self.assertTrue(lighting.normalize(self.profile, 100))
        self.assertEqual(self.profile["light_sources"], {})

    def test_immutable_viewer_dependent_snapshot_and_matrix(self):
        before = deepcopy(self.profile)
        sight = observe(self.environment, self.profile, 100)
        self.assertEqual(self.profile, before)
        with self.assertRaises(FrozenInstanceError):
            sight.effective_visibility = "clear"
        for visibility, allowed in (("clear", (True, True, True)), ("reduced", (True, True, False)), ("poor", (True, False, False))):
            snapshot = replace(sight, effective_visibility=visibility)
            self.assertEqual(tuple(perceives(snapshot, kind) for kind in ("conspicuous", "normal", "subtle")), allowed)

    def test_v5_migration_preserves_inventory_equipment_storage_quests_combat(self):
        old = deepcopy(self.profile)
        old["version"] = 5
        old.pop("light_sources")
        old["storage"] = {"scrap": 7}
        before = deepcopy(old)
        migrated = rules.migrate_profile(old)
        self.assertEqual(migrated["version"], 6)
        self.assertEqual(migrated["light_sources"], {})
        self.assertEqual({key: value for key, value in migrated.items() if key not in ("version", "light_sources")},
                         {key: value for key, value in old.items() if key != "version"})
        self.assertEqual(old, before)
        self.assertEqual(rules.migrate_profile(migrated), migrated)

    def test_supplies_claim_once_and_keep_previous_jungle_reward(self):
        self.profile["inventory"].pop("flashlight")
        self.profile["inventory"].pop("battery")
        rules.claim_emergency_light_cache(self.profile)
        self.assertEqual(self.profile["inventory"]["flashlight"], 1)
        self.assertEqual(self.profile["inventory"]["battery"], 2)
        before = deepcopy(self.profile)
        with self.assertRaises(rules.RuleError):
            rules.claim_emergency_light_cache(self.profile)
        self.assertEqual(self.profile, before)
        rules.claim_jungle_cache(self.profile)
        self.assertEqual(self.profile["inventory"]["bandage"], before["inventory"]["bandage"] + 2)
        self.assertEqual(self.profile["inventory"]["battery"], 4)

    def test_logout_freezes_charge_and_no_ongoing_tick_writes(self):
        lighting.insert_power(self.profile, "flashlight", "battery", 100)
        lighting.switch(self.profile, "flashlight", True, 100)
        before = deepcopy(self.profile)
        self.assertFalse(lighting.normalize(self.profile, 200))
        self.assertEqual(self.profile, before)
        self.assertTrue(lighting.normalize(self.profile, 200, turn_off=True))
        self.assertEqual(lighting.projected(self.profile, "flashlight", 5000)["charge_seconds"], 1700)
