"""실제 동적 명령·웹 Gateway의 Root UUID 소비·장비 회귀."""

from copy import deepcopy
from unittest.mock import patch

from django.test import override_settings
from world.actions.gateway import ResultStatus, execute, from_web
from world.actions.manifest import get_index
from world.actions.presentation import action_controls
from world.actions.resolver import dispatch_text
from world.item_entities import api
from world.item_entities.models import ItemEntity
from world.selection_numbers.api import descriptor, number_for

from tests.item_entity_fixture import NativeItemTest


@override_settings(ACTION_CONTENT_PACKAGES=("world.actions.item_equipment_content",))
class ItemEquipmentActionsTests(NativeItemTest):
    def setUp(self):
        super().setUp()
        self.session.puppet = self.char1
        self.session.logged_in = True
        self.char1.sessions.add(self.session)
        self.index = get_index()
        self.output = self.enterContext(patch.object(self.char1, "msg"))

    def raw(self, value):
        self.output.reset_mock()
        self.char1.execute_cmd(value, session=self.session)
        return " ".join(str(call.args[0]) for call in self.output.call_args_list if call.args)

    def test_bandage_number_consumes_selected_stack_only(self):
        first = self.create("bandage", quantity=2)
        second = self.create("bandage", quantity=3)
        self.char1.change(lambda p: p.update(hp=1))
        invocation = dispatch_text(self.char1, self.index, "game.use", "붕대 2", "사용")
        self.assertEqual(dict(invocation.roles)["subject"][0].identity, str(second.pk))
        self.assertIn("회복", self.raw("붕대 2 사용"))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.quantity, second.quantity), (2, 2))
        self.assertEqual(number_for(descriptor(second).reference), 2)

    def test_wrong_equipment_verbs_refuse_with_correct_hint_and_no_effect_or_control(self):
        self.create("cutting_machete")
        self.create("reinforced_vest")
        for query, verb, key, hint in (("절단마체테", "equip", "착용", "절단마체테 무장"),
                                       ("절단마체테", "remove", "벗어", "절단마체테 해제"),
                                       ("강화방호조끼", "wield", "무장", "강화방호조끼 착용"),
                                       ("강화방호조끼", "unwield", "해제", "강화방호조끼 벗어")):
            with self.subTest(verb=key):
                before = self.atomic_state()
                self.assertIn(hint, self.raw(query + " " + key))
                invocation = dispatch_text(self.char1, self.index, "game." + verb, query, key)
                self.assertIn(".advise_", invocation.action_id)
                result = execute(self.char1, self.session, invocation, self.index)
                self.assertEqual(result.status, ResultStatus.REFUSED)
                self.assertEqual(self.atomic_state(), before)
        self.assertFalse(any(".advise_" in control["action"]["action_id"]
                             for control in action_controls(self.char1, self.index)))

    def test_food_number_and_explicit_quantity_do_not_consume_other_stack(self):
        first = self.create("field_ration", quantity=2)
        second = self.create("field_ration", quantity=2)
        self.char1.change(lambda p: p.update(hp=1))
        self.assertIn("먹었다", self.raw("야전식량 2 1개 eat"))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.quantity, second.quantity), (2, 1))
        before = self.atomic_state()
        self.raw("야전식량 2 2개 먹어")
        self.assertEqual(self.atomic_state(), before)
        self.raw("야전식량 모두 먹어")
        self.assertEqual(self.atomic_state(), before)

    def test_stale_web_item_does_not_fall_back_to_same_definition(self):
        first = self.create("bandage", quantity=1)
        second = self.create("bandage", quantity=2)
        self.char1.change(lambda p: p.update(hp=1))
        control = next(c for c in action_controls(self.char1, self.index)
                       if c["action"]["action_id"] == "item.bandage.use"
                       and c["action"]["roles"]["provider"][0]["identity"] == str(first.pk))
        api.delete_item(first, operation="consume")
        before = self.atomic_state()
        result = execute(self.char1, self.session, from_web({**control["action"], "request_id": "stale-item"}, self.index), self.index)
        self.assertEqual(result.status, ResultStatus.REFUSED)
        self.assertEqual(self.atomic_state(), before)
        self.assertTrue(ItemEntity.objects.filter(pk=second.pk, quantity=2).exists())

    def test_equipment_real_aliases_and_stable_active_weapon(self):
        weapon = self.create("explorer_machete")
        armor = self.create("expedition_workwear")
        from world.content import ITEMS

        name = ITEMS[weapon.definition_id]["name"]
        self.assertIn("무장했다", self.raw(name + " wield"))
        weapon.refresh_from_db()
        self.assertEqual(weapon.location_kind, "equipment")
        self.raw(name + " 주무기")
        self.assertEqual(self.char1.db.active_weapon_item_id, str(weapon.pk))
        self.assertIn("해제했다", self.raw(name + " unwield"))
        # 표시 이름은 실제 콘텐츠 정의에 따라 선택한다.
        self.assertIn("착용했다", self.raw(ITEMS[armor.definition_id]["name"] + " 입"))
        self.assertIn("벗었다", self.raw(ITEMS[armor.definition_id]["name"] + " 벗"))

    def test_information_has_no_state_change_and_uses_number(self):
        self.create("bandage", quantity=1)
        second = self.create("bandage", quantity=3)
        before = self.atomic_state()
        output = self.raw("붕대 2 정보")
        self.assertIn("수량 3", output)
        self.assertIn("붕대 2", output)
        self.assertEqual(self.atomic_state(), before)
        control = next(c for c in action_controls(self.char1, self.index)
                       if c["action"]["action_id"] == "item.bandage.information"
                       and c["action"]["roles"]["provider"][0]["identity"] == str(second.pk))
        self.assertEqual(control["label"], "붕대 2 정보")

    def test_combat_queue_retains_uuid_and_missing_stack_is_not_substituted(self):
        from world import rules
        from world.item_inventory import bind_consumption

        first = self.create("bandage", quantity=1)
        second = self.create("bandage", quantity=2)
        self.char1.change(lambda p: p.update(hp=1, combat_target=123))
        self.assertIn("다음 차례", self.raw("붕대 2 사용"))
        self.assertEqual(self.char1.profile()["queued_item_id"], str(second.pk))
        api.delete_item(second, operation="consume")
        profile = self.char1.profile()
        self.assertFalse(bind_consumption(self.char1, profile, "bandage", profile.pop("queued_item_id")))
        damage, outcome = rules.player_attack(profile, "scavenger", 100, 2.5)
        self.assertEqual((damage, outcome["action"]), (0, "error"))
        self.char1.save_profile(profile)
        first.refresh_from_db()
        self.assertEqual(first.quantity, 1)

    def test_actual_combat_boundary_consumes_queued_uuid_once(self):
        from world.firearm_service import player_attack

        first = self.create("bandage", quantity=2)
        second = self.create("bandage", quantity=3)
        self.char1.change(lambda p: p.update(hp=1, combat_target=123))
        self.raw("붕대 2 사용")
        profile = self.char1.profile()
        damage, outcome = player_attack(self.char1, profile, "scavenger", 100, 2.5)
        self.assertEqual((damage, outcome["action"]), (0, "bandage"))
        self.char1.save_profile(profile)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.quantity, second.quantity), (2, 2))
        self.assertNotIn("queued_item_id", self.char1.profile())

    def test_web_request_duplicate_applies_exactly_once(self):
        from server.conf.primal_inputfuncs import pz_action

        item = self.create("water", quantity=3)
        self.char1.change(lambda p: p.update(hp=1))
        control = next(c for c in action_controls(self.char1, self.index)
                       if c["action"]["action_id"] == "item.water.drink")
        payload = deepcopy(control["action"])
        payload["request_id"] = "drink-once"
        pz_action(self.session, payload)
        after = self.atomic_state()
        pz_action(self.session, payload)
        self.assertEqual(self.atomic_state(), after)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

    def test_loaded_magazine_information_uses_root_provider_and_is_read_only(self):
        from world import firearm_service as guns

        gun = guns.create_firearm("guard_carbine", owner_object=self.char1, mode="partial", rounds=7)
        magazine = guns.loaded_magazine_item(gun)
        before = self.atomic_state()
        for query in ("카빈표준", "경비카빈의 카빈표준 1"):
            invocation = dispatch_text(self.char1, self.index, "game.information", query, "정보")
            self.assertEqual(dict(invocation.roles)["provider"][0].identity, str(gun.pk))
            self.assertEqual(dict(invocation.roles)["subject"][0].identity, str(magazine.pk))
            self.assertEqual(dict(invocation.roles)["subject"][0].scope_id, f"inside:{gun.pk}")
            self.assertIn("잔탄 7발", self.raw(query + " 정보"))
        self.assertEqual(self.atomic_state(), before)
        controls = action_controls(self.char1, self.index)
        child = next(c for c in controls if c["action"]["action_id"] == "item.inside_information.mag_556_standard")
        self.assertEqual(child["action"]["roles"]["provider"][0]["identity"], str(gun.pk))
        self.assertEqual(child["action"]["roles"]["subject"][0]["identity"], str(magazine.pk))
        self.assertFalse(any(c["action"]["roles"]["provider"][0]["identity"] == str(magazine.pk) for c in controls))
        result = execute(self.char1, self.session,
                         from_web({**child["action"], "request_id": "inside-info-success"}, self.index), self.index)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertIn("잔탄 7발", str(result.messages))
        self.assertEqual(self.atomic_state(), before)

    def test_root_and_inside_same_name_information_is_ambiguous_without_parent(self):
        from world import firearm_service as guns
        from world.rules import RuleError

        gun = guns.create_firearm("guard_carbine", owner_object=self.char1, mode="partial", rounds=7)
        magazine = guns.loaded_magazine_item(gun)
        self.create("mag_556_standard", state={"rounds": 2})
        before = self.atomic_state()
        with self.assertRaises(RuleError):
            dispatch_text(self.char1, self.index, "game.information", "카빈표준", "정보")
        invocation = dispatch_text(self.char1, self.index, "game.information", "경비카빈의 카빈표준", "정보")
        self.assertEqual(dict(invocation.roles)["subject"][0].identity, str(magazine.pk))
        self.assertIn("잔탄 7발", self.raw("경비카빈의 카빈표준 정보"))
        self.assertEqual(self.atomic_state(), before)

    def test_inside_information_stale_after_unload_or_parent_move_refuses_without_effect(self):
        from world import firearm_service as guns

        gun = guns.create_firearm("guard_carbine", owner_object=self.char1, mode="partial", rounds=7)
        magazine = guns.loaded_magazine_item(gun)
        control = next(c for c in action_controls(self.char1, self.index)
                       if c["action"]["action_id"] == "item.inside_information.mag_556_standard")
        payload = {**control["action"], "request_id": "inside-info-unload"}
        guns.unload_magazine(self.char1, gun)
        before = self.atomic_state()
        self.assertEqual(execute(self.char1, self.session, from_web(payload, self.index), self.index).status, ResultStatus.REFUSED)
        self.assertEqual(self.atomic_state(), before)
        guns.reload(self.char1, gun, magazine)
        control = next(c for c in action_controls(self.char1, self.index)
                       if c["action"]["action_id"] == "item.inside_information.mag_556_standard")
        payload = {**control["action"], "request_id": "inside-info-owner"}
        api.move_item_tree(gun, location_kind="inventory", owner_object=self.char2, operation="give")
        before = self.atomic_state()
        self.assertEqual(execute(self.char1, self.session, from_web(payload, self.index), self.index).status, ResultStatus.REFUSED)
        self.assertEqual(self.atomic_state(), before)
