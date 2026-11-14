from random import Random
from unittest.mock import Mock, patch

from typeclasses.explorers import Explorer
from world.rules import RuleError
from world.shared_combat import room_enemies

from tests.base import WorldCommandTest


class SharedCombatTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        super().setUp()
        self.rooms = self.world_rooms()
        for player in (self.char1, self.char2):
            player.location = self.rooms["ridge"]
            player.home = self.rooms["dock"]
            player.push_state = Mock()
            self.enterContext(patch.object(player.sessions, "count", return_value=1))
        self.enterContext(patch("world.shared_combat.delay"))
        self.enterContext(patch("typeclasses.explorers.delay"))
        self.enemy = room_enemies(self.rooms["ridge"])[0]

    def join(self):
        for player in (self.char1, self.char2):
            self.enemy.engage(player, now=100)

    def test_shared_hp_and_independent_retaliation(self):
        self.join()
        before = self.enemy.hp
        for player in (self.char1, self.char2):
            self.enemy.receive_attack(player, now=102.5, rng=Random(1))
        self.assertLess(self.enemy.hp, before + int(before * .75) - 10)
        self.assertEqual(self.enemy.max_hp, int(before * 1.75))
        self.assertEqual(self.char1.combat_snapshot()["hp"], self.char2.combat_snapshot()["hp"])
        self.assertEqual(self.char1.profile()["hp"], 60)
        self.assertEqual(self.char2.profile()["hp"], 60)
        self.enemy.enemy_tick(now=102.5, rng=Random(1))
        self.assertEqual(self.enemy.db.enemy_round, 1)
        hp = (self.char1.profile()["hp"], self.char2.profile()["hp"])
        self.enemy.enemy_tick(now=102.5)
        self.assertEqual(hp, (self.char1.profile()["hp"], self.char2.profile()["hp"]))

    def test_reserved_tick_is_recovered_without_replacing_pending_operation(self):
        self.enemy.engage(self.char1, now=100)
        generation = self.enemy.db.combat_generation
        pending = dict(self.enemy.db.encounter_state["pending"])
        self.enemy.stop_combat_timer()
        with patch("world.shared_combat.delay") as timer, patch("world.shared_combat.time", return_value=102.5):
            from world.lifecycle import reconcile_world

            reconcile_world(now=102.5)
            timer.assert_called_once_with(0.05, self.enemy.combat_tick, generation, pending["due_at"])
            self.assertEqual(dict(self.enemy.db.encounter_state["pending"]), pending)
            self.enemy.combat_tick(generation, pending["due_at"])
            self.enemy.combat_tick(generation, pending["due_at"])

        self.assertEqual(self.enemy.db.enemy_round, 1)
        state = self.enemy.db.encounter_state
        self.assertEqual(tuple(state["completed_operations"]), (pending["operation_id"],))
        self.assertEqual(state["pending"]["due_at"], 105)

    def test_state_delivery_failure_preserves_following_recipient_and_next_tick(self):
        self.join()
        due_at = self.enemy.db.next_attack_at
        generation = self.enemy.db.combat_generation
        self.char1.push_state.side_effect = RuntimeError("전달 오류")
        self.char2.push_state.reset_mock()
        with (patch("world.multiplayer.logger.log_err") as log,
              patch("world.shared_combat.delay") as timer,
              patch("world.shared_combat.time", return_value=due_at)):
            self.enemy.combat_tick(generation, due_at)
        pending = self.enemy.db.encounter_state["pending"]
        self.assertEqual(self.enemy.db.enemy_round, 1)
        self.assertEqual(pending["due_at"], due_at + 2.5)
        timer.assert_called_once_with(2.5, self.enemy.combat_tick, generation, due_at + 2.5)
        self.char2.push_state.assert_called()
        log.assert_called()

    def test_stale_combat_callback_preserves_current_timer(self):
        self.enemy.engage(self.char1, now=100)
        generation = self.enemy.db.combat_generation
        deadline = self.enemy.db.next_attack_at
        self.char1.leave_combat(now=101)
        self.enemy.engage(self.char1, now=103)
        task = self.enemy.ndb.combat_task
        self.assertGreater(self.enemy.db.combat_generation, generation)
        with patch.object(self.enemy, "enemy_tick") as tick:
            self.enemy.combat_tick(generation, deadline)
            self.enemy.combat_tick(self.enemy.db.combat_generation, deadline)
        tick.assert_not_called()
        self.assertIs(self.enemy.ndb.combat_task, task)

    def test_disabled_combat_capability_refuses_engagement(self):
        self.enemy.set_capability_active("combat", False)
        with self.assertRaisesRegex(RuleError, "참가할 수 없습니다"):
            self.enemy.engage(self.char1, now=100)
        self.assertFalse(self.enemy.db.combatants)
        self.assertIsNone(self.enemy.db.encounter_state)
        self.assertIsNone(self.char1.profile()["combat_target"])

    def test_reconcile_releases_players_when_combat_capability_is_disabled(self):
        self.enemy.engage(self.char1, now=100)
        self.enemy.set_capability_active("combat", False)
        self.enemy.reconcile(now=101)
        self.assertFalse(self.enemy.db.combatants)
        self.assertTrue(self.enemy.db.encounter_state["settled"])
        self.assertIsNone(self.enemy.db.encounter_state["pending"])
        self.assertIsNone(self.char1.profile()["combat_target"])

    def test_stale_lifecycle_callback_does_not_clear_current_reservation(self):
        self.enemy.engage(self.char1, now=100)
        old_generation = self.enemy.db.combat_generation
        self.char1.leave_combat(now=101)
        self.enemy.engage(self.char1, now=102)
        deadline = 105
        reservation = (self.enemy.db.combat_generation, deadline)
        task = Mock()
        self.enemy.ndb.lifecycle_task = task
        self.enemy.ndb.lifecycle_reservation = reservation
        with patch.object(self.enemy, "reconcile") as reconcile:
            self.enemy.lifecycle_tick(old_generation, deadline)
        reconcile.assert_not_called()
        self.assertEqual(self.enemy.ndb.lifecycle_reservation, reservation)
        self.assertIs(self.enemy.ndb.lifecycle_task, task)

    def test_enemy_timer_unique_threat_and_shared_boss_round(self):
        with patch("world.shared_combat.delay") as timer:
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

    def test_flee_disconnect_and_idle_recovery(self):
        self.join()
        self.enemy.receive_attack(self.char1, now=102.5, rng=Random(1))
        damaged = self.enemy.hp
        self.char1.leave_combat(now=103)
        self.assertNotIn(self.char1.id, self.enemy.db.combatants)
        self.assertNotIn(self.char1.id, self.enemy.db.threat)
        self.char2.location = self.rooms["dock"]
        self.enemy.reconcile(now=118)
        self.assertIsNone(self.char2.profile()["combat_target"])
        self.assertEqual(self.enemy.hp, damaged)
        self.enemy.reconcile(now=140)
        self.assertGreater(self.enemy.hp, damaged)
        self.assertLess(self.enemy.hp, self.enemy.max_hp)

    def test_legacy_profile_migration_preserves_personal_progress(self):
        profile = self.char1.profile()
        profile.update(
            version=1,
            encounter={"enemy": "alpha", "hp": 12},
            xp=333,
            credits=111,
            generator_fixed=True,
        )
        profile.pop("quests")
        profile.pop("discoveries")
        self.char1.db.profile = profile
        converted = self.char1.profile()
        self.assertNotIn("encounter", converted)
        self.assertEqual(
            (converted["xp"], converted["credits"], converted["quests"]["radio_tower"]["generator_fixed"]), (333, 111, True)
        )
        self.assertIsNone(converted["combat_target"])

    def test_prepared_solo_shared_boss_and_quest_completion(self):
        from typeclasses.loot import take_loot
        from world import rules

        profile = self.char1.profile()
        profile["quests"]["radio_tower"].update(started=True, record_read=True)
        rules.gain_xp(profile, rules.xp_threshold(4))
        for attribute in ("strength", "constitution"):
            for _ in range(4):
                rules.allocate_attribute(profile, attribute, safe=True)
        profile["skills"].update(attack=4, shooting=4, defense=4, suppress=4)
        profile["inventory"]["bandage"] = 8
        rules.treat(profile, safe=True)
        rules.add_item(profile, "generator_repair_part", 3)
        for item in ("guard_carbine", "reinforced_vest"):
            rules.add_item(profile, item)
            slot = rules.ITEMS[item]["slot"]
            rules.unequip(profile, profile["equipment"][slot], slot)
            rules.equip(profile, item)
        for slot, item in (("head", "security_goggles"), ("legs", "reinforced_explorer_pants"), ("feet", "non_slip_boots"), ("ring", "protection_ring")):
            rules.add_item(profile, item)
            profile["equipment"][slot] = item
        rules.treat(profile, safe=True)
        rules.fix_generator(profile)
        self.char1.save_profile(profile)
        self.enemy.engage(self.char1, now=100)
        rng = Random(9)
        for turn in range(1, 51):
            if self.enemy.db.state != "alive":
                break
            now = 100 + turn * 2.5
            profile = self.char1.profile()
            if self.enemy.db.enemy_round % 3 == 2 and profile["mental"] >= 6 and now >= profile["skill_ready_at"].get("suppress", 0):
                rules.queue_action(profile, "suppress", now)
            elif profile["hp"] < 65 and profile["inventory"].get("bandage"):
                rules.queue_action(profile, "bandage", now)
            elif now >= profile["skill_ready_at"].get("shooting", 0) and profile["mental"] >= 6:
                rules.queue_action(profile, "shooting", now)
            self.char1.save_profile(profile)
            self.enemy.receive_attack(self.char1, now=now, rng=rng)
            self.enemy.enemy_tick(now=now, rng=rng)
        self.assertTrue(self.char1.profile()["quests"]["radio_tower"]["boss_defeated"])
        self.assertEqual(self.enemy.db.state, "respawning")
        take_loot(self.char1, corpse=True, now=now)
        self.assertEqual(self.char1.profile()["inventory"]["fang"], 1)
        self.char1.change(rules.claim_quest)
        self.assertTrue(self.char1.profile()["quests"]["radio_tower"]["claimed"])
        with self.assertRaises(rules.RuleError):
            self.char1.change(rules.claim_quest)

    def test_missing_target_stops_player_timer_on_next_tick(self):
        self.char1.change(lambda profile: profile.update(combat_target=999999))
        with patch("typeclasses.explorers.delay") as timer:
            self.char1.schedule_combat()
            callback, *reservation = timer.call_args.args[1:]
            callback(*reservation)
        self.assertIsNone(self.char1.profile()["combat_target"])
        timer.assert_called_once()

    def test_previous_player_timer_does_not_consume_current_reservation(self):
        self.enemy.engage(self.char1, now=100)
        first_reservation = self.char1.ndb.combat_reservation
        self.char1.leave_combat(now=101)
        self.enemy.engage(self.char1, now=103)
        current_reservation = self.char1.ndb.combat_reservation
        current_task = self.char1.ndb.combat_task
        self.assertNotEqual(first_reservation, current_reservation)
        with patch.object(self.char1, "resolve_combat_round") as resolve:
            self.char1.combat_tick(*first_reservation)
        resolve.assert_not_called()
        self.assertEqual(self.char1.ndb.combat_reservation, current_reservation)
        self.assertIs(self.char1.ndb.combat_task, current_task)
