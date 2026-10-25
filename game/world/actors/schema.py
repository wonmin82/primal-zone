"""DB에 의존하지 않는 Actor/Capability의 불변 콘텐츠 계약."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from world.actions.schema import ArgumentDefinition


class Classification(StrEnum):
    HUMAN = "human"
    CREATURE = "creature"
    MACHINE = "machine"
    HYBRID = "hybrid"
    OTHER = "other"


def immutable(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: immutable(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(immutable(item) for item in value)
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise TypeError("Actor 콘텐츠에는 기본 자료형만 선언할 수 있습니다.")


@dataclass(frozen=True)
class ActorPresentation:
    description: str
    presence: str
    semantic_role: str = "npc"
    detectability: str = "normal"
    distant_visible: bool = False
    distant_presence: str = "멀리 서 있다."
    unit: str = "명"


@dataclass(frozen=True)
class CapabilityDescriptor:
    id: str
    required_profiles: tuple[str, ...] = ()
    profile_schemas: tuple[tuple[str, tuple[ArgumentDefinition, ...]], ...] = ()
    binding_ids: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    active_states: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("required_profiles", "binding_ids", "conflicts", "active_states"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(self, "profile_schemas", tuple(
            (name, tuple(schema)) for name, schema in self.profile_schemas))


@dataclass(frozen=True)
class ActorDefinition:
    id: str
    name: str
    classification: Classification
    presentation: ActorPresentation
    level: int = 1
    aliases: tuple[str, ...] = ()
    subtype: str | None = None
    faction: str | None = None
    capabilities: tuple[str, ...] = ()
    profiles: Mapping = field(default_factory=dict)
    defaults: Mapping = field(default_factory=dict)
    action_provider_id: str = "actor.entity"

    def __post_init__(self):
        object.__setattr__(self, "aliases", tuple(self.aliases))
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        object.__setattr__(self, "profiles", immutable(self.profiles))
        object.__setattr__(self, "defaults", immutable(self.defaults))


@dataclass(frozen=True)
class ActorSpawn:
    id: str
    actor_id: str
    room_id: str


@dataclass(frozen=True)
class WorldObjectDefinition:
    id: str
    name: str
    presentation: ActorPresentation
    action_provider_id: str
    aliases: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "aliases", tuple(self.aliases))
