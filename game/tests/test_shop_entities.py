"""실제 native source/sink, 잔탄 매입과 전체 rollback."""

from copy import deepcopy
from unittest.mock import patch

from evennia.utils.dbserialize import deserialize
from world import equipment_service, rules, shop_service
from world.content import ITEMS
from world.currency import format_currency
from world.firearm_service import create_firearm, loaded_magazine_item, unload_magazine
from world.item_entities import api
from world.item_entities.models import ItemEntity

from tests.phase5_fixture import Phase5Test


class NativeShopTests(Phase5Test):
    native = True

    def setUp(self):
        super().setUp()
        self.seller = self.obj("supply_shopkeeper")
        self.char1.location = self.seller.location

    def test_public_sale_preserves_other_light_and_clears_last_active_reference(self):
        from world.actions.room_npc_presentation import controls_for
        from world.lighting_service import switch

        from tests.action_control_fixture import execute_control

        active = self.create("flashlight", state={"power_type": "flashlight_battery", "remaining_power": 1800,
                                                  "enabled": False, "started_at": None})
        spare = self.create("flashlight")
        switch(self.char1, active, True, now=100)
        active.refresh_from_db()
        before_state = dict(active.state)
        sale = next(row for row in controls_for(self.char1, self.seller)
                    if row["action"]["action_id"] == "shop.sell.supply" and
                    row["action"]["roles"]["subject"][0]["identity"] == str(spare.pk))
        self.assertIn("매입했다", execute_control(self, sale))
        active.refresh_from_db()
        self.assertEqual(active.state, before_state)
        self.assertEqual(str(self.char1.db.active_light_item_id), str(active.pk))
        self.assertFalse(ItemEntity.objects.filter(pk=spare.pk).exists())
        self.assertIn("매입했다", self.command("손전등 1 팔아"))
        self.assertFalse(ItemEntity.objects.filter(pk=active.pk).exists())
        self.assertIsNone(self.char1.db.active_light_item_id)
        self.assertIn("소지품", self.command("탐사용손전등 사"))
        fresh = ItemEntity.objects.get(owner_object=self.char1, definition_id="flashlight")
        self.assertEqual(fresh.state["remaining_power"], 0)
        self.assertFalse(fresh.state["enabled"])

    def test_purchase_sources_and_firearm_full_standard(self):
        for shop_id, identity in (("supply", "bandage"), ("weapon", "guard_carbine")):
            seller = self.obj(shop_id + "_shopkeeper")
            self.char1.location = seller.location
            credits = self.char1.profile()["credits"]
            shop_service.buy(self.char1, seller, identity)
            row = ItemEntity.objects.get(owner_object=self.char1, definition_id=identity)
            self.assertEqual(self.char1.profile()["credits"], credits - rules.purchase_price(identity))
            self.assertEqual(deserialize(self.char1.db.profile)["inventory"], {})
            self.assertFalse(ItemEntity.objects.filter(owner_object=seller).exists())
            if identity == "guard_carbine":
                mag = loaded_magazine_item(row)
                self.assertEqual((mag.state["rounds"], mag.socket), (20, "magazine"))

    def test_create_and_save_failures_restore_purchase_profile_rows_sequence_refs(self):
        for method in ("create", "save"):
            before = self.state()
            failure = patch("world.shop_service.api.create_item", side_effect=RuntimeError("create")) if method == "create" else patch.object(self.char1, "save_profile", side_effect=RuntimeError("save"))
            with failure, self.assertRaises(RuntimeError):
                shop_service.buy(self.char1, self.seller, "bandage")
            self.assertEqual(self.state(), before)
        self.char1.location = self.obj("weapon_shopkeeper").location
        before = self.state()
        with patch.object(self.char1, "save_profile", side_effect=RuntimeError("save")), self.assertRaises(RuntimeError):
            shop_service.buy(self.char1, self.obj("weapon_shopkeeper"), "guard_carbine")
        self.assertEqual(self.state(), before)

    def test_stack_quantity_sale_keeps_source_identity_and_sink_has_no_stock(self):
        row = self.create("bandage", quantity=8)
        sequence, identity = row.sequence, row.pk
        from world.actions.room_npc_presentation import controls_for

        controls = [control for control in controls_for(self.char1, self.seller)
                    if control["action"]["action_id"] == "shop.sell.supply"]
        price = shop_service.resale(row)
        self.assertEqual({control["label"] for control in controls},
                         {f"붕대 1 · {format_currency(price)} 팔아",
                          f"붕대 1 모두 팔아 · 총 {format_currency(price * 8)}"})
        for control in controls:
            self.assertEqual(control["action"]["roles"]["subject"][0]["identity"], str(row.pk))
        self.assertEqual({control["action"]["arguments"]["count"] for control in controls}, {"1", "모두"})
        for raw, remaining in (("붕대 팔아", 7), ("붕대 3개 팔아", 4)):
            self.assertIn("매입", self.command(raw))
            row.refresh_from_db()
            self.assertEqual((row.pk, row.sequence, row.quantity), (identity, sequence, remaining))
        self.assertIn("매입", self.command("붕대 모두 팔아"))
        self.assertFalse(ItemEntity.objects.filter(pk=identity).exists())
        self.assertFalse(ItemEntity.objects.filter(owner_object=self.seller).exists())

    def test_duplicate_weapon_instance_advanced_resale_and_catalog_separation(self):
        first, second = self.create("jungle_longblade"), self.create("jungle_longblade")
        seller = self.obj("weapon_shopkeeper")
        self.char1.location = seller.location
        before = self.state()
        with self.assertRaises(rules.RuleError):
            shop_service.buy(self.char1, seller, "jungle_longblade")
        self.assertEqual(self.state(), before)
        self.assertGreater(shop_service.valuation(self.char1, seller, "정글장도 2"), 0)
        self.assertIn("매입", self.command("정글장도 2 팔아"))
        self.assertTrue(ItemEntity.objects.filter(pk=first.pk).exists())
        self.assertFalse(ItemEntity.objects.filter(pk=second.pk).exists())

    def test_loaded_firearm_rejects_then_unloaded_body_sells(self):
        seller = self.obj("weapon_shopkeeper")
        self.char1.location = seller.location
        firearm = create_firearm("guard_carbine", owner_object=self.char1, mode="full_standard")
        before = self.state()
        with self.assertRaisesRegex(rules.RuleError, "탄창을 먼저"):
            shop_service.sell(self.char1, seller, "경비카빈")
        self.assertEqual(self.state(), before)
        unload_magazine(self.char1, firearm)
        shop_service.sell(self.char1, seller, "경비카빈")
        self.assertFalse(ItemEntity.objects.filter(pk=firearm.pk).exists())

    def test_magazine_price_fixture_and_residual_output_use_production_sell_path(self):
        self.enterContext(patch.dict(ITEMS["mag_556_standard"], value=44, resale_unit_value=22))
        self.enterContext(patch.dict(ITEMS["ammo_556"], resale_unit_value=1))
        seller = self.obj("weapon_shopkeeper")
        self.char1.location = seller.location
        empty = self.create("mag_556_standard", state={"rounds": 0})
        self.assertEqual(shop_service.resale(empty), 22)
        api.delete_item(empty, operation="burn")
        mag = self.create("mag_556_standard", state={"rounds": 9})
        self.assertEqual(shop_service.resale(mag), 31)
        credits = self.char1.profile()["credits"]
        output = self.command("카빈표준 팔아")
        self.assertIn("잔탄 9발", output)
        self.assertEqual(self.char1.profile()["credits"], credits + 31)

    def test_sale_failures_nonaccepted_quantity_and_save_rollback(self):
        self.create("bandage", quantity=5)
        for raw in ("붕대 0개 팔아", "붕대 -1개 팔아", "붕대 9개 팔아", "붕대 3개 모두 팔아"):
            before = self.state()
            self.command(raw)
            self.assertEqual(self.state(), before)
        self.create("cutting_machete")
        before = self.state()
        with self.assertRaises(rules.RuleError):
            shop_service.sell(self.char1, self.seller, "절단마체테")
        self.assertEqual(self.state(), before)
        for method in ("delete", "save"):
            failure = patch("world.shop_service.api.destroy_quantity", side_effect=RuntimeError("delete")) if method == "delete" else patch.object(self.char1, "save_profile", side_effect=RuntimeError("save"))
            before = self.state()
            with failure, self.assertRaises(RuntimeError):
                shop_service.sell(self.char1, self.seller, "붕대", 3)
            self.assertEqual(self.state(), before)

    def test_web_payload_uses_native_selectors_and_catalog_only_purchase(self):
        from world.actions.room_npc_presentation import controls_for

        from tests.action_control_fixture import assert_provider, execute_control

        first = self.create("cutting_machete")
        second = self.create("cutting_machete")
        advanced = self.create("jungle_longblade")
        seller = self.obj("weapon_shopkeeper")
        self.char1.location = seller.location
        actions = controls_for(self.char1, seller, observed_at=100)
        sales = [row for row in actions if row["action"]["action_id"] == "shop.sell.weapon"]
        self.assertEqual({row["action"]["roles"]["subject"][0]["identity"] for row in sales},
                         {str(first.pk), str(second.pk), str(advanced.pk)})
        self.assertEqual(shop_service.resale(second), 27)
        self.assertEqual({row["action"]["roles"]["subject"][0]["identity"]: row["label"] for row in sales},
                         {str(first.pk): "절단마체테 1 · 27칩 팔아",
                          str(second.pk): "절단마체테 2 · 27칩 팔아",
                          str(advanced.pk): f"정글장도 1 · {format_currency(shop_service.resale(advanced))} 팔아"})
        self.assertNotIn("shop.buy.jungle_longblade", [row["action"]["action_id"] for row in actions])
        for row in actions:
            assert_provider(self, row, seller)
        # 안정 UUID는 실행 payload에 보존하되 사용자 레이블에는 노출하지 않는다.
        self.assertNotIn(str(first.pk), str([row["label"] for row in actions]))
        selected = next(row for row in sales if row["action"]["roles"]["subject"][0]["identity"] == str(second.pk))
        credits = self.char1.profile()["credits"]
        proceeds = shop_service.resale(second)
        self.assertIn("매입", execute_control(self, selected))
        self.assertTrue(ItemEntity.objects.filter(pk=first.pk).exists())
        self.assertFalse(ItemEntity.objects.filter(pk=second.pk).exists())
        self.assertEqual(self.char1.profile()["credits"], credits + proceeds)

    def test_equipped_or_other_owner_item_cannot_sell(self):
        row = self.create("cutting_machete")
        equipment_service.equip_item(self.char1, row)
        seller = self.obj("weapon_shopkeeper")
        self.char1.location = seller.location
        before = self.state()
        with self.assertRaises(rules.RuleError):
            shop_service.sell(self.char1, seller, "절단마체테")
        self.assertEqual(self.state(), before)

    def test_active_flashlight_sale_reconciles_and_failed_sale_restores_reference(self):
        from world.lighting_service import switch

        row = self.create("flashlight", state={"power_type": "flashlight_battery", "remaining_power": 1800,
                                              "enabled": False, "started_at": None})
        switch(self.char1, row, True, now=100)
        before = self.state()
        with patch.object(self.char1, "save_profile", side_effect=RuntimeError("save")), self.assertRaises(RuntimeError):
            shop_service.sell(self.char1, self.seller, "손전등")
        self.assertEqual(self.state(), before)
        shop_service.sell(self.char1, self.seller, "손전등")
        self.assertIsNone(self.char1.db.active_light_item_id)
        self.assertFalse(ItemEntity.objects.filter(pk=row.pk).exists())


    def test_public_sale_preserves_b1_gap_without_index_fallback(self):
        first = self.create("jungle_longblade")
        second = self.create("jungle_longblade")
        seller = self.obj("weapon_shopkeeper")
        self.char1.location = seller.location
        api.delete_item(first, operation="burn")
        before = self.state()
        self.command("정글장도 1 팔아")
        self.assertEqual(self.state(), before)
        self.assertTrue(ItemEntity.objects.filter(pk=second.pk).exists())
        from world.actions.room_npc_presentation import controls_for

        sale = next(row for row in controls_for(self.char1, seller)
                    if row["action"]["action_id"] == "shop.sell.weapon")
        self.assertEqual(sale["label"], f"정글장도 2 · {format_currency(shop_service.resale(second))} 팔아")
        self.assertEqual(sale["action"]["roles"]["subject"][0]["identity"], str(second.pk))
        self.assertIn("매입", self.command("정글장도 2 팔아"))
        self.assertFalse(ItemEntity.objects.filter(pk=second.pk).exists())


