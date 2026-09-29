"""inventory 영역의 명시적 게임 명령."""

from world import presentation as view
from world import rules
from world import text as ft
from world.content import EQUIPMENT_ACTIONS, ITEMS
from world.targets import item_selector, parse_loot

from commands.base import GameCommand


class Inventory(GameCommand):
    category = "보급"
    usage = "가방"
    summary = "전체 소지품을 확인합니다."
    key = "가방"
    aliases = ["i", "인벤토리"]

    def run(self):
        self.caller.msg(view.inventory(self.caller.profile()))


class Equip(GameCommand):
    category = "보급"
    usage = "강화 조끼 착용"
    summary = "소유한 방어구를 착용합니다."
    input_style = "target"
    expected_slot = "armor"
    key = EQUIPMENT_ACTIONS[expected_slot]
    aliases = ["wear"]

    def run(self):
        item = item_selector(self.args, ITEMS, self.key)
        if not item:
            raise rules.RuleError(f"사용법: {self.usage}")
        self.caller.change(lambda profile: rules.equip(profile, item, self.expected_slot))
        particle = "으로/로" if ITEMS[item]["slot"] == "weapon" else "을/를"
        self.caller.msg(
            ft.text(ft.item(item), ft.particle(ITEMS[item]["name"], particle), f" {self.key}했다.")
        )


class Wield(Equip):
    usage = "강철 마체테 무장"
    summary = "소유한 무기를 사용 중인 무기로 바꿉니다."
    expected_slot = "weapon"
    key = EQUIPMENT_ACTIONS[expected_slot]
    aliases = ["wield"]


class Shop(GameCommand):
    category = "보급"
    usage = "상점"
    summary = "부두의 크레딧 판매 가격을 확인합니다."
    key = "상점"
    aliases = ["shop"]

    def run(self):
        self.at_dock()
        self.caller.msg(view.shop())


class Buy(GameCommand):
    category = "보급"
    usage = "붕대 구매"
    summary = "크레딧으로 물건을 구매합니다."
    input_style = "target"
    key = "구매"
    aliases = ["buy"]

    def run(self):
        self.at_dock()
        item = item_selector(self.args, ITEMS, self.key)
        if not item:
            raise rules.RuleError("물건 이름을 확인하세요. 예: 붕대 구매")
        self.caller.change(lambda profile: rules.buy(profile, item))
        self.caller.msg(ft.text(ft.item(item), " 1개를 받아 가방에 넣었다."))


class Take(GameCommand):
    category = "전리품"
    usage = "시체에서 모두 가져 · 시체 2에서 모두 가져 · 모든 시체에서 회수부품 모두 가져 · 회수부품 2 가져 · 회수부품 모두 가져 · 모두 가져"
    summary = "권한에 따라 배정된 전리품을 분배합니다."
    key = "가져"
    input_style = "target"

    def run(self):
        from typeclasses.loot import take_loot

        request = parse_loot(
            self.args, [n for key, data in ITEMS.items() for n in (key, data["name"])]
        )
        take_loot(self.caller, request=request)


class Equipment(GameCommand):
    key = "장비"
    category = "성장"
    summary = "현재 착용한 무기와 방어구만 확인합니다."

    def run(self):
        self.caller.msg(view.equipment(self.caller.profile()))
