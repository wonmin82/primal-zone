"""현재 CmdSet에서 한 번 선택한다. 실제 문법 일치는 lock 거부 때도 개인 정의보다 우선한다."""

from dataclasses import dataclass

from evennia.commands.cmdparser import build_matches
from evennia.commands.cmdparser import cmdparser as default_parser


@dataclass(frozen=True)
class Selection:
    text: str
    matches: tuple
    global_expanded: bool = False


def _engine_matches(text, cmdset, caller, match_index, session):
    engine = [cmd for cmd in cmdset if not getattr(cmd, "input_style", None)]
    syntax = build_matches(text, engine, include_prefixes=True)
    if not syntax:
        syntax = build_matches(text, engine, include_prefixes=False)
    # Exit의 추가 인자는 공통 명령 경계에서 거절한다. 후치형 보기 선택은 계속 허용한다.
    matches = [m for m in default_parser(text, engine, caller, match_index, session)
               if not (getattr(m[2], "is_exit", False) and m[1].strip())]
    valid_syntax = [m for m in syntax if not (getattr(m[2], "is_exit", False) and m[1].strip())]
    return matches, valid_syntax


def _actual(text, cmdset, caller, match_index, session):
    game = [cmd for cmd in cmdset if getattr(cmd, "input_style", None)]
    quoted = text.startswith("'")
    parts = text.rsplit(None, 1)
    action = "말" if quoted else parts[-1].casefold()
    args = text[1:].strip() if quoted else parts[0] if len(parts) == 2 else ""
    if not quoted:
        multiword = sorted({name.casefold() for cmd in game for name in (cmd.key, *cmd.aliases)
                            if " " in name}, key=len, reverse=True)
        suffix = next((name for name in multiword if text.casefold() == name
                       or text.casefold().endswith(" " + name)), None)
        if suffix:
            action, args = suffix, text[:-len(suffix)].rstrip()
    candidates = [cmd for cmd in game if action in {name.casefold() for name in (cmd.key, *cmd.aliases)}]
    bundle = action == "해" and "," in text
    if not quoted and not bundle and not any(cmd.input_style == "chat" for cmd in candidates):
        matches, engine_syntax = _engine_matches(text, cmdset, caller, match_index, session)
        if engine_syntax:
            return matches, True  # 접근 거부가 개인 fallback의 이유가 되어서는 안 된다.
    if candidates:
        matches = [(action, args, cmd, len(action), len(action) / len(text), action)
                   for cmd in candidates if (not args or cmd.input_style in ("target", "chat"))
                   and cmd.access(caller, "cmd", session=session)]
        if len(matches) > 1 and match_index is not None:
            matches = matches[match_index - 1:match_index] if match_index > 0 else []
        return matches, True
    # 인자 있는 Exit 후보는 이동 문법이 아니다. 유효한 후치형 개인 호출을 숨기지 않는다.
    # 개인 이름도 없으면 UnknownCommand로 끝나며 Exit hook에는 전달하지 않는다.
    return [], False


def select_command(raw_string, cmdset, caller, match_index=None, session=None, *, shortcuts=None,
                   personal=True, global_aliases=True):
    from commands.aliases import ARGUMENT_SHORTCUTS, SHORTCUTS
    from commands.shortcuts import normalized_keys, parse_definition

    text = raw_string.strip()
    if not text:
        return Selection(text, ())
    matches, actual = _actual(text, cmdset, caller, match_index, session)
    if actual:
        return Selection(text, tuple(matches))
    # 정적 전역 단축어는 정확한 전체 입력에 한 번만 적용한다.
    if global_aliases and text in SHORTCUTS:
        final = SHORTCUTS[text]
        matches, _ = _actual(final, cmdset, caller, match_index, session)
        return Selection(final, tuple(matches), True)
    parts = text.rsplit(None, 1)
    action = parts[-1].casefold()
    args = parts[0] if len(parts) == 2 else ""
    if global_aliases and action in ARGUMENT_SHORTCUTS:
        # 인자형 전역 정의의 내부 기반. 실제·다른 전역·개인으로 재확장하지 않는다.
        from world.rules import RuleError

        commands = parse_definition(ARGUMENT_SHORTCUTS[action]).bind(args)
        if len(commands) != 1:
            raise RuleError("인자형 전역 단축어는 하나의 실제 명령만 실행할 수 있습니다.")
        from commands.command_shortcuts import GlobalShortcut

        command = GlobalShortcut()
        command.global_command = commands[0]
        return Selection(text, ((action, args, command, len(action), 1, action),), True)
    if personal and not text.startswith("'"):
        if shortcuts is None:
            snapshot = getattr(caller, "profile_snapshot", None)
            shortcuts = snapshot().get("command_shortcuts", {}) if callable(snapshot) else {}
        if isinstance(shortcuts, dict) and normalized_keys(shortcuts, action):
            from commands.command_shortcuts import PersonalShortcut

            command = PersonalShortcut()
            command.shortcut_name = action
            original_parts = raw_string.rsplit(None, 1)
            original_args = original_parts[0] if len(original_parts) == 2 else ""
            return Selection(text, ((action, original_args, command, len(action), len(action) / len(text), action),))
    return Selection(text, ())


def cmdparser(raw_string, cmdset, caller, match_index=None, session=None, **kwargs):
    from commands.prompt import with_prompt
    from commands.shortcut_execution import ShortcutError, dispatch_origin
    from world.rules import RuleError

    try:
        selected = select_command(raw_string, cmdset, caller, match_index, session)
    except RuleError as error:
        selected = Selection(raw_string, (("__shortcut_error", "", ShortcutError(str(error)), 0, 1, ""),))
    matches = []
    for name, args, command, *rest in selected.matches:
        command = with_prompt(command)
        command.shortcut_invocation = dispatch_origin()  # 내부 재진입도 직접 입력으로 승격하지 않는다.
        matches.append((name, args, command, *rest))
    return matches
