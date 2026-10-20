"""선택 이후 단일 동기 실행 경계. 웹 label/번호/확정 flag는 권한이 아니다."""

import json
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from secrets import token_urlsafe
from time import time
from types import CoroutineType, MappingProxyType

from evennia.objects.models import ObjectDB
from world import rules
from world import text as ft
from world.actions.registry import RegistryError
from world.actions.resolver import ActionInvocation, argument_values, provided
from world.actions.schema import DefaultTargetPolicy, ReferenceKind, TargetReference
from world.actions.synchronous import validate_handler
from world.multiplayer import after_change, world_change


class ResultStatus(StrEnum):
    SUCCESS = "success"
    REFUSED = "refused"
    ERROR = "error"
    CONFIRMATION = "confirmation"


@dataclass(frozen=True)
class ActionResult:
    status: ResultStatus = ResultStatus.SUCCESS
    messages: tuple = ()
    changed: bool = False
    confirm_variant: str | None = None
    confirmation_token: str | None = None
    duplicate: bool = False

    def __post_init__(self):
        object.__setattr__(self, "messages", tuple(self.messages))


@dataclass(frozen=True)
class ExecutionContext:
    caller: object
    session: object
    invocation: ActionInvocation
    binding: object
    roles: object
    arguments: object
    config: object


class ResultAbort(Exception):
    def __init__(self, result):
        self.result = result


def require_session(caller, session):
    account = getattr(session, "account", None)
    puppet = session.get_puppet() if callable(getattr(session, "get_puppet", None)) else getattr(session, "puppet", None)
    if (not session or not getattr(session, "logged_in", False) or puppet is not caller
            or not account or not caller.account or account.pk != caller.account.pk
            or not any(current is session for current in caller.sessions.all())):
        raise rules.RuleError("현재 세션의 캐릭터 제어권을 확인할 수 없습니다.")


def require_input_mode(caller):
    """추가 입력 Replace CmdSet은 텍스트와 구조화 행동을 함께 보류한다."""
    for owner in (caller, caller.account):
        if not owner:
            continue
        for cmdset in owner.cmdset.cmdset_stack:
            if cmdset and cmdset.mergetype == "Replace":
                raise rules.RuleError("현재 추가 입력을 먼저 완료하세요.")


def synchronous(handler):
    """Evennia 6.1 func는 Deferred를 기다리지 않는다. 실행 전 확인 가능한 위험도 차단한다."""
    try:
        validate_handler(handler)
    except ValueError:
        raise rules.RuleError("이 행동의 동기 완료를 보장할 수 없습니다.") from None


def signature(invocation):
    roles = sorted((name, [(ref.kind, ref.identity, ref.scope_id) for ref in refs]) for name, refs in invocation.roles)
    return sha256(json.dumps([invocation.action_id, roles, invocation.arguments], sort_keys=True).encode()).hexdigest()


def _confirmation(caller, session, invocation, variant):
    tokens = dict(caller.ndb.action_confirmations or {})
    row = tokens.get(invocation.confirmation_token)
    if not row or row != (signature(invocation), variant.id, session.sessid, row[3]) or time() >= row[3]:
        raise rules.RuleError("확인 요청이 만료되었거나 원래 대상과 다릅니다. 다시 요청하세요.")


def from_web(payload, index):
    if (type(payload) is not dict or set(payload) - {"action_id", "variant", "roles", "arguments", "confirmation_token", "request_id"}
            or len(json.dumps(payload, ensure_ascii=False).encode()) > 262144):
        raise rules.RuleError("행동 요청의 형식이나 크기를 확인하세요.")
    action_id, variant_id = payload.get("action_id"), payload.get("variant")
    action = index.actions.get(action_id) if type(action_id) is str else None
    if not action or not action.public or type(variant_id) is not str or variant_id not in {v.id for v in action.variants}:
        raise rules.RuleError("지금 사용할 수 없는 행동입니다.")
    if len(json.dumps(payload, ensure_ascii=False).encode()) > action.max_payload_bytes:
        raise rules.RuleError("행동 요청의 크기를 확인하세요.")
    request_id = payload.get("request_id")
    token = payload.get("confirmation_token")
    if type(request_id) is not str or not 1 <= len(request_id) <= 64 or (token is not None and (type(token) is not str or len(token) > 100)):
        raise rules.RuleError("행동 요청 식별자를 확인하세요.")
    roles, arguments = payload.get("roles"), payload.get("arguments", {})
    if type(roles) is not dict or type(arguments) is not dict or len(roles) > 8:
        raise rules.RuleError("행동 역할을 확인하세요.")
    output = []
    try:
        for name, references in roles.items():
            if type(references) is not list or not 1 <= len(references) <= action.max_references:
                raise ValueError
            refs = []
            for ref in references:
                if type(ref) is not dict or set(ref) != {"kind", "identity", "scope_id"} or any(type(value) is not str or len(value) > 180 for value in ref.values()):
                    raise ValueError
                refs.append(TargetReference(ReferenceKind(ref["kind"]), ref["identity"], ref["scope_id"]))
            output.append((name, tuple(refs)))
    except (ValueError, TypeError, KeyError):
        raise rules.RuleError("행동 대상 참조를 확인하세요.") from None
    return ActionInvocation(action.id, variant_id, tuple(output), argument_values(action, arguments), "web", token, request_id)


