"""현재 상태를 읽기만 하는 아이템 Action controls. UUID payload는 공통 경계를 쓴다."""

from world.actions.presentation import reference_json, target_label
from world.actions.presentation_context import profile_snapshot, scoped_reads


def render(caller, index, reference, binding, observed_at=None):
    operation = dict(binding.config)["operation"]
    if operation.startswith("advise_"):
        return []
    items = scoped_reads(caller, observed_at)
    item = items.resolve_entity(reference)
    if item is None or item.owner_object_id != caller.pk or item.parent_item_id or item.location_kind not in ("inventory", "equipment"):
        return []
    target = target_label(caller, reference, observed_at)
    if target is None:
        return []
    if operation == "inside_information":
        from world.actions.resolver import role_records

        action = index.actions[binding.action_id]
        subject = next(iter([role for role in action.roles if role.name == "subject"]))
        children = role_records(caller, subject, {"provider": (reference,)},
                                cache=items.records, item_entities=items.entities)
        controls = []
        for child in children:
            child_label = target_label(caller, child.reference, observed_at)
            if child_label is None:
                continue
            controls.append({"label": target + "의 " + child_label + " 정보",
                             "action": {"action_id": action.id, "variant": "normal",
                                        "roles": {"provider": [reference_json(reference)],
                                                  "subject": [reference_json(child.reference)]},
                                        "arguments": {"count": "1"}}})
        return controls
    if operation in ("equip", "wield") and item.location_kind != "inventory":
        return []
    if operation in ("remove", "unwield", "active_weapon") and item.location_kind != "equipment":
        return []
    if operation in ("use", "eat", "drink") and item.location_kind != "inventory":
        return []
    if operation not in ("information", "use") and profile_snapshot(caller).get("combat_target"):
        return []
    action = index.actions[binding.action_id]
    key = index.verbs[action.verb_id].key
    refs = [reference_json(reference)]
    return [{"label": target + " " + key, "action": {"action_id": action.id, "variant": "normal",
             "roles": {"provider": refs, "subject": refs}, "arguments": {"count": "1"}}}]
