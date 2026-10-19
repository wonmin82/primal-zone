"""명시 Manifest를 검증하고 읽기 전용 Index로 컴파일한다."""

import re
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from types import MappingProxyType

from world.targets import normalized

from .regex_overlap import (
    ALL_PREFIX,
    Relation,
    compare_patterns,
    explicit_argument_extension,
    literal_role_prefix,
)
from .schema import DefaultTargetPolicy, ReferenceKind, TargetScope
from .synchronous import validate_handler


class RegistryError(ValueError):
    """콘텐츠 등록 계약 위반. 사용자 진단에는 직접 노출하지 않는다."""


@dataclass(frozen=True)
class CompiledActionIndex:
    packages: object
    verbs: object
    actions: object
    services: object
    bindings: object
    providers: object
    verbs_by_public_keys: object
    bindings_for_provider: object

def _require(condition, message):
    if not condition:
        raise RegistryError(message)


def _logical_id(value):
    _require(type(value) is str and bool(re.fullmatch(r"[a-z][a-z0-9_-]*(?:[.:][a-z0-9_-]+)+", value)),
             "논리 ID에는 명시적인 namespace가 필요합니다.")


def _local_names(values):
    names = [value.name for value in values]
    _require(all(type(name) is str and name.isidentifier() for name in names), "역할/인자 이름 오류")
    _require(len(names) == len(set(names)), "역할/인자 이름 중복")
    return set(names)


def _roles(roles):
    names = _local_names(roles)
    for role in roles:
        _require(bool(role.kinds) and all(isinstance(kind, ReferenceKind) for kind in role.kinds),
                 "역할 참조 타입 오류")
        _require(len(role.kinds) == len(set(role.kinds)), "역할 참조 타입 중복")
        _require(not role.location_kinds or set(role.kinds) == {ReferenceKind.ITEM}, "아이템 위치 제약 역할 타입 오류")
        _require(all(type(value) is str for value in role.location_kinds)
                 and set(role.location_kinds) <= {"inventory", "equipment", "inside", "personal_storage", "shared_storage"},
                 "아이템 위치 제약 오류")
        if ReferenceKind.INVENTORY in role.kinds:
            _require(role.kinds == (ReferenceKind.INVENTORY,) and role.name != "provider"
                     and role.scope == TargetScope.CURRENT, "Inventory는 현재 소지품 Source 전용 참조입니다.")
        _require(isinstance(role.default, DefaultTargetPolicy) and type(role.required) is bool
                 and type(role.allow_all) is bool,
                 "역할 기본 선택 정책 오류")
        _require(isinstance(role.scope, TargetScope) and type(role.scope_from) is str
                 and role.scope_from.isidentifier(), "역할 Scope 선언 오류")
        if role.scope == TargetScope.CARRIED_AND_INSIDE:
            _require(role.kinds == (ReferenceKind.ITEM,), "소지품과 내부 결합 Scope는 아이템 역할 전용입니다.")
        _require(all(type(identity) is str and identity for identity in role.definition_ids)
                 and len(set(role.definition_ids)) == len(role.definition_ids), "역할 콘텐츠 정의 제한 오류")
    return names


def validate_argument(definition, value):
    """Gateway에서도 재사용하는 엄격한 인자 타입·수량 경계."""
    _require(type(value) is definition.kind, "인자 타입 오류")
    if definition.minimum is not None:
        _require(value >= definition.minimum, "인자 최솟값 오류")
    if definition.maximum is not None:
        _require(value <= definition.maximum, "인자 최댓값 오류")
    _require(not definition.choices or value in definition.choices, "선언된 인자 선택지 오류")
    return value


def _arguments(arguments):
    names = _local_names(arguments)
    for arg in arguments:
        _require(arg.kind in (str, int, bool) and type(arg.required) is bool, "인자 선언 타입 오류")
        _require(all(bound is None or type(bound) is int for bound in (arg.minimum, arg.maximum)),
                 "인자 범위 타입 오류")
        _require(arg.kind is int or (arg.minimum is None and arg.maximum is None), "정수 외 범위 오류")
        _require(arg.minimum is None or arg.maximum is None or arg.minimum <= arg.maximum,
                 "인자 범위 역전")
        _require(all(type(value) is arg.kind for value in arg.choices), "인자 선택지 타입 오류")
        if arg.default is not None:
            validate_argument(arg, arg.default)
    return names


