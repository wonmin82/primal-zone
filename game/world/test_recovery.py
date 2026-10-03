"""시간·회복 source·현재값과 credit의 경계를 직접 검증한다."""

from copy import deepcopy
from unittest import TestCase

from world import presentation, recovery, rules, text
from world.content import ITEMS, ROOMS
from world.content.headquarters import ROOF_ROOMS
from world.content.integrity import recovery_errors


class RecoveryRulesTests(TestCase):
    def profile(self):
        profile = rules.new_profile()
        profile.update(hp=10, mental=10, recovery=recovery.initialize(0))
        return profile

    def accrue(self, profile, now, room=None, items=None):
        recovery.accrue_player(profile, rules.stats(profile), room or {}, ITEMS if items is None else items, now)

    def test_mental_formula_level_gain_wisdom_and_retrain(self):
        for level, wisdom, maximum in ((1, 0, 40), (5, 0, 60), (10, 0, 85), (10, 5, 105)):
            p = rules.new_profile()
            p["xp"] = rules.xp_threshold(level)
            p["attributes"]["wisdom"]["allocated"] = wisdom
            self.assertEqual(rules.stats(p)["max_mental"], maximum)
        p = rules.new_profile()
        p["mental"] = 15
        rules.gain_xp(p, 60)
        self.assertEqual(p["mental"], 20)
        rules.allocate_attribute(p, "wisdom", safe=True)
        self.assertEqual((p["mental"], rules.stats(p)["max_mental"]), (20, 49))
        p["mental"] = 49
        rules.retrain(p, "attributes", safe=True)
        self.assertEqual(p["mental"], 45)

    def test_rates_equipment_all_slots_and_combat_sources(self):
        items = {"one": {"recovery_bonus": {"hp_per_minute": 2}},
                 "two": {"recovery_bonus": {"mental_per_minute": 3}}}
        values = {"max_hp": 60, "max_mental": 40}
        room = {"recovery": {"hp_per_minute": 6, "mental_per_minute": 2}}
        self.assertEqual(recovery.player_rates(values, False, room, ("one", "two"), items), {"hp": 11, "mental": 11})
        self.assertEqual(recovery.player_rates(values, True, room, ("one", "two"), items), {"hp": 2, "mental": 9})
        self.assertEqual(recovery.player_rates(values, True), {"hp": 0, "mental": 6})
        for maximum, rate in ((40, 6), (60, 7), (85, 8.25), (105, 9.25)):
            self.assertEqual(recovery.player_rates({**values, "max_mental": maximum})["mental"], rate)
        self.assertAlmostEqual(recovery.enemy_rate(24), 9.6)
        self.assertAlmostEqual(recovery.enemy_rate(190), 20 + 2 / 3)

    def test_accrue_only_and_boundary_tail_preserved(self):
        p = self.profile()
        self.accrue(p, 7)
        self.accrue(p, 13)
        self.assertEqual((p["hp"], p["mental"]), (10, 10))
        recovery.commit(p, rules.stats(p))
        self.assertEqual((p["hp"], p["mental"]), (10, 11))
        self.assertAlmostEqual(p["recovery"]["credit"]["mental"], .3)
        self.accrue(p, 20)
        recovery.commit(p, rules.stats(p))
        self.assertEqual((p["hp"], p["mental"]), (11, 12))

    def test_many_short_updates_equal_long_offline_batch(self):
        short, long = self.profile(), self.profile()
        for now in range(1, 301):
            self.accrue(short, now)
            recovery.commit(short, rules.stats(short))
        self.accrue(long, 300)
        recovery.commit(long, rules.stats(long))
        self.assertEqual((short["hp"], short["mental"]), (long["hp"], long["mental"]))
        for bucket in ("ready", "credit"):
            for key in recovery.RESOURCES:
                self.assertAlmostEqual(short["recovery"][bucket][key], long["recovery"][bucket][key])

    def test_transition_preserves_previous_rates_without_instant_payment(self):
        p = self.profile()
        self.accrue(p, 9, ROOMS["infirmary"])
        p["combat_target"] = 1
        self.accrue(p, 20, ROOMS["infirmary"])
        self.assertEqual((p["hp"], p["mental"]), (10, 10))
        recovery.commit(p, rules.stats(p))
        self.assertEqual((p["hp"], p["mental"]), (11, 12))

    def test_room_change_and_equipment_change_segments(self):
        p = self.profile()
        self.accrue(p, 5, ROOMS["infirmary"])
        self.accrue(p, 10)
        recovery.commit(p, rules.stats(p))
        self.assertEqual(p["hp"], 11)
        items = deepcopy(ITEMS)
        items["machete"]["recovery_bonus"] = {"mental_per_minute": 6}
        p["equipment"]["future_slot"] = "machete"
        self.accrue(p, 20, items=items)
        recovery.commit(p, rules.stats(p))
        self.assertEqual(p["mental"], 14)
        p["equipment"] = {}
        self.accrue(p, 30, items=items)
        recovery.commit(p, rules.stats(p))
        self.assertEqual(p["mental"], 15)

    def test_timed_effect_start_expiry_and_long_offline(self):
        p = self.profile()
        p["recovery_effects"] = [{"started_at": 30, "expires_at": 150, "hp_per_minute": 6, "mental_per_minute": 4}]
        self.accrue(p, 300)
        recovery.commit(p, rules.stats(p))
        self.assertEqual((p["hp"], p["mental"]), (37, 40))
        self.assertEqual(p["recovery"]["credit"]["mental"], 0)

    def test_full_resources_clear_credit_and_never_bank_future_damage(self):
        p = rules.new_profile()
        p["recovery"] = recovery.initialize(0)
        self.accrue(p, 600)
        p["hp"] = 50
        recovery.commit(p, rules.stats(p))
        self.assertEqual(p["hp"], 50)
        p["recovery"]["ready"]["hp"] = .9
        rules.treat(p, safe=True)
        recovery.clamp(p, rules.stats(p))
        self.assertEqual(p["recovery"]["ready"]["hp"], 0)
        p["mental"] = -1
        recovery.clamp(p, rules.stats(p))
        self.assertEqual(p["mental"], 0)

    def test_migration_preserves_all_old_fields_and_is_read_only(self):
        old = rules.new_profile()
        old.update(version=8, xp=rules.xp_threshold(5), hp=7, credits=127)
        old.pop("mental")
        old.pop("recovery_effects")
        before = deepcopy(old)
        result = rules.migrate_profile(old)
        self.assertEqual(result, {**before, "version": 9, "mental": 60, "recovery_effects": []})
        self.assertEqual(old, before)
        self.assertEqual(rules.migrate_profile(result), result)
        self.assertNotIn("recovery", result)

    def test_medical_roles_and_firstaid_mental_unchanged(self):
        p = self.profile()
        rules.treat(p, safe=True)
        self.assertEqual((p["hp"], p["mental"]), (60, 10))
        before = p["proficiencies"]["medicine"]["xp"]
        rules.rest(p, safe=True)
        self.assertEqual((p["hp"], p["mental"]), (60, 40))
        self.assertEqual(p["proficiencies"]["medicine"]["xp"], before)
        with self.assertRaises(rules.RuleError):
            rules.rest(p, safe=True)
        p["hp"] = 1
        rules.first_aid(p)
        self.assertEqual(p["mental"], 40)

    def test_place_metadata_and_no_staging_bonus(self):
        for zone, hp, mental in (("infirmary", 6, 2), ("hq_concourse", 2, 2), ("office", 2, 1),
                                  *((zone, 0, 2) for zone in ROOF_ROOMS)):
            rates = recovery.player_rates(rules.stats(rules.new_profile()), room=ROOMS[zone])
            self.assertEqual(rates, {"hp": 3 + hp, "mental": 6 + mental})
        self.assertNotIn("recovery", ROOMS["staging_room"])
        for invalid in (-1, float("inf"), True, "2"):
            self.assertTrue(recovery_errors("fixture", {"recovery": {"hp_per_minute": invalid}}, "recovery"))

    def test_prompt_only_current_values_colored_and_ratio_boundaries(self):
        for value, role in ((67, "success"), (66, "warning"), (34, "warning"), (33, "error"), (1, "error"), (0, "critical")):
            p = {"hp": value, "mental": value}
            prompt = text.resource_prompt(p, {"max_hp": 100, "max_mental": 100})
            self.assertEqual(str(prompt), f"[ {value}/100 · {value}/100 ] >")
            self.assertEqual([part["text"] for part in prompt.segments if part["role"] != "text"], [str(value)] * 2)
            self.assertEqual([part["role"] for part in prompt.segments if part["role"] != "text"], [role] * 2)
        self.assertIn("정신력 40/40", presentation.status("탐사자", rules.new_profile()))
