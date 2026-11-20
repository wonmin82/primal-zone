"""선택한 UUID 하나만 도메인에 전달하는 동기 실행 경계."""

from world.actions.gateway import ActionResult

EQUIPMENT_VERBS = {
    "weapon": ("무장했다", "해제했다"),
    "shield": ("들었다", "내려놓았다"),
    "offhand": ("장착했다", "해제했다"),
    "head": ("썼다", "벗었다"),
    "neck": ("걸었다", "벗었다"),
    "body": ("입었다", "벗었다"),
    "gloves": ("꼈다", "벗었다"),
    "waist": ("둘렀다", "풀었다"),
    "legs": ("입었다", "벗었다"),
    "feet": ("신었다", "벗었다"),
    "ring": ("꼈다", "뺐다"),
    "accessory": ("착용했다", "벗었다"),
}


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

        skill_services.use_support(context.caller, "bandage", item=item, bandage_label=label)
        return ActionResult(changed=True)
    if operation in ("eat", "drink"):
        from world.item_inventory import bind_consumption
        from world.presentation import consumable_recovery

        def apply(profile):
            if not bind_consumption(context.caller, profile, item.definition_id, item.pk):
                raise rules.RuleError("원래 선택한 아이템이 없어졌거나 위치가 바뀌었습니다.")
            amount = rules.eat_or_drink(profile, item.definition_id, "먹어" if operation == "eat" else "마셔")
            return consumable_recovery(label, operation, amount)

        return ActionResult(messages=(context.caller.change(apply),), changed=True)

    definition = ITEMS[item.definition_id]
    particle = "을/를"
    description = ""
    if operation == "active_weapon":
        equipment.set_active_weapon(context.caller, item)
        description = "주무기로 "
        verb = "지정했다"
    elif operation in ("equip", "wield", "remove", "unwield"):
        remove = operation in ("remove", "unwield")
        expected_slot = "weapon" if operation in ("wield", "unwield") else "armor"
        properties = definition["equipment_properties"]
        slot = properties["slot"]
        kind = properties["role"] if slot == "hands" else slot
        equip_verb, remove_verb = EQUIPMENT_VERBS[kind]
        verb = remove_verb if remove else equip_verb
        if kind == "weapon" and not remove:
            particle = "으로/로"
        (equipment.unequip_item if remove else equipment.equip_item)(context.caller, item, expected_slot)
    else:
        raise rules.RuleError("지원하지 않는 장비 행동입니다.")
    message = ft.text(ft.token("item", label), f"{ft.particle(label, particle)} {description}",
                      ft.token("success", verb), ".")
    return ActionResult(messages=(message,), changed=True)