def _argument_contract(base_action, base_variant, extended_action, extended_variant):
    """언어 중첩과 별개로 보존하는 전체 Provider/필수 Argument 확장 계약."""
    if (base_action.arguments or len(extended_action.arguments) != 1
            or base_action.roles != extended_action.roles
            or tuple(role.name for role in base_action.roles) != ("provider",)
            or base_action.provider_from is not None or extended_action.provider_from is not None
            or base_variant.all_roles or extended_variant.all_roles):
        return False
    argument = extended_action.arguments[0]
    if not argument.required or argument.default is not None:
        return False
    return explicit_argument_extension(base_variant.pattern, extended_variant.pattern, argument.name)


def _normal_all_contract(action, normal, all_variant):
    if (normal.all_roles or len(all_variant.all_roles) != 1
            or normal.suffix.casefold() != all_variant.suffix.casefold()
            or normal.confirmation_required != all_variant.confirmation_required
            or normal.all_when != all_variant.all_when):
        return ()
    name, = all_variant.all_roles
    if name == "provider":
        return ()
    role = next((role for role in action.roles if role.name == name), None)
    if not role or not (role.allow_all or role.default == DefaultTargetPolicy.ALL):
        return ()
    if not literal_role_prefix(normal.pattern, all_variant.pattern, name):
        return ()
    return ((name, ALL_PREFIX),)


@lru_cache(maxsize=256)
def normal_all_guards(action, normal_variant):
    """등록의 동일 AST 증명을 Resolver가 재사용하는 예약 prefix 계약."""
    return tuple(dict.fromkeys(guard for variant in action.variants
                              for guard in _normal_all_contract(action, normal_variant, variant)))


def _check_pair(a, va, b, vb, provider):
    if a.verb_id != b.verb_id or va.suffix.casefold() != vb.suffix.casefold():
        return
    provider_a = next(role for role in a.roles if role.name == "provider")
    provider_b = next(role for role in b.roles if role.name == "provider")
    if not set(provider_a.kinds) & set(provider_b.kinds):
        return
    relation = compare_patterns(va.pattern, vb.pattern)
    if relation == Relation.DISJOINT:
        return
    if relation == Relation.OVERLAP:
        if a.id == b.id and (_normal_all_contract(a, va, vb) or _normal_all_contract(a, vb, va)):
            return
        if _argument_contract(a, va, b, vb) or _argument_contract(b, vb, a, va):
            return
    raise RegistryError(
        f"동일 Provider의 모호 Action Handler: Verb={a.verb_id}; "
        f"Provider={provider}; Action={a.id}/{b.id}; "
        f"Variant={va.id}/{vb.id}; reason={relation.value}. "
        "SyntaxVariant 접미어 또는 Provider 역할/필수 인자 계약을 명시적으로 구분하세요.")


