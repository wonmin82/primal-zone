"""명시적 Actor Spawn 생성. 기존 실물의 위치·진행 상태는 재설정하지 않는다."""

from copy import deepcopy

from evennia import create_object
from evennia.objects.models import ObjectDB
from evennia.objects.objects import DefaultRoom

from world.multiplayer import world_change

from . import content
from .schema import ActorSpawn
from .validation import ActorDefinitionError, validate_definitions


def _mutable(value):
    if hasattr(value, "items"):
        return {key: _mutable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_mutable(item) for item in value]
    return deepcopy(value)


def ensure_spawn(spawn, room, *, index=None):
    """기존 Spawn은 재사용하고 정체성 충돌은 변경 전에 거절한다."""
    from typeclasses.actors import Actor

    if not isinstance(spawn, ActorSpawn) or not isinstance(room, DefaultRoom) or not room.pk:
        raise ActorDefinitionError("Spawn과 실제 Room이 필요합니다.")
    if room.db.zone_id and room.db.zone_id != spawn.room_id:
        raise ActorDefinitionError("Spawn의 Room 정체성이 일치하지 않습니다.")
    validate_definitions(content.ACTORS, content.CAPABILITIES, (spawn,), index=index)
    definition = content.ACTORS[spawn.actor_id]
    with world_change():
        existing = list(ObjectDB.objects.filter(db_tags__db_key=spawn.id,
                                              db_tags__db_category="primal_actor_spawn").distinct())
        if len(existing) > 1:
            raise ActorDefinitionError("동일 Spawn 실물이 중복되어 있습니다.")
        if existing:
            actor = existing[0]
            if not isinstance(actor, Actor) or actor.actor_id != spawn.actor_id or actor.spawn_id != spawn.id:
                raise ActorDefinitionError("기존 Spawn의 Actor 정체성이 일치하지 않습니다.")
            return actor
        attributes = [("actor_id", definition.id), ("spawn_id", spawn.id),
                      ("selection_definition_id", definition.id),
                      ("selection_group_id", f"actor:{definition.id}"),
                      ("action_provider_id", definition.action_provider_id),
                      *((name, _mutable(value)) for name, value in definition.defaults.items())]
        return create_object(Actor, key=definition.name, location=room, home=room,
                             aliases=definition.aliases, attributes=attributes,
                             tags=((spawn.id, "primal_actor_spawn"),))
