"""실제 native source/sink, 잔탄 매입과 전체 rollback."""

from copy import deepcopy
from unittest.mock import patch

from world import equipment_service, rules, shop_service
from world.content import ITEMS
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

    def test_purchase_sources_and_firearm_full_standard(self):
        for shop_id, identity in (("supply", "bandage"), ("weapon", "carbine")):
            seller = self.obj(shop_id + "_shopkeeper")
            self.char1.location = seller.location
            credits = self.char1.profile()["credits"]
            shop_service.buy(self.char1, seller, identity)
            row = ItemEntity.objects.get(owner_object=self.char1, definition_id=identity)
            self.assertEqual(self.char1.profile()["credits"], credits - ITEMS[identity]["value"])
            self.assertEqual(self.char1.profile()["inventory"], {})
            self.assertFalse(ItemEntity.objects.filter(owner_object=seller).exists())
            if identity == "carbine":
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
            shop_service.buy(self.char1, self.obj("weapon_shopkeeper"), "carbine")
        self.assertEqual(self.state(), before)

    def test_stack_quantity_sale_keeps_source_identity_and_sink_has_no_stock(self):
        row = self.create("bandage", quantity=8)
        sequence, identity = row.sequence, row.pk
        for raw, remaining in (("붕대 판매", 7), ("붕대 3개 판매", 4)):
            self.assertIn("매입", self.command(raw))
            row.refresh_from_db()
            self.assertEqual((row.pk, row.sequence, row.quantity), (identity, sequence, remaining))
        self.assertIn("매입", self.command("붕대 모두 판매"))
        self.assertFalse(ItemEntity.objects.filter(pk=identity).exists())
        self.assertFalse(ItemEntity.objects.filter(owner_object=self.seller).exists())

    def test_duplicate_weapon_instance_advanced_resale_and_catalog_separation(self):
        first, second = self.create("jungle_blade"), self.create("jungle_blade")
        seller = self.obj("weapon_shopkeeper")
        self.char1.location = seller.location
        before = self.state()
        with self.assertRaises(rules.RuleError):
            shop_service.buy(self.char1, seller, "jungle_blade")
        self.assertEqual(self.state(), before)
        self.assertGreater(shop_service.valuation(self.char1, seller, "정글도 2"), 0)
        self.assertIn("매입", self.command("정글도 2 판매"))
        self.assertTrue(ItemEntity.objects.filter(pk=first.pk).exists())
        self.assertFalse(ItemEntity.objects.filter(pk=second.pk).exists())

    def test_loaded_firearm_rejects_then_unloaded_body_sells(self):
        seller = self.obj("weapon_shopkeeper")
        self.char1.location = seller.location
        firearm = create_firearm("carbine", owner_object=self.char1, mode="full_standard")
        before = self.state()
        with self.assertRaisesRegex(rules.RuleError, "탄창을 먼저"):
            shop_service.sell(self.char1, seller, "탐사카빈")
        self.assertEqual(self.state(), before)
        unload_magazine(self.char1, firearm)
        shop_service.sell(self.char1, seller, "탐사카빈")
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
        output = self.command("카빈표준 판매")
        self.assertIn("잔탄 9발", output)
        self.assertEqual(self.char1.profile()["credits"], credits + 31)

    def test_sale_failures_nonaccepted_quantity_and_save_rollback(self):
        self.create("bandage", quantity=5)
        for raw in ("붕대 0개 판매", "붕대 -1개 판매", "붕대 9개 판매", "붕대 3개 모두 판매"):
            before = self.state()
            self.command(raw)
            self.assertEqual(self.state(), before)
        self.create("blade")
        before = self.state()
        with self.assertRaises(rules.RuleError):
            shop_service.sell(self.char1, self.seller, "강철마체테")
        self.assertEqual(self.state(), before)
        for method in ("delete", "save"):
            failure = patch("world.shop_service.api.destroy_quantity", side_effect=RuntimeError("delete")) if method == "delete" else patch.object(self.char1, "save_profile", side_effect=RuntimeError("save"))
            before = self.state()
            with failure, self.assertRaises(RuntimeError):
                shop_service.sell(self.char1, self.seller, "붕대", 3)
            self.assertEqual(self.state(), before)

    def test_web_payload_uses_native_selectors_and_catalog_only_purchase(self):
        self.create("blade")
        self.create("blade")
        self.create("jungle_blade")
        seller = self.obj("weapon_shopkeeper")
        self.char1.location = seller.location
        actions = seller.web_actions(self.char1, "무기상", observed_at=100)
        commands = [row["command"] for row in actions]
        self.assertIn("무기상에게 강철마체테 2 판매", commands)
        self.assertIn("무기상에게 정글도 판매", commands)
        self.assertNotIn("무기상에게 정글도 구매", commands)
        self.assertNotIn(str(ItemEntity.objects.first().pk), str(actions))

    def test_equipped_or_other_owner_item_cannot_sell(self):
        row = self.create("blade")
        equipment_service.equip_item(self.char1, row)
        seller = self.obj("weapon_shopkeeper")
        self.char1.location = seller.location
        before = self.state()
        with self.assertRaises(rules.RuleError):
            shop_service.sell(self.char1, seller, "강철마체테")
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


class LegacyShopCompatibilityTests(Phase5Test):
    def test_equipped_copy_keeps_spare_copy_sale_action(self):
        self.char1.change(lambda p: (p["inventory"].update(blade=2), p["equipment"].update(weapon="blade")))
        seller = self.obj("weapon_shopkeeper")
        self.char1.location = seller.location
        self.assertIn("무기상에게 강철마체테 판매", str(seller.web_actions(self.char1, "무기상")))
        self.command("강철마체테 판매")
        self.assertEqual(self.char1.profile()["inventory"]["blade"], 1)
        self.assertNotIn("무기상에게 강철마체테 판매", str(seller.web_actions(self.char1, "무기상")))

    def test_buy_sale_quantity_field_gear_without_entity_creation(self):
        seller = self.obj("supply_shopkeeper")
        self.char1.location = seller.location
        for _ in range(3):
            shop_service.buy(self.char1, seller, "bandage")
        self.char1.change(lambda p: p["inventory"].update(bandage=8, jungle_blade=1, tactical_vest=1))
        for raw in ("붕대 판매", "붕대 3개 판매", "붕대 모두 판매"):
            self.assertIn("매입", self.command(raw))
        self.assertNotIn("bandage", self.char1.profile()["inventory"])
        for shop, name in (("weapon", "정글도"), ("armor", "경량전술조끼")):
            seller = self.obj(shop + "_shopkeeper")
            self.char1.location = seller.location
            self.assertIn("매입가", self.command(name + " 가치"))
            self.assertIn("매입", self.command(name + " 판매"))
        self.assertFalse(ItemEntity.objects.exists())

    def test_legacy_purchase_failure_preserves_every_field(self):
        seller = self.obj("supply_shopkeeper")
        self.char1.location = seller.location
        before = deepcopy(self.state())
        with patch.object(self.char1, "save_profile", side_effect=RuntimeError("save")), self.assertRaises(RuntimeError):
            shop_service.buy(self.char1, seller, "bandage")
        self.assertEqual(self.state(), before)
