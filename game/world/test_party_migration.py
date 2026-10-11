"""v14 일행 명령 변환의 원본·동사·참조·충돌·멱등성."""

from copy import deepcopy
from unittest import TestCase

from commands.shortcuts import parse_definition
from commands.vocabulary import V13_RUNTIME_NAMES, migrate_party_shortcuts

from world import rules


class PartyMigrationTests(TestCase):
    def test_rt43_verbs_variables_sequence_and_chat_unchanged(self):
        old = {"초청": "$1 파티초대", "제외": "$* 파티제외", "큰변수": "$1 $2 $3 $4 $5 $6 $7 $8 $9 파티장위임",
               "달러": "$$ 파티초대", "가입": "파티수락", "상위": "가입",
               "묶음": "파티, $1 파티초대, 가입 해", "문장": "파티초대라는 글 말",
               "개인": "철수 파티초대 대화", "인사": "'파티수락", "새명령": "철수 일행초청"}
        before = deepcopy(old)
        changed = migrate_party_shortcuts(old)
        for key, expected in {"초청": "$1 일행초청", "제외": "$* 일행제외", "큰변수": "$1 $2 $3 $4 $5 $6 $7 $8 $9 일행리더",
                              "달러": "$$ 일행초청", "가입": "일행합류", "묶음": "일행, $1 일행초청, 가입 해"}.items():
            self.assertEqual(changed[key], expected)
        for key in ("문장", "개인", "인사", "상위", "새명령"):
            self.assertEqual(changed[key], old[key])
        self.assertEqual(old, before)
        self.assertEqual(migrate_party_shortcuts(changed), changed)

    def test_rt43_rt44_risky_sequences_indirect_cycles_and_collisions(self):
        old = {"무": "점수", "일행승계": "봐", "무_개인": "장비", "참조": "무",
               "승계참조": "일행승계", "동사": "$*", "위험": "점수, 동사 해", "상위": "위험",
               "a": "b", "b": "a, 위험 해", "손상": {"원본": "파티", "문제": "이전 사유"},
               "구목록": ["점수", "$1 파티초대"], "목록참조": "구목록", "불명": "철수 파티수락", "파티추방": "$*", "옛이름참조": "파티추방", "실제": "파티", "파티": "$*"}
        changed = migrate_party_shortcuts(old)
        self.assertEqual(changed['참조'], '무_개인2')
        self.assertEqual(changed['승계참조'], '일행승계_개인')
        self.assertEqual(changed['실제'], '일행')  # 구 실제 명령이 개인 이름보다 우선
        self.assertEqual(changed['손상'], old['손상'])
        for key in ('동사', '위험', '상위', 'a', 'b', '구목록', '목록참조', '불명', '파티', '파티추방', '옛이름참조'):
            self.assertEqual(changed[key]['원본'], old[key])
            with self.assertRaises(rules.RuleError):
                parse_definition(changed[key])
        self.assertEqual(migrate_party_shortcuts(changed), changed)

    def test_rt44_profile_only_definitions_changed_and_new_names_untouched(self):
        original = rules.new_profile()
        original.update(version=13, command_shortcuts={"초청": "$1 파티초대"})
        before = deepcopy(original)
        changed = rules.migrate_profile(original)
        self.assertEqual(changed['version'], 14)
        for key in before:
            if key not in ('version', 'command_shortcuts'):
                self.assertEqual(changed[key], before[key], key)
        self.assertEqual(original, before)
        self.assertEqual(rules.migrate_profile(changed), changed)
        fresh = rules.new_profile()
        fresh['command_shortcuts'] = {'무': '점수', '메시지': '철수 안녕 대화'}
        self.assertEqual(rules.migrate_profile(fresh), fresh)

    def test_rt44_every_existing_real_command_alias_beats_unsafe_personal_name(self):
        for name in V13_RUNTIME_NAMES:
            with self.subTest(name=name):
                changed = migrate_party_shortcuts({name:'$*', '안전호출':name})
                self.assertEqual(changed['안전호출'], name)
