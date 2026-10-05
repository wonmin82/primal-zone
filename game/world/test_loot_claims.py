import unittest

from world.loot_claims import ClaimContext, same_claim_context


class ClaimContractTests(unittest.TestCase):
    def test_same_allocation_and_rights_are_semantically_equal(self):
        first = ClaimContext("root-A", 1, None, 2, 300)
        self.assertTrue(same_claim_context(first, ClaimContext("root-A", 1, None, 2, 300)))
        self.assertFalse(same_claim_context(first, ClaimContext("root-B", 1, None, 2, 300)))
        self.assertFalse(same_claim_context(first, ClaimContext("root-A", 1, None, 3, 300)))
        self.assertTrue(same_claim_context(None, None))
        self.assertFalse(same_claim_context(first, None))
