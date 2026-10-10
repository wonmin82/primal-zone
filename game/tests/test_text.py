from random import Random
from unittest.mock import Mock, patch

import evennia
from commands.character import Help, Look
from evennia.objects.objects import DefaultCharacter
from evennia.utils.ansi import parse_ansi, strip_raw_ansi
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from typeclasses.interactables import (
    AttributeTrainer,
    Container,
    SettlementOfficer,
    Shopkeeper,
    SkillTrainer,
    TrainingManager,
    action_objects,
)
from typeclasses.loot import room_loot, take_loot
from typeclasses.parties import invite, respond
from world import presentation as view
from world import rules
from world import text as ft
from world.content import ITEMS, ROOMS, SHOP_CATALOGS
from world.progression import ATTRIBUTES, SKILLS

from tests.base import WorldCommandTest


def tokens(message, role):
    return [part["text"] for part in message.segments if part["role"] == role]


class SemanticTextTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
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
            self.assertEqual({name for name in tokens(output, "direction") + tokens(output, "warning") if name in ROOMS[zone]["exits"]}, set(ROOMS[zone]["exits"]))
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
                if isinstance(obj, Container):
                    # 빈 보관함은 보관 방법만 안내하며 실제 내용이 있을 때 회수를 안내한다.
                    self.assertIn("넣어", tokens(output, "command"))
                    self.assertTrue(set(tokens(output, "command")) <= set(obj.actions))
                elif isinstance(obj, SettlementOfficer):
                    self.assertEqual(tokens(output, "command"), ["환율", "교환", "교환", "교환", "교환"])
                elif isinstance(obj, Shopkeeper):
                    self.assertEqual(tokens(output, "command"), ["목록", "사", "가치", "팔아"])
                elif isinstance(obj, SkillTrainer):
                    self.assertEqual(tokens(output, "command"), ["배워"])
                    self.assertIn(SKILLS[obj.db.skill_id]["name"] + " 배워", output)
                elif isinstance(obj, AttributeTrainer):
                    self.assertEqual(tokens(output, "command"), ["배분"])
                    self.assertIn(ATTRIBUTES[obj.db.attribute_id]["name"] + " 배분", output)
                elif isinstance(obj, TrainingManager):
                    self.assertEqual(tokens(output, "command"), ["재분배", "재분배", "재훈련"])
                else:
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
        command.args = "탐사용 벌 목 도"
        with patch.object(self.char1, "msg") as message:
            command.func()
        self.assertEqual(tokens(message.call_args.args[0], "item"), [ITEMS["explorer_machete"]["name"]])
        self.assertEqual(tokens(message.call_args.args[0], "command"), ["무장"])

    def test_query_values_and_item_roles_are_consistent(self):
        profile = rules.new_profile()
        profile.update(xp=200, credits=123, kills=7, hp=43)
        profile["inventory"].update(cutting_machete=1, scrap=8)
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
        self.assertIn(f"다음 레벨 {next_xp}", view.experience(profile))
        self.assertIn("진행 60 / 100", view.experience(profile))
        self.assertIn(str(next_xp - 200), view.experience(profile))
        shop = view.shop("supply", "보급관")
        for key in SHOP_CATALOGS["supply"]["purchase_catalog"]:
            price = ITEMS[key]["value"]
            self.assertIn(ITEMS[key]["name"], tokens(shop, "item"))
            self.assertIn(f"{price}칩", tokens(shop, "reward"))
        self.assertNotIn("교환", shop)
        self.assertNotIn(ITEMS["scrap"]["name"], shop)

    def test_help_uses_registry_not_a_separate_command_list(self):
        from commands.registry import COMMANDS

        command = Help()
        command.caller = self.char1
        with patch.object(self.char1, "msg") as message:
            command.run()
        output = message.call_args.args[0]
        from commands.help_pages import HELP_CATEGORIES, category_page

        for category, data in HELP_CATEGORIES.items():
            self.assertIn(category + " |", output)
            for key in data["examples"]:
                self.assertIn(key, tokens(output, "command"))
        for cls in COMMANDS:
            if getattr(cls, "input_style", None):
                self.assertIn(cls.category, HELP_CATEGORIES)
                self.assertIn(cls.key, tokens(category_page(cls.category, COMMANDS), "command"))
        self.assertNotIn("8방향 이동", tokens(output, "command"))

    def test_compact_progression_values_and_maximums(self):
        from copy import deepcopy
        profile = rules.new_profile()
        profile.update(xp=200, hp=43, credits=123, kills=7)
        profile['attributes']['strength']['allocated'] = 3
        before = deepcopy(profile)
        values = rules.stats(profile)
        status = view.status('탐사자', profile)
        for value in (f"Lv.{values['level']}", f"공격 {values['attack']}", f"방어 {values['defense']}", '힘13'):
            self.assertIn(value, status)
        self.assertEqual(tokens(status, 'item'), [ITEMS[i]['name'] for i in profile['equipment'].values()])
        abilities = view.abilities(profile)
        self.assertIn('13 (10+3)', abilities)
        self.assertIn(f"남은 특성 포인트 {rules.point_pools(profile)['attribute_points']}", abilities)
        self.assertIn('다음 레벨까지', view.experience(profile))
        for key, data in SKILLS.items():
            self.assertIn(data['name'], view.skills(profile))
            self.assertIn(f"R1/{data['max_rank']}", view.skills(profile))
        for output in (status, abilities, view.experience(profile), view.skills(profile)):
            self.assertNotIn('숙련', output)
            self.assertEqual(output.kind, 'sheet')
            self.assertEqual(strip_raw_ansi(parse_ansi(output.ansi())), str(output))
        self.assertEqual(profile, before)
        profile['xp'] = rules.xp_threshold(rules.MAX_LEVEL)
        for key, data in SKILLS.items():
            profile['skills'][key] = data['max_rank']
        for key in profile['attributes']:
            profile['attributes'][key]['allocated'] = 20
        self.assertIn('최고 레벨', view.experience(profile))
        self.assertNotIn('다음', view.experience(profile))
        self.assertEqual(view.skills(profile).count('MAX'), len(SKILLS))
        self.assertIn('모든 특성을 완성', view.abilities(profile))

    def test_compact_inventory_equipment_and_quest(self):
        profile = rules.new_profile()
        profile["inventory"].update(cutting_machete=2, scrap=8)
        bag = view.inventory(profile)
        self.assertEqual(
            tokens(bag, "item"),
            [ITEMS[i]["name"] for i in ("explorer_machete", "expedition_workwear", "cutting_machete", "bandage", "scrap")],
        )
        self.assertIn("절단마체테×2", bag)
        self.assertIn("[재료] 회수부품×8", bag)
        self.assertEqual(len(tokens(bag, "success")), len(profile["equipment"]))
        self.assertNotIn("[기타]", bag)
        equip = view.equipment(profile)
        for slot, identity in profile["equipment"].items():
            self.assertIn("손" if slot == "weapon" else "몸", equip)
            self.assertIn(ITEMS[identity]["name"], tokens(equip, "item"))
        self.assertIn("[주무기]", equip)
        self.assertIn("공격 +2 · 방어 +1", equip.splitlines()[-1])
        profile["inventory"] = {}
        self.assertEqual(str(view.inventory(profile)), "[소지품] 20칩\n\n비어 있다.")
        self.assertEqual(tokens(view.shop("supply", "보급관"), "command"), ["사"])
        profile["quests"]["radio_tower"].update(started=True, record_read=True)
        quest = view.quest(profile)
        self.assertIn("2/5", quest.splitlines()[1])
        self.assertEqual([line[0] for line in quest.splitlines()[2:]], ["+", "+", ">", "-", "-"])
        self.assertIn("윤대장", tokens(quest, "npc"))
        self.assertEqual(tokens(quest, "object"), ["정비기록", "발전기"])
        self.assertTrue(tokens(quest, "hostile"))
        for key in ("generator_fixed", "boss_defeated", "claimed"):
            profile["quests"]["radio_tower"][key] = True
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
                self.assertIn(cls.key, tokens(output(Help(), self.char1, cls.category), "command"))
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
        output = ft.usage("강화방호조끼 착용 · 대상 기타", {"착용"})
        self.assertEqual(tokens(output, "command"), ["착용"])
        self.assertIn("강화방호조끼", tokens(output, "text"))
        self.assertIn("대상 기타", tokens(output, "text"))
        self.assertEqual(tokens(ft.usage("응급처치", {"응급처치"}), "command"), ["응급처치"])

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
            self.assertIn("1 피해를 입혔다.", attack)
            self.assertEqual(tokens(attack, "hostile"), [enemy.key])
            self.assertEqual(tokens(attack, "item"), [ITEMS["explorer_machete"]["name"]])
            rewards = [m for m in outputs if tokens(m, "reward")]
            self.assertEqual(len(rewards), 1)
            self.assertEqual(tokens(rewards[0], "reward"), ["경험치 11"])
            self.assertEqual(self.char1.profile()["xp"], 11)
            corpse = room_loot(self.char1.location)[0]
            output = corpse.return_appearance(self.char1)
            self.assertEqual(tokens(output, "remains"), [corpse.key, "시체"])
            first.reset_mock()
            second.reset_mock()
            take_loot(self.char2, now=103)
            outputs = [call.args[0] for call in second.call_args_list if call.args]
            assigned = next(m for m in outputs if tokens(m, "player") and tokens(m, "item"))
            self.assertEqual(tokens(assigned, "player"), [self.char1.key])
            self.assertEqual(tokens(assigned, "item"), [ITEMS["water"]["name"]])
            self.assertEqual(self.char1.profile()["inventory"]["water"], 1)
            self.assertEqual(self.char2.profile()["inventory"]["security_goggles"], 1)
            self.assertEqual(tokens(corpse.return_appearance(self.char1), "command"), [])
        self.assertEqual(rng.random.call_count, 3)

    def test_npc_quest_rewards_and_player_movement_keep_roles(self):
        from typeclasses.interactables import Commander, Generator

        commander = next(
            obj for obj in action_objects(self.rooms["dock"]) if isinstance(obj, Commander)
        )
        with patch.object(self.char1, "msg") as message:
            commander.perform_action(self.char1, "대화")
        self.assertEqual(tokens(message.call_args.args[0], "npc"), [commander.key])
        self.assertIn("발전기", tokens(message.call_args.args[0], "object"))
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(record_read=True))
        self.char1.change(lambda p: p["inventory"].update(generator_repair_part=3))
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
