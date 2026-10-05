"""실제 dispatcher·DB·공유 시체를 통한 화폐 보존과 실패 원자성."""

from copy import deepcopy
from random import Random
from unittest.mock import Mock, patch

from evennia import create_object, search_tag
from evennia.utils.dbserialize import deserialize
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from typeclasses.loot import Corpse, create_dropped_loot, room_loot, take_loot
from typeclasses.parties import invite, respond
from world import rules
from world.currency import currency_names
from world.item_transfers import transfer_currency
from world.state import loot_entries, multiplayer_state
from world.targets import parse_loot

from tests.base import WorldCommandTest


class EconomyTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        for player in (self.char1, self.char2):
            player.location = self.rooms["storage_room"]
            player.push_state = Mock()
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))

    def command(self, raw, caller=None):
        caller = caller or self.char1
        with patch.object(caller, "msg") as msg:
            caller.execute_cmd(raw)
        return str(msg.call_args_list)

    def take(self, raw, caller=None, now=103):
        return take_loot(caller or self.char1, request=parse_loot(raw, currency_names()), now=now)

    def currency_entry(self, quantity, shares=None, deadline=0):
        return {"kind": "currency", "id": "credits", "quantity": quantity,
                "eligible_players": sorted(shares or {}), "remaining_shares": shares or {}, "protection_until": deadline}

    def test_give_drop_and_indexed_ground_take_conserve_wallets(self):
        self.command(f"{self.char2.key}에게 칩 줘")
        self.assertEqual([p.profile()["credits"] for p in (self.char1, self.char2)], [19, 21])
        self.command(f"{self.char2.key}에게 칩 모두 줘")
        self.assertEqual([p.profile()["credits"] for p in (self.char1, self.char2)], [0, 40])
        self.command("20칩 버려", self.char2)
        self.command("칩 모두 버려", self.char2)
        ground = room_loot(self.char1.location, False)
        self.assertEqual([obj.db.entries[0]["quantity"] for obj in ground], [20, 20])
        self.command("칩 2 가져")
        self.assertEqual([obj.db.entries[0]["quantity"] for obj in ground], [20, 19])
        self.command("10칩 가져")
        self.assertEqual(self.char1.profile()["credits"], 11)
        self.command("칩 모두 가져")
        self.assertEqual(self.char1.profile()["credits"], 40)
        self.assertEqual(room_loot(self.char1.location, False), [])

    def test_bad_amounts_and_recipients_leave_state_unchanged(self):
        # 실패 원자성의 전체 profile 비교가 실제 자연회복 경계를 지나지 않도록 고정한다.
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        original = [p.profile() for p in (self.char1, self.char2)]
        for raw in ("0칩 버려", "-1칩 버려", "1.5칩 버려", "21칩 버려",
                    f"{self.char1.key}에게 칩 줘", "정산관에게 칩 줘"):
            self.command(raw)
            self.assertEqual([p.profile() for p in (self.char1, self.char2)], original)
            self.assertEqual(room_loot(self.char1.location, False), [])
        for invalid in ("remote", "hidden", "combat"):
            with self.subTest(invalid=invalid):
                if invalid == "remote":
                    self.char2.location = self.rooms["dock"]
                elif invalid == "hidden":
                    self.char2.locks.add("view:false()")
                else:
                    self.char2.change(lambda p: p.update(combat_target=999))
                before = [p.profile() for p in (self.char1, self.char2)]
                with self.assertRaises(rules.RuleError):
                    transfer_currency(self.char1, 1, self.char2)
                self.assertEqual([p.profile() for p in (self.char1, self.char2)], before)
                self.char2.location = self.char1.location
                self.char2.locks.add("view:all()")

    def test_transfer_and_drop_failure_roll_back_wallet_and_world(self):
        before = [p.profile() for p in (self.char1, self.char2)]
        with patch.object(self.char2, "save_profile", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                transfer_currency(self.char1, 10, self.char2)
        self.assertEqual([p.profile() for p in (self.char1, self.char2)], before)
        with patch("typeclasses.loot.create_dropped_loot", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                transfer_currency(self.char1, 10)
        self.assertEqual(self.char1.profile(), before[0])
        self.assertEqual(room_loot(self.char1.location, False), [])

    def test_solo_kill_defers_currency_until_corpse_take(self):
        self.char1.location = self.rooms["grass"]
        self.enterContext(patch.object(self.char1.sessions, "count", return_value=1))
        enemy = room_enemies(self.char1.location)[0]
        enemy.engage(self.char1, now=100)
        enemy.db.hp = 1
        enemy.receive_attack(self.char1, now=102.5, rng=Random(1))
        self.assertEqual((self.char1.profile()["credits"], self.char1.profile()["xp"], self.char1.profile()["kills"]), (20, 22, 1))
        corpse = room_loot(self.char1.location)[0]
        entry = next(e for e in corpse.db.entries if e["kind"] == "currency")
        self.assertEqual((entry["quantity"], dict(entry["remaining_shares"])), (8, {self.char1.id: 8}))
        self.take("시체에서 칩 모두")
        self.assertEqual(self.char1.profile()["credits"], 28)

    def test_party_partial_snapshot_survives_membership_and_decay(self):
        self.enterContext(patch("world.lifecycle.time", return_value=103))
        third = create_object(Explorer, key="새참여자", location=self.char1.location)
        third.push_state = Mock()
        party = invite(self.char1, self.char2)
        respond(self.char2, True)
        corpse = create_object(Corpse, key="공유 시체", location=self.char1.location)
        corpse.db.decay_at = 130
        corpse.db.entries = [self.currency_entry(21, {self.char1.id: 11, self.char2.id: 10}, 220)]
        party.transfer(self.char1, self.char2)
        party.remove_member(self.char1)
        invite(self.char2, third)
        respond(third, True)
        self.assertIn(corpse, room_loot(self.char1.location))
        with self.assertRaises(rules.RuleError):
            self.take("시체에서 칩 모두", third)
        self.assertIn(corpse, room_loot(self.char1.location))
        self.take("시체에서 10칩")
        self.assertEqual([p.profile()["credits"] for p in (self.char1, self.char2)], [25, 25])
        self.assertEqual(dict(corpse.db.entries[0]["remaining_shares"]), {self.char1.id: 6, self.char2.id: 5})
        self.assertEqual(list(corpse.db.entries[0]["eligible_players"]), [self.char1.id, self.char2.id])
        party.remove_member(third)
        party.remove_member(self.char2)
        corpse.reconcile(130)
        ground = room_loot(self.char1.location, False)[0]
        self.assertEqual((ground.db.entries[0]["quantity"], ground.db.entries[0]["protection_until"]), (11, 220))
        self.assertEqual(dict(ground.db.entries[0]["remaining_shares"]), {self.char1.id: 6, self.char2.id: 5})
        self.assertEqual(list(ground.db.entries[0]["eligible_players"]), [self.char1.id, self.char2.id])
        self.take("칩 모두", self.char2, now=131)
        self.assertEqual([p.profile()["credits"] for p in (self.char1, self.char2)], [31, 30])
        self.assertEqual(third.profile()["credits"], 20)

    def test_public_pools_select_accessible_entry_and_expire_to_free(self):
        corpse = create_object(Corpse, key="공용 시체", location=self.char1.location)
        corpse.db.decay_at = 300
        corpse.db.entries = [self.currency_entry(44, {self.char2.id: 44}, 220),
                             self.currency_entry(14, {self.char1.id: 14}, 220)]
        self.take("시체에서 10칩")
        self.assertEqual(self.char1.profile()["credits"], 30)
        self.assertEqual([e["quantity"] for e in corpse.db.entries], [44, 4])
        self.take("시체에서 칩 모두")
        self.assertEqual([e["quantity"] for e in corpse.db.entries], [44])
        self.take("시체에서 칩 모두", now=221)
        self.assertEqual([p.profile()["credits"] for p in (self.char1, self.char2)], [78, 20])

    def test_invalid_partial_take_and_combat_never_mutate_loot_or_wallet(self):
        dropped = create_dropped_loot(self.char1.location, [self.currency_entry(5)])
        before = deserialize(dropped.db.entries)
        for raw in ("0칩", "-1칩", "1.5칩", "6칩"):
            profile = self.char1.profile()
            with self.assertRaises(rules.RuleError):
                self.take(raw)
            self.assertEqual(self.char1.profile(), profile)
            self.assertEqual(deserialize(dropped.db.entries), before)
        self.char1.change(lambda p: p.update(combat_target=999))
        profile = self.char1.profile()
        with self.assertRaises(rules.RuleError):
            self.take("칩 모두")
        with self.assertRaises(rules.RuleError):
            transfer_currency(self.char1, 1)
        self.assertEqual(self.char1.profile(), profile)
        self.assertEqual(deserialize(dropped.db.entries), before)

    def test_multiple_sources_and_payout_failure_are_atomic(self):
        corpses = []
        for _ in range(2):
            corpse = create_object(Corpse, key="시체", location=self.char1.location)
            corpse.db.decay_at = 300
            corpse.db.entries = [self.currency_entry(21, {self.char1.id: 11, self.char2.id: 10}, 220)]
            corpses.append(corpse)
        before = [deserialize(c.db.entries) for c in corpses]
        wallets = [p.profile() for p in (self.char1, self.char2)]
        with patch.object(self.char2, "save_profile", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                self.take("모든 시체에서 칩 모두")
        self.assertEqual([deserialize(c.db.entries) for c in corpses], before)
        self.assertEqual([p.profile() for p in (self.char1, self.char2)], wallets)
        self.take("모든 시체에서 칩 모두")
        self.assertEqual([p.profile()["credits"] for p in (self.char1, self.char2)], [42, 40])

    def test_legacy_read_take_and_decay_and_web_use_common_assets(self):
        corpse = create_object(Corpse, key="옛 시체", location=self.char1.location)
        corpse.db.decay_at = 130
        corpse.db.entries = [{"item": "bandage", "quantity": 2, "protection_until": 0}]
        before = deserialize(corpse.db.entries)
        self.assertEqual(loot_entries(corpse, self.char1, 103)[0]["id"], "bandage")
        corpse.return_appearance(self.char1, observed_at=103)
        self.assertEqual(deserialize(corpse.db.entries), before)
        corpse.reconcile(130)
        self.take("붕대 모두", now=131)
        self.assertEqual(self.char1.profile()["inventory"]["bandage"], 5)
        self.command("칩 버려")
        state = multiplayer_state(self.char1)
        entry = state["ground_loot"][0]["loot"][0]
        self.assertEqual((entry["kind"], entry["amount_label"], entry["take_command"]), ("currency", "1칩", "칩 가져"))
        self.assertIn("식별 표식", self.command("보급칩 보기"))

    def test_value_sale_and_server_actions_preserve_equipped_copy(self):
        self.char1.location = self.rooms["weapon_shop"]
        self.char1.change(lambda p: p["inventory"].update(blade=3))
        self.command("강철마체테 무장")
        self.assertIn("60칩", self.command("무기상에게 강철마체테 가치"))
        self.assertIn("30칩", self.command("강철마체테 value"))
        actions = multiplayer_state(self.char1)["interactables"][0]["actions"]
        single = next(a for a in actions if a["label"] == "강철마체테 · 30칩 판매")
        self.assertTrue(single["command"].endswith("강철마체테 판매"))
        bulk = next(a for a in actions if a["label"] == "강철마체테 모두 판매 · 총 60칩")
        command = bulk["command"]
        self.assertIn("60칩", self.command(command))
        self.assertEqual((self.char1.profile()["credits"], self.char1.profile()["inventory"]["blade"]), (80, 1))
        before = self.char1.profile()
        for raw in ("강철마체테 판매", "회수부품 판매", "붕대 판매", "강철마체테 3개 판매"):
            self.command(raw)
            self.assertEqual(self.char1.profile(), before)
        seller = search_tag("weapon_shopkeeper", category="primal_interactable")[0]
        seller.locks.add("view:false()")
        self.command("강철마체테 가치")
        self.assertEqual(self.char1.profile(), before)

    def test_sale_storage_failure_rolls_back_proceeds_and_inventory(self):
        self.char1.location = self.rooms["supply_shop"]
        before = deepcopy(self.char1.profile())
        with patch.object(self.char1, "save_profile", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                self.char1.change(lambda p: rules.sell(p, "supply", "bandage", all_items=True))
        self.assertEqual(self.char1.profile(), before)

    def test_web_single_sale_and_all_sale_have_distinct_amounts(self):
        self.char1.location = self.rooms["supply_shop"]
        seller = search_tag("supply_shopkeeper", category="primal_interactable")[0]
        actions = seller.web_actions(self.char1, seller.key)
        single = next(a for a in actions if a["label"] == "붕대 · 4칩 판매")
        bulk = next(a for a in actions if a["label"] == "붕대 모두 판매 · 총 12칩")
        self.assertTrue(single["command"].endswith("붕대 판매"))
        self.assertTrue(bulk["command"].endswith("붕대 모두 판매"))
        self.command(single["command"])
        self.assertEqual((self.char1.profile()["inventory"]["bandage"], self.char1.profile()["credits"]), (2, 24))
        actions = seller.web_actions(self.char1, seller.key)
        bulk = next(a for a in actions if a["label"] == "붕대 모두 판매 · 총 8칩")
        self.command(bulk["command"])
        self.assertNotIn("bandage", self.char1.profile()["inventory"])
        self.assertEqual(self.char1.profile()["credits"], 32)

    def test_last_device_sale_via_dispatcher_cannot_restore_old_charge(self):
        self.char1.location = self.rooms["supply_shop"]
        self.char1.change(lambda p: p["inventory"].update(flashlight=2, battery=1))
        self.command("손전등에 건전지 넣어")
        device = deepcopy(self.char1.profile()["light_sources"]["flashlight"])
        self.command("탐사용손전등 판매")
        self.assertEqual(self.char1.profile()["light_sources"]["flashlight"], device)
        self.command("탐사용손전등 판매")
        self.assertNotIn("flashlight", self.char1.profile()["inventory"])
        self.assertNotIn("flashlight", self.char1.profile()["light_sources"])
        self.command("탐사용손전등 구매")
        self.assertIn("전원이 없습니다", self.command("탐사용손전등 켜"))
        self.assertNotIn("flashlight", self.char1.profile()["light_sources"])

    def test_zero_remaining_share_keeps_eligibility_and_pays_offline_recipient(self):
        players = [self.char1, self.char2]
        for name in ("참여다", "참여라", "외부마"):
            player = create_object(Explorer, key=name, location=self.char1.location)
            player.push_state = Mock()
            players.append(player)
        participants, outsider = players[:4], players[4]
        corpse = create_object(Corpse, key="공유 시체", location=self.char1.location)
        corpse.db.decay_at = 130
        corpse.db.entries = [self.currency_entry(8, {p.id: 2 for p in participants}, 220)]
        original = deserialize(corpse.db.entries)
        with self.assertRaises(rules.RuleError):
            self.take("시체에서 칩 모두", outsider)
        self.assertEqual(deserialize(corpse.db.entries), original)
        self.take("시체에서 7칩")
        entry = deserialize(corpse.db.entries)[0]
        self.assertEqual(entry["remaining_shares"], {participants[-1].id: 1})
        self.assertEqual(entry["eligible_players"], [p.id for p in participants])
        self.assertEqual([p.profile()["credits"] for p in participants], [22, 22, 22, 21])
        self.assertEqual(participants[-1].sessions.count(), 0)
        self.assertTrue(loot_entries(corpse, self.char1, 104)[0]["can_take"])
        corpse.reconcile(130)
        ground = room_loot(self.char1.location, False)[0]
        self.assertEqual(deserialize(ground.db.entries)[0], entry)
        self.take("칩 모두", now=131)
        self.assertEqual([p.profile()["credits"] for p in participants], [22, 22, 22, 22])
        self.assertEqual(room_loot(self.char1.location, False), [])

    def test_missing_currency_recipient_rolls_back_all_obligations(self):
        corpse = create_object(Corpse, key="공유 시체", location=self.char1.location)
        corpse.db.decay_at = 300
        corpse.db.entries = [self.currency_entry(3, {self.char1.id: 2, 999999: 1}, 220)]
        entry = deserialize(corpse.db.entries)
        profile = self.char1.profile()
        with self.assertRaises(rules.RuleError):
            self.take("시체에서 칩 모두")
        self.assertEqual(deserialize(corpse.db.entries), entry)
        self.assertEqual(self.char1.profile(), profile)

    def test_currency_display_and_indexed_take_target_are_independent(self):
        for amount in (8, 1):
            create_dropped_loot(self.char1.location, [self.currency_entry(amount)])
        entries = [s["loot"][0] for s in multiplayer_state(self.char1)["ground_loot"]]
        self.assertEqual([e["display_label"] for e in entries], ["8칩", "1칩"])
        self.assertEqual([e["take_target"] for e in entries], ["칩 1", "칩 2"])
        self.assertEqual([e["take_command"] for e in entries], ["칩 1 가져", "칩 2 가져"])
        self.command(entries[1]["take_command"])
        self.assertEqual(self.char1.profile()["credits"], 21)
        self.assertEqual(room_loot(self.char1.location, False)[0].db.entries[0]["quantity"], 8)

    def test_old_pr_currency_reads_without_write_and_decays_to_canonical_rights(self):
        corpse = create_object(Corpse, key="옛 화폐 시체", location=self.char1.location)
        corpse.db.decay_at = 130
        corpse.db.entries = [{"kind": "currency", "id": "credits", "quantity": 21,
                              "shares": {self.char1.id: 11, self.char2.id: 10}, "protection_until": 220}]
        before = deserialize(corpse.db.entries)
        state = loot_entries(corpse, self.char1, 103)[0]
        self.assertTrue(state["can_take"])
        self.assertEqual(state["display_label"], "21칩")
        corpse.return_appearance(self.char1, observed_at=103)
        self.assertEqual(deserialize(corpse.db.entries), before)
        corpse.reconcile(130)
        ground = room_loot(self.char1.location, False)[0]
        self.assertEqual(list(ground.db.entries[0]["eligible_players"]), [self.char1.id, self.char2.id])
        self.assertEqual(dict(ground.db.entries[0]["remaining_shares"]), {self.char1.id: 11, self.char2.id: 10})
        self.assertNotIn("shares", ground.db.entries[0])
        self.take("칩 모두", now=131)
        self.assertEqual([p.profile()["credits"] for p in (self.char1, self.char2)], [31, 30])

    def test_one_sellable_copy_has_only_single_sale_action(self):
        self.char1.location = self.rooms["supply_shop"]
        self.char1.change(lambda p: p["inventory"].update(bandage=1))
        actions = multiplayer_state(self.char1)["interactables"][0]["actions"]
        self.assertIn({"label": "붕대 · 4칩 판매", "command": "보급관에게 붕대 판매"}, actions)
        self.assertFalse(any(a["command"].endswith("붕대 모두 판매") for a in actions))
