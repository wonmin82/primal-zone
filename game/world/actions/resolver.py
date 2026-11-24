"""단일 Role 선택 규칙. 번호를 후보 인덱스로 바꾸거나 실패 대상을 대체하지 않는다."""

import re
from dataclasses import dataclass

from world.actions.registry import RegistryError, normal_all_guards, validate_argument
from world.actions.schema import (
    DefaultTargetPolicy,
    GlobalSource,
    ReferenceKind,
    ScopeRoot,
    TargetReference,
    TargetScope,
)
from world.rules import RuleError
from world.targets import (
    MAX_SELECTION_LENGTH,
    Mode,
    normalized,
    parse_exact_selector,
    parse_selector,
    quoted_name_spans,
)

_TEXT_ITEMS = ("text_items",)


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


def cached_item_scopes(caller, scopes, cache, item_entities, *, check_visibility=True, references=None):
    """같은 표시 요청의 Item Scope를 검증하고 비어 있는 Scope도 기록한다."""
    from world.selection_numbers.api import records_for

    keys = {scope: ("item_scope", scope, check_visibility, references) for scope in sorted(scopes)}
    missing = {scope: [] for scope, key in keys.items() if key not in cache}
    if missing:
        for record in records_for(caller, scope_ids=missing, kinds=(ReferenceKind.ITEM,),
                                  check_visibility=check_visibility, references=references,
                                  item_entities=item_entities):
            missing[record.scope_id].append(record)
        for scope, records in missing.items():
            cache[keys[scope]] = tuple(records)
    return tuple([record for key in keys.values() for record in cache[key]])


