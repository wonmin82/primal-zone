from evennia.commands.default.account import CmdQuit, CmdWho


class Quit(CmdQuit):
    input_style = "standalone"
    key = "종료"
    aliases = ["quit", "q"]


class Who(CmdWho):
    input_style = "standalone"
    key = "접속자"
    aliases = ["who"]