class LegacyShopCompatibilityTests(Phase5Test):
    def test_equipped_copy_keeps_spare_copy_sale_action(self):
        self.char1.change(lambda p: (p["inventory"].update(cutting_machete=2), p["equipment"].update(weapon="cutting_machete")))
        seller = self.obj("weapon_shopkeeper")
        self.char1.location = seller.location
        credits = self.char1.profile()["credits"]
        sale = shop_service.sell(self.char1, seller, "절단마체테")
        self.assertEqual((sale.identity, sale.quantity), ("cutting_machete", 1))
        self.assertEqual(self.char1.profile()["inventory"]["cutting_machete"], 1)
        self.assertEqual(self.char1.profile()["equipment"]["weapon"], "cutting_machete")
        self.assertEqual(self.char1.profile()["credits"], credits + sale.proceeds)
        with self.assertRaises(rules.RuleError):
            shop_service.sell(self.char1, seller, "절단마체테")

    def test_buy_sale_quantity_field_gear_without_entity_creation(self):
        seller = self.obj("supply_shopkeeper")
        self.char1.location = seller.location
        for _ in range(3):
            shop_service.buy(self.char1, seller, "bandage")
        self.char1.change(lambda p: p["inventory"].update(bandage=8, jungle_longblade=1, tactical_protective_suit=1))
        for quantity in (1, 3, None):
            before = self.char1.profile()
            sale = shop_service.sell(self.char1, seller, "붕대", quantity)
            expected = before["inventory"]["bandage"] if quantity is None else quantity
            self.assertEqual(sale.quantity, expected)
            self.assertEqual(self.char1.profile()["credits"], before["credits"] + sale.proceeds)
        self.assertNotIn("bandage", self.char1.profile()["inventory"])
        for shop, name in (("weapon", "정글장도"), ("armor", "전술방호복")):
            seller = self.obj(shop + "_shopkeeper")
            self.char1.location = seller.location
            price = shop_service.valuation(self.char1, seller, name)
            self.assertGreater(price, 0)
            credits = self.char1.profile()["credits"]
            sale = shop_service.sell(self.char1, seller, name)
            self.assertEqual((sale.quantity, sale.proceeds), (1, price))
            self.assertEqual(self.char1.profile()["credits"], credits + price)
        self.assertFalse(ItemEntity.objects.exists())

    def test_legacy_purchase_failure_preserves_every_field(self):
        seller = self.obj("supply_shopkeeper")
        self.char1.location = seller.location
        before = deepcopy(self.state())
        with patch.object(self.char1, "save_profile", side_effect=RuntimeError("save")), self.assertRaises(RuntimeError):
            shop_service.buy(self.char1, seller, "bandage")
        self.assertEqual(self.state(), before)
