"""아이템 이전·소비·장비 해제. 조사는 공통 selector helper에서 추출한다."""

from time import time

from world import rules
from world import text as ft
from world.content import ITEMS, UNEQUIP_ACTIONS, find_id
from world.currency import currency_names, currency_request, format_currency
from world.item_transfers import transfer, transfer_currency
from world.targets import (
    names,
    parse_relation,
    parse_selector,
    require_single,
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


class Store(Drop):
    key = "넣어"
    aliases = ["store"]
    particle = "에"
    usage = "보관상자에 붕대 넣어 · 개인 보관함에 붕대 모두 넣어 · 탐사용손전등에 건전지 넣어"
    summary = "한 보관함에 물건을 보관하거나 광원에 호환 전원 하나를 넣습니다."

    def run(self):
        from world import lighting
        from world.equipment_service import entity_runtime, resolve_item

        if entity_runtime(self.caller):
            from world import lighting_service

            from commands.firearms import load_loose, relation

            try:
                selected, value = relation(self.caller, self.args, self.particle)
            except rules.RuleError:
                selected = None
            if selected is not None:
                if ITEMS[selected.definition_id].get("light_source"):
                    power = resolve_item(self.caller, value, self.key)
                    lighting_service.insert_power(self.caller, selected, power)
                    self.caller.msg("광원에 전원 하나를 넣었다.")
                    return
                if ITEMS[selected.definition_id].get("magazine"):
                    load_loose(self.caller, selected, value)
                    return

        objects = room_objects(self.caller)
        selector, value = parse_relation(
            self.args, self.particle,
            [name for obj in objects for name in names(obj)] + lighting.source_names(),
        )
        identity = find_id(ITEMS, selector.name)
        if identity and ITEMS[identity].get("light_source"):
            require_single(selector, self.key)
            if selector.index:
                raise rules.RuleError("소지품의 광원은 번호 없이 지정하세요.")
            power, _ = stack_selector(value, ITEMS, self.key, allow_all=False)
            from world.lighting_service import insert_power

            insert_power(self.caller, identity, power, time())
            self.caller.msg(ft.text(ft.item(identity), "에 ", ft.item(power), " 한 개를 넣었다."))
            return
        super().run()


class LightOn(GameCommand):
    key = "켜"
    category = "이동·탐사"
    input_style = "target"
    usage = "손전등 켜 · 탐사용손전등 켜"
    summary = "전원이 있는 소지품의 광원을 켭니다."
    enabled = True

    def run(self):
        from world import lighting_service as service

        item, label = service.resolve_light(self.caller, self.args, self.key)
        service.switch(self.caller, item, self.enabled, time())
        self.caller.msg(ft.text(ft.token("item", label), ft.particle(label, "을/를"),
                               " 켰다." if self.enabled else " 껐다."))


class LightOff(LightOn):
    key = "꺼"
    enabled = False
    usage = "손전등 꺼"
    summary = "광원을 끄고 남은 전원을 보존합니다."


class LightStatus(GameCommand):
    key = "확인"
    category = "이동·탐사"
    input_style = "target"
    usage = "손전등 확인"
    summary = "광원의 상태, 전원 종류와 남은 사용 시간을 확인합니다."

    def run(self):
        from world import lighting_service as service

        item, label = service.resolve_light(self.caller, self.args, self.key)
        self.caller.msg(ft.compact(ft.token("item", label), service.status(self.caller, item, time())))


class Retrieve(Drop):
    key = "꺼내"
    aliases = ["retrieve"]
    particle = "에서"
    withdraw = True
    usage = "보관상자에서 붕대 꺼내 · 보관상자 2에서 붕대 모두 꺼내 · 개인 보관함에서 붕대 꺼내"
    summary = "한 보관함에서 물건 하나 또는 같은 스택 전부를 꺼냅니다."

    def run(self):
        from world.equipment_service import entity_runtime

        if entity_runtime(self.caller):
            from commands.firearms import relation, unload

            try:
                item, value = relation(self.caller, self.args, self.particle)
            except rules.RuleError:
                item = None
            if item is not None and (ITEMS[item.definition_id].get("magazine")
                                     or ITEMS[item.definition_id].get("firearm_family")):
                unload(self.caller, item, value)
                return
        super().run()


class Eat(GameCommand):
    key = "먹어"
    aliases = ["eat"]
    category = "아이템·보급"
    input_style = "target"
    usage = "야전식량 먹어"
    summary = "비전투 중 음식 하나를 먹어 체력을 회복합니다."

    def run(self):
        identity, _ = stack_selector(self.args, ITEMS, self.key, allow_all=False)
        amount = self.caller.change(lambda profile: rules.eat_or_drink(profile, identity, self.key))
        self.caller.msg(
            ft.text(
                ft.item(identity),
                ft.particle(ITEMS[identity]["name"], "을/를"),
                " 먹었다." if self.key == "먹어" else " 마셨다.",
                f" 체력이 {amount} 회복되었다.",
            )
        )


class Drink(Eat):
    key = "마셔"
    aliases = ["drink"]
    usage = "정제수 마셔"
    summary = "비전투 중 음료 하나를 마셔 체력을 회복합니다."


class RemoveArmor(GameCommand):
    equipment_change = True
    key = UNEQUIP_ACTIONS["armor"]
    aliases = ["remove"]
    expected_slot = "armor"
    category = "아이템·보급"
    input_style = "target"
    usage = "강화 조끼 벗어"
    summary = "현재 입은 방어구를 벗어 소지품에 남깁니다."

    def run(self):
        from world.equipment_service import resolve_item, selector_label, unequip_item

        selected = resolve_item(self.caller, self.args, self.key)
        label = selector_label(self.caller, selected)
        unequip_item(self.caller, selected, self.expected_slot)
        self.caller.msg(
            ft.text(
                ft.token("item", label),
                ft.particle(label, "을/를"),
                " 벗었다." if self.expected_slot == "armor" else " 해제했다.",
            )
        )


class Unwield(RemoveArmor):
    key = UNEQUIP_ACTIONS["weapon"]
    aliases = ["unwield"]
    expected_slot = "weapon"
    usage = "강철 마체테 해제"
    summary = "현재 무기를 해제해 소지품에 남깁니다. 맨손으로도 공격할 수 있습니다."
