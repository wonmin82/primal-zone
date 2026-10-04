"""DB/Evennia 없이 문법·확장 한계와 확인 안전성을 검증한다."""

from copy import deepcopy
from unittest import TestCase

from commands import shortcuts as sc

from world import rules


class CommandShortcutRulesTests(TestCase):
    def test_sequence_and_definition_keep_commas_in_chat(self):
        self.assertEqual(sc.parse_sequence("상태, 장비"), ["상태", "장비"])
        self.assertEqual(sc.parse_shortcut_definition("상태, 장비, 소지품 해"), ["상태", "장비", "소지품"])
        for definition in ("장비", "안녕, 반가워 말", "'안녕, 반가워 해"):
            self.assertEqual(sc.parse_shortcut_definition(definition), [definition])

    def test_malformed_sequence_is_never_silently_trimmed(self):
        for definition in ("상태 해", "상태,, 장비 해", ", 상태 해", "상태, 장비, 해", "해"):
            with self.subTest(definition=definition), self.assertRaises(rules.RuleError):
                sc.parse_shortcut_definition(definition)

    def test_name_policy(self):
        for name in ("점검", "무기점", "ㅈㄱ", "gear", "go2", "_", "모두", "가" * sc.MAX_NAME_CHARACTERS):
            self.assertEqual(sc.shortcut_name(name), name)
        self.assertEqual(sc.shortcut_name("Gear"), "gear")
        for name in ("", "공백 이름", "a,b", "a=b", "'말", "가" * (sc.MAX_NAME_CHARACTERS + 1)):
            with self.subTest(name=name), self.assertRaises(rules.RuleError):
                sc.shortcut_name(name)

    def test_nested_and_inline_sequences_expand_exact_names_only(self):
        shortcuts = {"점검": ["상태", "장비", "소지품"], "출발": ["점검", "북"]}
        sc.validate_shortcut_graph(shortcuts)
        self.assertEqual(sc.expand_shortcuts(["출발"], shortcuts), ["상태", "장비", "소지품", "북"])
        self.assertEqual(sc.expand_shortcuts(["점검", "북", "북"], shortcuts),
                         ["상태", "장비", "소지품", "북", "북"])
        self.assertEqual(sc.expand_shortcuts(["점검 말", "오늘 점검했어 말"], shortcuts),
                         ["점검 말", "오늘 점검했어 말"])
        self.assertEqual(sc.expand_shortcuts(["상태, 장비 해"], shortcuts), ["상태", "장비"])
        self.assertEqual(sc.expand_shortcuts(["점검"], shortcuts, {"점검"}), ["점검"])

    def test_all_cycle_lengths_and_malformed_saved_definitions(self):
        for shortcuts in ({"a": ["a"]}, {"a": ["b"], "b": ["a"]},
                          {"a": ["b"], "b": ["c"], "c": ["a"]},
                          {"a": []}, {"a": "상태"}, {"a": [None]}):
            before = deepcopy(shortcuts)
            with self.subTest(shortcuts=shortcuts), self.assertRaises(rules.RuleError):
                sc.validate_shortcut_graph(shortcuts)
            self.assertEqual(shortcuts, before)

    def test_count_depth_and_expanded_size_boundaries(self):
        self.assertEqual(len(sc.expand_shortcuts(["상태"] * sc.MAX_COMMANDS, {})), sc.MAX_COMMANDS)
        with self.assertRaises(rules.RuleError):
            sc.expand_shortcuts(["상태"] * (sc.MAX_COMMANDS + 1), {})
        graph = {f"a{i}": [f"a{i + 1}"] for i in range(sc.MAX_DEPTH - 1)}
        graph[f"a{sc.MAX_DEPTH - 1}"] = ["상태"]
        self.assertEqual(sc.expand_shortcuts(["a0"], graph), ["상태"])
        graph[f"a{sc.MAX_DEPTH - 1}"] = ["더깊음"]
        graph["더깊음"] = ["상태"]
        with self.assertRaises(rules.RuleError):
            sc.expand_shortcuts(["a0"], graph)
        limit = sc.MAX_EXPANDED_CHARACTERS
        self.assertEqual(sc.expand_shortcuts(["x" * limit], {}), ["x" * limit])
        with self.assertRaises(rules.RuleError):
            sc.expand_shortcuts(["x" * limit, "북"], {})

    def test_confirmation_requires_current_unexpired_request(self):
        shortcuts = {"b": ["장비"], "a": ["상태"]}
        request = sc.delete_all_request(shortcuts, 100)
        self.assertEqual(request["fingerprint"], sc.shortcut_fingerprint(dict(reversed(list(shortcuts.items())))))
        sc.validate_delete_all(request, shortcuts, 159.99)
        for pending, current, now in ((None, shortcuts, 100), (request, shortcuts, 160),
                                      (request, shortcuts, 99), (request, {"c": ["소지품"]}, 100)):
            with self.subTest(now=now), self.assertRaises(rules.RuleError):
                sc.validate_delete_all(pending, current, now)
        self.assertIsNone(sc.delete_all_request({}, 100))

    def test_v6_migration_preserves_entire_gameplay_and_is_idempotent(self):
        old = rules.new_profile()
        old.update(version=6, xp=155, credits=93, hp=41, storage={"scrap": 5}, visited=["dock", "ridge"])
        old["skills"]["heavy"] = 2
        old["quests"]["radio_tower"]["record_read"] = True
        old.pop("command_shortcuts")
        old.pop("mental")
        old.pop("recovery_effects")
        before = deepcopy(old)
        migrated = rules.migrate_profile(old)
        self.assertEqual(migrated, {**old, "version": rules.PROFILE_VERSION, "command_shortcuts": {},
                                    "mental": rules.stats(old)["max_mental"], "recovery_effects": []})
        self.assertEqual(rules.migrate_profile(migrated), migrated)
        self.assertEqual(old, before)
        for version in range(1, 7):
            profile = {**before, "version": version}
            result = rules.migrate_profile(profile)
            self.assertEqual(result["command_shortcuts"], {})
            self.assertEqual(result["version"], rules.PROFILE_VERSION)
            for key in ("xp", "hp", "credits", "inventory", "equipment", "storage", "visited"):
                self.assertEqual(result[key], profile[key])
