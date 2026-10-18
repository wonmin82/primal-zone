"""아이템 이전·소비·장비 해제. 조사는 공통 selector helper에서 추출한다."""


from world import rules
from world import text as ft
from world.content import ITEMS
from world.currency import currency_names, currency_request, format_currency
from world.item_transfers import transfer, transfer_currency
from world.targets import (
    names,
    parse_relation,
    parse_selector,
    resolve,
    room_objects,
    stack_selector,
)

from commands.base import GameCommand


class Drop(GameCommand):
    key = "버려"
    category = "아이템·보급"
    input_style = "target"
    usage = "붕대 버려 · 붕대 모두 버려 · 20칩 버려 · 칩 모두 버려"
    summary = "장착분을 남기고 물건 하나 또는 스택 전부를 공개된 바닥에 옮깁니다."
    aliases = ["drop"]
    particle = None
    withdraw = False

    def run(self):
        kwargs = {}
        value = self.args
        counterpart = None
        if self.particle:
            from typeclasses.explorers import Explorer
            from typeclasses.interactables import Container

            objects = room_objects(self.caller)
            selector, value = parse_relation(
                value, self.particle, [name for obj in objects for name in names(obj)]
            )
            cls = Explorer if isinstance(self, Give) else Container
            counterpart = resolve(
                objects, selector, self.caller, self.key, lambda obj: isinstance(obj, cls)
            )[0]
            kwargs["recipient" if cls is Explorer else "container"] = counterpart
        currency = currency_request(parse_selector(value, currency_names()))
        if currency and (counterpart is None or isinstance(self, Give)):
            if currency[1].index:
                raise rules.RuleError("보유 보급칩은 번호 없이 금액 또는 모두로 지정하세요.")
            quantity = transfer_currency(self.caller, currency[0], counterpart)
            item = ft.token("reward", format_currency(quantity))
            if counterpart:
                self.caller.msg(ft.text(ft.token("player", counterpart.key), "에게 ", item, "을 건넸다."))
                counterpart.msg(ft.text(ft.token("player", self.caller.key), "에게서 ", item, "을 받았다."))
                counterpart.push_state()
            else:
                self.caller.msg(ft.text(item, "을 바닥에 내려놓았다. 다른 탐사자도 가져갈 수 있다."))
            return
        from world.equipment_service import entity_runtime

        if entity_runtime(self.caller):
            from world.item_transfer_native import transfer as native_transfer

            identity, quantity = native_transfer(self.caller, value, withdraw=self.withdraw, **kwargs)
        else:
            identity, all_items = stack_selector(value, ITEMS, self.key)
            if counterpart and not isinstance(self, Give):
                quantity = counterpart.perform_action(self.caller, self.key, (identity, all_items))
            else:
                quantity = transfer(self.caller, identity, all_items=all_items, **kwargs)
        item = ft.text(ft.item(identity), f" {quantity}개")
        if isinstance(self, Give):
            self.caller.msg(
                ft.text(ft.token("player", counterpart.key), "에게 ", item, "를 건넸다.")
            )
            counterpart.msg(
                ft.text(ft.token("player", self.caller.key), "에게서 ", item, "를 받았다.")
            )
        elif counterpart:
            self.caller.msg(
                ft.text(
                    ft.token("object", counterpart.key),
                    "에서 " if self.withdraw else "에 ",
                    item,
                    "를 꺼냈다." if self.withdraw else "를 보관했다.",
                )
            )
        else:
            self.caller.msg(ft.text(item, "를 바닥에 내려놓았다. 다른 탐사자도 가져갈 수 있다."))


class Give(Drop):
    key = "줘"
    aliases = ["give"]
    particle = "에게"
    usage = "탐사자에게 붕대 줘 · 탐사자에게 붕대 모두 줘 · 탐사자에게 20칩 줘 · 탐사자에게 칩 모두 줘"
    summary = "같은 장소의 다른 비전투 탐사자에게 물건을 건넵니다."
