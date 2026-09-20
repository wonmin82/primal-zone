"""명령 등록 목록. 자동 discovery 없이 여기에서 조합한다."""

from commands.base import UnknownCommand
from commands.character import Abilities, Experience, Help, Look, Map, Quest, Skills, Status
from commands.combat import Attack, Flee, Guard, Heal, Heavy
from commands.inventory import Buy, Equip, Equipment, Exchange, Inventory, Shop, Take
from commands.party import (
    PartyAccept,
    PartyCommand,
    PartyInvite,
    PartyKick,
    PartyLeave,
    PartyLootMode,
    PartyReject,
    PartyTransfer,
)
from commands.skills import Allocate, Learn, Retrain
from commands.social import Say
from commands.world_actions import Investigate, Repair, Rest, Return, Talk

COMMANDS = [
    Abilities,
    Skills,
    Experience,
    Equipment,
    Learn,
    Allocate,
    Retrain,
    Take,
    PartyLootMode,
    PartyCommand,
    PartyInvite,
    PartyAccept,
    PartyReject,
    PartyLeave,
    PartyKick,
    PartyTransfer,
    Look,
    Help,
    Status,
    Inventory,
    Equip,
    Attack,
    Heavy,
    Guard,
    Heal,
    Flee,
    Return,
    Rest,
    Shop,
    Buy,
    Exchange,
    Quest,
    Talk,
    Investigate,
    Repair,
    Map,
    Say,
    UnknownCommand,
]
