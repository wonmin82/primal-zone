"""선택된 안정 참조만 기존 Loot 지급 경계에 전달하는 Adapter."""


from time import time  # noqa: F401 -- callback용 clock과 테스트 관찰 시각

from django.core import signing
from world import rules
from world.actions.gateway import ActionResult
from world.actions.loot_errors import LootUnavailable


def prepare(caller, invocation):
    from world.actions import loot_services as clock
    from world.lifecycle import reconcile_room

    reconcile_room(caller.location, clock.time())


def lock(caller, invocation):
    from typeclasses.loot import Corpse, DroppedLoot
    from world.loot_service import lock_sources
    from world.selection_numbers.api import resolve_references

    roles = dict(invocation.roles)
    refs = roles.get("source", ())
    resolved = resolve_references(refs)
    sources = [resolved.get(ref) for ref in refs]
    if not sources or any([not isinstance(source, (Corpse, DroppedLoot)) for source in sources]):
        raise LootUnavailable()
    lock_sources(sources, caller)


def take(context):
    from django.utils.crypto import constant_time_compare
    from typeclasses.loot import Corpse, can_take_entry
    from world import loot_service
    from world.actions import loot_services as clock
    from world.actions.loot_resolution import (
        SALT,
        fingerprint,
        read_loot_rights,
        snapshot_entry,
        snapshot_entry_index,
    )

    caller, now = context.caller, clock.time()
    sources = context.roles["source"]
    by_owner = {source.pk: source for source in sources}
    selections = []
    entries = snapshot_entry_index(sources)
    for entity in context.roles["subject"]:
        source = by_owner.get(entity.owner_object_id)
        entry = snapshot_entry(entries, entity)
        if source is None or entry is None:
            raise LootUnavailable()
        selections.append((source, entry))
    party, recipients = read_loot_rights(caller, [entry for _, entry in selections], now)
    if any([not can_take_entry(entry.as_entry(), caller, now, party=party, recipients=recipients)
            for _, entry in selections]):
        raise LootUnavailable()
    try:
        snapshot = signing.loads(context.arguments["snapshot"], salt=SALT, max_age=300)
    except signing.BadSignature:
        raise rules.RuleError("전리품 선택이 만료되었습니다. 다시 확인하세요.") from None
    nonce, _, expected = snapshot.partition(".") if isinstance(snapshot, str) else ("", "", "")
    if len(nonce) != 32 or len(expected) != 64:
        raise rules.RuleError("전리품 선택이 만료되었습니다. 다시 확인하세요.")
    current = fingerprint(caller, selections, now, nonce=nonce, party=party, recipients=recipients)
    if not constant_time_compare(expected, current):
        raise rules.RuleError("전리품 수량이나 권리가 바뀌었습니다. 다시 선택하세요.")
    if {source.pk for source, _ in selections} != {source.pk for source in sources}:
        raise LootUnavailable()
    received = []
    recovered = 0
    for source, entry in selections:
        quantity = context.arguments["quantity"] or entry.quantity
        received.extend(loot_service.pickup(source, entry, caller, quantity, now=now, locked=True))
        if entry.kind == "currency":
            recovered += quantity
    for source in sources:
        if not isinstance(source, Corpse) and not loot_service.loot_snapshot(source).entries:
            source.delete()
    loot_service.notify_pickup(caller, received, corpse=all([isinstance(source, Corpse) for source in sources]),
                               recovered_currency=recovered)
    return ActionResult(changed=True)
