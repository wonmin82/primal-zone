"""DB/Evennia 없이 문법·확장 한계와 확인 안전성을 검증한다."""

from copy import deepcopy
from unittest import TestCase

from commands import shortcuts as sc

from world import rules


class CommandShortcutRulesTests(TestCase):
    def test_repeated_star_is_bounded_before_string_allocation(self):
        import tracemalloc

        definition = sc.parse_definition("$*" * 1000)
        tracemalloc.start()
        try:
            with self.assertRaises(rules.RuleError):
                definition.bind("x" * 2000)
            self.assertLess(tracemalloc.get_traced_memory()[1], 131072)
        finally:
            tracemalloc.stop()

    def test_segment_binding_is_lazy_and_has_a_remaining_budget(self):
        segments = sc.parse_definition("상태, $*$* 해").bind_segments("x" * 2000)
        self.assertEqual(segments[0].render(), "상태")
        with self.assertRaises(rules.RuleError):
            segments[1].render()
        with self.assertRaises(rules.RuleError):
            sc.parse_definition("$*").bind_segments("x" * 1001)[0].render(maximum=1000)

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
        for name in ("점검", "무기점", "ㅈㄱ", "가", "gear", "go2", "_", "모두", "가" * sc.MAX_NAME_CHARACTERS):
            self.assertEqual(sc.shortcut_name(name), name)
        self.assertEqual(sc.shortcut_name("Gear"), "gear")
        for name in ("", "공백 이름", "a,b", "a=b", "'말", "가" * (sc.MAX_NAME_CHARACTERS + 1)):
            with self.subTest(name=name), self.assertRaises(rules.RuleError):
                sc.shortcut_name(name)

    def test_variable_binding_and_single_pass_literals(self):
        for source, arguments, expected in (
            ("$1에게 $2 줘", "철수  20칩", "철수에게 20칩 줘"),
            ("$1에게 $* 줘", "철수 20칩", "철수에게 철수 20칩 줘"),
            ("북 $1", "보기", "북 보기"),
            ("$*", "상태", "상태"),
            ("@help $1", "look", "@help look"),
            ("$$1 $$* $$$$", "", "$1 $* $$"),
            ("$* 말", "$1   $*", "$1 $* 말"),
            ("$$You()라고 말해 말", "", "$You()라고 말해 말"),
        ):
            with self.subTest(source=source):
                self.assertEqual(sc.parse_definition(source).bind(arguments), (expected,))
        self.assertEqual(sc.parse_definition("$* 말, 상태 해").bind("상태, 장비 해"),
                         ("상태, 장비 해 말", "상태"))
        self.assertEqual(sc.parse_definition("$* $2").bind("a b"), ("a b b",))
        self.assertEqual(sc.parse_definition(" ".join(f"${n}" for n in range(1, 10))).bind(
            " ".join(map(str, range(1, 10)))), ("1 2 3 4 5 6 7 8 9",))

    def test_local_syntax_and_argument_validation_only(self):
        for source in ("$0", "$10", "$abc", "$", "$2", "$1 $3", "a\n말", "a" * 2001):
            with self.subTest(source=source), self.assertRaises(rules.RuleError):
                sc.parse_definition(source)
        for source, args in (("$1 $2", "a"), ("$1", "a b"), ("상태", "a"),
                             ("$*", ""), ("$*", "a\n"), ("$*", "a" * 2001)):
            with self.subTest(source=source, args=args), self.assertRaises(rules.RuleError):
                sc.parse_definition(source).bind(args)
        for source in ("A", "B", "$*", "없는명령", "A, A 해", "a" * 2000):
            sc.parse_definition(source)  # 참조·존재·실행량 검사는 등록 문법의 책임이 아니다.
        self.assertEqual(sc.parse_definition("$*").bind("x" * 2000), ("x" * 2000,))

    def test_safe_legacy_conversion_preserves_boundaries(self):
        for values, expected in ((["장비"], "장비"), (["북 보기", "상태"], "북 보기, 상태 해")):
            self.assertEqual(sc.safe_legacy_definition(values), expected)
        for values in ([], [None], ["안녕, 반가워 말", "상태"], ["상태, 장비 해"], ["$10"]):
            self.assertIsNone(sc.safe_legacy_definition(values))

    def test_store_fingerprint_detects_all_values_and_rejects_unsupported(self):
        store = {"a": "장비", "b": ["상태"], "c": None, "d": {"n": 1}}
        before = deepcopy(store)
        for key in store:
            changed = {**store, key: "different"}
            self.assertNotEqual(sc.shortcut_fingerprint(store), sc.shortcut_fingerprint(changed))
        self.assertEqual(store, before)
        for value in ([], None, {1: "상태"}, {"a": object()}, {"a": float("nan")}):
            with self.assertRaises(rules.RuleError):
                sc.shortcut_fingerprint(value)

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
                                    "mental": rules.stats(old)["max_mental"], "recovery_effects": [], "skills": rules.growth_defaults()["skills"]})
        self.assertEqual(rules.migrate_profile(migrated), migrated)
        self.assertEqual(old, before)
        for version in range(1, 7):
            profile = {**before, "version": version}
            result = rules.migrate_profile(profile)
            self.assertEqual(result["command_shortcuts"], {})
            self.assertEqual(result["version"], rules.PROFILE_VERSION)
            for key in ("xp", "hp", "credits", "inventory", "equipment", "storage", "visited"):
                self.assertEqual(result[key], profile[key])


