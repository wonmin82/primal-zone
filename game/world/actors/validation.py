"""Actor 구성은 검증하되 Action·Service를 다시 등록하거나 실행하지 않는다."""

import re
from collections.abc import Mapping
from itertools import combinations

from world.actions.registry import RegistryError, _arguments, _check_pair, validate_argument
from world.actions.schema import ArgumentDefinition

from .schema import (
    ActorDefinition,
    ActorPresentation,
    ActorSpawn,
    CapabilityDescriptor,
    Classification,
)


class ActorDefinitionError(ValueError):
    """불완전하거나 모호한 정적 Actor 구성."""


def require(condition, message):
    if not condition:
        raise ActorDefinitionError(message)


def _identity(value):
    return type(value) is str and bool(re.fullmatch(r"[a-z][a-z0-9_.:-]*", value))


def _table(values, expected):
    entries = tuple(values.values()) if isinstance(values, Mapping) else tuple(values)
    require(all(isinstance(value, expected) and _identity(value.id) for value in entries), "콘텐츠 ID/자료형 오류")
    require(len({value.id for value in entries}) == len(entries), "콘텐츠 ID 중복")
    if isinstance(values, Mapping):
        require(all(key == value.id for key, value in values.items()), "콘텐츠 키와 ID 불일치")
    return {value.id: value for value in entries}


def _presentation(value):
    require(isinstance(value, ActorPresentation), "Presentation 누락")
    require(all(type(item) is str and item.strip() for item in (
        value.description, value.presence, value.semantic_role, value.distant_presence, value.unit)),
        "Presentation 문자열 오류")
    require(value.detectability in ("subtle", "normal", "conspicuous")
            and type(value.distant_visible) is bool, "Presentation 가시성 오류")


def validate_definitions(definitions, capabilities, spawns=(), *, index=None, room_ids=None):
    """완전한 구성 집합을 검증한다. 실행 가능성은 현재 Gateway/도메인에서 재검증한다."""
    actors = _table(definitions, ActorDefinition)
    descriptors = _table(capabilities, CapabilityDescriptor)
    placements = _table(spawns, ActorSpawn)
    for descriptor in descriptors.values():
        for field in (descriptor.required_profiles, descriptor.binding_ids, descriptor.conflicts,
                      descriptor.active_states):
            require(len(set(field)) == len(field) and all(_identity(value) for value in field),
                    "Capability 참조 중복/형식 오류")
        schemas = dict(descriptor.profile_schemas)
        require(len(schemas) == len(descriptor.profile_schemas), "Profile Schema 중복")
        require(set(descriptor.required_profiles) <= schemas.keys(), "필수 Profile Schema 누락")
        require(set(descriptor.conflicts) <= descriptors.keys(), "미존재 충돌 Capability")
        for name, schema in schemas.items():
            require(_identity(name) and all(isinstance(arg, ArgumentDefinition) for arg in schema),
                    "Profile Schema 형식 오류")
            try:
                _arguments(schema)
            except RegistryError as error:
                raise ActorDefinitionError(str(error)) from error
        if index is not None:
            require(set(descriptor.binding_ids) <= index.bindings.keys(), "미존재 ActionBinding 참조")
    scope_names = {}
    for actor in actors.values():
        require(type(actor.name) is str and bool(actor.name.strip()), "Actor 이름 누락")
        require(isinstance(actor.classification, Classification), "Actor Classification 오류")
        require(type(actor.level) is int and actor.level >= 1, "Actor Level은 1 이상의 정수여야 합니다.")
        require(all(type(alias) is str and alias.strip() for alias in actor.aliases)
                and len(set(actor.aliases)) == len(actor.aliases), "Actor Alias 오류")
        require(all(value is None or type(value) is str and value.strip()
                    for value in (actor.subtype, actor.faction)), "Actor 분류 메타데이터 오류")
        _presentation(actor.presentation)
        require(_identity(actor.action_provider_id), "Actor Provider ID 오류")
        require(isinstance(actor.profiles, Mapping) and isinstance(actor.defaults, Mapping),
                "Actor Profile과 초기 상태는 Mapping이어야 합니다.")
        require(len(set(actor.capabilities)) == len(actor.capabilities)
                and set(actor.capabilities) <= descriptors.keys(), "Capability 중복/미존재 참조")
        require(not {"actor_id", "spawn_id", "definition_id", "action_provider_id", "selection_group_id"}
                .intersection(actor.defaults), "초기 상태가 영속 정체성을 덮어쓸 수 없습니다.")
        profiles = set()
        bindings = []
        for capability_id in actor.capabilities:
            capability = descriptors[capability_id]
            require(not set(capability.conflicts).intersection(actor.capabilities), "Capability 조합 충돌")
            require(set(capability.required_profiles) <= actor.profiles.keys(), "필수 Profile 누락")
            for profile_id, schema in capability.profile_schemas:
                profiles.add(profile_id)
                if profile_id not in actor.profiles:
                    continue
                values = actor.profiles[profile_id]
                require(isinstance(values, Mapping), "Profile은 명시적 설정 Mapping이어야 합니다.")
                require(set(values) <= {arg.name for arg in schema}, "미선언 Profile 설정")
                for arg in schema:
                    require(arg.name in values or not arg.required or arg.default is not None, "필수 Profile 설정 누락")
                    if arg.name in values:
                        try:
                            validate_argument(arg, values[arg.name])
                        except RegistryError as error:
                            raise ActorDefinitionError(str(error)) from error
            if index is not None:
                for binding_id in capability.binding_ids:
                    binding = index.bindings[binding_id]
                    require(binding.provider_definition == actor.action_provider_id, "Capability Provider 불일치")
                    declared = getattr(binding, "capability_id", None)
                    require(declared in (None, capability_id), "Binding Capability 참조 불일치")
                    bindings.append(binding)
        require(set(actor.profiles) <= profiles, "보유 Capability가 소유하지 않는 Profile")
        require(len({binding.id for binding in bindings}) == len(bindings), "Capability의 Binding 중복 제공")
        for left, right in combinations(bindings, 2):
            a, b = index.actions[left.action_id], index.actions[right.action_id]
            for va in a.variants:
                for vb in b.variants:
                    try:
                        _check_pair(a, va, b, vb, actor.id)
                    except RegistryError as error:
                        raise ActorDefinitionError(str(error)) from error
    for spawn in placements.values():
        require(spawn.actor_id in actors and _identity(spawn.room_id), "Spawn Actor/Room 참조 오류")
        if room_ids is not None:
            require(spawn.room_id in room_ids, "Spawn 미존재 Room")
        key = (spawn.room_id, actors[spawn.actor_id].name.casefold())
        require(key not in scope_names or scope_names[key] == spawn.actor_id, "같은 장소의 Actor 선택 이름 모호성")
        scope_names[key] = spawn.actor_id
    return actors
