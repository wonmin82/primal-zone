"""실제 출입증 SSOT, owner scope, 임무/보상/sequence의 원자성."""

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from evennia.utils.dbserialize import deserialize
from world import credential_service as credentials
from world import presentation, rules
from world.content import ITEMS
from world.item_entities import api
from world.item_entities.models import ItemEntity, ItemSequence
from world.item_entities.policy import TREE_OPERATION_SCOPES, definition_errors

from tests.phase5_fixture import Phase5Test


class CredentialTests(Phase5Test):
    def prepare(self, quest):
        def ready(profile):
            profile["quests"]["radio_tower"].update(started=True, generator_fixed=True, boss_defeated=True)
            if quest == "deep_jungle":
                profile["quests"]["radio_tower"]["claimed"] = True
                profile["quests"][quest].update(started=True, boss_defeated=True)
        self.char1.change(ready)

    def test_definition_policy_and_database_uniqueness(self):
        for identity in credentials.CREDENTIAL_QUESTS:
            self.assertEqual(definition_errors(identity, ITEMS[identity]), [])
            row = credentials.grant_credential(self.char1, identity)
            before = self.state()
            for operation in (*TREE_OPERATION_SCOPES, "unknown"):
                if operation == "burn":
                    continue
                with self.subTest(operation=operation), self.assertRaises(ValidationError):
                    api.delete_item(row, operation=operation)
                self.assertEqual(self.state(), before)
            with self.assertRaises(IntegrityError), transaction.atomic():
                # DB 방어선을 직접 검증한다. 정상 API의 full_clean 우회는 이 fixture에만 한정한다.
                ItemEntity.objects.bulk_create([ItemEntity(definition_id=identity, sequence=row.sequence + 100000,
                    quantity=1, location_kind="inventory", owner_object=self.char1,
                    unique_scope_key=row.unique_scope_key)])

    def test_both_issuers_grant_and_reissue_without_repeating_rewards(self):
        for identity, quest in credentials.CREDENTIAL_QUESTS.items():
            with self.subTest(quest=quest):
                self.prepare(quest)
                operation = rules.commander_talk if quest == "radio_tower" else rules.jungle_talk
                result, granted, boss_granted = credentials.issuer_talk(self.char1, identity, operation)
                self.assertEqual((result, granted, boss_granted), ("complete", True, True))
                self.assertTrue(credentials.has_credential(self.char1, identity))
                self.assertNotIn(identity, self.char1.profile()["inventory"])
                self.assertIn(ITEMS[identity]["name"], presentation.inventory(self.char1.profile()))
                before = self.state()
                self.assertEqual(credentials.issuer_talk(self.char1, identity, operation), ("progress", False, False))
                self.assertEqual(self.state(), before)
                row = next(row for row in credentials.credential_items(self.char1) if row.definition_id == identity)
                api.delete_item(row, operation="burn")
                rewards = dict(self.char1.profile())
                self.assertEqual(credentials.issuer_talk(self.char1, identity, operation), ("progress", True, False))
                self.assertEqual(dict(self.char1.profile()), rewards)

    def test_reward_and_credential_failures_restore_all_state(self):
        for identity, quest in credentials.CREDENTIAL_QUESTS.items():
            self.prepare(quest)
            operation = rules.commander_talk if quest == "radio_tower" else rules.jungle_talk
            for method in ("grant_credential", "save_profile"):
                before = self.state()
                target = patch("world.credential_service.grant_credential", side_effect=RuntimeError("grant")) if method == "grant_credential" else patch.object(self.char1, "save_profile", side_effect=RuntimeError("save"))
                with target, self.assertRaises(RuntimeError):
                    credentials.issuer_talk(self.char1, identity, operation)
                self.assertEqual(self.state(), before)

    def test_hidden_owner_scope_prevents_duplicate_and_read_is_read_only(self):
        row = credentials.grant_credential(self.char1, "outpost_supply_pass")
        api.move_item_tree(row, location_kind="personal_storage", owner_object=self.char1)
        before = self.state()
        self.assertEqual(credentials.grant_credential(self.char1, row.definition_id).pk, row.pk)
        self.assertTrue(credentials.has_credential(self.char1, row.definition_id))
        self.assertEqual(self.state(), before)
        self.assertEqual(ItemSequence.objects.get(pk=1).last_value, row.sequence)

    def test_original_issuer_command_grants_and_reissues(self):
        self.prepare("radio_tower")
        self.char1.location = self.rooms["dock"]
        self.assertIn("출입증", self.command("윤대장 대화"))
        api.delete_item(credentials.credential_items(self.char1)[0], operation="burn")
        self.assertIn("재발급", self.command("윤대장 대화"))


class NativeCredentialTests(Phase5Test):
    native = True

    def test_native_quest_reward_does_not_write_legacy_inventory(self):
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(started=True, generator_fixed=True, boss_defeated=True))
        credentials.issuer_talk(self.char1, "outpost_supply_pass", rules.commander_talk)
        self.assertEqual(deserialize(self.char1.db.profile)["inventory"], {})
        self.assertEqual(ItemEntity.objects.get(owner_object=self.char1, definition_id="bandage").quantity, 3)

    def test_native_quest_save_failure_restores_reward_tree_and_sequence(self):
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(started=True, generator_fixed=True, boss_defeated=True))
        before = self.state()
        with patch.object(self.char1, "save_profile", side_effect=RuntimeError("save")), self.assertRaises(RuntimeError):
            credentials.issuer_talk(self.char1, "outpost_supply_pass", rules.commander_talk)
        self.assertEqual(self.state(), before)
