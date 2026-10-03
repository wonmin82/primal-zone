"""실제 정산관·명령·관찰·영속 객체와 정산 후 구매 동선."""

from copy import deepcopy
from unittest.mock import Mock, patch

from evennia import create_object, search_tag
from evennia.objects.models import ObjectDB
from evennia.utils.dbserialize import deserialize
from typeclasses.explorers import Explorer
from typeclasses.interactables import INTERACTABLES, SettlementOfficer
from world import rules
from world.bootstrap import build_world, stale_definitions
from world.content import ITEMS, SALVAGE_CREDIT_RATE
from world.content.integrity import errors
from world.observation import context_for
from world.room_hints import render
from world.state import multiplayer_state

from tests.base import WorldCommandTest


class SettlementFixture:
    character_typeclass = Explorer

    def setUp(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        super().setUp()
        self.rooms = self.world_rooms()
        self.officer = search_tag("salvage_officer", category="primal_interactable")[0]
        for player in (self.char1, self.char2):
            player.location = self.rooms["salvage_office"]
            player.home = self.rooms["dock"]
            player.push_state = Mock()
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))

    def command(self, value):
        with patch.object(self.char1, "msg") as output:
            self.char1.execute_cmd(value)
        return str(output.call_args_list)

    def prepare(self, scrap=7, credits=20):
        def change(profile):
            profile.update(credits=credits, combat_target=None)
            profile["inventory"]["scrap"] = scrap
        self.char1.change(change)


