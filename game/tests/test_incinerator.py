"""출입증 확정·재발급과 legacy/native 소각/잔여 identity/rollback."""

from unittest.mock import patch

from world import credential_service as credentials
from world import incinerator_service, rules
from world.access import can_enter
from world.content import ITEMS
from world.firearm_service import create_firearm, unload_magazine
from world.item_entities.models import ItemEntity

from tests.phase5_fixture import Phase5Test


class CredentialConfirmationCases:
    def burn_request(self, value, *, confirmed=False):
        """Native는 공개 Action 입력, Legacy는 보존된 도메인 API만 검증한다."""
        if self.native:
            suffix = " 소각 확정" if confirmed else " 소각"
            return self.command(value + suffix)
        return incinerator_service.incinerate(self.char1, value, confirmed=confirmed)

    def test_credentials_reject_quantity_confirmation_and_accept_exact_selector(self):
        for identity, quest in credentials.CREDENTIAL_QUESTS.items():
            with self.subTest(credential=identity):
                self.char1.change(lambda p: p["quests"][quest].update(started=True, claimed=True))
                credentials.grant_credential(self.char1, identity)
                name = ITEMS[identity]["name"]
                before = self.state()
                access = [can_enter(self.char1, zone) for zone in ("outpost_equipment", "outpost_weapon", "reserved_equipment", "reserved_weapon")]
                self.assertIn(name + " 소각 확정", self.burn_request(name))
                self.assertEqual(self.state(), before)
                for suffix in ("1개", "2개", "모두"):
                    with self.subTest(suffix=suffix):
                        if self.native:
                            # 잘못된 공개 입력은 실제 운영 Manifest/TargetResolver로 거절한다.
                            self.burn_request(f"{name} {suffix}", confirmed=True)
                            self.assertEqual(self.state(), before)
                        with self.assertRaises(rules.RuleError):
                            incinerator_service.incinerate(self.char1, f"{name} {suffix}", confirmed=True)
                        self.assertEqual(self.state(), before)
                        self.assertEqual([can_enter(self.char1, zone) for zone in ("outpost_equipment", "outpost_weapon", "reserved_equipment", "reserved_weapon")], access)
                for raw in (name + " 확정", name + " 확정 소각", name + " 소각 확정 확정"):
                    if self.native:
                        self.command(raw)
                    else:
                        with self.assertRaises(rules.RuleError):
                            self.burn_request(raw, confirmed=True)
                    self.assertEqual(self.state(), before)
                self.assertIn("소각했다", self.burn_request(name, confirmed=True))
                self.assertFalse(credentials.has_credential(self.char1, identity))
                after = self.state()
                expected = before[0]
                if self.native:
                    expected[0]["inventory"].pop(identity)
                self.assertEqual((after[0], after[2], after[3]), (expected, before[2], before[3]))
                if identity == "outpost_supply_pass":
                    self.assertFalse(can_enter(self.char1, "outpost_weapon"))
                credentials.reissue_credential(self.char1, identity)
                if self.native:
                    expected[0]["inventory"][identity] = 1
                self.assertEqual(self.state()[0], expected)
                # 구형 도메인 API의 ID/selector 호환 검사이며 공개 Action의 B-1 선택과 구분한다.
                incinerator_service.incinerate(self.char1, identity + " 1", confirmed=True)
                self.assertFalse(credentials.has_credential(self.char1, identity))

    def test_confirmed_regular_stack_is_rejected_without_mutation(self):
        if self.native:
            self.create("bandage", quantity=3)
        before = self.state()
        if self.native:
            self.burn_request("붕대", confirmed=True)
            self.assertEqual(self.state(), before)
        with self.assertRaisesRegex(rules.RuleError, "출입증"):
            incinerator_service.incinerate(self.char1, "붕대", confirmed=True)
        self.assertEqual(self.state(), before)


class IncineratorTests(CredentialConfirmationCases, Phase5Test):
    """Legacy 프로필과 기존 소각 도메인의 명시적 API 호환성."""

    def test_credential_exact_confirm_access_loss_and_issuer_reissue(self):
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(started=True, claimed=True))
        credentials.grant_credential(self.char1, "outpost_supply_pass")
        before = self.state()
        # 이 클래스는 Legacy API 호환 검사다. 공개 소각 문법은 NativeIncineratorTests가 검증한다.
        self.burn_request("전초 보급구역 출입증")
        self.assertEqual(self.state(), before)
        for value in ("전초 보급구역 출입증 확정", "전초 보급구역 출입증 소각 확정 확정",
                      "전초 보급구역 출입증 확정 소각"):
            with self.assertRaises(rules.RuleError):
                self.burn_request(value, confirmed=True)
            self.assertEqual(self.state(), before)
        self.assertIn("소각 확정", self.burn_request("전초 보급구역 출입증"))
        self.assertTrue(can_enter(self.char1, "outpost_weapon"))
        self.assertIn("소각했다", self.burn_request("전초 보급구역 출입증", confirmed=True))
        self.assertFalse(can_enter(self.char1, "outpost_weapon"))
        self.assertEqual(self.char1.profile()["quests"], before[0][0]["quests"])
        self.assertEqual(self.char1.profile()["credits"], before[0][0]["credits"])
        self.char1.location = self.rooms["dock"]
        self.assertIn("재발급", self.command("윤대장에게 재발급 말"))
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
            self.assertIn("소각했다", incinerator_service.incinerate(self.char1, raw.removesuffix(" 소각")))
            self.assertEqual(self.char1.profile()["inventory"].get("bandage", 0), remaining)
        self.assertFalse(ItemEntity.objects.exists())

    def test_legacy_failure_restores_profile_and_refs(self):
        before = self.state()
        with patch.object(self.char1, "save_profile", side_effect=RuntimeError("save")), self.assertRaises(RuntimeError):
            incinerator_service.incinerate(self.char1, "붕대")
        self.assertEqual(self.state(), before)


