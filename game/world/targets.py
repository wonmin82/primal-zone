"""공통 선택 문법. B-1 대상은 영속 번호, 그 밖의 목록은 기존 인덱스를 쓴다."""

import re
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
    exact: bool = False


@dataclass(frozen=True)
class LootRequest:
    target: TargetSelector
    source: TargetSelector | None = None


def normalized(value):
    return "".join(str(value).split()).translate(str.maketrans("", "", ".-_" )).casefold()


MAX_SELECTION_LENGTH = 1024
MAX_SELECTION_NUMBER = 2**63 - 1
_QUOTED_NAME = re.compile(r'"(?:[^"\\\x00-\x1f]|\\["\\])+"')
_EXACT = re.compile(r'(?P<name>' + _QUOTED_NAME.pattern + r')[ \t]+(?P<number>[1-9][0-9]{0,18})')


def parse_exact_selector(value):
    """완전한 B-1 인용 구문만 인식한다. 무효한 구문은 일반 실명 확인에 넘긴다."""
    if len(value) > MAX_SELECTION_LENGTH or not (match := _EXACT.fullmatch(value.strip())):
        return None
    number = int(match["number"])
    if number > MAX_SELECTION_NUMBER:
        return None
    name = re.sub(r'\\(["\\])', r'\1', match["name"][1:-1])
    return TargetSelector(name, Mode.INDEX, number, exact=True)


def quote_name(name):
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def exact_selector(name, number):
    return f"{quote_name(name)} {number}"


def quoted_name_spans(value):
    """복합 문법에서 이름 안의 조사·공백을 구문 경계로 쓰지 않는다."""
    return tuple(match.span() for match in _QUOTED_NAME.finditer(value))


def parse_selector(value, known_names=(), *, b1=False, literal_names=None):
    if isinstance(value, TargetSelector):
        return value
    if b1 and len(value) > MAX_SELECTION_LENGTH:
        raise RuleError(f"대상 선택은 {MAX_SELECTION_LENGTH}자 이하로 입력하세요.")
    value = value.strip()
    if b1 and (exact := parse_exact_selector(value)):
        return exact
    # 실제 이름 자체가 숫자로 끝나면 이름을 우선한다.
    known = {normalized(name) for name in known_names}
    if b1 and value.startswith('"'):
        literals = known if literal_names is None else {normalized(name) for name in literal_names}
        if normalized(value) not in literals:
            raise RuleError('정확한 대상은 "정식 선택 이름" 번호 형식으로 지정하세요.')
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
        try:
            index = int(suffix)
        except ValueError:
            raise RuleError("대상 번호가 너무 큽니다.") from None
        if index < 1:
            raise RuleError("대상 번호는 1부터 시작합니다.")
        if b1 and index > MAX_SELECTION_NUMBER:
            raise RuleError("대상 번호가 너무 큽니다.")
        return TargetSelector(name, Mode.INDEX, index)
    return TargetSelector(value)


def relation_parts(value, particle, *, b1=False):
    """공백 경계에 붙은 조사만 찾고 인용 내부의 원문을 보존한다."""
    spans = quoted_name_spans(value) if b1 else ()
    for match in re.finditer(re.escape(particle) + r"(?=\s|$)", value):
        start, end = match.span()
        if not any(left <= start < right for left, right in spans):
            yield value[:start].strip(), value[end:].strip()


def loot_parts(value):
    """출처만 분리한다. 품목 이름은 확정된 Source Scope에서 해석한다."""
    # 출처 구문은 접미 조사 '에서'가 붙은 토큰 경계에서만 나눈다.
    if len(value) > 2 * MAX_SELECTION_LENGTH + 16:
        raise RuleError("전리품 출처와 대상 입력이 너무 깁니다.")
    boundaries = list(relation_parts(value, "에서", b1=True))
    source = None
    if boundaries:
        if len(boundaries) != 1:
            raise RuleError("출처는 하나의 선택자로 지정하세요.")
        source_text, value = boundaries[0]
        if not source_text.startswith('"'):
            source_text = " ".join(source_text.split())
        if source_text.startswith("모든 "):
            name = source_text[len("모든 ") :].strip()
            if name != "시체":
                raise RuleError("현재 지원하는 출처는 시체입니다. 예: 모든 시체에서 모두 가져")
            source = TargetSelector(name, Mode.ALL)
        else:
            source = parse_selector(source_text, ("시체",), b1=True)
            if source.name != "시체" or source.mode == Mode.ALL:
                raise RuleError("시체에서 · 시체 2에서 · 모든 시체에서처럼 지정하세요.")
    return value, source


