"""후치형 개인 설정과 순차 실행 진입점. 실제 명령은 실행기가 매 단계 선택한다."""

from time import monotonic

from evennia import Command
from twisted.internet.defer import inlineCallbacks
from world import rules
from world import text as ft

from commands.base import GameCommand
from commands.shortcuts import (
    MAX_ARGUMENT_CHARACTERS,
    MAX_DEFINITION_CHARACTERS,
    MAX_SHORTCUTS,
    _input,
    delete_all_request,
    normalized_keys,
    parse_definition,
    parse_sequence,
    require_shortcut_store,
    shortcut_name,
    stored_key,
    validate_delete_all,
)


def reserved_names(cmdset):
    """잠긴 실제 명령도 예약한다. 다른 층/장소의 정적 이동 명령도 등록을 막는다."""
    from django.conf import settings
    from world.content import DIRECTION_ALIASES, ROOMS
    from world.progression import SKILLS

    from commands.aliases import ARGUMENT_SHORTCUTS, SHORTCUTS
    from commands.default_cmdsets import UnloggedinCmdSet
    from commands.registry import COMMANDS
    from commands.vocabulary import FUTURE_RESERVED_COMMAND_NAMES

    names = {"줄임말", "해지", "해", "전역"} | set(SHORTCUTS) | set(ARGUMENT_SHORTCUTS) | set(FUTURE_RESERVED_COMMAND_NAMES)
    names.update(data["name"] for data in SKILLS.values())
    for commands in (cmdset, UnloggedinCmdSet()):
        names.update(commands.get_all_cmd_keys_and_aliases())
    for cls in COMMANDS:
        names.update((cls.key, *cls.aliases))
    names.update(DIRECTION_ALIASES)
    names.update(DIRECTION_ALIASES.values())
    for room in ROOMS.values():
        names.update(room["exits"])
        names.update(room.get("blocked_exits", {}))
    return {normalized for name in names
            for normalized in (name.casefold(), name.casefold().lstrip(settings.CMD_IGNORE_PREFIXES))}



class Sequence(Command):
    read_only = True
    key = "해"
    input_style = "target"
    help_category = "원시구역"
    category = "편의"
    usage = "점수, 장비, 가진거 해"
    summary = "여러 명령을 순서대로 실행합니다. 각 명령은 실행 직전의 장소와 상태를 기준으로 처리합니다."
    help_sections = (
        ("사용법", ("명령1, 명령2 해",)),
        ("예시", ("점수, 장비 해", "북, 봐 해", "시체에서 모두 가져, 가진거 해")),
        ("실행 규칙", (
            ft.text("두 개 이상의 명령을 콤마로 구분하고 마지막에 ", ft.token("command", "해"), "를 붙입니다."),
            "앞선 명령이 완료되면 다음 명령을 실행하며, 이동 후에는 새 장소의 명령을 선택합니다.",
            "일반 게임 명령 실패 시 다음 명령을 계속 실행합니다.",
            "문법·줄임말 확장·순환·실행량 오류가 발생하면 남은 실행을 중단합니다.",
            "이미 완료된 동작의 결과는 되돌리지 않습니다.",
        )),
        ("제한", (
            "실제 명령 최대 10개 · 최종 명령 문자열 합계 최대 1,000자",
            "직접 입력한 즉석 묶음 최대 2,000자",
            "실행 후 추가 응답을 기다리는 대화형·progressive 명령은 내부에서 실행하지 않습니다.",
            ft.text(ft.token("command", "북 봐"), "처럼 입력할 때 인자를 함께 지정하는 일반 명령과는 다릅니다."),
            "동일 캐릭터에서는 한 번에 하나의 순차 실행만 허용합니다.",
        )),
        ("관련 도움말", ("줄임말 도움", "해지 도움")),
    )

    def initial_items(self):
        from commands.shortcut_execution import QueueItem

        _input(self.raw_string, MAX_DEFINITION_CHARACTERS)
        return tuple(QueueItem(text) for text in parse_sequence(self.args))

    def func(self):
        from commands.shortcut_execution import Execution, Invocation

        self.execution = None
        try:
            _input(self.raw_string, len(self.raw_string))  # 엔진이 trim하기 전 개행/제어문자도 거절한다.
            origin = getattr(self, "shortcut_invocation", None)
            if isinstance(origin, Invocation) and not origin.direct:
                raise rules.RuleError("단일 세그먼트에서 새 묶음을 생성할 수 없습니다.")
            self.execution = Execution.start(self.caller, self.session, self.initial_items())
            self.shortcut_invocation = Invocation(self.execution)
            self.execution.outputs.append(self)
        except rules.RuleError as error:
            self.caller.msg(ft.text(ft.token("error", str(error)), kind="error"))

    @inlineCallbacks
    def at_post_cmd(self):
        if self.execution:
            yield self.execution.run()


