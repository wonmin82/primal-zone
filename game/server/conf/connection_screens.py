# -*- coding: utf-8 -*-
"""
Connection screen

This is the text to show the user when they first connect to the game (before
they log in).

To change the login screen in this module, do one of the following:

- Define a function `connection_screen()`, taking no arguments. This will be
  called first and must return the full string to act as the connection screen.
  This can be used to produce more dynamic screens.
- Alternatively, define a string variable in the outermost scope of this module
  with the connection string that should be displayed. If more than one such
  variable is given, Evennia will pick one of them at random.

The commands available to the user when the connection screen is shown
are defined in evennia.default_cmds.UnloggedinCmdSet. The parsing and display
of the screen is done by the unlogged-in "look" command.

"""

from django.conf import settings
from evennia import utils


def connection_screen():
    return (
        "|g원시구역 · 첫 탐사|n\n"
        "접속창에서 탐사자 이름과 비밀번호를 입력하세요.\n"
        "사냥과 장비 수집으로 성장하고, 통신탑을 복구하세요.\n"
        "접속 후 '도움말'과 '임무'로 진행 방법을 확인할 수 있습니다."
    )


CONNECTION_SCREEN = """
|b==============================================================|n
 Welcome to |g{}|n, version {}!

 If you have an existing account, connect to it by typing:
      |wconnect <username> <password>|n
 If you need to create an account, type (without the <>'s):
      |wcreate <username> <password>|n

 If you have spaces in your username, enclose it in quotes.
 Enter |whelp|n for more info. |wlook|n will re-show this screen.
|b==============================================================|n""".format(
    settings.SERVERNAME, utils.get_evennia_version("short")
)
