"""Action 표현 조회의 결과 동등성·수명·관찰 격리를 실제 native fixture로 검증한다."""

from contextlib import nullcontext
from copy import deepcopy
from unittest.mock import Mock, patch

from typeclasses.interactables import TrainingManager
from world.actions.manifest import get_index
from world.actions.presentation import action_controls
from world.actions.presentation_context import available, presentation_scope, profile_snapshot
from world.actions.room_npc_presentation import render
from world.equipment import EquipmentProfile
from world.selection_numbers.api import descriptor
from world.selection_numbers.models import NumberScope, SelectionNumber

from tests.base import WorldCommandTest
from tests.item_entity_fixture import NativeItemTest


class ActionPresentationCacheTests(NativeItemTest, WorldCommandTest):
    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        self.char1.location = self.rooms["training_office"]
        self.char2.location = self.char1.location
        self.index = get_index()
        self.manager = next(obj for obj in self.char1.location.contents
                            if isinstance(obj, TrainingManager))

    def state(self):
        return (self.atomic_state(), list(NumberScope.objects.order_by("pk").values()),
                list(SelectionNumber.objects.order_by("pk").values()))

    def test_typed_controls_equal_without_writes_and_repeated_queries_decrease(self):
        self.create("guard_carbine")
        before = self.state()
        with patch("world.actions.presentation.presentation_scope", side_effect=lambda _: nullcontext()):
            with (patch.object(self.char1, "profile_snapshot", wraps=self.char1.profile_snapshot) as profiles,
                  patch.object(self.manager, "available", wraps=self.manager.available) as availability,
                  patch.object(self.manager, "access", wraps=self.manager.access) as access):
                expected = action_controls(self.char1, self.index, 100)
                uncached_counts = (profiles.call_count, availability.call_count,
                                   sum(call.args[1] == "call" for call in access.call_args_list))
        self.assertTrue(expected)
        self.assertEqual(self.state(), before)
        with (patch.object(self.char1, "profile_snapshot", wraps=self.char1.profile_snapshot) as profiles,
              patch.object(self.manager, "available", wraps=self.manager.available) as availability,
              patch.object(self.manager, "access", wraps=self.manager.access) as access):
            actual = action_controls(self.char1, self.index, 100)
            self.assertLess(profiles.call_count, uncached_counts[0])
            self.assertEqual(availability.call_count, 1)
            self.assertGreater(uncached_counts[1], availability.call_count)
            self.assertEqual(sum(call.args[1] == "call" for call in access.call_args_list),
                             uncached_counts[2])
        self.assertEqual(actual, expected)
        self.assertTrue(all("action_id" in row["action"] and "roles" in row["action"] for row in actual))
        self.assertEqual(self.state(), before)

    def test_snapshots_preserve_equipment_metadata_and_isolate_mutations(self):
        self.create("guard_carbine")
        expected = self.char1.profile_snapshot()
        with patch.object(self.char1, "profile_snapshot", wraps=self.char1.profile_snapshot) as profiles:
            with presentation_scope(self.char1):
                first = profile_snapshot(self.char1)
                self.assertIsInstance(first, EquipmentProfile)
                first["quests"].clear()
                first["hp"] = -1
                second = profile_snapshot(self.char1)
                self.assertEqual(second, expected)
                self.assertEqual(second.equipment_context, expected.equipment_context)
                self.assertIsNot(first.equipment_context, second.equipment_context)
                profiles.assert_called_once()
        self.assertEqual(self.char1.profile_snapshot(), expected)

    def test_next_requests_recheck_combat_location_and_visibility(self):
        baseline = action_controls(self.char1, self.index, 100)
        self.assertTrue(baseline)
        self.char1.change(lambda profile: profile.update(combat_target=999999))
        self.assertEqual(action_controls(self.char1, self.index, 100), [])
        self.char1.change(lambda profile: profile.update(combat_target=None))
        self.assertEqual(action_controls(self.char1, self.index, 100), baseline)
        with presentation_scope(self.char1):
            self.assertTrue(available(self.manager, self.char1, 100))
        self.char1.location = self.rooms["infirmary"]
        with presentation_scope(self.char1):
            self.assertFalse(available(self.manager, self.char1, 100))
        self.char1.location = self.rooms["training_office"]
        self.manager.locks.add("view:false()")
        hidden = action_controls(self.char1, self.index, 100)
        self.assertLess(len(hidden), len(baseline))
        self.manager.locks.add("view:all()")
        with patch("world.observation.can_perceive", return_value=False):
            with presentation_scope(self.char1):
                self.assertFalse(available(self.manager, self.char1, 100))
        self.assertEqual(action_controls(self.char1, self.index, 100), baseline)

    def test_provider_actor_and_time_are_separate_and_none_reobserves(self):
        provider = Mock(available=Mock(side_effect=[True, False, True, False, True, False]))
        other = Mock(available=Mock(return_value=False))
        with presentation_scope(self.char1):
            self.assertTrue(available(provider, self.char1, 100))
            self.assertTrue(available(provider, self.char1, 100))
            self.assertFalse(available(other, self.char1, 100))
            self.assertFalse(available(provider, self.char1, 101))
            self.assertTrue(available(provider, self.char2, 100))
            self.assertFalse(available(provider, self.char2, 100))
            self.assertTrue(available(provider, self.char1, None))
            self.assertFalse(available(provider, self.char1, None))
            self.assertTrue(available(object(), self.char1, 100))
        self.assertEqual(provider.available.call_count, 6)
        self.assertEqual(provider.available.call_args_list[-1].args, (self.char1, None))
        self.char2.change(lambda profile: profile.update(hp=7))
        with presentation_scope(self.char1):
            self.assertNotEqual(profile_snapshot(self.char1)["hp"], profile_snapshot(self.char2)["hp"])
            self.char2.change(lambda profile: profile.update(hp=9))
            self.assertEqual(profile_snapshot(self.char2)["hp"], 9)

    def test_direct_presenter_outside_scope_rechecks_same_provider_and_time(self):
        reference = descriptor(self.manager).reference
        binding = next(binding for binding in self.index.bindings.values()
                       if binding.provider_definition == "world.trainingmanager")
        with patch.object(self.manager, "available", side_effect=[True, False]) as availability:
            self.assertTrue(render(self.char1, self.index, reference, binding, 100))
            self.assertEqual(render(self.char1, self.index, reference, binding, 100), [])
            self.assertEqual(availability.call_count, 2)

    def test_nested_and_exception_scopes_restore_then_release_snapshots(self):
        with patch.object(self.char1, "profile_snapshot", wraps=self.char1.profile_snapshot) as profiles:
            with presentation_scope(self.char1):
                expected = deepcopy(profile_snapshot(self.char1))
                try:
                    with presentation_scope(self.char1):
                        self.assertEqual(profile_snapshot(self.char1), expected)
                        raise ValueError("범위 복원 확인")
                except ValueError:
                    pass
                self.assertEqual(profile_snapshot(self.char1), expected)
                self.assertEqual(profiles.call_count, 2)
            profile_snapshot(self.char1)
            self.assertEqual(profiles.call_count, 3)
        # action_controls 자체가 예외로 끝나도 다음 직접 Presenter 조회로 전파되지 않는다.
        def fail_after_snapshot(caller, index):
            profile_snapshot(caller)
            raise ValueError("조회 실패")

        with patch.object(self.char1, "profile_snapshot", wraps=self.char1.profile_snapshot) as profiles:
            with patch("world.actions.presentation.provided", side_effect=fail_after_snapshot):
                with self.assertRaises(ValueError):
                    action_controls(self.char1, self.index, 100)
            profile_snapshot(self.char1)
            profile_snapshot(self.char1)
            self.assertEqual(profiles.call_count, 3)
