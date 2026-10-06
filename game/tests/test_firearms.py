"""탄창 SSOT·교체·탄약·발사·실패 원자성을 격리 DB에서 검증한다."""

from copy import deepcopy
from random import Random
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from world import equipment_service as equipment
from world import firearm_service as service
from world import recovery, rules
from world.item_entities import api
from world.item_entities.models import ItemEntity
from world.multiplayer import world_change

from tests.item_entity_fixture import NativeItemTest


class FirearmTests(NativeItemTest):
    def gun(self, mode="no_mag", **kwargs):
        return service.create_firearm("test_pistol", owner_object=self.char1, mode=mode, **kwargs)

    def mag(self, rounds=0, identity="mag_9_standard"):
        return self.create(identity, state={"rounds": rounds})

    def combat_profile(self, action="attack"):
        profile = self.char1.profile()
        profile.update(combat_target=123, queued_action=action, next_attack_at=100)
        self.char1.save_profile(profile)
        return self.char1.profile()

    def test_noncombat_reload_reconciles_elapsed_command_boundary(self):
        gun = self.gun("empty")
        magazine = self.mag(12)
        before = self.char1.profile_snapshot()
        now = 100 + 6 * recovery.RECOVERY_INTERVAL + 1
        with patch("typeclasses.explorers.time", return_value=now), patch("world.firearm_service.time", return_value=now):
            self.char1.execute_cmd("시험권총 재장전")
        after = self.char1.profile_snapshot()
        self.assertEqual(service.loaded_magazine_item(gun).pk, magazine.pk)
        for resource in recovery.RESOURCES:
            self.assertGreater(after[resource], before[resource])
        self.assertEqual(after["recovery"]["updated_at"], now)
        self.assertEqual(after["skill_ready_at"], before["skill_ready_at"])
        self.assertEqual(after["player_round"], before["player_round"])

    def test_acquisition_all_modes_and_rollback_sequence(self):
        for mode, rounds in (("full_standard", None), ("empty", None), ("partial", 7), ("no_mag", None)):
            with self.subTest(mode=mode):
                gun = self.gun(mode, rounds=rounds)
                magazine = service.loaded_magazine_item(gun)
                if mode == "no_mag":
                    self.assertIsNone(magazine)
                else:
                    self.assertEqual((magazine.location_kind, magazine.parent_item_id, magazine.socket),
                                     ("inside", gun.pk, "magazine"))
                    self.assertEqual(magazine.state["rounds"], 12 if mode == "full_standard" else rounds or 0)
                self.assertEqual(gun.state, {})
        before = self.atomic_state()
        original = api.create_item
        with patch.object(api, "create_item", wraps=api.create_item) as create:

            def fail_mag(identity, **kwargs):
                if identity.startswith("mag_"):
                    raise ValidationError("탄창 생성 실패")
                return original(identity, **kwargs)

            create.side_effect = fail_mag
            with self.assertRaises(rules.RuleError):
                self.gun("full_standard")
        self.assertEqual(before, self.atomic_state())

    def test_rounds_validation_nonstack_ammo_stack_family_and_single_socket(self):
        gun = self.gun("full_standard")
        for rounds in (-1, 13, True, 1.5):
            with self.subTest(rounds=rounds), self.assertRaises(ValidationError):
                self.mag(rounds)
        with self.assertRaises(ValidationError):
            self.create("mag_9_standard", quantity=2)
        self.assertEqual(self.create("ammo_9", quantity=5).quantity, 5)
        for definition in ("mag_9_standard", "mag_556_standard"):
            before = self.atomic_state()
            with self.assertRaises(ValidationError):
                api.create_item(definition, location_kind="inside", parent_item=gun, socket="magazine")
            self.assertEqual(before, self.atomic_state())
        # raw insert도 magazine socket 두 칸을 만들 수 없다. generic 다른 socket은 제한하지 않는다.
        with self.assertRaises(IntegrityError), world_change():
            ItemEntity.objects.bulk_create([ItemEntity(definition_id="mag_9_standard", sequence=999999,
                location_kind="inside", parent_item=gun, socket="magazine", state={"rounds": 0})])
        magazine = service.loaded_magazine_item(gun)
        with self.assertRaises(ValidationError):
            api.update_item_state(gun, {"rounds": 12})
        self.assertEqual(magazine.state["rounds"], 12)

    def test_auto_reload_highest_rounds_sequence_and_noop(self):
        gun = self.gun("partial", rounds=7)
        first, second = self.mag(12), self.mag(12)
        self.assertTrue(service.reload(self.char1, gun, now=100))
        self.assertEqual(service.loaded_magazine_item(gun).pk, first.pk)
        before = self.atomic_state()
        self.assertFalse(service.reload(self.char1, gun, now=100))
        self.assertEqual(before, self.atomic_state())
        extended = self.mag(18, "mag_9_extended")
        self.assertTrue(service.reload(self.char1, gun, now=100))
        self.assertEqual(service.loaded_magazine_item(gun).pk, extended.pk)
        for row in (first, second):
            row.refresh_from_db()
            self.assertEqual((row.location_kind, row.state["rounds"]), ("inventory", 12))

    def test_reload_empty_missing_incompatible_foreign_and_explicit(self):
        gun = self.gun()
        for setup in (lambda: None, lambda: self.mag(0), lambda: self.mag(5, "mag_556_standard")):
            setup()
            before = self.atomic_state()
            with self.assertRaises(rules.RuleError):
                service.reload(self.char1, gun)
            self.assertEqual(before, self.atomic_state())
        incompatible = self.mag(5, "mag_556_standard")
        with self.assertRaises(rules.RuleError):
            service.reload(self.char1, gun, incompatible)
        magazine = self.mag(1)
        self.assertTrue(service.reload(self.char1, gun, magazine))
        self.assertEqual(service.loaded_magazine_item(gun).pk, magazine.pk)
        before = self.atomic_state()
        self.assertFalse(service.reload(self.char1, gun, magazine))
        self.assertEqual(before, self.atomic_state())
        with self.assertRaises(rules.RuleError):
            service.reload(self.char2, gun)

    def test_atomic_swap_failure_restores_location_rounds_refs_and_sequence(self):
        gun = self.gun("partial", rounds=7)
        replacement = self.mag(12)
        equipment.equip_item(self.char1, gun)
        before = self.atomic_state()
        original = api.move_item_tree

        def fail_insert(item, **kwargs):
            if kwargs["location_kind"] == "inside":
                raise ValidationError("삽입 실패")
            return original(item, **kwargs)

        with patch.object(api, "move_item_tree", side_effect=fail_insert):
            with self.assertRaises(rules.RuleError):
                service.reload(self.char1, gun, replacement)
        self.assertEqual(before, self.atomic_state())

    def test_reload_combat_consumes_once_without_mental_or_cooldown(self):
        gun, magazine = self.gun("partial", rounds=7), self.mag(12)
        self.combat_profile("shooting")
        before = deepcopy(dict(self.char1.profile()))
        self.assertTrue(service.reload(self.char1, gun, magazine, now=100))
        profile = self.char1.profile()
        self.assertEqual((profile["player_round"], profile["queued_action"]), (before["player_round"] + 1, "attack"))
        self.assertGreater(profile["next_attack_at"], 100)
        self.assertEqual(profile["mental"], before["mental"])
        self.assertEqual(profile["skill_ready_at"], before["skill_ready_at"])
        after = self.atomic_state()
        self.assertFalse(service.reload(self.char1, gun, now=100))
        self.assertEqual(after, self.atomic_state())
        self.assertFalse(service.reload(self.char1, gun, now=103))
        self.assertEqual(after, self.atomic_state())
        extended = self.mag(18, "mag_9_extended")
        # 준비된 기회 전의 사용자 입력도 다음 기회를 정확히 하나 대체한다.
        deadline = self.char1.profile()["next_attack_at"]
        turn = self.char1.profile()["player_round"]
        service.reload(self.char1, gun, extended, now=100)
        self.assertEqual(self.char1.profile()["player_round"], turn + 1)
        self.assertGreater(self.char1.profile()["next_attack_at"], deadline)

    def test_loose_load_partial_capacity_delete_and_inserted_access(self):
        magazine, ammo = self.mag(7), self.create("ammo_9", quantity=3)
        self.assertEqual(service.load_ammo(self.char1, magazine, ammo), 3)
        self.assertFalse(ItemEntity.objects.filter(pk=ammo.pk).exists())
        ammo = self.create("ammo_9", quantity=7)
        self.assertEqual(service.load_ammo(self.char1, magazine, ammo), 2)
        ammo.refresh_from_db()
        self.assertEqual(ammo.quantity, 5)
        gun = self.gun()
        service.reload(self.char1, gun, magazine)
        service.unload_ammo(self.char1, magazine)
        self.assertEqual(service.load_ammo(self.char1, magazine), 12)
        self.assertEqual(service.loaded_magazine(gun).rounds, 12)
        before = self.atomic_state()
        with self.assertRaises(rules.RuleError):
            service.load_ammo(self.char1, magazine)
        self.assertEqual(before, self.atomic_state())

    def test_ammo_mismatch_foreign_storage_and_combat_rejected(self):
        magazine, wrong = self.mag(7), self.create("ammo_556", quantity=10)
        before = self.atomic_state()
        with self.assertRaises(rules.RuleError):
            service.load_ammo(self.char1, magazine, wrong)
        with self.assertRaises(rules.RuleError):
            service.load_ammo(self.char2, magazine)
        self.assertEqual(before, self.atomic_state())
        api.move_item_tree(magazine, location_kind="personal_storage", owner_object=self.char1, operation="store")
        with self.assertRaises(rules.RuleError):
            service.unload_ammo(self.char1, magazine)
        api.move_item_tree(magazine, location_kind="inventory", owner_object=self.char1, operation="store")
        self.combat_profile()
        before = self.atomic_state()
        for action in (service.load_ammo, service.unload_ammo):
            with self.assertRaises(rules.RuleError):
                action(self.char1, magazine)
        self.assertEqual(before, self.atomic_state())

    def test_unload_all_merges_preserving_destination_and_magazine_sequence(self):
        gun = self.gun("partial", rounds=7)
        magazine = service.loaded_magazine_item(gun)
        loose = self.create("ammo_9", quantity=3)
        identity, sequence = loose.pk, loose.sequence
        mag_sequence = magazine.sequence
        self.assertEqual(service.unload_ammo(self.char1, magazine, "9mm"), 7)
        loose.refresh_from_db()
        self.assertEqual((loose.pk, loose.sequence, loose.quantity), (identity, sequence, 10))
        magazine.refresh_from_db()
        self.assertEqual((magazine.state["rounds"], magazine.sequence), (0, mag_sequence))
        self.assertEqual(ItemEntity.objects.filter(definition_id="ammo_9").count(), 1)
        service.unload_magazine(self.char1, gun)
        magazine.refresh_from_db()
        self.assertEqual((magazine.location_kind, magazine.parent_item_id, magazine.socket), ("inventory", None, None))
        self.assertEqual(magazine.sequence, mag_sequence)

    def test_ammo_load_unload_mutation_failure_rolls_back(self):
        magazine, ammo = self.mag(7), self.create("ammo_9", quantity=3)
        before = self.atomic_state()
        with patch.object(api, "update_item_state", side_effect=ValidationError("상태 실패")):
            for action in (service.load_ammo, service.unload_ammo):
                with self.assertRaises(rules.RuleError):
                    action(self.char1, magazine)
                self.assertEqual(before, self.atomic_state())
        self.assertTrue(ItemEntity.objects.filter(pk=ammo.pk).exists())

    def test_actual_shots_and_nonshots_consume_rounds(self):
        gun = self.gun("full_standard")
        equipment.equip_item(self.char1, gun)
        magazine = service.loaded_magazine_item(gun)
        for index, action in enumerate(("attack", "shooting", "suppress", "insight", "heal", "breathing")):
            with self.subTest(action=action):
                profile = self.combat_profile(action)
                before = magazine.state["rounds"]
                damage, outcome = service.player_attack(self.char1, profile, "scavenger", 100 + index * 20, 2.5, Random(1))
                magazine.refresh_from_db()
                shot = action in ("attack", "shooting", "suppress")
                self.assertEqual(outcome.get("shot_fired"), shot)
                self.assertEqual(magazine.state["rounds"], before - int(shot))
                if shot:
                    self.assertGreater(damage, 0)
        before = magazine.state["rounds"]
        with world_change():
            service.consume_shot(magazine, {"shot_fired": True, "damage": 0, "hit": False})
        magazine.refresh_from_db()
        self.assertEqual(magazine.state["rounds"], before - 1)

    def test_empty_shots_consume_opportunity_before_skill_cost(self):
        gun = self.gun()
        equipment.equip_item(self.char1, gun)
        for mode in ("no_mag", "empty"):
            if mode == "empty":
                api.create_item("mag_9_standard", location_kind="inside", parent_item=gun, socket="magazine")
            for action in ("attack", "shooting", "suppress"):
                with self.subTest(mode=mode, action=action):
                    profile = self.combat_profile(action)
                    mental, cooldowns, turn = profile["mental"], deepcopy(profile["skill_ready_at"]), profile["player_round"]
                    damage, outcome = service.player_attack(self.char1, profile, "scavenger", 100, 2.5)
                    self.assertEqual((damage, outcome["shot_fired"]), (0, False))
                    self.assertEqual(profile["player_round"], turn + 1)
                    self.assertEqual((profile["mental"], profile["skill_ready_at"]), (mental, cooldowns))
                    self.assertEqual(profile["queued_action"], "attack")

    def test_shot_state_failure_rolls_back_persistent_profile_and_magazine(self):
        gun = self.gun("full_standard")
        equipment.equip_item(self.char1, gun)
        self.combat_profile("shooting")
        before = self.atomic_state()
        with patch.object(api, "update_item_state", side_effect=ValidationError("탄약 저장 실패")):
            with self.assertRaises(ValidationError), world_change():
                profile = self.char1.profile()
                service.player_attack(self.char1, profile, "scavenger", 100, 2.5)
                self.char1.save_profile(profile)
        self.assertEqual(before, self.atomic_state())

    def test_loaded_structural_policy_before_move_and_magazine_sale_burn_allowed(self):
        from world.item_entities.policy import can_item_operation

        gun = self.gun("full_standard")
        equipment.equip_item(self.char1, gun)
        before = self.atomic_state()
        for operation in ("sell", "burn"):
            self.assertFalse(can_item_operation(gun, operation))
            with self.subTest(operation=operation), self.assertRaises(ValidationError):
                api.move_item_tree(gun, location_kind="inventory", owner_object=self.char1, operation=operation)
            self.assertEqual(before, self.atomic_state())
        equipment.unequip_item(self.char1, gun)
        api.move_item_tree(gun, location_kind="personal_storage", owner_object=self.char1, operation="store")
        api.move_item_tree(gun, location_kind="inventory", owner_object=self.char1, operation="store")
        magazine = service.unload_magazine(self.char1, gun)
        for operation in ("sell", "burn"):
            self.assertTrue(can_item_operation(magazine, operation))
            self.assertTrue(can_item_operation(gun, operation))
            api.move_item_tree(magazine, location_kind="inventory", owner_object=self.char1, operation=operation)
            api.move_item_tree(gun, location_kind="inventory", owner_object=self.char1, operation=operation)
        before = self.atomic_state()
        with self.assertRaises(ValidationError):
            api.move_item_tree(gun, location_kind="inventory", owner_object=self.char1, operation="unknown")
        self.assertEqual(before, self.atomic_state())

    def test_stateful_duplicate_selectors_and_command_parser(self):
        from commands.firearms import LoadMagazine
        from commands.items import Retrieve, Store

        first, second = self.gun(), self.gun()
        self.mag(2)
        magazine = self.mag(7)
        self.assertEqual(equipment.resolve_item(self.char1, "시험총 2", "장전").pk, second.pk)
        self.call(LoadMagazine(), "시험총 2에 권총표준 2", "탄창을 장전했다.")
        self.assertEqual(service.loaded_magazine_item(second).pk, magazine.pk)
        self.assertIsNone(service.loaded_magazine_item(first))
        self.assertEqual(equipment.resolve_item(self.char1, "권총표준 2", "채워").pk, magazine.pk)
        ammo = self.create("ammo_9", quantity=3)
        self.call(Store(), "권총표준 2에 권총탄", "탄창에 3발을 넣었다.")
        self.assertFalse(ItemEntity.objects.filter(pk=ammo.pk).exists())
        self.call(Retrieve(), "시험총 2에서 탄창", "탄창을 꺼냈다.")
        self.call(Retrieve(), "권총표준 2에서 권총탄", "탄창에서 10발을 전부 꺼냈다.")
        profile = self.char1.profile()
        rows = equipment.eq.inventory_rows(profile)
        self.assertNotIn(str(magazine.pk), str(rows))
        self.assertIn("0/12", str(rows))

    def test_legacy_firearm_combat_remains_ammo_free_and_reload_rejected(self):
        self.char1.db.equipment_backend = None
        profile = rules.new_profile()
        profile["inventory"]["guard_carbine"] = 1
        profile["equipment"]["weapon"] = "guard_carbine"
        self.char1.db.profile = profile
        profile = self.char1.profile()
        before = ItemEntity.objects.count()
        damage, outcome = service.player_attack(self.char1, profile, "scavenger", 100, 2.5, Mock(randint=Mock(return_value=0)))
        self.assertGreater(damage, 0)
        self.assertTrue(outcome["shot_fired"])
        with self.assertRaises(rules.RuleError):
            service.reload(self.char1, "guard_carbine")
        self.assertEqual(before, ItemEntity.objects.count())
        self.assertNotIn("rounds", self.char1.profile())

    def test_live_enemy_path_commits_shot_and_rolls_back_ammo_failure(self):
        from evennia.utils.create import create_object
        from typeclasses.enemies import Enemy

        self.enterContext(patch("typeclasses.enemies.delay"))
        self.enterContext(patch.object(self.char1.sessions, "count", return_value=1))
        enemy = create_object(Enemy, key="시험 적", location=self.char1.location)
        enemy.db.enemy_id = "scavenger"
        enemy.db.hp = enemy.db.max_hp = 1000
        gun = self.gun("full_standard")
        equipment.equip_item(self.char1, gun)
        enemy.engage(self.char1, now=100)
        magazine = service.loaded_magazine_item(gun)
        before_hp = enemy.db.hp
        enemy.receive_attack(self.char1, now=103, rng=Random(1))
        magazine.refresh_from_db()
        self.assertEqual(magazine.state["rounds"], 11)
        self.assertLess(enemy.db.hp, before_hp)
        before = self.atomic_state()
        enemy_before = (enemy.db.hp, deepcopy(enemy.db.contribution), deepcopy(enemy.db.threat))
        with patch.object(api, "update_item_state", side_effect=ValidationError("발사 저장 실패")):
            with self.assertRaises(ValidationError):
                enemy.receive_attack(self.char1, now=106, rng=Random(1))
        self.assertEqual(before, self.atomic_state())
        self.assertEqual(enemy_before, (enemy.db.hp, enemy.db.contribution, enemy.db.threat))