def compile_manifest(manifest, protected_names=()):
    tables = {name: {} for name in ("packages", "verbs", "actions", "services", "bindings", "providers")}
    owners, all_ids = {}, set()

    def add(table, value, owner):
        _logical_id(value.id)
        _require(value.id not in all_ids, "중복 논리 ID")
        all_ids.add(value.id)
        tables[table][value.id] = value
        owners[value.id] = owner

    for package in manifest.packages:
        add("packages", package, package.id)
        for table in ("verbs", "actions", "services", "bindings", "providers"):
            for value in getattr(package, table):
                add(table, value, package.id)

    reachable = {}
    visiting = set()

    def dependencies(package_id):
        _require(package_id in tables["packages"], "미존재 패키지 의존성")
        _require(package_id not in visiting, "패키지 의존성 순환")
        if package_id not in reachable:
            visiting.add(package_id)
            result = {package_id}
            for dependency in tables["packages"][package_id].dependencies:
                result.update(dependencies(dependency))
            visiting.remove(package_id)
            reachable[package_id] = result
        return reachable[package_id]

    for package_id in tables["packages"]:
        dependencies(package_id)

    def reference(owner_id, table, target_id):
        _require(target_id in tables[table], "미존재 등록 참조")
        _require(owners[target_id] in reachable[owners[owner_id]], "선언되지 않은 패키지 의존성")
        return tables[table][target_id]

    public_keys = {}
    protected = {name.casefold() for name in protected_names}
    for verb in tables["verbs"].values():
        _require(all(type(value) is str and value for value in
                     (verb.unavailable_message, verb.invalid_message, verb.ambiguous_message)), "공개 진단 선언 오류")
        for key in (verb.key, *verb.aliases):
            _require(type(key) is str and bool(key) and key == key.strip(), "공개 동사 키 오류")
            key = key.casefold()
            _require(key not in protected, "엔진/Exit/고정 전역 명령 이름 침범")
            _require(key not in public_keys or public_keys[key] == verb.id, "다른 정규 동사 별칭 충돌")
            public_keys[key] = verb.id

    for action in tables["actions"].values():
        reference(action.id, "verbs", action.verb_id)
        role_names = _roles(action.roles)
        _require("provider" in role_names, "Action Provider 역할 누락")
        roles = {role.name: role for role in action.roles}
        for role in action.roles:
            if role.scope == TargetScope.CURRENT:
                continue
            _require(role.scope_from in role_names and role.scope_from != role.name,
                     "역할 Scope 출처가 다른 기존 역할을 참조해야 합니다.")
            visited, current = {role.name}, role
            while current.scope != TargetScope.CURRENT:
                _require(current.scope_from in roles and current.scope_from not in visited,
                         "역할 Scope 출처 순환/누락")
                visited.add(current.scope_from)
                current = roles[current.scope_from]
        argument_names = _arguments(action.arguments)
        _require(not role_names & argument_names, "역할/인자 capture 중복")
        _require(action.provider_from is None or action.provider_from in role_names, "미존재 Provider 역할")
        _require(type(action.public) is bool and bool(action.variants), "Action 공개/문법 선언 오류")
        _require(type(action.max_references) is int and 1 <= action.max_references <= 4096
                 and type(action.max_payload_bytes) is int and 8192 <= action.max_payload_bytes <= 262144,
                 "행동 요청 크기 선언 오류")
        if action.text_resolver is not None:
            try:
                validate_handler(action.text_resolver)
            except ValueError as error:
                raise RegistryError(str(error)) from error
        variant_ids = set()
        for variant in action.variants:
            _require(type(variant.pattern) is str, "문법 정규식은 문자열이어야 합니다.")
            _require(type(variant.id) is str and bool(variant.id) and variant.id not in variant_ids,
                     "문법 Variant ID 오류/중복")
            variant_ids.add(variant.id)
            _require(type(variant.suffix) is str and type(variant.confirmation_required) is bool,
                     "문법 Variant 확인 타입 오류")
            _require(type(variant.show_control) is bool, "문법 Variant 화면 표시 타입 오류")
            _require(variant.suffix == variant.suffix.strip(), "Variant 접미 공백 오류")
            _require(not variant.confirmation_required or bool(variant.suffix), "확정 Variant 접미 누락")
            _require(set(variant.all_roles) <= role_names, "전체 선택 Variant 역할 오류")
            _require(all(role.allow_all or role.default == DefaultTargetPolicy.ALL for role in action.roles
                         if role.name in variant.all_roles), "전체 선택 미지원 역할")
            for condition in variant.all_when:
                _require(len(condition) == 3, "조건부 전체 선택 선언 오류")
                role_name, argument_name, expected = condition
                _require(role_name in roles and argument_name in argument_names, "조건부 전체 선택 역할/인자 누락")
                _require(roles[role_name].allow_all, "조건부 전체 선택 미지원 역할")
                argument = next(arg for arg in action.arguments if arg.name == argument_name)
                validate_argument(argument, expected)
            try:
                pattern = re.compile(variant.pattern)
            except (re.error, TypeError) as error:
                raise RegistryError("문법 정규식 오류") from error
            _require(pattern.groups == len(pattern.groupindex), "이름 없는 문법 capture 금지")
            _require(set(pattern.groupindex) <= role_names | argument_names, "미존재 문법 capture")

    # 실제 CmdSet에 추가할 다단어 Variant 키도 같은 공개 이름 계약으로 검사한다.
    expanded_keys = dict(public_keys)
    for action in tables["actions"].values():
        verb = tables["verbs"][action.verb_id]
        for variant in action.variants:
            for key in (verb.key, *verb.aliases):
                key = (key + (" " + variant.suffix if variant.suffix else "")).casefold()
                _require(key not in protected, "Variant 엔진/Exit/고정 전역 이름 침범")
                _require(key not in expanded_keys or expanded_keys[key] == verb.id,
                         "다른 정규 동사와 Variant 공개 키 충돌")
                expanded_keys[key] = verb.id

    for service in tables["services"].values():
        _require(callable(service.handler), "Service Handler 누락")
        try:
            validate_handler(service.handler)
            if service.presenter is not None:
                validate_handler(service.presenter)
            if service.locker is not None:
                validate_handler(service.locker)
            if service.prepare is not None:
                validate_handler(service.prepare)
        except ValueError as error:
            raise RegistryError(str(error)) from error
        _roles(service.role_kinds)
        _arguments(service.config_schema)

    provider_bindings = {}
    for binding in tables["bindings"].values():
        _logical_id(binding.provider_definition)
        if tables["providers"]:
            reference(binding.id, "providers", binding.provider_definition)
        action = reference(binding.id, "actions", binding.action_id)
        service = reference(binding.id, "services", binding.service_id)
        roles = {role.name: role for role in action.roles}
        for expected in service.role_kinds:
            _require(expected.name in roles, "Service 미존재 역할")
            _require(set(roles[expected.name].kinds) <= set(expected.kinds), "Service 역할 타입 불일치")
            _require(not expected.required or roles[expected.name].required, "Service 필수 역할 불일치")
            if expected.scope != TargetScope.CURRENT:
                actual = roles[expected.name]
                _require((actual.scope, actual.scope_from) == (expected.scope, expected.scope_from),
                         "Service 역할 Scope 불일치")
        try:
            config = dict(binding.config)
        except (TypeError, ValueError) as error:
            raise RegistryError("Binding 설정 형식 오류") from error
        _require(len(config) == len(binding.config), "Binding 설정 키 중복")
        schema = {arg.name: arg for arg in service.config_schema}
        _require(set(config) <= set(schema), "미선언 Service 설정")
        for name, arg in schema.items():
            _require(name in config or not arg.required or arg.default is not None, "필수 Service 설정 누락")
            if name in config:
                validate_argument(arg, config[name])
        provider_bindings.setdefault(binding.provider_definition, []).append(binding)

    for action in tables["actions"].values():
        providers = sorted({binding.provider_definition for binding in tables["bindings"].values()
                            if binding.action_id == action.id})
        for va, vb in combinations(action.variants, 2):
            _check_pair(action, va, action, vb, ",".join(providers) or "<unbound>")

    for bindings in provider_bindings.values():
        for left, right in combinations(bindings, 2):
            a, b = tables["actions"][left.action_id], tables["actions"][right.action_id]
            for va in a.variants:
                for vb in b.variants:
                    _check_pair(a, va, b, vb, left.provider_definition)

    scope_names = {}
    for provider in tables["providers"].values():
        _logical_id(provider.group_id)
        _require(type(provider.scope_id) is str and bool(provider.scope_id) and bool(provider.name), "Provider Scope/이름 오류")
        key = (provider.scope_id, normalized(provider.name))
        _require(key not in scope_names or scope_names[key] == provider.group_id, "동일 Scope의 동명 그룹 충돌")
        scope_names[key] = provider.group_id
        _require(all(type(name) is str and name == provider.name for name in provider.unique_names),
                 "고유 호환 이름은 정식 선택 이름만 허용")

    return CompiledActionIndex(**{name: MappingProxyType(table) for name, table in tables.items()},
                               verbs_by_public_keys=MappingProxyType(public_keys),
                               bindings_for_provider=MappingProxyType({key: tuple(value) for key, value in provider_bindings.items()}))
