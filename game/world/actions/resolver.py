"""단일 Role 선택 규칙. 번호를 후보 인덱스로 바꾸거나 실패 대상을 대체하지 않는다."""

import re
from dataclasses import dataclass

from world.actions.registry import RegistryError, validate_argument
from world.actions.schema import DefaultTargetPolicy, ReferenceKind, TargetReference, TargetScope
from world.rules import RuleError
from world.targets import Mode, normalized, parse_selector


@dataclass(frozen=True)
class ActionInvocation:
    action_id: str
    variant_id: str
    roles: tuple[tuple[str, tuple[TargetReference, ...]], ...]
    arguments: tuple[tuple[str, object], ...] = ()
    origin: str = "text"
    confirmation_token: str | None = None
    request_id: str | None = None


def role_records(caller, role, bindings=None):
    from world.selection_numbers.api import current_scopes, records_for, resolve_reference

    if role.scope == TargetScope.CURRENT:
        kind = None if {ReferenceKind.LOOT, ReferenceKind.CURRENCY}.intersection(role.kinds) else ReferenceKind.ITEM
        scopes = current_scopes(caller, kind)
    else:
        from typeclasses.interactables import Container
        from world.item_entities.models import ItemEntity
        from world.observation import can_perceive, context_for

        scopes = set()
        for reference in (bindings or {}).get(role.scope_from, ()):
            entity = resolve_reference(reference)
            if role.scope == TargetScope.STORAGE:
                if (not isinstance(entity, Container) or entity.location != caller.location
                        or not can_perceive(entity, context_for(caller)) or not entity.access(caller, "call")):
                    continue
                scopes.add(f"personal_storage:{caller.pk}" if entity.personal else f"shared_storage:{entity.pk}")
            elif isinstance(entity, ItemEntity):
                root = entity.root()
                if root.location_kind in ("inventory", "equipment") and root.owner_object_id == caller.pk:
                    scopes.add(f"inside:{entity.pk}")
    return tuple(record for record in records_for(caller, scope_ids=scopes) if record.reference.kind in role.kinds)


def select_role(caller, role, query=None, *, bindings=None):
    records = role_records(caller, role) if bindings is None else role_records(caller, role, bindings)
    if query is None or not query.strip():
        if role.required:
            raise RuleError("대상 이름을 입력하세요.")
        matches, selector = list(records), None
    else:
        # 실제 정식 이름은 별칭보다 먼저, 숫자 접미를 분해하기 전 확인한다.
        exact = [record for record in records if normalized(record.name) == normalized(query)]
        if exact:
            if len(exact) > 1 and re.search(r"\d+$", query.strip()):
                raise RuleError("숫자로 끝나는 실제 이름이 여러 대상과 일치합니다. 다른 고유 이름을 지정하세요.")
            matches, selector = exact, None
        else:
            known = [name for record in records for name in (record.name, *record.aliases)]
            selector = parse_selector(query, known)
            matches = [record for record in records if normalized(selector.name) in
                       {normalized(name) for name in (record.name, *record.aliases)}]
            if len({record.group_id for record in matches}) > 1:
                raise RuleError("서로 다른 선택 그룹의 별칭이 겹칩니다. 실제 이름을 지정하세요.")
            if selector.mode == Mode.INDEX:
                unique_match = len(matches) == 1
                matches = [record for record in matches if record.number == selector.index or
                           (selector.index == 1 and unique_match and selector.name in record.unique_names)]
    if not matches:
        raise RuleError("지금 선택할 수 없는 대상입니다.")
    if selector and selector.mode == Mode.ALL and not (role.allow_all or role.default == DefaultTargetPolicy.ALL):
        raise RuleError("이 행동은 전체 대상 선택을 지원하지 않습니다.")
    if selector and selector.mode == Mode.ALL or role.default == DefaultTargetPolicy.ALL:
        return tuple(record.reference for record in matches)
    if role.default == DefaultTargetPolicy.FIRST_LEGACY_ORDER:
        from world.selection_numbers.api import resolve_reference

        def legacy_order(record):
            entity = resolve_reference(record.reference)
            return getattr(entity, "sequence", getattr(entity, "pk", 0))

        return (min(matches, key=legacy_order).reference,)
    if len(matches) != 1:
        raise RuleError("대상을 이름과 번호로 명확하게 지정하세요.")
    return (matches[0].reference,)


def argument_values(action, values, *, text=False):
    declarations = {argument.name: argument for argument in action.arguments}
    if set(values) - declarations.keys():
        raise RuleError("행동 인자를 확인하세요.")
    output = []
    for argument in action.arguments:
        value = values.get(argument.name, argument.default)
        if value is None:
            if argument.required:
                raise RuleError("행동 인자가 부족합니다.")
            continue
        if text and argument.kind is int and type(value) is str and value.isdecimal():
            value = int(value)
        try:
            validate_argument(argument, value)
        except (RegistryError, TypeError, ValueError):
            raise RuleError("행동 인자의 형식이나 수량을 확인하세요.") from None
        output.append((argument.name, value))
    return tuple(output)


def provider_definition(reference):
    from world.content import ITEMS
    from world.selection_numbers.api import resolve_reference

    entity = resolve_reference(reference)
    if entity is None:
        raise RuleError("원래 대상이 없어졌거나 위치가 바뀌었습니다.")
    if reference.kind in (ReferenceKind.ITEM, ReferenceKind.LOOT):
        return ITEMS[entity.definition_id].get("action_provider_id", "item." + entity.definition_id)
    if reference.kind == ReferenceKind.CURRENCY:
        return "currency.credits"
    if reference.kind == ReferenceKind.OBJECT:
        from world.selection_numbers.mixins import NumberedObjectMixin

        if not isinstance(entity, NumberedObjectMixin):
            raise RuleError("선언형 객체는 원자적 Provider 생명주기 타입이 필요합니다.")
    return entity.db.action_provider_id if hasattr(entity, "db") else None


