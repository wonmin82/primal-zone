"""inventory 영역의 명시적 게임 명령."""

from world import presentation as view
from world.content import ITEMS
from world.currency import currency_names
from world.targets import parse_loot

from commands.base import GameCommand
from commands.help_contracts import command_sections


class Inventory(GameCommand):
    help_sections = command_sections('가진거')
    category = "아이템·보급"
    usage = "가진거"
    summary = "보급칩 잔액과 전체 소지품을 확인합니다."
    key = "가진거"
    aliases = ["가진", "소", "소지", "소지품"]

    def run(self):
        self.caller.msg(view.inventory(self.caller.profile()))















class Take(GameCommand):
    help_sections = command_sections('가져')
    aliases = ["집"]
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
    help_sections = command_sections('장비')
    aliases = ["장"]
    key = "장비"
    category = "아이템·보급"
    summary = "현재 착용한 무기와 방어구만 확인합니다."

    def run(self):
        self.caller.msg(view.equipment(self.caller.profile()))
