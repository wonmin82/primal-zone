"""Storage 버튼은 현재 접근 가능한 실제 UUID를 전달한다. 조회 중 이동하지 않는다."""

from world.actions.presentation import ItemActionControl, target_label
from world.actions.presentation_context import (
    item_presentation,
    observation_snapshot,
    profile_snapshot,
)


def render(caller, index, reference, binding, observed_at=None):
    from world import item_transfer_native as domain
    from world import rules
    from world.actions.resolver import role_records
    from world.content import ITEMS
    from world.item_entities.policy import can_item_operation
    from world.selection_numbers.api import descriptor

    items = item_presentation(caller, observed_at)
    provider = items.item(reference)

    def observation():
        return observation_snapshot(caller, observed_at)

    try:
        rules.require_peace(profile_snapshot(caller))
        domain.require_container(caller, provider, get_observation=observation)
    except rules.RuleError:
        return []
    action = index.actions[binding.action_id]
    role = next(iter([role for role in action.roles if role.name == "subject"]))
    records = role_records(caller, role, {"provider": (reference,)},
                           cache=items.records, item_entities=items.entities, provider_entities=items.entities,
                           get_observation=observation)
    withdraw = dict(binding.config)["withdraw"]
    candidates = []
    for record in records:
        label = target_label(caller, record.reference, observed_at)
        if label is None:
            continue
        item = items.entities.get(record.reference)
        current = descriptor(item)
        if (current is None or current.reference != record.reference
                or (not withdraw and item.location_kind != "inventory")
                or not can_item_operation(item, "store")):
            continue
        candidates.append((record, label, item))

    destination = caller if withdraw or provider.personal else provider
    transfers = [item for _, _, item in candidates if item.owner_object_id != destination.pk]
    children = items.read(
        ("ownership_transfer_children", frozenset({item.pk for item in transfers})),
        lambda: domain.ownership_transfer_children(transfers),
    ) if transfers else None
    output = []
    for record, label, item in candidates:
        try:
            domain.require_ownership_transfer(item, destination, children=children)
        except rules.RuleError:
            continue
        quantities = ("1", "모두") if ITEMS[item.definition_id]["stackable"] and item.quantity > 1 else ("1",)
        for count in quantities:
            control_label = label + (" 스택 전부" if count == "모두" else "") + (" 꺼내" if withdraw else " 넣어")
            output.append(ItemActionControl(control_label, action.help, action.id, "normal",
                                            reference, record, count))
    return output
