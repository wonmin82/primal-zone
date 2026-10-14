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


class DefaultTargetPolicy(StrEnum):
    REQUIRE_UNIQUE = "require_unique"
    FIRST_LEGACY_ORDER = "first_legacy_order"
    ALL = "all"


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

    def __post_init__(self):
        object.__setattr__(self, "kinds", tuple(self.kinds))


@dataclass(frozen=True)
class ArgumentDefinition:
    name: str
    kind: type = str
    required: bool = True
    default: object = None
    minimum: int | None = None
    maximum: int | None = None

    def __post_init__(self):
        object.__setattr__(self, "default", freeze(self.default))


@dataclass(frozen=True)
class SyntaxVariant:
    id: str
    pattern: str
    suffix: str = ""
    confirmation_required: bool = False
    all_roles: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "all_roles", tuple(self.all_roles))


@dataclass(frozen=True)
class VerbDefinition:
    id: str
    key: str
    aliases: tuple[str, ...] = ()
    summary: str = ""

    def __post_init__(self):
        object.__setattr__(self, "aliases", tuple(self.aliases))


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

    def __post_init__(self):
        for field in ("roles", "variants", "arguments", "examples"):
            object.__setattr__(self, field, tuple(getattr(self, field)))


@dataclass(frozen=True)
class ServiceDefinition:
    id: str
    handler: Callable
    role_kinds: tuple[RoleDefinition, ...] = ()
    config_schema: tuple[ArgumentDefinition, ...] = ()

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