def _roles(caller, action, invocation):
    from world.actions.resolver import role_records
    from world.selection_numbers.api import resolve_reference

    declarations = {role.name: role for role in action.roles}
    bindings = dict(invocation.roles)
    if len(bindings) != len(invocation.roles) or set(bindings) - declarations.keys():
        raise rules.RuleError("행동 역할이 일치하지 않습니다.")
    entities = {}
    for name, role in declarations.items():
        refs = bindings.get(name, ())
        if (role.required and not refs) or (not role.allow_all and role.default != DefaultTargetPolicy.ALL and len(refs) > 1) or len(refs) != len(set(refs)):
            raise rules.RuleError("행동 대상 수를 확인하세요.")
        current = {record.reference for record in role_records(caller, role, bindings)}
        if any(ref.kind not in role.kinds or ref not in current for ref in refs):
            if (action.id == "loot.take" and name == "subject"
                    and all(ref.kind in role.kinds for ref in refs)):
                from world.actions.loot_errors import LootUnavailable

                raise LootUnavailable()
            raise rules.RuleError("원래 대상이 없어졌거나 위치·권한이 바뀌었습니다.")
        entities[name] = tuple(resolve_reference(ref) for ref in refs)
    if action.provider_from and bindings.get("provider") != bindings.get(action.provider_from):
        raise rules.RuleError("행동 제공자와 대상이 일치하지 않습니다.")
    return entities


def _lock_roles(caller, invocation):
    from world.item_entities import api
    from world.item_entities.models import ItemEntity
    from world.loot_entities.models import CurrencyLoot
    from world.selection_numbers.api import resolve_reference

    identities, items, sources = {caller.pk}, set(), {}
    for _, refs in invocation.roles:
        for ref in refs:
            entity = resolve_reference(ref)
            if entity is None:
                raise rules.RuleError("원래 대상이 없어졌거나 위치가 바뀌었습니다.")
            if isinstance(entity, ObjectDB):
                identities.add(entity.pk)
            elif isinstance(entity, ItemEntity):
                current = entity
                while current:
                    items.add(current.pk)
                    if current.owner_object_id:
                        identities.add(current.owner_object_id)
                    current = current.parent_item
                if ref.kind == ReferenceKind.LOOT:
                    sources[entity.owner_object_id] = entity.owner_object
            elif isinstance(entity, CurrencyLoot):
                identities.add(entity.owner_object_id)
                sources[entity.owner_object_id] = entity.owner_object
    # Loot의 item/claim/currency/share lock은 기존 도메인 API가 같은 총순서로 확보한다.
    if sources:
        from world.loot_service import lock_sources

        lock_sources(list(sources.values()), caller=caller, extra_owners=identities)
    else:
        list(ObjectDB.objects.select_for_update().filter(pk__in=sorted(identities)).order_by("pk"))
        if items:
            api.lock_items(items)


