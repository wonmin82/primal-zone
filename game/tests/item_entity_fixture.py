"""신규 Entity domain 테스트용 빈 캐릭터와 전체 원자성 snapshot."""

from copy import deepcopy
from unittest.mock import Mock, patch

from typeclasses.explorers import Explorer
from world import equipment_service, recovery, rules
from world.content import ITEMS
from world.item_entities import api
from world.item_entities.models import ItemEntity, ItemSequence

from tests.base import GameCommandTest


class NativeItemTest(GameCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        self.enterContext(patch("typeclasses.explorers.delay"))
        self.enterContext(patch("world.lighting_service.time", return_value=100))
        for character in (self.char1, self.char2):
            character.push_state = Mock()
            profile = rules.new_profile()
            profile.update(inventory={}, equipment={"weapon": None, "armor": None},
                           hp=30, mental=20, recovery=recovery.initialize(100))
            character.db.profile = profile
            equipment_service.use_item_entities(character)
        definition = deepcopy(ITEMS["guard_carbine"])
        definition.update(name="시험권총", aliases=["시험총"], firearm_family="pistol_9mm",
                          equipment_properties={"slot": "hands", "role": "weapon", "hands_required": 1,
                                                "weapon_type": "firearm", "weapon_attack": 10})
        self.enterContext(patch.dict(ITEMS, {"test_pistol": definition}))

    def create(self, identity, **kwargs):
        return api.create_item(identity, location_kind="inventory", owner_object=self.char1, **kwargs)

    def atomic_state(self):
        return (list(ItemEntity.objects.order_by("sequence").values()),
                [(character.db.active_weapon_item_id, character.db.active_light_item_id,
                  deepcopy(dict(character.profile()))) for character in (self.char1, self.char2)],
                ItemSequence.objects.get(pk=1).last_value)
