"""M04 웹 컨트롤은 실제 UUID를 보존하며 시간·전력은 순수 투영만 한다."""

from world.actions.presentation import reference_json, target_label
from world.actions.presentation_context import item_presentation, profile_snapshot


def item_label(item, caller=None):
    from world.content import ITEMS
    from world.selection_numbers.api import descriptor

    record = descriptor(item) if caller is not None else None
    return (target_label(caller, record.reference) if record else None) or ITEMS[item.definition_id]["name"]


def render(caller, index, reference, binding, observed_at=None):
    view = item_presentation(caller, observed_at)
    return _controls(caller, index, reference, binding, observed_at, view)


def _controls(caller, index, reference, binding, observed_at, view):
    operation = dict(binding.config)["operation"]
    if operation == "load":
        return view.read(("load", reference, binding.id),
                         lambda: _render(caller, index, reference, binding, observed_at, view, operation))
    return _render(caller, index, reference, binding, observed_at, view, operation)


def _magazine(view, item):
    from world.firearm_service import magazine_snapshot

    return view.read(("magazine", item.pk), lambda: magazine_snapshot(item))


def _firearm(view, item):
    from world.firearm_service import firearm_snapshot

    def magazine(firearm):
        mounted = view.loaded_magazine_item(firearm)
        return _magazine(view, mounted) if mounted is not None else None

    return view.read(("firearm", item.pk), lambda: firearm_snapshot(item, read_magazine=magazine))


def _role(caller, declaration, bindings, view):
    from world.actions.resolver import role_records

    return role_records(caller, declaration, bindings, cache=view.records, item_entities=view.entities)


def _render(caller, index, reference, binding, observed_at, view, operation):
    from world import firearm_service, lighting
    from world.content import ITEMS

    provider = view.item(reference)
    target_name = target_label(caller, reference, observed_at)
    if provider is None or target_name is None:
        return []
    action = index.actions[binding.action_id]
    if operation == "fill":
        return fill_controls(caller, action, reference, provider, target_name, observed_at, view)
    if operation == "reload":
        from copy import deepcopy

        # 텍스트 자동 선택은 가짜 Source를 만들지 않는다. 웹은 실제 명시 Action으로
        # 투영하여 버튼 생성 시 선택한 Source UUID만 실행하도록 고정한다.
        mapped = "item_ops.load"
        target_binding = next(iter([candidate for candidate in index.bindings_for_provider[binding.provider_definition]
                                    if candidate.action_id == mapped]), None)
        if target_binding is None:
            return []
        from world import firearms

        controls = _controls(caller, index, reference, target_binding, observed_at, view)
        snapshot = _firearm(view, provider)
        compatible = view.read(("compatible", snapshot.family),
                               lambda: firearm_service.compatible_magazines(caller, provider, snapshot=snapshot))
        best = firearms.automatic_magazine(snapshot, compatible)
        if best is None:
            return []
        key = index.verbs[action.verb_id].key
        return [{**deepcopy(control), "label": control["label"].rsplit(" · ", 1)[0] + " · " + key}
                for control in controls if control["action"]["roles"]["source"][0]["identity"] == best.identity]
    combat = profile_snapshot(caller).get("combat_target")
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
    combinations = [(roles, [], provider)]
    for declaration in action.roles:
        if declaration.name == "provider":
            continue
        candidates = _role(caller, declaration, {"provider": (reference,)}, view)
        next_combinations = []
        for record in candidates:
            selected_label = target_label(caller, record.reference, observed_at)
            entity = view.item(record.reference)
            if selected_label is None or entity is None:
                continue
            if declaration.name == "source":
                current_magazine = (operation == "load" and entity.location_kind == "inside"
                                    and entity.parent_item_id == provider.pk and entity.socket == "magazine")
                if entity.location_kind != "inventory" and not current_magazine:
                    continue
                if operation in ("reload", "load"):
                    snapshot = _magazine(view, entity)
                    if (snapshot.family != _firearm(view, provider).family
                            or snapshot.rounds <= 0 and not current_magazine):
                        continue
            if declaration.name == "source" and current_magazine:
                selected_label += " (현재 삽입)"
            for current, targets, target in combinations:
                if declaration.name == "source":
                    if operation in ("fill", "ammo_insert"):
                        snapshot = _magazine(view, target)
                        if (snapshot.rounds >= snapshot.capacity
                                or ITEMS[entity.definition_id].get("ammo_type") != snapshot.ammo_type):
                            continue
                    elif operation == "power_insert":
                        if ITEMS[entity.definition_id]["power_source"]["type"] != ITEMS[provider.definition_id]["light_source"]["power_type"]:
                            continue
                next_combinations.append(({**current, declaration.name: [reference_json(record.reference)]},
                                          [*targets, selected_label],
                                          entity if declaration.name == "subject" else target))
        combinations = next_combinations
        if not combinations:
            return []
    defaults = {argument.name: argument.default for argument in action.arguments if argument.default is not None}
    key = index.verbs[action.verb_id].key
    output = []
    for current, targets, target in combinations:
        if operation == "ammo_remove":
            snapshot = _magazine(view, target)
            if snapshot.rounds <= 0 or snapshot.ammo_type != ITEMS[defaults["ammo"]]["ammo_type"]:
                continue
        output.append({"label": " · ".join((target_name, *targets, key)), "description": action.help,
                       "action": {"action_id": action.id, "variant": "normal", "roles": current, "arguments": defaults}})
    return output


def fill_controls(caller, action, reference, provider, provider_label, observed_at, view):
    """집계 채우기는 단일 안정 Inventory Source와 원래 UUID·수량 집합을 고정한다."""
    from world.actions.collections import inventory_version
    from world.content import ITEMS

    if profile_snapshot(caller).get("combat_target"):
        return []
    subject = next(iter([role for role in action.roles if role.name == "subject"]), None)
    source = next(iter([role for role in action.roles if role.name == "source"]))
    targets = _role(caller, subject, {"provider": (reference,)}, view) if subject else (None,)
    sources = _role(caller, source, None, view)
    if not sources:
        return []
    output = []
    for record in targets:
        target = view.item(record.reference) if record else provider
        child_label = target_label(caller, record.reference, observed_at) if record else None
        if target is None or (record and child_label is None):
            continue
        snapshot = _magazine(view, target)
        if snapshot.rounds >= snapshot.capacity:
            continue
        definitions = tuple([identity for identity, data in ITEMS.items() if data.get("ammo_type") == snapshot.ammo_type])
        version, members = view.read(("inventory_version", definitions), lambda: inventory_version(caller, definitions))
        if not members:
            continue
        roles = {"provider": [reference_json(reference)], "source": [reference_json(sources[0].reference)]}
        if record:
            roles["subject"] = [reference_json(record.reference)]
        label = provider_label + (" · " + child_label if record else "") + " · 채워"
        output.append({"label": label, "description": action.help,
                       "action": {"action_id": action.id, "variant": "normal", "roles": roles,
                                  "arguments": {"snapshot": version}}})
    return output
