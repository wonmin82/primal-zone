"""기존 후치형 Loot 문법을 실제 Source와 영속 Entry 참조로 확정한다."""

from time import time  # noqa: F401 -- 테스트와 실행 Adapter가 공유하는 관찰 시각

from django.core import signing
from world import rules
from world.actions.loot_errors import LootUnavailable
from world.actions.resolver import ActionInvocation
from world.selection_numbers.api import descriptor

SALT = "primal-zone.loot-selection.v1"


def entry_reference(entry):
    from world.item_entities.models import ItemEntity
    from world.loot_entities.models import CurrencyLoot

    entity = (ItemEntity.objects.filter(pk=entry.item_id).first() if entry.kind == "item"
              else CurrencyLoot.objects.filter(pk=entry.currency_id).first())
    record = descriptor(entity) if entity is not None else None
    if record is None:
        raise rules.RuleError("전리품의 안정 참조를 확인할 수 없습니다.")
    return record.reference


def entry_records(selections):
    """출처와 실제 owner가 일치하는 Entry descriptor를 일괄 읽는다."""
    from world.actions.schema import ReferenceKind
    from world.item_entities.models import ItemEntity
    from world.loot_entities.models import CurrencyLoot

    items = ItemEntity.objects.select_related("owner_object").in_bulk(
        {entry.item_id for _, entry in selections if entry.item_id is not None}
    )
    money = CurrencyLoot.objects.select_related("owner_object").in_bulk(
        {entry.currency_id for _, entry in selections if entry.currency_id is not None}
    )
    records = {}
    for source, entry in selections:
        entity = items.get(entry.item_id) if entry.kind == "item" else money.get(entry.currency_id)
        if entity is not None and entity.owner_object_id == source.pk:
            record = descriptor(entity)
            if record is not None and record.reference.kind in (ReferenceKind.LOOT, ReferenceKind.CURRENCY):
                records[source.pk, entry] = record
    return records


def fingerprint(caller, selections, now):
    from typeclasses.loot import can_take_entry

    return {"caller": caller.pk, "party": caller.db.party_id,
            "entries": [[source.pk, str(entry.item_id) if entry.item_id else None, entry.currency_id,
                         entry.quantity, entry.reserved_party, entry.reserved_player, entry.assigned_player,
                         entry.protection_until, [list(share) for share in entry.shares],
                         now < entry.protection_until, bool(can_take_entry(entry.as_entry(), caller, now))]
                        for source, entry in selections]}


def make_invocation(caller, selections, *, quantity=0, now=None, origin="text", references=None):
    from world.actions import loot_resolution as clock

    now = clock.time() if now is None else now
    if not selections:
        raise rules.RuleError("가져갈 물건이 없거나 다른 탐사자의 보호된 전리품입니다.")
    if references is None:
        sources = tuple(dict.fromkeys([descriptor(source).reference for source, _ in selections]))
        subjects = tuple([entry_reference(entry) for _, entry in selections])
    else:
        sources, subjects = references
    token = signing.dumps(fingerprint(caller, selections, now), salt=SALT, compress=True)
    return ActionInvocation("loot.take", "take", (("provider", sources), ("source", sources),
                            ("subject", subjects)), (("quantity", quantity), ("snapshot", token)), origin)


def resolve(caller, index, action, args, command_name):
    from typeclasses.loot import room_loot
    from world.actions import loot_resolution as clock
    from world.lifecycle import reconcile_room
    from world.loot_service import loot_snapshot
    from world.observation import can_inspect_loot, can_perceive, context_for
    from world.selection_numbers.api import numbered_records
    from world.targets import loot_parts

    if command_name not in ("가져", "집"):
        return None
    now = clock.time()
    # 실행 진입점의 기존 관찰 정합화는 순수 선택과 분리한다.
    parts = loot_parts(args)
    reconcile_room(caller.location, now)
    context = context_for(caller, observed_at=now)
    if not can_inspect_loot(context):
        raise rules.RuleError("지금은 작은 전리품을 식별할 수 없습니다. 광원을 사용하세요.")
    sources = {source.pk: source for source in room_loot(caller.location, parts[1] is not None)
               if can_perceive(source, context)}
    sources_records = {pk: record for pk, source in sources.items() if (record := descriptor(source))}
    numbered_sources = {record.reference: record for record in numbered_records(sources_records.values())}
    sources_records = {pk: numbered_sources.get(record.reference, record) for pk, record in sources_records.items()}
    source_ids = _source_ids(sources_records, parts[1])
    snapshots = {pk: loot_snapshot(sources[pk]) for pk in source_ids}
    assets = entry_records([(sources[pk], entry) for pk, snapshot in snapshots.items()
                            if snapshot.native for entry in snapshot.entries])
    valid = {record.reference: record for record in numbered_records(assets.values())}
    entries = {pk: [(entry, asset.reference if (asset := assets.get((pk, entry))) else None)
                    for entry in snapshot.entries] for pk, snapshot in snapshots.items()}
    selected, quantity = select_loot(
        caller, args, now=now, sources=sources_records, entries=entries,
        records=[valid.get(record.reference, record) for record in assets.values()], parts=parts,
    )
    selected_sources = tuple(dict.fromkeys([sources_records[pk].reference for pk, _ in selected]))
    selected_entries = tuple([assets[pk, entry].reference for pk, entry in selected])
    return make_invocation(caller, [(sources[pk], entry) for pk, entry in selected], quantity=quantity, now=now,
                           references=(selected_sources, selected_entries))


