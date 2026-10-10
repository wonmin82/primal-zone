"""예약 어휘와 저장된 명령의 버전별 변환. DB와 Evennia에 의존하지 않는다."""

FUTURE_RESERVED_COMMAND_NAMES = frozenset()
NEW_RESERVED_NAMES = frozenset({"소지품", "소", "ㅂㄷ", "ㄴㄷ", "ㄴㅅ", "ㅂㅅ", "상품", "도망", "응급처치", "진료", "내려", "단축어", "firstaid", "가진거", "치료", "힐", "heal"})

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


def migrate_shortcuts(shortcuts, occupied_names=()):
    """새 예약 이름은 보존하며 rename하고, 정확한 참조와 명령 위치만 변환한다."""
    from commands.shortcuts import MAX_NAME_CHARACTERS

    occupied = set(shortcuts) | set(occupied_names)
    renamed = {}
    for name in sorted(shortcuts):
        if name.casefold() not in NEW_RESERVED_NAMES:
            continue
        index = 1
        while True:
            suffix = "_개인" + (str(index) if index > 1 else "")
            candidate = name[:MAX_NAME_CHARACTERS - len(suffix)] + suffix
            if candidate.casefold() not in {key.casefold() for key in occupied}:
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


def migrate_progression_shortcuts(shortcuts, occupied_names=()):
    """v10의 새 명령과 충돌하는 개인 정의를 보존하고 제거된 action만 변환한다."""
    from commands.shortcuts import MAX_NAME_CHARACTERS

    reserved = {"사격", "shooting", "간파", "insight", "견제", "suppress", "호흡", "breathing", "사용"}
    occupied, renamed = set(shortcuts) | set(occupied_names), {}
    for name in sorted(shortcuts):
        if name.casefold() not in reserved:
            continue
        index = 1
        while True:
            suffix = "_개인" + (str(index) if index > 1 else "")
            candidate = name[:MAX_NAME_CHARACTERS - len(suffix)] + suffix
            if candidate.casefold() not in {key.casefold() for key in occupied}:
                break
            index += 1
        occupied.add(candidate)
        renamed[name] = candidate

    def command(value):
        stripped = value.strip()
        if stripped in renamed:
            return renamed[stripped]
        if stripped.casefold() in {"붕대", "응급처치", "firstaid"}:
            return "붕대 사용"
        if stripped.casefold() in {"방어", "guard"}:
            return "견제"
        return value

    return {renamed.get(name, name): [command(value) for value in values] for name, values in shortcuts.items()}


def migrate_safe_shortcuts(shortcuts, transform):
    """변환에는 정상 이름·명령 목록만 전달하며 비정상 항목을 원본으로 남긴다."""
    from world.rules import RuleError

    from commands.shortcuts import (
        normalized_keys,
        parse_definition,
        parse_shortcut_definition,
        shortcut_name,
    )

    if not isinstance(shortcuts, dict) or any(not isinstance(key, str) for key in shortcuts):
        return shortcuts
    safe, strings = {}, set()
    for key, value in shortcuts.items():
        try:
            name = shortcut_name(key)
            if len(normalized_keys(shortcuts, name)) != 1:
                continue
            if isinstance(value, str):
                parse_definition(value)
                values = parse_shortcut_definition(value)
                strings.add(key)
            else:
                values = value
            if not isinstance(values, list) or not values or any(not isinstance(v, str) for v in values):
                continue
            for command in values:
                parse_definition(command)
            safe[key] = values
        except RuleError:
            continue
    changed = transform(safe, occupied_names=shortcuts)
    preserved = {key: value for key, value in shortcuts.items() if key not in safe}
    # transform의 rename 기준을 항목별로 반복하지 않는다. 참조 변환도 기존 함수를 따른다.
    for (original_key, original_values), (key, value) in zip(safe.items(), changed.items(), strict=True):
        if isinstance(value, dict) and "변환 확인" in value:
            value = {"원본": shortcuts[original_key], "문제": value["변환 확인"]}
        elif original_key in strings:
            value = shortcuts[original_key] if value == original_values else value[0] if len(value) == 1 else ", ".join(value) + " 해"
        preserved[key] = value
    return preserved


def migrate_string_shortcuts(shortcuts):
    from world.rules import RuleError

    from commands.shortcuts import normalized_keys, safe_legacy_definition, shortcut_name

    if not isinstance(shortcuts, dict) or any(not isinstance(key, str) for key in shortcuts):
        return shortcuts
    result = dict(shortcuts)
    for key, value in shortcuts.items():
        try:
            if len(normalized_keys(shortcuts, shortcut_name(key))) != 1:
                continue
        except RuleError:
            continue
        converted = safe_legacy_definition(value)
        if converted is not None:
            result[key] = converted
    return result


