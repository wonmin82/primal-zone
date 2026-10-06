"""Phase 5의 시각 고정·월드·전체 rollback 상태 fixture."""

from copy import deepcopy
from unittest.mock import Mock, patch

from evennia import search_tag
from typeclasses.explorers import Explorer
from world import equipment_service, recovery, rules
from world.item_entities import api
from world.item_entities.models import ItemEntity, ItemSequence

from tests.base import WorldCommandTest


class Phase5Test(WorldCommandTest):
    character_typeclass = Explorer
    native = False

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        self.enterContext(patch("world.lighting_service.time", return_value=100))
        for module in ("explorers", "enemies", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))
        for character in (self.char1, self.char2):
            character.location = self.rooms["salvage_office"]
            character.push_state = Mock()
            profile = rules.new_profile()
            profile.update(credits=2000, recovery=recovery.initialize(100))
            if self.native:
                profile.update(inventory={}, equipment={"weapon": None, "armor": None})
            character.db.profile = profile
            if self.native:
                equipment_service.use_item_entities(character)

    def obj(self, identity):
        return search_tag(identity, category="primal_interactable")[0]

    def create(self, identity, **kwargs):
        return api.create_item(identity, location_kind="inventory", owner_object=self.char1, **kwargs)

    def state(self):
        return (deepcopy([dict(player.profile_snapshot()) for player in (self.char1, self.char2)]),
                list(ItemEntity.objects.order_by("sequence").values()),
                ItemSequence.objects.get(pk=1).last_value,
                [(player.db.active_weapon_item_id, player.db.active_light_item_id) for player in (self.char1, self.char2)])

    def command(self, raw):
        with patch.object(self.char1, "msg") as message:
            self.char1.execute_cmd(raw)
        return str(message.call_args_list)
