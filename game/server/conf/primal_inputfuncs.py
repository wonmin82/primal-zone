"""Structured login avoids putting passwords in command history or game output."""

import re as _re

from django.conf import settings as _settings
from evennia.utils.utils import class_from_module as _class_from_module


def pz_auth(session, payload=None, **kwargs):
    if session.account:
        return
    if not isinstance(payload, dict):
        return
    username = payload.get("username", "")
    password = payload.get("password", "")
    mode = payload.get("mode")
    if (
        not isinstance(username, str)
        or not isinstance(password, str)
        or not _re.fullmatch(r"[가-힣A-Za-z0-9_]{2,24}", username)
        or not 8 <= len(password) <= 128
        or mode not in ("login", "register")
    ):
        session.msg(
            pz_auth=(
                [
                    {
                        "ok": False,
                        "message": "이름은 한글·영문·숫자·밑줄 2~24자, 비밀번호는 8~128자로 입력하세요.",
                    }
                ],
                {},
            )
        )
        return
    Account = _class_from_module(_settings.BASE_ACCOUNT_TYPECLASS)
    if mode == "register":
        if not _settings.NEW_ACCOUNT_REGISTRATION_ENABLED:
            session.msg(pz_auth=([{"ok": False, "message": "현재 가입이 닫혀 있습니다."}], {}))
            return
        account, errors = Account.create(
            username=username, password=password, ip=session.address, session=session
        )
    else:
        account, errors = Account.authenticate(
            username=username, password=password, ip=session.address, session=session
        )
    if account:
        session.msg(pz_auth=([{"ok": True, "message": "접속되었습니다."}], {}))
        session.sessionhandler.login(session, account)
    else:
        session.msg(
            pz_auth=([{"ok": False, "message": "\n".join(str(error) for error in errors)}], {})
        )