def role_records(caller, role, bindings=None, *, cache=None, check_visibility=True, references=None, item_entities=None,
                 provider_entities=None, get_observation=None):
    from world.selection_numbers.api import (
        SelectionRecord,
        current_scopes,
        records_for,
        resolve_reference,
    )

    def resolve_entity(reference):
        entities = item_entities if reference.kind == ReferenceKind.ITEM else provider_entities
        if entities is None:
            return resolve_reference(reference)
        if reference not in entities:
            entities[reference] = resolve_reference(reference)
        return entities[reference]

    if role.kinds == (ReferenceKind.INVENTORY,):
        scope = f"inventory:{caller.pk}"
        return (SelectionRecord(TargetReference(ReferenceKind.INVENTORY, str(caller.pk), scope),
                                scope, "inventory:root", "소지품"),)

    references = None if references is None else frozenset(references)
    if role.scope == TargetScope.CURRENT:
        kind = None if {ReferenceKind.LOOT, ReferenceKind.CURRENCY}.intersection(role.kinds) else ReferenceKind.ITEM
        scopes = current_scopes(caller, kind)
        if role.scope_root == ScopeRoot.CURRENT_ROOM:
            scopes = {scope for scope in scopes if not scope.startswith("character:")}
        elif role.scope_root == ScopeRoot.ROLE:
            scopes = {ref.scope_id for ref in (bindings or {}).get(role.root_role, ())
                      if resolve_entity(ref) is not None}
        if role.include_carried_inside and references is not None:
            # Scope는 조회 범위 힌트다. records_for가 현재 실물과 소지 Root를 검사한다.
            scopes.update({ref.scope_id for ref in references
                           if ref.kind == ReferenceKind.ITEM and ref.scope_id.startswith("inside:")})
    else:
        from typeclasses.interactables import Container
        from world.item_entities.models import ItemEntity
        from world.observation import can_perceive, context_for

        scopes = (set(current_scopes(caller, ReferenceKind.ITEM))
                  if role.scope == TargetScope.CARRIED_AND_INSIDE else set())
        for reference in (bindings or {}).get(role.scope_from, ()):
            entity = resolve_entity(reference)
            if role.scope == TargetScope.STORAGE:
                if (not isinstance(entity, Container) or entity.location != caller.location
                        or not can_perceive(entity, get_observation() if get_observation else context_for(caller))
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
    key = ("scope", frozenset(scopes), frozenset(role.kinds), check_visibility, references,
           role.include_carried_inside)

    def load_records(scope_ids=scopes):
        if role.include_carried_inside and references is None:
            from world.item_entities.api import carried_items
            from world.selection_numbers.api import descriptor, numbered_records

            kinds = tuple(kind for kind in role.kinds if kind != ReferenceKind.ITEM)
            current = records_for(caller, scope_ids=scopes, kinds=kinds,
                                  check_visibility=check_visibility)
            items = numbered_records([descriptor(row) for row in carried_items(caller)])
            return (*current, *items)
        return records_for(caller, scope_ids=scope_ids, kinds=role.kinds, check_visibility=check_visibility,
                           references=references, require_carried_root=role.include_carried_inside,
                           item_entities=item_entities, provider_entities=provider_entities)

    if cache is not None and item_entities is not None and role.kinds == (ReferenceKind.ITEM,) and not role.include_carried_inside:
        # 여러 총기가 같은 소지 범위를 쓰더라도 각 총기의 Inside 후보는 구분한다.
        records = cached_item_scopes(caller, scopes, cache, item_entities,
                                     check_visibility=check_visibility, references=references)
    elif cache is None:
        records = load_records()
    else:
        if key not in cache:
            cache[key] = load_records()
        records = cache[key]
    records = tuple(record for record in records if record.reference.kind in role.kinds)
    if role.scope == TargetScope.SOURCE:
        owners = {ref.identity for ref in (bindings or {}).get(role.scope_from, ())}
        records = tuple(record for record in records
                        if str(getattr(resolve_entity(record.reference), "owner_object_id", "")) in owners)
    if role.definition_ids or role.location_kinds:
        def entity(record):
            key = ("entity", record.reference)
            if cache is None:
                return resolve_entity(record.reference)
            if key not in cache:
                cache[key] = resolve_entity(record.reference)
            return cache[key]

        records = tuple(record for record in records
                        if (not role.definition_ids or getattr(entity(record), "definition_id", None) in role.definition_ids)
                        and (not role.location_kinds or getattr(entity(record), "location_kind", None) in role.location_kinds))
    return records


def select_role(caller, role, query=None, *, bindings=None, candidates=None, cache=None):
    # 이 맵은 문자열 선택에만 쓰이며 표시 문맥이나 실행 Gateway로 넘기지 않는다.
    items = {} if cache is None else cache.setdefault(_TEXT_ITEMS, {})
    records = role_records(caller, role, bindings, cache=cache, item_entities=items)
    if candidates is not None:
        records = tuple(record for record in records if record.reference in candidates)
    return select_records(role, records, query, observed_items=items)


def record_selector(query, records, *, b1=True):
    primary = [record.name for record in records]
    aliases = [alias for record in records for alias in record.aliases]
    return parse_selector(query, (*primary, *aliases), b1=b1, literal_names=primary)


def matching_records(records, selector):
    records = tuple(records)
    if selector.exact:
        matches = [record for record in records
                   if record.name == selector.name and record.number == selector.index]
    else:
        name = normalized(selector.name)
        matches = [record for record in records if normalized(record.name) == name]
        if not matches or selector.mode == Mode.ALL:
            matches = [record for record in records if name in
                       {normalized(value) for value in (record.name, *record.aliases)}]
        elif selector.mode == Mode.DEFAULT and len(matches) > 1 and selector.name[-1:].isdecimal():
            raise TargetAmbiguous("숫자로 끝나는 실제 이름이 여러 대상과 일치합니다. 다른 고유 이름을 지정하세요.")
        if len({record.group_id for record in matches}) > 1:
            raise TargetAmbiguous("서로 다른 선택 그룹의 별칭이 겹칩니다. 실제 이름을 지정하세요.")
        if selector.mode == Mode.INDEX:
            matches = [record for record in matches if record.number == selector.index]
    if selector.mode == Mode.INDEX and len(matches) > 1:
        raise TargetAmbiguous("대상 번호가 겹칩니다. 대상을 고유하게 지정하세요.")
    return matches


def select_records(role, records, query, *, observed_items=None):
    """이미 관찰된 Role 후보에서 선택한다. 반환한 참조는 실행 Gateway에서 다시 검증한다."""
    empty = query is None or (isinstance(query, str) and not query.strip())
    if empty:
        if role.required:
            raise RuleError("대상 이름을 입력하세요.")
        matches, selector = list(records), None
    else:
        selector = record_selector(query, records, b1=any(
            kind not in (ReferenceKind.ROOM, ReferenceKind.INVENTORY) for kind in role.kinds
        ))
        matches = matching_records(records, selector)
    if not matches:
        if empty and not role.required:
            return ()
        raise TargetNotFound("지금 선택할 수 없는 대상입니다.")
    if selector and selector.mode == Mode.INDEX:
        return (matches[0].reference,)
    if selector and selector.mode == Mode.ALL and not (role.allow_all or role.default == DefaultTargetPolicy.ALL):
        raise RuleError("이 행동은 전체 대상 선택을 지원하지 않습니다.")
    if selector and selector.mode == Mode.ALL or role.default == DefaultTargetPolicy.ALL:
        return tuple(record.reference for record in matches)
    if role.default == DefaultTargetPolicy.FIRST_LEGACY_ORDER:
        from world.selection_numbers.api import resolve_references

        items = observed_items if observed_items is not None else {}
        resolved = resolve_references(record.reference for record in matches if record.reference not in items)

        def legacy_order(record):
            entity = items[record.reference] if record.reference in items else resolved.get(record.reference)
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


def provider_definition(reference, *, entity=None):
    from world.content import ITEMS
    from world.selection_numbers.api import resolve_reference

    entity = entity if entity is not None else resolve_reference(reference)
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
    offered_verbs = {index.actions[binding.action_id].verb_id for _, binding in pairs}
    for action in index.actions.values():
        if not action.public or action.verb_id not in offered_verbs:
            continue
        verb = index.verbs[action.verb_id]
        names = {(key + (" " + suffix if suffix else "")).casefold()
                 for key in (verb.key, *verb.aliases) for suffix in ("", *(variant.suffix for variant in action.variants))}
        if protected.intersection(names):
            blocked.add(verb.id)
    return tuple((ref, binding) for ref, binding in pairs if index.actions[binding.action_id].verb_id not in blocked)


def _root_records(caller, action, name):
    """제공 여부의 후보 존재만 확인한다. 실제 선택은 요청의 역할 Query로 별도 확정한다."""
    roles = {role.name: role for role in action.roles}
    bindings, visiting = {}, set()

    def candidates(role_name):
        if role_name in bindings:
            return bindings[role_name]
        if role_name not in roles or role_name in visiting:
            return ()
        visiting.add(role_name)
        role = roles[role_name]
        dependencies = []
        if role.scope != TargetScope.CURRENT:
            dependencies.append(role.scope_from)
        if role.scope_root == ScopeRoot.ROLE:
            dependencies.append(role.root_role)
        for dependency in dependencies:
            candidates(dependency)
        records = role_records(caller, role, bindings)
        bindings[role_name] = tuple(record.reference for record in records)
        visiting.remove(role_name)
        return bindings[role_name]

    return candidates(name)


def provided(caller, index, *, action_id=None, for_cmdset=False, item_entities=None, provider_entities=None,
             get_observation=None):
    def included(binding):
        action = index.actions[binding.action_id]
        return (action.public and (action_id is None or action.id == action_id)
                and (not for_cmdset or not index.verbs[action.verb_id].adapter_only))

    bindings = tuple(binding for binding in index.bindings.values() if included(binding))
    if not bindings:
        return ()
    from world.actions.schema import RoleDefinition
    from world.selection_numbers.api import resolve_reference, visible_entity

    # 내부 ItemEntity는 대상으로 조회할 수 있어도 독립 Provider가 되지 않는다.
    kinds = {kind for binding in bindings
             for action in (index.actions[binding.action_id],)
             for role in action.roles if role.name == "provider" for kind in role.kinds}
    pairs = []
    for binding in bindings:
        if not isinstance(binding.source, GlobalSource):
            continue
        action = index.actions[binding.action_id]
        if not caller.pk:
            continue
        if binding.source.root == ScopeRoot.CURRENT_ROOM and not caller.location:
            continue
        if binding.source.root == ScopeRoot.ROLE:
            if not _root_records(caller, action, binding.source.role):
                continue
        pairs.append((None, binding))
    role = RoleDefinition("provider", tuple(sorted(kinds)), required=False)
    records = role_records(caller, role, check_visibility=False, item_entities=item_entities,
                           provider_entities=provider_entities) if kinds else ()
    for record in records:
        reference = record.reference
        entities = item_entities if reference.kind == ReferenceKind.ITEM else provider_entities
        entity = entities.get(reference) if entities is not None else resolve_reference(reference)
        if entity is None:
            continue
        try:
            definition = provider_definition(reference, entity=entity)
        except (RuleError, KeyError):
            continue
        offers = tuple(binding for binding in index.bindings_for_provider.get(definition, ()) if included(binding))
        if not offers:
            continue
        if reference.kind == ReferenceKind.ITEM:
            if (entity.parent_item_id is not None or entity.location_kind not in ("inventory", "equipment")
                    or entity.owner_object_id != caller.pk):
                continue
        elif reference.kind not in (ReferenceKind.LOOT, ReferenceKind.CURRENCY) and entity.db.action_available is False:
            continue
        if not for_cmdset and not visible_entity(caller, entity, get_observation=get_observation):
            continue
        capabilities = getattr(entity, "capability_binding_ids", None)
        active_bindings = capabilities() if callable(capabilities) else None
        for binding in offers:
            action = index.actions[binding.action_id]
            provider = next((role for role in action.roles if role.name == "provider"), None)
            if active_bindings is not None and binding.id not in active_bindings:
                continue
            if binding.capability_id:
                active = getattr(entity, "capability_active", None)
                if not callable(active) or not active(binding.capability_id):
                    continue
            if provider and reference.kind in provider.kinds:
                pairs.append((reference, binding))
    return unshadowed(caller, index, pairs)


def _variant_fields(pattern, args, spans):
    """인용 안에서 분리된 capture를 버리고 원문 위치를 보존해 다시 맞춘다."""
    masked = args
    while match := re.fullmatch(pattern, masked):
        split = {(left, right) for left, right in spans
                 if any(left < boundary < right for position in match.regs[1:] for boundary in position)}
        if not split:
            return {key: args[left:right] if left >= 0 else None
                    for key in match.groupdict() for left, right in [match.span(key)]}
        updates = list(masked)
        for left, right in split:
            updates[left:right] = "\ue000" * (right - left)
        revised = "".join(updates)
        if revised == masked:
            break
        masked = revised
    return None


def dispatch_text(caller, index, verb_id, args, command_name):
    if len(args) > 4 * MAX_SELECTION_LENGTH:
        raise RuleError("행동 대상과 인자 입력이 너무 깁니다.")
    possible = []
    verb = index.verbs[verb_id]
    selections = {}
    items = {}
    record_cache = {_TEXT_ITEMS: items}  # 구문 선택 한 번에만 사용한다. Gateway는 잠금 뒤 다시 검증한다.
    spans = quoted_name_spans(args)
    offers = provided(caller, index, item_entities=items)
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
            fields = _variant_fields(variant.pattern, args, spans)
            if fields is None:
                continue
            # 정적으로 검증한 normal/all 쌍의 예약 접두어는 별칭 조회보다 먼저 검사한다.
            # 선언 순서가 아니라 서로 배타적인 입력 계약이며 일반 Role 선택 순서는 유지한다.
            if any(fields.get(role) is not None and fields[role].startswith(prefix)
                   for role, prefix in normal_all_guards(action, variant)):
                continue
            roles = {} if isinstance(binding.source, GlobalSource) else {"provider": (reference,)}
            try:
                arguments = argument_values(action, {arg.name: fields[arg.name] for arg in action.arguments
                                                    if fields.get(arg.name) is not None}, text=True)
                argument_map = dict(arguments)
                all_roles = set(variant.all_roles) | {name for name, argument, expected in variant.all_when
                                                     if argument_map.get(argument) == expected}
                # 현재 Scope 역할을 먼저, 그 안정 참조를 사용하는 내부/보관 역할은 뒤에 선택한다.
                pending = [role for role in action.roles if role.name != "provider"]
                ordered = []
                known = set(roles)
                while pending:
                    ready = next(role for role in pending
                                 if (role.scope == TargetScope.CURRENT or role.scope_from in known)
                                 and (role.scope_root != ScopeRoot.ROLE or role.root_role in known))
                    pending.remove(ready)
                    ordered.append(ready)
                    known.add(ready.name)
                for role in ordered:
                    if role.name == "provider":
                        continue
                    query = fields.get(role.name)
                    if role.name in all_roles and query:
                        if parse_exact_selector(query):
                            raise RuleError("정확한 번호와 '모두'를 함께 지정할 수 없습니다.")
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
                elif reference is not None:
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
