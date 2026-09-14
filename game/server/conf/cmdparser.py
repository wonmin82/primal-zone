"""게임 명령은 대상 + 행동으로, 엔진 관리 명령은 기본 문법으로 해석한다."""

from evennia.commands.cmdparser import cmdparser as default_parser


def cmdparser(raw_string, cmdset, caller, match_index=None, session=None, **kwargs):
    text = raw_string.strip()
    if not text:
        return []
    game_commands = [cmd for cmd in cmdset if getattr(cmd, "input_style", None)]
    if not game_commands:
        return default_parser(raw_string, cmdset, caller, match_index, session, **kwargs)

    # 작은따옴표 이후에는 행동 이름도 모두 대화 내용이다.
    quoted = text.startswith("'")
    parts = text.rsplit(None, 1)
    action = "말" if quoted else parts[-1].lower()
    args = text[1:].strip() if quoted else parts[0] if len(parts) == 2 else ""
    candidates = [cmd for cmd in game_commands if action in (cmd.key.lower(), *cmd.aliases)]
    # 채팅 외의 엔진 명령은 인자 끝에 게임 행동 이름이 있어도 원래 문법을 유지한다.
    engine_matches = []
    if not quoted and not any(cmd.input_style == "chat" for cmd in candidates):
        engine_matches = [
            match
            for match in default_parser(text, cmdset, caller, match_index, session, **kwargs)
            if not getattr(match[2], "input_style", None)
        ]
        if engine_matches:
            return engine_matches
    if candidates:
        matches = [
            (action, args, cmd, len(action), len(action) / len(text), action)
            for cmd in candidates
            if (not args or cmd.input_style in ("target", "chat"))
            and cmd.access(caller, "cmd", session=session)
        ]
        if len(matches) > 1 and match_index is not None:
            return matches[match_index - 1 : match_index] if match_index > 0 else []
        return matches

    return []
