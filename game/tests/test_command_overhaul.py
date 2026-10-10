"""Issue #46 단계별 최소 Smoke. 격리 SQLite와 실제 후치형 dispatcher를 사용한다."""

from copy import deepcopy
from unittest.mock import patch

from commands.help_pages import help_page
from commands.registry import COMMANDS
from commands.vocabulary import migrate_command_overhaul_shortcuts, migrate_safe_shortcuts
from evennia import create_object
from world import equipment_service, firearm_service, rules
from world.bootstrap import build_world

from tests.item_entity_fixture import NativeItemTest


class CommandOverhaulSmoke(NativeItemTest):
    def setUp(self):
        super().setUp()
        self.rooms = build_world()
        self.char1.location = self.rooms["supply_shop"]
        for module in ("enemies", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))
            self.enterContext(patch(f"typeclasses.{module}.time", return_value=100))
        self.enterContext(patch("commands.character.time", return_value=100))

    def raw(self, command):
        with patch.object(self.char1, "msg") as output, patch.object(self.account, "msg") as account_output:
            completed = []
            self.char1.execute_cmd(command).addCallback(lambda _: completed.append(True))
            self.assertEqual(completed, [True], command)
        return "\n".join(str(call.args[0] if call.args else call.kwargs.get("text", "")) for call in [*output.call_args_list, *account_output.call_args_list])

    def test_phase_a(self):
        for command, expected in (("봐", "보급품 상점"), ("보", "보급품 상점"),
                                  ("도움", "이동"), ("점수", "체력"), ("상", "체력"),
                                  ("가진거", "칩"), ("소", "칩"), ("누구", "Accounts"), ("누", "Accounts")):
            self.assertIn(expected, self.raw(command))
        self.char1.change(lambda p: p.update(credits=100))
        self.assertIn("붕대", self.raw("목록"))
        self.raw("보급관에게 붕대 구입")
        self.assertEqual(self.char1.profile_snapshot()["inventory"]["bandage"], 1)
        self.raw("붕대 팔아")
        self.assertNotIn("bandage", self.char1.profile_snapshot()["inventory"])
        self.char1.location = self.rooms["hq_stairs_3f"]
        self.raw("ㅇ")
        self.assertEqual(self.char1.zone, "hq_stairs_4f")
        self.raw("아")
        self.assertEqual(self.char1.zone, "hq_stairs_3f")
        self.char1.location = self.rooms["grass"]
        gun = firearm_service.create_firearm("scout_pistol", owner_object=self.char1, mode="full_standard")
        equipment_service.equip_item(self.char1, gun, "weapon")
        self.raw("어린청소룡 쳐")
        enemy = self.char1.combat_target()
        before = (enemy.db.hp, self.char1.profile_snapshot()["next_attack_at"], deepcopy(firearm_service.loaded_magazine_item(gun).state))
        self.raw("쏴")
        self.assertEqual(self.char1.profile_snapshot()["queued_action"], "shooting")
        self.assertEqual(before, (enemy.db.hp, self.char1.profile_snapshot()["next_attack_at"], dict(firearm_service.loaded_magazine_item(gun).state)))
        self.assertIn("명령을 확인", self.raw("사격"))
        self.char1.leave_combat()
        self.char1.location = self.rooms["supply_shop"]
        corpses = [create_object("typeclasses.loot.Corpse", key="시험 시체", location=self.char1.location) for _ in range(2)]
        from world import loot_service
        from world.item_entities import api

        self.char2.location = self.char1.location
        for corpse, owner in zip(corpses, (self.char2, self.char1), strict=True):
            corpse.db.decay_at = 1000
            loot_service.populate_source(corpse, [])
            row = api.create_item("bandage", quantity=2, location_kind="corpse_loot", owner_object=corpse)
            loot_service.create_claim(row, reserved_player=owner, assigned_player=owner, protection_until=1000)
        inventory = dict(self.char1.profile_snapshot()["inventory"])
        self.raw("시")
        self.assertEqual(inventory, self.char1.profile_snapshot()["inventory"])
        self.raw("시2")
        self.assertEqual(self.char1.profile_snapshot()["inventory"].get("bandage"), 2)
        self.assertIn("추가했습니다", self.raw("사냥준비 점수, 장비 해 준말"))
        self.assertIn("체력", self.raw("사냥준비"))
        self.assertIn("사용법", self.raw("보 도움"))
        from commands.aliases import ARGUMENT_SHORTCUTS
        with patch.dict(ARGUMENT_SHORTCUTS, {"회수": "$* 가져"}):
            self.assertEqual(help_page("회수", COMMANDS), help_page("가져", COMMANDS))
        self.assertEqual(help_page("시2", COMMANDS), help_page("가져", COMMANDS))
        titles = ["사용법", "예시", "실행 규칙", "제한", "관련 도움말"]
        weapon_help = self.raw("해제 도움")
        self.assertIn("강철 마체테 해제", weapon_help)
        self.assertNotIn("방어구 벗어", weapon_help)
        for cls in COMMANDS:
            if cls.key in ("봐", "출구", "도움", "점수", "가진거", "때려", "목록", "사", "팔아", "쏴", "지도", "경험치", "장비", "착용", "벗어", "가져", "줄임말", "가치"):
                self.assertEqual([title for title, _ in cls.help_sections], titles, cls.key)
                for alias in cls.aliases:
                    self.assertEqual(help_page(alias, COMMANDS), help_page(cls.key, COMMANDS))
        old = {"봐": "$1 공격", "참조": "적 봐", "인사": "사격 회복 말", "정보조회": "정보", "애매": {"원본": "유지"}}
        converted = migrate_safe_shortcuts(old, migrate_command_overhaul_shortcuts)
        self.assertEqual(converted["봐_개인"], "$1 때려")
        self.assertEqual(converted["참조"], "적 봐_개인")
        self.assertEqual(converted["인사"], old["인사"])
        self.assertEqual(converted["애매"], old["애매"])
        self.assertEqual(converted["정보조회"], "점수")
        self.assertEqual(converted, migrate_safe_shortcuts(converted, migrate_command_overhaul_shortcuts))
        self.assertEqual(rules.PROFILE_VERSION, 12)


    def test_phase_b(self):
        gun = firearm_service.create_firearm("scout_pistol", owner_object=self.char1, mode="partial", rounds=7)
        equipment_service.equip_item(self.char1, gun, "weapon")
        firearm_service.create_firearm("scout_pistol", owner_object=self.char1, mode="empty")
        self.create("bandage", quantity=2)
        self.create("flashlight")
        before = deepcopy(self.atomic_state())
        saved = deepcopy(dict(self.char1.db.profile))
        for raw, expected in (("정찰권총 정보", "7/12"), ("정찰권총 2 정보", "0/12"),
                              ("9mm 표준탄창 정보", "잔탄 7발"), ("붕대 정보", "기준 구매가"),
                              ("탐사용손전등 정보", "꺼짐")):
            self.assertIn(expected, self.raw(raw))
            self.assertEqual(before, self.atomic_state())
            self.assertEqual(saved, dict(self.char1.db.profile))
        self.assertIn("아이템", self.raw("정보 도움"))
        self.assertNotIn("레벨·HP/SP", self.raw("정보 도움"))
        self.assertIn("대상", self.raw("정찰권총 3 정보"))
        self.assertEqual(before, self.atomic_state())


    def test_phase_c(self):
        from evennia import search_tag
        from typeclasses.interactables import INTERACTABLES
        from world.content.integrity import errors

        self.char1.location = self.rooms["infirmary"]
        maximum = rules.stats(self.char1.profile_snapshot())["max_hp"]
        self.char1.change(lambda p: p.update(hp=maximum - 20, credits=100, mental=10))
        self.assertIn("예상 비용", self.raw("의무관 봐"))
        with patch("typeclasses.explorers.time", return_value=200):
            self.assertIn("HP 20 회복", self.raw("회복"))
        self.assertEqual((self.char1.profile_snapshot()["hp"], self.char1.profile_snapshot()["credits"], self.char1.profile_snapshot()["mental"]), (maximum, 95, 10))
        self.char1.change(lambda p: p.update(hp=maximum - 30, credits=100))
        self.assertIn("HP 20 회복", self.raw("의무관에게 20 회복"))
        self.assertEqual((self.char1.profile_snapshot()["hp"], self.char1.profile_snapshot()["credits"]), (maximum - 10, 95))
        self.char1.change(lambda p: p.update(credits=0))
        before = deepcopy(self.atomic_state())
        self.assertIn("부족", self.raw("20 회복"))
        self.assertEqual(before, self.atomic_state())
        for raw in ("0 회복", "-2 회복", "1.5 회복", "99999999999999999999 회복", "의무관에게 x 회복"):
            self.assertIn("정수", self.raw(raw))
            self.assertEqual(before, self.atomic_state())
        self.char1.change(lambda p: p.update(credits=100))
        before = deepcopy(self.atomic_state())
        original = self.char1.save_profile
        def fail_save(profile):
            original(profile)
            raise RuntimeError("저장 실패")
        from commands.world_actions import Treat
        command = Treat()
        command.caller, command.args = self.char1, "20"
        with patch.object(self.char1, "save_profile", side_effect=fail_save), self.assertRaises(RuntimeError):
            command.run()
        self.assertEqual(before, self.atomic_state())
        bed = search_tag("infirmary_bed", category="primal_interactable")[0]
        stable = bed.pk
        # 구 DB 위치에서 반복 bootstrap을 수행해 같은 객체만 이동함을 확인한다.
        bed.location = self.rooms["infirmary"]
        for _ in range(2):
            build_world()
            self.assertEqual([obj.pk for obj in search_tag("infirmary_bed", category="primal_interactable")], [stable])
            self.assertEqual(bed.location, self.rooms["recovery_room"])
        from world.content import ITEMS
        with patch.dict(ITEMS, {key: value for key, value in ITEMS.items() if key != "test_pistol"}, clear=True):
            self.assertEqual(errors(INTERACTABLES), [])
        self.char1.location = self.rooms["recovery_room"]
        credits = self.char1.profile_snapshot()["credits"]
        self.assertIn("체력과 정신력을 모두 회복", self.raw("휴식"))
        profile = self.char1.profile_snapshot()
        self.assertEqual((profile["hp"], profile["mental"], profile["credits"]), (maximum, rules.stats(profile)["max_mental"], credits))
        self.assertIn("2*H", self.raw("회복 도움"))
        self.assertIn("명령을 확인", self.raw("진료"))
        old = rules.new_profile()
        old.update(version=7, command_shortcuts={"응급": ["회복"], "의료": ["진료"], "전투": ["사격"], "인사": ["진료 사격 말"]})
        migrated = rules.migrate_profile(old)
        self.assertEqual(migrated["command_shortcuts"], {"응급": "붕대 사용", "의료": "회복", "전투": "쏴", "인사": "진료 사격 말"})
        self.assertEqual(rules.migrate_profile(migrated), migrated)
        v11 = rules.new_profile()
        v11.update(version=11, command_shortcuts={"응급": "회복", "애매": "붕대 정보", "의료": "진료"})
        moved = rules.migrate_profile(v11)["command_shortcuts"]
        self.assertEqual(moved["응급"], "붕대 사용")
        self.assertEqual(moved["의료"], "회복")
        self.assertEqual(moved["애매"]["원본"], "붕대 정보")
        self.assertIn("재등록", moved["애매"]["문제"])
        migrated["command_shortcuts"]["의료"] = "회복"
        self.assertEqual(rules.migrate_profile(migrated)["command_shortcuts"]["의료"], "회복")
        for level, expected in ((10, 5), (50, 9), (99, 14), (100, 24)):
            profile = rules.new_profile()
            profile.update(xp=rules.xp_threshold(level), hp=1)
            self.assertEqual(rules.treatment_quote(profile, 20, safe=True), (20, expected))
        profile.update(xp=rules.xp_threshold(10))
        self.assertEqual(rules.treatment_quote(profile, 5, safe=True), (5, 2))
