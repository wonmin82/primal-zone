"""inventory 영역의 명시적 게임 명령."""

from world import presentation as view

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















class Equipment(GameCommand):
    help_sections = command_sections('장비')
    aliases = ["장"]
    key = "장비"
    category = "아이템·보급"
    summary = "현재 착용한 무기와 방어구만 확인합니다."

    def run(self):
        self.caller.msg(view.equipment(self.caller.profile()))