def migrate_dialogue_shortcuts(shortcuts):
    """v12→v13 방법 B. 구형 NPC 동작과 공개 출력이 동등한 변환은 현재 없다."""
    from copy import deepcopy

    from world.rules import RuleError

    from commands.aliases import ARGUMENT_SHORTCUTS, SHORTCUTS
    from commands.shortcuts import MAX_NAME_CHARACTERS, parse_definition, parse_shortcut_definition

    if not isinstance(shortcuts, dict) or any(not isinstance(key, str) for key in shortcuts):
        return shortcuts
    # v12의 실제 명령/고정 단축어가 개인 이름보다 우선한다. 이력 해석용이다.
    actual = V12_RESERVED | frozenset({
        "말", "say", "대화", "조사", "수리", "귀환", "home", "휴식", "rest", "임무", "퀘스트", "quest",
        "상태", "상", "소지품", "소", "도움말", "help", "때려", "공격", "치료", "힐", "heal",
        "강타", "간파", "견제", "호흡", "사용", "도망", "장비", "무장", "착용", "벗어", "해제",
        "가져", "버려", "줘", "먹어", "마셔", "켜", "꺼", "확인", "넣어", "꺼내", "재장전", "채워",
        "환율", "교환", "배워", "배분", "재분배", "재훈련", "기술", "능력", "경험치", "날씨", "지도",
        "출구", "단축어", "줄임말", "해지", "종료", "quit", "exit", "@help", "정보", "가치",
        "파티", "파티초대", "파티수락", "파티거절", "파티탈퇴", "파티추방", "파티위임", "전리품방식",
        "소각", "소각 확정",
    }) | frozenset(SHORTCUTS) | frozenset(ARGUMENT_SHORTCUTS)
    normalized = {}
    for key in shortcuts:
        normalized.setdefault(key.casefold(), []).append(key)
    occupied = set(normalized)
    renamed = {}
    for key in shortcuts:
        if key.casefold() not in {"대화", "대답", "대화거부"}:
            continue
        index = 1
        while True:
            suffix = "_개인" + (str(index) if index > 1 else "")
            candidate = key[:MAX_NAME_CHARACTERS - len(suffix)] + suffix
            if candidate.casefold() not in occupied:
                break
            index += 1
        renamed[key] = candidate
        occupied.add(candidate.casefold())
    graph, reasons, converted, preserve_invalid = {}, {}, {}, set()

    def inspect(value, owner):
        commands = parse_shortcut_definition(value)
        rendered = []
        for command in commands:
            if command.startswith("'"):
                rendered.append(command)
                continue
            parts = command.rsplit(None, 1)
            verb = parts[-1].casefold()
            if verb == "대화":
                reasons[owner] = "구형 NPC 대화는 상태별 행동·개인 출력을 포함해 새 공개 Intent/개인 메시지와 동등하지 않습니다."
            elif "$" in verb:
                reasons[owner] = "변수로 생성하는 동사·간접 참조의 기존 대화 의미를 확정할 수 없습니다."
            elif verb not in actual and verb in normalized:
                refs = normalized[verb]
                graph[owner].update(refs)
                if len(refs) != 1:
                    reasons[owner] = "정규화 이름이 충돌하는 개인 참조의 의미를 확정할 수 없습니다."
                elif refs[0] in renamed:
                    command = (parts[0] + " " if len(parts) == 2 else "") + renamed[refs[0]]
            rendered.append(command)
        return rendered[0] if len(rendered) == 1 else ", ".join(rendered) + " 해"

    for key, value in shortcuts.items():
        graph[key] = set()
        if isinstance(value, dict):
            reasons[key] = str(value.get("문제", "불명확한 구형 저장 정의"))
            preserve_invalid.add(key)
            converted[key] = deepcopy(value)
            continue
        try:
            # v11에서 안전 변환되지 못한 목록은 원래 경계를 유지해 검사만 한다.
            if isinstance(value, list):
                if not value or any(not isinstance(command, str) for command in value):
                    raise RuleError("불명확한 구형 저장 정의")
                rendered = [inspect(command, key) for command in value]
                converted[key] = value if rendered == value else rendered
            elif isinstance(value, str):
                parse_definition(value)
                replacement = inspect(value, key)
                converted[key] = value if replacement == value.strip() else replacement
            else:
                raise RuleError("불명확한 구형 저장 정의")
        except RuleError as error:
            reasons[key] = str(error)
            converted[key] = deepcopy(value)
            preserve_invalid.add(key)
    changed = True
    while changed:
        changed = False
        for key, refs in graph.items():
            if key not in reasons and any(reference in reasons for reference in refs):
                reasons[key] = "비활성 또는 불명확한 개인 줄임말을 간접 참조합니다."
                changed = True
    result = {}
    for key, value in shortcuts.items():
        if key in reasons and key not in preserve_invalid and not (isinstance(value, dict) and "문제" in value):
            entry = {"원본": deepcopy(value), "문제": reasons[key]}
            if key in renamed:
                entry["원래이름"] = key
        else:
            entry = converted[key]
        result[renamed.get(key, key)] = entry
    return result


