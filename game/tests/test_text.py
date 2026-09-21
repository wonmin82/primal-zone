from random import Random
from unittest.mock import Mock, patch

import evennia
from commands.character import Help, Look
from evennia.objects.objects import DefaultCharacter
from evennia.utils.ansi import strip_raw_ansi
from evennia.utils.test_resources import EvenniaCommandTest
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from typeclasses.interactables import action_objects
from typeclasses.loot import room_loot, take_loot
from typeclasses.parties import invite, respond
from world import presentation as view
from world import rules
from world import text as ft
from world.bootstrap import build_world
from world.content import EXCHANGE, ITEMS, ROOMS, SHOP
from world.progression import ATTRIBUTES, SKILLS


def tokens(message, role):
    return [part["text"] for part in message.segments if part["role"] == role]


class SemanticTextTests(EvenniaCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = build_world()
        for player in (self.char1, self.char2):
            player.location = self.rooms["dock"]
            player.home = self.rooms["dock"]
            player.push_state = Mock()
            self.enterContext(patch.object(player.sessions, "count", return_value=1))
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))

    def test_room_roles_come_from_objects_and_real_exits(self):
        for zone, room in self.rooms.items():
            self.char1.location = room
            output = room.return_appearance(self.char1)
            self.assertEqual(set(tokens(output, "direction")), set(ROOMS[zone]["exits"]))
            self.assertEqual(tokens(output, "hostile"), [e.key for e in room_enemies(room)])
            for obj in action_objects(room):
                self.assertIn(obj.key, tokens(output, obj.semantic_role))
            self.assertIn(ROOMS[zone]["desc"], tokens(output, "text"))
            self.assertNotIn("사냥 대상:", output)
            self.assertNotIn("가능한 행동", output)
            self.assertEqual(tokens(output, "command"), [])

    def test_target_appearance_actions_and_spaced_lookup(self):
        for room in self.rooms.values():
            self.char1.location = room
            for obj in action_objects(room):
                output = obj.return_appearance(self.char1)
                self.assertEqual(tokens(output, "command"), list(obj.actions))
                self.assertIn(obj.key, tokens(output, obj.semantic_role))
        self.char1.location = self.rooms["grass"]
        enemy = room_enemies(self.char1.location)[0]
        command = Look()
        command.caller, command.args = self.char1, "어린 청소룡"
        with patch.object(self.char1, "msg") as message:
            command.func()
        output = message.call_args.args[0]
        self.assertEqual(tokens(output, "hostile"), [enemy.key])
        self.assertEqual(tokens(output, "command"), ["공격"])
        command.args = "낡은 마체테"
        with patch.object(self.char1, "msg") as message:
            command.func()
        self.assertEqual(tokens(message.call_args.args[0], "item"), [ITEMS["machete"]["name"]])
        self.assertEqual(tokens(message.call_args.args[0], "command"), ["착용"])

    def test_query_values_and_item_roles_are_consistent(self):
        profile = rules.new_profile()
        profile.update(xp=200, credits=123, kills=7, hp=43)
        profile["inventory"].update(blade=1, scrap=8)
        stats = rules.stats(profile)
        status = view.status("탐사자", profile)
        self.assertEqual(tokens(status, "player"), ["탐사자"])
        for expected in (f"43 / {stats['max_hp']}", "123", "7", "200"):
            self.assertIn(expected, status)
        for output in (status, view.equipment(profile), view.inventory(profile)):
            self.assertTrue(
                set(tokens(output, "item")).issubset({v["name"] for v in ITEMS.values()})
            )
            self.assertEqual(output.kind, "sheet")
        self.assertEqual(view.inventory(profile).count("[착용]"), len(profile["equipment"]))
        for key, data in ATTRIBUTES.items():
            self.assertIn(data["name"], view.abilities(profile))
        for key, data in SKILLS.items():
            self.assertIn(
                f"Rank {rules.skill_rank(profile, key)} / {data['max_rank']}",
                view.skills(profile),
            )
        next_xp = rules.xp_threshold(rules.level_of(profile) + 1)
        self.assertIn(f"200 / {next_xp}", view.experience(profile))
        self.assertIn(str(next_xp - 200), view.experience(profile))
        shop = view.shop()
        for key, price in SHOP.items():
            self.assertIn(ITEMS[key]["name"], tokens(shop, "item"))
            self.assertIn(f"{price} 크레딧", tokens(shop, "reward"))
            if key in EXCHANGE:
                self.assertIn(f"{EXCHANGE[key]}개", shop)

    def test_help_uses_registry_not_a_separate_command_list(self):
        from commands.registry import COMMANDS

        command = Help()
        command.caller = self.char1
        with patch.object(self.char1, "msg") as message:
            command.run()
        output = message.call_args.args[0]
        for cls in COMMANDS:
            if getattr(cls, "input_style", None):
                self.assertIn(cls.key, tokens(output, "command"))

    def test_usage_styles_only_declared_action_metadata(self):
        output = ft.usage("강철 마체테 착용 · 대상 기타", {"착용"})
        self.assertEqual(tokens(output, "command"), ["착용"])
        self.assertIn("강철 마체테", tokens(output, "text"))
        self.assertIn("대상 기타", tokens(output, "text"))
        self.assertEqual(tokens(ft.usage("회복", {"회복"}), "command"), ["회복"])

    def test_shared_kill_and_round_robin_text_matches_committed_results(self):
        for player in (self.char1, self.char2):
            player.location = self.rooms["grass"]
        invite(self.char1, self.char2, now=100)
        respond(self.char2, True, now=100)
        enemy = room_enemies(self.rooms["grass"])[0]
        enemy.engage(self.char2, now=100)
        enemy.receive_attack(self.char2, now=102.5, rng=Random(1))
        enemy.engage(self.char1, now=100)
        enemy.db.hp = 1
        rng = Mock()
        rng.randint.return_value = 1
        rng.random.return_value = 0
        with patch.object(self.char1, "msg") as first, patch.object(self.char2, "msg") as second:
            enemy.receive_attack(self.char1, now=102.5, rng=rng)
            enemy.receive_attack(self.char1, now=102.5, rng=rng)
            outputs = [call.args[0] for call in first.call_args_list if call.args]
            attack = next(m for m in outputs if tokens(m, "item"))
            self.assertIn("1의 피해를 입혔다.", attack)
            self.assertEqual(tokens(attack, "hostile"), [enemy.key])
            self.assertEqual(tokens(attack, "item"), [ITEMS["machete"]["name"]])
            rewards = [m for m in outputs if tokens(m, "reward")]
            self.assertEqual(len(rewards), 1)
            self.assertEqual(tokens(rewards[0], "reward"), ["경험치 11", "4크레딧"])
            self.assertEqual(self.char1.profile()["xp"], 11)
            corpse = room_loot(self.char1.location)[0]
            output = corpse.return_appearance(self.char1)
            self.assertEqual(tokens(output, "remains"), [corpse.key])
            first.reset_mock()
            second.reset_mock()
            take_loot(self.char2, now=103)
            outputs = [call.args[0] for call in second.call_args_list if call.args]
            assigned = next(m for m in outputs if tokens(m, "player"))
            self.assertEqual(tokens(assigned, "player"), [self.char1.key])
            self.assertEqual(tokens(assigned, "item"), [ITEMS["scrap"]["name"]])
            self.assertEqual(self.char1.profile()["inventory"]["scrap"], 1)
            self.assertEqual(self.char2.profile()["inventory"]["blade"], 1)
            self.assertEqual(tokens(corpse.return_appearance(self.char1), "command"), [])
        rng.random.assert_called_once()

    def test_npc_quest_rewards_and_player_movement_keep_roles(self):
        from typeclasses.interactables import Commander, Generator

        commander = next(
            obj for obj in action_objects(self.rooms["dock"]) if isinstance(obj, Commander)
        )
        with patch.object(self.char1, "msg") as message:
            commander.perform_action(self.char1, "대화")
        self.assertEqual(tokens(message.call_args.args[0], "npc"), [commander.key])
        self.assertIn("발전기", tokens(message.call_args.args[0], "object"))
        self.char1.change(lambda p: p.update(record_read=True))
        self.char1.change(lambda p: p["inventory"].update(scrap=3))
        self.char1.location = self.rooms["generator"]
        generator = next(
            obj for obj in action_objects(self.char1.location) if isinstance(obj, Generator)
        )
        before = self.char1.profile()["xp"]
        with patch.object(self.char1, "msg") as message:
            generator.perform_action(self.char1, "수리")
        self.assertEqual(
            tokens(message.call_args.args[0], "reward"),
            [f"경험치 {self.char1.profile()['xp'] - before}"],
        )
        self.char1.location = self.rooms["dock"]
        with patch.object(self.char2, "msg") as message:
            self.char1.announce_move_from(self.rooms["grass"])
        self.assertEqual(tokens(message.call_args.args[0], "player"), [self.char1.key])
        self.assertIn("떠났다", message.call_args.args[0])
        self.assertEqual(
            tokens(self.char1.return_appearance(self.char2), "player"), [self.char1.key]
        )

    def test_web_wire_preserves_literal_untrusted_text_without_markup(self):
        value = "<img src=x onerror=alert(1)> |r붕대|n $You()\x1b[31m"
        message = ft.text(ft.token("player", value), ": ", value, kind="chat")
        with patch.object(self.session, "protocol_key", "websocket"):
            with patch.object(DefaultCharacter, "msg") as base:
                Explorer.msg(self.char1, (message, {"type": "look"}), session=self.session)
        args = base.call_args.kwargs
        self.assertNotIn("text", args)
        wire = evennia.SESSION_HANDLER.clean_senddata(self.session, args)
        payload = wire["pz_log"][0][0]
        self.assertEqual(payload["kind"], "chat")
        self.assertEqual(payload["segments"], message.segments)
        self.assertNotIn("\x1b", str(payload))
        self.assertIn("$You()", str(payload))
        self.assertIn("<img", str(payload))  # 브라우저는 textContent로만 표시한다.
        with patch.object(self.session, "protocol_key", "telnet"):
            with patch.object(DefaultCharacter, "msg") as base:
                Explorer.msg(self.char1, message, session=self.session)
        self.assertEqual(strip_raw_ansi(base.call_args.args[0]), str(message))
        self.assertTrue(base.call_args.kwargs["options"]["raw"])

    def test_chat_body_never_acquires_entity_or_command_roles(self):
        self.char1.key = "검증|r이름<img>"
        with patch.object(self.char2, "msg") as other:
            self.char1.execute_cmd("'어린청소룡 북 공격 <script>alert(1)</script>")
        message = other.call_args.args[0]
        self.assertEqual(tokens(message, "player"), [self.char1.key])
        self.assertEqual(tokens(message, "hostile"), [])
        self.assertEqual(tokens(message, "direction"), [])
        self.assertEqual(tokens(message, "command"), [])
        self.assertIn("<script>", tokens(message, "text")[-1])
