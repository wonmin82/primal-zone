"""단일 Role 선택 규칙. 번호를 후보 인덱스로 바꾸거나 실패 대상을 대체하지 않는다."""

import re
from dataclasses import dataclass

from world.actions.registry import RegistryError, normal_all_guards, validate_argument
from world.actions.schema import DefaultTargetPolicy, ReferenceKind, TargetReference, TargetScope
from world.rules import RuleError
from world.targets import Mode, normalized, parse_selector


class TargetNotFound(RuleError):
    """유효한 문법이지만 현재 후보가 없는 선택."""


class TargetAmbiguous(RuleError):
    """실제 후보의 이름·번호 충돌. 문법 오류와 구분한다."""


@dataclass(frozen=True)
class ActionInvocation:
    action_id: str
    variant_id: str
    roles: tuple[tuple[str, tuple[TargetReference, ...]], ...]
    arguments: tuple[tuple[str, object], ...] = ()
    origin: str = "text"
    confirmation_token: str | None = None
    request_id: str | None = None


def role_records(caller, role, bindings=None, *, cache=None):
    from world.selection_numbers.api import (
        SelectionRecord,
        current_scopes,
        records_for,
        resolve_reference,
    )

    if role.kinds == (ReferenceKind.INVENTORY,):
        scope = f"inventory:{caller.pk}"
        return (SelectionRecord(TargetReference(ReferenceKind.INVENTORY, str(caller.pk), scope),
                                scope, "inventory:root", "소지품"),)

    if role.scope == TargetScope.CURRENT:
        kind = None if {ReferenceKind.LOOT, ReferenceKind.CURRENCY}.intersection(role.kinds) else ReferenceKind.ITEM
        scopes = current_scopes(caller, kind)
    else:
        from typeclasses.interactables import Container
        from world.item_entities.models import ItemEntity
        from world.observation import can_perceive, context_for

        scopes = (set(current_scopes(caller, ReferenceKind.ITEM))
                  if role.scope == TargetScope.CARRIED_AND_INSIDE else set())
        for reference in (bindings or {}).get(role.scope_from, ()):
            entity = resolve_reference(reference)
            if role.scope == TargetScope.STORAGE:
                if (not isinstance(entity, Container) or entity.location != caller.location
                        or not can_perceive(entity, context_for(caller))
                        or not entity.access(caller, "view") or not entity.access(caller, "call")):
                    continue
                scopes.add(f"personal_storage:{caller.pk}" if entity.personal else f"shared_storage:{entity.pk}")
            elif role.scope == TargetScope.SOURCE:
                from typeclasses.loot import Corpse, DroppedLoot

                if isinstance(entity, (Corpse, DroppedLoot)) and entity.location == caller.location:
                    scopes.add(f"corpse_loot:{entity.pk}" if isinstance(entity, Corpse)
                               else f"ground:{caller.location.pk}")
            elif isinstance(entity, ItemEntity):
                root = entity.root()
                if root.location_kind in ("inventory", "equipment") and root.owner_object_id == caller.pk:
                    scopes.add(f"inside:{entity.pk}")
    key = ("scope", frozenset(scopes))
    if cache is None:
        records = records_for(caller, scope_ids=scopes)
    else:
        if key not in cache:
            cache[key] = records_for(caller, scope_ids=scopes)
        records = cache[key]
    records = tuple(record for record in records if record.reference.kind in role.kinds)
    if role.scope == TargetScope.SOURCE:
        owners = {ref.identity for ref in (bindings or {}).get(role.scope_from, ())}
        records = tuple(record for record in records
                        if str(getattr(resolve_reference(record.reference), "owner_object_id", "")) in owners)
    if role.definition_ids or role.location_kinds:
        def entity(record):
            key = ("entity", record.reference)
            if cache is None:
                return resolve_reference(record.reference)
            if key not in cache:
                cache[key] = resolve_reference(record.reference)
            return cache[key]

        records = tuple(record for record in records
                        if (not role.definition_ids or getattr(entity(record), "definition_id", None) in role.definition_ids)
                        and (not role.location_kinds or getattr(entity(record), "location_kind", None) in role.location_kinds))
    return records


