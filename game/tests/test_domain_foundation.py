"""Actor 기반 실행 권한·회차 정산·지연 복구·전달·Fresh 안전 경계."""

from dataclasses import replace
from unittest.mock import Mock, patch

from django.test import TestCase
from evennia import create_object
from evennia.objects.objects import DefaultObject
from evennia.scripts.models import ScriptDB
from world.combat_contracts import (
    Combatant,
    EncounterPolicy,
    PendingState,
    apply_tick,
    begin_encounter,
    pending_state,
    plan_tick,
    settle_encounter,
)
from world.delivery import Delivery, deliver_after_commit
from world.domain_context import (
    DomainExecutionContext,
    Origin,
    Principal,
    combat_timer_context,
    validate_context,
)
from world.multiplayer import world_change
from world.rules import RuleError
from world.world_format import FORMAT_KEY, assert_fresh, initialize_world, require_ready

from tests.base import GameCommandTest
from tests.item_entity_fixture import NativeItemTest


class DomainFoundationTests(GameCommandTest):
    def encounter(self):
        return begin_encounter(self.obj1, (self.char1, self.char2))

    def context(self, encounter, operation_id="tick:1", now=100):
        return combat_timer_context(self.obj1, operation_id=operation_id,
                                    domain_scope=encounter.identity,
                                    generation=encounter.generation, clock=lambda: now)

    def test_internal_principal_cannot_be_forged_or_change_domain(self):
        encounter = self.encounter()
        context = self.context(encounter)
        def validate(current, operation="combat.tick", scope=encounter.identity):
            return validate_context(current, operation, actor=self.obj1, domain_scope=scope,
                                    generation=encounter.generation, permission=lambda _: True)
        validate(context)
        forged = DomainExecutionContext(Origin.TIMER,
            Principal(Origin.TIMER, str(self.obj1.pk), encounter.identity, frozenset(("combat.tick",)),
                      "tick:1", encounter.generation),
            self.obj1, None, "tick:1", encounter.identity, lambda: 100, encounter.generation)
        for current, operation, scope in ((forged, "combat.tick", encounter.identity),
                                          (context, "reward.grant", encounter.identity),
                                          (context, "combat.tick", "other:encounter")):
            with self.assertRaises(RuleError):
                validate(current, operation, scope)
        with self.assertRaises(RuleError):
            validate_context(context, "combat.tick", actor=self.obj1, domain_scope=encounter.identity,
                             generation=encounter.generation, permission=lambda _: False)
        with self.assertRaises(RuleError):
            validate(replace(context, operation_id="tick:other"))

    def test_settlement_is_atomic_and_duplicate_finish_has_no_effect(self):
        encounter = self.encounter()
        self.char1.db.foundation_reward = 0

        def reward(_):
            self.char1.db.foundation_reward += 10
            self.obj1.db.foundation_corpse_count = (self.obj1.db.foundation_corpse_count or 0) + 1

        def failing(state):
            reward(state)
            raise RuntimeError("정산 중 실패")

        with self.assertRaises(RuntimeError):
            settle_encounter(encounter, {"kind": "death"}, failing)
        self.assertEqual(self.char1.db.foundation_reward, 0)
        self.assertIsNone(self.obj1.db.foundation_corpse_count)
        self.assertFalse(encounter.current()["settled"])
        self.assertTrue(settle_encounter(encounter, {"kind": "death"}, reward))
        self.assertFalse(settle_encounter(encounter, {"kind": "death"}, reward))
        self.assertEqual(self.char1.db.foundation_reward, 10)
        self.assertEqual(self.obj1.db.foundation_corpse_count, 1)

    def test_callback_loss_recovers_from_persistent_due_and_rejects_duplicate(self):
        encounter = self.encounter()
        trigger = Mock()
        with patch("world.combat_contracts.after_change"):
            plan_tick(encounter, operation_id="tick:1", due_at=100, trigger=trigger)
        trigger.assert_not_called()
        # 메모리 예약과 원래 Encounter handle을 버린 뒤 영속 상태로 재활성화한다.
        from world.combat_contracts import Encounter

        restored = Encounter(self.obj1, self.obj1.db.combat_generation)
        self.assertEqual(pending_state(restored, self.context(restored, now=99)), PendingState.PENDING)
        context = self.context(restored, now=101)
        self.assertEqual(pending_state(restored, context), PendingState.DUE)
        effects = Mock()
        apply_tick(restored, context, effects)
        self.assertEqual(pending_state(restored, context), PendingState.COMPLETED)
        with self.assertRaises(RuleError):
            apply_tick(restored, context, effects)
        effects.assert_called_once()
        self.assertFalse(plan_tick(restored, operation_id="tick:1", due_at=102, trigger=trigger))
        plan_tick(restored, operation_id="tick:2", due_at=103, trigger=trigger)
        self.assertFalse(plan_tick(restored, operation_id="tick:1", due_at=104, trigger=trigger))

    def test_old_generation_and_invalidated_operation_are_refused(self):
        first = self.encounter()
        plan_tick(first, operation_id="tick:1", due_at=100, trigger=lambda *args: None)
        context = self.context(first)
        settle_encounter(first, {"kind": "death"}, lambda _: None)
        self.assertEqual(pending_state(first, context), PendingState.COMPLETED)
        second = self.encounter()
        self.assertGreater(second.generation, first.generation)
        self.assertNotEqual(second.identity, first.identity)
        self.assertEqual(pending_state(first, context), PendingState.STALE)
        self.assertEqual(pending_state(second, replace(context, generation=second.generation)), PendingState.INVALID)
        effect = Mock()
        with self.assertRaises(RuleError):
            apply_tick(first, context, effect)
        effect.assert_not_called()

    def test_unsupported_policies_do_not_silently_start_shared(self):
        for policy in (EncounterPolicy.EXCLUSIVE_DUEL, EncounterPolicy.SIMULATION, EncounterPolicy.WORLD_EVENT):
            with self.assertRaises(RuleError):
                begin_encounter(self.obj1, (self.char1,), policy=policy)
        self.assertIsNone(self.obj1.db.encounter_state)

    def test_combatant_effect_requires_domain_boundary(self):
        self.obj1.capability_active = lambda capability: capability == "combat"
        self.obj1.db.combat_state = {"hp": 10}
        combatant = Combatant(self.obj1)
        with self.assertRaises(RuntimeError):
            combatant.apply(lambda state: state.update(hp=5))
        with world_change():
            combatant.apply(lambda state: state.update(hp=5))
        self.assertEqual(combatant.snapshot()["hp"], 5)
        with self.assertRaises(RuntimeError):
            with world_change():
                combatant.apply(lambda state: state.update(hp=0))
                raise RuntimeError("상태 적용 실패")
        self.assertEqual(combatant.snapshot()["hp"], 5)

    def test_delivery_waits_for_commit_preserves_order_and_isolates_failure(self):
        received = []
        broken = Mock()
        broken.msg.side_effect = RuntimeError("연결 소실")
        receiver = Mock()
        receiver.msg.side_effect = lambda message, **kwargs: received.append(message)
        errors = Mock()
        event = Delivery("result:1", "combat", (broken, receiver), ("공격", "보상"))
        with world_change():
            self.obj1.db.committed_effect = True
            deliver_after_commit(event, on_error=errors)
            self.assertEqual(received, [])
        self.assertTrue(self.obj1.db.committed_effect)
        self.assertEqual(received, ["공격", "보상"])
        errors.assert_called_once_with("result:1", broken)
        with self.assertRaises(RuntimeError):
            with world_change():
                deliver_after_commit(Delivery("result:2", "combat", (receiver,), ("잘못된 성공",)))
                raise RuntimeError("rollback")
        self.assertEqual(received, ["공격", "보상"])