class SettlementCommandsTests(SettlementFixture, WorldCommandTest):
    def test_real_parser_one_numeric_all_and_targeted_commands(self):
        for raw, quantity in (("회수부품 교환", 1), ("회수 부품 교환", 1),
                              ("회수부품 3개 교환", 3), ("회수부품 모두 교환", 7),
                              ("정산관에게 회수부품 교환", 1), ("정산관에게 회수부품 3개 교환", 3),
                              ("정산관에게 회수부품 모두 교환", 7),
                              ("자원 정산관에게 회수 부품 3개 교환", 3), ("회수부품 exchange", 1)):
            with self.subTest(command=raw):
                self.prepare()
                before = deepcopy(self.char1.profile())
                self.assertIn(f"{quantity * SALVAGE_CREDIT_RATE}칩", self.command(raw))
                before["credits"] += quantity * SALVAGE_CREDIT_RATE
                if quantity == 7:
                    del before["inventory"]["scrap"]
                else:
                    before["inventory"]["scrap"] -= quantity
                self.assertEqual(self.char1.profile(), before)
        for raw in ("환율", "정산관 환율", "자원 정산관 환율", "정산관 rate"):
            before = deepcopy(self.char1.profile())
            with patch.object(self.char1, "save_profile") as save:
                self.assertIn(f"{SALVAGE_CREDIT_RATE}칩", self.command(raw))
                save.assert_not_called()
            self.assertEqual(self.char1.profile(), before)

    def test_invalid_resource_quantity_and_removed_gear_exchange_are_atomic(self):
        self.prepare(scrap=2)
        for raw in ("회수부품 0개 교환", "회수부품 -1개 교환", "회수부품 abc개 교환",
                    "회수부품 999개 교환", "회수부품 모두 1개 교환", "붕대 교환",
                    "강철마체테 교환", "강화 조끼 교환"):
            before = deepcopy(self.char1.profile())
            self.assertNotIn("칩을 받았다", self.command(raw))
            self.assertEqual(self.char1.profile(), before)
        self.char1.change(lambda p: p["inventory"].pop("scrap", None))
        before = deepcopy(self.char1.profile())
        self.assertIn("정산할 회수부품이 없습니다", self.command("회수부품 모두 교환"))
        self.assertEqual(self.char1.profile(), before)
        self.char1.location = self.rooms["dock"]
        for raw in ("강철마체테 교환", "강화 조끼 교환", "회수부품 교환", "환율"):
            self.assertIn("정산관을 찾지", self.command(raw))
            self.assertEqual(self.char1.profile(), before)

    def test_multiple_officers_require_target_and_hidden_does_not_count(self):
        extra = create_object(SettlementOfficer, key=self.officer.key, location=self.char1.location,
                              aliases=["정산관"])
        self.prepare()
        before = deepcopy(self.char1.profile())
        for raw in ("환율", "회수부품 교환"):
            self.assertIn("정산관이 여러 명", self.command(raw))
            self.assertEqual(self.char1.profile(), before)
        with patch.object(extra, "act", wraps=extra.act) as selected, patch.object(self.officer, "act") as other:
            self.command("자원 정산관 2에게 회수부품 3개 교환")
            selected.assert_called_once()
            other.assert_not_called()
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 4)
        self.assertIn("자원 정산관 2에게 회수부품 모두 교환", str(multiplayer_state(self.char1)))
        extra.locks.add("view:false()")
        self.assertNotIn("여러 명", self.command("환율"))
        self.command("회수부품 교환")
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 3)

    def test_hidden_missing_combat_and_unsafe_services_do_not_mutate_or_leak(self):
        self.prepare()
        self.officer.locks.add("view:false()")
        before = deepcopy(self.char1.profile())
        for raw in ("환율", "회수부품 교환", "정산관 환율", "정산관에게 회수부품 교환"):
            self.assertNotIn("칩을 받았다", self.command(raw))
            self.assertEqual(self.char1.profile(), before)
        self.assertEqual(multiplayer_state(self.char1)["interactables"], [])
        self.assertEqual(render(context_for(self.char1)), "")
        self.officer.locks.add("view:all()")
        self.char1.change(lambda p: p.update(combat_target=999))
        before = deepcopy(self.char1.profile())
        for raw in ("환율", "회수부품 교환"):
            self.assertIn("전투 중입니다", self.command(raw))
            self.assertEqual(self.char1.profile(), before)
        self.assertEqual(multiplayer_state(self.char1)["interactables"][0]["actions"], [])
        self.assertEqual(render(context_for(self.char1)), "")
        self.char1.change(lambda p: p.update(combat_target=None))
        self.officer.location = self.rooms["support_roof"]
        self.assertIn("정산관을 찾지", self.command("환율"))
        self.char1.location = self.officer.location
        self.command("회수부품 교환")
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 6)
        self.officer.location = self.char1.location = self.rooms["grass"]
        before = deepcopy(self.char1.profile())
        with patch("world.observation.can_perceive", return_value=True):
            for raw in ("환율", "회수부품 교환"):
                self.assertIn("안전한 곳", self.command(raw))
                self.assertEqual(self.char1.profile(), before)
            objects = multiplayer_state(self.char1)["interactables"]
            self.assertEqual(next(obj for obj in objects if obj["name"] == self.officer.key)["actions"], [])


