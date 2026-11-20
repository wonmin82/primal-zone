"""실제 동적 명령·웹 Gateway의 Root UUID 소비·장비 회귀."""

from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

from django.test import override_settings
from world import equipment_service
from world import text as ft
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

    def equipment_action(self, query, verb, expected_item):
        action, keyword = verb
        invocation = dispatch_text(self.char1, self.index, f"game.{action}", query, keyword)
        self.assertEqual(dict(invocation.roles)["subject"][0].identity, str(expected_item.pk))
        return execute(self.char1, self.session, invocation, self.index)

    def assert_equipment_message(self, result, sentence, label, description, verb):
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertTrue(result.changed)
        self.assertEqual(result.messages, (sentence,))
        message = result.messages[0]
        self.assertIsInstance(message, ft.Text)
        self.assertEqual(message.segments, [
            {"role": "item", "text": label},
            {"role": "text", "text": description},
            {"role": "success", "text": verb},
            {"role": "text", "text": "."},
        ])

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
        self.assertIn("입었다", self.raw(ITEMS[armor.definition_id]["name"] + " 입"))
        self.assertIn("벗었다", self.raw(ITEMS[armor.definition_id]["name"] + " 벗"))

    def test_equipment_slot_and_hand_role_golden_messages(self):
        cases = (
            ("folding_shield", "접이식방패 1", "들었다", "내려놓았다"),
            ("portable_analyzer", "휴대분석기 1", "장착했다", "해제했다"),
            ("security_goggles", "보안고글 1", "썼다", "벗었다"),
            ("expedition_tag", "탐사인식표 1", "걸었다", "벗었다"),
            ("light_protective_suit", "경량방호복 1", "입었다", "벗었다"),
            ("shock_absorbing_gloves", "충격흡수장갑 1", "꼈다", "벗었다"),
            ("emergency_belt", "응급벨트 1", "둘렀다", "풀었다"),
            ("reinforced_explorer_pants", "보강탐사바지 1", "입었다", "벗었다"),
            ("non_slip_boots", "미끄럼방지탐사화 1", "신었다", "벗었다"),
            ("focus_ring", "집중링 1", "꼈다", "뺐다"),
            ("survival_module", "생존모듈 1", "착용했다", "벗었다"),
        )
        weapon = self.create("explorer_machete")
        self.equipment_action("탐사용 벌목도 1", ("wield", "무장"), weapon)
        for identity, label, equip_verb, remove_verb in cases:
            with self.subTest(item=identity):
                row = self.create(identity)
                before = self.atomic_state()
                for command, location, verb in (
                    (("equip", "착용"), "equipment", equip_verb),
                    (("remove", "벗어"), "inventory", remove_verb),
                ):
                    result = self.equipment_action(label, command, row)
                    self.assert_equipment_message(result, f"{label}을 {verb}.", label, "을 ", verb)
                    row.refresh_from_db()
                    self.assertEqual(row.location_kind, location)
                    self.assertEqual(number_for(descriptor(row).reference), 1)
                self.assertEqual(self.atomic_state(), before)

    def test_numbered_weapon_messages_and_active_weapon_identity(self):
        first, second, third = (self.create("scout_pistol") for _ in range(3))
        identities = (first.pk, second.pk, third.pk)
        result = self.equipment_action("정찰권총 1", ("wield", "무장"), first)
        self.assert_equipment_message(result, "정찰권총 1로 무장했다.", "정찰권총 1", "로 ", "무장했다")
        self.assertEqual(self.char1.db.active_weapon_item_id, str(first.pk))
        for row, label, tool_particle, object_particle in (
            (second, "정찰권총 2", "로", "를"),
            (third, "정찰권총 3", "으로", "을"),
        ):
            with self.subTest(label=label):
                result = self.equipment_action(label, ("wield", "무장"), row)
                self.assert_equipment_message(result, f"{label}{tool_particle} 무장했다.",
                                              label, f"{tool_particle} ", "무장했다")
                self.assertEqual(equipment_service.hand_usage(self.char1), 2)
                self.assertEqual(self.char1.db.active_weapon_item_id, str(first.pk))
                row.refresh_from_db()
                self.assertEqual(row.location_kind, "equipment")
                self.assertEqual(equipment_service.selector_label(self.char1, row), label)
                result = self.equipment_action(label, ("active_weapon", "주무기"), row)
                self.assert_equipment_message(result, f"{label}{object_particle} 주무기로 지정했다.",
                                              label, f"{object_particle} 주무기로 ", "지정했다")
                self.assertEqual(self.char1.db.active_weapon_item_id, str(row.pk))
                result = self.equipment_action(label, ("unwield", "해제"), row)
                self.assert_equipment_message(result, f"{label}{object_particle} 해제했다.",
                                              label, f"{object_particle} ", "해제했다")
                self.assertEqual(self.char1.db.active_weapon_item_id, str(first.pk))
        result = self.equipment_action("정찰권총 1", ("unwield", "해제"), first)
        self.assert_equipment_message(result, "정찰권총 1을 해제했다.", "정찰권총 1", "을 ", "해제했다")
        self.assertIsNone(self.char1.db.active_weapon_item_id)
        for number, row, identity in zip(range(1, 4), (first, second, third), identities, strict=True):
            row.refresh_from_db()
            self.assertEqual((row.pk, row.location_kind, number_for(descriptor(row).reference)),
                             (identity, "inventory", number))

    def test_two_handed_weapon_refuses_shield_with_existing_error_and_no_mutation(self):
        weapon, shield = self.create("pioneer_spear"), self.create("folding_shield")
        result = self.equipment_action("개척창 1", ("wield", "무장"), weapon)
        self.assert_equipment_message(result, "개척창 1로 무장했다.", "개척창 1", "로 ", "무장했다")
        self.assertEqual(equipment_service.hand_usage(self.char1), 2)
        before = self.atomic_state()
        result = self.equipment_action("접이식방패 1", ("equip", "착용"), shield)
        self.assertEqual(result.status, ResultStatus.REFUSED)
        self.assertIn("손 장비 공간이 부족합니다. 먼저 기존 장비를 해제하세요.", result.messages[0])
        self.assertEqual(self.atomic_state(), before)
        result = self.equipment_action("개척창 1", ("unwield", "해제"), weapon)
        self.assert_equipment_message(result, "개척창 1을 해제했다.", "개척창 1", "을 ", "해제했다")

    def test_unsupported_equipment_operation_is_refused_before_changing_state(self):
        self.create("light_protective_suit")
        invocation = dispatch_text(self.char1, self.index, "game.equip", "경량방호복", "착용")
        original = self.index.bindings[invocation.action_id + ".binding"]
        invalid = replace(original, config=(("operation", "equipp"),))
        provider = original.provider_definition
        index = replace(
            self.index,
            bindings={**self.index.bindings, invalid.id: invalid},
            bindings_for_provider={
                **self.index.bindings_for_provider,
                provider: tuple(invalid if row == original else row for row in self.index.bindings_for_provider[provider]),
            },
        )
        before = self.atomic_state()
        with patch.object(equipment_service, "equip_item", wraps=equipment_service.equip_item) as equip:
            result = execute(self.char1, self.session, invocation, index)
        equip.assert_not_called()
        self.assertEqual(result.status, ResultStatus.REFUSED)
        self.assertEqual(result.messages, ("지원하지 않는 장비 행동입니다.",))
        self.assertEqual(self.atomic_state(), before)

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
