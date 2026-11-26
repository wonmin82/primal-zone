"""정확 인용 선택과 Native 배열 순서·저장 번호 차이의 회귀."""

from dataclasses import replace

from django.test import SimpleTestCase, override_settings
from world.actions.manifest import get_index
from world.actions.resolver import (
    TargetAmbiguous,
    _variant_fields,
    matching_records,
    select_records,
)
from world.actions.schema import DefaultTargetPolicy, ReferenceKind, RoleDefinition, TargetReference
from world.equipment_service import resolve_item
from world.item_entities import api
from world.item_transfer_native import transfer
from world.rules import RuleError
from world.selection_numbers.api import SelectionRecord, descriptor, number_for
from world.targets import (
    MAX_SELECTION_LENGTH,
    Mode,
    TargetSelector,
    exact_selector,
    parse_loot,
    parse_relation,
    parse_selector,
    quoted_name_spans,
    select,
)

from tests.item_entity_fixture import NativeItemTest


class ExactSelectorTests(SimpleTestCase):
    def test_escapes_and_whitespace_preserve_canonical_name(self):
        name = '장치  "B"\\원본'
        raw = exact_selector(name, 7)
        self.assertEqual(parse_selector(raw, b1=True), TargetSelector(name, Mode.INDEX, 7, exact=True))
        self.assertEqual(parse_selector(raw, (raw,), b1=True).name, name)
        self.assertEqual(parse_selector(raw, (raw,)), TargetSelector(raw))

    def test_malformed_is_never_an_ordinary_number_for_another_name(self):
        for value in ('"장치" 0', '"장치" 01', '"장치" +2', '"장치" ２', '"장치" 9223372036854775808',
                      '"장치"2', '"장치 2', '"장\\t치" 2', '"" 2', '"장치" 2 모두'):
            with self.subTest(value=value):
                with self.assertRaises(RuleError):
                    parse_selector(value, ('"장치"',), b1=True)
                self.assertEqual(parse_selector(value, (value,), b1=True), TargetSelector(value))
        with self.assertRaises(RuleError):
            parse_selector('"' + '장' * MAX_SELECTION_LENGTH + '" 1', b1=True)

    def test_relations_outside_quotes_and_legacy_default_and_all(self):
        selector, body = parse_relation('"윤대장에게  물어본 사람" 2에게 안녕', "에게", b1=True)
        self.assertEqual((selector, body), (TargetSelector("윤대장에게  물어본 사람", Mode.INDEX, 2, True), "안녕"))
        request = parse_loot('"시체" 2에서 "시체에서  발견한 부품" 4')
        self.assertEqual(request.source, TargetSelector("시체", Mode.INDEX, 2, True))
        self.assertEqual(request.target, TargetSelector("시체에서  발견한 부품", Mode.INDEX, 4, True))
        self.assertEqual(parse_loot('"시체" 2에서 회수부품 모두').target, TargetSelector("회수부품", Mode.ALL))
        self.assertEqual(select(["first", "second"], parse_selector("플레이어 2")), ["second"])
        self.assertEqual(select(["first", "second"], parse_selector("플레이어 모두")), ["first", "second"])

    def test_compound_action_captures_do_not_split_quoted_provider(self):
        raw = '"장치에서 발견한  보관함" 2에서 "회수부품" 4'
        captures = _variant_fields(r"(?P<provider>.+?)에서 (?P<subject>.+)", raw, quoted_name_spans(raw))
        self.assertEqual(captures, {"provider": '"장치에서 발견한  보관함" 2', "subject": '"회수부품" 4'})

    def test_real_numeric_name_and_exact_selection_are_distinct(self):
        reference = TargetReference(ReferenceKind.OBJECT, "40", "room:10")
        record = SelectionRecord(reference, "room:10", "device", "장 치", ("별칭",), number=2)
        collision = replace(record, reference=replace(reference, identity="41"), name="장 치 2", number=1,
                            group_id="other", aliases=())
        role = RoleDefinition("subject", (ReferenceKind.OBJECT,), DefaultTargetPolicy.ALL)
        self.assertEqual(select_records(role, (record, collision), "장 치 2"), (collision.reference,))
        self.assertEqual(select_records(role, (record, collision), '"장 치" 2'), (reference,))
        alias_collision = replace(collision, name="다른 장치", number=2, aliases=(record.name,))
        self.assertEqual(select_records(role, (record, alias_collision), "장 치 2"), (reference,))
        for value in ('"장치" 2', '"별칭" 2'):
            self.assertEqual(matching_records((record,), parse_selector(value, b1=True)), [])
        duplicate = replace(record, reference=replace(reference, identity="42", scope_id="room:11"), scope_id="room:11")
        with self.assertRaises(TargetAmbiguous):
            select_records(role, (record, duplicate), '"장 치" 2')


