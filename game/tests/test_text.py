from random import Random
from unittest.mock import Mock, patch

import evennia
from commands.character import Help, Look
from evennia.objects.objects import DefaultCharacter
from evennia.utils.ansi import parse_ansi, strip_raw_ansi
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
        self.assertEqual(tokens(message.call_args.args[0], "command"), ["무장"])

    def test_query_values_and_item_roles_are_consistent(self):
        profile = rules.new_profile()
        profile.update(xp=200, credits=123, kills=7, hp=43)
        profile["inventory"].update(blade=1, scrap=8)
        stats = rules.stats(profile)
        status = view.status("탐사자", profile)
        self.assertEqual(tokens(status, "player"), ["탐사자"])
        for expected in (f"43/{stats['max_hp']}", "123", "7", "200"):
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
                f"R{rules.skill_rank(profile, key)}/{data['max_rank']}",
                view.skills(profile),
            )
        next_xp = rules.xp_threshold(rules.level_of(profile) + 1)
        self.assertIn(f"200/{next_xp}", view.experience(profile))
        self.assertIn(str(next_xp - 200), view.experience(profile))
        shop = view.shop()
        for key, price in SHOP.items():
            self.assertIn(ITEMS[key]["name"], tokens(shop, "item"))
            self.assertIn(f"{price}C", tokens(shop, "reward"))
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

    def test_compact_progression_values_and_maximums(self):
        from copy import deepcopy

        from world.progression import PROFICIENCIES

        profile = rules.new_profile()
        profile.update(xp=200, hp=43, credits=123, kills=7)
        profile["attributes"]["strength"]["allocated"] = 3
        profile["proficiencies"]["weapon"]["xp"] = 47
        before = deepcopy(profile)
        values = rules.stats(profile)
        status = view.status("탐사자", profile)
        for value in (
            f"Lv.{values['level']}",
            f"공격 {values['attack']}",
            f"방어 {values['defense']}",
            "힘13",
        ):
            self.assertIn(value, status)
        self.assertEqual(
            tokens(status, "item"), [ITEMS[i]["name"] for i in profile["equipment"].values()]
        )
        abilities = view.abilities(profile)
        self.assertIn("힘 13 (10+3)", abilities)
        self.assertIn(
            f"남은 특성 포인트 {rules.point_pools(profile)['attribute_points']}", abilities
        )
        for key, name in PROFICIENCIES.items():
            self.assertIn(f"{name} R{rules.proficiency_rank(profile, key)}", abilities)
            self.assertIn(
                f"{name} R{rules.proficiency_rank(profile, key)} XP{profile['proficiencies'][key]['xp']}",
                view.experience(profile),
            )
        for key, data in SKILLS.items():
            next_rank = rules.skill_rank(profile, key) + 1
            self.assertIn(
                f"다음 Lv{data['requirements'][next_rank]}/{data['point_cost'][next_rank]}점/{data['credit_cost'][next_rank]}C",
                view.skills(profile),
            )
            self.assertIn(data["description"], view.skills(profile))
        self.assertEqual(tokens(view.skills(profile), "command"), ["배워"])
        self.assertIn(
            f"남은 점수 {rules.point_pools(profile)['skill_points']}", view.skills(profile)
        )
        for output, limit in (
            (status, 5),
            (abilities, 6),
            (view.experience(profile), 2),
            (view.skills(profile), len(SKILLS) + 2),
        ):
            self.assertLessEqual(len(output.splitlines()), limit)
            self.assertNotIn("────", output)
            self.assertEqual(output.kind, "sheet")
            self.assertEqual(strip_raw_ansi(parse_ansi(output.ansi())), str(output))
        self.assertEqual(profile, before)
        profile["xp"] = rules.xp_threshold(rules.MAX_LEVEL)
        for key, data in SKILLS.items():
            profile["skills"][key] = data["max_rank"]
        self.assertIn("최고 등급", view.status("탐사자", profile))
        self.assertIn("최고 등급", view.experience(profile))
        self.assertNotIn("다음", view.experience(profile))
        self.assertEqual(view.skills(profile).count("최고 Rank"), len(SKILLS))

    def test_compact_inventory_equipment_and_quest(self):
        profile = rules.new_profile()
        profile["inventory"].update(blade=2, scrap=8)
        bag = view.inventory(profile)
        self.assertEqual(
            tokens(bag, "item"),
            [ITEMS[i]["name"] for i in ("machete", "vest", "blade", "bandage", "scrap")],
        )
        self.assertIn("강철마체테×2", bag)
        self.assertIn("[재료] 회수부품×8", bag)
        self.assertEqual(len(tokens(bag, "success")), len(profile["equipment"]))
        self.assertNotIn("[기타]", bag)
        equip = view.equipment(profile)
        for slot, identity in profile["equipment"].items():
            self.assertIn("무기" if slot == "weapon" else "방어구", equip)
            self.assertIn(ITEMS[identity]["name"], tokens(equip, "item"))
            for key, label in (("attack", "공격"), ("defense", "방어")):
                if ITEMS[identity].get(key):
                    self.assertIn(f"{label} +{ITEMS[identity][key]}", equip)
        attack = sum(ITEMS[i].get("attack", 0) for i in profile["equipment"].values())
        defense = sum(ITEMS[i].get("defense", 0) for i in profile["equipment"].values())
        self.assertIn(f"공격 +{attack} · 방어 +{defense}", equip.splitlines()[-1])
        profile["inventory"] = {}
        self.assertEqual(str(view.inventory(profile)), "[가방] 비어 있다.")
        self.assertEqual(tokens(view.shop(), "command"), ["구매", "교환"])
        profile.update(quest_started=True, record_read=True)
        quest = view.quest(profile)
        self.assertIn("2/5", quest.splitlines()[0])
        self.assertEqual([line[0] for line in quest.splitlines()[1:]], ["+", "+", ">", "-", "-"])
        self.assertIn("윤대장", tokens(quest, "npc"))
        self.assertEqual(tokens(quest, "object"), ["정비기록", "발전기"])
        self.assertTrue(tokens(quest, "hostile"))
        for key in ("generator_fixed", "boss_defeated", "quest_claimed"):
            profile[key] = True
        self.assertIn("5/5", view.quest(profile))
        self.assertNotIn(">", view.quest(profile))

    def test_compact_party_invitation_and_detailed_help(self):
        from commands.combat import Attack
        from commands.party import PartyCommand
        from commands.registry import COMMANDS
        from evennia import CmdSet
        from server.conf.cmdparser import cmdparser

        def output(command, caller, args=""):
            command.caller, command.args = caller, args
            with patch.object(caller, "msg") as message:
                command.run()
            return message.call_args.args[0]

        self.assertIn("소속 파티 없음", output(PartyCommand(), self.char2))
        invite(self.char1, self.char2)
        invitation = output(PartyCommand(), self.char2)
        self.assertIn(self.char1.key, tokens(invitation, "player"))
        self.assertTrue({"파티수락", "파티거절"}.issubset(tokens(invitation, "command")))
        respond(self.char2, True)
        party = output(PartyCommand(), self.char1)
        self.assertIn(f"파티장 {self.char1.key} · 전리품 순번", party)
        self.assertIn(f"{self.char1.key}(장) · {self.char2.key}", party)
        self.assertEqual(len(party.splitlines()), 2)
        help_text = output(Help(), self.char1)
        for cls in COMMANDS:
            if getattr(cls, "input_style", None):
                self.assertIn(f"{getattr(cls, 'category', '탐사')} |", help_text)
                self.assertIn(cls.key, tokens(help_text, "command"))
        for query in (Attack.key, *Attack.aliases):
            detail = output(Help(), self.char1, query)
            self.assertIn(Attack.summary, detail)
            self.assertIn(Attack.usage, detail)
            self.assertTrue(set(Attack.aliases).issubset(tokens(detail, "command")))
        detail = output(Help(), self.char1, "능")
        for data in ATTRIBUTES.values():
            self.assertIn(data["description"], detail)
        with self.assertRaises(rules.RuleError):
            output(Help(), self.char1, "<script>")
        cmdset = CmdSet(self.char1)
        cmdset.add(Help())
        self.assertEqual(cmdparser("공격 도움말", cmdset, self.char1)[0][1], "공격")
        self.assertFalse(cmdparser("도움말 공격", cmdset, self.char1))

    def test_usage_styles_only_declared_action_metadata(self):
        output = ft.usage("강화 조끼 착용 · 대상 기타", {"착용"})
        self.assertEqual(tokens(output, "command"), ["착용"])
        self.assertIn("강화 조끼", tokens(output, "text"))
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
