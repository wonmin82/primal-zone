"""현재 상태를 읽기만 하는 아이템 Action controls. UUID payload는 공통 경계를 쓴다."""

from world.actions.presentation import reference_json


def render(caller, index, reference, binding, observed_at=None):
    from dataclasses import replace

    from world.selection_numbers.api import descriptor, label, number_for, resolve_reference

    item = resolve_reference(reference)
    operation = dict(binding.config)["operation"]
    if operation.startswith("advise_"):
        return []
    if item is None or item.owner_object_id != caller.pk or item.parent_item_id or item.location_kind not in ("inventory", "equipment"):
        return []
    if operation == "inside_information":
        from world.actions.resolver import role_records

        action = index.actions[binding.action_id]
        subject = next(iter([role for role in action.roles if role.name == "subject"]))
        children = role_records(caller, subject, {"provider": (reference,)})
        root_record = descriptor(item)
        root_label = label(replace(root_record, number=number_for(reference)))
        controls = []
        for child in children:
            controls.append({"label": root_label + "의 " + label(child) + " 정보",
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
    if operation not in ("information", "use") and caller.profile_snapshot().get("combat_target"):
        return []
    record = descriptor(item)
    target = label(replace(record, number=number_for(reference)))
    action = index.actions[binding.action_id]
    key = index.verbs[action.verb_id].key
    refs = [reference_json(reference)]
    return [{"label": target + " " + key, "action": {"action_id": action.id, "variant": "normal",
             "roles": {"provider": refs, "subject": refs}, "arguments": {"count": "1"}}}]
