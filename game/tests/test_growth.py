from copy import deepcopy
from random import Random
from unittest.mock import Mock, patch

from commands.character import Abilities, Experience, Help, Skills
from commands.default_cmdsets import CharacterCmdSet, UnloggedinCmdSet
from commands.inventory import Equipment
from commands.skills import Allocate
from evennia import CmdSet, Command, create_object, search_tag
from evennia.commands.cmdparser import cmdparser as default_parser
from server.conf.cmdparser import cmdparser
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from typeclasses.interactables import (
    INTERACTABLES,
    AttributeTrainer,
    SkillTrainer,
    TrainingManager,
    action_objects,
    growth_controls,
)
from typeclasses.parties import invite, respond
from world import rules
from world.bootstrap import build_world
from world.multiplayer import world_change
from world.progression import ATTRIBUTES, SKILLS

from tests.base import WorldCommandTest


class GrowthIntegrationTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        self.enterContext(patch('typeclasses.explorers.time', return_value=100))
        self.enterContext(patch('world.skill_services.time', return_value=100))
        super().setUp()
        self.rooms = self.world_rooms()
        for player in (self.char1, self.char2):
            player.location = self.rooms['training_room']
            player.home = self.rooms['dock']
            player.push_state = Mock()
            self.enterContext(patch.object(player.sessions, 'count', return_value=1))
        for module in ('enemies', 'explorers', 'loot'):
            self.enterContext(patch(f'typeclasses.{module}.delay'))

    def command(self, text, player=None):
        player = player or self.char1
        with patch.object(player, 'msg') as output:
            player.execute_cmd(text)
        return '\n'.join(str(c.args[0]) for c in output.call_args_list if c.args)

    def trainable(self, level=50):
        self.char1.change(lambda p: p.update(xp=rules.xp_threshold(level)))

    def test_all_trainers_share_typeclasses_and_exact_data_ownership(self):
        skill_trainers = [obj for room in self.rooms.values() for obj in action_objects(room) if isinstance(obj, SkillTrainer)]
        attribute_trainers = [obj for room in self.rooms.values() for obj in action_objects(room) if isinstance(obj, AttributeTrainer)]
        self.assertEqual(len(skill_trainers), 8)
        self.assertEqual({obj.db.skill_id for obj in skill_trainers}, set(SKILLS))
        self.assertEqual({type(obj) for obj in skill_trainers}, {SkillTrainer})
        self.assertEqual(len(attribute_trainers), 4)
        self.assertEqual({obj.db.attribute_id for obj in attribute_trainers}, set(ATTRIBUTES))
        self.assertEqual({type(obj) for obj in attribute_trainers}, {AttributeTrainer})
        self.trainable()
        for obj in skill_trainers:
            self.char1.location = obj.location
            self.assertIn('R1에서 R2', self.command(SKILLS[obj.db.skill_id]['name'] + ' 배워'))
            self.assertIn('R2에서 R3', self.command(obj.key + '에게 ' + SKILLS[obj.db.skill_id]['name'] + ' 배워'))
        for obj in attribute_trainers:
            self.char1.location = obj.location
            name = ATTRIBUTES[obj.db.attribute_id]['name']
            self.assertIn('10에서 13', self.command(name + ' 3 배분'))
            self.assertIn('13에서 15', self.command(obj.key + '에게 ' + name + ' 2 배분'))
        self.assertEqual(self.char1.profile()['credits'], 20)

    def test_training_rejects_atomic_budget_cap_wrong_owner_combat_and_ambiguity(self):
        before = self.char1.profile()
        for command in ('강타 배워', '힘 5 배분', '체질 1 배분', '방호교관에게 강타 배워', '강타 5 배워'):
            self.command(command)
            self.assertEqual(self.char1.profile(), before, command)
        self.trainable(133)
        self.command('힘 20 배분')
        before = self.char1.profile()
        self.assertIn('상한', self.command('힘 1 배분'))
        self.assertEqual(self.char1.profile(), before)
        self.char1.change(lambda p: p.update(combat_target=999))
        before = self.char1.profile()
        self.assertIn('전투 중', self.command('강타 배워'))
        self.assertEqual(self.char1.profile(), before)
        self.char1.change(lambda p: p.update(combat_target=None))
        extra = create_object(SkillTrainer, key='다른 타격교관', location=self.rooms['training_room'])
        extra.db.skill_id = 'heavy'
        before = self.char1.profile()
        self.assertIn('명확하지', self.command('강타 배워'))
        self.assertEqual(self.char1.profile(), before)
        self.assertNotIn('heavy', growth_controls(self.char1))
        self.assertIn('R1에서 R2', self.command('타격교관에게 강타 배워'))
        self.char1.change(lambda p: (p.update(xp=rules.xp_threshold(133)), p['skills'].update(heavy=20)))
        before = self.char1.profile()
        self.assertIn('최고 Rank', self.command('타격교관에게 강타 배워'))
        self.assertEqual(self.char1.profile(), before)

    def test_reset_manager_only_returns_investments_preserves_deadlines_and_rolls_back(self):
        self.trainable()
        self.command('힘 3 배분')
        self.command('강타 배워')
        self.char1.change(lambda p: p['skill_ready_at'].update(breathing=130))
        self.char1.location = self.rooms['training_office']
        manager = search_tag('instructor', category='primal_interactable')[0]
        self.assertIsInstance(manager, TrainingManager)
        self.assertIn('모든 기술을 R1로 초기화', self.command('훈련관리관에게 기술 재분배'))
        self.assertEqual(self.char1.profile()['skills']['heavy'], 1)
        self.assertEqual(self.char1.profile()['attributes']['strength']['allocated'], 3)
        before = deepcopy(self.char1.profile())
        original = self.char1.save_profile
        def fail(profile):
            original(profile)
            raise RuntimeError('save failure')
        with patch.object(self.char1, 'save_profile', side_effect=fail):
            with self.assertRaises(RuntimeError):
                with world_change():
                    manager.perform_action(self.char1, '재분배', 'all')
        self.assertEqual(self.char1.profile(), before)
        self.command('전체 재훈련')
        self.assertEqual(self.char1.profile()['attributes']['strength']['allocated'], 0)
        self.assertEqual(self.char1.profile()['skill_ready_at']['breathing'], 130)
        self.assertEqual(self.char1.profile()['credits'], 20)
        self.assertIn('교관이 없다', self.command('강타 배워'))

    def test_bootstrap_preserves_objects_and_updates_legacy_instructor_typeclass(self):
        first = {obj.id for room in self.rooms.values() for obj in action_objects(room)}
        self.assertEqual(len(first), len(INTERACTABLES))
        self.command('힘 2 배분')
        before = self.char1.profile()
        for _ in range(2):
            build_world()
            self.assertEqual(first, {obj.id for room in self.rooms.values() for obj in action_objects(room)})
            self.assertEqual(self.char1.profile(), before)
        manager = search_tag('instructor', category='primal_interactable')[0]
        manager.db_typeclass_path = 'typeclasses.interactables.ActionObject'
        manager.save(update_fields=['db_typeclass_path'])
        build_world()
        self.assertEqual(search_tag('instructor', category='primal_interactable')[0].id, manager.id)
        self.assertEqual(manager.db_typeclass_path, 'typeclasses.interactables.TrainingManager')

    def test_migration_does_not_modify_shared_enemies_loot_or_party(self):
        from typeclasses.loot import Corpse, DroppedLoot
        from typeclasses.parties import party_for

        invite(self.char1, self.char2, now=100)
        respond(self.char2, True, now=100)
        party = party_for(self.char1)
        party_state = deepcopy(party.state())
        enemy = room_enemies(self.rooms['grass'])[0]
        enemy.db.hp = 13
        corpse = create_object(Corpse, key='보존 시체', location=enemy.location)
        corpse.db.loot = [{'item': 'scrap', 'quantity': 2}]
        dropped = create_object(DroppedLoot, key='보존 전리품', location=enemy.location)
        dropped.db.protection_until = 9876543210
        old = self.char1.profile()
        old.update(version=9, skills={'heavy': 3, 'guard': 3, 'firstaid': 3},
                   proficiencies={'medicine': {'xp': 123}}, xp=rules.xp_threshold(37))
        self.char1.db.profile = old
        migrated = self.char1.profile()
        self.char1.save_profile(migrated)
        self.assertEqual(self.char1.profile(), migrated)
        self.assertEqual(party_for(self.char1).state(), party_state)
        self.assertEqual(enemy.db.hp, 13)
        self.assertEqual(corpse.db.loot[0]['quantity'], 2)
        self.assertEqual(dropped.db.protection_until, 9876543210)

    def test_shared_suppression_refresh_and_insight_leave_cleanup(self):
        enemy = room_enemies(self.rooms['ridge'])[0]
        for player in (self.char1, self.char2):
            player.location = enemy.location
            player.change(lambda p: p.update(xp=rules.xp_threshold(50)))
            enemy.engage(player, now=100)
        self.char1.change(lambda p: (p['skills'].update(suppress=7), p.update(queued_action='suppress')))
        enemy.receive_attack(self.char1, 102.5, Random(1))
        self.assertEqual(enemy.db.suppressions[str(self.char1.id)]['attacks'], 3)
        self.char2.change(lambda p: p.update(queued_action='suppress'))
        enemy.receive_attack(self.char2, 102.5, Random(1))
        self.assertEqual(enemy.db.suppressions[str(self.char1.id)]['rank'], 7)
        self.assertEqual(enemy.db.suppressions[str(self.char2.id)]['rank'], 1)
        enemy.enemy_tick(now=102.5, rng=Random(1))
        self.assertEqual(enemy.db.suppressions[str(self.char1.id)]['attacks'], 2)
        self.assertNotIn(str(self.char2.id), enemy.db.suppressions)
        self.char1.change(lambda p: p.update(queued_action='insight'))
        enemy.receive_attack(self.char1, 105, Random(1))
        self.assertEqual(self.char1.profile()['insight']['target'], enemy.id)
        self.char1.location = self.rooms['dock']
        enemy.reconcile(now=106)
        self.assertIsNone(self.char1.profile()['insight'])
        self.assertNotIn('proficiencies', self.char1.profile())

    def test_party_healing_effective_amount_and_invalid_target_atomicity(self):
        self.char1.location = self.char2.location = self.rooms['grass']
        self.char2.change(lambda p: p.update(hp=58))
        before = deepcopy(self.char1.profile())
        self.assertIn('파티원', self.command(self.char2.key + ' 치료'))
        self.assertEqual(self.char1.profile(), before)
        invite(self.char1, self.char2, now=100)
        respond(self.char2, True, now=100)
        self.assertIn('HP 2', self.command(self.char2.key + ' 치료'))
        self.assertEqual(self.char2.profile()['hp'], 60)
        self.assertEqual(self.char1.profile()['mental'], 30)
        self.char2.location = self.rooms['dock']
        before = deepcopy(self.char1.profile())
        self.command(self.char2.key + ' 치료')
        self.assertEqual(self.char1.profile(), before)

    def test_queued_party_heal_replaces_one_attack_and_keeps_insight(self):
        self.char1.location = self.char2.location = self.rooms['ridge']
        invite(self.char1, self.char2, now=100)
        respond(self.char2, True, now=100)
        enemy = room_enemies(self.rooms['ridge'])[0]
        enemy.engage(self.char1, now=100)
        self.char1.change(lambda p: p.update(queued_action='insight'))
        enemy.receive_attack(self.char1, 102.5, Random(1))
        self.char2.change(lambda p: p.update(hp=40))
        before_hp = enemy.db.hp
        self.command(self.char2.key + ' 치료')
        enemy.receive_attack(self.char1, 105, Random(1))
        self.assertEqual(enemy.db.hp, before_hp)
        self.assertGreater(self.char2.profile()['hp'], 40)
        self.assertIsNotNone(self.char1.profile()['insight'])
        self.assertEqual(self.char1.profile()['mental'], 22)
        self.char1.leave_combat(now=106)
        self.assertIsNone(self.char1.profile()['insight'])

    def test_attack_save_failure_rolls_back_damage_and_support_resources(self):
        enemy = room_enemies(self.rooms['grass'])[0]
        self.char1.location = enemy.location
        enemy.engage(self.char1, now=100)
        enemy.db.hp = 1
        before = self.char1.profile()
        with patch.object(enemy, 'finish_death', side_effect=RuntimeError('death failed')):
            with self.assertRaises(RuntimeError):
                enemy.receive_attack(self.char1, now=102.5, rng=Random(1))
        self.assertEqual(self.char1.profile(), before)
        self.assertEqual(enemy.db.hp, 1)

    def test_insight_clears_on_enemy_movement_and_death(self):
        enemy = room_enemies(self.rooms['grass'])[0]
        self.char1.location = enemy.location
        enemy.engage(self.char1, now=100)
        self.char1.change(lambda p: p.update(queued_action='insight'))
        enemy.receive_attack(self.char1, 102.5, Random(1))
        self.assertIsNotNone(self.char1.profile()['insight'])
        enemy.move_to(self.rooms['trail'], quiet=True)
        self.assertIsNone(self.char1.profile()['insight'])
        self.assertIsNone(self.char1.profile()['combat_target'])
        self.char1.location = enemy.location
        enemy.engage(self.char1, now=110)
        enemy.db.hp = 1
        self.char1.change(lambda p: p.update(insight={'target': enemy.id, 'penetration': .25, 'bonus': .05}))
        enemy.receive_attack(self.char1, 112.5, Random(1))
        self.assertEqual(enemy.db.state, 'respawning')
        self.assertIsNone(self.char1.profile()['insight'])

    def test_queued_heal_revalidates_party_target_and_preserves_resources(self):
        enemy = room_enemies(self.rooms['ridge'])[0]
        self.char1.location = self.char2.location = enemy.location
        invite(self.char1, self.char2, now=100)
        respond(self.char2, True, now=100)
        self.char2.change(lambda p: p.update(hp=40))
        enemy.engage(self.char1, now=100)
        self.command(self.char2.key + ' 치료')
        self.char2.location = self.rooms['dock']
        before = self.char1.profile()
        enemy_hp = enemy.db.hp
        enemy.receive_attack(self.char1, 102.5, Random(1))
        after = self.char1.profile()
        self.assertEqual(after['mental'], before['mental'])
        self.assertEqual(after['skill_ready_at'], before['skill_ready_at'])
        self.assertEqual(after['player_round'], before['player_round'] + 1)
        self.assertEqual(enemy.db.hp, enemy_hp)
        self.assertEqual(self.char2.profile()['hp'], 40)

    def test_breathing_deadline_survives_reload_snapshot_and_reset(self):
        self.char1.change(lambda p: p.update(mental=0))
        self.assertIn('정신력 3', self.command('호흡'))
        self.assertEqual(self.char1.profile()['skill_ready_at']['breathing'], 130)
        saved = deepcopy(self.char1.profile())
        self.char1.db.profile = saved
        self.assertIn('30초', self.command('호흡'))
        self.assertEqual(self.char1.profile(), saved)
        self.char1.location = self.rooms['training_office']
        self.command('전체 재훈련')
        self.assertEqual(self.char1.profile()['skill_ready_at']['breathing'], 130)

    def test_telegraph_does_not_consume_a_second_suppression_attack(self):
        enemy = room_enemies(self.rooms['ridge'])[0]
        self.char1.location = enemy.location
        enemy.engage(self.char1, now=100)
        enemy.db.suppressions = {str(self.char1.id): {'rank': 7, 'reduction': .08, 'attacks': 3}}
        enemy.db.enemy_round = 1
        enemy.enemy_tick(now=102.5, rng=Random(1))
        self.assertEqual(enemy.db.suppressions[str(self.char1.id)]['attacks'], 2)


    def test_shortcuts_are_whole_input_only_and_engine_remains_default(self):
        cmdset = CharacterCmdSet(self.char1)
        for alias, key in (
            ("상", "점수"),
            ("능", "능력"),
            ("기", "기술"),
            ("장", "장비"),
            ("소", "가진거"),
        ):
            self.assertEqual(cmdparser(alias, cmdset, self.char1)[0][2].key, key)
        north = Command(key="북")
        cmdset.add(north)
        self.assertEqual(cmdparser("ㅂ", cmdset, self.char1)[0][2].key, "북")
        for text in ("ㅂ 말", "'ㅂ"):
            match = cmdparser(text, cmdset, self.char1)[0]
            self.assertEqual((match[2].key, match[1]), ("말", "ㅂ"))
        match = cmdparser("ㅂ 정비 기록 조사", cmdset, self.char1)[0]
        self.assertEqual(match[1], "ㅂ 정비 기록")
        self.assertFalse(cmdparser("배워 강타", cmdset, self.char1))
        self.assertEqual(cmdparser("절단마체테 무장", cmdset, self.char1)[0][1], "절단마체테")
        unlogged = UnloggedinCmdSet(self.char1)
        self.assertEqual(
            cmdparser("상", unlogged, self.char1), default_parser("상", unlogged, self.char1)
        )
        admin = CmdSet(self.char1)
        admin.add(Command(key="상"))
        admin.add(Allocate())
        self.assertEqual(cmdparser("상", admin, self.char1)[0][2].key, "상")

    def test_information_commands_and_help_registry(self):
        for command, heading in (
            (Abilities(), "능력"),
            (Skills(), "기술"),
            (Experience(), "경험치"),
            (Equipment(), "장비"),
            (Help(), "도움"),
        ):
            with patch.object(self.char1, "msg") as message:
                command.caller = self.char1
                command.run()
            output = message.call_args.args[0]
            self.assertEqual(output.kind, "sheet")
            self.assertIn(heading, output)

    def test_migration_does_not_modify_shared_objects_or_party(self):
        from evennia import create_object
        from typeclasses.loot import Corpse, DroppedLoot
        from typeclasses.parties import invite, party_for, respond

        invite(self.char1, self.char2)
        respond(self.char2, True)
        party = party_for(self.char1)
        enemy = room_enemies(self.rooms["grass"])[0]
        enemy.db.hp = 13
        corpse = create_object(Corpse, key="보존 시체", location=self.rooms["grass"])
        dropped = create_object(DroppedLoot, key="보존 전리품", location=self.rooms["grass"])
        corpse.db.loot = [{"item": "scrap", "quantity": 2}]
        dropped.db.protection_until = 9876543210
        state = deepcopy(party.state())
        for version in (1, 2):
            profile = self.char1.profile()
            profile["version"] = version
            for key in rules.growth_defaults():
                profile.pop(key)
            if version == 1:
                profile["encounter"] = {"enemy": "scavenger", "hp": 8}
            self.char1.db.profile = profile
            migrated = self.char1.profile()
            self.char1.save_profile(migrated)
            self.assertEqual(self.char1.profile(), migrated)
            self.assertEqual(party_for(self.char1).state(), state)
            self.assertEqual(enemy.db.hp, 13)
            self.assertEqual(corpse.db.loot[0]["quantity"], 2)
            self.assertEqual(dropped.db.protection_until, 9876543210)
