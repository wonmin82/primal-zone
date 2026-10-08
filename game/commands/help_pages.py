"""게임 도움말의 분류와 표시. 실제 명령 detail은 registry metadata를 사용한다."""

from world import text as ft
from world.content.directions import DIRECTION_ALIASES, DIRECTION_ORDER, DIRECTION_SHORTCUTS

from commands.aliases import INFORMATION_SHORTCUTS, SHORTCUTS

# 표시 순서, 접근 query, 대표 명령을 함께 관리한다. 전체 소속은 class.category다.
HELP_CATEGORIES = {
    "이동·탐사": {"query": "이동", "examples": ("보기", "출구", "지도", "임무")},
    "전투·회복": {"query": "전투", "examples": ("공격", "강타", "사격", "치료", "도망")},
    "아이템·보급": {"query": "아이템", "examples": ("소지품", "장비", "가져", "상품")},
    "성장": {"query": "성장", "examples": ("상태", "능력", "경험치", "기술")},
    "파티·교류": {"query": "교류", "examples": ("파티", "파티초대", "말")},
    "편의": {"query": "편의", "examples": ("해", "줄임말", "단축어")},
}


def commands_text(values):
    return ft.join([ft.token("command", value) for value in values], " · ")


def root_page():
    lines = []
    for category, data in HELP_CATEGORIES.items():
        examples = commands_text(data["examples"])
        if category == "이동·탐사":
            examples = ft.text("8방향 이동 · ", examples)
        lines.append(ft.text(category, " | ", examples))
    queries = [data["query"] + " 도움말" for data in HELP_CATEGORIES.values()]
    lines.extend(["", "분류:", commands_text(queries[:3]), commands_text(queries[3:]),
                  "", "개별 명령:", commands_text(["공격 도움말", "상품 도움말", "줄임말 도움말"]),
                  "", "입력 규칙:", commands_text(["입력 도움말"])])
    return ft.compact("도움말", *lines)


def category_page(category, commands):
    lines = [commands_text([cls.key for cls in commands if getattr(cls, "category", None) == category])]
    if category == "이동·탐사":
        lines.extend(["", ft.join([ft.token("direction", value) for value in DIRECTION_ORDER], " · "),
                      ft.join([ft.token("direction", alias) for alias in DIRECTION_ALIASES.values()], " · "),
                      commands_text(DIRECTION_SHORTCUTS),
                      "", commands_text(["계단", "위", "아래", "나가기", "승강기", "1층", "2층", "3층", "4층", "5층", "옥상"]),
                      "실제 출구 이름만 입력해 이동합니다. 계단실은 위·아래·나가기, 승강기 안은 층별 출구로 연결됩니다."])
    elif category == "전투·회복":
        lines.extend(["", "치료는 정신력을, 붕대 사용은 소지한 붕대 하나를 사용합니다. 방어는 패시브 기술입니다.",
                      "진료는 의무관에게 받습니다. 휴식은 의무실 침대에서 이용합니다."])
    elif category == "아이템·보급":
        lines.append(ft.text("대상은 ", ft.token("command", "보기"), "로 확인할 수 있습니다."))
        lines.extend(["보급칩은 칩 단위로 옮기며, 판매는 장착하지 않은 물건만 취급합니다.",
                      commands_text(["철수에게 20칩 줘", "20칩 버려", "시체에서 20칩 가져",
                                     "절단마체테 가치", "절단마체테 판매"])])
    lines.extend(["", ft.text("상세: ", ft.token("command", "명령이름 도움말"))])
    return ft.compact(category, *lines)


def input_page():
    return ft.compact("입력", "기본", "대상이름 행동",
                      ft.usage("어린청소룡 공격 · 윤대장 대화", {"공격", "대화"}),
                      "", "선택", "대상 2 · 대상 모두", "",
                      "전리품", commands_text(["시체에서 모두 가져", "모든 시체에서 회수부품 모두 가져"]),
                      "", "보급칩", commands_text(["철수에게 20칩 줘", "20칩 버려", "시체에서 20칩 가져"]),
                      "", "관계", "플레이어에게 · 보관함에 · 보관함에서", "",
                      "묶음 실행", commands_text(["상태, 장비, 소지품 해"]),
                      "", "개인 설정", commands_text(["줄임말 도움말"]),
                      "", "기본 단축어", commands_text(["단축어"]))


def shortcut_page():
    lines = []
    for label, shortcuts, role in (("이동", DIRECTION_SHORTCUTS, "direction"),
                                   ("정보", INFORMATION_SHORTCUTS, "command")):
        lines.append(label)
        entries = [ft.text(ft.token("command", source), " → ", ft.token(role, target))
                   for source, target in shortcuts.items()]
        lines.extend(ft.join(entries[index:index + 4], " · ") for index in range(0, len(entries), 4))
        lines.append("")
    lines.extend(["게임에서 기본 제공하는 고정 단축어입니다.",
                  ft.text("개인 설정은 ", ft.token("command", "줄임말"), "로 확인하고 관리할 수 있습니다.")])
    return ft.compact("단축어", *lines)


def help_page(query, commands):
    """실제 명령 > 방향 > 분류/topic. 개인 줄임말을 help query로 확장하지 않는다."""
    query = query.strip().casefold()
    query = SHORTCUTS.get(query, query)
    selected = next((cls for cls in commands if query in {name.casefold() for name in (cls.key, *cls.aliases)}), None)
    if selected:
        lines = [selected.summary, ft.text("사용법: ", ft.usage(getattr(selected, "usage", "") or selected.key,
                                                            {selected.key, *selected.aliases}))]
        if selected.aliases:
            lines.append(ft.text("별칭: ", commands_text(selected.aliases)))
        shortcuts = [source for source, target in SHORTCUTS.items() if target == selected.key]
        if shortcuts:
            lines.append(ft.text("단축어: ", commands_text(shortcuts)))
        if selected.key == "능력":
            from world.progression import ATTRIBUTES

            lines.extend(f"{data['name']} | {data['description']}" for data in ATTRIBUTES.values())
        return ft.compact(ft.token("command", selected.key), *lines)
    if query in DIRECTION_ALIASES or query in DIRECTION_ALIASES.values():
        return category_page("이동·탐사", commands)
    for category, data in HELP_CATEGORIES.items():
        if query in (category, data["query"]):
            return category_page(category, commands)
    if query == "입력":
        return input_page()
    return None
