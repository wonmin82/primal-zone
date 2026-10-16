"""선택된 안정 참조를 기존 도메인 규칙에 전달하는 동기 Service 경계."""

from world.actions.gateway import ActionResult, ResultStatus


def object_effect(context):
    from world import interactable_services as domain

    effect = getattr(domain, context.config["effect"])
    provider = context.roles["provider"][0]
    args = dict(context.arguments)
    argument = args.get("value")
    if "amount" in args:
        argument = (argument, args["amount"])
    effect(provider, context.caller, context.config["operation"], argument)
    return ActionResult(changed=context.config.get("changed", True))


def door(context):
    from world import doors

    changed = doors.operate_endpoint(context.caller, context.roles["provider"][0], context.config["operation"])
    return ActionResult(changed=changed)


def buy(context):
    from world import interactable_services as domain

    domain.shopkeeper(context.roles["provider"][0], context.caller, "사", context.arguments["value"])
    return ActionResult(changed=True)


def value(context):
    from world import interactable_services as domain

    quantity(context.arguments["count"])
    subjects = context.roles.get("subject", ())
    target = subjects[0] if subjects else context.arguments["value"]
    domain.shopkeeper(context.roles["provider"][0], context.caller, "가치", (target, 1))
    return ActionResult()


def quantity(value):
    from world.rules import RuleError

    if value == "모두":
        return None
    number = value.removesuffix("개")
    if not number.isdecimal() or len(number) > 9 or int(number) <= 0:
        raise RuleError("수량은 1개 이상의 정수로 지정하세요.")
    return int(number)


def settle(context):
    """집계 정산도 요청 당시 고정한 실제 Root 집합 밖의 아이템을 소비하지 않는다."""
    from world import interactable_services as domain
    from world.actions.collections import inventory_version
    from world.item_entities.services import lock_character_items
    from world.rules import RuleError

    if context.roles.get("source") != (context.caller,):
        raise RuleError("정산할 소지품 Source를 확인하세요.")
    lock_character_items(context.caller)
    version, _members = inventory_version(context.caller, ("scrap",))
    if context.invocation.origin == "web" and context.arguments["snapshot"] != version:
        raise RuleError("정산할 원래 소지품이 바뀌었습니다. 다시 요청하세요.")
    domain.settlementofficer(context.roles["provider"][0], context.caller, "교환", context.arguments.get("value"))
    return ActionResult(changed=True)


def sell(context):
    from world import interactable_services as domain

    domain.shopkeeper(context.roles["provider"][0], context.caller, "팔아",
                      (context.roles["subject"][0], quantity(context.arguments["count"])))
    return ActionResult(changed=True)


def burn(context):
    from world import incinerator_service as domain

    confirmed = context.invocation.variant_id == "confirmed"
    result = domain.incinerate_selected(context.caller, context.roles["provider"][0],
                                       context.roles["subject"][0],
                                       quantity(context.arguments["count"]), confirmed=confirmed,
                                       explicit_quantity=context.arguments["count"] != "1")
    if not confirmed and result.startswith("출입 권한을 잃습니다"):
        return ActionResult(ResultStatus.CONFIRMATION, (result,), confirm_variant="confirmed")
    return ActionResult(messages=(result,), changed=True)