def _source_ids(sources, selector):
    from world.actions.resolver import matching_records
    from world.actions.schema import ReferenceKind
    from world.targets import Mode

    source_kind = ReferenceKind.CORPSE if selector else ReferenceKind.OBJECT
    source_ids = [pk for pk, record in sources.items() if record.reference.kind == source_kind]
    if selector:
        if selector.mode == Mode.INDEX:
            refs = {record.reference for record in matching_records([sources[pk] for pk in source_ids], selector)}
            source_ids = [pk for pk in source_ids if sources[pk].reference in refs]
        elif selector.mode != Mode.ALL:
            source_ids = source_ids[:1]
    if not source_ids:
        raise rules.RuleError("지금 선택할 수 없는 전리품 출처입니다.")
    return source_ids


def select_loot(caller, args, *, now, sources, entries, records, accessible=None, parts=None):
    """현재 Source와 Entry Snapshot에서 효과 없이 전체 선택과 수량을 계산한다."""
    from typeclasses.loot import can_take_entry
    from world.actions.resolver import TargetAmbiguous, matching_records
    from world.actions.schema import ReferenceKind
    from world.currency import currency_names, currency_request
    from world.targets import Mode, loot_parts, loot_request

    query, source_selector = loot_parts(args) if parts is None else parts
    source_ids = _source_ids(sources, source_selector)
    matches = [(pk, entry, ref) for pk in source_ids for entry, ref in entries.get(pk, ())]
    by_ref = {record.reference: record for record in records}
    if accessible is None:
        accessible = {ref for _, entry, ref in matches if can_take_entry(entry.as_entry(), caller, now)}
    selected_refs = {ref for _, _, ref in matches}
    scoped = [record for ref, record in by_ref.items() if ref in selected_refs]
    visible = [record for record in scoped if record.reference in accessible]
    request = loot_request(query, source_selector,
                           [name for record in visible for name in (record.name, *record.aliases)] + list(currency_names()),
                           literal_names=[record.name for record in visible])
    selector = request.target
    currency = None if selector.exact else currency_request(selector)
    if selector.exact or (selector.name, selector.mode) != ("전리품", Mode.ALL):
        from dataclasses import replace

        if not selector.exact:
            kind = ReferenceKind.CURRENCY if currency else ReferenceKind.LOOT
            scoped = [record for record in scoped if record.reference.kind == kind]
        if currency:
            selector = replace(selector, name="보급칩")
        try:
            selected = {record.reference for record in matching_records(scoped, selector)}
        except TargetAmbiguous:
            # 같은 오류가 공개 후보에서도 발생할 때만 구체적인 모호성 오류를 보여 준다.
            matching_records([record for record in scoped if record.reference in accessible], selector)
            raise LootUnavailable() from None
        matches = [(pk, entry, ref) for pk, entry, ref in matches if ref in selected]
    if selector.mode != Mode.ALL:
        matches = matches[:1]
    else:
        matches = [(pk, entry, ref) for pk, entry, ref in matches
                   if ref in accessible or (ref is None and can_take_entry(entry.as_entry(), caller, now))]
    if not matches:
        if (selector.name, selector.mode) == ("전리품", Mode.ALL):
            raise rules.RuleError("가져갈 물건이 없거나 다른 탐사자의 보호된 전리품입니다.")
        raise LootUnavailable()
    for pk, _, ref in matches:
        if sources[pk].number is None or (record := by_ref.get(ref)) is None or record.number is None:
            raise LootUnavailable()
    quantity = 0 if selector.mode == Mode.ALL else currency[0] if currency else 1
    return [(pk, entry) for pk, entry, _ in matches], quantity
