from copy import deepcopy
from random import Random
from unittest.mock import Mock, patch

from evennia import create_object
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from typeclasses.loot import Corpse, DroppedLoot, room_loot, take_loot
from typeclasses.parties import invite, respond
from world.multiplayer import object_by_id, world_change
from world.rules import RuleError

from tests.base import WorldCommandTest


class LootTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        for player in (self.char1, self.char2):
            player.location = self.rooms["grass"]
            player.push_state = Mock()
            self.connect_character(player)
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))
        self.enemy = room_enemies(self.rooms["grass"])[0]

    def kill(self, party=False):
        if party:
            group = invite(self.char1, self.char2)
            respond(self.char2, True)
            self.enemy.engage(self.char2, now=100)
            self.enemy.receive_attack(self.char2, now=102.5, rng=Random(1))
        else:
            group = None
        self.enemy.engage(self.char1, now=100)
        self.enemy.db.hp = 1
        rng = Mock()
        rng.randint.return_value = 1
        rng.random.return_value = 0
        self.enemy.receive_attack(self.char1, now=102.5, rng=rng)
        return room_loot(self.rooms["grass"])[0], group, rng

    def test_once_only_death_rng_rewards_and_corpse_visibility(self):
        corpse, _, rng = self.kill()
        self.enemy.receive_attack(self.char1, now=102.5, rng=rng)
        self.enemy.finish_death(self.char1, now=102.5, rng=rng)
        self.assertEqual(Corpse.objects.count(), 1)
        self.assertEqual(rng.random.call_count, 3)
        self.assertEqual(self.char1.profile()["xp"], 22)
        self.assertNotIn("water", self.char1.profile()["inventory"])
        with patch("world.lifecycle.time", return_value=103):
            self.assertIn(corpse.key, self.rooms["grass"].return_appearance(self.char1, observed_at=103))
        self.assertEqual(room_enemies(self.rooms["grass"]), [])
        with self.assertRaises(RuleError):
            self.enemy.engage(self.char2, now=103)

    def test_specific_then_all_and_outsider_blocked(self):
        corpse, _, _ = self.kill()
        with self.assertRaises(RuleError):
            take_loot(self.char2, corpse=True, now=103)
        take_loot(self.char1, "water", corpse=True, now=103)
        self.assertEqual(self.char1.profile()["inventory"]["water"], 1)
        self.assertEqual(len(corpse.db.entries), 2)
        take_loot(self.char1, corpse=True, now=104)
        self.assertEqual(self.char1.profile()["inventory"]["security_goggles"], 1)
        with self.assertRaises(RuleError):
            take_loot(self.char1, corpse=True, now=104)

    def test_party_round_robin_delivers_to_assignees(self):
        corpse, party, _ = self.kill(party=True)
        self.assertEqual(
            [entry["assigned_player"] for entry in corpse.db.entries if entry["kind"] == "item"],
            [self.char1.id, self.char2.id],
        )
        take_loot(self.char2, corpse=True, now=103)
        self.assertEqual(self.char1.profile()["inventory"]["water"], 1)
        self.assertEqual(self.char2.profile()["inventory"]["security_goggles"], 1)
        self.assertNotIn("water", self.char2.profile()["inventory"])
        self.assertEqual(party.state()["round_robin_cursor"], 2)

    def test_decay_preserves_reservation_respawn_preserves_ground_and_ffa(self):
        corpse, _, _ = self.kill()
        entries = list(corpse.db.entries)
        corpse.reconcile(now=132.5)
        corpse.reconcile(now=133)
        self.assertEqual(Corpse.objects.count(), 0)
        self.assertEqual(DroppedLoot.objects.count(), 3)
        self.assertEqual(
            [dict(obj.db.entries[0]) for obj in room_loot(self.rooms["grass"], False)], entries
        )
        with self.assertRaises(RuleError):
            take_loot(self.char2, corpse=False, now=133)
        self.enemy.reconcile(now=147.5)
        self.enemy.reconcile(now=148)
        self.assertEqual(self.enemy.db.state, "alive")
        self.assertEqual(DroppedLoot.objects.count(), 3)
        take_loot(self.char2, "water", corpse=False, now=222.5)
        self.assertEqual(self.char2.profile()["inventory"]["water"], 1)
        take_loot(self.char2, corpse=False, now=223)
        self.assertEqual(self.char2.profile()["inventory"]["security_goggles"], 1)
        self.assertEqual(DroppedLoot.objects.count(), 0)

    def test_ground_owner_can_collect_before_expiry(self):
        corpse, _, _ = self.kill()
        corpse.reconcile(now=133)
        take_loot(self.char1, "water", corpse=False, now=134)
        self.assertEqual(self.char1.profile()["inventory"]["water"], 1)

    def test_raw_item_names_ignore_spaces(self):
        self.kill()
        with (
            patch("typeclasses.loot.time", return_value=103),
            patch("world.lifecycle.time", return_value=103),
        ):
            self.char1.execute_cmd("시체에서 정제 수 가져")
        self.assertEqual(self.char1.profile()["inventory"]["water"], 1)

    def test_death_failure_rolls_back_hp_rewards_and_corpse(self):
        self.enemy.engage(self.char1, now=100)
        self.enemy.db.hp = 1
        with patch("typeclasses.loot.build_entries", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                self.enemy.receive_attack(self.char1, now=102.5, rng=Random(1))
        self.assertEqual(object_by_id(self.enemy.id).db.state, "alive")
        self.assertEqual(self.enemy.db.hp, 1)
        self.assertEqual(self.char1.profile()["xp"], 0)
        self.assertEqual(Corpse.objects.count(), 0)
        self.enemy.receive_attack(self.char1, now=102.5, rng=Random(1))
        self.assertEqual(Corpse.objects.count(), 1)
        self.assertEqual(self.char1.profile()["xp"], 22)

    def test_public_groups_receive_separate_item_rights(self):
        boss = room_enemies(self.rooms["ridge"])[0]
        for player in (self.char1, self.char2):
            player.location = self.rooms["ridge"]
            boss.engage(player, now=100)
        boss.db.contribution = {
            player.id: {"damage": 10, "last_action_at": 102, "group": f"player:{player.id}"}
            for player in (self.char1, self.char2)
        }
        boss.db.hp = 0
        boss.finish_death(self.char1, now=102, rng=Random(1))
        corpse = room_loot(self.rooms["ridge"])[0]
        self.assertEqual(
            {entry["assigned_player"] for entry in corpse.db.entries if entry["kind"] == "item"},
            {self.char2.id},  # trophy 한 entry는 한 allocation unit이다.
        )
        self.assertEqual({entry["reserved_player"] for entry in corpse.db.entries if entry["kind"] == "currency"},
                         {self.char1.id, self.char2.id})
        take_loot(self.char1, corpse=True, now=103)
        self.assertEqual(len(corpse.db.entries), 2)
        take_loot(self.char2, corpse=True, now=103)
        self.assertEqual(len(corpse.db.entries), 0)

    def test_party_delivery_failure_preserves_all_items_and_inventories(self):
        corpse, _, _ = self.kill(party=True)
        original = [dict(entry) for entry in corpse.db.entries]
        inventories = [player.profile()["inventory"] for player in (self.char1, self.char2)]
        with patch.object(self.char2, "save_profile", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                take_loot(self.char1, corpse=True, now=103)
        self.assertEqual([dict(entry) for entry in corpse.db.entries], original)
        self.assertEqual(
            [player.profile()["inventory"] for player in (self.char1, self.char2)], inventories
        )
        take_loot(self.char1, corpse=True, now=104)
        self.assertEqual(self.char1.profile()["inventory"]["water"], 1)
        self.assertEqual(self.char2.profile()["inventory"]["security_goggles"], 1)

    def test_decay_failure_restores_corpse_and_retry_does_not_duplicate_ground(self):
        corpse, _, _ = self.kill()
        identity = corpse.id
        original_delete = corpse.delete

        def fail_after_delete():
            original_delete()
            raise RuntimeError("injected")

        with patch.object(corpse, "delete", side_effect=fail_after_delete):
            with self.assertRaises(RuntimeError):
                corpse.reconcile(now=133)
        self.assertEqual(corpse.id, identity)
        self.assertIn(corpse, room_loot(self.rooms["grass"]))
        self.assertEqual(DroppedLoot.objects.count(), 0)
        corpse.reconcile(now=134)
        corpse.reconcile(now=135)
        self.assertEqual(Corpse.objects.count(), 0)
        self.assertEqual(DroppedLoot.objects.count(), 3)


class LootNotificationTests(WorldCommandTest):
    """Legacy 실제 수령의 최상위 커밋과 외부 전송 경계."""

    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        for path in ("typeclasses.explorers.time", "typeclasses.loot.time", "world.lifecycle.time"):
            self.enterContext(patch(path, return_value=100))
        for module in ("explorers", "loot", "enemies"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))
        for player in (self.char1, self.char2):
            player.location = self.world_rooms()["grass"]
            self.connect_character(player)
        self.party = invite(self.char1, self.char2, now=100)
        respond(self.char2, True, now=100)
        self.source = create_object(Corpse, key="알림 경계 시체", location=self.char1.location)
        self.source.db.decay_at = 1000
        self.source.db.entries = [
            {"kind": "item", "id": "bandage", "quantity": 2, "assigned_player": self.char1.pk,
             "reserved_party": self.party.pk, "protection_until": 300},
            {"kind": "item", "id": "water", "quantity": 1, "assigned_player": self.char2.pk,
             "reserved_party": self.party.pk, "protection_until": 300},
            {"kind": "currency", "id": "credits", "quantity": 20, "reserved_party": self.party.pk,
             "eligible_players": [self.char1.pk, self.char2.pk],
             "remaining_shares": {self.char1.pk: 6, self.char2.pk: 14}, "protection_until": 300},
        ]
        self.events = []
        for player in (self.char1, self.char2):
            self.enterContext(patch.object(player, "msg", side_effect=lambda message, player=player:
                                          self.events.append((player.pk, "msg", message))))
            self.enterContext(patch.object(player, "push_state", side_effect=lambda player=player:
                                          self.events.append((player.pk, "state", self.snapshot()))))

    def snapshot(self):
        return deepcopy((list(self.source.db.entries), self.char1.profile(), self.char2.profile()))

    def take(self, target="모두"):
        from world.targets import parse_loot
        return take_loot(self.char1, now=100, request=parse_loot("시체에서 " + target))

    def outer_rollback(self, target):
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "outer rollback"):
            with world_change():
                received = self.take(target)
                self.assertTrue(received)
                pending_events = list(self.events)
                raise RuntimeError("outer rollback")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(pending_events, [])
        self.assertEqual(self.events, [])

    def test_test01_legacy_item_outer_rollback_has_no_success_effects(self):
        self.outer_rollback("붕대 모두")

    def test_test02_legacy_currency_outer_rollback_has_no_recipient_effects(self):
        self.outer_rollback("보급칩 모두")

    def assert_success(self, received, before):
        from world import text as ft
        from world.content import ITEMS
        self.assertEqual(received, [(self.char1, "bandage", 2), (self.char2, "water", 1),
                                    (self.char1, "credits", 6), (self.char2, "credits", 14)])
        self.assertEqual(list(self.source.db.entries), [])
        after = self.snapshot()
        for index, amount in ((1, 6), (2, 14)):
            self.assertEqual(after[index]["credits"], before[index]["credits"] + amount)
        self.assertEqual(after[1]["inventory"].get("bandage", 0), before[1]["inventory"].get("bandage", 0) + 2)
        self.assertEqual(after[2]["inventory"].get("water", 0), before[2]["inventory"].get("water", 0) + 1)
        messages = [row for row in self.events if row[1] == "msg"]
        self.assertEqual([row[0] for row in messages], [self.char1.pk] * 4 + [self.char2.pk] * 2)
        self.assertEqual(str(messages[0][2]), f"시체를 뒤져 {ITEMS['bandage']['name']} 두 개를 챙겼다.")
        self.assertEqual(str(messages[1][2]), "시체에서 20칩을 회수했다.")
        self.assertEqual(str(messages[2][2]), f"{self.char1.key} 6칩 · {self.char2.key} 14칩")
        self.assertEqual(messages[3][2], messages[4][2])
        self.assertEqual(str(messages[5][2]), "전리품 분배로 14칩을 받았다.")
        self.assertTrue(all(isinstance(row[2], ft.Text) and row[2].kind == "event" for row in messages))
        self.assertEqual([row[1] for row in self.events],
                         ["state"] * 4 + ["msg"] * 5 + ["state", "msg"] + ["state"] * 3)
        states = [row for row in self.events if row[1] == "state"]
        self.assertEqual(len(states), 8)  # 기존 profile 저장 4회 + 수령인별 2회 + 방 구성원별 2회
        self.assertTrue(all(row[2] == after for row in states))

    def test_test04_standalone_preserves_returns_messages_and_committed_state(self):
        before = self.snapshot()
        received = self.take()
        self.assert_success(received, before)
        with self.assertRaises(RuleError):
            self.take()
        self.assertEqual(len(self.events), 14)

    def test_test05_test07_nested_multiple_awards_keep_order_and_frozen_results(self):
        before = self.snapshot()
        with world_change():
            received = self.take()
            original = list(received)
            self.assertEqual(self.events, [])
            received.clear()  # 반환 목록을 호출자가 바꿔도 확정 알림에는 영향이 없어야 한다.
        self.assert_success(original, before)

    def test_test06_failed_savepoint_discards_callbacks_and_outer_can_continue(self):
        before = self.snapshot()
        with world_change():
            try:
                with world_change():
                    self.take()
                    raise RuntimeError("savepoint rollback")
            except RuntimeError:
                pass
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(self.events, [])
            received = self.take("붕대 모두")
            self.assertEqual(self.events, [])
        self.assertEqual(received, [(self.char1, "bandage", 2)])
        self.assertEqual([str(row[2]) for row in self.events if row[1] == "msg"],
                         ["시체를 뒤져 붕대 두 개를 챙겼다."])
        self.assertEqual(self.char2.profile(), before[2])
        self.assertEqual(len([row for row in self.events if row[1] == "state"]), 3)

    def test_test07_multiple_awards_outer_rollback_leaves_no_partial_success(self):
        self.outer_rollback("모두")

    def test_test08_payout_exception_restores_prior_awards_without_effects(self):
        before = self.snapshot()
        save = self.char2.save_profile

        def fail_after_save(profile):
            save(profile)
            raise RuntimeError("payout failure")

        with patch.object(self.char2, "save_profile", side_effect=fail_after_save):
            with self.assertRaisesRegex(RuntimeError, "payout failure"):
                self.take()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.events, [])

    def test_test08_quantity_failure_has_no_success_effects(self):
        before = self.snapshot()
        with self.assertRaises(RuleError):
            self.take("21 보급칩")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.events, [])

    def test_test08_invalid_shares_or_missing_recipient_preserve_data_without_effects(self):
        for shares in ({self.char1.pk: 6, self.char2.pk: 13},
                       {self.char1.pk: 6, 999999: 14}):
            with self.subTest(shares=shares):
                entry = dict(self.source.db.entries[-1])
                entry.update(eligible_players=list(shares), remaining_shares=shares)
                self.source.db.entries = [entry]
                before = self.snapshot()
                with self.assertRaises(RuleError):
                    self.take("보급칩 모두")
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.events, [])
