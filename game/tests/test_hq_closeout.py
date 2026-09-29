"""본부 전체 managed identity와 bootstrap의 개인/공용 상태 보존 경계."""

from copy import deepcopy
from unittest.mock import Mock, patch

from evennia import create_script, search_tag
from evennia.objects.models import ObjectDB
from evennia.utils.dbserialize import deserialize
from typeclasses.explorers import Explorer
from typeclasses.interactables import INTERACTABLES
from typeclasses.scripts import WorldLifecycle
from world import environment, rules
from world.bootstrap import build_world, stale_definitions
from world.content.integrity import errors
from world.observation import context_for
from world.room_hints import render

from tests.base import WorldCommandTest


class HeadquartersCloseoutTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        self.char1.push_state = Mock()
        self.char1.location = self.rooms["storage_room"]
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))

    def test_bootstrap_preserves_all_managed_identities_player_and_shared_state(self):
        box = search_tag("shared_container", category="primal_interactable")[0]
        box.db.items = {"bandage": 4, "scrap": 2}
        self.rooms["support_elevator"].db.current_stop = "3f"
        script = create_script(WorldLifecycle, autostart=False)
        script.db.facilities = {"version": 1, "states": {"outpost_power": True}}
        script.db.environment = environment.new_environment(100)
        profile = rules.new_profile()
        profile.update(credits=143, xp=90, storage={"scrap": 5},
                       visited=["staging_room", "storage_room", "support_3f_c"])
        profile["skills"]["heavy"] = 2
        profile["proficiencies"]["weapon"]["xp"] = 7
        profile["attributes"]["strength"]["allocated"] = 1
        profile["quests"]["radio_tower"]["record_read"] = True
        self.char1.save_profile(profile)
        before_profile = deepcopy(self.char1.profile())
        before_shared = [deserialize(script.db.facilities), deserialize(script.db.environment)]

        def snapshot():
            return {obj.id: (obj.key, obj.db_location_id, obj.db_destination_id,
                             sorted(obj.aliases.all()), sorted(obj.tags.all(return_key_and_category=True)),
                             obj.db.shop_id) for obj in ObjectDB.objects.all()}

        before = snapshot()
        for _ in range(2):
            build_world()
            self.assertEqual(snapshot(), before)
            self.assertEqual(self.char1.profile(), before_profile)
            self.assertEqual(self.char1.location, self.rooms["storage_room"])
            self.assertEqual(deserialize(box.db.items), {"bandage": 4, "scrap": 2})
            self.assertEqual(self.rooms["support_elevator"].db.current_stop, "3f")
            self.assertEqual([deserialize(script.db.facilities), deserialize(script.db.environment)], before_shared)
            self.assertEqual(stale_definitions(), [])
            self.assertEqual(errors(INTERACTABLES), [])

    def test_same_service_policy_keeps_perception_safety_combat_and_hint_contracts(self):
        for identity in ("instructor", "doctor", "infirmary_bed", "salvage_officer", "supply_shopkeeper"):
            service = search_tag(identity, category="primal_interactable")[0]
            self.char1.location = service.location
            self.assertTrue(service.available(self.char1))
            hint = render(context_for(self.char1))
            service.locks.add("view:false()")
            self.assertFalse(service.available(self.char1))
            self.assertNotIn(service.key, render(context_for(self.char1)))
            service.locks.add("view:all()")
            self.assertEqual(render(context_for(self.char1)), hint)
            self.char1.change(lambda p: p.update(combat_target=999999))
            self.assertFalse(service.available(self.char1))
            self.char1.change(lambda p: p.update(combat_target=None))
            self.char1.location = self.rooms["dock"]
            self.assertFalse(service.available(self.char1))
            original = service.location
            service.location = self.char1.location
            self.assertTrue(service.available(self.char1))
            service.location = self.char1.location = self.rooms["grass"]
            self.assertFalse(service.available(self.char1))
            service.location = original
