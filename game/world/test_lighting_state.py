"""광원 전원의 순수 시간 투영과 canonical 상태 검증."""

from copy import deepcopy
from unittest import TestCase

from world.content import ITEMS
from world.item_states import default_state, state_errors
from world.lighting import project_power


class LightingDomainTests(TestCase):
    def test_projection_never_mutates_saved_state_and_clamps_exhaustion(self):
        state = {**default_state(ITEMS["flashlight"]), "enabled": True, "remaining_power": 1800, "started_at": 100}
        before = deepcopy(state)
        projected = project_power(state, 160)
        self.assertEqual(projected["remaining_power"], 1740)
        self.assertEqual(state, before)
        exhausted = project_power(state, 2000)
        self.assertEqual((exhausted["remaining_power"], exhausted["enabled"], exhausted["started_at"]), (0, False, None))
        self.assertEqual(project_power(state, 90)["remaining_power"], 1800)

    def test_default_and_invalid_state(self):
        default = default_state(ITEMS["flashlight"])
        self.assertEqual(state_errors(ITEMS["flashlight"], default), [])
        for value in (-1, 1801, True, float("inf"), "1800"):
            self.assertTrue(state_errors(ITEMS["flashlight"], {**default, "remaining_power": value}))
