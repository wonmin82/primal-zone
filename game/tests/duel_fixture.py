"""격리 검증용 Actor 정의와 Spawn."""

from dataclasses import replace
from unittest.mock import patch

from world.actions.gateway import ActionResult
from world.actions.schema import (
    ActionBinding,
    ActionDefinition,
    ContentPackage,
    ExecutionPolicy,
    ProviderDefinition,
    ReferenceKind,
    RoleDefinition,
    ServiceDefinition,
    SyntaxVariant,
    VerbDefinition,
)
from world.actors import content
from world.actors.schema import (
    ActorSpawn,
    AttackPhrase,
    CapabilityDescriptor,
    Classification,
    CombatNarrationSpec,
)
from world.actors.spawn import ensure_spawn

INSTRUCTOR_ID = "fixture.duel_instructor"
GUARD_ID = "fixture.duel_guard"


def definitions():
    trainer = content.ACTORS["trainer_heavy"]
    sentinel = content.ACTORS["sentinel"]
    return {
        INSTRUCTOR_ID: replace(
            trainer,
            id=INSTRUCTOR_ID,
            name="대련교관",
            aliases=(),
            capabilities=(*trainer.capabilities, "combat", "duel"),
            combat_narration=CombatNarrationSpec((AttackPhrase("주먹", "때렸다", "세게 때렸다"),)),
            profiles={**trainer.profiles, "combat": content.ACTORS["scavenger"].profiles["combat"]},
            defaults={**trainer.defaults, "state": "alive", "combat_state": {"hp": 24}},
        ),
        GUARD_ID: replace(
            sentinel,
            id=GUARD_ID,
            name="대련경비기",
            aliases=(),
            classification=Classification.MACHINE,
            capabilities=("combat", "duel", "interaction"),
            action_provider_id=GUARD_ID,
        ),
    }


def registry_overlay():
    return patch.object(content, "ACTORS", {**content.ACTORS, **definitions()})


def spawn_fixture(identity, room, *, index=None):
    return ensure_spawn(ActorSpawn(identity, identity, room.db.zone_id), room, index=index)


def inspect_guard(context):
    actor, = context.roles["provider"]
    return ActionResult(messages=(actor.key + "의 외부 진단 단자가 응답한다.",))


INTERACTION_ID = "fixture.duel_guard.inspect"
INTERACTION = CapabilityDescriptor("interaction", binding_ids=(INTERACTION_ID + ".binding",))
PROVIDER = RoleDefinition("provider", (ReferenceKind.ACTOR,))
PACKAGE = ContentPackage(
    "fixture.duel",
    verbs=(VerbDefinition(INTERACTION_ID + ".verb", "경비진단"),),
    actions=(ActionDefinition(INTERACTION_ID, INTERACTION_ID + ".verb", (PROVIDER,),
                              (SyntaxVariant("direct", r"(?P<provider>.+)"),)),),
    services=(ServiceDefinition(INTERACTION_ID + ".service", inspect_guard, (PROVIDER,),
                                 policy=ExecutionPolicy.READ_ONLY),),
    bindings=(ActionBinding(INTERACTION_ID + ".binding", GUARD_ID, INTERACTION_ID,
                             INTERACTION_ID + ".service", capability_id="interaction"),),
    providers=(ProviderDefinition(GUARD_ID, "대련경비기", "actor:" + GUARD_ID, "training_room"),),
)
