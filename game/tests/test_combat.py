from random import Random
from unittest.mock import Mock, patch

from evennia.utils.test_resources import EvenniaCommandTest
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from world.bootstrap import build_world


class SharedCombatTests(EvenniaCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = build_world()
        for player in (self.char1, self.char2):
            player.location = self.rooms["ridge"]
            player.home = self.rooms["dock"]
            player.push_state = Mock()
            self.enterContext(patch.object(player.sessions, "count", return_value=1))
        self.enterContext(patch("typeclasses.enemies.delay"))
        self.enterContext(patch("typeclasses.explorers.delay"))
        self.enemy = room_enemies(self.rooms["ridge"])[0]

    def join(self):
        for player in (self.char1, self.char2):
            self.enemy.engage(player, now=100)

    def test_shared_hp_and_independent_retaliation(self):
        self.join()
        before = self.enemy.db.hp
        for player in (self.char1, self.char2):
            self.enemy.receive_attack(player, now=102.5, rng=Random(1))
        self.assertLess(self.enemy.db.hp, before - 10)
        self.assertEqual(self.char1.combat_snapshot()["hp"], self.char2.combat_snapshot()["hp"])
        self.assertEqual(self.char1.profile()["hp"], 60)
        self.assertEqual(self.char2.profile()["hp"], 60)
        self.enemy.enemy_tick(now=102.5, rng=Random(1))
        self.assertEqual(self.enemy.db.enemy_round, 1)
        hp = (self.char1.profile()["hp"], self.char2.profile()["hp"])
        self.enemy.enemy_tick(now=102.5)
        self.assertEqual(hp, (self.char1.profile()["hp"], self.char2.profile()["hp"]))

    def test_enemy_timer_unique_threat_and_shared_boss_round(self):
        with patch("typeclasses.enemies.delay") as timer:
            self.join()
            for _ in range(5):
                self.enemy.engage(self.char1, now=101)
            self.assertEqual(timer.call_count, 1)
        self.enemy.db.threat = {self.char1.id: 1, self.char2.id: 100}
        self.enemy.enemy_tick(now=102.5, rng=Random(1))
        self.assertEqual(self.char1.profile()["hp"], 60)
        self.assertLess(self.char2.profile()["hp"], 60)
        self.enemy.enemy_tick(now=105, rng=Random(1))
        self.assertTrue(self.char1.combat_snapshot()["telegraph"])
        self.assertTrue(self.char2.combat_snapshot()["telegraph"])

    def test_flee_disconnect_and_idle_reset(self):
        self.join()
        self.enemy.receive_attack(self.char1, now=102.5, rng=Random(1))
        self.char1.leave_combat()
        self.assertNotIn(self.char1.id, self.enemy.db.combatants)
        self.assertNotIn(self.char1.id, self.enemy.db.threat)
        self.char2.location = self.rooms["dock"]
        self.enemy.reconcile(now=118)
        self.assertIsNone(self.char2.profile()["combat_target"])
        self.assertEqual(self.enemy.db.hp, self.enemy.db.max_hp)

    def test_legacy_profile_migration_preserves_personal_progress(self):
        profile = self.char1.profile()
        profile.update(
            version=1,
            encounter={"enemy": "alpha", "hp": 12},
            xp=333,
            credits=111,
            generator_fixed=True,
        )
        self.char1.db.profile = profile
        converted = self.char1.profile()
        self.assertNotIn("encounter", converted)
        self.assertEqual(
            (converted["xp"], converted["credits"], converted["generator_fixed"]), (333, 111, True)
        )
        self.assertIsNone(converted["combat_target"])

    def test_prepared_solo_shared_boss_and_quest_completion(self):
        from typeclasses.loot import take_loot
        from world import rules

        profile = self.char1.profile()
        profile.update(quest_started=True, record_read=True)
        rules.gain_xp(profile, rules.xp_threshold(4))
        rules.add_item(profile, "scrap", 3)
        for item in ("carbine", "armor"):
            rules.add_item(profile, item)
            rules.equip(profile, item)
        rules.fix_generator(profile)
        self.char1.save_profile(profile)
        self.enemy.engage(self.char1, now=100)
        rng = Random(9)
        for turn in range(1, 51):
            if self.enemy.db.state != "alive":
                break
            now = 100 + turn * 2.5
            profile = self.char1.profile()
            if self.enemy.db.enemy_round % 3 == 2:
                rules.queue_action(profile, "guard", now)
            elif profile["hp"] < 45 and profile["inventory"].get("bandage"):
                rules.queue_action(profile, "heal", now)
            elif now >= profile["heavy_ready_at"]:
                rules.queue_action(profile, "heavy", now)
            self.char1.save_profile(profile)
            self.enemy.receive_attack(self.char1, now=now, rng=rng)
            self.enemy.enemy_tick(now=now, rng=rng)
        self.assertTrue(self.char1.profile()["boss_defeated"])
        self.assertEqual(self.enemy.db.state, "respawning")
        take_loot(self.char1, corpse=True, now=now)
        self.assertEqual(self.char1.profile()["inventory"]["fang"], 1)
        self.char1.change(rules.claim_quest)
        self.assertTrue(self.char1.profile()["quest_claimed"])
        with self.assertRaises(rules.RuleError):
            self.char1.change(rules.claim_quest)

    def test_missing_target_stops_player_timer_on_next_tick(self):
        self.char1.change(lambda profile: profile.update(combat_target=999999))
        with patch("typeclasses.explorers.delay") as timer:
            self.char1.combat_tick()
        self.assertIsNone(self.char1.profile()["combat_target"])
        timer.assert_not_called()