class ShortcutMigrationV11Tests(TestCase):
    def test_every_supported_version_preserves_gameplay_and_only_safe_lists_convert(self):
        shortcuts = {"장확": ["장비"], "정찰": ["북 보기", "상태"],
                     "대화": ["안녕, 반가워 말", "상태"], "빈": [], "꺼짐": None,
                     "잘못된 이름": ["상태"], "Gear": ["장비"], "gear": ["상태"],
                     "변수": "$1 보기", "오류": "$10"}
        for version in range(7, 12):
            old = rules.new_profile()
            old.update(version=version, command_shortcuts=deepcopy(shortcuts), xp=234, credits=77,
                       storage={"scrap": 3}, visited=["dock", "ridge"], hp=30, mental=25)
            before = deepcopy(old)
            migrated = rules.migrate_profile(old)
            self.assertEqual(migrated["version"], 12)
            self.assertEqual(old, before)
            for key in ("xp", "credits", "storage", "visited", "hp", "mental", "quests", "inventory", "equipment"):
                baseline = rules.migrate_profile({**before, "command_shortcuts": {}})
                self.assertEqual(migrated[key], baseline[key], (version, key))
            expected = deepcopy(shortcuts)
            if version < 11:
                expected.update(장확="장비", 정찰="북 봐, 점수 해")
            else:
                expected.update(정찰=["북 봐", "점수"])
            expected.update(대화=["안녕, 반가워 말", "점수"], 변수="$1 봐")
            self.assertEqual(migrated["command_shortcuts"], expected, version)
            self.assertEqual(rules.migrate_profile(migrated), migrated)

    def test_unsupported_store_does_not_break_other_migrations_or_initialize_it(self):
        for value in (None, [], "broken", {1: ["상태"]}, {"정상": ["상태"], "비활성": None}):
            old = rules.new_profile()
            old.update(version=7, command_shortcuts=value, credits=83)
            migrated = rules.migrate_profile(old)
            self.assertEqual(migrated["credits"], 83)
            self.assertEqual(migrated["version"], 12)
            expected = {"정상": "점수", "비활성": None} if isinstance(value, dict) and "정상" in value else value
            self.assertEqual(migrated["command_shortcuts"], expected)

    def test_v8_v10_safe_transform_reserves_abnormal_original_keys(self):
        old = rules.new_profile()
        old.update(version=7, command_shortcuts={"소": ["가방"], "소_개인": None,
                   "사격": ["붕대"], "사격_개인": [], "참조": ["소", "사격"], "붕대": None})
        result = rules.migrate_profile(old)["command_shortcuts"]
        self.assertEqual(result, {"소_개인": None, "소_개인2": "가진거", "사격_개인": [],
                                 "사격_개인2": "붕대 사용", "참조": "소_개인2, 사격_개인2 해", "붕대": None})

    def test_v11_does_not_retry_lists_or_rename_old_names(self):
        old = rules.new_profile()
        old["command_shortcuts"] = {"사격": ["상태"], "Gear": ["장비"]}
        self.assertEqual(rules.migrate_profile(old)["command_shortcuts"], old["command_shortcuts"])

    def test_valid_old_string_vocabulary_and_invalid_values_are_isolated(self):
        old = rules.new_profile()
        old.update(version=7, command_shortcuts={"표시": "가방", "전투": "붕대", "잘못": [None]})
        self.assertEqual(rules.migrate_profile(old)["command_shortcuts"],
                         {"표시": "가진거", "전투": "붕대 사용", "잘못": [None]})

    def test_historical_rename_does_not_collide_with_abnormal_casefold_key(self):
        old = rules.new_profile()
        old.update(version=7, command_shortcuts={"HEAL": ["가방"], "heal_개인": None, "오류": "$10"})
        self.assertEqual(rules.migrate_profile(old)["command_shortcuts"],
                         {"HEAL_개인2": "가진거", "heal_개인": None, "오류": "$10"})
