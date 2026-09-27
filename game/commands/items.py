"""아이템 이전·소비·장비 해제. 조사는 공통 selector helper에서 추출한다."""

from world import rules
from world import text as ft
from world.content import ITEMS, UNEQUIP_ACTIONS
from world.item_transfers import transfer
from world.targets import names, parse_relation, resolve, room_objects, stack_selector

from commands.base import GameCommand


class Drop(GameCommand):
    key = "버려"
    category = "보급"
    input_style = "target"
    usage = "붕대 버려 · 붕대 모두 버려"
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
    usage = "탐사자에게 붕대 줘 · 탐사자에게 붕대 모두 줘"
    summary = "같은 장소의 다른 비전투 탐사자에게 물건을 건넵니다."


class Store(Drop):
    key = "넣어"
    aliases = ["store"]
    particle = "에"
    usage = "보관상자에 붕대 넣어 · 보관상자 2에 붕대 모두 넣어 · 개인 보관함에 붕대 넣어"
    summary = "한 보관함에 장착분을 제외한 물건을 보관합니다."


class Retrieve(Drop):
    key = "꺼내"
    aliases = ["retrieve"]
    particle = "에서"
    withdraw = True
    usage = "보관상자에서 붕대 꺼내 · 보관상자 2에서 붕대 모두 꺼내 · 개인 보관함에서 붕대 꺼내"
    summary = "한 보관함에서 물건 하나 또는 같은 스택 전부를 꺼냅니다."


class Eat(GameCommand):
    key = "먹어"
    aliases = ["eat"]
    category = "보급"
    input_style = "target"
    usage = "야전식량 먹어"
    summary = "비전투 중 음식 하나를 먹어 체력을 회복합니다. 치료 숙련은 오르지 않습니다."

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
    summary = "비전투 중 음료 하나를 마셔 체력을 회복합니다. 치료 숙련은 오르지 않습니다."


class RemoveArmor(GameCommand):
    key = UNEQUIP_ACTIONS["armor"]
    aliases = ["remove"]
    expected_slot = "armor"
    category = "보급"
    input_style = "target"
    usage = "강화 조끼 벗어"
    summary = "현재 입은 방어구를 벗어 가방에 남깁니다."

    def run(self):
        identity, _ = stack_selector(self.args, ITEMS, self.key, allow_all=False)
        self.caller.change(lambda profile: rules.unequip(profile, identity, self.expected_slot))
        self.caller.msg(
            ft.text(
                ft.item(identity),
                ft.particle(ITEMS[identity]["name"], "을/를"),
                " 벗었다." if self.expected_slot == "armor" else " 해제했다.",
            )
        )


class Unwield(RemoveArmor):
    key = UNEQUIP_ACTIONS["weapon"]
    aliases = ["unwield"]
    expected_slot = "weapon"
    usage = "강철 마체테 해제"
    summary = "현재 무기를 해제해 가방에 남깁니다. 맨손으로도 공격할 수 있습니다."
