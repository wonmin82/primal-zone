"""실제 dispatcher·로그인/reload 경로와 도움말 어휘 회귀."""

from copy import deepcopy
from unittest.mock import Mock, patch

from commands.aliases import SHORTCUTS
from commands.help_pages import HELP_CATEGORIES, category_page, help_page, root_page, shortcut_page
from commands.registry import COMMANDS
from evennia.utils.dbserialize import deserialize
from typeclasses.explorers import Explorer
from world.content.directions import DIRECTION_SHORTCUTS, DIRECTIONS
from world.content.headquarters import ROOF_SIDES

from tests.base import WorldCommandTest


def tokens(value, role):
    return [part["text"] for part in value.segments if part["role"] == role]


class VocabularyTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        for player in (self.char1, self.char2):
            player.location = self.rooms["dock"]
            player.push_state = Mock()
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))

    def raw(self, command):
        with patch.object(self.char1, "msg") as output:
            completed = []
            self.char1.execute_cmd(command).addCallback(lambda _: completed.append(True))
            self.assertEqual(completed, [True])
        return "\n".join(str(call.args[0]) for call in output.call_args_list if call.args)

    def test_inventory_aliases_and_removed_commands_are_not_active(self):
        # 제거된 명령의 불변성을 실제 10초 자연회복 경계와 분리한다.
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        self.char1.reconcile_recovery(emit_prompt=False)
        outputs = [self.raw(command) for command in ("가진거", "가진", "소지", "소지품", "소")]
        self.assertEqual(len(set(outputs)), 1)
        self.assertIn("가진거", outputs[0])
        self.char1.location = self.rooms["weapon_shop"]
        for old in ("상점", "shop", "도주", "응급치료", "firstaid", "붕대", "방어", "guard", "내리기"):
            before = self.char1.profile_snapshot()
            self.assertIn("명령을 확인", self.raw(old), old)
            self.assertEqual(self.char1.profile_snapshot(), before)
        for command in ("목록", "무기상 메뉴"):
            self.assertIn("절단마체테", self.raw(command))

    def test_healing_aliases_bandage_and_medical_services(self):
        for command in ('치료', '힐', 'heal'):
            self.char1.change(lambda p: p.update(hp=20, mental=40, skill_ready_at={}))
            before = self.char1.profile_snapshot()
            self.raw(command)
            after = self.char1.profile_snapshot()
            self.assertGreater(after['hp'], 20)
            self.assertEqual(after['mental'], 30)
            self.assertEqual(after['inventory'], before['inventory'])
        self.char1.change(lambda p: p.update(hp=20))
        self.raw('붕대 사용')
        self.assertEqual(self.char1.profile_snapshot()['inventory']['bandage'], 2)
        self.char1.location = self.rooms['infirmary']
        for command in ('회복', '의무관 회복', '의무관에게 회복', '휴식', '침대 휴식', '침대에서 휴식', 'rest'):
            self.char1.location = self.rooms['infirmary'] if '회복' in command else self.rooms['recovery_room']
            self.char1.change(lambda p: p.update(hp=1, credits=1000))
            before = self.char1.profile_snapshot()
            output = self.raw(command)
            self.assertIn('HP 59 회복' if command in ('회복', '의무관 회복', '의무관에게 회복', 'treat') else '휴식하며', output)
            self.assertGreater(self.char1.profile_snapshot()['hp'], 1)
            if '회복' in command:
                self.assertEqual(self.char1.profile_snapshot()['credits'], before['credits'] - 12)
            else:
                self.assertEqual(self.char1.profile_snapshot()['credits'], before['credits'])
            for field in ('inventory', 'skills'):
                self.assertEqual(self.char1.profile_snapshot()[field], before[field])

    def test_jamo_direction_shortcuts_traverse_roof_round_trips(self):
        for source, direction in DIRECTION_SHORTCUTS.items():
            if direction not in ROOF_SIDES:
                continue  # 수직 실제 이동은 Issue #46 단계 A Smoke에서 확인한다.
            self.char1.location = self.rooms["support_roof"]
            self.raw(source)
            self.assertEqual(self.char1.zone, ROOF_SIDES[direction])
            reverse = DIRECTIONS[direction]["opposite"]
            self.raw(DIRECTIONS[reverse]["shortcut"])
            self.assertEqual(self.char1.zone, "support_roof")

    def test_reserved_names_and_released_ga_shortcut(self):
        for name in ("소", "ㅂㄷ", "ㄴㄷ", "ㄴㅅ", "ㅂㅅ", "치료", "힐", "heal"):
            self.raw(f"{name} 상태 줄임말")
            self.assertEqual(self.char1.profile_snapshot()["command_shortcuts"], {})
        self.raw("가 상태 줄임말")
        self.assertEqual(self.char1.profile_snapshot()["command_shortcuts"], {"가": "상태"})
        self.assertIn("체력", self.raw("가"))

    def test_healing_is_active_and_defense_is_passive(self):
        for query in ('치료', '힐', 'heal', '회복', '휴식', '사용'):
            self.assertIn('사용법', self.raw(query + ' 도움말'))
        registered = {name for cls in COMMANDS for name in (cls.key, *cls.aliases)}
        self.assertTrue({'치료', '힐', 'heal'}.issubset(registered))
        self.assertTrue({'방어', 'guard', '응급처치', 'firstaid'}.isdisjoint(registered))

    def test_help_taxonomy_routes_semantics_and_shortcut_ssot(self):
        commands = [cls for cls in COMMANDS if getattr(cls, "input_style", None)]
        self.assertEqual(len(HELP_CATEGORIES), 6)
        root = root_page()
        self.assertNotIn("8방향 이동", tokens(root, "command"))
        membership = []
        for category, data in HELP_CATEGORIES.items():
            membership.extend(cls for cls in commands if cls.category == category)
            for query in (category, data["query"]):
                self.assertEqual(help_page(query, commands), category_page(category, commands))
            for example in data["examples"]:
                self.assertTrue(any(cls.key == example and cls.category == category for cls in commands))
        self.assertCountEqual(membership, commands)
        for query in (*DIRECTIONS, *[data["alias"] for data in DIRECTIONS.values()], *DIRECTION_SHORTCUTS):
            self.assertIn("이동·탐사", self.raw(query + " 도움말"))
        self.assertTrue(set(data["alias"] for data in DIRECTIONS.values()).issubset(
            set(tokens(category_page("이동·탐사", commands), "direction"))))
        self.assertIn("가진거", self.raw("소 도움말"))
        self.assertIn("소속 파티", self.raw("파티"))
        self.assertIn("사용법", self.raw("파티 도움말"))
        self.assertIn("묶음 실행", self.raw("입력 도움말"))
        self.assertIn("'도움말' 대상을 찾을 수 없습니다", self.raw("도움말 공격"))
        page = shortcut_page()
        self.assertEqual(set(tokens(page, "direction")), set(DIRECTION_SHORTCUTS.values()))
        for source, target in SHORTCUTS.items():
            self.assertIn(source, tokens(page, "command"))
            self.assertIn(target, tokens(page, "direction" if source in DIRECTION_SHORTCUTS else "command"))
        self.assertNotIn("가", tokens(page, "command"))

    def test_real_new_puppet_and_live_session_reload_have_distinct_location_policy(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        self.account.unpuppet_object(self.session)
        self.account.puppet_object(self.session, self.char1)
        self.assertEqual(self.char1.zone, "staging_room")
        self.char1.location = self.rooms["support_3f_c"]
        self.char1.change(lambda p: p.update(credits=87, storage={"scrap": 3}, command_shortcuts={"점검": ["상태"]}))
        before = deepcopy(self.char1.profile_snapshot())
        # 실제 ServerSession.at_sync + ORM Object 재연결: hook을 mock하지 않는다.
        self.session.puid = self.char1.id
        self.session.at_sync()
        self.assertEqual(self.session.puppet.zone, "support_3f_c")
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.account.unpuppet_object(self.session)
        self.assertIsNone(self.char1.location)
        self.account.puppet_object(self.session, self.char1)
        self.assertEqual(self.char1.zone, "staging_room")
        self.assertEqual(self.char1.profile_snapshot(), before)
        self.assertEqual(self.char1.home, self.rooms["dock"])

    def test_v7_snapshot_migration_is_read_only_and_saved_profile_is_latest(self):
        old = self.char1.profile_snapshot()
        old.update(version=7, queued_action="heal", command_shortcuts={"소": ["가방"], "연결": ["소"]})
        old["skills"] = {"heavy": 1, "guard": 1, "heal": 1}
        self.char1.db.profile = old
        with patch.object(self.char1, "save_profile") as save:
            snapshot = self.char1.profile_snapshot()
            save.assert_not_called()
        self.assertEqual(deserialize(self.char1.db.profile), old)
        self.assertEqual(snapshot["command_shortcuts"], {"소_개인": "가진거", "연결": "소_개인"})
        self.char1.profile()
        self.assertEqual(deserialize(self.char1.db.profile), snapshot)
