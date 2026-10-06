"""공통 이동·개인 출입증·예약 시설·bootstrap의 계약."""

from unittest.mock import patch

from evennia import search_tag
from evennia.objects.models import ObjectDB
from typeclasses.parties import invite, respond
from world.access import can_enter, entry_message
from world.bootstrap import build_world
from world.content import ROOMS
from world.credential_service import grant_credential
from world.item_entities import api

from tests.phase5_fixture import Phase5Test


class AccessTests(Phase5Test):
    def test_actual_pass_required_not_quest_or_other_pass(self):
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(claimed=True))
        for zone in ("outpost_equipment", "outpost_weapon"):
            self.assertFalse(can_enter(self.char1, self.rooms[zone]))
        grant_credential(self.char1, "special_supply_pass")
        self.assertFalse(can_enter(self.char1, "outpost_weapon"))
        grant_credential(self.char1, "outpost_supply_pass")
        before = self.state()
        for zone in ("outpost_equipment", "outpost_weapon"):
            self.assertTrue(can_enter(self.char1, self.rooms[zone]))
        for zone in ("reserved_equipment", "reserved_weapon"):
            self.assertFalse(can_enter(self.char1, zone))
            self.assertEqual(entry_message(self.char1, zone), "출입 권한은 확인되지만 시설은 아직 폐쇄되어 있다.")
        self.assertEqual(self.state(), before)

    def test_direction_web_command_and_direct_move_use_same_access(self):
        self.char1.location = self.rooms["support_3f_w2"]
        with patch("world.access.entry_message", wraps=entry_message) as check:
            self.command("북")
            self.assertTrue(check.called)
        self.assertEqual(self.char1.zone, "support_3f_w2")
        self.assertFalse(self.char1.move_to(self.rooms["outpost_equipment"]))
        grant_credential(self.char1, "outpost_supply_pass")
        self.command("북")  # Web도 동일 direction command를 전달한다.
        self.assertEqual(self.char1.zone, "outpost_equipment")
        row = api.items_owned_by(self.char1).get(definition_id="outpost_supply_pass")
        api.delete_item(row, operation="burn")
        self.command("남")
        self.assertEqual(self.char1.zone, "support_3f_w2")
        self.command("북")
        self.assertEqual(self.char1.zone, "support_3f_w2")

    def test_party_does_not_share_credential(self):
        invite(self.char1, self.char2)
        respond(self.char2, True)
        grant_credential(self.char1, "outpost_supply_pass")
        self.assertTrue(can_enter(self.char1, "outpost_weapon"))
        self.assertFalse(can_enter(self.char2, "outpost_weapon"))

    def test_existing_quest_gate_and_public_exit(self):
        self.assertFalse(can_enter(self.char1, "ridge"))
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(generator_fixed=True))
        self.assertTrue(can_enter(self.char1, "ridge"))
        for zone in ("support_3f_w2", "support_3f_e2"):
            self.assertTrue(can_enter(self.char1, zone))

    def test_world_topology_objects_and_rebuild_are_idempotent(self):
        before = ObjectDB.objects.count()
        for _ in range(2):
            build_world()
            self.assertEqual(ObjectDB.objects.count(), before)
        for corridor, active, reserved in (("support_3f_w2", "outpost_equipment", "reserved_equipment"),
                                            ("support_3f_e2", "outpost_weapon", "reserved_weapon")):
            self.assertEqual(ROOMS[corridor]["exits"]["북"], active)
            self.assertEqual(ROOMS[corridor]["exits"]["남"], reserved)
            self.assertEqual(len(search_tag(active + "_shopkeeper", category="primal_interactable")), 1)
            self.assertFalse(any(obj.is_typeclass("typeclasses.interactables.Shopkeeper")
                                 for obj in self.rooms[reserved].contents))
        self.assertEqual(self.obj("incinerator").location, self.rooms["salvage_office"])