# v11 이하 저장 입력에서만 해석하며 현재 runtime alias를 등록하지 않는다.
V11_COMMANDS = {
    "보기": "봐", "look": "봐", "l": "봐", "둘러보기": "봐",
    "도움말": "도움", "안내": "도움", "?": "도움",
    "상태": "점수", "stat": "점수", "정보": "점수",
    "소지품": "가진거", "가방": "가진거", "i": "가진거", "인벤토리": "가진거",
    "접속자": "누구", "who": "누구", "공격": "때려", "사냥": "때려", "attack": "때려",
    "상품": "목록", "구매": "사", "buy": "사", "판매": "팔아", "sell": "팔아",
    "사격": "쏴", "shooting": "쏴", "진료": "회복", "treat": "회복",
    "회복": "붕대 사용",
    "map": "지도", "wear": "착용", "remove": "벗어", "value": "가치",
}
V11_STANDALONE = frozenset({"상태", "stat", "정보", "소지품", "가방", "i", "인벤토리", "접속자", "who", "사격", "shooting", "회복"})
V12_RESERVED = frozenset({"봐", "본", "보", "도움", "점수", "점", "가진거", "가진", "소지",
                         "누구", "누", "때려", "쳐", "목록", "품목", "품", "목", "메뉴", "사",
                         "구입", "팔아", "팔", "판", "쏴", "지", "경", "입어", "입", "벗", "집",
                         "준말", "얼마", "ㅇ", "ㅁ", "아", "시", "시2", "시3", "시4", "시5", "정보", "회복"})


def migrate_command_overhaul_shortcuts(shortcuts, occupied_names=()):
    """충돌 이름·후치형 참조를 보존하며 동사 자리만 v12로 변환한다."""
    from commands.shortcuts import MAX_NAME_CHARACTERS, parse_shortcut_definition

    occupied = {key.casefold() for key in (*shortcuts, *occupied_names)}
    renamed = {}
    for name in sorted(shortcuts):
        if name.casefold() not in V12_RESERVED:
            continue
        index = 1
        while True:
            suffix = "_개인" + (str(index) if index > 1 else "")
            candidate = name[:MAX_NAME_CHARACTERS - len(suffix)] + suffix
            if candidate.casefold() not in occupied:
                break
            index += 1
        renamed[name.casefold()] = candidate
        occupied.add(candidate.casefold())

    def command(value):
        stripped = value.strip()
        if stripped.startswith("'"):
            return value
        parts = stripped.rsplit(None, 1)
        verb = parts[-1].casefold()
        # 콤마 묶음의 기존 경계만 재귀 처리한다. 변수와 채팅 본문은 치환하지 않는다.
        if verb == "해" and len(parts) == 2:
            return ", ".join(command(v) for v in parse_shortcut_definition(stripped)) + " 해"
        if verb not in renamed and len(parts) == 2 and (
                verb in V11_STANDALONE or (verb in {"진료", "treat"} and parts[0].strip().isdecimal())):
            raise ValueError("구 명령의 인자 의미를 확정할 수 없습니다. 원본을 확인한 뒤 현재 명령으로 재등록하세요.")
        target = renamed.get(verb) or V11_COMMANDS.get(verb)
        if target is None:
            return value
        return (parts[0] + " " if len(parts) == 2 else "") + target

    result = {}
    for name, values in shortcuts.items():
        try:
            converted = [command(v) for v in values]
        except ValueError as error:
            converted = {"변환 확인": str(error)}
        result[renamed.get(name.casefold(), name)] = converted
    return result
