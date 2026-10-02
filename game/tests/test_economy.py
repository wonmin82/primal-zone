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
                "shares": shares or {}, "protection_until": deadline}

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
        self.assertEqual((entry["quantity"], dict(entry["shares"])), (8, {self.char1.id: 8}))
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
        self.assertEqual(dict(corpse.db.entries[0]["shares"]), {self.char1.id: 6, self.char2.id: 5})
        party.remove_member(third)
        party.remove_member(self.char2)
        corpse.reconcile(130)
        ground = room_loot(self.char1.location, False)[0]
        self.assertEqual((ground.db.entries[0]["quantity"], ground.db.entries[0]["protection_until"]), (11, 220))
        self.assertEqual(dict(ground.db.entries[0]["shares"]), {self.char1.id: 6, self.char2.id: 5})
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
        self.char1.change(lambda p: p["inventory"].update(blade=2))
        self.command("강철마체테 무장")
        self.assertIn("60칩", self.command("무기상에게 강철마체테 가치"))
        self.assertIn("30칩", self.command("강철마체테 value"))
        actions = multiplayer_state(self.char1)["interactables"][0]["actions"]
        command = next(a["command"] for a in actions if a["command"].endswith("모두 판매"))
        self.assertIn("30칩", self.command(command))
        self.assertEqual((self.char1.profile()["credits"], self.char1.profile()["inventory"]["blade"]), (50, 1))
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
