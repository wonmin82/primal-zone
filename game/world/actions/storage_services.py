"""선택된 Storage Provider와 ItemEntity를 도메인 이동에 전달한다."""

from world.actions.gateway import ActionResult


def transfer(context):
    from world import item_transfer_native as domain
    from world import rules
    from world import text as ft

    count = context.arguments["count"]
    if count == "모두":
        quantity = None
    else:
        value = count.removesuffix("개")
        if len(value) > 9 or not value.isascii() or not value.isdecimal() or int(value) < 1:
            raise rules.RuleError("수량은 1개 이상의 정수로 지정하세요.")
        quantity = int(value)
    provider = context.roles["provider"][0]
    withdraw = context.config["withdraw"]
    context.caller.reconcile_recovery(emit_prompt=False)
    identity, amount = domain.transfer_selected(context.caller, provider, context.roles["subject"], quantity,
                                               withdraw=withdraw)
    message = ft.text(ft.token("object", provider.key), "에서 " if withdraw else "에 ",
                      ft.item(identity), f" {amount}개", "를 꺼냈다." if withdraw else "를 보관했다.")
    return ActionResult(messages=(message,), changed=True)
