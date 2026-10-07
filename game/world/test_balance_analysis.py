"""실제 규칙 재사용·합법적 build·가격 변화와 전투의 분리 회귀."""

from unittest import TestCase
from unittest.mock import patch

from world import balance_analysis as analysis
from world.content import ITEMS


class BalanceAnalysisTests(TestCase):
    def test_builds_fit_actual_attribute_training_and_loadout_budgets(self):
        for spec in analysis.build_specs().values():
            analysis.build(spec)  # 실제 validate_loadout와 성장 예산 검사

    def test_fixed_seed_is_reproducible_and_ammo_price_does_not_change_combat(self):
        spec = analysis.build_specs()["t1_firearm"]
        before = analysis.fight([spec], "sentinel", 3)
        self.assertEqual(before, analysis.fight([spec], "sentinel", 3))
        unit = ITEMS["ammo_556"]["purchase_unit_value"]
        with patch.dict(ITEMS["ammo_556"], purchase_unit_value=unit + 1):
            after = analysis.fight([spec], "sentinel", 3)
        for key in before.keys() - {"ammo_cost", "net"}:
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(after["ammo_cost"] - before["ammo_cost"], before["shots"])
        self.assertEqual(before["net"] - after["net"], before["shots"])

    def test_party_reward_conservation_and_support_is_finite(self):
        specs = analysis.build_specs()
        result = analysis.summary([specs[f"t1_{role}"] for role in
                                   ("shield", "2h", "firearm", "support")], "alpha", 4)
        self.assertEqual(sum(result["xp_shares"].values()), 130)
        self.assertEqual(sum(result["currency_shares"].values()), 50)
        self.assertGreater(result["mental_spent"], 0)
        self.assertGreater(result["healed"], 0)
        self.assertLess(result["rounds"], 200)
