"""콘텐츠가 선언하는 순수·불변 Action 계약. DB나 게임 객체를 생성하지 않는다."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class ReferenceKind(StrEnum):
    OBJECT = "object"
    ROOM = "room"
    ENEMY = "enemy"
    DOOR = "door"
    ITEM = "item"
    CORPSE = "corpse"
    LOOT = "loot"
    CURRENCY = "currency"
    STORAGE = "storage"
    INVENTORY = "inventory"


class DefaultTargetPolicy(StrEnum):
    REQUIRE_UNIQUE = "require_unique"
    FIRST_LEGACY_ORDER = "first_legacy_order"
    ALL = "all"


class TargetScope(StrEnum):
    CURRENT = "current"
    STORAGE = "storage"
    SOURCE = "source"
    INSIDE = "inside"
    CARRIED_AND_INSIDE = "carried_and_inside"


def freeze(value):
    """콘텐츠 설정의 중첩 컨테이너도 외부 변경으로부터 분리한다."""
    if isinstance(value, dict):
        return tuple((key, freeze(item)) for key, item in value.items())
    if isinstance(value, (tuple, list)):
        return tuple(freeze(item) for item in value)
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise TypeError("콘텐츠 설정에는 불변 기본 자료형만 허용됩니다.")


@dataclass(frozen=True)
class TargetReference:
    kind: ReferenceKind
    identity: str
    scope_id: str

    def __post_init__(self):
        if not isinstance(self.kind, ReferenceKind):
            raise TypeError("참조 종류가 유효하지 않습니다.")
        if not all(type(value) is str and value for value in (self.identity, self.scope_id)):
            raise ValueError("참조에는 안정 ID와 Scope가 필요합니다.")


@dataclass(frozen=True)
class RoleDefinition:
    name: str
    kinds: tuple[ReferenceKind, ...]
    default: DefaultTargetPolicy = DefaultTargetPolicy.REQUIRE_UNIQUE
    required: bool = True
    allow_all: bool = False
    scope: TargetScope = TargetScope.CURRENT
    scope_from: str = "provider"
    definition_ids: tuple[str, ...] = ()
    location_kinds: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "kinds", tuple(self.kinds))
        object.__setattr__(self, "definition_ids", tuple(self.definition_ids))
        object.__setattr__(self, "location_kinds", tuple(self.location_kinds))


@dataclass(frozen=True)
class ArgumentDefinition:
    name: str
    kind: type = str
    required: bool = True
    default: object = None
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "default", freeze(self.default))
        object.__setattr__(self, "choices", tuple(freeze(value) for value in self.choices))


@dataclass(frozen=True)
class SyntaxVariant:
    id: str
    pattern: str
    suffix: str = ""
    confirmation_required: bool = False
    all_roles: tuple[str, ...] = ()
    show_control: bool = True
    all_when: tuple[tuple[str, str, object], ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "all_roles", tuple(self.all_roles))
        object.__setattr__(self, "all_when", tuple(tuple(entry) for entry in self.all_when))


@dataclass(frozen=True)
class VerbDefinition:
    id: str
    key: str
    aliases: tuple[str, ...] = ()
    summary: str = ""
    usage: str = ""
    category: str = ""
    help_sections: tuple[tuple[str, tuple[str, ...]], ...] = ()
    unavailable_message: str = "현재 이곳에서 사용할 수 없는 행동입니다. 대상과 도움말을 확인하세요."
    invalid_message: str = "지금 선택할 수 없는 행동 또는 대상입니다."
    ambiguous_message: str = "행동의 제공자와 대상을 명확하게 지정하세요."

    def __post_init__(self):
        object.__setattr__(self, "aliases", tuple(self.aliases))
        object.__setattr__(self, "help_sections", tuple((title, tuple(entries)) for title, entries in self.help_sections))


@dataclass(frozen=True)
class ActionDefinition:
    id: str
    verb_id: str
    roles: tuple[RoleDefinition, ...]
    variants: tuple[SyntaxVariant, ...]
    arguments: tuple[ArgumentDefinition, ...] = ()
    provider_from: str | None = None
    public: bool = True
    help: str = ""
    examples: tuple[str, ...] = ()
    text_resolver: Callable | None = None
    max_references: int = 32
    max_payload_bytes: int = 8192

    def __post_init__(self):
        for field in ("roles", "variants", "arguments", "examples"):
            object.__setattr__(self, field, tuple(getattr(self, field)))


@dataclass(frozen=True)
class ServiceDefinition:
    id: str
    handler: Callable
    role_kinds: tuple[RoleDefinition, ...] = ()
    config_schema: tuple[ArgumentDefinition, ...] = ()
    presenter: Callable | None = None
    locker: Callable | None = None
    prepare: Callable | None = None

    def __post_init__(self):
        object.__setattr__(self, "role_kinds", tuple(self.role_kinds))
        object.__setattr__(self, "config_schema", tuple(self.config_schema))


@dataclass(frozen=True)
class ActionBinding:
    id: str
    provider_definition: str
    action_id: str
    service_id: str
    config: tuple[tuple[str, object], ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "config", freeze(self.config))


@dataclass(frozen=True)
class ProviderDefinition:
    id: str
    name: str
    group_id: str
    scope_id: str
    unique_names: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "unique_names", tuple(self.unique_names))


@dataclass(frozen=True)
class ContentPackage:
    id: str
    verbs: tuple[VerbDefinition, ...] = ()
    actions: tuple[ActionDefinition, ...] = ()
    services: tuple[ServiceDefinition, ...] = ()
    bindings: tuple[ActionBinding, ...] = ()
    dependencies: tuple[str, ...] = ()
    providers: tuple[ProviderDefinition, ...] = ()

    def __post_init__(self):
        for field in ("verbs", "actions", "services", "bindings", "dependencies", "providers"):
            object.__setattr__(self, field, tuple(getattr(self, field)))


@dataclass(frozen=True)
class PackageManifest:
    packages: tuple[ContentPackage, ...]

    def __post_init__(self):
        object.__setattr__(self, "packages", tuple(self.packages))
