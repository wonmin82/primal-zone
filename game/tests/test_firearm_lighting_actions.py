"""운영 M04 선언을 실제 명령·웹 Gateway와 영속 UUID에 연결하는 회귀."""

from copy import deepcopy
from unittest.mock import patch

from django.test import override_settings
from world import firearm_service as guns
from world import recovery, rules
from world.actions.gateway import ResultStatus, execute, from_web
from world.actions.manifest import get_index
from world.actions.presentation import action_controls
from world.actions.resolver import dispatch_text, provided
from world.item_entities import api
from world.item_entities.models import ItemEntity
from world.selection_numbers.api import descriptor, number_for

from tests.item_entity_fixture import NativeItemTest


@override_settings(ACTION_CONTENT_PACKAGES=("world.actions.item_shared_content", "world.actions.firearm_lighting_content"))
class FirearmLightingActionsTests(NativeItemTest):
    def setUp(self):
        super().setUp()
        self.connect_character(self.char1)
        self.output = self.enterContext(patch.object(self.char1, "msg"))
        self.index = get_index()

    def raw(self, value):
        self.output.reset_mock()
        self.char1.execute_cmd(value, session=self.session)
        return " ".join(str(call.args[0]) for call in self.output.call_args_list if call.args)

    def gun(self, mode="no_mag", rounds=None):
        return guns.create_firearm("guard_carbine", owner_object=self.char1, mode=mode, rounds=rounds)

    def web(self, control, request="once"):
        invocation = from_web({**deepcopy(control["action"]), "request_id": request}, self.index)
        return execute(self.char1, self.session, invocation, self.index)

    def control(self, action, provider):
        return next(control for control in action_controls(self.char1, self.index, observed_at=100)
                    if control["action"]["action_id"] == "item_ops." + action
                    and control["action"]["roles"]["provider"][0]["identity"] == str(provider.pk))

    def test_registry_and_real_reload_best_magazine_once(self):
        gun = self.gun("empty")
        first = self.create("mag_556_standard", state={"rounds": 7})
        best = self.create("mag_556_extended", state={"rounds": 22})
        invocation = dispatch_text(self.char1, self.index, "game.reload", "경비카빈", "재장전")
        self.assertNotIn("source", dict(invocation.roles))
        recommendation = next(control for control in action_controls(self.char1, self.index, observed_at=100)
                              if control["label"].endswith(" · 재장전"))
        self.assertEqual(recommendation["action"]["action_id"], "item_ops.load")
        self.assertEqual(recommendation["action"]["roles"]["source"][0]["identity"], str(best.pk))
        before = number_for(descriptor(gun).reference)
        self.assertIn("재장전했다", self.raw("경비카빈 재장전"))
        self.assertEqual(guns.loaded_magazine_item(gun).pk, best.pk)
        self.assertEqual(number_for(descriptor(gun).reference), before)
        self.assertIn("현재 탄창을 유지", self.raw("경비카빈 재장전"))
        first.refresh_from_db()
        self.assertEqual(first.location_kind, "inventory")

    def test_explicit_magazine_uuid_web_and_repeat_dedup(self):
        from server.conf.primal_inputfuncs import pz_action

        gun = self.gun()
        magazine = self.create("mag_556_standard", state={"rounds": 9})
        control = self.control("load", gun)
        self.assertEqual(control["action"]["roles"]["source"][0]["identity"], str(magazine.pk))
        payload = {**deepcopy(control["action"]), "request_id": "load-one"}
        with patch.object(guns, "reload", wraps=guns.reload) as apply:
            pz_action(self.session, payload)
            pz_action(self.session, payload)
        self.assertEqual(apply.call_count, 1)
        self.assertEqual(guns.loaded_magazine_item(gun).pk, magazine.pk)
        self.assertEqual(guns.loaded_magazine_item(gun).state["rounds"], 9)

    def test_explicit_missing_source_does_not_auto_choose_other_magazine(self):
        gun = self.gun()
        first = self.create("mag_556_standard", state={"rounds": 9})
        second = self.create("mag_556_standard", state={"rounds": 10})
        control = self.control("load", gun)
        source = control["action"]["roles"]["source"][0]["identity"]
        api.delete_item(ItemEntity.objects.get(pk=source))
        before = self.atomic_state()
        self.assertEqual(self.web(control).status, ResultStatus.REFUSED)
        self.assertEqual(self.atomic_state(), before)
        del control["action"]["roles"]["source"]
        self.assertEqual(self.web(control, "missing-source").status, ResultStatus.REFUSED)
        self.assertEqual(self.atomic_state(), before)
        self.assertIsNone(guns.loaded_magazine_item(gun))
        self.assertTrue(ItemEntity.objects.filter(pk=first.pk if str(second.pk) == source else second.pk).exists())

    def test_root_fill_and_inside_fill_have_typed_parent_and_single_effect(self):
        gun = self.gun("empty")
        magazine = guns.loaded_magazine_item(gun)
        source = self.create("ammo_556", quantity=5)
        invocation = dispatch_text(self.char1, self.index, "game.fill", "카빈표준", "채워")
        self.assertEqual(dict(invocation.roles)["source"][0].kind, "inventory")
        self.assertEqual(dict(invocation.roles)["source"][0].identity, str(self.char1.pk))
        self.assertEqual(invocation.action_id, "item_ops.inside_fill")
        self.assertEqual(dict(invocation.roles)["provider"][0].identity, str(gun.pk))
        self.assertEqual(dict(invocation.roles)["subject"][0].identity, str(magazine.pk))
        self.assertEqual(dict(invocation.roles)["subject"][0].scope_id, f"inside:{gun.pk}")
        self.assertIn("5발", self.raw("카빈표준 채워"))
        magazine.refresh_from_db()
        self.assertEqual(magazine.state["rounds"], 5)
        self.assertFalse(ItemEntity.objects.filter(pk=source.pk).exists())
        offered_ids = {reference.identity for reference, _binding in provided(self.char1, self.index)}
        self.assertNotIn(str(magazine.pk), offered_ids)
        self.assertIn("5발", self.raw("카빈표준에서 카빈탄 꺼내"))
        magazine.refresh_from_db()
        self.assertEqual(magazine.state["rounds"], 0)
        self.assertEqual(ItemEntity.objects.get(definition_id="ammo_556", owner_object=self.char1).quantity, 5)
        self.assertIn("탄창을 꺼냈다", self.raw("경비카빈에서 탄창 꺼내"))
        magazine.refresh_from_db()
        self.assertEqual(magazine.location_kind, "inventory")
        self.assertIn("5발", self.raw("카빈표준에 카빈탄 넣어"))

    def test_stale_inside_web_cannot_remove_replacement_magazine(self):
        gun = self.gun("partial", 3)
        original = guns.loaded_magazine_item(gun)
        control = self.control("magazine_remove", gun)
        replacement = self.create("mag_556_standard", state={"rounds": 8})
        guns.reload(self.char1, gun, replacement)
        before = self.atomic_state()
        self.assertEqual(self.web(control).status, ResultStatus.REFUSED)
        self.assertEqual(self.atomic_state(), before)
        self.assertEqual(guns.loaded_magazine_item(gun).pk, replacement.pk)
        original.refresh_from_db()
        self.assertEqual(original.location_kind, "inventory")

    def test_light_power_uuid_consumption_and_projection_has_no_effect(self):
        from server.conf.primal_inputfuncs import pz_action

        light = self.create("flashlight")
        battery = self.create("battery", quantity=2)
        control = self.control("power_insert", light)
        self.assertEqual(control["action"]["roles"]["source"][0]["identity"], str(battery.pk))
        payload = {**deepcopy(control["action"]), "request_id": "power-one"}
        from world import lighting_service
        with patch.object(lighting_service, "insert_power", wraps=lighting_service.insert_power) as apply:
            pz_action(self.session, payload)
            pz_action(self.session, payload)
        self.assertEqual(apply.call_count, 1)
        battery.refresh_from_db()
        self.assertEqual(battery.quantity, 1)
        self.assertIn("켰다", self.raw("손전등 켜"))
        light.refresh_from_db()
        self.assertTrue(light.state["enabled"])
        before = self.atomic_state()
        controls = action_controls(self.char1, self.index, observed_at=105)
        action_controls(self.char1, self.index, observed_at=110)
        self.assertEqual(self.atomic_state(), before)
        self.assertEqual(self.char1.db.active_light_item_id, str(light.pk))
        self.assertTrue(any(c["action"]["action_id"] == "item_ops.light_off" for c in controls))
        self.assertIn("켜짐", self.raw("손전등 확인"))
        self.assertIn("껐다", self.raw("손전등 꺼"))
        light.refresh_from_db()
        self.assertFalse(light.state["enabled"])

    def test_remote_storage_and_foreign_power_are_refused_without_effect(self):
        light = self.create("flashlight")
        battery = self.create("battery")
        control = self.control("power_insert", light)
        api.move_item_tree(battery, location_kind="personal_storage", owner_object=self.char1)
        before = self.atomic_state()
        self.assertEqual(self.web(control).status, ResultStatus.REFUSED)
        self.assertEqual(self.atomic_state(), before)
        self.assertNotIn("전원 하나를 넣었다", self.raw("손전등에 건전지 넣어"))
        self.assertEqual(self.atomic_state(), before)

    def test_combat_reload_consumes_one_opportunity_and_fill_refusal_no_effect(self):
        self.gun("empty")
        self.create("mag_556_standard", state={"rounds": 8})
        ammo = self.create("ammo_556", quantity=4)
        self.char1.change(lambda p: p.update(combat_target=123, next_attack_at=100))
        with patch("world.firearm_service.time", return_value=100):
            self.assertIn("재장전했다", self.raw("경비카빈 재장전"))
        self.assertGreater(self.char1.profile()["next_attack_at"], 100)
        before = self.atomic_state()
        self.assertNotIn("발을 넣었다", self.raw("카빈표준 채워"))
        self.assertEqual(self.atomic_state(), before)
        ammo.refresh_from_db()
        self.assertEqual(ammo.quantity, 4)

    def test_shared_verbs_and_normalized_ammo_names_keep_exact_source(self):
        magazine = self.create("mag_556_standard")
        source = self.create("ammo_556", quantity=4)
        wrong = self.create("ammo_9", quantity=8)
        before = self.atomic_state()
        self.assertNotIn("발을 넣었다", self.raw("카빈표준에 권총탄 넣어"))
        self.assertEqual(self.atomic_state(), before)
        self.assertIn("4발", self.raw("카빈표준에 카빈탄 store"))
        self.assertFalse(ItemEntity.objects.filter(pk=source.pk).exists())
        wrong.refresh_from_db()
        self.assertEqual(wrong.quantity, 8)
        self.assertIn("4발", self.raw("카빈표준에서 5.56mm카빈탄 retrieve"))
        magazine.refresh_from_db()
        self.assertEqual(magazine.state["rounds"], 0)

    def test_light_gap_label_is_stable_and_stale_provider_fails(self):
        first = self.create("flashlight")
        second = self.create("flashlight")
        control = self.control("light_status", second)
        self.assertIn("탐사용손전등 2", control["label"])
        api.delete_item(first)
        after = self.control("light_status", second)
        self.assertIn("탐사용손전등 2", after["label"])
        self.assertEqual(control["action"]["roles"], after["action"]["roles"])
        api.move_item_tree(second, location_kind="personal_storage", owner_object=self.char1)
        before = self.atomic_state()
        self.assertEqual(self.web(control).status, ResultStatus.REFUSED)
        self.assertEqual(self.atomic_state(), before)

    def test_inside_parent_scope_disambiguates_same_root_name_and_number(self):
        gun = self.gun("empty")
        inside = guns.loaded_magazine_item(gun)
        root = self.create("mag_556_standard")
        self.create("ammo_556", quantity=4)
        self.assertEqual(number_for(descriptor(inside).reference), 1)
        self.assertEqual(number_for(descriptor(root).reference), 1)
        before = self.atomic_state()
        self.assertNotIn("발을 넣었다", self.raw("카빈표준 1 채워"))
        self.assertEqual(self.atomic_state(), before)
        invocation = dispatch_text(self.char1, self.index, "game.fill", "경비카빈의 카빈표준 1", "채워")
        self.assertEqual(dict(invocation.roles)["provider"][0].identity, str(gun.pk))
        self.assertEqual(dict(invocation.roles)["subject"][0].identity, str(inside.pk))
        self.assertIn("4발", self.raw("경비카빈의 카빈표준 1 채워"))
        root.refresh_from_db()
        inside.refresh_from_db()
        self.assertEqual(root.state["rounds"], 0)
        self.assertEqual(inside.state["rounds"], 4)

    def test_fill_text_and_single_web_button_consume_all_compatible_stacks(self):
        text_magazine = self.create("mag_556_standard")
        self.create("ammo_556", quantity=2)
        self.create("ammo_556", quantity=3)
        self.assertIn("5발", self.raw("카빈표준 1 채워"))
        text_magazine.refresh_from_db()
        self.assertEqual(text_magazine.state["rounds"], 5)
        web_magazine = self.create("mag_556_standard")
        first = self.create("ammo_556", quantity=2)
        second = self.create("ammo_556", quantity=3)
        controls = [control for control in action_controls(self.char1, self.index, observed_at=100)
                    if control["action"]["action_id"] == "item_ops.fill"
                    and control["action"]["roles"]["provider"][0]["identity"] == str(web_magazine.pk)]
        self.assertEqual(len(controls), 1)
        control = controls[0]
        self.assertEqual(control["action"]["roles"]["source"], [
            {"kind": "inventory", "identity": str(self.char1.pk), "scope_id": f"inventory:{self.char1.pk}"}])
        with patch.object(guns, "load_ammo", wraps=guns.load_ammo) as apply:
            self.assertEqual(self.web(control).status, ResultStatus.SUCCESS)
        self.assertEqual(apply.call_count, 1)
        self.assertIsNone(apply.call_args.args[2])
        web_magazine.refresh_from_db()
        self.assertEqual(web_magazine.state["rounds"], text_magazine.state["rounds"])
        self.assertFalse(ItemEntity.objects.filter(pk__in=[first.pk, second.pk]).exists())

    def test_fill_thirty_three_stacks_uses_one_inventory_reference(self):
        gun = self.gun("empty")
        magazine = guns.loaded_magazine_item(gun)
        for _index in range(33):
            self.create("ammo_556", quantity=1)
        control = self.control("inside_fill", gun)
        self.assertEqual(len(control["action"]["roles"]["source"]), 1)
        self.assertEqual(control["action"]["roles"]["subject"][0]["identity"], str(magazine.pk))
        self.assertEqual(self.web(control).status, ResultStatus.SUCCESS)
        magazine.refresh_from_db()
        self.assertEqual(magazine.state["rounds"], 20)
        self.assertEqual(sum(ItemEntity.objects.filter(owner_object=self.char1, definition_id="ammo_556")
                             .values_list("quantity", flat=True)), 13)

    def test_fill_stale_quantity_split_and_replacement_reject_without_effect(self):
        magazine = self.create("mag_556_standard")
        source = self.create("ammo_556", quantity=5)
        control = self.control("fill", magazine)
        source.quantity = 4
        source.save()
        before = self.atomic_state()
        self.assertEqual(self.web(control, "quantity-changed").status, ResultStatus.REFUSED)
        self.assertEqual(self.atomic_state(), before)
        control = self.control("fill", magazine)
        api.split_stack(source, 1)
        before = self.atomic_state()
        self.assertEqual(self.web(control, "split-changed").status, ResultStatus.REFUSED)
        self.assertEqual(self.atomic_state(), before)
        control = self.control("fill", magazine)
        for row in list(ItemEntity.objects.filter(owner_object=self.char1, definition_id="ammo_556")):
            api.delete_item(row)
        self.create("ammo_556", quantity=4)
        before = self.atomic_state()
        self.assertEqual(self.web(control, "replacement-changed").status, ResultStatus.REFUSED)
        self.assertEqual(self.atomic_state(), before)

    def test_fill_foreign_inventory_reference_is_rejected(self):
        magazine = self.create("mag_556_standard")
        self.create("ammo_556", quantity=5)
        control = self.control("fill", magazine)
        control["action"]["roles"]["source"] = [
            {"kind": "inventory", "identity": str(self.char2.pk), "scope_id": f"inventory:{self.char2.pk}"}]
        before = self.atomic_state()
        self.assertEqual(self.web(control).status, ResultStatus.REFUSED)
        self.assertEqual(self.atomic_state(), before)
        del control["action"]["roles"]["source"]
        self.assertEqual(self.web(control, "missing-fill-source").status, ResultStatus.REFUSED)
        self.assertEqual(self.atomic_state(), before)

    def test_reload_elapsed_recovery_and_text_prompt_complete_once(self):
        self.gun("empty")
        self.create("mag_556_standard", state={"rounds": 7})
        before = self.char1.profile_snapshot()
        now = 100 + 6 * recovery.RECOVERY_INTERVAL + 1
        with (patch("typeclasses.explorers.time", return_value=now),
              patch("world.firearm_service.time", return_value=now),
              patch.object(self.char1, "push_prompt", wraps=self.char1.push_prompt) as prompt):
            self.assertIn("재장전했다", self.raw("경비카빈 재장전"))
        after = self.char1.profile_snapshot()
        for resource in recovery.RESOURCES:
            self.assertGreater(after[resource], before[resource])
        self.assertEqual(after["recovery"]["updated_at"], now)
        prompt.assert_called_once()

    def test_light_status_web_elapsed_recovery_prompt_and_request_dedup(self):
        from server.conf.primal_inputfuncs import pz_action

        light = self.create("flashlight")
        control = self.control("light_status", light)
        before = self.char1.profile_snapshot()
        now = 100 + 6 * recovery.RECOVERY_INTERVAL + 1
        payload = {**deepcopy(control["action"]), "request_id": "status-recovery"}
        with (patch("typeclasses.explorers.time", return_value=now),
              patch.object(self.char1, "push_prompt", wraps=self.char1.push_prompt) as prompt):
            pz_action(self.session, payload)
            after = self.char1.profile_snapshot()
            pz_action(self.session, payload)
        for resource in recovery.RESOURCES:
            self.assertGreater(after[resource], before[resource])
        self.assertEqual(self.char1.profile_snapshot(), after)
        self.assertEqual(after["recovery"]["updated_at"], now)
        prompt.assert_called_once()

    def test_loading_current_inside_magazine_is_noop_even_when_empty(self):
        gun = self.gun("empty")
        current = guns.loaded_magazine_item(gun)
        invocation = dispatch_text(self.char1, self.index, "game.load", "경비카빈에 카빈표준", "장전")
        selected = dict(invocation.roles)["source"][0]
        self.assertEqual((selected.identity, selected.scope_id), (str(current.pk), f"inside:{gun.pk}"))
        before = self.atomic_state()
        self.assertIn("현재 탄창을 유지한다", self.raw("경비카빈에 카빈표준 장전"))
        self.assertEqual(self.atomic_state(), before)
        self.assertEqual(guns.loaded_magazine_item(gun).pk, current.pk)

    def test_current_magazine_name_default_preserves_legacy_sequence_and_combat_cost_zero(self):
        gun = self.gun("partial", 3)
        current = guns.loaded_magazine_item(gun)
        replacement = self.create("mag_556_standard", state={"rounds": 9})
        self.char1.change(lambda profile: profile.update(combat_target=123, next_attack_at=100))
        invocation = dispatch_text(self.char1, self.index, "game.load", "경비카빈에 카빈표준", "장전")
        self.assertEqual(dict(invocation.roles)["source"][0].identity, str(current.pk))
        self.assertLess(current.sequence, replacement.sequence)
        before = self.atomic_state()
        with patch("world.firearm_service.time", return_value=100):
            self.assertIn("현재 탄창을 유지한다", self.raw("경비카빈에 카빈표준 장전"))
        self.assertEqual(self.atomic_state(), before)
        self.assertEqual(self.char1.profile()["next_attack_at"], 100)
        self.assertEqual(guns.loaded_magazine_item(gun).pk, current.pk)
        replacement.refresh_from_db()
        self.assertEqual(replacement.location_kind, "inventory")

    def test_web_current_inside_magazine_uuid_is_noop_with_single_prompt(self):
        from server.conf.primal_inputfuncs import pz_action

        gun = self.gun("empty")
        current = guns.loaded_magazine_item(gun)
        control = next(control for control in action_controls(self.char1, self.index, observed_at=100)
                       if control["action"]["action_id"] == "item_ops.load"
                       and control["action"]["roles"]["source"][0]["identity"] == str(current.pk))
        self.assertEqual(control["action"]["roles"]["source"][0]["scope_id"], f"inside:{gun.pk}")
        self.assertIn("현재 삽입", control["label"])
        before = self.atomic_state()
        payload = {**deepcopy(control["action"]), "request_id": "current-magazine-noop"}
        with (patch.object(self.char1, "push_prompt", wraps=self.char1.push_prompt) as prompt,
              patch.object(guns, "reload", wraps=guns.reload) as apply):
            pz_action(self.session, payload)
        prompt.assert_called_once()
        self.assertEqual(apply.call_count, 1)
        self.assertEqual(apply.call_args.args[2].pk, current.pk)
        self.assertEqual(self.atomic_state(), before)

    def test_stale_inside_load_source_and_other_gun_child_are_rejected(self):
        gun = self.gun("partial", 3)
        current = guns.loaded_magazine_item(gun)
        control = next(control for control in action_controls(self.char1, self.index, observed_at=100)
                       if control["action"]["action_id"] == "item_ops.load"
                       and control["action"]["roles"]["source"][0]["identity"] == str(current.pk))
        guns.unload_magazine(self.char1, gun)
        before = self.atomic_state()
        with patch.object(guns, "reload", wraps=guns.reload) as apply:
            self.assertEqual(self.web(control, "unloaded-source").status, ResultStatus.REFUSED)
        apply.assert_not_called()
        self.assertEqual(self.atomic_state(), before)
        other_gun = self.gun("partial", 8)
        other_child = guns.loaded_magazine_item(other_gun)
        control["action"]["roles"]["source"] = [{"kind": "item", "identity": str(other_child.pk),
                                                    "scope_id": f"inside:{other_gun.pk}"}]
        before = self.atomic_state()
        self.assertEqual(self.web(control, "other-gun-child").status, ResultStatus.REFUSED)
        self.assertEqual(self.atomic_state(), before)

    def test_explicit_number_collision_across_root_and_inside_is_not_first_wins(self):
        gun = self.gun("partial", 3)
        current = guns.loaded_magazine_item(gun)
        replacement = self.create("mag_556_standard", state={"rounds": 9})
        self.assertEqual(number_for(descriptor(current).reference), 1)
        self.assertEqual(number_for(descriptor(replacement).reference), 1)
        with self.assertRaises(rules.RuleError):
            dispatch_text(self.char1, self.index, "game.load", "경비카빈에 카빈표준 1", "장전")
        before = self.atomic_state()
        self.assertNotIn("탄창을 장전했다", self.raw("경비카빈에 카빈표준 1 장전"))
        self.assertEqual(self.atomic_state(), before)
