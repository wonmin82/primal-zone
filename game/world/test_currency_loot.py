"""영속 backend도 기존 화폐 payout 수식과 eligibility 의미를 그대로 사용한다."""

import unittest

from world.loot_assets import currency_payouts, normalize_entry
from world.rules import RuleError


class CurrencyContractTests(unittest.TestCase):
    def entry(self, shares, *, deadline=300):
        return dict(kind="currency", id="credits", quantity=sum(shares.values()),
                    eligible_players=list(shares), remaining_shares=shares, protection_until=deadline)

    def test_partial_weighted_split_preserves_amount(self):
        entry = self.entry({1: 10, 2: 10})
        self.assertEqual(currency_payouts(entry, 5, 1, 100), {1: 3, 2: 2})
        self.assertEqual(currency_payouts(entry, 20, 1, 100), {1: 10, 2: 10})

    def test_zero_share_is_eligible_but_has_no_payout_weight(self):
        entry = normalize_entry(self.entry({1: 0, 2: 20}))
        self.assertEqual(entry["eligible_players"], [1, 2])
        self.assertEqual(currency_payouts(entry, 5, 1, 100), {2: 5})

    def test_expiry_free_payout_ignores_old_allocation(self):
        self.assertEqual(currency_payouts(self.entry({1: 10, 2: 10}), 5, 3, 300), {3: 5})

    def test_invalid_amount_or_share_sum_rejected(self):
        entry = self.entry({1: 10})
        for amount in (0, -1, 11, True):
            with self.subTest(amount=amount), self.assertRaises(RuleError):
                currency_payouts(entry, amount, 1, 100)
        entry["quantity"] = 11
        with self.assertRaises(RuleError):
            currency_payouts(entry, 1, 1, 100)