class PersonalShortcut(Sequence):
    key = "__personal_shortcut"

    def initial_items(self):
        from commands.shortcut_execution import QueueItem

        parts = self.raw_string.rsplit(None, 1)
        _input(parts[0] if len(parts) == 2 else "", MAX_ARGUMENT_CHARACTERS)
        return (QueueItem(self.raw_string),)


class GlobalShortcut(Sequence):
    key = "__argument_global_shortcut"

    def initial_items(self):
        from commands.shortcut_execution import QueueItem

        parts = self.raw_string.rsplit(None, 1)
        _input(parts[0] if len(parts) == 2 else "", MAX_ARGUMENT_CHARACTERS)
        return (QueueItem(self.global_command, global_expanded=True),)


class Shortcuts(GameCommand):
    read_only = True  # 조회/검증 실패 및 전체 삭제는 자연회복을 저장하지 않는다.
    key = "줄임말"
    aliases = ["준말"]
    input_style = "target"
    category = "편의"
    usage = "줄임말 · 이름 줄임말 · 이름 정의 줄임말 · 전역 줄임말 · 모두 삭제 줄임말 · 모두 삭제 확인 줄임말"
    summary = "자주 사용하는 명령을 개인 줄임말로 등록하고 실행합니다."
    help_sections = (
        ("사용법", ("줄임말", "이름 줄임말", "이름 정의 줄임말", "이름 해지",
                  "전역 줄임말", "모두 삭제 줄임말", "모두 삭제 확인 줄임말")),
        ("예시", ("정찰 $1 봐, 점수 해 줄임말", "북 정찰", "줍기 $* 가져 줄임말",
                "시체에서 모두 줍기", "실행 $* 줄임말", "점수 실행")),
        ("실행 규칙", (
            "이름만 지정하면 개별 조회하며, 정의를 지정하면 등록·수정합니다. 원본 내부 공백을 보존합니다.",
            "$1~$9: 위치 인자 · $*: 전체 인자 · $$: 리터럴 $",
            "변수는 한 번만 치환하며 변수로 행동 이름을 생성하거나 변경할 수 있습니다.",
            "$* 없이 위치 변수는 $1부터 연속해야 하며 부족하거나 사용하지 않은 인자는 거절합니다.",
            "실제 게임·엔진 명령·잠긴 명령·Exit·고정 단축어가 개인 줄임말보다 우선합니다.",
            "실제 명령과 문법이 충돌하면 개인 줄임말이 선택되지 않을 수 있습니다.",
            "각 명령은 실행 직전의 장소와 상태를 기준으로 처리합니다.",
            "변수 치환으로 새로운 묶음을 생성할 수 없습니다.",
            "등록 시 다른 정의의 순환을 검사하지 않으며 실제 실행 경로에서 순환을 검사합니다.",
            "일반 명령 실패 후에는 계속 실행하며 구조·확장 오류에서는 중단합니다.",
            "이미 완료된 동작은 되돌리지 않습니다. 콤마가 포함된 정의는 직접 등록해야 합니다.",
        )),
        ("제한", (
            "캐릭터당 최대 100개 · 이름은 한글·자모·영문·숫자·밑줄 1~20자",
            "원본 정의 최대 2,000자 · 호출 인자 최대 2,000자",
            "최종 명령 최대 10개 · 최종 명령 문자열 합계 최대 1,000자",
            "개인 줄임말 중첩 최대 5단계 · 동일 캐릭터 순차 실행은 한 번에 하나",
            "실행 후 추가 응답이 필요한 progressive 명령은 내부 실행 불가",
            "전체 삭제는 별도 직접 입력으로 요청하고 60초가 지나기 전에 별도 직접 입력으로 확인합니다.",
            "요청 후 목록이 바뀌면 확인할 수 없습니다. 확인은 성공·실패 모두 일회성입니다.",
            "구형 비활성 정의는 유효한 정의로 재등록하세요.",
        )),
        ("관련 도움말", ("해 도움", "해지 도움", "단축어 도움")),
    )

    def run(self):
        _input(self.raw_string, len(self.raw_string))
        args = self.args.strip()
        special = " ".join(args.split())
        if special in ("모두 삭제 확인", "모두 삭제"):
            self.delete_all(special)
            return
        if args == "전역":
            from commands.help_pages import shortcut_page

            self.caller.msg(shortcut_page())
            return
        shortcuts = self.caller.profile_snapshot().get("command_shortcuts", {})
        require_shortcut_store(shortcuts)
        if not args:
            self.listing(shortcuts)
            return
        parts = args.split(None, 1)
        name = shortcut_name(parts[0])
        key = stored_key(shortcuts, name)
        if len(parts) == 1:
            if key is None:
                raise rules.RuleError("등록된 개인 줄임말을 찾을 수 없습니다.")
            preview, omitted = self.preview(shortcuts[key], 2000)
            self.caller.msg(ft.sheet("개인 줄임말", f"{key} = {preview}",
                                     *( ["나머지 정의는 생략했습니다."] if omitted else [])))
            return
        definition = parts[1].strip()
        parse_definition(definition)  # 다른 정의·실제 행동·참조 그래프는 검사하지 않는다.
        from commands.shortcut_execution import Invocation

        origin = getattr(self, "shortcut_invocation", None)
        if isinstance(origin, Invocation) and not origin.direct and "," in definition:
            raise rules.RuleError("콤마를 포함하는 정의의 등록·수정은 직접 입력하세요.")
        if name in reserved_names(self.cmdset):
            raise rules.RuleError("기존 명령·별칭·시스템 단축어는 줄임말 이름으로 사용할 수 없습니다.")

        def register(profile):
            current = require_shortcut_store(profile.get("command_shortcuts"))
            old_key = stored_key(current, name)
            if old_key is None and len(current) >= MAX_SHORTCUTS:
                raise rules.RuleError("개인 줄임말은 100개까지 등록할 수 있습니다.")
            prospective = dict(current)
            if old_key is not None:
                del prospective[old_key]
            prospective[name] = definition
            profile["command_shortcuts"] = prospective
            return old_key is not None

        replaced = self.store_change(register)
        self.caller.msg("줄임말을 변경했습니다." if replaced else "줄임말을 추가했습니다.")

    def store_change(self, operation):
        # 다른 진행·회복 상태를 바꾸지 않는 동일 프로필 저장 트랜잭션이다.
        from world.multiplayer import world_change

        with world_change():
            profile = self.caller.profile()
            result = operation(profile)
            self.caller.save_profile(profile)
            return result

    @staticmethod
    def preview(value, limit):
        # 원본을 전부 직렬화해 거대한 임시 문자열을 만들지 않는다.
        import reprlib

        if isinstance(value, str):
            return value[:limit], len(value) > limit
        printer = reprlib.Repr()
        printer.maxstring = limit
        printer.maxother = limit
        printer.maxlist = 8
        printer.maxdict = 8
        preview = printer.repr(value)
        return preview[:limit], len(preview) > limit or "..." in preview

    def listing(self, shortcuts):
        entries = []
        # 100개를 초과한 구형 저장값은 삭제하지 않고 화면만 제한한다.
        for name in sorted(shortcuts)[:100]:
            value = shortcuts[name]
            collision = len(normalized_keys(shortcuts, name.casefold())) > 1
            try:
                shortcut_name(name)
                parse_definition(value)
                active = not collision
            except rules.RuleError:
                active = False
            preview, omitted = self.preview(value, 120)
            status = "정규화 충돌" if collision else "활성" if active else "비활성"
            entries.append(f"{name[:120]} [{status}] = {preview}" + (" (생략)" if omitted else ""))
        entries.append(f"전체 등록: {len(shortcuts)}개")
        if len(shortcuts) > 100:
            entries.append(f"{len(shortcuts) - 100}개 항목을 생략했습니다.")
        entries.append("비활성 항목은 유효한 정의로 재등록하세요. 이름 충돌·잘못된 이름은 전체 삭제 또는 관리자 복구가 필요합니다.")
        self.caller.msg(ft.sheet("개인 줄임말", *entries))

    def delete_all(self, args):
        from commands.shortcut_execution import Invocation

        origin = getattr(self, "shortcut_invocation", None)
        if not isinstance(origin, Invocation) or not origin.direct:
            raise rules.RuleError("전체 삭제 요청과 확인은 각각 직접 입력하세요. 묶음·줄임말로 실행할 수 없습니다.")
        if args == "모두 삭제":
            shortcuts = self.caller.profile_snapshot().get("command_shortcuts", {})
            request = delete_all_request(shortcuts, monotonic())
            self.caller.ndb.shortcut_delete_all_request = request
            if request is None:
                self.caller.msg("삭제할 개인 줄임말이 없습니다.")
                return
            self.caller.msg(f"개인 줄임말 {len(shortcuts)}개를 모두 삭제합니다. 계속하려면 '모두 삭제 확인 줄임말'을 입력하세요.")
            return
        request = self.caller.ndb.shortcut_delete_all_request
        self.caller.ndb.shortcut_delete_all_request = None  # 직접 확인은 성공/실패 모두 일회성이다.

        def clear(profile):
            current = profile.get("command_shortcuts")
            validate_delete_all(request, current, monotonic())
            count = len(current)
            profile["command_shortcuts"] = {}
            return count

        count = self.store_change(clear)
        self.caller.msg(f"개인 줄임말 {count}개를 모두 삭제했습니다.")