@override_settings(ACTION_CONTENT_PACKAGES=("world.actions.item_equipment_content",))
class NativeSelectionNumberTests(NativeItemTest):
    def test_nested_inside_display_and_observation_candidates_read_at_fixed_depth(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from world.actions.global_actions import LOOK_TARGET
        from world.actions.presentation import _carried_labels
        from world.actions.resolver import role_records
        from world.equipment_service import equipment_display
        from world.item_entities.api import carried_items

        root = self.create("bandage")
        child = api.create_item("flashlight", location_kind="inside", parent_item=root, socket="tool")
        target = api.create_item("battery", location_kind="inside", parent_item=child, socket="power")
        scope = f"inside:{child.pk}"
        reference = descriptor(target).reference

        def observations():
            with CaptureQueriesContext(connection) as queries:
                labels = _carried_labels(self.char1)
                records = role_records(self.char1, LOOK_TARGET)
                display = equipment_display(carried_items(self.char1), observed_at=100)
            return (labels[scope], {record.reference for record in records}, display, len(queries))

        first, first_refs, display, small = observations()
        names = [descriptor(row).name for row in (root, child, target)]
        self.assertEqual(display[str(target.pk)].label, "의 ".join(names))
        self.assertEqual(first, {reference: names[-1]})
        self.assertIn(reference, first_refs)
        siblings = [api.create_item("battery", location_kind="inside", parent_item=child, socket="power")
                    for _ in range(9)]
        expanded, refs, _, large = observations()
        self.assertEqual(expanded[reference], f"{names[-1]} 1")
        self.assertTrue({descriptor(item).reference for item in siblings} <= refs)
        self.assertEqual(small, large)
        print(f"Inside 표시·관찰·장비 Projection SQL (같은 깊이의 자식 1개/10개) {small}/{large}")

    def test_same_inside_name_has_its_own_parent_display_context(self):
        from world.equipment_service import equipment_display
        from world.item_entities.api import carried_items

        parents = [self.create("guard_carbine") for _ in range(2)]
        magazines = [api.create_item("mag_556_standard", location_kind="inside", parent_item=parent, socket="magazine")
                     for parent in parents]
        display = equipment_display(carried_items(self.char1), observed_at=100)
        inside = {str(item.pk): display[str(item.pk)].label for item in magazines}
        self.assertEqual(inside, {str(magazine.pk): f"경비카빈 {number}의 5.56mm 표준탄창"
                                  for number, magazine in enumerate(magazines, 1)})

    def test_number_seven_remains_selectable_in_first_array_position(self):
        rows = [self.create("bandage", quantity=2) for _ in range(7)]
        original = rows[-1]
        for row in rows[:-1]:
            api.delete_item(row)
        self.assertEqual(number_for(descriptor(original).reference), 7)
        self.assertEqual(resolve_item(self.char1, "붕대", "봐").pk, original.pk)
        self.assertEqual(resolve_item(self.char1, "붕대 7", "봐").pk, original.pk)
        self.assertEqual(resolve_item(self.char1, '"붕대" 7', "봐").pk, original.pk)
        with self.assertRaises(RuleError):
            resolve_item(self.char1, "붕대 1", "봐")
        with self.assertRaises(RuleError):
            transfer(self.char1, "붕대 1", recipient=self.char2)
        self.assertEqual(transfer(self.char1, '"붕대" 7', recipient=self.char2), ("bandage", 1))
        original.refresh_from_db()
        self.assertEqual((original.owner_object_id, original.quantity), (self.char1.pk, 1))
        self.assertEqual(number_for(descriptor(original).reference), 7)

    def test_information_declaration_accepts_ordinary_and_quoted_numbers(self):
        from world.actions.resolver import dispatch_text

        first, second = (self.create("bandage", quantity=2) for _ in range(2))
        for command in ('붕대 2', '"붕대" 2'):
            invocation = dispatch_text(self.char1, get_index(), "game.information", command, "정보")
            self.assertEqual(dict(invocation.roles)["subject"], (descriptor(second).reference,))
        self.assertNotEqual(descriptor(first).reference, descriptor(second).reference)

    def test_native_and_role_keep_distinct_all_rules_for_a_canonical_name_and_alias(self):
        from unittest.mock import patch

        from world.actions.global_actions import LOOK_TARGET
        from world.actions.resolver import select_role
        from world.content import ITEMS
        from world.targets import select_native_items

        alias = self.create("flashlight")
        canonical = self.create("bandage")
        reference = descriptor(canonical).reference
        alias_definition = {**ITEMS["flashlight"], "aliases": ("붕대",)}

        with patch.dict(ITEMS, {"flashlight": alias_definition}):
            for query in ("붕-대", "붕대 1", '"붕대" 1'):
                with self.subTest(query=query):
                    self.assertEqual(resolve_item(self.char1, query, "봐").pk, canonical.pk)
                    self.assertEqual(select_role(self.char1, LOOK_TARGET, query), (reference,))

            matches, selector = select_native_items((alias, canonical), "붕대 모두")
            self.assertEqual((matches, selector.mode), ([alias, canonical], Mode.ALL))
            with self.assertRaisesMessage(TargetAmbiguous, "서로 다른 선택 그룹의 별칭이 겹칩니다."):
                select_role(self.char1, LOOK_TARGET, "붕대 모두")

    def test_text_default_keeps_sequence_over_uuid_and_number_order(self):
        from unittest.mock import patch
        from uuid import UUID

        from world.actions.resolver import dispatch_text, role_records, select_role
        from world.item_entities.models import ItemEntity
        from world.selection_numbers import api as numbering

        with patch.object(ItemEntity._meta.pk, "_get_default",
                          side_effect=(UUID(int=3), UUID(int=2), UUID(int=1))):
            hole = self.create("bandage")
            oldest = api.create_item("bandage", location_kind="inventory", owner_object=self.char2)
            newest = self.create("bandage")
        api.delete_item(hole)
        oldest = api.move_item_tree(oldest, location_kind="inventory", owner_object=self.char1)
        original = descriptor(oldest).reference
        later = descriptor(newest).reference
        self.assertLess(oldest.sequence, newest.sequence)
        self.assertGreater(oldest.pk, newest.pk)
        self.assertEqual((number_for(later), number_for(original)), (2, 3))
        role = RoleDefinition("subject", (ReferenceKind.ITEM,), DefaultTargetPolicy.FIRST_LEGACY_ORDER,
                              allow_all=True, definition_ids=("bandage",))
        with patch.object(numbering, "resolve_reference", wraps=numbering.resolve_reference) as lookup:
            result = dispatch_text(self.char1, get_index(), "game.information", "붕대", "정보")
            self.assertEqual(dict(result.roles)["subject"], (original,))
            self.assertFalse(any(call.args[0].kind == ReferenceKind.ITEM for call in lookup.call_args_list))
        self.assertEqual(select_role(self.char1, role, "붕대 2"), (later,))
        self.assertEqual(select_role(self.char1, role, '"붕대" 3'), (original,))
        self.assertEqual(select_role(self.char1, role, "붕대 모두"), (later, original))

        records = role_records(self.char1, role)
        api.move_item_tree(oldest, location_kind="inventory", owner_object=self.char2)
        # 이미 입력된 후보의 실물이 사라졌다면 다른 UUID로 바꾸지 않는다.
        self.assertEqual(select_records(role, records, "붕대"), (original,))
        self.assertEqual(select_role(self.char1, role, "붕대"), (later,))

    def test_mixed_legacy_candidates_compare_item_sequence_and_object_pk(self):
        from evennia import create_object
        from typeclasses.interactables import PersonalLocker

        item = self.create("bandage")
        locker = create_object(PersonalLocker, key="개인 보관함", location=self.char1.location)
        records = (descriptor(locker), descriptor(item))
        role = RoleDefinition("subject", (ReferenceKind.OBJECT, ReferenceKind.ITEM),
                              DefaultTargetPolicy.FIRST_LEGACY_ORDER, required=False)
        expected = item if item.sequence < locker.pk else locker
        self.assertEqual(select_records(role, records, None), (descriptor(expected).reference,))