def select_role(caller, role, query=None, *, bindings=None, candidates=None, cache=None):
    records = role_records(caller, role, bindings, cache=cache)
    if candidates is not None:
        records = tuple(record for record in records if record.reference in candidates)
    if query is None or not query.strip():
        if role.required:
            raise RuleError("대상 이름을 입력하세요.")
        matches, selector = list(records), None
    else:
        # 실제 정식 이름은 별칭보다 먼저, 숫자 접미를 분해하기 전 확인한다.
        exact = [record for record in records if normalized(record.name) == normalized(query)]
        if exact:
            if len(exact) > 1 and re.search(r"\d+$", query.strip()):
                raise TargetAmbiguous("숫자로 끝나는 실제 이름이 여러 대상과 일치합니다. 다른 고유 이름을 지정하세요.")
            matches, selector = exact, None
        else:
            known = [name for record in records for name in (record.name, *record.aliases)]
            selector = parse_selector(query, known)
            matches = [record for record in records if normalized(selector.name) in
                       {normalized(name) for name in (record.name, *record.aliases)}]
            if len({record.group_id for record in matches}) > 1:
                raise TargetAmbiguous("서로 다른 선택 그룹의 별칭이 겹칩니다. 실제 이름을 지정하세요.")
            if selector.mode == Mode.INDEX:
                unique_match = len(matches) == 1
                matches = [record for record in matches if record.number == selector.index or
                           (selector.index == 1 and unique_match and selector.name in record.unique_names)]
                if len({record.scope_id for record in matches}) > 1:
                    raise TargetAmbiguous("서로 다른 보관 범위의 번호가 겹칩니다. 대상을 고유하게 지정하세요.")
    if not matches:
        if (query is None or not query.strip()) and not role.required:
            return ()
        raise TargetNotFound("지금 선택할 수 없는 대상입니다.")
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
        raise TargetAmbiguous("대상을 이름과 번호로 명확하게 지정하세요.")
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
        if text and argument.kind is int and type(value) is str and re.fullmatch(r"[+-]?[0-9]+", value):
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
    return (getattr(entity, "action_provider_definition", None) or entity.db.action_provider_id) if hasattr(entity, "db") else None


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
    verb = index.verbs[verb_id]
    selections = {}
    record_cache = {}  # 구문 선택 한 번에만 재사용한다. Gateway는 잠금 뒤 새로 검증한다.
    offers = provided(caller, index)
    custom = {index.actions[binding.action_id] for _, binding in offers
              if index.actions[binding.action_id].verb_id == verb_id
              and index.actions[binding.action_id].text_resolver is not None}
    custom_errors = []
    for action in custom:
        try:
            result = action.text_resolver(caller, index, action, args, command_name)
            if result is not None:
                possible.append(result)
        except RuleError as error:
            custom_errors.append(error)
    for reference, binding in offers:
        action = index.actions[binding.action_id]
        if action.verb_id != verb_id or action.text_resolver is not None:
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
            # 정적으로 검증한 normal/all 쌍의 예약 접두어는 별칭 조회보다 먼저 검사한다.
            # 선언 순서가 아니라 서로 배타적인 입력 계약이며 일반 Role 선택 순서는 유지한다.
            if any(fields.get(role) is not None and fields[role].startswith(prefix)
                   for role, prefix in normal_all_guards(action, variant)):
                continue
            roles = {"provider": (reference,)}
            try:
                arguments = argument_values(action, {arg.name: fields[arg.name] for arg in action.arguments
                                                    if fields.get(arg.name) is not None}, text=True)
                argument_map = dict(arguments)
                all_roles = set(variant.all_roles) | {name for name, argument, expected in variant.all_when
                                                     if argument_map.get(argument) == expected}
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
                    if role.name in all_roles and query:
                        query += " 모두"
                    context = () if role.scope == TargetScope.CURRENT else roles.get(role.scope_from, ())
                    key = (role, query, context)
                    if key not in selections:
                        selections[key] = select_role(caller, role, query, bindings=roles, cache=record_cache)
                    roles[role.name] = selections[key]
                if action.provider_from:
                    if reference not in roles[action.provider_from]:
                        continue
                    roles["provider"] = roles[action.provider_from]
                elif fields.get("provider"):
                    role = next(role for role in action.roles if role.name == "provider")
                    candidates = {ref for ref, offer in offers if offer.action_id == action.id}
                    selected = select_role(caller, role, fields["provider"], candidates=candidates, cache=record_cache)
                    if reference not in selected:
                        continue
                    roles["provider"] = (reference,)
                else:
                    roles["provider"] = (reference,)
            except RuleError:
                continue
            possible.append(ActionInvocation(action.id, variant.id, tuple(roles.items()), arguments))
    unique = tuple(dict.fromkeys(possible))
    if not unique and custom_errors:
        raise custom_errors[0]
    if len(unique) != 1:
        raise RuleError(verb.ambiguous_message if unique else verb.invalid_message)
    return unique[0]
