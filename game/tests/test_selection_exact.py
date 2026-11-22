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
    def test_same_inside_name_has_its_own_parent_display_context(self):
        from world.equipment_service import entity_snapshot

        parents = [self.create("guard_carbine") for _ in range(2)]
        magazines = [api.create_item("mag_556_standard", location_kind="inside", parent_item=parent, socket="magazine")
                     for parent in parents]
        snapshot = entity_snapshot(self.char1)
        inside = {item.identity: snapshot.label(item) for item in snapshot.carried if item.location == "inside"}
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
