"""기존 후치형 Loot 문법을 실제 Source와 영속 Entry 참조로 확정한다."""

from time import time

from django.core import signing
from world import rules
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


def fingerprint(caller, selections, now):
    from typeclasses.loot import can_take_entry

    return {"caller": caller.pk, "party": caller.db.party_id,
            "entries": [[source.pk, str(entry.item_id) if entry.item_id else None, entry.currency_id,
                         entry.quantity, entry.reserved_party, entry.reserved_player, entry.assigned_player,
                         entry.protection_until, [list(share) for share in entry.shares],
                         now < entry.protection_until, bool(can_take_entry(entry.as_entry(), caller, now))]
                        for source, entry in selections]}


def make_invocation(caller, selections, *, quantity=0, now=None, origin="text"):
    now = time() if now is None else now
    if not selections:
        raise rules.RuleError("가져갈 물건이 없거나 다른 탐사자의 보호된 전리품입니다.")
    sources = tuple(dict.fromkeys([descriptor(source).reference for source, _ in selections]))
    subjects = tuple([entry_reference(entry) for _, entry in selections])
    token = signing.dumps(fingerprint(caller, selections, now), salt=SALT, compress=True)
    return ActionInvocation("loot.take", "take", (("provider", sources), ("source", sources),
                            ("subject", subjects)), (("quantity", quantity), ("snapshot", token)), origin)


def resolve(caller, index, action, args, command_name):
    from dataclasses import replace

    from typeclasses.loot import can_take_entry, room_loot
    from world.actions import loot_resolution as clock
    from world.actions.loot_resolution import entry_reference, make_invocation
    from world.actions.resolver import role_records, select_role
    from world.actions.schema import DefaultTargetPolicy, ReferenceKind
    from world.currency import currency_names, currency_request
    from world.lifecycle import reconcile_room
    from world.loot_service import loot_snapshot
    from world.observation import can_inspect_loot, can_perceive, context_for
    from world.selection_numbers.api import descriptor as describe
    from world.selection_numbers.api import number_for
    from world.targets import Mode, loot_parts, parse_loot

    if command_name not in ("가져", "집"):
        return None
    now = clock.time()
    # 전역 카탈로그 별칭은 실제 Scope의 정식 이름보다 먼저 선택하지 않는다.
    _, source_selector = loot_parts(args)
    reconcile_room(caller.location, now)
    context = context_for(caller, observed_at=now)
    if not can_inspect_loot(context):
        raise rules.RuleError("지금은 작은 전리품을 식별할 수 없습니다. 광원을 사용하세요.")
    sources = [source for source in room_loot(caller.location, source_selector is not None)
               if can_perceive(source, context)]
    if source_selector:
        if source_selector.mode == Mode.INDEX:
            sources = [source for source in sources
                       if number_for(describe(source).reference) == source_selector.index]
        elif source_selector.mode != Mode.ALL:
            sources = sources[:1]
    if not sources:
        raise rules.RuleError("지금 선택할 수 없는 전리품 출처입니다.")
    bindings = {"source": tuple([describe(source).reference for source in sources])}
    subject = next(iter([role for role in action.roles if role.name == "subject"]))
    records = role_records(caller, subject, bindings)
    request = parse_loot(args, [name for record in records for name in (record.name, *record.aliases)]
                         + list(currency_names()))
    currency = currency_request(request.target)
    matches = [(source, entry) for source in sources for entry in loot_snapshot(source).entries]
    if request.target.name != "전리품":
        kinds = (ReferenceKind.CURRENCY,) if currency else (ReferenceKind.LOOT,)
        role = replace(subject, kinds=kinds, default=DefaultTargetPolicy.ALL)
        query = "보급칩" if currency else request.target.name
        query += f" {request.target.index}" if request.target.mode == Mode.INDEX else " 모두" if request.target.mode == Mode.ALL else ""
        selected = set(select_role(caller, role, query, bindings=bindings,
                                   candidates={record.reference for record in records}))
        matches = [(source, entry) for source, entry in matches if entry_reference(entry) in selected]
    if request.target.mode != Mode.ALL:
        # 공통 정식 이름/그룹/번호 판정 뒤 기존 Source PK·Entry 순서의 기본값을 보존한다.
        matches = matches[:1]
    else:
        matches = [(source, entry) for source, entry in matches
                   if can_take_entry(entry.as_entry(), caller, now)]
    quantity = 0 if request.target.mode == Mode.ALL else currency[0] if currency else 1
    return make_invocation(caller, matches, quantity=quantity, now=now)
