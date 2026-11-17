"""Actor 및 시설의 정적 등록."""

from types import MappingProxyType

from typeclasses.interactables import INTERACTABLES, Shopkeeper

from world.actions.schema import ArgumentDefinition
from world.content import ROOMS, spawn_id_for

from .hostile_content import HOSTILE_ACTORS
from .schema import (
    ActorDefinition,
    ActorPresentation,
    ActorSpawn,
    CapabilityDescriptor,
    Classification,
)

SHOPS = {identity: row for identity, row in INTERACTABLES.items() if row["typeclass"] == "Shopkeeper"}

TRAINERS = {identity: row for identity, row in INTERACTABLES.items()
            if row["typeclass"] in {"TrainingManager", "SkillTrainer", "AttributeTrainer"}}


def trainer_definition(identity, row):
    provider = "world.trainingmanager"
    if "skill_id" in row:
        provider = "skill." + row["skill_id"]
    elif "attribute_id" in row:
        provider = "attribute." + row["attribute_id"]
    return ActorDefinition(
        identity, row["name"], Classification.HUMAN,
        ActorPresentation(row["description"], row["presence"], detectability="conspicuous", distant_visible=True),
        aliases=row["aliases"], capabilities=("dialogue", "training"),
        profiles={"dialogue": {"role": row["typeclass"]}},
        defaults={key: row[key] for key in ("skill_id", "attribute_id", "dialogue") if key in row},
        action_provider_id=provider,
    )


ACTORS = MappingProxyType({
    **HOSTILE_ACTORS,
    **{identity: trainer_definition(identity, row) for identity, row in TRAINERS.items()},
    **{identity: ActorDefinition(
        identity, row["name"], Classification.HUMAN,
        ActorPresentation(Shopkeeper.description, Shopkeeper.presence, detectability=Shopkeeper.detectability),
        aliases=row["aliases"], capabilities=("dialogue", "shop"),
        profiles={"dialogue": {"role": "Shopkeeper"}}, defaults={"shop_id": row["shop_id"]},
        action_provider_id="shop." + row["shop_id"],
    ) for identity, row in SHOPS.items()},
    "salvage_officer": ActorDefinition(
        "salvage_officer", "자원 정산관", Classification.HUMAN,
        ActorPresentation("회수부품을 보급칩으로 정산하는 담당자다.",
                          "탐사에서 회수한 물자를 확인하며 정산을 준비하고 있다.", detectability="conspicuous"),
        aliases=("정산관",), capabilities=("dialogue", "settlement"),
        profiles={"dialogue": {"role": "SettlementOfficer"}},
        action_provider_id="world.settlementofficer",
    ),
    "doctor": ActorDefinition(
        "doctor", "의무관", Classification.HUMAN,
        ActorPresentation("보급칩을 받고 부족한 HP를 회복하는 의무관이다. 정신력은 회복하지 않는다.",
                          "탐사자의 부상을 살피며 회복을 준비하고 있다.", detectability="conspicuous"),
        aliases=("의사",), capabilities=("dialogue", "medical"), profiles={"dialogue": {"role": "Doctor"}},
        action_provider_id="world.doctor",
    ),
    "commander": ActorDefinition(
        "commander", "윤대장", Classification.HUMAN,
        ActorPresentation("탐사대를 지휘하는 책임자다. 낡은 지도와 무전기를 늘 곁에 두고 있다.",
                          "낡은 지도를 펼쳐 놓고 탐사대를 기다리고 있다.", detectability="conspicuous",
                          distant_visible=True),
        aliases=("대장",), capabilities=("dialogue",), profiles={"dialogue": {"role": "Commander"}},
    ),
    "pathfinder": ActorDefinition(
        "pathfinder", "선발대 길잡이", Classification.HUMAN,
        ActorPresentation("밀림에서 돌아온 선발대 길잡이다. 두 갈래 탐사로의 표식을 찾고 있다.",
                          "젖은 지도 위에 선발대의 이동 경로를 표시하고 있다.", detectability="conspicuous",
                          distant_visible=True),
        aliases=("길잡이",), capabilities=("dialogue",), profiles={"dialogue": {"role": "Pathfinder"}},
    ),
})
ACTOR_SPAWNS = MappingProxyType({
    **{identity: ActorSpawn(identity, identity, row["room"])
       for identity, row in {**SHOPS, **TRAINERS}.items()},
    "salvage_officer": ActorSpawn("salvage_officer", "salvage_officer", "salvage_office"),
    "doctor": ActorSpawn("doctor", "doctor", "infirmary"),
    "commander": ActorSpawn("commander", "commander", "dock"),
    "pathfinder": ActorSpawn("pathfinder", "pathfinder", "jungle_edge"),
    **{spawn_id_for(room_id, actor_id): ActorSpawn(spawn_id_for(room_id, actor_id), actor_id, room_id)
    for room_id, room in ROOMS.items()
    for actor_id in room["enemies"]},
})
CAPABILITIES = MappingProxyType({
    "training": CapabilityDescriptor("training"),
    "shop": CapabilityDescriptor("shop"),
    "settlement": CapabilityDescriptor("settlement", binding_ids=(
        "settlement.rate.binding", "settlement.exchange.binding", "settlement.all.binding",
    )),
    "medical": CapabilityDescriptor("medical", binding_ids=("medical.treat.binding",)),
    "dialogue": CapabilityDescriptor(
        "dialogue", ("dialogue",), (("dialogue", (ArgumentDefinition("role"),)),),
    ),
    "combat": CapabilityDescriptor(
        "combat", ("combat",), (("combat", (
            ArgumentDefinition("combat_mode", choices=("claimed", "public")),
            ArgumentDefinition("hp", int, minimum=1),
            ArgumentDefinition("attack", int, minimum=0),
            ArgumentDefinition("defense", int, minimum=0),
            ArgumentDefinition("xp", int, minimum=0),
            ArgumentDefinition("currency", int, minimum=0),
            ArgumentDefinition("boss", bool, required=False),
            ArgumentDefinition("boss_quest", required=False),
            ArgumentDefinition("special_period", int, required=False, minimum=1),
            ArgumentDefinition("special_verb", required=False),
            ArgumentDefinition("telegraph", required=False),
        )),), active_states=("alive",),
    ),
    "duel": CapabilityDescriptor("duel", active_states=("alive",)),
})
WORLD_OBJECTS = MappingProxyType({})
