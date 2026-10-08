"""게임 명령은 대상 + 행동으로, 엔진 관리 명령은 기본 문법으로 해석한다."""

from evennia.commands.cmdparser import cmdparser as default_parser


def cmdparser(raw_string, cmdset, caller, match_index=None, session=None, **kwargs):
    from commands.prompt import with_prompt

    return [(name, args, with_prompt(command), *rest) for name, args, command, *rest in
            _matches(raw_string, cmdset, caller, match_index, session, **kwargs)]


def _matches(raw_string, cmdset, caller, match_index=None, session=None, **kwargs):
    text = raw_string.strip()
    if not text:
        return []
    game_commands = [cmd for cmd in cmdset if getattr(cmd, "input_style", None)]
    if not game_commands:
        return default_parser(raw_string, cmdset, caller, match_index, session, **kwargs)

    from commands.aliases import SHORTCUTS

    if text in SHORTCUTS:
        original = default_parser(text, cmdset, caller, match_index, session, **kwargs)
        engine = [match for match in original if not getattr(match[2], "input_style", None)]
        if engine:
            return engine
        text = SHORTCUTS[text]

    # 줄임말 설정·계단 조작은 명시적인 전치형이다. 채팅 내용·기존 후치형 명령은 그대로 둔다.
    prefix_parts = text.split(None, 1)
    prefix, remainder = prefix_parts[0], prefix_parts[1] if len(prefix_parts) > 1 else ""
    settings_commands = [cmd for cmd in game_commands
                         if cmd.input_style == "prefix" and prefix.lower() in (cmd.key, *cmd.aliases)]
    help_names = {name for cmd in game_commands if cmd.key == "도움말" for name in (cmd.key, *cmd.aliases)}
    if settings_commands and remainder not in help_names:
        engine = [match for match in default_parser(text, cmdset, caller, match_index, session, **kwargs)
                  if not getattr(match[2], "input_style", None)]
        if engine:
            return engine
        return [(prefix, remainder.strip(), cmd, len(prefix), len(prefix) / len(text), prefix)
                for cmd in settings_commands if cmd.access(caller, "cmd", session=session)]

    # 작은따옴표 이후에는 행동 이름도 모두 대화 내용이다.
    quoted = text.startswith("'")
    parts = text.rsplit(None, 1)
    action = "말" if quoted else parts[-1].lower()
    args = text[1:].strip() if quoted else parts[0] if len(parts) == 2 else ""
    # 여러 단어로 된 명시적 행동 alias도 대상 뒤에서만 인식한다.
    multiword = sorted({name for cmd in game_commands for name in (cmd.key, *cmd.aliases)
                        if " " in name}, key=len, reverse=True)
    if not quoted:
        suffix = next((name for name in multiword if text.lower().endswith(" " + name)), None)
        if suffix:
            action, args = suffix, text[:-len(suffix)].rstrip()
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

    # 정상 명령/lock 우선. 개인 설정 조회는 read-only이며 입력 전체가 이름일 때만 확장한다.
    from django.conf import settings

    known = {normalized for name in cmdset.get_all_cmd_keys_and_aliases()
             for normalized in (name.casefold(), name.casefold().lstrip(settings.CMD_IGNORE_PREFIXES))}
    snapshot = getattr(caller, "profile_snapshot", None)
    if not quoted and text.casefold() not in known and callable(snapshot):
        if text.casefold() in snapshot().get("command_shortcuts", {}):
            from commands.command_shortcuts import PersonalShortcut

            return [(text, text.casefold(), PersonalShortcut(), len(text), 1.0, text)]
    return []
