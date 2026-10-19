"""선택된 안정 참조만 기존 Loot 지급 경계에 전달하는 Adapter."""


from time import time  # noqa: F401 -- callback용 clock과 테스트 관찰 시각

from django.core import signing
from world import rules
from world.actions.gateway import ActionResult


def prepare(caller, invocation):
    from world.actions import loot_services as clock
    from world.lifecycle import reconcile_room

    reconcile_room(caller.location, clock.time())


def lock(caller, invocation):
    from typeclasses.loot import Corpse, DroppedLoot
    from world.loot_service import lock_sources
    from world.selection_numbers.api import resolve_reference

    roles = dict(invocation.roles)
    sources = [resolve_reference(ref) for ref in roles.get("source", ())]
    if not sources or any([not isinstance(source, (Corpse, DroppedLoot)) for source in sources]):
        raise rules.RuleError("전리품 출처가 사라졌습니다.")
    lock_sources(sources, caller)


def take(context):
    from typeclasses.loot import Corpse, can_take_entry
    from world import loot_service
    from world.actions import loot_services as clock
    from world.actions.loot_resolution import SALT, entry_reference, fingerprint
    from world.selection_numbers.api import resolve_reference

    caller, now = context.caller, clock.time()
    refs = dict(context.invocation.roles)["subject"]
    sources = context.roles["source"]
    selections = []
    snapshots = {source.pk: loot_service.loot_snapshot(source) for source in sources}
    for ref in refs:
        entity = resolve_reference(ref)
        source = next(iter([source for source in sources if source.pk == getattr(entity, "owner_object_id", None)]), None)
        if source is None:
            raise rules.RuleError("원래 전리품 출처가 바뀌었습니다.")
        entry = next(iter([entry for entry in snapshots[source.pk].entries if entry_reference(entry) == ref]), None)
        if entry is None or not can_take_entry(entry.as_entry(), caller, now):
            raise rules.RuleError("원래 전리품을 회수할 권한이 없습니다.")
        selections.append((source, entry))
    try:
        expected = signing.loads(context.arguments["snapshot"], salt=SALT, max_age=300)
    except signing.BadSignature:
        raise rules.RuleError("전리품 선택이 만료되었습니다. 다시 확인하세요.") from None
    if expected != fingerprint(caller, selections, now):
        raise rules.RuleError("전리품 수량이나 권리가 바뀌었습니다. 다시 선택하세요.")
    if {source.pk for source, _ in selections} != {source.pk for source in sources}:
        raise rules.RuleError("선택한 전리품과 출처가 일치하지 않습니다.")
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