class NativeCombatantFoundationTests(NativeItemTest):
    def test_snapshot_and_effect_preserve_equipment_and_native_consumption(self):
        from world import equipment_service, rules
        from world.equipment import EquipmentProfile
        from world.item_inventory import bind_consumption

        weapon = self.create("explorer_machete")
        equipment_service.equip_item(self.char1, weapon)
        selected = self.create("bandage", quantity=3)
        other = self.create("bandage", quantity=2)
        combatant = Combatant(self.char1)
        expected_stats = rules.stats(self.char1.profile_snapshot())
        snapshot = combatant.snapshot()
        self.assertIsInstance(snapshot, EquipmentProfile)
        self.assertEqual(rules.stats(snapshot), expected_stats)
        self.assertGreater(expected_stats["weapon_attack"], 0)
        self.assertEqual(snapshot.equipment_context.active.identity, str(weapon.pk))
        self.assertEqual(snapshot.item_baseline["bandage"], 5)

        def use_selected_bandage(profile):
            self.assertEqual(rules.stats(profile), expected_stats)
            self.assertTrue(bind_consumption(self.char1, profile, "bandage", selected.pk))
            rules.use_bandage(profile)

        with world_change():
            result = combatant.apply(use_selected_bandage)
        selected.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((selected.quantity, other.quantity), (2, 2))
        self.assertGreater(self.char1.profile_snapshot()["hp"], 30)
        self.assertIsInstance(result, EquipmentProfile)
        self.assertEqual(result.item_baseline["bandage"], 4)
        self.assertEqual(result.item_operations["bandage"], "consume")
        self.assertEqual(result.item_consumption_ids["bandage"], str(selected.pk))
        self.assertEqual(rules.stats(result)["weapon_attack"], expected_stats["weapon_attack"])
        self.assertEqual(combatant.snapshot().item_baseline["bandage"], 4)


