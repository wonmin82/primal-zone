import re
from pathlib import Path
from random import Random
from unittest import TestCase
from unittest.mock import Mock, patch

import evennia
from commands.character import Help, Look
from evennia.objects.objects import DefaultCharacter
from evennia.utils.ansi import parse_ansi, strip_raw_ansi
from typeclasses.explorers import Explorer
from typeclasses.interactables import (
    Container,
    Incinerator,
    action_objects,
)
from typeclasses.loot import room_loot, take_loot
from typeclasses.parties import invite, respond
from world import presentation as view
from world import rules
from world import text as ft
from world.content import ITEMS, ROOMS, SHOP_CATALOGS
from world.interactable_services import generator as repair_generator
from world.progression import ATTRIBUTES, SKILLS
from world.shared_combat import room_enemies

from tests.base import WorldCommandTest


def tokens(message, role):
    return [part["text"] for part in message.segments if part["role"] == role]


class NarrationSemanticTests(TestCase):
    def test_narration_respects_colorless_terminal_before_raw_delivery(self):
        message = ft.text(ft.token("damage_taken", "1 피해"), " |r 원문")
        for protocol, flags, options, colored in (
            ("telnet", {"NOCOLOR": True}, {}, False),
            ("telnet", {"TTYPE": True, "ANSI": False, "XTERM256": False}, {}, False),
            ("telnet", {}, {"ansi": False, "xterm256": False}, False),
            ("telnet", {"TTYPE": True, "ANSI": True}, {}, True),
            ("ssh", {"ANSI": False, "XTERM256": False}, {}, False),
            ("ssh", {"NOCOLOR": True}, {}, False),
            ("ssh", {}, {}, True),
        ):
            with self.subTest(protocol=protocol, flags=flags, options=options), patch.object(DefaultCharacter, "msg") as deliver:
                target = Mock(protocol_key=protocol, protocol_flags=flags)
                Explorer().msg(message, session=target, options=options)
                rendered = deliver.call_args.args[0]
                self.assertEqual(strip_raw_ansi(rendered), str(message))
                self.assertEqual("\x1b" in rendered, colored)
                self.assertTrue(deliver.call_args.kwargs["options"]["raw"])

    def test_narration_roles_share_exact_web_and_terminal_contract(self):
        static = Path(__file__).resolve().parents[1] / "web" / "static" / "webclient"
        javascript = (static / "js" / "primal.js").read_text(encoding="utf-8")
        stylesheet = (static / "css" / "primal.css").read_text(encoding="utf-8")
        allowlist = re.search(r"const semanticRoles = new Set\(\[([^]]+)\]\)", javascript)
        self.assertIsNotNone(allowlist)
        self.assertEqual(set(re.findall(r'"(\w+)"', allowlist[1])), set(ft.ANSI))
        self.assertRegex(stylesheet, r"(?:^|\n)body\{font-synthesis:none[;\}]")
        for role, rgb, ansi, bold in (
            ("combat_verb_outgoing", "#EFB66D", "\033[22m\033[33m", False),
            ("damage_dealt", "#FFD098", "\033[1m\033[33m", True),
            ("combat_verb_incoming", "#F0B39B", "\033[22m\033[31m", False),
            ("damage_taken", "#FF8585", "\033[1m\033[31m", True),
            ("hp_recovered", "#91DBA5", "\033[1m\033[32m", True),
            ("mental_recovered", "#8ECFCE", "\033[1m\033[36m", True),
            ("status_buff", "#94C4E8", "\033[22m\033[36m", False),
            ("status_debuff", "#E8C779", "\033[22m\033[33m", False),
        ):
            with self.subTest(role=role):
                rule = re.search(rf"\.semantic-{role}\{{([^}}]+)\}}", stylesheet)
                self.assertIsNotNone(rule)
                declarations = rule[1].split(";")
                self.assertIn(f"color:{rgb}", declarations)
                self.assertEqual("font-weight:700" in declarations, bold)
                self.assertEqual("font-synthesis:weight" in declarations, bold)
                output = ft.text(ft.token(role, "핵심"), " 기본색")
                rendered = parse_ansi(output.ansi())
                self.assertEqual(rendered, f"{ansi}핵심\033[0m 기본색\033[0m")
                self.assertEqual(strip_raw_ansi(rendered), str(output))
        with self.assertRaisesRegex(ValueError, "알 수 없는 텍스트 역할"):
            ft.token("undefined_narration_role", "오류")


class SemanticTextTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        for player in (self.char1, self.char2):
            player.location = self.rooms["dock"]
            player.home = self.rooms["dock"]
            player.push_state = Mock()
            self.connect_character(player)
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch("world.shared_combat.delay" if module == "enemies" else f"typeclasses.{module}.delay"))

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
        from world.equipment_service import use_item_entities
        from world.item_entities import api

        # 현재 행동의 대상은 legacy dict가 아니라 실제 소지 UUID로 제공한다.
        self.char1.change(lambda profile: profile.update(
            inventory={}, equipment={"weapon": None, "armor": None},
            xp=rules.xp_threshold(20), hp=1, credits=1000))
        use_item_entities(self.char1)
        self.char1.location = self.rooms["storage_room"]
        container = next(obj for obj in action_objects(self.char1.location) if isinstance(obj, Container))
        self.assertNotIn("넣어", tokens(container.return_appearance(self.char1), "command"))
        # 보급·무기·장비 상점의 각 매입 분류 및 정산·보관에 필요한 실물을 갖춘다.
        for identity in ("bandage", "cutting_machete", "reinforced_vest", "scrap"):
            api.create_item(identity, location_kind="inventory", owner_object=self.char1)
        for room in self.rooms.values():
            self.char1.location = room
            for obj in action_objects(room):
                output = obj.return_appearance(self.char1)
                if isinstance(obj, Container):
                    # 보관 가능한 소지 실물이 있을 때만 보관 방법을 안내한다.
                    self.assertIn("넣어", tokens(output, "command"))
                    self.assertTrue(set(tokens(output, "command")) <= set(obj.actions))
                elif getattr(obj, "capability_active", lambda _: False)("settlement"):
                    self.assertEqual(tokens(output, "command"), ["환율", "교환", "교환", "교환", "교환"])
                elif getattr(obj, "capability_active", lambda _: False)("shop"):
                    self.assertEqual(tokens(output, "command"), ["목록", "사", "가치", "팔아"])
                elif getattr(obj, "capability_active", lambda _: False)("training") and obj.db.skill_id:
                    self.assertEqual(tokens(output, "command"), ["배워"])
                    self.assertIn(SKILLS[obj.db.skill_id]["name"] + " 배워", output)
                elif getattr(obj, "capability_active", lambda _: False)("training") and obj.db.attribute_id:
                    self.assertEqual(tokens(output, "command"), ["배분"])
                    self.assertIn(ATTRIBUTES[obj.db.attribute_id]["name"] + " 배분", output)
                elif getattr(obj, "capability_active", lambda _: False)("training"):
                    self.assertEqual(tokens(output, "command"), ["재분배", "재분배", "재훈련"])
                elif isinstance(obj, Incinerator):
                    self.assertEqual(tokens(output, "command"), ["소각"])
                elif getattr(obj, "capability_active", lambda _: False)("medical"):
                    self.assertIn("회복", tokens(output, "command"))
                else:
                    self.assertEqual(tokens(output, "command"), list(getattr(obj, "actions", ())))
                from dataclasses import replace

                from world.selection_numbers.api import descriptor, label, number_for

                record = descriptor(obj)
                expected_label = (label(replace(record, number=number_for(record.reference)))
                                  if isinstance(obj, Container) and record else obj.key)
                self.assertIn(expected_label, tokens(output, obj.semantic_role))

    def test_spaced_enemy_and_legacy_item_lookup_keeps_semantic_roles(self):
        # 과거 데이터의 읽기 전용 상세 표시는 기존 fixture로 별도 보존한다.
        self.char1.location = self.rooms["grass"]
        enemy = room_enemies(self.char1.location)[0]
        command = Look()
        command.caller, command.session, command.args = self.char1, self.session, "어린 청소룡"
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
        command.caller, command.session = self.char1, self.session
        with patch.object(self.char1, "msg") as message:
            command.func()
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
        self.assertEqual(str(view.inventory(profile)), "[가진거] 20칩\n\n비어 있다.")
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
                if isinstance(command, Help):
                    command.session = caller.sessions.all()[0]
                    command.func()
                else:
                    command.run()
            return message.call_args.args[0]

        self.assertIn("소속 일행 없음", output(PartyCommand(), self.char2))
        invite(self.char1, self.char2)
        invitation = output(PartyCommand(), self.char2)
        self.assertIn(self.char1.key, tokens(invitation, "player"))
        self.assertTrue({"일행합류", "일행거절"}.issubset(tokens(invitation, "command")))
        respond(self.char2, True)
        party = output(PartyCommand(), self.char1)
        self.assertIn(f"리더 {self.char1.key} (온라인) · 전리품 순번", party)
        self.assertIn(f"{self.char1.key}(장) · {self.char2.key}", party)
        self.assertEqual(len(party.splitlines()), 4)
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
        self.assertIn("등록된 명령을 찾을 수 없습니다.", output(Help(), self.char1, "<script>"))
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
        enemy.hp = 1
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
            self.assertEqual(tokens(output, "remains"), [corpse.key, "시체 1"])
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
        from typeclasses.actors import Actor
        from typeclasses.interactables import Generator

        commander = next(
            obj for obj in self.rooms["dock"].contents if isinstance(obj, Actor) and obj.actor_id == "commander"
        )
        from world.dialogue_actions import invoke

        with patch.object(self.char1, "msg") as message:
            invoke(self.char1, self.session, message="윤대장에게 임무")
            invoke(self.char1, self.session, message="윤대장에게 수락")
            spoken = [call.args[0] for call in message.call_args_list
                      if call.args and isinstance(call.args[0], ft.Text) and tokens(call.args[0], "npc")]
        self.assertEqual(tokens(spoken[0], "npc"), [commander.key])
        self.assertIn("발전기", str(spoken[0]))
        self.assertIn("〈수락〉", str(spoken[0]))
        self.assertTrue(self.char1.profile_snapshot()["quests"]["radio_tower"]["started"])
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(record_read=True))
        self.char1.change(lambda p: p["inventory"].update(generator_repair_part=3))
        self.char1.location = self.rooms["generator"]
        generator = next(
            obj for obj in action_objects(self.char1.location) if isinstance(obj, Generator)
        )
        before = self.char1.profile()["xp"]
        with patch.object(self.char1, "msg") as message:
            repair_generator(generator, self.char1, "수리", None)
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
        from world.dialogue_actions import invoke

        value = "<img src=x onerror=alert(1)> |r붕대|n $You()\x1b[31m"
        message = ft.text(ft.token("player", value), ": ", value, kind="chat")
        with patch.object(self.char1, "msg") as messages:
            invoke(self.char1, self.session, message="윤대장에게 임무")
        emitted = [call.args[0] for call in messages.call_args_list if call.args]
        self.assertTrue(all(isinstance(item, ft.Text) for item in emitted))
        self.assertEqual([item.kind for item in emitted], ["chat", "chat", "event", "event"])
        for output in (message, *emitted):
            with self.subTest(kind=output.kind, text=str(output)):
                with patch.object(self.session, "protocol_key", "websocket"):
                    with patch.object(DefaultCharacter, "msg") as base:
                        Explorer.msg(self.char1, (output, {"type": "look"}), session=self.session)
                args = base.call_args.kwargs
                self.assertNotIn("text", args)
                wire = evennia.SESSION_HANDLER.clean_senddata(self.session, args)
                payload = wire["pz_log"][0][0]
                self.assertEqual(payload["kind"], output.kind)
                self.assertEqual(payload["segments"], output.segments)
                self.assertEqual("".join(part["text"] for part in payload["segments"]), str(output))
                self.assertNotIn("\x1b", str(payload))
                if output is message:
                    self.assertIn("$You()", str(payload))
                    self.assertIn("<img", str(payload))  # 브라우저는 textContent로만 표시한다.
                with patch.object(self.session, "protocol_key", "telnet"):
                    with patch.object(DefaultCharacter, "msg") as base:
                        Explorer.msg(self.char1, output, session=self.session)
                self.assertEqual(strip_raw_ansi(base.call_args.args[0]), str(output))
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
