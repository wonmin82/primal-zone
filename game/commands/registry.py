"""명령 등록 목록. 자동 discovery 없이 여기에서 조합한다."""

from commands.base import UnknownCommand
from commands.character import (
    Abilities,
    Exits,
    Experience,
    GlobalShortcuts,
    Help,
    Look,
    Map,
    Quest,
    Skills,
    Status,
    Weather,
)
from commands.combat import Attack, Breathe, Flee, Heal, Heavy, Insight, Shooting, Suppress
from commands.command_shortcuts import DeleteShortcut, Sequence, Shortcuts
from commands.inventory import (
    Equipment,
    Inventory,
    Take,
)
from commands.items import (
    Drop,
    Give,
)
from commands.party import PARTY_COMMANDS
from commands.social import PrivateTalk, RefuseTalk, Reply, Say
from commands.world_actions import Return

COMMANDS = [
    Abilities,
    Skills,
    Experience,
    Equipment,
    Take,
    *PARTY_COMMANDS,
    Look,
    Exits,
    Weather,
    Help,
    GlobalShortcuts,
    Sequence,
    Shortcuts,
    DeleteShortcut,
    Status,
    Inventory,
    Drop,
    Give,
    Attack,
    Heavy,
    Shooting,
    Insight,
    Suppress,
    Heal,
    Breathe,
    Flee,
    Return,
    Quest,
    Map,
    Say,
    PrivateTalk,
    Reply,
    RefuseTalk,
    UnknownCommand,
]
