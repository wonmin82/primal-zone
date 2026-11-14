"""명시적 Actor Spawn 생성. 기존 실물의 위치·진행 상태는 재설정하지 않는다."""

from copy import deepcopy

from django.db.models import Q
from evennia import create_object
from evennia.objects.models import ObjectDB
from evennia.objects.objects import DefaultRoom

from world.multiplayer import world_change

from . import content
from .validation import ActorDefinitionError, validate_definitions


def _mutable(value):
    if hasattr(value, "items"):
        return {key: _mutable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_mutable(item) for item in value]
    return deepcopy(value)


def ensure_spawn(spawn, room, *, index=None):
    """개별 배치 선언을 검증한 뒤 실물을 확보한다."""
    validate_definitions(content.ACTORS, content.CAPABILITIES, (spawn,), index=index)
    return _ensure_spawn(spawn, room)


def ensure_registered_spawns(rooms):
    """Bootstrap에서 정적 배치 집합을 한 번 검증한다."""
    validate_definitions(content.ACTORS, content.CAPABILITIES, content.ACTOR_SPAWNS, room_ids=rooms)
    with world_change():
        for spawn in content.ACTOR_SPAWNS.values():
            _ensure_spawn(spawn, rooms[spawn.room_id])


def _ensure_spawn(spawn, room):
    from typeclasses.actors import Actor

    from world.bootstrap import CATEGORY

    if not isinstance(room, DefaultRoom) or not room.pk:
        raise ActorDefinitionError("실제 Room이 필요합니다.")
    definition = content.ACTORS[spawn.actor_id]
    with world_change():
        room_ids = ObjectDB.objects.filter(db_tags__db_key=spawn.room_id, db_tags__db_category=CATEGORY)
        if (room.db.zone_id != spawn.room_id
                or room.tags.get(category=CATEGORY, return_list=True) != [spawn.room_id]
                or list(room_ids.values_list("pk", flat=True).distinct()) != [room.pk]):
            raise ActorDefinitionError("Spawn의 Room 정체성이 일치하지 않습니다.")
        existing = list(ObjectDB.objects.filter(db_tags__db_key=spawn.id,
                                              db_tags__db_category="primal_actor_spawn").distinct())
        if len(existing) > 1:
            raise ActorDefinitionError("동일 Spawn 실물이 중복되어 있습니다.")
        if existing:
            actor = existing[0]
            if not isinstance(actor, Actor) or actor.actor_id != spawn.actor_id or actor.spawn_id != spawn.id:
                raise ActorDefinitionError("기존 Spawn의 Actor 정체성이 일치하지 않습니다.")
            if actor.supports_shared_combat:
                actor.attributes.remove("suppression")
                if actor.db.suppressions is None or not actor.db.combatants:
                    actor.db.suppressions = {}
                from world.loot_rules import boss_hp, updated_enemy_hp

                profile = actor.combat_profile
                maximum = profile["hp"]
                if profile.get("boss"):
                    maximum = boss_hp(maximum, actor.db.scaling_participants or 1)
                if actor.max_hp != maximum:
                    actor.db.combat_state = {
                        **actor.db.combat_state,
                        "max_hp": maximum,
                        "hp": updated_enemy_hp(actor.hp, actor.max_hp, maximum,
                                               actor.db.state, bool(actor.db.combatants)),
                    }
            if actor.capability_active("shop") and actor.db.shop_id != definition.defaults["shop_id"]:
                actor.db.shop_id = definition.defaults["shop_id"]
            if actor.home != room:
                previous_home = actor.home
                actor.home = room
                if actor.location == previous_home and not actor.db.combatants:
                    actor.location = room
            return actor
        return create_actor(definition.id, room, spawn_id=spawn.id)


def create_actor(actor_id, location, *, name=None, spawn_id=None, selection_group=None):
    """같은 정의로 관리 Spawn과 격리 검증 실물을 생성한다."""
    from typeclasses.actors import Actor

    definition = content.ACTORS[actor_id]
    attributes = [("actor_id", actor_id),
                  ("selection_definition_id", actor_id),
                  ("selection_group_id", selection_group or f"actor:{actor_id}"),
                  ("action_provider_id", definition.action_provider_id),
                  *((key, _mutable(value)) for key, value in definition.defaults.items())]
    tags = ()
    if spawn_id is not None:
        attributes.append(("spawn_id", spawn_id))
        tags = ((spawn_id, "primal_actor_spawn"),)
    with world_change():
        actor = create_object(Actor, key=name or definition.name, location=location,
                              home=location, aliases=definition.aliases,
                              attributes=attributes, tags=tags)
        if actor.supports_shared_combat:
            if spawn_id is not None:
                actor.locks.add("delete:false()")
            actor.initialize_shared_combat()
            actor.max_hp = actor.combat_profile["hp"]
        return actor


def legacy_spawn_issues():
    """운영 배치와 충돌하는 이전 형식을 읽기 전용으로 검사한다."""
    issues = []
    if ObjectDB.objects.filter(Q(db_typeclass_path="typeclasses.enemies.Enemy")
                               | Q(db_tags__db_category="primal_spawn")).exists():
        issues.append("이전 적 Spawn이 남아 있는 월드는 자동 변환할 수 없습니다.")
    npc_types = ("Commander", "Pathfinder", "Doctor", "SettlementOfficer", "Shopkeeper",
                 "GrowthTrainer", "SkillTrainer", "AttributeTrainer", "TrainingManager")
    if ObjectDB.objects.filter(
        Q(db_typeclass_path__in=[f"typeclasses.interactables.{name}" for name in npc_types])
        | Q(db_tags__db_category="primal_interactable", db_tags__db_key__in=content.ACTOR_SPAWNS.keys()),
    ).exists():
        issues.append("이전 NPC 실물이 남아 있는 월드는 자동 변환할 수 없습니다.")
    return issues


def audit_registered_spawns():
    """현재 위치가 바뀌었더라도 선언과 실물의 일대일 관계를 확인한다."""
    from typeclasses.actors import Actor

    found = set()
    issues = legacy_spawn_issues()
    objects = ObjectDB.objects.filter(db_tags__db_category="primal_actor_spawn").distinct()
    for actor in objects:
        tags = actor.tags.get(category="primal_actor_spawn", return_list=True)
        spawn = content.ACTOR_SPAWNS.get(tags[0]) if len(tags) == 1 else None
        if (spawn is None or spawn.id in found or not isinstance(actor, Actor)
                or actor.actor_id != spawn.actor_id or actor.spawn_id != spawn.id):
            issues.append(f"Actor Spawn 정체성 불일치: #{actor.pk}")
            continue
        found.add(spawn.id)
    issues.extend(f"Actor Spawn 누락: {spawn_id}" for spawn_id in sorted(content.ACTOR_SPAWNS.keys() - found))
    return issues