def execute(caller, session, invocation, index):
    """모든 경로가 같은 검증·transaction·Service를 통과한다. 출력은 호출 어댑터가 한 번만 한다."""
    try:
        require_session(caller, session)
        require_input_mode(caller)
        action = index.actions.get(invocation.action_id)
        if not action or not action.public or invocation.origin not in ("text", "web"):
            raise rules.RuleError("지금 사용할 수 없는 행동입니다.")
        variant = next((v for v in action.variants if v.id == invocation.variant_id), None)
        if variant is None:
            raise rules.RuleError("행동 문법을 확인하세요.")
        if variant.confirmation_required and invocation.origin == "web":
            _confirmation(caller, session, invocation, variant)
        services = {index.services[binding.service_id] for binding in index.bindings.values()
                    if binding.action_id == action.id}
        lockers = {service.locker for service in services}
        preparations = {service.prepare for service in services}
        if len(lockers) != 1 or len(preparations) != 1:
            raise rules.RuleError("행동 잠금 계약을 확정할 수 없습니다.")
        prepare = next(iter(preparations))
        if prepare is not None:
            synchronous(prepare)
            prepare(caller, invocation)
        with world_change():
            # Lifecycle 확정 후 owner→item→claim→currency→share를 한 번에 잠근다.
            locker = next(iter(lockers))
            if locker is None:
                _lock_roles(caller, invocation)
            else:
                synchronous(locker)
                locker(caller, invocation)
            require_session(caller, session)
            entities = _roles(caller, action, invocation)
            provider_refs = dict(invocation.roles).get("provider", ())
            offered = [(ref, binding) for ref, binding in provided(caller, index)
                       if binding.action_id == action.id and ref in provider_refs]
            if {ref for ref, _ in offered} != set(provider_refs):
                raise rules.RuleError("행동 제공자를 확정할 수 없습니다.")
            candidates = tuple(dict.fromkeys(binding for _, binding in offered))
            if len(candidates) != 1:
                raise rules.RuleError("행동 제공자를 확정할 수 없습니다.")
            binding = candidates[0]
            arguments = argument_values(action, dict(invocation.arguments))
            service = index.services[binding.service_id]
            config = {arg.name: arg.default for arg in service.config_schema if arg.default is not None}
            config.update(binding.config)
            if config.get("peaceful"):
                rules.require_peace(caller.profile_snapshot())
            if any(hasattr(provider, "access") and not provider.access(caller, config.get("access", "call"))
                   for provider in entities["provider"]):
                raise rules.RuleError("이 행동을 실행할 권한이 없습니다.")
            quantity = dict(arguments).get("quantity")
            for name, values in entities.items():
                for entity in values:
                    if any(ref.kind in (ReferenceKind.LOOT, ReferenceKind.CURRENCY) for ref in dict(invocation.roles).get(name, ())):
                        from time import time as now

                        from typeclasses.loot import can_take_entry
                        from world.loot_service import loot_snapshot

                        entries = loot_snapshot(entity.owner_object).entries
                        match = next((entry for entry in entries if str(entry.item_id if hasattr(entity, "definition_id") else entry.currency_id) == str(entity.pk)), None)
                        if match is None or not can_take_entry(match.as_entry(), caller, now()):
                            if action.id == "loot.take":
                                from world.actions.loot_errors import LootUnavailable

                                raise LootUnavailable()
                            raise rules.RuleError("원래 전리품을 회수할 권한이 없습니다.")
                    if hasattr(entity, "quantity") and quantity is not None and quantity > entity.quantity:
                        raise rules.RuleError("원래 대상의 수량이 부족합니다.")
            synchronous(service.handler)
            result = service.handler(ExecutionContext(caller, session, invocation, binding,
                                                      MappingProxyType(entities), MappingProxyType(dict(arguments)),
                                                      MappingProxyType(config)))
            if isinstance(result, CoroutineType):
                result.close()
            if not isinstance(result, ActionResult):
                raise rules.RuleError("행동의 동기 완료 결과를 확인할 수 없습니다.")
            if result.status != ResultStatus.SUCCESS:
                raise ResultAbort(result)
            if result.changed:
                from typeclasses.explorers import Explorer

                after_change(lambda: [player.push_state() for player in Explorer.objects.all() if player.sessions.count()])
        if variant.confirmation_required and invocation.confirmation_token:
            tokens = dict(caller.ndb.action_confirmations or {})
            tokens.pop(invocation.confirmation_token, None)
            caller.ndb.action_confirmations = tokens
        return result
    except ResultAbort as abort:
        result = abort.result
        if result.status == ResultStatus.CONFIRMATION:
            target = next((v for v in action.variants if v.id == result.confirm_variant and v.confirmation_required), None)
            if target is None:
                return ActionResult(ResultStatus.ERROR, ("행동 완료 설정을 확인할 수 없습니다.",))
            token = token_urlsafe(24)
            tokens = {key: row for key, row in (caller.ndb.action_confirmations or {}).items() if time() < row[3]}
            tokens[token] = (signature(invocation), target.id, session.sessid, time() + 60)
            caller.ndb.action_confirmations = dict(list(tokens.items())[-32:])
            return ActionResult(result.status, result.messages, False, target.id, token)
        return result
    except (rules.RuleError, RegistryError) as error:
        return ActionResult(ResultStatus.REFUSED, (str(error),))
    except Exception:
        # 자유 예외/입력/대상 로그를 생성하지 않는다. 결과 오류 분류만 공개한다.
        return ActionResult(ResultStatus.ERROR, ("행동 처리 중 오류가 발생했습니다. 다시 확인하세요.",))


def emit(caller, session, invocation, result):
    for message in result.messages:
        caller.msg(ft.text(ft.token("error", message)) if result.status in (ResultStatus.REFUSED, ResultStatus.ERROR)
                   else message, session=session, kind="error" if result.status in (ResultStatus.REFUSED, ResultStatus.ERROR) else "event")
    if result.confirmation_token:
        from world.actions.presentation import reference_json

        caller.msg(session=session, pz_action_result=([{"action_id": invocation.action_id,
                  "action": {"action_id": invocation.action_id, "variant": result.confirm_variant,
                             "roles": {name: [reference_json(ref) for ref in refs] for name, refs in invocation.roles},
                             "arguments": dict(invocation.arguments), "confirmation_token": result.confirmation_token}}], {}))
