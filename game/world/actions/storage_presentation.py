"""Storage 버튼은 현재 접근 가능한 실제 UUID를 전달한다. 조회 중 이동하지 않는다."""

from world.actions.presentation import reference_json, target_label
from world.actions.presentation_context import profile_snapshot


def render(caller, index, reference, binding, observed_at=None):
    from world import item_transfer_native as domain
    from world import rules
    from world.actions.resolver import role_records
    from world.content import ITEMS
    from world.item_entities.models import ItemEntity
    from world.item_entities.policy import can_item_operation
    from world.selection_numbers.api import descriptor, resolve_reference

    provider = resolve_reference(reference)
    try:
        rules.require_peace(profile_snapshot(caller))
        domain.require_container(caller, provider)
    except rules.RuleError:
        return []
    action = index.actions[binding.action_id]
    role = next(iter([role for role in action.roles if role.name == "subject"]))
    records = role_records(caller, role, {"provider": (reference,)})
    items = {str(item.pk): item for item in
             ItemEntity.objects.filter(pk__in=[record.reference.identity for record in records])}
    withdraw = dict(binding.config)["withdraw"]
    output = []
    for record in records:
        label = target_label(caller, record.reference, observed_at)
        if label is None:
            continue
        item = items.get(record.reference.identity)
        current = descriptor(item)
        if (current is None or current.reference != record.reference
                or (not withdraw and item.location_kind != "inventory")
                or not can_item_operation(item, "store")):
            continue
        try:
            domain.require_ownership_transfer(item, caller if withdraw or provider.personal else provider)
        except rules.RuleError:
            continue
        quantities = ("1", "모두") if ITEMS[item.definition_id]["stackable"] and item.quantity > 1 else ("1",)
        for count in quantities:
            output.append({"label": label + (" 스택 전부" if count == "모두" else "") + (" 꺼내" if withdraw else " 넣어"),
                           "description": action.help,
                           "action": {"action_id": action.id, "variant": "normal",
                                      "roles": {"provider": [reference_json(reference)],
                                                "subject": [reference_json(record.reference)]},
                                      "arguments": {"count": count}}})
    return output
