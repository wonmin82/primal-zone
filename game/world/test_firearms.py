"""순수 발사 계약·자동 선택·정의/alias integrity 검증."""

from copy import deepcopy
from random import Random
from unittest import TestCase

from world import firearms, rules
from world.content import ITEMS, find_id
from world.content.integrity import alias_errors
from world.item_entities.policy import definition_errors
from world.targets import normalized


class FirearmDomainTests(TestCase):
    def test_automatic_reload_ties_and_current_preference(self):
        mags = [firearms.MagazineSnapshot("b", "mag", 2, "pistol_9mm", "9mm", 18, 12),
                firearms.MagazineSnapshot("a", "mag", 1, "pistol_9mm", "9mm", 12, 12)]
        gun = firearms.FirearmSnapshot("gun", "gun", "pistol_9mm")
        self.assertEqual(firearms.automatic_magazine(gun, mags).identity, "a")
        gun = firearms.FirearmSnapshot("gun", "gun", "pistol_9mm", mags[0])
        self.assertIsNone(firearms.automatic_magazine(gun, mags))

    def test_shot_contract_for_every_action_and_both_weapon_types(self):
        for weapon in ("melee", "firearm"):
            for action in ("attack", "shooting", "suppress", "insight", "heal", "breathing", "bandage"):
                self.assertEqual(firearms.needs_shot(action, weapon),
                                 weapon == "firearm" and action in ("attack", "shooting", "suppress"))
        profile = rules.new_profile()
        profile["equipment"]["weapon"] = "explorer_machete"
        for action in ("attack", "suppress"):
            profile["queued_action"] = action
            outcome = rules.player_attack(profile, "scavenger", 100, 2.5, Random(1))[1]
            self.assertFalse(outcome["shot_fired"])
        profile["equipment"]["weapon"] = "guard_carbine"
        profile["inventory"]["bandage"] = 1
        profile["hp"] = 30
        profile["queued_action"] = "bandage"
        self.assertFalse(rules.player_attack(profile, "scavenger", 100, 2.5)[1]["shot_fired"])

    def test_loaded_magazine_value_and_alias_normalization_collision(self):
        self.assertEqual(firearms.magazine_resale(7, 12, 1), 19)
        self.assertEqual(normalized(" 5.56-mm_카빈탄 "), normalized("556mm카빈탄"))
        self.assertNotEqual(normalized("556mm"), normalized("56mm"))
        self.assertNotEqual(normalized("556mm"), normalized("556"))
        self.assertEqual(find_id(ITEMS, "카빈-표준"), "mag_556_standard")
        self.assertEqual(alias_errors(ITEMS), [])
        collision = {**ITEMS, "wrong": {"name": "다른 탄창", "aliases": ["권총_표준"]}}
        self.assertTrue(alias_errors(collision))

    def test_all_definitions_and_invalid_phase3_metadata(self):
        for identity, definition in ITEMS.items():
            with self.subTest(identity=identity):
                self.assertEqual(definition_errors(identity, definition), [])
        for changes in ({"magazine": {"family": "wrong", "ammo_type": "9mm", "capacity": 12}},
                        {"stackable": True}, {"magazine": {"family": "pistol_9mm", "ammo_type": "556mm", "capacity": 12}},
                        {"magazine": {"family": "pistol_9mm", "ammo_type": "9mm", "capacity": 0}}):
            definition = {**deepcopy(ITEMS["mag_9_standard"]), **changes}
            self.assertTrue(definition_errors("fixture", definition))
