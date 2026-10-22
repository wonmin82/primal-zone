"""M01/M02 서비스의 순수 화면. 실행 문장을 만들지 않고 안정 참조를 전달한다."""

from world.actions.presentation import reference_json
from world.actions.presentation_context import available, profile_snapshot


def render(caller, index, reference, binding, observed_at=None):
    from world import rules
    from world.actions.resolver import role_records
    from world.content import ITEMS
    from world.selection_numbers.api import resolve_reference

    action = index.actions[binding.action_id]
    provider = resolve_reference(reference)
    config = dict(binding.config)
    if not available(provider, caller, observed_at):
        return []
    if profile_snapshot(caller).get("combat_target"):
        return []
    if reference.kind == "door":
        from world import doors
        target = next(iter([target for target in doors.current_doors(caller, observed_at) if target.exit_pk == provider.pk]), None)
        if target is None or config["operation"] not in {a["label"] for a in doors.actions_for(caller, target, observed_at)}:
            return []
    defaults = {arg.name: arg.default for arg in action.arguments if arg.default is not None}
    if binding.provider_definition.startswith("skill."):
        if not rules.skill_state(profile_snapshot(caller), defaults["value"])["can_learn"]:
            return []
    if binding.provider_definition.startswith("attribute."):
        profile = profile_snapshot(caller)
        if rules.point_pools(profile)["attribute_points"] < 1 or rules.allocated(profile, defaults["value"]) >= 20:
            return []
    if config.get("effect") == "doctor":
        try:
            restored, cost = provider.quote(caller)
        except rules.RuleError:
            return []
    roles = {"provider": [reference_json(reference)]}
    subjects = next(iter([role for role in action.roles if role.name == "subject"]), None)
    candidates = role_records(caller, subjects) if subjects else (None,)
    if action.verb_id == "game.exchange":
        from world.actions.collections import inventory_version
        source = next(iter([role for role in action.roles if role.name == "source"]))
        version, members = inventory_version(caller, source.definition_ids)
        if not members:
            return []
        roles["source"] = [reference_json(record.reference) for record in role_records(caller, source)]
        defaults["snapshot"] = version
        candidates = (None,)
    if subjects and not subjects.required and not candidates:
        candidates = (None,)
    output = []
    for record in candidates:
        args = dict(defaults)
        current_roles = dict(roles)
        key = index.verbs[action.verb_id].key
        label = key
        if config.get("effect") == "doctor":
            label = f"HP {restored} 회복 · 예상 {cost}칩"
        elif action.verb_id == "game.exchange":
            label = "회수부품 모두 교환" if "value" not in defaults else "회수부품 교환"
        if record:
            from world.item_entities.policy import can_item_operation
            from world.selection_numbers.api import label as target_label
            item = resolve_reference(record.reference)
            operation = "burn" if key == "소각" else "sell"
            if key != "가치" and (item.location_kind != "inventory" or not can_item_operation(item, operation)):
                continue
            current_roles["subject"] = [reference_json(record.reference)]
            label = target_label(record) + " " + key
            if key == "팔아":
                from world.currency import format_currency
                from world.shop_service import resale

                price = resale(item)
                label = f"{target_label(record)} · {format_currency(price)} 팔아"
        elif "value" in defaults and defaults["value"] in ITEMS:
            label = ITEMS[defaults["value"]]["name"] + " " + key
            if key == "사":
                from world.currency import format_currency
                identity = defaults["value"]
                unit = f" ×{ITEMS[identity]['purchase_quantity']}발" if ITEMS[identity].get("purchase_quantity", 1) != 1 else ""
                label = f"{ITEMS[identity]['name']}{unit} · {format_currency(rules.purchase_price(identity))} 사"
        elif "value" in defaults:
            from world.progression import ATTRIBUTES, SKILLS
            name = (SKILLS.get(defaults["value"]) or ATTRIBUTES.get(defaults["value"]) or {}).get("name", {"all": "전체", "skills": "기술", "attributes": "특성"}.get(defaults["value"], ""))
            label = name + " " + key
            if key == "배분":
                label = name + " +1 배분"
        if action.verb_id == "game.exchange":
            label = "회수부품 모두 교환" if "value" not in defaults else "회수부품 교환"
        for variant in action.variants:
            if variant.confirmation_required or not variant.show_control:
                continue
            output.append({"label": label, "description": action.help,
                           "action": {"action_id": action.id, "variant": variant.id,
                                      "roles": current_roles, "arguments": args}})
            if record and "count" in args and item.quantity > 1 and ITEMS[item.definition_id]["stackable"]:
                all_label = (f"{target_label(record)} 모두 팔아 · 총 {format_currency(item.quantity * price)}"
                             if key == "팔아" else label.replace(" " + key, " 모두 " + key))
                output.append({"label": all_label, "description": action.help,
                               "action": {"action_id": action.id, "variant": variant.id,
                                          "roles": current_roles, "arguments": {**args, "count": "모두"}}})
    return output


def sort_controls(provider, rows):
    """기존 상점의 목록→catalog 순서→판매 순서를 유지한다."""
    from world.actions.manifest import get_index
    from world.content import SHOP_CATALOGS

    catalog = SHOP_CATALOGS.get(provider.db.shop_id, {}).get("purchase_catalog", ())
    index = get_index()

    def order(row):
        invocation = row.get("action", {})
        definition = index.actions.get(invocation.get("action_id"))
        if definition is None:
            return (10000, "")
        if definition.verb_id == "game.list":
            return (0, "")
        value = invocation.get("arguments", {}).get("value")
        if value in catalog and definition.verb_id in ("game.buy", "game.value"):
            return (1 + 2 * catalog.index(value) + (definition.verb_id == "game.value"), "")
        return (1000, invocation.get("action_id", ""))

    return sorted(rows, key=order)


def controls_for(caller, provider, observed_at=None):
    from typeclasses.interactables import Container
    from world.actions.manifest import get_index
    from world.actions.presentation import action_controls
    from world.selection_numbers.api import descriptor

    if isinstance(provider, Container):
        return [{"label": "봐", "command": provider.key + " 봐"}]
    record = descriptor(provider)
    if not record:
        return []
    serialized = reference_json(record.reference)
    rows = [control for control in action_controls(caller, get_index(), observed_at)
            if control["action"]["roles"].get("provider") == [serialized]]
    return sort_controls(provider, rows)
