"""Actor의 선언·구성 검증. 실제 효과는 기존 도메인 Service가 소유한다."""

from .schema import (
    ActorDefinition,
    ActorPresentation,
    ActorSpawn,
    CapabilityDescriptor,
    Classification,
    WorldObjectDefinition,
)

__all__ = (
    "ActorDefinition",
    "ActorPresentation", "ActorSpawn", "CapabilityDescriptor",
    "Classification", "WorldObjectDefinition",
)
