"""공통 선택 문법과 안정적인 정렬. 번호는 저장하지 않는 표시용 인덱스다."""

from dataclasses import dataclass
from enum import StrEnum

from world.rules import RuleError


class Mode(StrEnum):
    DEFAULT = "default"
    INDEX = "index"
    ALL = "all"


@dataclass(frozen=True)
class TargetSelector:
    name: str
    mode: Mode = Mode.DEFAULT
    index: int | None = None


@dataclass(frozen=True)
class LootRequest:
    target: TargetSelector
    source: TargetSelector | None = None


def normalized(value):
    return "".join(str(value).split()).translate(str.maketrans("", "", ".-_" )).casefold()


def parse_selector(value, known_names=()):
    value = value.strip()
    # 실제 이름 자체가 숫자로 끝나면 이름을 우선한다.
    known = {normalized(name) for name in known_names}
    if normalized(value) in known:
        return TargetSelector(value)
    parts = value.split()
    if not parts:
        raise RuleError("대상 이름을 입력하세요.")
    if parts[0] in ("전체", "모든"):
        raise RuleError("대상 뒤에 '모두'를 붙이세요. 예: 회수부품 모두 가져")
    suffix = parts[-1]
    if suffix == "모두" or suffix.isdecimal():
        if len(parts) == 1 or (
            (parts[-2] == "모두" or parts[-2].isdecimal())
            and normalized(" ".join(parts[:-1])) not in known
        ):
            raise RuleError("번호와 '모두' 중 하나만 대상 뒤에 붙이세요.")
        name = " ".join(parts[:-1])
        if suffix == "모두":
            return TargetSelector(name, Mode.ALL)
        index = int(suffix)
        if index < 1:
            raise RuleError("대상 번호는 1부터 시작합니다.")
        return TargetSelector(name, Mode.INDEX, index)
    return TargetSelector(value)


def parse_loot(value, known_names=()):
    # 출처 구문은 접미 조사 '에서'가 붙은 토큰 경계에서만 나눈다.
    words = value.strip().split()
    boundaries = [i for i, word in enumerate(words) if word.endswith("에서")]
    source = None
    if boundaries:
        if len(boundaries) != 1:
            raise RuleError("출처는 하나의 선택자로 지정하세요.")
        position = boundaries[0]
        source_text = " ".join(words[:position] + [words[position][:-2]])
        if source_text.startswith("모든 "):
            name = source_text[len("모든 ") :].strip()
            if name != "시체":
                raise RuleError("현재 지원하는 출처는 시체입니다. 예: 모든 시체에서 모두 가져")
            source = TargetSelector(name, Mode.ALL)
        else:
            source = parse_selector(source_text, ("시체",))
            if source.name != "시체" or source.mode == Mode.ALL:
                raise RuleError("시체에서 · 시체 2에서 · 모든 시체에서처럼 지정하세요.")
        value = " ".join(words[position + 1 :])
    target = (
        TargetSelector("전리품", Mode.ALL)
        if value.strip() == "모두"
        else parse_selector(value, known_names)
    )
    if source and source.mode == Mode.ALL and target.mode != Mode.ALL:
        raise RuleError(
            "여러 시체에서 가져오려면 가져올 대상에도 '모두'를 붙이세요. "
            "예: 모든 시체에서 회수부품 모두 가져"
        )
    return LootRequest(target, source)


def require_single(selector, action):
    if selector.mode == Mode.ALL:
        raise RuleError(
            f"'{action}'은 한 대상을 지정하는 행동입니다. "
            f"{selector.name} {action} 또는 {selector.name} 2 {action}처럼 사용하세요."
        )


def ordered(objects):
    return sorted(objects, key=lambda obj: obj.id)


def names(obj):
    from typeclasses.loot import Corpse

    values = [obj.key, *obj.aliases.all()]
    if isinstance(obj, Corpse):
        values.append("시체")
    if obj.db.enemy_id:
        values.append(obj.db.enemy_id)
    return values


def room_objects(caller, room=None, observed_at=None):
    from typeclasses.enemies import Enemy

    from world.observation import can_perceive, context_for

    room = caller.location if room is None else room
    context = context_for(caller, room, observed_at)
    return (
        ordered(
            obj
            for obj in room.contents
            if can_perceive(obj, context) and (not isinstance(obj, Enemy) or obj.db.state == "alive")
        )
        if room
        else []
    )


