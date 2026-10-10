from evennia.commands.default.account import CmdQuit, CmdWho

from commands.help_contracts import command_sections


class Quit(CmdQuit):
    input_style = "standalone"
    key = "종료"
    aliases = ["quit", "q"]


class Who(CmdWho):
    summary = "현재 접속한 탐사자의 공개 목록을 확인합니다."
    usage = "누구"
    category = "파티·교류"
    help_sections = command_sections('누구')
    input_style = "standalone"
    key = "누구"
    aliases = ["누"]
