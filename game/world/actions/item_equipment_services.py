"""선택한 UUID 하나만 도메인에 전달하는 동기 실행 경계."""

from world.actions.gateway import ActionResult


def execute(context):
    from world import equipment_service as equipment
    from world import rules
    from world import text as ft
    from world.content import ITEMS
    from world.item_entities import api

    item = context.roles["subject"][0]
    operation = context.config["operation"]
    if context.arguments["count"] not in ("1", "1개"):
        raise rules.RuleError("이 행동은 한 번에 하나의 아이템만 선택하세요.")
    if operation == "inside_information":
        from world.item_information import information_for_item

        return ActionResult(messages=(information_for_item(context.caller, item, parent=context.roles["provider"][0]),))
    if item.owner_object_id != context.caller.pk or item.location_kind not in ("inventory", "equipment") or item.parent_item_id:
        raise rules.RuleError("직접 소지하거나 장착한 자신의 아이템만 선택하세요.")
    if operation.startswith("advise_"):
        correct = {"advise_equip": "무장", "advise_remove": "해제", "advise_wield": "착용", "advise_unwield": "벗어"}[operation]
        raise rules.RuleError(f"이 장비에는 '{ITEMS[item.definition_id]['name']} {correct}' 명령을 사용하세요.")
    if operation not in ("information", "active_weapon"):
        api._check_tree_operation(item, (), "consume" if operation in ("use", "eat", "drink") else
                                  "equip" if operation in ("equip", "wield") else "unequip")
    label = equipment.selector_label(context.caller, item)
    if operation == "information":
        from world.item_information import information_for_item

        return ActionResult(messages=(information_for_item(context.caller, item),))
    if operation == "use":
        from world import skill_services

        skill_services.use_support(context.caller, "bandage", item=item)
        return ActionResult(changed=True)
    if operation in ("eat", "drink"):
        from world.item_inventory import bind_consumption

        def apply(profile):
            if not bind_consumption(context.caller, profile, item.definition_id, item.pk):
                raise rules.RuleError("원래 선택한 아이템이 없어졌거나 위치가 바뀌었습니다.")
            return rules.eat_or_drink(profile, item.definition_id, "먹어" if operation == "eat" else "마셔")

        amount = context.caller.change(apply)
        message = ft.text(ft.token("item", label), ft.particle(ITEMS[item.definition_id]["name"], "을/를"),
                          " 먹었다." if operation == "eat" else " 마셨다.", f" 체력이 {amount} 회복되었다.")
    elif operation == "active_weapon":
        equipment.set_active_weapon(context.caller, item)
        message = "주무기를 지정했다."
    else:
        remove = operation in ("remove", "unwield")
        slot = "weapon" if operation in ("wield", "unwield") else "armor"
        (equipment.unequip_item if remove else equipment.equip_item)(context.caller, item, slot)
        key = {"equip": "착용했다.", "wield": "무장했다.", "remove": "벗었다.", "unwield": "해제했다."}[operation]
        particle = "으로/로" if operation == "wield" else "을/를"
        message = ft.text(ft.token("item", label), ft.particle(label, particle), " " + key)
    return ActionResult(messages=(message,), changed=True)