def parse_loot(value, known_names=(), *, literal_names=None):
    value, source = loot_parts(value)
    return loot_request(value, source, known_names, literal_names=literal_names)


def loot_request(value, source, known_names=(), *, literal_names=None):
    target = (
        TargetSelector("전리품", Mode.ALL)
        if value.strip() == "모두"
        else parse_selector(value, known_names, b1=True, literal_names=literal_names)
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
    combat_id = getattr(obj, "combat_definition_id", None)
    if combat_id and getattr(obj, "supports_shared_combat", False):
        values.append(combat_id)
    return values


def room_objects(caller, room=None, observed_at=None):

    from world.observation import can_perceive, context_for

    room = caller.location if room is None else room
    context = context_for(caller, room, observed_at)
    return (
        ordered(
            obj
            for obj in room.contents
            if can_perceive(obj, context) and (not getattr(obj, "supports_shared_combat", False) or obj.db.state == "alive")
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


def parse_relation(value, particle, known_names=(), *, b1=False):
    """에게/에/에서의 경계만 추출하고 개체 선택은 기존 parser에 맡긴다."""
    known = {normalized(name) for name in known_names}
    for left, right in relation_parts(value, particle, b1=b1):
        if not right:
            continue
        selector = parse_selector(left, known_names, b1=b1)
        if known and not selector.exact and normalized(selector.name) not in known:
            continue
        return selector, right
    raise RuleError(f"대상 뒤에 '{particle}'를 붙이고 아이템을 지정하세요.")


def visible(obj, caller):
    return obj.access(caller, "view")


def matching(objects, selector, name_values=names):
    if selector.exact:
        from world.selection_numbers.api import descriptor

        return [obj for obj in objects if (record := descriptor(obj)) and record.name == selector.name]
    return [
        obj
        for obj in objects
        if normalized(selector.name) in {normalized(name) for name in name_values(obj)}
    ]


def select(candidates, selector):
    """후보 순서를 그대로 사용한다. 권한/보상 조건으로 기본 대상을 건너뛰지 않는다."""
    if selector.exact:
        raise RuleError("지금 선택할 수 없는 대상입니다.")
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


def select_native_items(items, query, action=None):
    """Native Root/Inside 후보의 순서를 유지하고 명시 번호는 저장 행으로만 해석한다."""
    from world.actions.resolver import matching_records
    from world.content import ITEMS
    from world.selection_numbers.api import descriptor, numbered_records

    items = tuple(items)

    def item_names(item):
        definition = ITEMS[item.definition_id]
        return definition["name"], item.definition_id, *definition.get("aliases", ())

    selector = parse_selector(
        query, [name for item in items for name in item_names(item)], b1=True,
        literal_names=[ITEMS[item.definition_id]["name"] for item in items],
    )
    if action:
        require_single(selector, action)
    if selector.mode != Mode.INDEX:
        candidates = matching(items, selector, item_names)
        if selector.mode == Mode.DEFAULT:
            formal = [item for item in candidates
                      if normalized(ITEMS[item.definition_id]["name"]) == normalized(selector.name)]
            if formal:
                candidates = formal
        return select(candidates, selector), selector

    pairs = [(item, record) for item in items if (record := descriptor(item)) is not None]
    records = numbered_records(record for _, record in pairs)
    references = {record.reference for record in matching_records(records, selector)}
    candidates = [item for item, record in pairs if record.reference in references]
    return select(candidates, TargetSelector(selector.name)), selector


def resolve(objects, selector, caller, action=None, supports=None, *, observed_at=None, numbered=None):
    from world.actions.schema import ReferenceKind
    from world.observation import can_perceive, context_for
    from world.selection_numbers.api import descriptor, numbered_records

    if action:
        require_single(selector, action)
    candidates = matching(ordered(obj for obj in objects if visible(obj, caller)), selector)
    if selector.exact or any(not obj.destination for obj in candidates):
        context = context_for(caller, observed_at=observed_at)
        candidates = [obj for obj in candidates if can_perceive(obj, context)]
    records = [descriptor(obj) for obj in candidates]
    if not selector.exact and any(getattr(obj, "supports_shared_combat", False) for obj in candidates):
        # 실제 이름이 먼저다. 특히 숫자 접미 실명을 다른 실물의 별칭이나
        # INDEX로 바꿔 해석하지 않는다(§4.14).
        exact = [(obj, record) for obj, record in zip(candidates, records)
                 if normalized(obj.key) == normalized(selector.name)]
        if exact:
            candidates, records = map(list, zip(*exact))
            if selector.mode == Mode.DEFAULT and selector.name[-1:].isdecimal() and len(exact) > 1:
                raise RuleError("숫자로 끝나는 실제 이름이 여러 대상과 일치합니다. 다른 고유 이름을 지정하세요.")
    if supports and selector.mode == Mode.DEFAULT:
        candidates = [obj for obj in candidates if supports(obj)]
        records = [descriptor(obj) for obj in candidates]
    by_reference = {record.reference: obj for obj, record in zip(candidates, records)
                    if record and record.reference.kind != ReferenceKind.ROOM}
    if selector.mode == Mode.INDEX and (selector.exact or by_reference):
        from world.actions.resolver import matching_records

        if not selector.exact and len(by_reference) != len(candidates):
            raise RuleError("대상 번호가 겹칩니다. 대상을 고유하게 지정하세요.")
        available = (numbered_records(records) if numbered is None else
                     [numbered[ref] for ref in by_reference if ref in numbered])
        selected = select([by_reference[record.reference] for record in matching_records(available, selector)],
                          TargetSelector(selector.name))
    elif any(getattr(obj, "supports_shared_combat", False) for obj in candidates):
        # Enemy는 Action Provider가 아니어도 B-1 대상이다. 생존/시야로 줄어든
        # 후보 순서를 명시 번호로 재해석하지 않는다. DEFAULT/ALL과 이름·별칭은
        # 기존 전투 선택 정책을 유지하고, 영속 번호 조회만 SSOT를 사용한다.
        if not all(record for record in records) or len({(record.scope_id, record.group_id, record.reference.kind)
                                                        for record in records}) != 1:
            raise RuleError("서로 다른 선택 그룹의 별칭이 겹칩니다. 실제 이름을 지정하세요.")
        selected = select(candidates, selector)
    elif records and all(record and record.reference.kind != ReferenceKind.ROOM and not obj.destination
                         for obj, record in zip(candidates, records)):
        from world.actions.resolver import select_records
        from world.actions.schema import DefaultTargetPolicy, RoleDefinition

        policies = {getattr(obj, "selection_default_policy", DefaultTargetPolicy.REQUIRE_UNIQUE)
                    for obj in candidates}
        if len(policies) != 1:
            raise RuleError("대상들의 기본 선택 규칙이 다릅니다. 이름과 번호를 지정하세요.")
        kinds = tuple(sorted({reference.kind for reference in by_reference}))
        by_number = ({record.reference: record for record in numbered_records(records)}
                     if numbered is None else numbered)
        references = select_records(
            RoleDefinition("provider", kinds, DefaultTargetPolicy(next(iter(policies))), allow_all=True),
            [by_number.get(record.reference, record) for record in records],
            selector,
        )
        if not set(references) <= by_number.keys():
            raise RuleError("지금 선택할 수 없는 대상입니다.")
        selected = [by_reference[ref] for ref in references]
    else:
        selected = select(candidates, selector)
    if supports and any(not supports(obj) for obj in selected):
        raise RuleError(f"지정한 대상은 '{action}' 행동을 지원하지 않습니다.")
    return selected


def labels(objects, name_values=lambda obj: obj.key):
    """B-1 실물은 저장 번호만 쓴다. 번호가 누락된 실물의 값은 None이다."""
    from world.actions.schema import ReferenceKind
    from world.selection_numbers.api import descriptor, label, number_for

    pool = ordered(objects)
    result = {}
    for obj in pool:
        name = name_values(obj)
        record = descriptor(obj)
        if record and record.reference.kind != ReferenceKind.ROOM:
            from dataclasses import replace

            number = number_for(record.reference)
            result[obj.id] = None if number is None else label(replace(record, number=number))
            continue
        peers = [other for other in pool if normalized(name_values(other)) == normalized(name)]
        result[obj.id] = f"{name} {peers.index(obj) + 1}" if len(peers) > 1 else name
    return result
