"""전환 전 main에서 확보한 8종·15 Spawn·고정 RNG 결과의 Golden 기준선."""

import json
from pathlib import Path
from random import Random
from unittest import TestCase

from world import rules
from world.content import ENEMIES, ROOMS, spawn_id_for


class ActorBalanceBaselineTests(TestCase):
    def test_original_content_spawns_and_fixed_rng_combat_are_preserved(self):
        baseline = json.loads((Path(__file__).parent / "fixtures" / "actor_v16_baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(ENEMIES, baseline["enemies"])
        spawns = {spawn_id_for(zone, enemy): {"room": zone, "enemy_id": enemy}
                  for zone, room in ROOMS.items() for enemy in room.get("enemies", ())}
        self.assertEqual(spawns, baseline["spawns"])
        for enemy, expected in baseline["fixed_rng_84"].items():
            with self.subTest(enemy=enemy):
                damage, outcome = rules.player_attack(rules.new_profile(), enemy, 100, 2.5, rng=Random(84))
                self.assertEqual([damage, outcome], expected["player"])
                self.assertEqual(rules.enemy_attack(rules.new_profile(), enemy, 1, 100, rng=Random(84)), expected["enemy"])