class SettlementWorldTests(SettlementFixture, WorldCommandTest):
    def test_server_actions_resource_snapshot_and_settlement_push(self):
        self.prepare(scrap=7, credits=0)
        actions = multiplayer_state(self.char1)["interactables"][0]["actions"]
        self.assertEqual([action["command"] for action in actions],
                         ["자원 정산관 환율", "자원 정산관에게 회수부품 모두 교환"])
        self.assertEqual(render(context_for(self.char1)), "자원 정산관 환율")
        appearance = str(self.officer.return_appearance(self.char1))
        for usage in ("환율", "10개", "모두"):
            self.assertIn(usage, appearance)
        self.char1.push_state = lambda: Explorer.push_state(self.char1)
        with patch.object(self.char1, "msg") as output:
            self.char1.execute_cmd(actions[-1]["command"])
        payloads = [call.kwargs["pz_state"][0][0] for call in output.call_args_list if "pz_state" in call.kwargs]
        self.assertTrue(payloads)
        for state in payloads:
            self.assertEqual(state["credits"], 7 * SALVAGE_CREDIT_RATE)
            self.assertEqual(state["resources"], {"scrap": {"name": "회수부품", "count": 0}})
        self.assertEqual([action["command"] for action in multiplayer_state(self.char1)["interactables"][0]["actions"]],
                         ["자원 정산관 환율"])
        self.char1.location = self.rooms["support_1f_w2"]
        self.assertNotIn("정산관", self.command("북 보기"))

    def test_bootstrap_identity_aliases_and_all_existing_data_are_preserved(self):
        self.prepare()
        self.char1.change(lambda p: p["storage"].update(scrap=8))
        self.char2.change(lambda p: p["storage"].update(scrap=3))
        profiles = [deepcopy(player.profile()) for player in (self.char1, self.char2)]
        identities = {key: search_tag(key, category="primal_interactable")[0].id for key in INTERACTABLES}
        box = search_tag("shared_container", category="primal_interactable")[0]
        box.db.items = {"scrap": 4, "bandage": 2}
        count = ObjectDB.objects.count()
        for _ in range(2):
            build_world()
            self.assertEqual(ObjectDB.objects.count(), count)
            for key, identity in identities.items():
                objs = search_tag(key, category="primal_interactable")
                self.assertEqual([obj.id for obj in objs], [identity])
                self.assertEqual(objs[0].location, self.rooms[INTERACTABLES[key]["room"]])
            self.assertEqual(self.officer.aliases.all(), ["정산관"])
            self.assertEqual([player.profile() for player in (self.char1, self.char2)], profiles)
            self.assertEqual(deserialize(box.db.items), {"scrap": 4, "bandage": 2})
        self.assertEqual(stale_definitions(), [])
        self.assertEqual(errors(INTERACTABLES), [])

    def test_scrap_settlement_credits_purchase_end_to_end_and_generator_resource(self):
        self.prepare(scrap=6, credits=0)
        self.char1.location = self.rooms["support_1f_c"]
        for raw in ("서", "서", "북"):
            self.command(raw)
        self.assertEqual(self.char1.zone, "salvage_office")
        self.assertIn(f"{SALVAGE_CREDIT_RATE}칩", self.command("정산관 환율"))
        self.command("회수부품 6개 교환")
        self.assertNotIn("scrap", self.char1.profile()["inventory"])
        self.assertEqual(self.char1.profile()["credits"], ITEMS["blade"]["value"])
        for raw in ("남", "동", "동", "승강기", "3층", "동", "북"):
            self.command(raw)
        self.assertEqual(self.char1.zone, "weapon_shop")
        shop = self.command("상품")
        self.assertNotIn("교환", shop)
        self.assertNotIn("회수부품", shop)
        self.command("강철마체테 구매")
        self.assertEqual(self.char1.profile()["credits"], 0)
        self.assertEqual(self.char1.profile()["inventory"]["blade"], 1)
        for raw in ("남", "서", "승강기", "1층", "북", "서"):
            self.command(raw)
        self.command("윤대장 대화")
        self.char1.change(lambda p: rules.add_item(p, "scrap", 3))
        self.char1.location = self.rooms["office"]
        self.command("정비 기록 조사")
        self.char1.location = self.rooms["generator"]
        self.command("발전기 수리")
        self.assertTrue(self.char1.profile()["quests"]["radio_tower"]["generator_fixed"])
        self.assertNotIn("scrap", self.char1.profile()["inventory"])
        self.assertEqual(self.char1.home, self.rooms["dock"])

    def test_scrap_remains_transferable_storable_and_lootable_material(self):
        self.prepare(scrap=5)
        self.char1.location = self.char2.location = self.rooms["storage_room"]
        self.command("보관상자에 회수부품 모두 넣어")
        self.command("보관상자에서 회수부품 모두 꺼내")
        self.command("개인 보관함에 회수부품 넣어")
        self.assertEqual(self.char1.profile()["storage"]["scrap"], 1)
        self.assertNotIn("scrap", self.char2.profile()["storage"])
        self.command("개인 보관함에서 회수부품 꺼내")
        self.command(f"{self.char2.key}에게 회수부품 줘")
        self.command("회수부품 모두 버려")
        self.command("회수부품 모두 가져")
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 4)
        self.assertEqual(self.char2.profile()["inventory"]["scrap"], 1)
        self.assertEqual(self.char1.profile()["credits"], 20)
