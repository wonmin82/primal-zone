"""Issue #48 FREEZE의 명령·멤버십·세션·전술 경계 검증."""


from types import SimpleNamespace
from unittest.mock import Mock, patch

from commands.help_pages import help_page
from commands.party import PARTY_COMMANDS
from commands.registry import COMMANDS
from evennia import create_object
from typeclasses.explorers import Explorer
from world import text as ft
from world.multiplayer import object_by_id
from world.rules import RuleError

from tests.base import GameCommandTest, WorldCommandTest
from tests.loot_entity_fixture import NativeLootTest


class PartyCommandContractTests(GameCommandTest):
    character_typeclass = Explorer

    def test_rt01_all_sixteen_commands_aliases_help_and_old_verbs_absent(self):
        from commands.vocabulary import V13_RUNTIME_NAMES, V14_PARTY_NAMES
        self.assertSetEqual(set(V13_RUNTIME_NAMES), {name for cls in COMMANDS if cls not in PARTY_COMMANDS
                                            for name in (cls.key, *cls.aliases)})
        self.assertEqual(V14_PARTY_NAMES, {name for cls in PARTY_COMMANDS for name in (cls.key, *cls.aliases)})
        expected = {
            "일행": ["무리", "그룹"], "일행모으기": ["그룹만들기", "그룹모으기"],
            "일행초청": ["그룹초청"], "일행합류": ["그룹가입"], "일행거절": [],
            "일행요청": ["그룹요청"], "일행허락": ["그룹허락"], "일행제외": [],
            "일행탈퇴": ["그룹탈퇴"], "일행리더": ["그룹리더"], "일행승계": ["그룹승계"],
            "일행해체": ["그룹해체"], "일행대화": ["무리말", "그룹대화", "무"],
            "일행공격": ["일공"], "일행방어": ["그룹방어"], "일행분배": [],
        }
        self.assertEqual({cls.key: set(cls.aliases) for cls in PARTY_COMMANDS},
                         {key: set(aliases) for key, aliases in expected.items()})
        self.assertFalse(any(name.startswith("파티") for cls in COMMANDS for name in (cls.key, *cls.aliases)))
        for cls in PARTY_COMMANDS:
            self.assertIn(cls, COMMANDS)
            self.assertEqual([title for title, _ in cls.help_sections],
                             ["사용법", "예시", "실행 규칙", "제한", "관련 도움말"])
            page = help_page(cls.key, COMMANDS)
            self.assertIsInstance(page, ft.Text)
            for alias in cls.aliases:
                self.assertEqual(str(help_page(alias, COMMANDS)), str(page))
            for name in (cls.key, *cls.aliases):
                for suffix in ("도움", "도움말"):
                    with patch.object(self.char1, "msg") as output:
                        self.char1.execute_cmd(name + " " + suffix)
                    self.assertTrue(any(cls.summary in str(call.args[0]) for call in output.call_args_list if call.args), name)

    def test_rt02_postfix_and_alias_preserve_arguments(self):
        from commands.default_cmdsets import CharacterCmdSet
        from server.conf.cmdparser import select_command

        cmdset = CharacterCmdSet()
        for value, key, args in (("철수 그룹초청", "일행초청", "철수"),
                                 ("확인 일행해체", "일행해체", "확인"),
                                 ("모여 주세요 무", "일행대화", "모여 주세요"),
                                 ("해제 1 그룹방어", "일행방어", "해제 1")):
            selection = select_command(value, cmdset, self.char1)
            self.assertEqual(len(selection.matches), 1, value)
            self.assertEqual(selection.matches[0][2].key, key)
            self.assertEqual(selection.matches[0][1], args)
        self.assertFalse(any(match[2].key == "일행해체"
                             for match in select_command("일행해체 확인", cmdset, self.char1).matches))


