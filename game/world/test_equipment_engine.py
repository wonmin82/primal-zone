"""ORM 없이 modifier·정의·Defense V1·기술 연결을 검증한다."""

from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock, patch

from world import equipment as eq
from world import modifiers as mod
from world import progression as pg
from world import recovery, rules
from world.content import ENEMIES, ITEMS
from world.item_entities.policy import definition_errors


class EquipmentEngineTests(TestCase):
    def profile(self, modifiers, weapon_type="melee"):
        data = {**deepcopy(ITEMS["machete"]), "equipment_properties": {
            "slot": "hands", "role": "weapon", "hands_required": 1,
            "weapon_type": weapon_type, "weapon_attack": 2}, "modifiers": modifiers}
        item = eq.item_snapshot("fixture", data, item_id="opaque")
        return eq.EquipmentProfile(rules.new_profile(), eq.EquipmentSnapshot((item,), (item,), "opaque"))

    def modifier(self, target, value, op="add", scope="equipped"):
        return {"target": target, "op": op, "value": value, "scope": scope}

    def test_add_then_product_and_target_clamps(self):
        selected = [mod.Modifier("stat.attack", "multiply", 1.04, "equipped"),
                    mod.Modifier("stat.attack", "add", 4, "equipped"),
                    mod.Modifier("stat.attack", "multiply", 1.03, "equipped")]
        self.assertAlmostEqual(mod.apply("stat.attack", 10, selected), 14 * 1.04 * 1.03)
        self.assertEqual(mod.apply("stat.defense", -5), 0)
        self.assertEqual(mod.apply("skill.shooting.penetration", 2), 1)
        self.assertEqual(len(mod.TARGETS), 15)

    def test_invalid_definition_metadata_is_rejected_early(self):
        valid = {**deepcopy(ITEMS["machete"]), "equipment_properties": {
            "slot": "hands", "role": "weapon", "hands_required": 1, "weapon_type": "melee"}}
        for key, value in (("slot", "unknown"), ("slot", []), ("role", None),
                           ("hands_required", 3), ("hands_required", True), ("weapon_type", None),
                           ("weapon_attack", float("nan"))):
            with self.subTest(field=key):
                data = deepcopy(valid)
                data["equipment_properties"][key] = value
                self.assertTrue(definition_errors("fixture", data))
        for key, value in (("target", "unknown"), ("target", []), ("op", "unknown"),
                           ("scope", "unknown"), ("value", True), ("value", float("inf"))):
            with self.subTest(field=key):
                data = deepcopy(valid)
                data["modifiers"] = [{**self.modifier("stat.attack", 1), key: value}]
                self.assertTrue(definition_errors("fixture", data))

    def test_defense_diminishing_returns_penetration_and_reduction(self):
        self.assertEqual(rules.apply_defense(100, 0), 100)
        self.assertEqual(rules.apply_defense(100, 20), 50)
        self.assertEqual(rules.apply_defense(100, 40), 33)
        self.assertEqual(rules.apply_defense(100, 40, .5), 50)
        self.assertEqual(rules.apply_defense(100, 40, .5, .2), 40)
        self.assertEqual(rules.apply_defense(.1, 100000, 0, 1), 1)
        self.assertEqual(rules.apply_defense(19.9, 1, .2, .152), int(19.9 * 20 / 20.8 * .848))

    def test_both_attack_paths_use_same_curve_and_rounding(self):
        profile = self.profile([self.modifier("stat.attack", 10), self.modifier("stat.defense", 7)])
        enemy = {**ENEMIES["scavenger"], "attack": 19, "defense": 7, "special_period": None}
        profile.update(combat_target=1)
        rng = Mock(randint=Mock(return_value=0))
        with patch.dict(ENEMIES, {"fixture": enemy}):
            player_damage = rules.player_attack(profile, "fixture", 100, 2.5, rng)[0]
            enemy_damage = rules.enemy_attack(profile, "fixture", 1, 100, rng)["damage"]
        self.assertEqual(player_damage, rules.apply_defense(19, 7))
        self.assertEqual(player_damage, enemy_damage)

    def test_heavy_and_shooting_damage_and_penetration_targets(self):
        rng = Mock(randint=Mock(return_value=0))
        for action, kind in (("heavy", "melee"), ("shooting", "firearm")):
            profile = self.profile([self.modifier(f"skill.{action}.damage", 1.5, "multiply"),
                                    self.modifier(f"skill.{action}.damage", 2),
                                    self.modifier("skill.shooting.penetration", .03)], kind)
            profile.update(combat_target=1, queued_action=action)
            damage = rules.player_attack(profile, "alpha", 100, 2.5, rng)[0]
            penetration = .08 if action == "shooting" else 0
            expected = rules.apply_defense((9 * pg.physical_multiplier(action, 1) + 2) * 1.5,
                                          ENEMIES["alpha"]["defense"], penetration)
            self.assertEqual(damage, expected)

    def test_insight_and_suppression_modifiers_keep_progression_contract(self):
        profile = self.profile([self.modifier("skill.insight.penetration", .03),
                                self.modifier("skill.insight.damage", 1.04, "multiply"),
                                self.modifier("skill.suppress.reduction", .03)])
        profile.update(combat_target=1, queued_action="insight")
        effect = rules.player_attack(profile, "scavenger", 100, 2.5)[1]
        self.assertAlmostEqual(effect["penetration"], .28)
        self.assertAlmostEqual(effect["bonus"], 1.05 * 1.04 - 1)
        profile["queued_action"] = "suppress"
        effect = rules.player_attack(profile, "scavenger", 103, 2.5)[1]["suppression"]
        self.assertAlmostEqual(effect["reduction"], .13)
        applied = pg.apply_suppression({}, 1, 1, effect=effect)[0]
        self.assertEqual(applied["1"], effect)

    def test_heal_and_breathing_amount_targets_preserve_costs(self):
        profile = self.profile([self.modifier("skill.heal.amount", 3),
                                self.modifier("skill.breathing.amount", 3)])
        profile.update(hp=1, mental=20)
        result = rules.support_action(profile, "heal", 100)
        self.assertEqual(result["amount"], pg.healing_amount(60, 1, 0) + 3)
        self.assertEqual(result["cost"], pg.mental_cost("heal", 1))
        result = rules.support_action(profile, "breathing", 100)
        self.assertEqual(result["amount"], pg.breathing_amount(40, 1) + 3)

    def test_legacy_all_known_hand_metadata_and_numeric_translation(self):
        from world.equipment_legacy import LEGACY_HAND_UNITS

        for identity in ("machete", "blade", "spear", "jungle_blade", "carbine", "heavy_carbine"):
            item = eq.item_snapshot(identity, ITEMS[identity])
            self.assertEqual((item.slot, item.role, item.hands_required, item.weapon_attack),
                             ("hands", "weapon", LEGACY_HAND_UNITS.get(identity, 1), ITEMS[identity]["attack"]))
        for identity in ("vest", "leather_suit", "armor", "tactical_vest", "heavy_suit"):
            item = eq.item_snapshot(identity, ITEMS[identity])
            self.assertEqual(item.slot, "body")
            self.assertEqual(mod.apply("stat.defense", 0, item.modifiers), ITEMS[identity]["defense"])

    def test_legacy_automatic_replacement_is_atomic(self):
        profile = rules.new_profile()
        rules.add_item(profile, "blade")
        before = deepcopy(profile)
        with self.assertRaises(rules.RuleError):
            rules.equip(profile, "blade")
        self.assertEqual(profile, before)
        for operation in ("equip", "unequip"):
            with patch.dict(ITEMS["machete"]["operation_policy"], {operation: False}):
                with self.assertRaises(rules.RuleError):
                    getattr(rules, operation)(profile, "machete", "weapon")
            self.assertEqual(profile, before)

    def test_equipment_and_level_up_resource_semantics_are_distinct(self):
        profile = self.profile([self.modifier("stat.max_hp", 20), self.modifier("stat.max_mental", 20)])
        profile.update(hp=30, mental=20)
        rules.gain_xp(profile, 60)
        self.assertEqual((profile["hp"], profile["mental"]), (40, 25))
        self.assertEqual((rules.stats(profile)["max_hp"], rules.stats(profile)["max_mental"]), (90, 65))

    def test_recovery_multipliers_apply_after_room_and_character_base(self):
        profile = self.profile([self.modifier("recovery.hp_per_minute", 2, "multiply"),
                                self.modifier("recovery.mental_per_minute", 2, "multiply")])
        rates = recovery.player_rates(rules.stats(profile), room={"recovery": {"hp_per_minute": 6}},
                                      snapshot=eq.context(profile))
        self.assertEqual(rates, {"hp": 18, "mental": 12})
