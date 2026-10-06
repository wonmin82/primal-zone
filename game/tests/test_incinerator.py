"""출입증 확정·재발급과 legacy/native 소각/잔여 identity/rollback."""

from unittest.mock import patch

from world import credential_service as credentials
from world import incinerator_service, rules
from world.access import can_enter
from world.content import ITEMS
from world.firearm_service import create_firearm, unload_magazine
from world.item_entities.models import ItemEntity

from tests.phase5_fixture import Phase5Test


class IncineratorTests(Phase5Test):
    def test_credential_exact_confirm_access_loss_and_issuer_reissue(self):
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(started=True, claimed=True))
        credentials.grant_credential(self.char1, "outpost_supply_pass")
        before = self.state()
        for raw in ("전초 보급구역 출입증 소각", "전초 보급구역 출입증 확정", "전초 보급구역 출입증 소각 확정 확정",
                    "전초 보급구역 출입증 확정 소각"):
            self.command(raw)
            self.assertEqual(self.state(), before)
        self.assertIn("소각 확정", self.command("전초 보급구역 출입증 소각"))
        self.assertTrue(can_enter(self.char1, "outpost_weapon"))
        self.assertIn("소각했다", self.command("전초 보급구역 출입증 소각 확정"))
        self.assertFalse(can_enter(self.char1, "outpost_weapon"))
        self.assertEqual(self.char1.profile()["quests"], before[0][0]["quests"])
        self.assertEqual(self.char1.profile()["credits"], before[0][0]["credits"])
        self.char1.location = self.rooms["dock"]
        self.assertIn("재발급", self.command("윤대장 대화"))
        self.assertTrue(can_enter(self.char1, "outpost_weapon"))

    def test_same_room_and_visible_incinerator_required(self):
        credentials.grant_credential(self.char1, "outpost_supply_pass")
        before = self.state()
        self.char1.location = self.rooms["dock"]
        with self.assertRaises(rules.RuleError):
            incinerator_service.incinerate(self.char1, "전초 보급구역 출입증", confirmed=True)
        self.char1.location = self.rooms["salvage_office"]
        self.obj("incinerator").locks.add("view:false()")
        with self.assertRaises(rules.RuleError):
            incinerator_service.incinerate(self.char1, "전초 보급구역 출입증", confirmed=True)
        self.assertEqual(self.state(), before)

    def test_legacy_quantity_burn_and_no_lazy_conversion(self):
        self.char1.change(lambda p: p["inventory"].update(bandage=8))
        for raw, remaining in (("붕대 소각", 7), ("붕대 3개 소각", 4), ("붕대 모두 소각", 0)):
            self.assertIn("소각했다", self.command(raw))
            self.assertEqual(self.char1.profile()["inventory"].get("bandage", 0), remaining)
        self.assertFalse(ItemEntity.objects.exists())

    def test_legacy_failure_restores_profile_and_refs(self):
        before = self.state()
        with patch.object(self.char1, "save_profile", side_effect=RuntimeError("save")), self.assertRaises(RuntimeError):
            incinerator_service.incinerate(self.char1, "붕대")
        self.assertEqual(self.state(), before)


class NativeIncineratorTests(Phase5Test):
    native = True

    def test_native_quantities_keep_source_uuid_sequence_and_state(self):
        row = self.create("bandage", quantity=8, state={"provenance": "fixture"})
        initial = (row.pk, row.sequence, row.state)
        for raw, remaining in (("붕대 소각", 7), ("붕대 3개 소각", 4)):
            self.assertIn("소각했다", self.command(raw))
            row.refresh_from_db()
            self.assertEqual((row.pk, row.sequence, row.state), initial)
            self.assertEqual(row.quantity, remaining)
        self.command("붕대 모두 소각")
        self.assertFalse(ItemEntity.objects.filter(pk=row.pk).exists())

    def test_magazine_rounds_destroyed_and_loaded_firearm_rejected(self):
        firearm = create_firearm("carbine", owner_object=self.char1, mode="full_standard")
        before = self.state()
        with self.assertRaisesRegex(rules.RuleError, "탄창을 먼저"):
            incinerator_service.incinerate(self.char1, "탐사카빈")
        self.assertEqual(self.state(), before)
        unload_magazine(self.char1, firearm)
        credits = self.char1.profile()["credits"]
        self.assertIn("소각했다", self.command("카빈표준 소각"))
        self.assertFalse(ItemEntity.objects.filter(definition_id="ammo_556").exists())
        self.assertEqual(self.char1.profile()["credits"], credits)
        self.assertIn("소각했다", self.command("탐사카빈 소각"))

    def test_invalid_quantity_and_after_change_failure_roll_back_everything(self):
        self.create("bandage", quantity=5)
        for value in ("붕대 0개", "붕대 6개", "붕대 3개 모두", "붕대 확정"):
            before = self.state()
            with self.assertRaises(rules.RuleError):
                incinerator_service.incinerate(self.char1, value)
            self.assertEqual(self.state(), before)
        for value in ("붕대 3개", "붕대 모두"):
            before = self.state()
            with patch("world.equipment_service.after_item_change", side_effect=RuntimeError("reconcile")), self.assertRaises(RuntimeError):
                incinerator_service.incinerate(self.char1, value)
            self.assertEqual(self.state(), before)

    def test_credential_burn_failure_retains_pass_and_access(self):
        credentials.grant_credential(self.char1, "outpost_supply_pass")
        before = self.state()
        with patch("world.equipment_service.after_item_change", side_effect=RuntimeError("reconcile")), self.assertRaises(RuntimeError):
            incinerator_service.incinerate(self.char1, ITEMS["outpost_supply_pass"]["name"], confirmed=True)
        self.assertEqual(self.state(), before)
        self.assertTrue(can_enter(self.char1, "outpost_weapon"))

    def test_active_flashlight_burn_clears_reference_atomically(self):
        from world.lighting_service import switch

        row = self.create("flashlight", state={"power_type": "flashlight_battery", "remaining_power": 1800,
                                              "enabled": False, "started_at": None})
        switch(self.char1, row, True, now=100)
        self.assertIn("소각했다", self.command("손전등 소각"))
        self.assertIsNone(self.char1.db.active_light_item_id)
        self.assertFalse(ItemEntity.objects.filter(pk=row.pk).exists())