class DeleteShortcut(Shortcuts):
    aliases = []
    key = "해지"
    usage = "이름 해지"
    summary = "등록한 개인 줄임말 하나를 삭제합니다."
    help_sections = (
        ("사용법", ("이름 해지",)),
        ("예시", ("장확 해지", "모두 해지")),
        ("실행 규칙", (
            "지정한 개인 줄임말 하나만 삭제합니다.",
            ft.text(ft.token("command", "모두 해지"), "는 전체 삭제가 아니라 모두라는 이름의 줄임말 하나만 삭제합니다."),
            "다른 개인 줄임말의 참조나 정의를 연쇄 변경하지 않습니다.",
        )),
        ("제한", (
            ft.text("전체 삭제는 ", ft.token("command", "모두 삭제 줄임말"), "로 별도 요청해야 합니다."),
            ft.text(ft.token("command", "모두 삭제 확인 줄임말"), "을 요청 후 60초가 지나기 전에 별도로 직접 입력하세요."),
        )),
        ("관련 도움말", ("줄임말 도움", "해 도움")),
    )

    def run(self):
        _input(self.raw_string, len(self.raw_string))
        name = shortcut_name(self.args.strip())

        def remove(profile):
            current = require_shortcut_store(profile.get("command_shortcuts"))
            key = stored_key(current, name)
            if key is None:
                raise rules.RuleError("등록된 개인 줄임말을 찾을 수 없습니다.")
            del current[key]

        self.store_change(remove)
        self.caller.msg("줄임말을 삭제했습니다.")