class PartyFixture(GameCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.enterContext(patch('typeclasses.explorers.delay'))
        self.enterContext(patch('typeclasses.enemies.delay'))
        self.sessions = {}
        self.people = [self.char1, self.char2] + [create_object(Explorer, key=f'구성원{i}', location=self.room1) for i in range(3)]
        for obj in self.people:
            self.set_online(obj)
            obj.push_state = Mock()
        self.enterContext(patch('typeclasses.parties.time', return_value=100))

    def set_online(self, obj, count=1):
        if obj.id not in self.sessions:
            self.sessions[obj.id] = []
            self.enterContext(patch.object(obj.sessions, 'all', side_effect=lambda obj=obj: self.sessions[obj.id]))
            self.enterContext(patch.object(obj.sessions, 'count', side_effect=lambda obj=obj: len(self.sessions[obj.id])))
        self.sessions[obj.id] = [SimpleNamespace(puppet=obj, logged_in=True, data_out=Mock(), protocol_key="telnet") for _ in range(count)]

    def pair(self):
        from typeclasses.parties import invite, respond
        party = invite(self.char1, self.char2, now=100)
        respond(self.char2, True, now=101)
        return party



class PartyMembershipTests(PartyFixture):
    def test_rt03_rt04_creation_permissions_and_pending_cleanup(self):
        from typeclasses.parties import Party, create_party, invite, party_for, request_join
        party = create_party(self.char1, now=100)
        with self.assertRaises(RuleError):
            create_party(self.char1)
        request_join(self.char2, self.char1, now=100)
        invite(self.char1, self.char2, now=100)
        own = create_party(self.char2, now=101)
        self.assertNotIn(self.char2.id, party.state()['invitations'])
        self.assertNotIn(self.char2.id, party.state()['join_requests'])
        self.assertEqual(party_for(self.char2), own)
        self.assertEqual(Party.objects.count(), 2)
        for obj in (self.char1, self.char2):
            with self.assertRaises(RuleError):
                invite(self.char1, obj)
        self.set_online(self.people[2], 0)
        with self.assertRaises(RuleError):
            invite(self.char1, self.people[2])

    def test_rt05_rt07_rt08_rt09_rt10_ttl_and_independent_requests(self):
        from typeclasses.parties import create_party, invitation_for, invite, request_join, respond
        party = create_party(self.char1, now=100)
        request_join(self.char2, self.char1, now=100)
        request_join(self.char2, self.char1, now=110)
        invite(self.char1, self.char2, now=100)
        invite(self.char1, self.char2, now=110)
        self.assertEqual(party.state()['invitations'][self.char2.id]['expires_at'], 160)
        self.assertEqual(party.state()['join_requests'][self.char2.id]['expires_at'], 160)
        self.set_online(self.char2, 0)
        with self.assertRaises(RuleError):
            party.answer_request(self.char1, self.char2, True, now=159)
        self.assertIn(self.char2.id, party.state()['join_requests'])
        self.set_online(self.char2)
        party.answer_request(self.char1, self.char2, True, now=159.999)
        self.assertFalse(party.state()['invitations'])
        self.assertFalse(party.state()['join_requests'])
        invite(self.char1, self.people[2], now=100)
        self.assertEqual(invitation_for(self.people[2], now=160), (None, None))
        with self.assertRaises(RuleError):
            respond(self.people[2], True, now=160)

    def test_rt06_rt11_rt27_invite_survives_offline_and_transfer(self):
        from typeclasses.parties import invite, respond
        party = self.pair()
        invite(self.char1, self.people[2], now=102)
        party.transfer(self.char1, self.char2)
        self.set_online(self.char2, 0)
        respond(self.people[2], True, now=103)
        self.assertEqual(party.state()['members'], [obj.id for obj in self.people[:3]])
        party.remove_member(self.char2, now=104)
        self.assertEqual(party.state()['leader'], self.char1.id)

    def test_rt04_rt07_capacity_rechecked_and_requests_single(self):
        from typeclasses.parties import create_party, invite, request_join, respond
        party = self.pair()
        for obj in self.people[2:]:
            invite(self.char1, obj, now=100)
        for obj in self.people[2:4]:
            respond(obj, True, now=101)
        with self.assertRaises(RuleError):
            respond(self.people[4], True, now=102)
        self.assertEqual(len(party.state()['members']), 4)
        other = create_party(self.people[4])
        self.assertNotEqual(party.id, other.id)
        party.remove_member(self.char1, self.char2)
        request_join(self.char2, self.char1, now=103)
        with self.assertRaises(RuleError):
            request_join(self.char2, self.people[4], now=104)
        party.answer_request(self.char1, self.char2, False, now=104)
        self.assertFalse(party.state()['join_requests'])

    def test_rt13_rt14_dissolve_snapshot_ttl_and_stale_target(self):
        from typeclasses.parties import invite, respond
        party = self.pair()
        self.char2.change(lambda p: p.update(combat_target=999999))
        party.dissolve(self.char1, now=100)
        with self.assertRaises(RuleError):
            party.dissolve(self.char1, True, now=160)
        party.dissolve(self.char1, now=170)
        invite(self.char1, self.people[2], now=170)
        respond(self.people[2], True, now=171)
        with self.assertRaises(RuleError):
            party.dissolve(self.char1, True, now=172)
        party.dissolve(self.char1, now=180)
        identity = party.id
        party.dissolve(self.char1, True, now=239.999)
        self.assertIsNone(object_by_id(identity))
        self.assertTrue(all(obj.db.party_id is None for obj in self.people[:3]))

    def test_rt07_rt08_ambiguous_request_target_and_reject_modes(self):
        from typeclasses.parties import create_party, invite, request_join
        party = create_party(self.char1)
        other = create_party(self.people[2])
        self.char1.key = self.people[2].key = '동명리더'
        self.char2.execute_cmd('동명리더 일행요청')
        self.assertFalse(party.state()['join_requests'])
        self.assertFalse(other.state()['join_requests'])
        request_join(self.char2, self.char1)
        invite(self.char1, self.char2)
        self.char2.execute_cmd('일행거절')
        self.assertFalse(party.state()['invitations'])
        self.assertIn(self.char2.pk, party.state()['join_requests'])
        self.char2.execute_cmd(f'{self.char2.key} 일행거절')
        self.assertIn(self.char2.pk, party.state()['join_requests'])
        self.char1.execute_cmd(f'{self.char2.key} 일행거절')
        self.assertFalse(party.state()['join_requests'])

    def test_rt13_expired_invite_keeps_confirmation_but_leader_change_invalidates(self):
        from typeclasses.parties import invite
        party = self.pair()
        invite(self.char1, self.people[2], now=90)
        party.dissolve(self.char1, now=100)
        party.reconcile(now=150)
        self.assertTrue(self.char1.ndb.party_dissolve_request)
        party.transfer(self.char1, self.char2)
        with self.assertRaises(RuleError):
            party.dissolve(self.char2, True, now=151)
        party.dissolve(self.char2, now=151)
        party.remove_member(self.char1, now=152)
        with self.assertRaises(RuleError):
            party.dissolve(self.char2, True, now=153)
        party.dissolve(self.char2, now=153)
        identity = party.pk
        party.dissolve(self.char2, True, now=154)
        with self.assertRaises(RuleError):
            party.dissolve(self.char2, True, now=155)
        self.assertIsNone(object_by_id(identity))

    def test_rt42_legacy_defaults_preserve_valid_data(self):
        party = self.pair()
        state = party.state()
        state['round_robin_cursor'] = 7
        for field in ('tactics', 'join_requests', 'leader_offline_since'):
            state.pop(field)
        party.db.state = state
        identity = party.id
        party.reconcile(now=102)
        self.assertEqual(party.id, identity)
        self.assertEqual(party.state()['round_robin_cursor'], 7)
        self.assertEqual(party.state()['members'], [self.char1.id, self.char2.id])
        self.assertEqual(party.state()['tactics'], {'defender_id': None})

    def test_rt16_creation_and_join_rollback_restore_attributes(self):
        from typeclasses.parties import Party, create_party, invite, respond
        with patch('typeclasses.parties.clear_pending', side_effect=RuntimeError('storage')):
            with self.assertRaises(RuntimeError):
                create_party(self.char1)
        self.assertEqual(Party.objects.count(), 0)
        self.assertIsNone(self.char1.db.party_id)
        party = invite(self.char1, self.char2)
        with patch('typeclasses.parties.clear_pending', side_effect=RuntimeError('storage')):
            with self.assertRaises(RuntimeError):
                respond(self.char2, True)
        self.assertEqual(party.state()['members'], [self.char1.id])
        self.assertIsNone(self.char2.db.party_id)


class PartyLootRightsTests(NativeLootTest):
    def setUp(self):
        super().setUp()
        for obj in (self.char1, self.char2):
            self.connect_character(obj)
        self.enterContext(patch('typeclasses.parties.time', return_value=100))

    def test_rt15_native_and_legacy_personal_rights_survive_dissolution(self):
        from typeclasses.parties import invite, respond
        from world import loot_service
        from world.loot_entities.models import CurrencyLoot, LootClaim
        party = invite(self.char1, self.char2)
        respond(self.char2, True)
        root = self.loot_item(party=party, assigned=self.char2)
        currency = loot_service.create_currency(self.source, 20, reserved_party=party,
                                               protection_until=300, shares={self.char1: 10, self.char2: 10})
        from typeclasses.loot import Corpse
        legacy = create_object(Corpse, key='구형 시체', location=self.char1.location)
        legacy.db.entries = [{'kind': 'item', 'id': 'bandage', 'quantity': 1,
                              'assigned_player': self.char2.pk, 'reserved_party': party.pk, 'protection_until': 300}]
        party.dissolve(self.char1, now=100)
        party.dissolve(self.char1, True, now=101)
        claim = LootClaim.objects.get(item_entity=root)
        self.assertEqual((claim.assigned_player_id, claim.reserved_party_id, claim.protection_until), (self.char2.pk, None, 300))
        row = CurrencyLoot.objects.get(pk=currency.pk)
        self.assertIsNone(row.reserved_party_id)
        self.assertEqual(dict(row.shares.values_list('player_id', 'remaining_amount')), {self.char1.pk: 10, self.char2.pk: 10})
        self.assertEqual(legacy.db.entries[0]['assigned_player'], self.char2.pk)
        self.assertEqual(legacy.db.entries[0]['protection_until'], 300)
        self.assertIsNone(legacy.db.entries[0]['reserved_party'])

    def test_rt15_rt16_unallocated_protected_rights_stop_deletion_and_roll_back(self):
        from typeclasses.parties import invite, respond
        from world.loot_entities.models import LootClaim
        party = invite(self.char1, self.char2)
        respond(self.char2, True)
        root = self.loot_item(party=party, assigned=self.char2)
        LootClaim.objects.filter(item_entity=root).update(assigned_player=None, reserved_player=None)
        before = self.all_state()
        party.dissolve(self.char1, now=100)
        with self.assertRaises(RuleError):
            party.dissolve(self.char1, True, now=101)
        self.assertEqual(self.all_state(), before)
        self.assertEqual(party.state()['members'], [self.char1.pk, self.char2.pk])
        self.assertEqual(self.char1.db.party_id, party.pk)

    def test_rt15_rt16_expired_and_legacy_currency_rights_without_shared_recovery(self):
        from typeclasses.loot import Corpse, can_take_entry
        from typeclasses.parties import invite, respond
        from world.loot_entities.models import LootClaim
        party = invite(self.char1, self.char2)
        respond(self.char2, True)
        root = self.loot_item(party=party, assigned=self.char2, deadline=99)
        LootClaim.objects.filter(item_entity=root).update(assigned_player=None, reserved_player=None)
        legacy = create_object(Corpse, key='구형 지분 시체', location=self.char1.location)
        legacy.db.entries = [
            {'kind':'currency','id':'credits','quantity':8,'reserved_party':party.pk,'protection_until':300,
             'eligible_players':[self.char1.pk,self.char2.pk],'remaining_shares':{self.char1.pk:4,self.char2.pk:4}},
            {'kind':'item','id':'bandage','quantity':1,'reserved_party':party.pk,'protection_until':300,
             'assigned_player':self.char2.pk}]
        party.dissolve(self.char1, now=100)
        party.dissolve(self.char1, True, now=101)
        claim = LootClaim.objects.get(item_entity=root)
        self.assertEqual((claim.reserved_party_id, claim.protection_until), (None, 99))
        currency, item = list(legacy.db.entries)
        self.assertEqual((currency['quantity'], dict(currency['remaining_shares'])), (8,{self.char1.pk:4,self.char2.pk:4}))
        self.assertTrue(can_take_entry(currency, self.char1, 101))
        self.assertFalse(can_take_entry(item, self.char1, 101))
        self.assertTrue(can_take_entry(item, self.char2, 101))

    def test_rt16_partial_currency_shares_stop_deletion_without_reallocation(self):
        from typeclasses.parties import invite, respond
        from world import loot_service
        party = invite(self.char1, self.char2)
        respond(self.char2, True)
        currency = loot_service.create_currency(self.source,20,reserved_party=party,protection_until=300,
                                               shares={self.char1:10,self.char2:10})
        currency.shares.filter(player=self.char2).update(remaining_amount=9)
        before = self.all_state()
        party.dissolve(self.char1, now=100)
        with self.assertRaises(RuleError):
            party.dissolve(self.char1, True, now=101)
        self.assertEqual(self.all_state(), before)
        self.assertIsNotNone(object_by_id(party.pk))


class PartyChatTests(PartyFixture):
    def test_rt28_rt29_private_members_cross_rooms_and_validation(self):
        from world import private_messaging
        party = self.pair()
        self.char2.location = self.room2
        private = private_messaging.state(self.char2)
        private['blocked_character_ids'] = [self.char1.pk]
        self.char2.attributes.add(private_messaging.ATTRIBUTE, private)
        before = private_messaging.state(self.char2)
        for obj in self.people:
            obj.msg = Mock()
        party.chat(self.char1, '모여 주세요')
        messages = [obj.msg.call_args.args[0] for obj in self.people[:2]]
        self.assertEqual([str(value) for value in messages], [f'[일행] {self.char1.key}: 모여 주세요'] * 2)
        self.assertTrue(all(isinstance(value, ft.Text) and value.kind == 'chat' for value in messages))
        self.assertEqual(private_messaging.state(self.char2), before)
        self.assertTrue(all(not obj.msg.called for obj in self.people[2:]))
        for body in ('', 'x' * 301, 'bad\x1b[31m', 'bad\x00'):
            with self.assertRaises(RuleError):
                party.chat(self.char1, body)

    def test_rt30_delivery_rechecks_departed_recipient_and_sender(self):
        party = self.pair()
        callbacks = []
        with patch('typeclasses.parties.after_change', side_effect=callbacks.append):
            party.chat(self.char1, '윤대장에게 수락')
        party.remove_member(self.char2)
        for obj in self.people:
            obj.msg = Mock()
        callbacks[0]()
        self.assertTrue(self.char1.msg.called)
        self.assertFalse(self.char2.msg.called)
        self.assertIsNone(self.char1.ndb.npc_dialogue_context)
        self.char1.msg.reset_mock()
        identity = party.pk
        party.remove_member(self.char1)
        self.char1.msg.reset_mock()
        self.assertIsNone(object_by_id(identity))
        callbacks[0]()
        self.assertFalse(self.char1.msg.called)


class PartySuccessionTests(PartyFixture):
    def test_rt25_stale_competing_succession_rechecks_current_leader_once(self):
        from typeclasses.parties import invite, respond
        party = self.pair()
        invite(self.char1, self.people[2], now=100)
        respond(self.people[2], True, now=100)
        self.set_online(self.char1, 0)
        party.reconcile_leader(now=100)
        for obj in self.people:
            obj.msg = Mock()
        party.succeed(self.char2, now=700)
        with self.assertRaises(RuleError):
            party.succeed(self.people[2], automatic=True, now=700)
        self.assertEqual(sum('승계했습니다' in str(call.args[0]) for call in self.char2.msg.call_args_list if call.args), 1)
        party.transfer(self.char2, self.people[2])
        party.reconcile_leader(now=1000)
        self.assertEqual(party.state()['leader'], self.people[2].pk)

    def test_rt17_rt18_immediate_and_online_rejection(self):
        party = self.pair()
        with self.assertRaises(RuleError):
            party.succeed(self.char2, now=102)
        self.set_online(self.char1, 0)
        self.assertTrue(party.succeed(self.char2, now=102))
        self.assertEqual(party.state()['leader'], self.char2.pk)
        self.set_online(self.char1)
        party.reconcile_leader(now=1000)
        self.assertEqual(party.state()['leader'], self.char2.pk)
        with self.assertRaises(RuleError):
            party.succeed(self.char1)

    def test_rt19_rt20_rt25_tick_boundary_order_and_stale_recheck(self):
        from typeclasses.parties import invite, respond
        party = self.pair()
        invite(self.char1, self.people[2], now=101)
        respond(self.people[2], True, now=102)
        self.set_online(self.char1, 0)
        party.reconcile_leader(now=200)
        party.reconcile_leader(now=799.999)
        self.assertEqual(party.state()['leader'], self.char1.pk)
        party.reconcile_leader(now=800)
        self.assertEqual(party.state()['leader'], self.char2.pk)
        with self.assertRaises(RuleError):
            party.succeed(self.people[2])

    def test_rt21_rt22_no_candidate_then_member_or_leader_reconnect(self):
        from typeclasses.parties import connection_changed
        party = self.pair()
        self.set_online(self.char1, 0)
        self.set_online(self.char2, 0)
        party.reconcile_leader(now=200)
        party.reconcile_leader(now=800)
        self.assertEqual(party.state()['leader'], self.char1.pk)
        self.set_online(self.char1)
        connection_changed(self.char1, now=801)
        self.assertIsNone(party.state()['leader_offline_since'])
        self.set_online(self.char1, 0)
        party.reconcile_leader(now=900)
        self.set_online(self.char2)
        connection_changed(self.char2, now=1500)
        self.assertEqual(party.state()['leader'], self.char2.pk)

    def test_rt23_reload_multisession_and_unpuppet_event(self):
        from evennia.server.models import ServerConfig
        from typeclasses.parties import connection_changed
        party = self.pair()
        self.set_online(self.char1, 2)
        self.sessions[self.char1.pk].pop()
        connection_changed(self.char1, now=200)
        self.assertIsNone(party.state()['leader_offline_since'])
        ServerConfig.objects.conf('server_restart_mode', 'reload')
        self.set_online(self.char1, 0)
        party.reconcile_leader(now=300)
        self.assertIsNone(party.state()['leader_offline_since'])
        self.set_online(self.char1)
        ServerConfig.objects.conf('server_restart_mode', delete=True)
        party.reconcile_leader(now=400)
        self.assertIsNone(party.state()['leader_offline_since'])
        self.set_online(self.char1, 0)
        with patch('typeclasses.parties.time', return_value=500):
            self.char1.at_post_unpuppet(self.account)
        self.assertEqual(party.state()['leader_offline_since'], 500)

    def test_rt24_restart_persistent_time_missing_field_and_scheduler(self):
        from world.lifecycle import reconcile_world
        party = self.pair()
        self.set_online(self.char1, 0)
        state = party.state()
        state.pop('leader_offline_since')
        party.db.state = state
        reconcile_world(now=200, restart=True)
        self.assertEqual(party.state()['leader_offline_since'], 200)
        self.assertEqual(object_by_id(party.pk).state()['leader_offline_since'], 200)
        reconcile_world(now=799.999, restart=True)
        self.assertEqual(party.state()['leader'], self.char1.pk)
        reconcile_world(now=804)
        self.assertEqual(party.state()['leader'], self.char2.pk)

    def test_rt26_rt27_confirmation_and_party_data_preserved(self):
        from typeclasses.parties import invite, request_join
        party = self.pair()
        invite(self.char1, self.people[2], now=100)
        request_join(self.people[3], self.char1, now=100)
        state = party.state()
        state['round_robin_cursor'] = 5
        state['tactics']['defender_id'] = self.char1.pk
        party.db.state = state
        party.dissolve(self.char1, now=100)
        self.set_online(self.char1, 0)
        party.succeed(self.char2, now=101)
        after = party.state()
        for field in ('members', 'invitations', 'join_requests', 'loot_mode', 'round_robin_cursor', 'tactics', 'created_at'):
            self.assertEqual(after[field], state[field], field)
        self.assertIsNone(self.char1.ndb.party_dissolve_request)


class PartyCombatFixture(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.enterContext(patch('world.lifecycle.time', return_value=100))
        from typeclasses.enemies import room_enemies
        self.rooms = self.world_rooms()
        self.people = [self.char1, self.char2] + [create_object(Explorer, key=f'전술탐사자{i}') for i in range(3)]
        for obj in self.people:
            obj.location = self.rooms['grass']
            self.connect_character(obj)
            obj.push_state = Mock()
            obj.msg = Mock()
        for module in ('enemies', 'explorers', 'parties', 'loot'):
            self.enterContext(patch(f'typeclasses.{module}.delay')) if module != 'parties' else None
            self.enterContext(patch(f'typeclasses.{module}.time', return_value=100))
        self.enemy = room_enemies(self.rooms['grass'])[0]

    def pair(self):
        from typeclasses.parties import invite, respond
        party = invite(self.char1, self.char2)
        respond(self.char2, True)
        return party


class PartyAttackTests(PartyCombatFixture):
    def test_rt03_rt04_existing_combat_invite_and_new_combat_party_denied(self):
        from typeclasses.parties import Party, create_party, invite
        party = self.pair()
        self.enemy.engage(self.char1, now=100)
        invite(self.char1, self.people[2], now=101)
        self.assertIn(self.people[2].pk, party.state()['invitations'])
        self.people[3].change(lambda p: p.update(combat_target=self.enemy.pk))
        self.enemy.db.combatants = [*self.enemy.db.combatants, self.people[3].pk]
        before = Party.objects.count()
        with self.assertRaises(RuleError):
            create_party(self.people[3], now=101)
        with self.assertRaises(RuleError):
            invite(self.people[3], self.people[4], now=101)
        self.assertEqual(Party.objects.count(), before)

    def test_rt31_rt32_rt34_partial_attack_preserves_existing_schedule(self):
        from typeclasses.parties import invite, respond
        party = self.pair()
        for obj in self.people[2:4]:
            invite(self.char1, obj)
            respond(obj, True)
        self.enemy.engage(self.char2, now=100)
        before = dict(self.char2.profile())
        self.char1.change(lambda p: p.update(combat_target=999999))
        self.people[3].location = self.rooms['dock']
        enemy_hp = self.enemy.db.hp
        result = party.attack(self.char1, self.enemy)
        self.assertEqual(result['new'], [self.people[2].key])
        self.assertEqual(result['existing'], [self.char2.key])
        self.assertEqual(len(result['skipped']), 2)
        self.assertEqual(dict(self.char2.profile()), before)
        self.assertEqual(self.enemy.db.hp, enemy_hp)
        self.assertEqual(self.people[2].profile()['next_attack_at'], 102.5)
        self.assertEqual(self.people[2].profile()['queued_action'], 'attack')
        self.assertEqual(self.people[2].profile()['xp'], 0)

    def test_rt33_all_existing_none_eligible_and_runtime_error(self):
        party = self.pair()
        first = party.attack(self.char1, self.enemy)
        self.assertEqual(first['new'], [self.char1.key, self.char2.key])
        before = [(obj.profile()['next_attack_at'], obj.ndb.combat_task) for obj in self.people[:2]]
        repeat = party.attack(self.char1, self.enemy)
        self.assertEqual(repeat['existing'], first['new'])
        self.assertEqual([(obj.profile()['next_attack_at'], obj.ndb.combat_task) for obj in self.people[:2]], before)
        for obj in self.people[:2]:
            obj.leave_combat(now=100)
            obj.change(lambda p: p.update(hp=0))
        with self.assertRaises(RuleError):
            party.attack(self.char1, self.enemy)
        for obj in self.people[:2]:
            obj.change(lambda p: p.update(hp=60))
        with patch.object(self.char2, 'start_combat', side_effect=RuntimeError('database')):
            with self.assertRaises(RuntimeError):
                party.attack(self.char1, self.enemy)
        self.assertEqual(self.char1.profile()['combat_target'], self.enemy.pk)
        self.assertIsNone(self.char2.profile()['combat_target'])
        self.assertIn('후속 참가 처리를 중단', str(self.char1.msg.call_args.args[0]))

    def test_rt31_rt35_leader_permission_visibility_and_other_claim(self):
        party = self.pair()
        with self.assertRaises(RuleError):
            party.attack(self.char2, self.enemy)
        self.enemy.engage(self.people[2], now=100)
        with self.assertRaises(RuleError):
            party.attack(self.char1, self.enemy)
        self.assertEqual(list(self.enemy.db.combatants), [self.people[2].pk])
        with patch('world.observation.can_perceive', return_value=False):
            with self.assertRaises(RuleError):
                party.attack(self.char1, self.enemy)

    def test_rt13_dissolve_rejects_real_combat_at_both_steps(self):
        party = self.pair()
        self.enemy.engage(self.char2, now=100)
        with self.assertRaises(RuleError):
            party.dissolve(self.char1, now=100)
        self.char2.leave_combat(now=100)
        party.dissolve(self.char1, now=100)
        self.enemy.engage(self.char2, now=100)
        with self.assertRaises(RuleError):
            party.dissolve(self.char1, True, now=101)


class PartyDefenseTests(PartyCombatFixture):
    def test_rt36_rt37_offline_persistent_assignment_control_and_idempotency(self):
        party = self.pair()
        with patch.object(self.char2.sessions, 'all', return_value=[]), patch.object(self.char2.sessions, 'count', return_value=0):
            party.set_defender(self.char1, self.char2)
        self.assertEqual(party.state()['tactics']['defender_id'], self.char2.pk)
        before = party.state()
        party.set_defender(self.char1, self.char2)
        self.assertEqual(party.state(), before)
        with self.assertRaises(RuleError):
            party.set_defender(self.char2, self.char1)
        self.char2.key = '해제'
        self.char1.execute_cmd('해제 1 일행방어')
        self.assertEqual(party.state()['tactics']['defender_id'], self.char2.pk)
        self.char1.execute_cmd('해제 일행방어')
        self.assertIsNone(party.state()['tactics']['defender_id'])
        party.set_defender(self.char1, None)
        self.assertIsNone(party.state()['tactics']['defender_id'])

    def test_rt38_enemy_tick_redirects_without_threat_damage_or_interval_change(self):
        from random import Random
        party = self.pair()
        party.attack(self.char1, self.enemy)
        party.set_defender(self.char1, self.char2)
        self.enemy.db.threat = {self.char1.pk: 20, self.char2.pk: 1}
        hp = [obj.profile()['hp'] for obj in self.people[:2]]
        with patch('world.rules.enemy_attack', wraps=__import__('world.rules', fromlist=['enemy_attack']).enemy_attack) as attack:
            self.enemy.enemy_tick(now=102.5, rng=Random(2))
        self.assertEqual(self.char1.profile()['hp'], hp[0])
        self.assertLess(self.char2.profile()['hp'], hp[1])
        self.assertEqual(dict(self.enemy.db.threat), {self.char1.pk: 20, self.char2.pk: 1})
        self.assertEqual(self.enemy.db.next_attack_at, 105)
        self.assertEqual(attack.call_count, 1)

    def test_rt39_solo_and_other_party_priority_not_hijacked(self):
        from typeclasses.parties import create_party, invite, respond
        party = self.pair()
        party.set_defender(self.char1, self.char2)
        # 공개 적은 여러 일행이 참여할 수 있다. AI의 기본 대상 기준만 검사한다.
        self.enemy.db.claim = None
        self.enemy.db.combatants = [obj.pk for obj in self.people[:4]]
        for obj in self.people[:4]:
            obj.change(lambda p: p.update(combat_target=self.enemy.pk))
        self.assertEqual(party.defense_target(self.enemy, self.people[2]), self.people[2])
        self.people[2].change(lambda p: p.update(combat_target=None))
        self.enemy.db.combatants = [obj.pk for obj in self.people[:2]]
        other = create_party(self.people[2])
        self.people[2].change(lambda p: p.update(combat_target=self.enemy.pk))
        self.enemy.db.combatants = [obj.pk for obj in self.people[:4]]
        invite(self.people[2], self.people[3])
        self.people[3].change(lambda p: p.update(combat_target=None))
        respond(self.people[3], True)
        self.people[3].change(lambda p: p.update(combat_target=self.enemy.pk))
        other.set_defender(self.people[2], self.people[3])
        self.assertEqual(other.defense_target(self.enemy, self.people[2]), self.people[3])
        self.assertEqual(party.defense_target(self.enemy, self.people[2]), self.people[2])

    def test_rt40_rt41_effect_inactive_keeps_assignment_and_departure_clears(self):
        party = self.pair()
        party.set_defender(self.char1, self.char2)
        party.attack(self.char1, self.enemy)
        self.char2.leave_combat(now=100)
        self.assertEqual(party.defense_target(self.enemy, self.char1), self.char1)
        self.assertEqual(party.state()['tactics']['defender_id'], self.char2.pk)
        self.char2.location = self.rooms['dock']
        self.char2.at_server_shutdown()
        self.assertEqual(object_by_id(party.pk).state()['tactics']['defender_id'], self.char2.pk)
        self.char2.location = self.rooms['grass']
        self.char2.start_combat(self.enemy)
        self.assertEqual(party.defense_target(self.enemy, self.char1), self.char2)
        party.transfer(self.char1, self.char2)
        self.assertEqual(party.state()['tactics']['defender_id'], self.char2.pk)
        party.remove_member(self.char2)
        self.assertIsNone(party.state()['tactics']['defender_id'])

    def test_rt41_broken_deleted_defender_cleaned_without_reassigning(self):
        party = self.pair()
        state = party.state()
        state['tactics']['defender_id'] = 999999
        party.db.state = state
        party.reconcile(now=100)
        self.assertIsNone(party.state()['tactics']['defender_id'])
