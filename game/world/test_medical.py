"""의료·패배 규칙의 의미 경계와 상태 보존."""

from copy import deepcopy
from random import Random
from unittest import TestCase
from unittest.mock import patch

from world import rules


class MedicalRulesTests(TestCase):
    def test_defeat_penalty_minimum_hp_and_preserved_progress(self):
        for credits in (50, 4, 0):
            profile = rules.new_profile()
            profile.update(hp=-3, credits=credits, xp=123, storage={"bandage": 4})
            before = deepcopy(profile)
            with patch.object(rules, "treat") as treat, patch.object(rules, "rest") as rest:
                self.assertEqual(rules.apply_defeat(profile), min(credits, 10))
                treat.assert_not_called()
                rest.assert_not_called()
            before.update(hp=rules.DEFEAT_RECOVERY_HP, credits=max(0, credits - 10))
            self.assertEqual(profile, before)
            with self.assertRaises(rules.RuleError):
                rules.apply_defeat(profile)
            self.assertEqual(profile, before)

    def test_enemy_attack_does_not_apply_defeat_recovery_or_penalty(self):
        profile = rules.new_profile()
        profile.update(hp=1, credits=50)
        with patch.object(rules, "apply_defeat") as recovery:
            outcome = rules.enemy_attack(profile, "alpha", 3, 100, Random(4))
            recovery.assert_not_called()
        self.assertTrue(outcome["defeated"])
        self.assertLessEqual(profile["hp"], 0)
        self.assertEqual(profile["credits"], 50)

    def test_treat_and_rest_are_independent_free_full_heals(self):
        for operation, other in ((rules.treat, "rest"), (rules.rest, "treat")):
            profile = rules.new_profile()
            profile.update(hp=5, credits=0)
            before = deepcopy(profile)
            with patch.object(rules, other) as separate, patch.object(rules, "first_aid") as bandage:
                self.assertEqual(operation(profile, safe=True), 55)
                separate.assert_not_called()
                bandage.assert_not_called()
            before["hp"] = 60
            self.assertEqual(profile, before)

    def test_rejected_medical_rules_never_mutate(self):
        for operation in (rules.treat, rules.rest):
            for hp, safe, target in ((60, True, None), (1, False, None), (1, True, 99)):
                profile = rules.new_profile()
                profile.update(hp=hp, combat_target=target)
                before = deepcopy(profile)
                with self.assertRaises(rules.RuleError):
                    operation(profile, safe=safe)
                self.assertEqual(profile, before)


if __name__ == "__main__":
    import unittest

    unittest.main()
