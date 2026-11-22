"""공개 후보에서 표시와 실행용 선택 문자열을 각각 계산한다."""

from collections import defaultdict
from dataclasses import dataclass

from world.targets import normalized


def displays(records, *, same_context=False, other_names=()):
    from world.rules import RuleError
    from world.targets import exact_selector, parse_selector

    records = tuple(records)
    occupied = {normalized(name) for name in other_names}
    names = defaultdict(set)
    aliases = defaultdict(set)
    candidates = defaultdict(set)
    initial = {}
    for record in records:
        scope = None if same_context else record.scope_id
        names[scope, normalized(record.name)].add(record.reference)
        for name in (*record.aliases, *record.unique_names):
            aliases[scope, normalized(name)].add(record.reference)
    for record in records:
        scope = None if same_context else record.scope_id
        name = record.name
        if len(names[scope, normalized(name)]) > 1 and record.number is not None:
            name = f"{name} {record.number}"
        initial[record.reference] = name
        candidates[scope, normalized(name)].add(record.reference)
    result = {}
    for record in records:
        ref = record.reference
        scope = None if same_context else record.scope_id
        name = initial[ref]
        key = (scope, normalized(name))
        try:
            reserved = parse_selector(name, b1=True).exact
        except RuleError:
            reserved = False
        # 실제 이름은 다른 객체의 번호 표기와 별칭에 앞선다.
        sole_literal = names[key] == {ref} and name == record.name
        collides = normalized(name) in occupied or (
            not sole_literal and bool((names[key] | aliases[key] | candidates[key]) - {ref}))
        if record.number is None:
            result[ref] = None
        elif reserved or collides:
            result[ref] = exact_selector(record.name, record.number)
        else:
            result[ref] = name
    return result


def selection_text(record, resolve):
    """실제 문맥의 Resolver가 같은 참조 하나를 반환하는 표기만 제공한다."""
    from world.rules import RuleError
    from world.targets import exact_selector

    if record is None or record.number is None:
        return None
    for text in (record.name, f"{record.name} {record.number}", exact_selector(record.name, record.number)):
        try:
            if tuple(resolve(text)) == (record.reference,):
                return text
        except RuleError:
            continue
    return None


@dataclass(frozen=True)
class RoomSnapshot:
    labels: dict
    records: dict
    references: dict


def room_snapshot(caller, observed_at=None, *, objects=None):
    from django.db.models import Q
    from typeclasses.loot import DroppedLoot

    from world.actions.schema import ReferenceKind
    from world.door_entities.models import Door
    from world.observation import context_for, perceives
    from world.selection_numbers.api import descriptor, numbered_records
    from world.targets import room_objects

    objects = tuple(room_objects(caller, observed_at=observed_at) if objects is None else objects)
    endpoints = {obj.pk for obj in objects if obj.db_destination_id}
    doors_by_endpoint = {}
    if endpoints:
        for door in Door.objects.filter(Q(exit_a_id__in=endpoints) | Q(exit_b_id__in=endpoints)).order_by("pk"):
            doors_by_endpoint.setdefault(door.exit_a_id, door)
            doors_by_endpoint.setdefault(door.exit_b_id, door)
    by_id = {obj.pk: record for obj in objects if (record := descriptor(obj, doors_by_endpoint=doors_by_endpoint))
             and record.reference.kind != ReferenceKind.ROOM}
    doors = [pk for pk, record in by_id.items() if record.reference.kind == ReferenceKind.DOOR]
    if doors and not perceives(context_for(caller, observed_at=observed_at).snapshot, "normal"):
        for pk in doors:
            del by_id[pk]
    valid = {record.reference: record for record in numbered_records(by_id.values())}
    rendered = displays(
        [valid.get(record.reference, record) for obj in objects
         if (record := by_id.get(obj.pk)) and not isinstance(obj, DroppedLoot)],
        same_context=True,
        other_names=[obj.key for obj in objects if obj.pk not in by_id],
    )
    labels = {obj.pk: obj.key for obj in objects if obj.pk not in by_id}
    for obj in objects:
        if obj.pk in by_id:
            reference = by_id[obj.pk].reference
            labels[obj.pk] = obj.get_display_name(caller) if isinstance(obj, DroppedLoot) else rendered[reference]
    return RoomSnapshot(
        labels,
        valid,
        {pk: record.reference for pk, record in by_id.items() if record.reference in valid},
    )


def action_command(caller, records, verb, arguments):
    """현재 동사의 Dispatcher로 안내에 지정한 역할 전체를 확인한다."""
    from itertools import product

    if any(record is None or record.number is None for record in records.values()):
        return None
    from world.actions.manifest import get_index
    from world.actions.resolver import dispatch_text
    from world.rules import RuleError
    from world.targets import exact_selector

    index = get_index()
    verb_id = next(iter([item.id for item in index.verbs.values() if item.key == verb]), None)
    if verb_id is None:
        return None

    candidates = [(record.name, f"{record.name} {record.number}", exact_selector(record.name, record.number))
                  for record in records.values()]
    for selections in product(*candidates):
        args = arguments(*selections)
        try:
            invocation = dispatch_text(caller, index, verb_id, args, verb)
        except RuleError:
            continue
        actual = dict(invocation.roles)
        if all(actual.get(role) == (record.reference,) for role, record in records.items()):
            return f"{args} {verb}"
    return None


def provider_command(caller, record, verb, arguments):
    return action_command(caller, {"provider": record}, verb, arguments)