class WorldFormatFoundationTests(TestCase):
    def prepare_item_runtime(self):
        from world.item_entities.models import ItemRuntime

        ItemRuntime.objects.create(pk=1, version=1)

    def test_fresh_initialization_and_repeated_audit_preserve_state(self):
        assert_fresh()
        created = []

        def build():
            self.prepare_item_runtime()
            created.append(create_object(DefaultObject, key="보존할 실물"))
            created[0].db.hp = 7

        marker = initialize_world(build, lambda: ())
        self.assertEqual(marker.db.status, "ready")
        self.assertEqual(initialize_world(lambda: self.fail("반복 생성 금지"), lambda: ()).pk, marker.pk)
        self.assertEqual(created[0].db.hp, 7)
        with self.assertRaises(RuleError):
            require_ready(lambda: ("손상된 관계",))
        for invalid_version in (True, "1", 0, 2):
            marker.db.version = invalid_version
            with self.subTest(version=invalid_version), self.assertRaises(RuleError):
                require_ready(lambda: ())

    def test_existing_objects_and_native_marker_are_not_fresh(self):
        actor = create_object(DefaultObject, key="기존 데이터")
        with self.assertRaises(RuleError):
            initialize_world(lambda: self.fail("기존 DB 초기화 금지"), lambda: ())
        self.assertEqual(actor.key, "기존 데이터")
        self.assertFalse(ScriptDB.objects.filter(db_key=FORMAT_KEY).exists())

    def test_partial_marker_or_invalid_format_is_not_reinitialized(self):
        from evennia import create_script
        from world.world_format import WorldFormat

        marker = create_script(WorldFormat)
        marker.db.version = 1
        marker.db.status = "initializing"
        marker.db.world_id = "not-a-valid-id"
        with self.assertRaises(RuleError):
            initialize_world(lambda: self.fail("부분 DB 재초기화 금지"), lambda: ())
        self.assertEqual(marker.db.status, "initializing")

    def test_failed_initialization_rolls_back_marker_and_domain_objects(self):
        from evennia.objects.models import ObjectDB

        def build():
            self.prepare_item_runtime()
            create_object(DefaultObject, key="실패할 실물")
            raise RuntimeError("초기화 중단")

        with self.assertRaises(RuntimeError):
            initialize_world(build, lambda: ())
        self.assertFalse(ScriptDB.objects.filter(db_key=FORMAT_KEY).exists())
        self.assertFalse(ObjectDB.objects.exists())
        assert_fresh()
