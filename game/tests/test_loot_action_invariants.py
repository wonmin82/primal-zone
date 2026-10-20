"""실제 Loot Action의 권리·안정 참조·원자적 지급 회귀. 격리 SQLite만 사용한다."""

from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

from server.conf.primal_inputfuncs import pz_action
from typeclasses.parties import create_party, invite, respond
from world import loot_service
from world.actions.gateway import ResultStatus, execute
from world.actions.loot_presentation import source_controls
from world.actions.manifest import compiled, get_index
from world.actions.presentation import reference_json
from world.actions.resolver import dispatch_text
from world.item_entities import api
from world.item_entities.models import ItemEntity, ItemSequence
from world.loot_entities.models import CurrencyLoot, CurrencyLootShare, LootClaim
from world.multiplayer import world_change
from world.selection_numbers.api import descriptor, number_for, records_for
from world.selection_numbers.models import NumberScope, SelectionNumber

from tests.loot_entity_fixture import NativeLootTest


class LootActionInvariantTests(NativeLootTest):
    def setUp(self):
        super().setUp()
        compiled.cache_clear()
        self.index = get_index()
        self.sessions = {player.pk: self.connect_character(player) for player in (self.char1, self.char2)}
        self.output = {player.pk: self.enterContext(patch.object(player, "msg"))
                       for player in (self.char1, self.char2)}
        # 고정 기한의 권리를 실제 Gateway/도메인에서 같은 시각에 판정한다.
        for module in ("typeclasses.loot", "world.actions.gateway", "world.lifecycle",
                       "world.actions.loot_resolution", "world.actions.loot_services"):
            self.enterContext(patch(f"{module}.time", return_value=100))
        self.verb = next(verb.id for verb in self.index.verbs.values() if verb.key == "가져")

    def tearDown(self):
        compiled.cache_clear()
        super().tearDown()

    def invocation(self, argument="시체에서 모두", player=None):
        return dispatch_text(player or self.char1, self.index, self.verb, argument, "가져")

    def run_action(self, invocation, player=None):
        player = player or self.char1
        return execute(player, self.sessions[player.pk], invocation, self.index)

    def payload(self, invocation, request_id="loot-invariant"):
        return {"action_id": invocation.action_id, "variant": invocation.variant_id,
                "roles": {name: [reference_json(ref) for ref in refs] for name, refs in invocation.roles},
                "arguments": dict(invocation.arguments), "request_id": request_id}

    def state(self):
        from typeclasses.loot import DroppedLoot

        return ([list(model.objects.order_by("pk").values())
                 for model in (ItemEntity, LootClaim, CurrencyLoot, CurrencyLootShare)],
                [(player.pk, deepcopy(dict(player.profile()))) for player in (self.char1, self.char2)],
                ItemSequence.objects.filter(pk=1).values_list("last_value", flat=True).first(),
                list(DroppedLoot.objects.values_list("pk", flat=True)),
                deepcopy(list(self.source.db.entries or [])),
                list(SelectionNumber.objects.order_by("pk").values()),
                list(NumberScope.objects.order_by("pk").values()))

    def currency(self, *, shares=None, quantity=20, deadline=300):
        return loot_service.create_currency(self.source, quantity,
                                            shares={self.char1: 10, self.char2: 10} if shares is None else shares,
                                            reserved_player=self.char1, protection_until=deadline)

    def balances(self):
        return tuple(player.profile()["credits"] for player in (self.char1, self.char2))

    def public_errors(self, command=None, payload=None):
        """실제 공개 어댑터가 출력한 오류만 비교하고 Prompt는 별도로 보존한다."""
        output = self.output[self.char2.pk]
        output.reset_mock()
        if command is not None:
            completed = []
            self.char2.execute_cmd(command, session=self.sessions[self.char2.pk]).addCallback(
                lambda _: completed.append(True))
            self.assertEqual(completed, [True])
        else:
            pz_action(self.sessions[self.char2.pk], payload)
        self.assertFalse([call for call in output.call_args_list if call.kwargs.get("kind") == "event"])
        return [str(call.args[0]) for call in output.call_args_list if call.kwargs.get("kind") == "error"]

    def test_private_item_public_name_and_number_match_absent_without_side_effects(self):
        from time import time

        item = self.loot_item(quantity=7, deadline=time() + 300)
        reference = descriptor(item).reference
        before = self.state()
        responses = [self.public_errors(command=f"시체에서 {query} 가져")
                     for query in ("권총탄", "없는부품", "권총탄 1", "권총탄 999",
                                   "권총탄 모두", "없는부품 모두")]
        self.assertEqual(self.state(), before)
        self.output[self.char1.pk].assert_not_called()
        self.char1.push_state.assert_not_called()
        self.char2.push_state.assert_not_called()
        self.assertEqual(number_for(reference), 1)
        self.assertTrue(all(responses))
        self.assertEqual(responses, [responses[0]] * 6)

    def test_private_currency_public_number_matches_absent_without_side_effects(self):
        from time import time

        self.currency(shares={self.char1: 20}, deadline=time() + 300)
        before = self.state()
        responses = [self.public_errors(command=f"시체에서 {query} 집")
                     for query in ("칩 1", "칩 999", "20칩", "999칩")]
        self.assertEqual(self.state(), before)
        self.output[self.char1.pk].assert_not_called()
        self.assertTrue(all(responses))
        self.assertEqual(responses, [responses[0]] * 4)

    def test_private_web_references_match_absent_for_items_and_currency(self):
        from time import time
        from uuid import uuid4

        from world.actions.gateway import from_web

        item = self.loot_item(quantity=7, deadline=time() + 300)
        currency = self.currency(shares={self.char1: 20}, deadline=time() + 300)
        before = self.state()
        for query, row in (("권총탄 1", item), ("칩 1", currency)):
            selected = self.invocation(f"시체에서 {query}")
            roles = dict(selected.roles)
            reference = roles["subject"][0]
            missing = replace(reference, identity=str(uuid4()) if row is item else "999999999")
            absent = replace(selected, roles=tuple((name, (missing,) if name == "subject" else refs)
                                                  for name, refs in selected.roles))
            results, public = [], []
            for counter, invocation in enumerate((selected, absent)):
                payload = self.payload(invocation, f"private-{query}-{counter}")
                results.append(self.run_action(from_web(payload, self.index), self.char2))
                public.append(self.public_errors(payload=payload))
            self.assertEqual([result.status for result in results], [ResultStatus.REFUSED] * 2)
            self.assertEqual(self.state(), before)
            self.output[self.char1.pk].assert_not_called()
            self.assertEqual(results[0].messages, results[1].messages)
            self.assertTrue(all(public))
            self.assertEqual(public[0], public[1])
            self.assertNotIn(str(row.pk), str(public))

    def test_mixed_private_number_never_falls_back_to_accessible_entry(self):
        from time import time

        private = self.loot_item(quantity=7, deadline=time() + 300)
        accessible = self.loot_item(quantity=3, deadline=99)
        loot_service.reconcile_claims(self.source, now=100)
        refs = [descriptor(item).reference for item in (private, accessible)]
        before = self.state()
        denied = self.public_errors(command="시체에서 권총탄 1 가져")
        absent = self.public_errors(command="시체에서 권총탄 999 가져")
        default = self.public_errors(command="시체에서 권총탄 가져")
        self.assertEqual(self.state(), before)
        self.assertEqual([number_for(ref) for ref in refs], [1, 2])
        self.assertTrue(denied)
        self.assertEqual(denied, absent)
        self.assertEqual(default, denied)
        result = self.run_action(self.invocation("시체에서 권총탄 2", self.char2), self.char2)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        accessible.refresh_from_db()
        private.refresh_from_db()
        self.assertEqual((private.quantity, accessible.quantity), (7, 2))
        self.assertEqual(ItemEntity.objects.get(owner_object=self.char2).quantity, 1)

    def test_private_alias_collision_and_numeric_name_do_not_change_public_errors(self):
        from time import time

        from world.content import ITEMS

        definitions = {name: {**deepcopy(ITEMS["ammo_9"]), "name": label, "aliases": ["비공개별칭"]}
                       for name, label in (("hidden_a", "숨김부품 2"), ("hidden_b", "다른숨김부품"))}
        with patch.dict(ITEMS, definitions):
            for identity in definitions:
                self.loot_item(identity, quantity=7, deadline=time() + 300)
            before = self.state()
            absent = self.public_errors(command="시체에서 없는부품 가져")
            alias = self.public_errors(command="시체에서 비공개별칭 가져")
            self.assertEqual(alias, absent)
            malformed = [self.public_errors(command=f"시체에서 {query} 가져")
                         for query in ("숨김부품 2 3", "없는부품 2 3")]
            self.assertTrue(all(malformed))
            self.assertEqual(malformed[0], malformed[1])
            self.assertNotEqual(malformed[0], absent)
            self.assertEqual(self.state(), before)

    def test_authorized_quantity_error_and_success_keep_domain_behavior(self):
        row = self.currency(shares={self.char1: 20})
        before = self.state()
        refused = self.run_action(self.invocation("시체에서 21칩"))
        self.assertEqual(refused.status, ResultStatus.REFUSED)
        self.assertEqual(refused.messages, ("원래 대상의 수량이 부족합니다.",))
        self.assertEqual(self.state(), before)
        self.assertEqual(self.run_action(self.invocation("시체에서 5칩")).status, ResultStatus.SUCCESS)
        row.refresh_from_db()
        self.assertEqual(row.quantity, 15)

    def test_unrelated_private_entry_preserves_accessible_alias_ambiguity(self):
        from time import time

        from world.content import ITEMS
        from world.rules import RuleError

        definitions = {name: {**deepcopy(ITEMS["ammo_9"]), "name": label, "aliases": ["공개별칭"]}
                       for name, label in (("public_a", "공개부품A"), ("public_b", "공개부품B"))}
        with patch.dict(ITEMS, definitions):
            for identity in definitions:
                api.create_item(identity, quantity=2, location_kind="corpse_loot", owner_object=self.source)
            self.loot_item(quantity=7, deadline=time() + 300)
            before = self.state()
            with self.assertRaisesMessage(RuleError, "서로 다른 선택 그룹의 별칭이 겹칩니다."):
                self.invocation("시체에서 공개별칭", self.char2)
            self.assertEqual(self.state(), before)

    def test_public_command_accepts_item_names_with_spaces_after_native_cutover(self):
        row = self.loot_item("water", quantity=2)
        completed = []
        self.char1.execute_cmd("시체에서 정제 수 집").addCallback(lambda _: completed.append(True))
        self.assertEqual(completed, [True])
        row.refresh_from_db()
        self.assertEqual(row.quantity, 1)
        self.assertEqual(ItemEntity.objects.get(location_kind="inventory").definition_id, "water")

    def test_player_rights_do_not_renumber_or_change_stable_references(self):
        first = self.loot_item(quantity=2)
        second = self.loot_item(quantity=3, assigned=self.char2)
        claim = LootClaim.objects.get(item_entity=second)
        claim.reserved_player = self.char2
        claim.save()
        refs = tuple(descriptor(item).reference for item in (first, second))
        before = self.state()
        for player in (self.char1, self.char2):
            visible = {record.reference: record.number for record in records_for(player)}
            self.assertEqual([visible[ref] for ref in refs], [1, 2])
        one = self.invocation("시체에서 권총탄 1", self.char1)
        two = self.invocation("시체에서 권총탄 2", self.char2)
        self.assertEqual(dict(one.roles)["subject"], (refs[0],))
        self.assertEqual(dict(two.roles)["subject"], (refs[1],))
        self.assertEqual(self.state(), before)
        # 선택권이 없는 1번을 2번으로 대체하거나 권한별로 번호를 앞당기지 않는다.
        denied = self.invocation("시체에서 권총탄 1", self.char2)
        self.assertEqual(self.run_action(denied, self.char2).status, ResultStatus.REFUSED)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.run_action(two, self.char2).status, ResultStatus.SUCCESS)
        self.assertEqual(number_for(refs[0]), 1)

    def test_zero_currency_share_retains_action_trigger_right_and_partial_split(self):
        row = self.currency(shares={self.char1: 0, self.char2: 20})
        reference = descriptor(row).reference
        before = self.balances()
        result = self.run_action(self.invocation("시체에서 5칩"))
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        row.refresh_from_db()
        self.assertEqual(row.quantity, 15)
        self.assertEqual(self.balances(), (before[0], before[1] + 5))
        self.assertEqual(row.shares.get(player=self.char1).remaining_amount, 0)
        self.assertEqual(number_for(reference), 1)
        self.assertEqual(self.run_action(self.invocation("시체에서 칩 모두")).status, ResultStatus.SUCCESS)
        self.assertFalse(CurrencyLoot.objects.exists())
        self.assertFalse(CurrencyLootShare.objects.exists())
        self.assertEqual(self.balances(), (before[0], before[1] + 20))

    def test_partial_currency_invalidates_other_preselected_request(self):
        row = self.currency()
        first = self.invocation("시체에서 5칩", self.char1)
        second = self.invocation("시체에서 5칩", self.char2)
        self.assertEqual(self.run_action(first).status, ResultStatus.SUCCESS)
        before = self.state()
        self.assertEqual(self.run_action(second, self.char2).status, ResultStatus.REFUSED)
        self.assertEqual(self.state(), before)
        row.refresh_from_db()
        self.assertEqual(row.quantity, 15)

    def test_partial_item_invalidates_stale_quantity_and_keeps_source_number(self):
        row = self.loot_item(quantity=10)
        reference = descriptor(row).reference
        selected = self.invocation("시체에서 권총탄 1")
        partial = replace(selected, arguments=tuple((key, 3 if key == "quantity" else value)
                                                    for key, value in selected.arguments))
        self.assertEqual(self.run_action(partial).status, ResultStatus.SUCCESS)
        row.refresh_from_db()
        self.assertEqual((row.quantity, number_for(reference)), (7, 1))
        self.assertEqual(ItemEntity.objects.get(location_kind="inventory").quantity, 3)
        before = self.state()
        self.assertEqual(self.run_action(selected).status, ResultStatus.REFUSED)
        self.assertEqual(self.state(), before)

    def test_rights_and_share_changes_reject_preselected_request_without_payout(self):
        item = self.loot_item()
        row = self.currency()
        selected = self.invocation()
        claim = LootClaim.objects.get(item_entity=item)
        claim.assigned_player = self.char2
        claim.save()
        before = self.state()
        self.assertEqual(self.run_action(selected).status, ResultStatus.REFUSED)
        self.assertEqual(self.state(), before)
        selected = self.invocation("시체에서 칩 모두")
        first = row.shares.get(player=self.char1)
        second = row.shares.get(player=self.char2)
        first.remaining_amount = 9
        first.save()
        second.remaining_amount = 11
        second.save()
        before = self.state()
        self.assertEqual(self.run_action(selected).status, ResultStatus.REFUSED)
        self.assertEqual(self.state(), before)

    def test_party_join_leave_and_assignment_do_not_reissue_number(self):
        party = create_party(self.char1, now=100)
        row = self.loot_item(party=party, assigned=self.char1)
        reference = descriptor(row).reference
        number = number_for(reference)
        invite(self.char1, self.char2, now=100)
        respond(self.char2, True, now=100)
        selected = self.invocation("시체에서 모두", self.char2)
        party.remove_member(self.char2, now=100)
        before = self.state()
        self.assertEqual(self.run_action(selected, self.char2).status, ResultStatus.REFUSED)
        self.assertEqual(self.state(), before)
        self.assertEqual(number_for(reference), number)
        invite(self.char1, self.char2, now=100)
        respond(self.char2, True, now=100)
        self.assertEqual(self.run_action(self.invocation(player=self.char2), self.char2).status, ResultStatus.SUCCESS)
        row.refresh_from_db()
        self.assertEqual(row.owner_object_id, self.char1.pk)

    def test_expired_protection_preserves_number_and_pays_current_caller(self):
        item = self.loot_item(deadline=99)
        reference = descriptor(item).reference
        number = number_for(reference)
        result = self.run_action(self.invocation(player=self.char2), self.char2)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        item.refresh_from_db()
        self.assertEqual(item.owner_object_id, self.char2.pk)
        self.assertEqual(number, 1)

    def test_source_decay_and_deleted_entry_never_redirect_old_reference(self):
        item = self.loot_item()
        selected = self.invocation()
        old = descriptor(item).reference
        self.source.reconcile(now=200)
        item.refresh_from_db()
        self.assertNotEqual(descriptor(item).reference, old)
        before = self.state()
        self.assertEqual(self.run_action(selected).status, ResultStatus.REFUSED)
        self.assertEqual(self.state(), before)

    def test_owner_reassignment_with_same_ground_scope_rejects_source_snapshot(self):
        item = self.loot_item()
        self.source.reconcile(now=200)
        item.refresh_from_db()
        old_reference = descriptor(item).reference
        selected = self.invocation("권총탄")
        from evennia import create_object
        from typeclasses.loot import DroppedLoot

        other = create_object(DroppedLoot, key="다른 바닥 전리품", location=self.char1.location)
        loot_service.populate_source(other, [])
        with world_change():
            api.move_item_tree(item, location_kind="world_loot", owner_object=other)
        item.refresh_from_db()
        # Room ground Scope와 UUID가 동일해도 원래 Source 소유자는 다르다.
        self.assertEqual(descriptor(item).reference, old_reference)
        before = self.state()
        self.assertEqual(self.run_action(selected).status, ResultStatus.REFUSED)
        self.assertEqual(self.state(), before)

    def test_deleted_uuid_cannot_select_replacement_with_same_definition(self):
        item = self.loot_item()
        selected = self.invocation()
        original = item.pk
        loot_service.pickup(self.source, self.entry(item), self.char1, 10, now=100)
        replacement = self.loot_item()
        self.assertNotEqual(replacement.pk, original)
        before = self.state()
        self.assertEqual(self.run_action(selected).status, ResultStatus.REFUSED)
        self.assertEqual(self.state(), before)

    def test_merged_entry_uuid_rejects_stale_action_without_taking_merge_target(self):
        first = self.loot_item(deadline=99)
        second = self.loot_item(deadline=99)
        loot_service.reconcile_claims(self.source, now=100)
        selected = self.invocation("시체에서 권총탄 1")
        reference = descriptor(second).reference
        api.merge_stack(first, second)
        before = self.state()
        self.assertEqual(self.run_action(selected).status, ResultStatus.REFUSED)
        self.assertEqual(self.state(), before)
        second.refresh_from_db()
        self.assertEqual((second.quantity, number_for(reference)), (20, 2))

    def test_unique_recipient_conflict_rolls_back_other_selected_awards(self):
        from world.content import ITEMS

        definition = deepcopy(ITEMS["bandage"])
        definition.update(stackable=False, max_stack=1, unique_per_owner=True)
        with patch.dict(ITEMS, {"invariant_unique": definition}):
            self.create("invariant_unique")
            self.loot_item("water", quantity=1)
            self.loot_item("invariant_unique", quantity=1)
            selected = self.invocation()
            before = self.state()
            self.assertNotEqual(self.run_action(selected).status, ResultStatus.SUCCESS)
            self.assertEqual(self.state(), before)

    def test_missing_assigned_recipient_rejects_whole_selection(self):
        self.loot_item()
        assigned = self.loot_item("water", quantity=1, assigned=self.char2)
        selected = self.invocation()
        before = self.state()
        from world.multiplayer import object_by_id

        with patch("typeclasses.loot.object_by_id",
                   side_effect=lambda identity: None if identity == self.char2.pk else object_by_id(identity)):
            self.assertEqual(self.run_action(selected).status, ResultStatus.REFUSED)
        self.assertEqual(self.state(), before)
        assigned.refresh_from_db()
        self.assertEqual(assigned.owner_object_id, self.source.pk)

    def test_second_currency_recipient_failure_restores_item_currency_claims_and_numbers(self):
        self.loot_item()
        self.currency()
        selected = self.invocation()
        before = self.state()
        with patch.object(self.char2, "save_profile", side_effect=RuntimeError("recipient failure")):
            self.assertEqual(self.run_action(selected).status, ResultStatus.ERROR)
        self.assertEqual(self.state(), before)
        self.output[self.char1.pk].assert_not_called()
        self.output[self.char2.pk].assert_not_called()
        self.char1.push_state.assert_not_called()
        self.char2.push_state.assert_not_called()

    def test_web_request_retransmission_has_one_payout_and_one_notification(self):
        self.currency()
        payload = self.payload(self.invocation("시체에서 5칩"))
        pz_action(self.sessions[self.char1.pk], payload)
        before = self.state()
        messages = self.output[self.char1.pk].call_count
        pz_action(self.sessions[self.char1.pk], payload)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.output[self.char1.pk].call_count, messages)
        self.assertEqual(self.balances(), (23, 22))

    def test_stale_web_quantity_snapshot_never_repeats_partial_payout(self):
        row = self.currency()
        payload = self.payload(self.invocation("시체에서 5칩"), "partial-first")
        pz_action(self.sessions[self.char1.pk], payload)
        before = self.state()
        pz_action(self.sessions[self.char1.pk], {**payload, "request_id": "partial-stale"})
        self.assertEqual(self.state(), before)
        row.refresh_from_db()
        self.assertEqual(row.quantity, 15)
        self.assertEqual(self.balances(), (23, 22))

    def test_simultaneous_players_share_single_server_lock_and_award_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        from django.db import connections

        item = self.loot_item(deadline=99)
        self.currency()
        selected = [self.invocation(player=player) for player in (self.char1, self.char2)]
        source_ref, item_ref = descriptor(self.source).reference, descriptor(item).reference
        before = sum(self.balances())
        barrier = Barrier(2)
        shared_connection = connections["default"]
        shared_connection.inc_thread_sharing()

        def attempt(player, invocation):
            # 공식 대상인 SQLite+단일 서버의 같은 연결을 실제 world_change RLock으로
            # 직렬화한다. 별도 서버/연결의 DB row-lock 동시성 검증을 주장하지 않는다.
            connections["default"] = shared_connection
            barrier.wait(timeout=10)
            return self.run_action(invocation, player).status

        try:
            with patch("world.loot_service.notify_pickup", wraps=loot_service.notify_pickup) as notify:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    pending = [pool.submit(attempt, player, invocation)
                               for player, invocation in zip((self.char1, self.char2), selected, strict=True)]
                    statuses = [future.result(timeout=20) for future in pending]
                notify.assert_called_once()
        finally:
            shared_connection.dec_thread_sharing()
        self.assertCountEqual(statuses, [ResultStatus.SUCCESS, ResultStatus.REFUSED])
        self.assertEqual(sum(self.balances()), before + 20)
        self.assertEqual(ItemEntity.objects.filter(location_kind="inventory", quantity=10).count(), 1)
        self.assertFalse(LootClaim.objects.exists())
        self.assertFalse(CurrencyLoot.objects.exists())
        self.assertFalse(CurrencyLootShare.objects.exists())
        self.assertEqual(number_for(source_ref), 1)
        self.assertIsNone(number_for(item_ref))

    def test_outer_rollback_discards_payout_notifications_and_refresh(self):
        self.loot_item()
        self.currency()
        selected = self.invocation()
        before = self.state()
        with self.assertRaises(RuntimeError), world_change():
            self.assertEqual(self.run_action(selected).status, ResultStatus.SUCCESS)
            self.output[self.char1.pk].assert_not_called()
            self.output[self.char2.pk].assert_not_called()
            self.char1.push_state.assert_not_called()
            self.char2.push_state.assert_not_called()
            raise RuntimeError("outer rollback")
        self.assertEqual(self.state(), before)
        self.output[self.char1.pk].assert_not_called()
        self.output[self.char2.pk].assert_not_called()
        self.char1.push_state.assert_not_called()
        self.char2.push_state.assert_not_called()

    def test_notifications_and_state_refresh_wait_for_outer_commit(self):
        self.loot_item()
        with world_change():
            self.assertEqual(self.run_action(self.invocation()).status, ResultStatus.SUCCESS)
            self.output[self.char1.pk].assert_not_called()
            self.char1.push_state.assert_not_called()
        self.char1.push_state.assert_called_once()
        self.output[self.char1.pk].assert_called_once()

    def test_protected_web_actions_do_not_expose_subject_or_quantity(self):
        item = self.loot_item(quantity=7)
        row = self.currency(shares={self.char1: 20})
        controls = source_controls(self.char2, now=100)[self.source.pk]
        serialized = str(controls["loot"])
        self.assertNotIn(str(item.pk), serialized)
        self.assertNotIn(str(row.pk), serialized)
        self.assertEqual(controls["loot"], [])
        self.assertIsNone(controls["take_action"])
