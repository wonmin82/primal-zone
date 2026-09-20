from unittest.mock import patch

from evennia import create_object
from evennia.utils.test_resources import EvenniaCommandTest
from typeclasses.explorers import Explorer
from typeclasses.parties import Party, invitation_for, invite, party_for, respond
from world.multiplayer import object_by_id
from world.rules import RuleError


class PartyTests(EvenniaCommandTest):
    character_typeclass = Explorer

    def test_invite_accept_persistence_and_duplicate(self):
        party = invite(self.char1, self.char2, now=100)
        self.assertEqual(invite(self.char1, self.char2, now=110), party)
        respond(self.char2, True, now=120)
        self.assertEqual(party_for(self.char2).id, party.id)
        self.assertEqual(object_by_id(party.id).state()["members"], [self.char1.id, self.char2.id])
        with patch.object(self.char1.sessions, "count", return_value=0):
            self.char1.at_post_unpuppet(self.account)
        self.assertEqual(party.state()["leader"], self.char1.id)
        with self.assertRaises(RuleError):
            respond(self.char2, True, now=120)

    def test_reject_expiry_and_deleted_party(self):
        party = invite(self.char1, self.char2, now=100)
        respond(self.char2, False, now=110)
        self.assertIsNone(party_for(self.char2))
        invite(self.char1, self.char2, now=120)
        self.assertEqual(invitation_for(self.char2, now=180), (None, None))
        with self.assertRaises(RuleError):
            respond(self.char2, True, now=180)
        invite(self.char1, self.char2, now=200)
        party.remove_member(self.char1)
        with self.assertRaises(RuleError):
            respond(self.char2, True, now=201)

    def test_invalid_invites_do_not_create_parties(self):
        for target in (None, self.char1):
            with self.assertRaises(RuleError):
                invite(self.char1, target)
        self.assertEqual(Party.objects.count(), 0)

    def test_permissions_membership_transfer_and_leave(self):
        party = invite(self.char1, self.char2)
        respond(self.char2, True)
        third = create_object(Explorer, key="세번째탐사자")
        for caller, target in ((self.char1, self.char2), (third, self.char2), (self.char2, third)):
            with self.assertRaises(RuleError):
                invite(caller, target)
        with self.assertRaises(RuleError):
            party.remove_member(self.char2, self.char1)
        with self.assertRaises(RuleError):
            party.remove_member(self.char1, self.char1)
        party.transfer(self.char1, self.char2)
        self.assertEqual(party.state()["leader"], self.char2.id)
        party.remove_member(self.char2)
        self.assertEqual(party.state()["leader"], self.char1.id)
        identity = party.id
        party.remove_member(self.char1)
        self.assertIsNone(object_by_id(identity))
        self.assertIsNone(party_for(self.char1))

    def test_full_party_rechecked_at_accept_and_kick(self):
        party = invite(self.char1, self.char2)
        extras = [create_object(Explorer, key=f"추가탐사자{i}") for i in range(3)]
        for target in extras:
            invite(self.char1, target)
        respond(self.char2, True)
        for target in extras[:2]:
            respond(target, True)
        with self.assertRaises(RuleError):
            respond(extras[2], True)
        with self.assertRaises(RuleError):
            invite(self.char1, create_object(Explorer, key="초과탐사자"))
        party.remove_member(self.char1, self.char2)
        self.assertIsNone(party_for(self.char2))
        party.remove_member(self.char1)
        self.assertEqual(party.state()["leader"], extras[0].id)

    def test_target_action_commands(self):
        self.char1.execute_cmd(f"{self.char2.key} 파티초대")
        self.char2.execute_cmd("파티수락")
        self.assertEqual(party_for(self.char1), party_for(self.char2))
        self.char1.execute_cmd(f"{self.char2.key} 파티장위임")
        self.assertEqual(party_for(self.char1).state()["leader"], self.char2.id)
        self.char2.execute_cmd(f"{self.char1.key} 파티제외")
        self.assertIsNone(party_for(self.char1))
        self.char2.execute_cmd("파티탈퇴")
        self.assertIsNone(party_for(self.char2))