class NativeIncineratorTests(CredentialConfirmationCases, Phase5Test):
    """실제 Native Provider/Subject와 운영 Action·웹 Gateway 실행."""

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

    def test_numeric_ammo_names_keep_one_quantity_and_all_burn(self):
        for identity in ("ammo_9", "ammo_556", "ammo_762"):
            with self.subTest(ammo=identity):
                row = self.create(identity, quantity=8)
                name = ITEMS[identity]["name"]
                for suffix, remaining in (("", 7), (" 3개", 4)):
                    self.assertIn("소각했다", self.command(name + suffix + " 소각"))
                    row.refresh_from_db()
                    self.assertEqual(row.quantity, remaining)
                self.assertIn("소각했다", self.command(name + " 모두 소각"))
                self.assertFalse(ItemEntity.objects.filter(pk=row.pk).exists())

    def test_magazine_rounds_destroyed_and_loaded_firearm_rejected(self):
        firearm = create_firearm("guard_carbine", owner_object=self.char1, mode="full_standard")
        before = self.state()
        with self.assertRaisesRegex(rules.RuleError, "탄창을 먼저"):
            incinerator_service.incinerate(self.char1, "경비카빈")
        self.assertEqual(self.state(), before)
        unload_magazine(self.char1, firearm)
        credits = self.char1.profile()["credits"]
        self.assertIn("소각했다", self.command("카빈표준 소각"))
        self.assertFalse(ItemEntity.objects.filter(definition_id="ammo_556").exists())
        self.assertEqual(self.char1.profile()["credits"], credits)
        self.assertIn("소각했다", self.command("경비카빈 소각"))

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

    def test_web_confirmation_keeps_stable_credential_and_requires_server_token(self):
        from server.conf.primal_inputfuncs import pz_action
        from world.actions.room_npc_presentation import controls_for

        credential = credentials.grant_credential(self.char1, "outpost_supply_pass")
        controls = controls_for(self.char1, self.obj("incinerator"))
        control = next(row for row in controls if row["action"]["action_id"] == "incinerator.burn"
                       and row["action"]["roles"]["subject"][0]["identity"] == str(credential.pk))
        self.assertEqual(control["action"]["variant"], "normal")
        before = self.state()
        for quantity in ("1개", "2개", "모두"):
            payload = {**control["action"], "arguments": {"count": quantity},
                       "request_id": "credential-quantity-" + quantity}
            with patch.object(self.char1, "msg") as output:
                pz_action(self.session, payload)
            self.assertEqual(self.state(), before)
            self.assertFalse(any("pz_action_result" in call.kwargs for call in output.call_args_list))
        for forged in ({**control["action"], "confirmed": True},
                       {**control["action"], "variant": "confirmed"}):
            with patch.object(self.char1, "msg"):
                pz_action(self.session, {**forged, "request_id": "forged-" + str(len(forged))})
            self.assertEqual(self.state(), before)
        with patch.object(self.char1, "msg") as output:
            pz_action(self.session, {**control["action"], "request_id": "credential-prompt"})
        results = [call.kwargs["pz_action_result"][0][0]["action"]
                   for call in output.call_args_list if "pz_action_result" in call.kwargs]
        self.assertEqual(len(results), 1)
        confirmation = results[0]
        self.assertEqual(confirmation["roles"], control["action"]["roles"])
        self.assertEqual(confirmation["variant"], "confirmed")
        self.assertTrue(confirmation["confirmation_token"])
        self.assertEqual(self.state(), before)
        with patch.object(self.char1, "msg") as output:
            pz_action(self.session, {**confirmation, "request_id": "credential-confirmed"})
        self.assertEqual(sum("소각했다" in str(call.args[0]) for call in output.call_args_list if call.args), 1)
        self.assertFalse(ItemEntity.objects.filter(pk=credential.pk).exists())
        self.assertFalse(can_enter(self.char1, "outpost_weapon"))
        after = self.state()
        with patch.object(self.char1, "msg") as duplicate:
            pz_action(self.session, {**confirmation, "request_id": "credential-confirmed"})
        self.assertEqual(self.state(), after)
        self.assertFalse(any("소각했다" in str(call.args[0]) for call in duplicate.call_args_list if call.args))
