"""Issue #48 FREEZE의 명령·멤버십·세션·전술 경계 검증."""


from commands.help_pages import help_page
from commands.party import PARTY_COMMANDS
from commands.registry import COMMANDS
from typeclasses.explorers import Explorer
from world import text as ft

from tests.base import GameCommandTest


class PartyCommandContractTests(GameCommandTest):
    character_typeclass = Explorer

    def test_rt01_all_sixteen_commands_aliases_help_and_old_verbs_absent(self):
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
