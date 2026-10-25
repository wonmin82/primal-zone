"""Actor의 선언·구성 검증. 실제 효과는 기존 도메인 Service가 소유한다."""

from .content import ACTOR_SPAWNS, ACTORS, CAPABILITIES, WORLD_OBJECTS
from .schema import (
    ActorDefinition,
    ActorPresentation,
    ActorSpawn,
    CapabilityDescriptor,
    Classification,
    WorldObjectDefinition,
)
from .validation import ActorDefinitionError, validate_definitions

__all__ = (
    "ACTORS", "ACTOR_SPAWNS", "CAPABILITIES", "WORLD_OBJECTS", "ActorDefinition",
    "ActorDefinitionError", "ActorPresentation", "ActorSpawn", "CapabilityDescriptor",
    "Classification", "WorldObjectDefinition", "validate_definitions",
)
