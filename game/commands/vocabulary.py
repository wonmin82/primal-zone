"""예약 어휘와 저장된 명령의 v8 변환. DB와 Evennia에 의존하지 않는다."""

FUTURE_RESERVED_COMMAND_NAMES = frozenset({"치료", "heal"})
NEW_RESERVED_NAMES = frozenset({"소지품", "소", "ㅂㄷ", "ㄴㄷ", "ㄴㅅ", "ㅂㅅ", "상품", "도망", "응급처치", "진료", "내려", "단축어", "firstaid", "가진거"}) | FUTURE_RESERVED_COMMAND_NAMES

# 저장된 v7 입력만 해석한다. 새 runtime alias를 제공하는 표가 아니다.
LEGACY_COMMANDS = {
    "가": "소지품", "가방": "소지품", "가진거": "소지품", "i": "소지품", "인벤토리": "소지품",
    "상점": "상품", "메뉴": "상품", "shop": "상품",
    "도주": "도망", "flee": "도망",
    "회복": "응급처치", "응급치료": "응급처치", "heal": "응급처치", "붕대": "응급처치",
    "치료": "진료", "treat": "진료", "내리기": "내려",
}
# v7 저장 데이터를 해석하는 과거 계약이다. 현재 플레이의 방향 단축어 SSOT와 독립적으로 유지한다.
V7_GLOBAL_SHORTCUTS = {
    "ㅂ": "북", "ㄴ": "남", "ㄷ": "동", "ㅅ": "서",
    "상": "상태", "능": "능력", "기": "기술", "장": "장비",
}


def migrate_shortcuts(shortcuts):
    """새 예약 이름은 보존하며 rename하고, 정확한 참조와 명령 위치만 변환한다."""
    from commands.shortcuts import MAX_NAME_CHARACTERS

    occupied = set(shortcuts)
    renamed = {}
    for name in sorted(shortcuts):
        if name.casefold() not in NEW_RESERVED_NAMES:
            continue
        index = 1
        while True:
            suffix = "_개인" + (str(index) if index > 1 else "")
            candidate = name[:MAX_NAME_CHARACTERS - len(suffix)] + suffix
            if candidate not in occupied:
                break
            index += 1
        renamed[name] = candidate
        occupied.add(candidate)

    def command(value):
        stripped = value.strip()
        # exact 개인 참조가 새 글로벌 이름으로 가려지지 않게 먼저 보존한다.
        if stripped in renamed:
            return renamed[stripped]
        if stripped.startswith("'"):
            return value
        if stripped.casefold() in V7_GLOBAL_SHORTCUTS:
            return V7_GLOBAL_SHORTCUTS[stripped.casefold()]
        if stripped.casefold() in LEGACY_COMMANDS:
            return LEGACY_COMMANDS[stripped.casefold()]
        parts = stripped.rsplit(None, 1)
        if len(parts) == 2 and parts[1].casefold() in LEGACY_COMMANDS and parts[1] != "가":
            # 후치 action만 교체한다. 말의 내용과 아이템/대상 이름은 그대로다.
            return parts[0] + " " + LEGACY_COMMANDS[parts[1].casefold()]
        return value

    return {renamed.get(name, name): [command(value) for value in values]
            for name, values in shortcuts.items()}
