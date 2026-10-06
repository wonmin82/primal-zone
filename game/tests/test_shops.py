"""실제 판매자·parser·관찰·bootstrap·Web·지원동 구매 동선."""

from copy import deepcopy
from unittest.mock import Mock, patch

from evennia import create_object, search_tag
from evennia.objects.models import ObjectDB
from evennia.utils.dbserialize import deserialize
from typeclasses.explorers import Explorer
from typeclasses.interactables import INTERACTABLES, Shopkeeper
from world.bootstrap import build_world, stale_definitions
from world.content import ITEMS, SHOP_CATALOGS
from world.content.integrity import errors
from world.observation import context_for
from world.room_hints import render
from world.state import multiplayer_state

from tests.base import WorldCommandTest


class ShopTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        super().setUp()
        self.rooms = self.world_rooms()
        self.sellers = {shop_id: search_tag(shop_id + "_shopkeeper", category="primal_interactable")[0]
                        for shop_id in SHOP_CATALOGS}
        self.char1.location = self.rooms["supply_shop"]
        self.char1.home = self.rooms["dock"]
        self.char1.push_state = Mock()
        self.char1.change(lambda p: p.update(credits=2000, combat_target=None))
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))

    def command(self, raw):
        with patch.object(self.char1, "msg") as message:
            self.char1.execute_cmd(raw)
        return str(message.call_args_list)

    def test_all_menus_only_show_the_sellers_catalog_and_real_npc_title(self):
        for shop_id, seller in self.sellers.items():
            self.char1.location = seller.location
            for raw in ("상품", seller.key + " 상품"):
                output = self.command(raw)
                self.assertIn("[" + seller.key + "]", output)
                for item in {item for catalog in SHOP_CATALOGS.values() for item in catalog["purchase_catalog"]}:
                    self.assertEqual(ITEMS[item]["name"] in output, item in SHOP_CATALOGS[shop_id]["purchase_catalog"])
                self.assertNotIn("회수부품", output)
            self.assertIn(seller.key + "에게 물건이름 구매", self.command(seller.key + " 보기"))
            self.assertIn("판매 목록", self.command(seller.key + " 대화"))

    def test_bare_targeted_alias_purchases_and_infinite_catalog(self):
        for shop_id, item in (("supply", "bandage"), ("weapon", "blade"), ("armor", "armor")):
            seller = self.sellers[shop_id]
            self.char1.location = seller.location
            for raw in (ITEMS[item]["name"] + " 구매", seller.key + "에게 " + ITEMS[item]["name"] + " 구매",
                        seller.aliases.all()[0] + "에게 " + ITEMS[item]["name"] + " buy"):
                before = deepcopy(self.char1.profile())
                self.assertIn("1개를 받아", self.command(raw))
                before["credits"] -= ITEMS[item]["value"]
                before["inventory"][item] = before["inventory"].get(item, 0) + 1
                self.assertEqual(self.char1.profile(), before)
            self.assertIn(ITEMS[item]["name"], self.command("상품"))

    def test_wrong_vendor_quantities_insufficient_credits_and_dock_are_atomic(self):
        for shop_id, item in (("supply", "blade"), ("weapon", "bandage"), ("armor", "spear")):
            seller = self.sellers[shop_id]
            self.char1.location = seller.location
            before = deepcopy(self.char1.profile())
            self.assertIn("취급하지", self.command(seller.key + "에게 " + ITEMS[item]["name"] + " 구매"))
            self.assertEqual(self.char1.profile(), before)
        self.char1.location = self.rooms["supply_shop"]
        self.char1.change(lambda p: p.update(credits=7))
        before = deepcopy(self.char1.profile())
        for raw in ("붕대 구매", "붕대 모두 구매", "붕대 10개 구매"):
            self.assertNotIn("1개를 받아", self.command(raw))
            self.assertEqual(self.char1.profile(), before)
        self.char1.location = self.rooms["dock"]
        for raw in ("상품", "붕대 구매", "강철마체테 구매", "강화조끼 구매"):
            self.assertIn("상인", self.command(raw))
            self.assertEqual(self.char1.profile(), before)
        self.assertEqual([obj["name"] for obj in multiplayer_state(self.char1)["interactables"]], ["윤대장"])
        self.assertEqual(render(context_for(self.char1)), "윤대장 대화")

    def test_multiple_sellers_filter_by_item_and_use_common_number_selector(self):
        seller = self.sellers["supply"]
        weapon = self.sellers["weapon"]
        weapon.location = seller.location
        self.assertIn("여러 명", self.command("상품"))
        self.assertIn("1개를 받아", self.command("붕대 구매"))
        extra = create_object(Shopkeeper, key=seller.key, location=seller.location)
        extra.db.shop_id = "supply"
        before = deepcopy(self.char1.profile())
        self.assertIn("여러 명", self.command("붕대 구매"))
        self.assertEqual(self.char1.profile(), before)
        with patch.object(extra, "act", wraps=extra.act) as selected, patch.object(seller, "act") as other:
            self.command("보급관 2에게 붕대 구매")
            selected.assert_called_once()
            other.assert_not_called()
        commands = [a["command"] for obj in multiplayer_state(self.char1)["interactables"] for a in obj["actions"]]
        self.assertIn("보급관 2에게 붕대 구매", commands)
        weapon.location = self.rooms["weapon_shop"]
        extra.locks.add("view:false()")
        self.assertNotIn("여러 명", self.command("상품"))
        self.assertIn("1개를 받아", self.command("붕대 구매"))

    def test_hidden_seller_is_excluded_from_commands_hints_web_and_detail(self):
        seller = self.sellers["supply"]
        seller.locks.add("view:false()")
        before = deepcopy(self.char1.profile())
        for raw in ("상품", "붕대 구매", "보급관 상품", "보급상인에게 붕대 구매", "보급관 보기"):
            self.assertNotIn("1개를 받아", self.command(raw))
            self.assertEqual(self.char1.profile(), before)
        self.assertEqual(multiplayer_state(self.char1)["interactables"], [])
        self.assertEqual(render(context_for(self.char1)), "")
        self.assertNotIn("보급관", str(self.char1.location.return_appearance(self.char1)))

    def test_object_driven_location_safe_and_noncombat_policy(self):
        seller = self.sellers["weapon"]
        seller.location = self.rooms["support_roof"]
        self.char1.location = self.rooms["weapon_shop"]
        before = deepcopy(self.char1.profile())
        self.command("강철마체테 구매")
        self.assertEqual(self.char1.profile(), before)
        self.char1.location = seller.location
        self.assertIn("1개를 받아", self.command("강철마체테 구매"))
        self.char1.change(lambda p: p.update(combat_target=999))
        before = deepcopy(self.char1.profile())
        for raw in ("상품", "강철마체테 구매", "무기상에게 강철마체테 구매"):
            self.assertIn("전투 중", self.command(raw))
            self.assertEqual(self.char1.profile(), before)
        self.assertEqual(multiplayer_state(self.char1)["interactables"][0]["actions"], [])
        self.char1.change(lambda p: p.update(combat_target=None))
        self.char1.location = seller.location = self.rooms["grass"]
        before = deepcopy(self.char1.profile())
        for raw in ("상품", "강철마체테 구매"):
            self.assertIn("안전한 곳", self.command(raw))
            self.assertEqual(self.char1.profile(), before)
        self.assertEqual(next(obj for obj in multiplayer_state(self.char1)["interactables"] if obj["name"] == seller.key)["actions"], [])

    def test_server_purchase_actions_and_existing_capabilities(self):
        for shop_id, seller in self.sellers.items():
            self.char1.location = seller.location
            actions = multiplayer_state(self.char1)["interactables"][0]["actions"]
            self.assertEqual(actions[0]["command"], seller.key + " 상품")
            self.assertEqual([a["command"] for a in actions if a["command"].endswith(" 구매")],
                             [seller.key + "에게 " + ITEMS[item]["name"] + " 구매" for item in SHOP_CATALOGS[shop_id]["purchase_catalog"]])
            self.assertEqual(render(context_for(self.char1)), seller.key + " 상품")
            self.assertIn("1개를 받아", self.command(actions[1]["command"]))
        for zone, expected in (("storage_room", {"보기"}), ("training_room", {"힘 +1 배분"}),
                               ("infirmary", {"진료", "휴식", "체질 +1 배분"}), ("salvage_office", {"환율", "보기"}),
                               ("dock", {"대화"}), ("office", {"조사"}), ("generator", {"수리"})):
            self.char1.location = self.rooms[zone]
            self.assertEqual({a["label"] for obj in multiplayer_state(self.char1)["interactables"] for a in obj["actions"]}, expected)
        self.char1.location = self.rooms["salvage_office"]
        self.char1.change(lambda p: p["inventory"].update(scrap=2))
        self.assertIn("회수부품 모두 교환", str(multiplayer_state(self.char1)))

    def test_roof_elevator_weapon_purchase_and_smoke_return_route(self):
        self.char1.location = self.rooms["support_roof"]
        for raw in ("승강기", "3층", "동", "북"):
            self.command(raw)
        self.assertEqual(self.char1.zone, "weapon_shop")
        self.command("강철마체테 구매")
        self.assertEqual(self.char1.profile()["inventory"]["blade"], 1)
        for raw in ("남", "서", "승강기", "1층", "북", "서", "북", "북", "동"):
            self.command(raw)
        self.assertEqual(self.char1.zone, "office")
        self.assertEqual(self.char1.home, self.rooms["dock"])

    def test_bootstrap_reuses_all_objects_normalizes_catalog_and_preserves_data(self):
        ids = {key: search_tag(key, category="primal_interactable")[0].id for key in INTERACTABLES}
        box = search_tag("shared_container", category="primal_interactable")[0]
        box.db.items = {"scrap": 4}
        self.char1.change(lambda p: p["storage"].update(scrap=9))
        profiles = [deepcopy(player.profile()) for player in (self.char1, self.char2)]
        elevator = self.rooms["support_elevator"]
        elevator.db.current_stop = "roof"
        count = ObjectDB.objects.count()
        for seller in self.sellers.values():
            seller.db.shop_id = "missing"
            seller.location = self.rooms["dock"]
        for _ in range(2):
            build_world()
            self.assertEqual(ObjectDB.objects.count(), count)
            for key, identity in ids.items():
                objects = search_tag(key, category="primal_interactable")
                self.assertEqual([obj.id for obj in objects], [identity])
                self.assertEqual(objects[0].zone if hasattr(objects[0], "zone") else objects[0].location.db.zone_id, INTERACTABLES[key]["room"])
            for shop_id, seller in self.sellers.items():
                self.assertEqual(seller.db.shop_id, shop_id)
                self.assertEqual(seller.aliases.all(), INTERACTABLES[shop_id + "_shopkeeper"]["aliases"])
            self.assertEqual([player.profile() for player in (self.char1, self.char2)], profiles)
            self.assertEqual(deserialize(box.db.items), {"scrap": 4})
            self.assertEqual(elevator.db.current_stop, "roof")
        self.assertEqual(stale_definitions(), [])
        self.assertEqual(errors(INTERACTABLES), [])
