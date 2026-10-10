"""게임 의미를 생성 시점에 보존하는 작은 텍스트 조각 포맷. DB/Evennia 비의존."""

import unicodedata

# 터미널 근사색. 웹의 실제 팔레트는 CSS 변수 한 곳에서 관리한다.
ANSI = {
    "text": "",
    "muted": "|w",
    "title": "|w",
    "hostile": "|r",
    "npc": "|c",
    "player": "|g",
    "object": "|y",
    "remains": "|m",
    "item": "|m",
    "command": "|g",
    "direction": "|g",
    "reward": "|y",
    "warning": "|y",
    "success": "|g",
    "error": "|r",
    "critical": "|r|h",
    "dialogue_topic": "|c",
    "dialogue_action": "|y|h",
}


def literal(value):
    return "".join(c for c in str(value) if c in "\n\t" or unicodedata.category(c) != "Cc")


class Text(str):
    """기본 문자열은 색 없는 내용이며 wire/터미널 변환에서만 색을 적용한다."""

    def __new__(cls, segments, kind="event"):
        obj = super().__new__(cls, "".join(part["text"] for part in segments))
        obj.segments = segments
        obj.kind = kind
        return obj

    def ansi(self):
        return "".join(
            ANSI[part["role"]] + part["text"].replace("|", "||") + "|n" for part in self.segments
        )


def token(role, value):
    if role not in ANSI:
        raise ValueError("알 수 없는 텍스트 역할")
    return Text([{"text": literal(value), "role": role}])


def dialogue_keyword(keyword, kind, selection=None):
    """활성 키워드의 선택 권한은 서버 불투명 토큰만 전달한다."""
    role = "dialogue_" + kind if selection else "text"
    segment = {"text": literal(f"〈{keyword}〉"), "role": role}
    if selection:
        segment["dialogue_selection"] = selection
    return Text([segment])


def text(*parts, kind="event"):
    segments = []
    for part in parts:
        segments.extend(part.segments if isinstance(part, Text) else token("text", part).segments)
    return Text(segments, kind)


def join(parts, separator="\n"):
    result = []
    for part in parts:
        if result:
            result.append(separator)
        result.append(part)
    return text(*result)


def resource_value(current, maximum):
    ratio = current * 100 / maximum if maximum else 0
    role = "critical" if current == 0 else "success" if ratio >= 67 else "warning" if ratio >= 34 else "error"
    return token(role, current)


def resource_prompt(profile, values):
    return text("[ ", resource_value(profile["hp"], values["max_hp"]),
                f"/{values['max_hp']} · ", resource_value(profile["mental"], values["max_mental"]),
                f"/{values['max_mental']} ] >", kind="prompt")


def particle(value, pair="이/가"):
    last = str(value)[-1:] or " "
    # Resource amounts and attribute values are read as Sino-Korean numbers.
    if last in "0123456789":
        last = "영일이삼사오육칠팔구"[int(last)]
    consonant = 0xAC00 <= ord(last) <= 0xD7A3 and (ord(last) - 0xAC00) % 28 != 0
    if pair == "으로/로" and consonant and (ord(last) - 0xAC00) % 28 == 8:
        consonant = False
    return pair.split("/")[0 if consonant else 1]


def named(role, value, pair=None):
    return text(token(role, value), particle(value, pair) if pair else "")


def item(identity):
    from world.content import ITEMS

    return token("item", ITEMS[identity]["name"])


def sheet(title, *lines):
    return text(
        token("muted", "────────────────────────\n"),
        title,
        token("muted", "\n────────────────────────\n\n"),
        join(lines),
        kind="sheet",
    )


def compact(title, *lines, summary=""):
    """조회 제목과 첫 내용을 붙이고 의미 조각을 유지하는 작은 정보창."""
    heading = text(token("title", "["), title, token("title", "]"), " " if summary else "", summary)
    return text(join([heading, *lines]), kind="sheet")


def display_width(value):
    """색 변환 전 visible text의 기존 동아시아 표시 폭 정책."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(value))


def row(label, value, width=12):
    columns = display_width(label)
    return text(label, " " * max(2, width - columns), value)


def actions(values):
    if not values:
        return text("지금은 가능한 행동이 없다.")
    return text("가능한 행동 : ", join([token("command", value) for value in values], " · "))


def usage(examples, action_names):
    """명령 메타데이터의 사용 예에서 끝의 등록된 행동 토큰만 강조한다."""
    lines = []
    for example in examples.split(" · "):
        target, separator, action = example.rpartition(" ")
        lines.append(
            text(target, separator, token("command", action))
            if action in action_names
            else text(example)
        )
    return join(lines, " · ")
