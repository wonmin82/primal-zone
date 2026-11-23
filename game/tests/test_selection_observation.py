"""안정 대상 관찰과 대화가 실제 Gateway에서 원래 실물만 실행하는지 확인한다."""

from unittest.mock import patch

from evennia import create_object
from evennia.objects.models import ObjectDB
from typeclasses.interactables import ActionObject
from typeclasses.loot import Corpse, DroppedLoot
from world import loot_service
from world.actions.gateway import ResultStatus, execute, from_web
from world.actions.global_actions import target_action
from world.actions.manifest import get_index
from world.actions.resolver import ActionInvocation
from world.bootstrap import build_world
from world.doors import current_doors
from world.item_entities.api import move_item
from world.selection_numbers.api import descriptor, number_for
from world.targets import exact_selector

from tests.item_entity_fixture import NativeItemTest


class SelectionObservationTests(NativeItemTest):
    def setUp(self):
        super().setUp()
        self.session = self.connect_character(self.char1)
        self.index = get_index()
        self.enterContext(patch("commands.character.time", return_value=100))
        self.enterContext(patch("world.lifecycle.time", return_value=100))

    def request(self, action, target):
        payload = target_action(action, descriptor(target).reference)
        payload["request_id"] = "selection-observation"
        return from_web(payload, self.index)

    def run_action(self, request, session=None):
        return execute(self.char1, self.session if session is None else session, request, self.index)

    def look(self, query):
        return self.run_action(ActionInvocation("global.look", "adapter", (), (("query", query),)))

    def object(self, name):
        return create_object(ActionObject, key=name, location=self.char1.location)

    def test_dialogue_hint_round_trips_the_addressee_with_an_internal_particle(self):
        from world.actors.spawn import create_actor
        from world.npc_dialogue import dialogue_target_text, explicit_target

        first = create_actor("commander", self.char1.location, name="윤대장")
        second = create_actor("commander", self.char1.location, name="윤대장에게 작전")
        self.assertEqual(explicit_target(self.char1, f"{second.key}에게 안녕")[0], first)
        text = dialogue_target_text(self.char1, second)
        self.assertEqual(text, exact_selector(second.key, number_for(descriptor(second).reference)))
        self.assertEqual(explicit_target(self.char1, f"{text}에게 안녕"), (second, "안녕"))
        colored = create_actor("commander", self.char1.location, name="윤대장|n")
        self.assertIsNone(dialogue_target_text(self.char1, colored))

    def test_exact_look_beats_literal_reserved_name_and_typed_look_uses_identity(self):
        target = self.object("장치에서 발견한 부품")
        number = number_for(descriptor(target).reference)
        query = exact_selector(descriptor(target).name, number)
        collision = self.object(query)
        malformed = self.object('"실제 이름" 0')
        actual_selection = exact_selector(descriptor(collision).name, number_for(descriptor(collision).reference))

        with patch.object(self.char1, "at_look", return_value="세부 설명") as observe:
            self.assertEqual(self.look(query).status, ResultStatus.SUCCESS)
            self.assertIs(observe.call_args.args[0], target)
            self.assertEqual(self.look(actual_selection).status, ResultStatus.SUCCESS)
            self.assertIs(observe.call_args.args[0], collision)
            self.assertEqual(self.run_action(self.request("look_target", target)).status, ResultStatus.SUCCESS)
            self.assertIs(observe.call_args.args[0], target)
            self.assertEqual(self.look(malformed.key).status, ResultStatus.SUCCESS)
            self.assertIs(observe.call_args.args[0], malformed)
            self.assertEqual(observe.call_count, 4)

    def test_exact_look_rejects_same_number_across_room_and_inventory_and_typed_stays_exact(self):
        item = self.create("test_pistol")
        entity = self.object(descriptor(item).name)
        reference = descriptor(entity).reference
        self.assertEqual(number_for(reference), number_for(descriptor(item).reference))
        query = exact_selector(descriptor(item).name, number_for(reference))
        item_request = self.request("look_target", item)
        with patch.object(self.char1, "at_look", return_value="세부 설명") as observe:
            self.assertIn("여러 범위", str(self.look(query).messages[0]))
            observe.assert_not_called()
            viewed_item = self.run_action(item_request)
            self.assertEqual(viewed_item.status, ResultStatus.SUCCESS)
            self.assertIn(descriptor(item).name, str(viewed_item.messages[0]))
            self.assertEqual(self.run_action(self.request("look_target", entity)).status, ResultStatus.SUCCESS)
            self.assertIs(observe.call_args.args[0], entity)
            observe.reset_mock()
            move_item(item, location_kind="inventory", owner_object=self.char2)
            self.assertEqual(self.run_action(item_request).status, ResultStatus.REFUSED)
            observe.assert_not_called()

    def test_inside_look_uses_the_nested_uuid_in_typed_and_exact_text(self):
        from world.actions.presentation import action_controls
        from world.equipment_service import selector_label
        from world.item_entities.api import create_item, delete_item

        root = self.create("bandage")
        child = create_item("flashlight", location_kind="inside", parent_item=root, socket="tool")
        batteries = [create_item("battery", location_kind="inside", parent_item=child, socket="power")
                     for _ in range(7)]
        for removed in batteries[:-1]:
            delete_item(removed)
        target = batteries[-1]
        reference = descriptor(target).reference
        self.assertEqual(number_for(reference), 7)
        other = self.create("flashlight")
        same_name = create_item("battery", location_kind="inside", parent_item=other, socket="power")
        self.assertEqual(number_for(descriptor(same_name).reference), 1)
        with patch("world.equipment_service.selector_label", wraps=selector_label) as observe:
            web = self.run_action(self.request("look_target", target))
            text = self.look(exact_selector(descriptor(target).name, 7))
            self.assertEqual(web.status, ResultStatus.SUCCESS, web.messages)
            self.assertEqual(text.status, ResultStatus.SUCCESS, text.messages)
            self.assertEqual(tuple(map(str, text.messages)), tuple(map(str, web.messages)))
            self.assertEqual([call.args[1].pk for call in observe.call_args_list], [target.pk, target.pk])
        controls = [row["action"] for row in action_controls(self.char1, self.index, 100)
                    if row["action"]["action_id"] == "global.look_target"]
        self.assertIn(target_action("look_target", reference), controls)

    def test_direct_inside_light_can_be_observed_without_activating_it(self):
        from world.item_entities.api import create_item

        root = self.create("bandage")
        first = create_item("flashlight", location_kind="inside", parent_item=root, socket="tool")
        second_root = self.create("bandage")
        second = create_item("flashlight", location_kind="inside", parent_item=second_root, socket="tool")
        number = number_for(descriptor(first).reference)
        self.assertEqual(number, number_for(descriptor(second).reference))
        self.assertIn("여러 범위", str(self.look(exact_selector(descriptor(first).name, number)).messages))
        state = first.state.copy()
        result = self.run_action(self.request("look_target", first))
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertIn("붕대 1의 탐사용손전등", str(result.messages))
        first.refresh_from_db()
        self.assertEqual(first.state, state)

    def test_inside_look_refuses_stale_scopes_and_private_roots(self):
        from typeclasses.interactables import Container
        from world.equipment_service import selector_label
        from world.item_entities.api import create_item, delete_item, move_item_tree

        root = self.create("bandage")
        child = create_item("battery", location_kind="inside", parent_item=root, socket="part")
        old_request = self.request("look_target", child)
        with patch("world.equipment_service.selector_label", wraps=selector_label) as observe:
            move_item_tree(root, location_kind="inventory", owner_object=self.char2)
            self.assertEqual(self.run_action(old_request).status, ResultStatus.REFUSED)
            move_item_tree(root, location_kind="personal_storage", owner_object=self.char1)
            self.assertEqual(self.run_action(old_request).status, ResultStatus.REFUSED)
            box = create_object(Container, key="비공개 보관함", location=self.char1.location)
            box.locks.add("view:false();call:false()")
            move_item_tree(root, location_kind="shared_storage", owner_object=box)
            self.assertEqual(self.run_action(old_request).status, ResultStatus.REFUSED)
            move_item_tree(root, location_kind="inventory", owner_object=self.char1)
            moved = move_item(child, location_kind="inventory", owner_object=self.char1)
            self.assertEqual(self.run_action(old_request).status, ResultStatus.REFUSED)
            child = move_item(moved, location_kind="inside", parent_item=root, socket="part")
            delete_item(child)
            replacement = create_item("battery", location_kind="inside", parent_item=root, socket="part")
            self.assertEqual(number_for(descriptor(replacement).reference), 1)
            self.assertEqual(self.run_action(old_request).status, ResultStatus.REFUSED)
            observe.assert_not_called()

    def test_inside_look_refuses_corrupt_parent_cycle(self):
        from world.actions.presentation import target_label
        from world.item_entities.api import create_item
        from world.item_entities.models import ItemEntity

        root = self.create("bandage")
        child = create_item("battery", location_kind="inside", parent_item=root, socket="part")
        reference = descriptor(child).reference
        request = self.request("look_target", child)
        # 격리 DB에 위치 제약은 만족하고 부모 관계만 손상된 데이터를 재현한다.
        ItemEntity.objects.filter(pk=root.pk).update(location_kind="inside", owner_object_id=None,
                                                    parent_item_id=child.pk, socket="broken")
        try:
            with patch("world.actions.global_actions._item_appearance") as observe:
                self.assertEqual(self.run_action(request).status, ResultStatus.REFUSED)
                self.assertIsNone(target_label(self.char1, reference, 100))
                observe.assert_not_called()
        finally:
            ItemEntity.objects.filter(pk=root.pk).update(location_kind="inventory", owner_object=self.char1,
                                                        parent_item_id=None, socket=None)

    def test_hidden_moved_and_deleted_corpse_never_observe_replacement(self):
        room = self.char1.location
        remote = create_object("typeclasses.rooms.Room", key="다른 방")
        corpse = create_object(Corpse, key="원래 시체", location=room)
        corpse.db.decay_at = 500
        loot_service.populate_source(corpse, [])
        reference = descriptor(corpse).reference
        self.assertEqual(number_for(reference), 1)
        request = self.request("look_target", corpse)

        with patch.object(self.char1, "at_look", return_value="세부 설명") as observe:
            self.assertEqual(self.run_action(request).status, ResultStatus.SUCCESS)
            self.assertIs(observe.call_args.args[0], corpse)
            observe.reset_mock()
            corpse.locks.add("view:false()")
            self.assertEqual(self.run_action(request).status, ResultStatus.REFUSED)
            corpse.locks.add("view:all()")
            corpse.location = remote
            self.assertEqual(self.run_action(request).status, ResultStatus.REFUSED)
            corpse.delete()
            replacement = create_object(Corpse, key="새 시체", location=room)
            replacement.db.decay_at = 500
            loot_service.populate_source(replacement, [])
            self.assertEqual(number_for(descriptor(replacement).reference), 1)
            self.assertEqual(self.run_action(request).status, ResultStatus.REFUSED)
            observe.assert_not_called()

    def test_exact_look_does_not_expose_a_ground_sources_raw_asset_name(self):
        source = create_object(DroppedLoot, key="숨은 물품 이름", location=self.char1.location)
        loot_service.populate_source(source, [])
        record = descriptor(source)
        query = exact_selector(record.name, number_for(record.reference))

        with patch.object(self.char1, "at_look", return_value="원본 관찰") as observe:
            self.assertIn("지금 살펴볼 수 없는", str(self.look(query).messages[0]))
            observe.assert_not_called()
            self.assertIsNotNone(number_for(record.reference))

    def test_npc_and_door_revalidate_access_and_reuse_observation(self):
        rooms = build_world()
        self.char1.location = rooms["dock"]
        npc = next(obj for obj in self.char1.location.contents if obj.key == "윤대장")
        request = self.request("greet_target", npc)
        with patch.object(self.char1, "msg"):
            self.assertEqual(self.run_action(request).status, ResultStatus.SUCCESS)
        self.assertEqual(self.char1.ndb.npc_dialogue_context["npc_id"], npc.pk)
        npc.locks.add("view:false()")
        with patch("world.npc_dialogue.public_speech") as speech:
            self.assertEqual(self.run_action(request).status, ResultStatus.REFUSED)
            speech.assert_not_called()

        self.char1.location = rooms["hq_concourse"]
        door = current_doors(self.char1, 100)[0]
        endpoint = ObjectDB.objects.get(pk=door.exit_pk)
        request = self.request("look_target", endpoint)
        query = exact_selector("문", number_for(descriptor(endpoint).reference))
        text = self.look(query)
        web = self.run_action(request)
        self.assertEqual(web.status, ResultStatus.SUCCESS)
        self.assertEqual(tuple(map(str, web.messages)), tuple(map(str, text.messages)))
        endpoint.locks.add("view:false()")
        self.assertEqual(self.run_action(request).status, ResultStatus.REFUSED)

    def test_door_observation_and_operation_reject_mismatched_endpoint(self):
        from world.door_entities.models import Door
        from world.doors import DoorTarget, describe_door, operate_endpoint
        from world.rules import RuleError

        rooms = build_world()
        self.char1.location = rooms["hq_concourse"]
        original = current_doors(self.char1, 100)[0]
        endpoint = ObjectDB.objects.get(pk=original.exit_pk)
        other = Door.objects.exclude(door_id=original.identity).first()
        incorrect = DoorTarget(other.door_id, original.direction, original.exit_pk)
        with patch("world.doors.current_doors", return_value=[incorrect]), patch(
                "world.doors.effective_door_state", return_value="CLOSED"):
            self.assertIn("이용할 수 없다", describe_door(self.char1, incorrect, 100))
            with self.assertRaises(RuleError):
                operate_endpoint(self.char1, endpoint, "열어", 100)
        self.assertEqual(Door.objects.get(pk=other.pk).state, other.state)