def item_selector(value, collection, action):
    """장비/학습 등 단일 데이터 대상도 같은 접미 문법을 사용한다."""
    from world.content import find_id

    known = [name for key, data in collection.items() for name in (key, data["name"], *data.get("aliases", []))]
    selector = parse_selector(value, known)
    if action != "봐":
        require_single(selector, action)
    identity = find_id(collection, selector.name)
    if not identity:
        raise RuleError("대상 이름을 확인하세요.")
    select([identity], selector)
    return identity


def stack_selector(value, collection, action, *, allow_all=True):
    """소지품/보관 아이템은 개체 번호가 아닌 스택이다."""
    from world.content import find_id

    known = [name for key, data in collection.items() for name in (key, data["name"], *data.get("aliases", []))]
    selector = parse_selector(value, known)
    if not allow_all:
        require_single(selector, action)
    if selector.mode == Mode.INDEX:
        raise RuleError("소지품과 보관 아이템은 번호 없이 하나, 또는 '모두'로 지정하세요.")
    identity = find_id(collection, selector.name)
    if not identity:
        raise RuleError("아이템 이름을 확인하세요.")
    return identity, selector.mode == Mode.ALL


def parse_relation(value, particle, known_names=()):
    """에게/에/에서의 경계만 추출하고 개체 선택은 기존 parser에 맡긴다."""
    parts = value.split()
    known = {normalized(name) for name in known_names}
    for index, part in enumerate(parts[:-1]):
        if not part.endswith(particle):
            continue
        left = " ".join([*parts[:index], part[: -len(particle)]]).strip()
        selector = parse_selector(left, known_names)
        if known and normalized(selector.name) not in known:
            continue
        return selector, " ".join(parts[index + 1 :])
    raise RuleError(f"대상 뒤에 '{particle}'를 붙이고 아이템을 지정하세요.")


def visible(obj, caller):
    return obj.access(caller, "view")


def matching(objects, selector, name_values=names):
    return [
        obj
        for obj in objects
        if normalized(selector.name) in {normalized(name) for name in name_values(obj)}
    ]


def select(candidates, selector):
    """후보 순서를 그대로 사용한다. 권한/보상 조건으로 기본 대상을 건너뛰지 않는다."""
    if not candidates:
        raise RuleError(f"이곳에서 '{selector.name}' 대상을 찾을 수 없습니다.")
    if selector.mode == Mode.ALL:
        return candidates
    index = selector.index if selector.mode == Mode.INDEX else 1
    if index > len(candidates):
        raise RuleError(f"'{selector.name}'의 {index}번째 대상은 없습니다.")
    return [candidates[index - 1]]


def strict_single(candidates, selector, action):
    """모호한 기본 선택은 거절하며 공통 번호/ALL 규약을 재사용한다."""
    require_single(selector, action)
    if selector.mode == Mode.DEFAULT and len(candidates) > 1:
        raise RuleError("대상이 여러 명입니다. 이름과 번호를 지정하세요.")
    return select(candidates, selector)[0]


def resolve(objects, selector, caller, action=None, supports=None, *, observed_at=None):
    from world.observation import can_perceive, context_for

    if action:
        require_single(selector, action)
    candidates = matching(ordered(obj for obj in objects if visible(obj, caller)), selector)
    if any(not obj.destination for obj in candidates):
        context = context_for(caller, observed_at=observed_at)
        candidates = [obj for obj in candidates if can_perceive(obj, context)]
    if supports and selector.mode == Mode.DEFAULT:
        candidates = [obj for obj in candidates if supports(obj)]
    selected = select(candidates, selector)
    if supports and any(not supports(obj) for obj in selected):
        raise RuleError(f"지정한 대상은 '{action}' 행동을 지원하지 않습니다.")
    return selected


def labels(objects, name_values=lambda obj: obj.key):
    """동일 표시 이름끼리만 번호를 붙인다. 입력 후보와 동일한 순서를 사용한다."""
    pool = ordered(objects)
    result = {}
    for obj in pool:
        name = name_values(obj)
        peers = [other for other in pool if normalized(name_values(other)) == normalized(name)]
        result[obj.id] = f"{name} {peers.index(obj) + 1}" if len(peers) > 1 else name
    return result
