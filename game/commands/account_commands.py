from evennia.commands.default.account import CmdQuit, CmdWho


class Quit(CmdQuit):
    key = "종료"
    aliases = ["quit", "q"]


class Who(CmdWho):
    key = "접속자"
    aliases = ["who"]
