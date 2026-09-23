from copy import deepcopy
from random import Random
from unittest.mock import Mock, patch

from commands.character import Abilities, Experience, Help, Skills
from commands.default_cmdsets import CharacterCmdSet, UnloggedinCmdSet
from commands.inventory import Equipment
from commands.skills import Allocate, Learn, Retrain
from commands.world_actions import resolve_action
from evennia import CmdSet, Command
from evennia.commands.cmdparser import cmdparser as default_parser
from evennia.utils.test_resources import EvenniaCommandTest
from server.conf.cmdparser import cmdparser
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from typeclasses.interactables import action_objects, instructor_for
from world import rules
from world.bootstrap import build_world


class GrowthIntegrationTests(EvenniaCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = build_world()
        for player in (self.char1, self.char2):
            player.location = self.rooms["dock"]
            player.home = self.rooms["dock"]
            player.push_state = Mock()
        self.enterContext(patch("typeclasses.enemies.delay"))
        self.enterContext(patch("typeclasses.explorers.delay"))

    def test_instructor_dispatch_learning_allocation_and_retraining(self):
        self.call(Allocate(), "체질 4", "체질에 4 포인트")
        self.assertEqual(self.char1.profile()["hp"], 60)
        self.assertEqual(rules.stats(self.char1.profile())["max_hp"], 76)
        self.call(Learn(), "강타", "강타 Rank 2 학습 완료.")
        self.assertEqual(self.char1.profile()["credits"], 16)
        self.call(Retrain(), "특성", "재훈련 완료.")
        self.assertEqual(self.char1.profile()["skills"]["heavy"], 2)
        self.call(Retrain(), "기술", "재훈련 완료.")
        self.assertEqual(self.char1.profile()["skills"]["heavy"], 1)
        self.call(Allocate(), "힘 2", "힘에 2 포인트")
        self.call(Learn(), "방어", "방어 Rank 2")
        self.call(Retrain(), "전체", "재훈련 완료.")
        self.assertEqual(rules.point_pools(self.char1.profile())["attribute_points"], 4)
        self.assertEqual(rules.point_pools(self.char1.profile())["skill_points"], 2)

    def test_training_rejects_wrong_location_combat_and_remote_npc(self):
        instructor = instructor_for(self.char1)
        self.char1.location = self.rooms["grass"]
        before = self.char1.profile()
        with self.assertRaises(rules.RuleError):
            resolve_action(self.char1, "배워")
        with self.assertRaises(rules.RuleError):
            instructor.perform_action(self.char1, "재분배", "all")
        self.char1.location = self.rooms["dock"]
        self.char1.change(lambda p: p.update(combat_target=999))
        before = self.char1.profile()
        with self.assertRaises(rules.RuleError):
            instructor.perform_action(self.char1, "재분배", "all")
        self.assertEqual(self.char1.profile(), before)
        self.char1.change(lambda p: p.update(combat_target=None))
        instructor.location = self.rooms["grass"]
        self.char1.location = self.rooms["grass"]
        with self.assertRaises(rules.RuleError):
            instructor.perform_action(self.char1, "배워", "heavy")

    def test_combined_retraining_save_failure_rolls_back_everything(self):
        self.char1.change(lambda p: rules.allocate_attribute(p, "strength", 2, safe=True))
        self.char1.change(lambda p: rules.learn_skill(p, "heavy", safe=True))
        before = self.char1.profile()
        original = self.char1.save_profile

        def fail(profile):
            original(profile)
            raise RuntimeError("simulated save failure")

        with patch.object(self.char1, "save_profile", side_effect=fail):
            with self.assertRaises(RuntimeError):
                instructor_for(self.char1).perform_action(self.char1, "재분배", "all")
        self.assertEqual(self.char1.profile(), before)

    def test_world_objects_are_persistent_and_bootstrap_does_not_reset(self):
        first = {obj.id for room in self.rooms.values() for obj in action_objects(room)}
        self.assertEqual(len(first), 5)
        self.char1.change(lambda p: rules.allocate_attribute(p, "wisdom", 2, safe=True))
        before = self.char1.profile()
        build_world()
        self.assertEqual(
            first, {obj.id for room in self.rooms.values() for obj in action_objects(room)}
        )
        self.assertEqual(self.char1.profile(), before)
        self.assertEqual(
            resolve_action(self.char1, "대화", "탐사대 훈련관"), instructor_for(self.char1)
        )

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

    def test_real_combat_awards_personal_proficiency_once(self):
        enemy = room_enemies(self.rooms["ridge"])[0]
        for player in (self.char1, self.char2):
            player.location = self.rooms["ridge"]
            self.enterContext(patch.object(player.sessions, "count", return_value=1))
            enemy.engage(player, now=100)
        for _ in range(5):
            self.char1.change(lambda p: rules.queue_action(p, "guard", now=101))
        self.assertEqual(self.char1.profile()["proficiencies"]["weapon"]["xp"], 0)
        enemy.receive_attack(self.char1, now=102.5, rng=Random(1))
        enemy.receive_attack(self.char1, now=102.5, rng=Random(1))
        self.assertEqual(self.char1.profile()["proficiencies"]["weapon"]["xp"], 1)
        self.assertEqual(self.char2.profile()["proficiencies"]["weapon"]["xp"], 0)
        enemy.enemy_tick(now=102.5, rng=Random(1))
        enemy.enemy_tick(now=102.5, rng=Random(1))
        self.assertEqual(self.char1.profile()["proficiencies"]["defense"]["xp"], 1)
        self.char1.change(lambda p: p.update(hp=20, queued_action="heal"))
        enemy.receive_attack(self.char1, now=105, rng=Random(1))
        enemy.receive_attack(self.char1, now=105, rng=Random(1))
        self.assertEqual(self.char1.profile()["proficiencies"]["medicine"]["xp"], 1)
        self.assertEqual(self.char1.profile()["proficiencies"]["weapon"]["xp"], 1)

    def test_proficiency_rolls_back_on_death_failure(self):
        enemy = room_enemies(self.rooms["grass"])[0]
        self.char1.location = self.rooms["grass"]
        self.enterContext(patch.object(self.char1.sessions, "count", return_value=1))
        enemy.engage(self.char1, now=100)
        enemy.db.hp = 1
        before = self.char1.profile()
        with patch.object(enemy, "finish_death", side_effect=RuntimeError("death failed")):
            with self.assertRaises(RuntimeError):
                enemy.receive_attack(self.char1, now=102.5, rng=Random(1))
        self.assertEqual(self.char1.profile(), before)
        self.assertEqual(enemy.db.hp, 1)

    def test_shortcuts_are_whole_input_only_and_engine_remains_default(self):
        cmdset = CharacterCmdSet(self.char1)
        for alias, key in (
            ("상", "상태"),
            ("능", "능력"),
            ("기", "기술"),
            ("장", "장비"),
            ("가", "가방"),
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
        self.assertEqual(cmdparser("강철 마체테 무장", cmdset, self.char1)[0][1], "강철 마체테")
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
            (Help(), "도움말"),
        ):
            with patch.object(self.char1, "msg") as message:
                command.caller = self.char1
                command.run()
            output = message.call_args.args[0]
            self.assertEqual(output.kind, "sheet")
            self.assertIn(heading, output)
