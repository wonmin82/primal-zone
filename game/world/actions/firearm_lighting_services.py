"""이미 선택한 UUID만 기존 원자적 총기·광원 도메인으로 전달한다."""

from world.actions.gateway import ActionResult


def execute(context):
    from world import firearm_service as guns
    from world import lighting_service as lights
    from world import rules
    from world.actions.firearm_lighting_presentation import item_label
    from world.content import ITEMS

    provider = context.roles["provider"][0]
    subjects = context.roles.get("subject", ())
    target = subjects[0] if subjects else provider
    sources = context.roles.get("source", ())
    source = sources[0] if sources else None
    operation = context.config["operation"]
    # 기존 GameCommand의 명령 완료 경계에서 이루어지던 자연 회복을 유지한다.
    # Gateway transaction 안이므로 뒤의 거절·예외에서는 회복/알림도 함께 취소된다.
    context.caller.reconcile_recovery(emit_prompt=False)
    if operation == "reload" and context.invocation.origin == "web":
        # 자동 문법은 텍스트에서만 현재 후보를 결정한다. 웹 추천 버튼은 load/store의
        # 명시 Source Invocation으로 만들며, 오래된 추천을 다른 Source로 대체하지 않는다.
        raise rules.RuleError("조작할 원래 탄창·탄약을 지정하세요.")
    if operation == "reload":
        changed = guns.reload(context.caller, provider)
        message = item_label(provider) + ": " + ("재장전했다." if changed else "현재 탄창을 유지한다.")
    elif operation == "load":
        if source is None:
            raise rules.RuleError("장전할 탄창을 지정하세요.")
        changed = guns.reload(context.caller, provider, source)
        message = "탄창을 장전했다." if changed else "현재 탄창을 유지한다."
    elif operation in ("fill", "ammo_insert"):
        if operation == "fill":
            from world.actions.collections import inventory_version
            from world.item_entities.services import lock_character_items

            if context.roles.get("source") != (context.caller,):
                raise rules.RuleError("채울 탄약의 소지품 Source를 확인하세요.")
            lock_character_items(context.caller)
            ammo_type = guns.magazine_snapshot(target).ammo_type
            definitions = tuple([identity for identity, data in ITEMS.items() if data.get("ammo_type") == ammo_type])
            version, _members = inventory_version(context.caller, definitions)
            if context.invocation.origin == "web" and context.arguments["snapshot"] != version:
                raise rules.RuleError("채울 원래 탄약이 바뀌었습니다. 다시 요청하세요.")
        count = guns.load_ammo(context.caller, target, None if operation == "fill" else source)
        changed, message = True, f"탄창에 {count}발을 넣었다."
    elif operation == "magazine_remove":
        # 요청 이후 삽입물이 바뀌면 기존 버튼을 새 탄창에 적용하지 않는다.
        current = guns.loaded_magazine_item(provider)
        if not subjects or current is None or current.pk != target.pk:
            raise rules.RuleError("원래 삽입된 탄창이 바뀌었습니다.")
        guns.unload_magazine(context.caller, provider)
        changed, message = True, "탄창을 꺼냈다."
    elif operation == "ammo_remove":
        ammo_type = ITEMS[context.arguments["ammo"]]["ammo_type"]
        count = guns.unload_ammo(context.caller, target, ammo_type)
        changed, message = True, f"탄창에서 {count}발을 전부 꺼냈다."
    elif operation == "power_insert":
        if source is None:
            raise rules.RuleError("넣을 전원을 지정하세요.")
        lights.insert_power(context.caller, provider, source)
        changed, message = True, "광원에 전원 하나를 넣었다."
    elif operation == "light_status":
        return ActionResult(messages=(item_label(provider) + "\n" + lights.status(context.caller, provider),))
    elif operation in ("light_on", "light_off"):
        enabled = operation == "light_on"
        lights.switch(context.caller, provider, enabled)
        from world.text import particle
        target_label = item_label(provider)
        changed, message = True, target_label + particle(target_label, "을/를") + (" 켰다." if enabled else " 껐다.")
    else:
        raise rules.RuleError("등록된 조작을 확인하세요.")
    return ActionResult(messages=(message,), changed=changed)
