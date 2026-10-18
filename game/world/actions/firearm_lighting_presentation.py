"""M04 웹 컨트롤은 실제 UUID를 보존하며 시간·전력은 순수 투영만 한다."""

from world.actions.presentation import reference_json


def item_label(item):
    from dataclasses import replace

    from world.content import ITEMS
    from world.selection_numbers.api import descriptor, label, number_for

    record = descriptor(item)
    return label(replace(record, number=number_for(record.reference))) if record else ITEMS[item.definition_id]["name"]


def render(caller, index, reference, binding, observed_at=None):
    from dataclasses import replace

    from world import firearm_service, lighting
    from world.actions.resolver import role_records
    from world.content import ITEMS
    from world.selection_numbers.api import descriptor, label, number_for, resolve_reference

    provider = resolve_reference(reference)
    action = index.actions[binding.action_id]
    operation = dict(binding.config)["operation"]
    if operation == "fill":
        return fill_controls(caller, index, reference, binding)
    if operation == "reload":
        # 텍스트 자동 선택은 가짜 Source를 만들지 않는다. 웹은 실제 명시 Action으로
        # 투영하여 버튼 생성 시 선택한 Source UUID만 실행하도록 고정한다.
        mapped = "item_ops.load"
        target_binding = next(iter([candidate for candidate in index.bindings_for_provider[binding.provider_definition]
                                    if candidate.action_id == mapped]), None)
        if target_binding is None:
            return []
        controls = render(caller, index, reference, target_binding, observed_at)
        if operation == "reload":
            from world import firearms

            snapshot = firearm_service.firearm_snapshot(provider)
            best = firearms.automatic_magazine(snapshot, firearm_service.compatible_magazines(caller, provider))
            if best is None:
                return []
            controls = [control for control in controls
                        if control["action"]["roles"]["source"][0]["identity"] == best.identity]
        key = index.verbs[action.verb_id].key
        return [{**control, "label": control["label"].rsplit(" · ", 1)[0] + " · " + key}
                for control in controls]
    combat = caller.profile_snapshot().get("combat_target")
    if combat and operation not in ("reload", "load", "light_on", "light_off", "light_status"):
        return []
    if operation in ("light_on", "light_off"):
        from time import time
        state = lighting.project_power(provider.state, time() if observed_at is None else observed_at)
        if (operation == "light_on" and (state["enabled"] or state["remaining_power"] <= 0)
                or operation == "light_off" and not state["enabled"]):
            return []
    if operation == "power_insert":
        from time import time
        if lighting.project_power(provider.state, time() if observed_at is None else observed_at)["remaining_power"] > 0:
            return []
    roles = {"provider": [reference_json(reference)]}
    combinations = [(roles, [])]
    for declaration in action.roles:
        if declaration.name == "provider":
            continue
        refs = {name: tuple([__reference(ref) for ref in entries]) for name, entries in roles.items()}
        candidates = role_records(caller, declaration, refs)
        next_combinations = []
        for record in candidates:
            entity = resolve_reference(record.reference)
            if declaration.name == "source":
                current_magazine = (operation == "load" and entity.location_kind == "inside"
                                    and entity.parent_item_id == provider.pk and entity.socket == "magazine")
                if entity.location_kind != "inventory" and not current_magazine:
                    continue
                if operation in ("reload", "load"):
                    snapshot = firearm_service.magazine_snapshot(entity)
                    if (snapshot.family != firearm_service.firearm_snapshot(provider).family
                            or snapshot.rounds <= 0 and not current_magazine):
                        continue
            for current, targets in combinations:
                target = (resolve_reference(__reference(current["subject"][0]))
                          if "subject" in current else provider)
                if declaration.name == "source":
                    if operation in ("fill", "ammo_insert"):
                        snapshot = firearm_service.magazine_snapshot(target)
                        if (snapshot.rounds >= snapshot.capacity
                                or ITEMS[entity.definition_id].get("ammo_type") != snapshot.ammo_type):
                            continue
                    elif operation == "power_insert":
                        if ITEMS[entity.definition_id]["power_source"]["type"] != ITEMS[provider.definition_id]["light_source"]["power_type"]:
                            continue
                selected_label = label(record)
                if declaration.name == "source" and current_magazine:
                    selected_label += " (현재 삽입)"
                next_combinations.append(({**current, declaration.name: [reference_json(record.reference)]},
                                          [*targets, selected_label]))
        combinations = next_combinations
        if not combinations:
            return []
    record = descriptor(provider)
    target = label(replace(record, number=number_for(reference)))
    defaults = {argument.name: argument.default for argument in action.arguments if argument.default is not None}
    key = index.verbs[action.verb_id].key
    output = []
    for current, targets in combinations:
        if operation == "ammo_remove":
            selected = resolve_reference(__reference(current["subject"][0])) if "subject" in current else provider
            snapshot = firearm_service.magazine_snapshot(selected)
            if snapshot.rounds <= 0 or snapshot.ammo_type != ITEMS[defaults["ammo"]]["ammo_type"]:
                continue
        output.append({"label": " · ".join((target, *targets, key)), "description": action.help,
                       "action": {"action_id": action.id, "variant": "normal", "roles": current, "arguments": defaults}})
    return output


def fill_controls(caller, index, reference, binding):
    """집계 채우기는 단일 안정 Inventory Source와 원래 UUID·수량 집합을 고정한다."""
    from world import firearm_service
    from world.actions.collections import inventory_version
    from world.actions.resolver import role_records
    from world.content import ITEMS
    from world.selection_numbers.api import resolve_reference

    if caller.profile_snapshot().get("combat_target"):
        return []
    action = index.actions[binding.action_id]
    provider = resolve_reference(reference)
    subject = next(iter([role for role in action.roles if role.name == "subject"]), None)
    source = next(iter([role for role in action.roles if role.name == "source"]))
    targets = role_records(caller, subject, {"provider": (reference,)}) if subject else (None,)
    sources = role_records(caller, source)
    if not sources:
        return []
    output = []
    for record in targets:
        target = resolve_reference(record.reference) if record else provider
        snapshot = firearm_service.magazine_snapshot(target)
        if snapshot.rounds >= snapshot.capacity:
            continue
        definitions = tuple([identity for identity, data in ITEMS.items() if data.get("ammo_type") == snapshot.ammo_type])
        version, members = inventory_version(caller, definitions)
        if not members:
            continue
        roles = {"provider": [reference_json(reference)], "source": [reference_json(sources[0].reference)]}
        if record:
            roles["subject"] = [reference_json(record.reference)]
        label = item_label(provider) + (" · " + item_label(target) if record else "") + " · 채워"
        output.append({"label": label, "description": action.help,
                       "action": {"action_id": action.id, "variant": "normal", "roles": roles,
                                  "arguments": {"snapshot": version}}})
    return output


def __reference(value):
    from world.actions.schema import ReferenceKind, TargetReference
    return TargetReference(ReferenceKind(value["kind"]), value["identity"], value["scope_id"])
