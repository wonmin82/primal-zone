"""견제의 교전 수명·source 중첩과 전문 교관의 정보 책임 회귀."""

from copy import deepcopy
from random import Random
from unittest.mock import Mock, patch

from evennia import create_object, search_tag
from evennia.utils.ansi import strip_ansi
from evennia.utils.dbserialize import deserialize
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
from world import progression as pg
from world import rules
from world.bootstrap import build_world
from world.content.integrity import errors
from world.multiplayer import CLAIM_TIMEOUT_SECONDS, PARTY_MAX_SIZE

from tests.base import WorldCommandTest


class GrowthReviewTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        self.clock = self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        for module in ("typeclasses.enemies", "world.skill_services", "time"):
            self.enterContext(patch(module + ".time", side_effect=lambda: self.clock.return_value))
        super().setUp()
        self.rooms = self.world_rooms()
        for player in (self.char1, self.char2):
            player.location = self.rooms["training_room"]
            player.push_state = Mock()
            self.enterContext(patch.object(player.sessions, "count", return_value=1))
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))

    def command(self, text, player=None):
        player = player or self.char1
        with patch.object(player, "msg") as output:
            player.execute_cmd(text)
        return strip_ansi("\n".join(str(call.args[0]) for call in output.call_args_list if call.args))

    def suppressed_enemy(self, zone="grass"):
        now = max(self.clock.return_value, self.char1.profile()["skill_ready_at"].get("suppress", 0))
        enemy = room_enemies(self.rooms[zone])[0]
        self.char1.location = enemy.location
        enemy.engage(self.char1, now=now)
        self.char1.change(lambda p: p.update(queued_action="suppress"))
        self.clock.return_value = now + 2.5
        enemy.receive_attack(self.char1, now=now + 2.5, rng=Random(1))
        self.assertIn(str(self.char1.id), enemy.db.suppressions)
        return enemy

    def test_flee_and_reengage_clear_suppression_before_hp_recovery(self):
        enemy = self.suppressed_enemy()
        hp = enemy.db.hp
        self.assertLess(hp, enemy.db.max_hp)
        self.command("도망")
        self.assertEqual(enemy.db.suppressions, {})
        self.assertEqual(enemy.db.hp, hp)
        enemy.engage(self.char1, now=103)
        self.assertEqual(enemy.db.suppressions, {})
        self.assertEqual(enemy.db.hp, hp)

    def test_last_combatant_and_claim_timeout_cleanup(self):
        enemy = self.suppressed_enemy("ridge")
        self.char2.location = enemy.location
        enemy.engage(self.char2, now=103)
        self.char1.leave_combat(now=104)
        self.assertTrue(enemy.db.suppressions)
        self.char2.leave_combat(now=104)
        self.assertEqual(enemy.db.suppressions, {})
        enemy = self.suppressed_enemy()
        enemy.reconcile(now=enemy.db.claim_last_activity + CLAIM_TIMEOUT_SECONDS)
        self.assertEqual(enemy.db.suppressions, {})
        self.assertIsNone(self.char1.profile()["combat_target"])

    def test_enemy_movement_death_and_respawn_cleanup(self):
        enemy = self.suppressed_enemy()
        enemy.move_to(self.rooms["trail"], quiet=True)
        self.assertEqual(enemy.db.suppressions, {})
        self.assertIsNone(self.char1.profile()["combat_target"])
        self.char1.location = enemy.location
        enemy.engage(self.char1, now=110)
        enemy.db.suppressions = {str(self.char1.id): pg.suppression_effect(10)}
        enemy.db.hp = 1
        enemy.receive_attack(self.char1, now=112.5, rng=Random(1))
        self.assertEqual(enemy.db.state, "respawning")
        self.assertEqual(enemy.db.suppressions, {})
        enemy.db.suppressions = {str(self.char1.id): pg.suppression_effect(10)}
        enemy.reconcile(now=enemy.db.respawn_at)
        self.assertEqual(enemy.db.state, "alive")
        self.assertEqual(enemy.db.suppressions, {})

    def test_source_specific_apply_logs_and_one_event_consumption(self):
        enemy = room_enemies(self.rooms["ridge"])[0]
        enemy.db.hp = enemy.db.max_hp = 1000
        for player in (self.char1, self.char2):
            player.location = enemy.location
            player.change(lambda p: p.update(xp=rules.xp_threshold(50), mental=165))
            enemy.engage(player, now=100)
        self.char2.change(lambda p: (p["skills"].update(suppress=4), p.update(queued_action="suppress")))
        enemy.receive_attack(self.char2, now=102.5, rng=Random(1))
        other = deepcopy(deserialize(enemy.db.suppressions)[str(self.char2.id)])
        for now, rank, phrase in ((102.5, 7, "다음 3회 공격력을"), (112.5, 7, "연장했다"), (122.5, 10, "강화했다"), (132.5, 7, "더 강한 견제 효과가 유지됐다")):
            self.char1.change(lambda p: (p["skills"].update(suppress=rank), p.update(queued_action="suppress")))
            with patch.object(self.char1, "msg") as output:
                enemy.receive_attack(self.char1, now=now, rng=Random(1))
            rendered = strip_ansi(str(output.call_args.args[0]))
            self.assertIn(phrase, rendered)
            self.assertEqual(enemy.db.suppressions[str(self.char2.id)], other)
        effects = deserialize(enemy.db.suppressions)
        self.assertEqual(set(effects), {str(self.char1.id), str(self.char2.id)})
        enemy.enemy_tick(now=132.5, rng=Random(1))
        self.assertEqual({key: value["attacks"] for key, value in deserialize(enemy.db.suppressions).items()},
                         {str(self.char1.id): 3, str(self.char2.id): 1})

    def test_public_enemy_multi_party_cap_keeps_and_consumes_all_sources(self):
        enemy = room_enemies(self.rooms["ridge"])[0]
        players = [self.char1, self.char2]
        for index in range(6):
            player = create_object(Explorer, key=f"견제참여자{index}", location=enemy.location)
            player.push_state = Mock()
            self.enterContext(patch.object(player.sessions, "count", return_value=1))
            players.append(player)
        for player in players:
            player.location = enemy.location
        for members in (players[:4], players[4:]):
            for member in members[1:]:
                invite(members[0], member, now=100)
                respond(member, True, now=100)
        self.assertGreater(len(players), PARTY_MAX_SIZE)
        for boss, quest, individual, cap in ((True, None, .095, .329198049375), (False, "radio_tower", .19, .56953279)):
            with self.subTest(boss=boss):
                definition = {**rules.ENEMIES["alpha"], "boss": boss, "hp": 10000}
                definition.pop("boss_quest", None)
                if quest:
                    definition["boss_quest"] = quest
                with patch.dict(rules.ENEMIES, alpha=definition):
                    self.assertEqual(definition["combat_mode"], "public")
                    enemy.db.hp = enemy.db.max_hp = 10000
                    enemy.db.suppressions = {}
                    for player in players:
                        player.change(lambda p: (p.update(xp=rules.xp_threshold(50), mental=165, next_attack_at=0),
                                                 p["skills"].update(suppress=10), p["skill_ready_at"].clear()))
                        enemy.engage(player, now=100)
                        player.change(lambda p: rules.queue_action(p, "suppress", 100))
                        enemy.receive_attack(player, now=102.5, rng=Random(1))
                    effects = deserialize(enemy.db.suppressions)
                    self.assertEqual(set(effects), {str(player.id) for player in players})
                    for effect in effects.values():
                        self.assertAlmostEqual(effect["reduction"], individual)
                    groups = enemy.reward_groups(102.5)
                    self.assertEqual(len(groups), 2)
                    self.assertEqual(sum(len(group) for group in groups.values()), 8)
                    enemy.db.next_attack_at = 102.5
                    with patch("world.rules.enemy_attack", wraps=rules.enemy_attack) as attack:
                        enemy.enemy_tick(now=102.5, rng=Random(1))
                    self.assertAlmostEqual(attack.call_args.args[-1], cap)
                    self.assertEqual({effect["attacks"] for effect in deserialize(enemy.db.suppressions).values()}, {3})
                    self.assertEqual(len(enemy.db.suppressions), 8)
                    for player in players:
                        player.leave_combat(now=102.5)

    def test_party_heal_shortage_command_is_atomic_in_and_out_of_combat(self):
        self.char1.location = self.char2.location = self.rooms["ridge"]
        invite(self.char1, self.char2, now=100)
        respond(self.char2, True, now=100)
        self.char1.change(lambda p: p.update(xp=rules.xp_threshold(133), mental=19))
        self.char2.change(lambda p: p.update(hp=20))
        enemy = room_enemies(self.rooms["ridge"])[0]
        for in_combat in (False, True):
            with self.subTest(in_combat=in_combat):
                if in_combat:
                    enemy.engage(self.char1, now=100)
                before = deepcopy(self.char1.profile()), deepcopy(self.char2.profile())
                enemy_before = enemy.db.hp, deepcopy(deserialize(enemy.db.suppressions))
                result = self.command(self.char2.key + " 치료")
                self.assertIn("치료", result)
                self.assertIn("정신력이 20 필요하다", result)
                self.assertEqual((self.char1.profile(), self.char2.profile()), before)
                self.assertEqual((enemy.db.hp, deserialize(enemy.db.suppressions)), enemy_before)

    def test_cooldowns_survive_profile_reload_real_login_session_restore_and_resets(self):
        self.char1.change(lambda p: (p.update(xp=rules.xp_threshold(50)), p["skill_ready_at"].update(insight=110, suppress=110)))
        saved = deepcopy(self.char1.profile())
        self.char1.db.profile = saved
        self.account.puppet_object(self.session, self.char1)
        self.char1.move_to(self.rooms["training_office"], quiet=True)
        self.session.puid = self.char1.id
        self.session.at_sync()
        self.assertEqual(self.char1.profile()["skill_ready_at"], saved["skill_ready_at"])
        for scope in ("기술 재분배", "전체 재훈련"):
            self.command(scope)
            self.assertEqual(self.char1.profile()["skill_ready_at"], saved["skill_ready_at"])
        with patch.object(self.char1.sessions, "count", return_value=0):
            self.account.unpuppet_object(self.session)
        self.account.puppet_object(self.session, self.char1)
        self.assertEqual(self.char1.profile()["skill_ready_at"], saved["skill_ready_at"])
        enemy = room_enemies(self.rooms["ridge"])[0]
        self.char1.location = enemy.location
        enemy.engage(self.char1, now=100)
        for command in ("간파", "견제"):
            self.assertIn("10초", self.command(command))
        self.char1.at_server_shutdown()
        self.assertEqual(self.char1.profile()["skill_ready_at"], saved["skill_ready_at"])

    def test_reset_scopes_report_actual_available_totals_without_free_resources(self):
        self.char1.location = self.rooms["training_office"]
        for command, reset_attr, reset_skill in (("특성 재분배", True, False), ("기술 재분배", False, True), ("전체 재훈련", True, True)):
            with self.subTest(command=command):
                self.char1.change(lambda p: (p.update(xp=rules.xp_threshold(37), hp=20, mental=10),
                                             p["attributes"]["strength"].update(allocated=3),
                                             p["skills"].update(heavy=4), p["skill_ready_at"].update(insight=110, suppress=110)))
                result = self.command(command)
                p = self.char1.profile()
                pools = rules.point_pools(p)
                self.assertEqual(p["attributes"]["strength"]["allocated"], 0 if reset_attr else 3)
                self.assertEqual(p["skills"]["heavy"], 1 if reset_skill else 4)
                self.assertEqual((p["hp"], p["mental"]), (20, 10))
                self.assertEqual(p["skill_ready_at"]["suppress"], 110)
                if reset_attr:
                    self.assertIn(f"특성 포인트 {pools['attribute_points']}점", result)
                else:
                    self.assertNotIn("특성", result)
                if reset_skill:
                    self.assertIn(f"기술 훈련 {pools['skill_points']}회", result)
                else:
                    self.assertNotIn("기술", result)

    def test_trainer_discovery_dialogue_and_web_provider_are_data_driven(self):
        trainers = [obj for room in self.rooms.values() for obj in action_objects(room)
                    if isinstance(obj, (SkillTrainer, AttributeTrainer, TrainingManager))]
        self.assertEqual(sum(type(obj) is SkillTrainer for obj in trainers), 8)
        self.assertEqual(sum(type(obj) is AttributeTrainer for obj in trainers), 4)
        dialogues = set()
        for obj in trainers:
            identity = obj.tags.get(category="primal_interactable")
            definition = INTERACTABLES[identity]
            self.char1.location = obj.location
            appearance = self.command(obj.key + " 봐")
            self.assertIn(definition["description"], appearance)
            for forbidden in ("남은 기술 훈련", "남은 특성 포인트", "R1/", "정신력", "피해 배율", "현재 지혜", "최대 정신력 +4"):
                self.assertNotIn(forbidden, appearance)
            self.assertEqual(appearance, strip_ansi(str(obj.return_appearance(self.char2))))
            dialogue = self.command(obj.key + " 대화")
            self.assertIn(definition["dialogue"], dialogue)
            dialogues.add(definition["dialogue"])
            if type(obj) is SkillTrainer:
                name = pg.SKILLS[obj.db.skill_id]["name"]
                self.assertIn(name + " 배워", appearance)
                self.assertNotIn("재훈련", dialogue)
                self.assertIn(obj.db.skill_id, growth_controls(self.char1))
            elif type(obj) is AttributeTrainer:
                name = pg.ATTRIBUTES[obj.db.attribute_id]["name"]
                self.assertIn(name + " 배분", appearance)
                self.assertNotIn("재훈련", dialogue)
                self.assertIn(obj.db.attribute_id, growth_controls(self.char1))
            else:
                for usage in ("특성 재분배", "기술 재분배", "전체 재훈련"):
                    self.assertIn(usage, appearance)
            self.assertFalse(any(action in ("배워", "배분", "재분배") for action in getattr(obj.location, "actions", ())))
        self.assertEqual(len(dialogues), 13)
        self.assertEqual(errors(INTERACTABLES), [])
        for field in ("description", "dialogue", "presence"):
            broken = deepcopy(INTERACTABLES)
            broken["trainer_heavy"].pop(field)
            self.assertTrue(any("trainer_heavy" in error and field in error for error in errors(broken)))

    def test_bootstrap_clears_old_unattributed_effect_preserves_live_new_effect_and_identity(self):
        enemy = self.suppressed_enemy()
        old_ids = {obj.id for room in self.rooms.values() for obj in action_objects(room)}
        effects = deepcopy(deserialize(enemy.db.suppressions))
        enemy.db.suppression = pg.suppression_effect(10)
        before = deepcopy(self.char1.profile())
        for _ in range(2):
            build_world()
            self.assertFalse(enemy.attributes.has("suppression"))
            self.assertEqual(enemy.db.suppressions, effects)
            self.assertEqual(search_tag(enemy.db.spawn_id, category="primal_spawn")[0].id, enemy.id)
            self.assertEqual({obj.id for room in self.rooms.values() for obj in action_objects(room)}, old_ids)
            self.assertEqual(self.char1.profile(), before)
            self.assertEqual(self.char1.profile()["version"], 11)