def unshadowed(caller, index, pairs):
    """CmdSet·웹 표시·Gateway가 같은 현재 보호 이름과 입력 모드를 공유한다."""
    from django.conf import settings

    protected = set()
    for owner in (caller, caller.account):
        if not owner:
            continue
        for cmdset in owner.cmdset.cmdset_stack:
            if not cmdset:
                continue
            if cmdset.mergetype == "Replace":
                return ()
            for command in cmdset:
                if not getattr(command, "dynamic_action", False):
                    protected.update((command.key, *command.aliases))
    if caller.location:
        for obj in caller.location.contents:
            if obj.destination:
                protected.update((obj.key, *obj.aliases.all()))
    protected = {name.casefold() for key in protected for name in (key, key.lstrip(settings.CMD_IGNORE_PREFIXES))}
    blocked = set()
    for action_id in {binding.action_id for _, binding in pairs}:
        action = index.actions[action_id]
        verb = index.verbs[action.verb_id]
        names = {(key + (" " + suffix if suffix else "")).casefold()
                 for key in (verb.key, *verb.aliases) for suffix in ("", *(variant.suffix for variant in action.variants))}
        if protected.intersection(names):
            blocked.add(verb.id)
    return tuple((ref, binding) for ref, binding in pairs if index.actions[binding.action_id].verb_id not in blocked)


def provided(caller, index):
    if not index.bindings:
        return ()
    from world.actions.schema import RoleDefinition

    # 내부 ItemEntity는 대상으로 조회할 수 있어도 독립 Provider가 되지 않는다.
    role = RoleDefinition("provider", tuple(ReferenceKind), required=False)
    pairs = []
    for record in role_records(caller, role):
        try:
            definition = provider_definition(record.reference)
            if record.reference.kind == ReferenceKind.ITEM:
                from world.selection_numbers.api import resolve_reference

                item = resolve_reference(record.reference)
                if item.parent_item_id is not None or item.location_kind not in ("inventory", "equipment") or item.owner_object_id != caller.pk:
                    continue
            elif record.reference.kind not in (ReferenceKind.LOOT, ReferenceKind.CURRENCY):
                from world.selection_numbers.api import resolve_reference

                entity = resolve_reference(record.reference)
                if entity.db.action_available is False:
                    continue
        except (RuleError, KeyError):
            continue
        for binding in index.bindings_for_provider.get(definition, ()):
            action = index.actions[binding.action_id]
            provider = next((role for role in action.roles if role.name == "provider"), None)
            if action.public and provider and record.reference.kind in provider.kinds:
                pairs.append((record.reference, binding))
    return unshadowed(caller, index, pairs)


def dispatch_text(caller, index, verb_id, args, command_name):
    possible = []
    selections = {}
    for reference, binding in provided(caller, index):
        action = index.actions[binding.action_id]
        if action.verb_id != verb_id:
            continue
        for variant in action.variants:
            suffix = " " + variant.suffix if variant.suffix else ""
            verb = index.verbs[verb_id]
            if command_name.casefold() not in {(key + suffix).casefold() for key in (verb.key, *verb.aliases)}:
                continue
            match = re.fullmatch(variant.pattern, args)
            if not match:
                continue
            fields = match.groupdict()
            roles = {"provider": (reference,)}
            try:
                # 현재 Scope 역할을 먼저, 그 안정 참조를 사용하는 내부/보관 역할은 뒤에 선택한다.
                pending = [role for role in action.roles if role.name != "provider"]
                ordered = []
                known = {"provider"}
                while pending:
                    ready = next(role for role in pending if role.scope == TargetScope.CURRENT or role.scope_from in known)
                    pending.remove(ready)
                    ordered.append(ready)
                    known.add(ready.name)
                for role in ordered:
                    if role.name == "provider":
                        continue
                    query = fields.get(role.name)
                    if role.name in variant.all_roles and query:
                        query += " 모두"
                    context = () if role.scope == TargetScope.CURRENT else roles.get(role.scope_from, ())
                    key = (role, query, context)
                    if key not in selections:
                        selections[key] = select_role(caller, role, query, bindings=roles)
                    roles[role.name] = selections[key]
                if action.provider_from:
                    if reference not in roles[action.provider_from]:
                        continue
                    roles["provider"] = roles[action.provider_from]
                elif fields.get("provider"):
                    role = next(role for role in action.roles if role.name == "provider")
                    selected = select_role(caller, role, fields["provider"])
                    if reference not in selected:
                        continue
                    roles["provider"] = (reference,)
                else:
                    roles["provider"] = (reference,)
                arguments = argument_values(action, {arg.name: fields[arg.name] for arg in action.arguments
                                                    if fields.get(arg.name) is not None}, text=True)
            except RuleError:
                continue
            possible.append(ActionInvocation(action.id, variant.id, tuple(roles.items()), arguments))
    unique = tuple(dict.fromkeys(possible))
    if len(unique) != 1:
        raise RuleError("행동의 제공자와 대상을 명확하게 지정하세요." if unique else
                        "지금 선택할 수 없는 행동 또는 대상입니다.")
    return unique[0]
