"""실제 판매자·parser·관찰·bootstrap·Web·지원동 사 동선."""

import re
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
from world.selection_numbers.api import descriptor
from world.state import multiplayer_state

from tests.action_control_fixture import selection_label
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
            for raw in ("목록", seller.key + " 목록"):
                output = self.command(raw)
                self.assertIn("[" + seller.key + "]", output)
                for item in {item for catalog in SHOP_CATALOGS.values() for item in catalog["purchase_catalog"]}:
                    # 집중링/정신집중링처럼 이름의 부분 문자열이 겹쳐도 독립 상품으로 검사한다.
                    self.assertEqual(bool(re.search(r"(?<![가-힣])" + re.escape(ITEMS[item]["name"]) + r" ·", output)), item in SHOP_CATALOGS[shop_id]["purchase_catalog"], item)
                self.assertNotIn("회수부품", output)
            self.assertIn(selection_label(seller) + "에게 물건이름 사", self.command(seller.key + " 봐"))
            self.assertIn("판매 목록", self.command(seller.key + "에게 보급 말"))

    def test_bare_targeted_alias_purchases_and_infinite_catalog(self):
        for shop_id, item in (("supply", "bandage"), ("weapon", "cutting_machete"), ("armor", "reinforced_vest")):
            seller = self.sellers[shop_id]
            self.char1.location = seller.location
            for raw in (ITEMS[item]["name"] + " 사", seller.key + "에게 " + ITEMS[item]["name"] + " 사",
                        seller.aliases.all()[0] + "에게 " + ITEMS[item]["name"] + " 구입"):
                before = deepcopy(self.char1.profile())
                self.assertIn("1개를 받아", self.command(raw))
                before["credits"] -= ITEMS[item]["value"]
                before["inventory"][item] = before["inventory"].get(item, 0) + 1
                self.assertEqual(self.char1.profile(), before)
            self.assertIn(ITEMS[item]["name"], self.command("목록"))

    def test_wrong_vendor_quantities_insufficient_credits_and_dock_are_atomic(self):
        for shop_id, item in (("supply", "cutting_machete"), ("weapon", "bandage"), ("armor", "pioneer_spear")):
            seller = self.sellers[shop_id]
            self.char1.location = seller.location
            before = deepcopy(self.char1.profile())
            self.assertIn("취급하지", self.command(seller.key + "에게 " + ITEMS[item]["name"] + " 사"))
            self.assertEqual(self.char1.profile(), before)
        self.char1.location = self.rooms["supply_shop"]
        self.char1.change(lambda p: p.update(credits=7))
        before = deepcopy(self.char1.profile())
        for raw in ("붕대 사", "붕대 모두 사", "붕대 10개 사"):
            self.assertNotIn("1개를 받아", self.command(raw))
            self.assertEqual(self.char1.profile(), before)
        self.char1.location = self.rooms["dock"]
        for raw in ("목록", "붕대 사", "절단마체테 사", "강화방호조끼 사"):
            self.assertIn("상인", self.command(raw))
            self.assertEqual(self.char1.profile(), before)
        self.assertEqual([obj["name"] for obj in multiplayer_state(self.char1)["interactables"]], ["윤대장"])
        self.assertEqual(render(context_for(self.char1)), "'윤대장 1에게 안녕")

    def test_multiple_sellers_filter_by_item_and_use_common_number_selector(self):
        seller = self.sellers["supply"]
        weapon = self.sellers["weapon"]
        weapon.location = seller.location
        self.assertIn("여러 명", self.command("목록"))
        self.assertIn("1개를 받아", self.command("붕대 사"))
        extra = create_object(Shopkeeper, key=seller.key, location=seller.location,
                              attributes=[("selection_group_id", descriptor(seller).group_id)])
        extra.db.shop_id = "supply"
        before = deepcopy(self.char1.profile())
        self.assertIn("여러 명", self.command("붕대 사"))
        self.assertEqual(self.char1.profile(), before)
        from world import interactable_services

        from tests.action_control_fixture import assert_provider

        with patch.object(interactable_services, "shopkeeper", wraps=interactable_services.shopkeeper) as selected:
            self.command("보급관 2에게 붕대 사")
        self.assertEqual(selected.call_count, 1)
        self.assertEqual(selected.call_args.args[0].pk, extra.pk)
        controls = [a for obj in multiplayer_state(self.char1)["interactables"] for a in obj["actions"]
                    if a.get("action", {}).get("action_id") == "shop.buy.bandage"]
        selected = next(control for control in controls
                        if control["action"]["roles"]["provider"][0]["identity"] == str(extra.pk))
        assert_provider(self, selected, extra)
        weapon.location = self.rooms["weapon_shop"]
        extra.locks.add("view:false()")
        self.assertNotIn("여러 명", self.command("목록"))
        self.assertIn("1개를 받아", self.command("붕대 사"))

    def test_hidden_seller_is_excluded_from_commands_hints_web_and_detail(self):
        seller = self.sellers["supply"]
        seller.locks.add("view:false()")
        before = deepcopy(self.char1.profile())
        for raw in ("목록", "붕대 사", "보급관 목록", "보급상인에게 붕대 사", "보급관 봐"):
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
        self.command("절단마체테 사")
        self.assertEqual(self.char1.profile(), before)
        self.char1.location = seller.location
        self.assertIn("1개를 받아", self.command("절단마체테 사"))
        self.char1.change(lambda p: p.update(combat_target=999))
        before = deepcopy(self.char1.profile())
        for raw in ("목록", "절단마체테 사", "무기상에게 절단마체테 사"):
            self.assertIn("전투 중", self.command(raw))
            self.assertEqual(self.char1.profile(), before)
        self.assertEqual(multiplayer_state(self.char1)["interactables"][0]["actions"], [])
        self.char1.change(lambda p: p.update(combat_target=None))
        self.char1.location = seller.location = self.rooms["grass"]
        before = deepcopy(self.char1.profile())
        for raw in ("목록", "절단마체테 사"):
            self.assertIn("안전한 곳", self.command(raw))
            self.assertEqual(self.char1.profile(), before)
        self.assertEqual(next(obj for obj in multiplayer_state(self.char1)["interactables"] if obj["name"] == seller.key)["actions"], [])

    def test_server_purchase_actions_and_existing_capabilities(self):
        for shop_id, seller in self.sellers.items():
            self.char1.location = seller.location
            actions = multiplayer_state(self.char1)["interactables"][0]["actions"]
            from tests.action_control_fixture import assert_provider, execute_control

            self.assertEqual(actions[0]["action"]["action_id"], "shop.menu." + shop_id)
            purchases = [a for a in actions if a.get("action", {}).get("action_id", "").startswith("shop.buy.")]
            self.assertEqual([a["action"]["arguments"]["value"] for a in purchases],
                             list(SHOP_CATALOGS[shop_id]["purchase_catalog"]))
            for control in (actions[0], *purchases):
                assert_provider(self, control, seller)
            self.assertEqual(render(context_for(self.char1)), seller.key + " 목록")
            item = purchases[0]["action"]["arguments"]["value"]
            before = deepcopy(self.char1.profile())
            self.assertIn("1개를 받아", execute_control(self, purchases[0]))
            self.assertEqual(self.char1.profile()["credits"], before["credits"] - ITEMS[item]["value"])
            self.assertEqual(self.char1.profile()["inventory"].get(item, 0), before["inventory"].get(item, 0) + ITEMS[item].get("purchase_quantity", 1))
        for zone, expected in (("storage_room", {"봐"}), ("training_room", {"힘 +1 배분"}),
                               ("infirmary", {"회복"}), ("recovery_room", {"휴식", "닫아"}), ("survival_training_room", {"체질 +1 배분"}), ("salvage_office", {"환율", "봐"}),
                               ("dock", {"말 걸기"}), ("office", {"조사"}), ("generator", {"수리"})):
            self.char1.location = self.rooms[zone]
            if zone == "infirmary":
                self.char1.change(lambda p: p.update(hp=1))
                from world import rules

                restored, cost = rules.treatment_quote(self.char1.profile_snapshot(), safe=True)
                expected = {f"HP {restored} 회복 · 예상 {cost}칩"}
            if zone == "recovery_room":
                from world.doors import operate
                # 실제 조작으로 OPEN을 준비해 현재 침대/문 기능을 함께 검증한다.
                operate(self.char1, "문", "닫아")
                operate(self.char1, "문", "열어")
            self.assertEqual({a["label"] for obj in multiplayer_state(self.char1)["interactables"] for a in obj["actions"] if a["label"] != "말 걸기" or zone == "dock"}, expected)
        self.char1.location = self.rooms["salvage_office"]
        from world.equipment_service import use_item_entities

        profile = self.char1.profile()
        profile.update(inventory={}, equipment={"weapon": None, "armor": None})
        self.char1.db.profile = profile
        use_item_entities(self.char1)
        self.char1.change(lambda p: p["inventory"].update(scrap=2))
        self.assertIn("회수부품 모두 교환", str(multiplayer_state(self.char1)))

    def test_roof_elevator_weapon_purchase_and_smoke_return_route(self):
        self.char1.location = self.rooms["support_roof"]
        for raw in ("승강기", "5층", "동", "북"):
            self.command(raw)
        self.assertEqual(self.char1.zone, "weapon_shop")
        self.command("절단마체테 사")
        self.assertEqual(self.char1.profile()["inventory"]["cutting_machete"], 1)
        for raw in ("남", "서", "승강기", "1층", "서", "북", "북", "동"):
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
