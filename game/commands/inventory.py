"""inventory 영역의 명시적 게임 명령."""

from world import presentation as view
from world import rules
from world import text as ft
from world.content import EQUIPMENT_ACTIONS, ITEMS
from world.currency import currency_names
from world.targets import item_selector, names, parse_loot, parse_relation, resolve, stack_selector

from commands.base import GameCommand
from commands.shops import resolve_shopkeeper, shopkeepers


class Inventory(GameCommand):
    category = "아이템·보급"
    usage = "소지품"
    summary = "보급칩 잔액과 전체 소지품을 확인합니다."
    key = "소지품"
    aliases = ["가방", "가진거", "i", "인벤토리"]

    def run(self):
        self.caller.msg(view.inventory(self.caller.profile()))


class Equip(GameCommand):
    equipment_change = True
    category = "아이템·보급"
    usage = "강화 조끼 착용"
    summary = "소유한 방어구를 착용합니다."
    input_style = "target"
    expected_slot = "armor"
    key = EQUIPMENT_ACTIONS[expected_slot]
    aliases = ["wear"]

    def run(self):
        from world.equipment_service import equip_item, resolve_item, selector_label

        selected = resolve_item(self.caller, self.args, self.key)
        item = selected.definition_id if hasattr(selected, "definition_id") else selected
        label = selector_label(self.caller, selected)
        equip_item(self.caller, selected, self.expected_slot)
        particle = "으로/로" if ITEMS[item]["slot"] == "weapon" else "을/를"
        self.caller.msg(
            ft.text(ft.token("item", label), ft.particle(label, particle), f" {self.key}했다.")
        )


class Wield(Equip):
    usage = "강철 마체테 무장"
    summary = "소유한 무기를 빈 손에 장착합니다. 자동 교체는 하지 않습니다."
    expected_slot = "weapon"
    key = EQUIPMENT_ACTIONS[expected_slot]
    aliases = ["wield"]


class Shop(GameCommand):
    category = "아이템·보급"
    usage = "상품 · 무기상 상품"
    summary = "주변 상인의 보급칩 판매 목록을 확인합니다."
    input_style = "target"
    key = "상품"
    aliases = []

    def run(self):
        resolve_shopkeeper(self.caller, self.args).perform_action(self.caller, self.key)


class Buy(GameCommand):
    category = "아이템·보급"
    usage = "붕대 구매 · 보급관에게 붕대 구매"
    summary = "주변 판매자에게 보급칩으로 물건 1개를 구매합니다."
    input_style = "target"
    key = "구매"
    aliases = ["buy"]
    stack = False

    def run(self):
        objects = shopkeepers(self.caller)
        value, seller = self.args, None
        if any(word.endswith("에게") for word in value.split()):
            selector, value = parse_relation(value, "에게", [n for obj in objects for n in names(obj)])
            seller = resolve(objects, selector, self.caller, self.key)[0]
        if self.stack:
            item, all_items = stack_selector(value, ITEMS, self.key)
        else:
            item = item_selector(value, ITEMS, self.key)
        if not item:
            raise rules.RuleError("물건 이름을 확인하세요. 예: 붕대 구매")
        seller = seller or resolve_shopkeeper(self.caller, item=item, objects=objects)
        seller.perform_action(self.caller, self.key, (item, all_items) if self.stack else item)


class Value(Buy):
    key = "가치"
    aliases = ["value"]
    usage = "강철마체테 가치 · 무기상에게 강철마체테 가치"
    summary = "주변 상인에게 취급 품목의 가치와 매입가를 확인합니다."


class Sell(Buy):
    key = "판매"
    aliases = ["sell"]
    stack = True
    usage = "강철마체테 판매 · 무기상에게 강철마체테 판매 · 붕대 모두 판매"
    summary = "장착한 복사본을 남기고 취급 품목을 상인에게 판매합니다."


class Take(GameCommand):
    category = "아이템·보급"
    usage = "시체에서 모두 가져 · 시체 2에서 모두 가져 · 모든 시체에서 회수부품 모두 가져 · 회수부품 2 가져 · 회수부품 모두 가져 · 시체에서 20칩 가져 · 칩 2 가져 · 칩 모두 가져 · 모두 가져"
    summary = "권한에 따라 배정된 전리품을 분배합니다."
    key = "가져"
    input_style = "target"

    def run(self):
        from typeclasses.loot import take_loot

        request = parse_loot(
            self.args, [n for key, data in ITEMS.items() for n in (key, data["name"])] + list(currency_names())
        )
        take_loot(self.caller, request=request)


class Equipment(GameCommand):
    key = "장비"
    category = "아이템·보급"
    summary = "현재 착용한 무기와 방어구만 확인합니다."

    def run(self):
        self.caller.msg(view.equipment(self.caller.profile()))


class ActiveWeapon(GameCommand):
    key = "주무기"
    input_style = "target"
    category = "아이템·보급"
    equipment_change = True
    usage = "강철마체테 2 주무기"
    summary = "장착한 무기 하나를 실제 공격에 사용할 주무기로 지정합니다."

    def run(self):
        from world.equipment_service import resolve_item, set_active_weapon

        item = resolve_item(self.caller, self.args, self.key)
        set_active_weapon(self.caller, item)
        self.caller.msg("주무기를 지정했다.")
