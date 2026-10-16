"""게임/DB 없이 선언·등록 실패와 불변성 경계를 확인한다."""

from dataclasses import FrozenInstanceError, replace
from functools import lru_cache, partial, wraps
from unittest import TestCase

from world.actions.registry import (
    RegistryError,
    compile_manifest,
    normal_all_guards,
    validate_argument,
)
from world.actions.schema import (
    ActionBinding,
    ActionDefinition,
    ArgumentDefinition,
    ContentPackage,
    DefaultTargetPolicy,
    PackageManifest,
    ProviderDefinition,
    ReferenceKind,
    RoleDefinition,
    ServiceDefinition,
    SyntaxVariant,
    TargetReference,
    TargetScope,
    VerbDefinition,
)


def handler(context):
    return context


def package():
    role = RoleDefinition("provider", (ReferenceKind.OBJECT,))
    return ContentPackage(
        "fixture.package",
        verbs=(VerbDefinition("fixture.verb", "검증", ("살펴",)),),
        actions=(ActionDefinition("fixture.action", "fixture.verb", (role,),
                                  (SyntaxVariant("normal", r"(?P<provider>.+)"),)),),
        services=(ServiceDefinition("fixture.service", handler, (role,)),),
        bindings=(ActionBinding("fixture.binding", "fixture.provider", "fixture.action",
                                "fixture.service"),),
        providers=(ProviderDefinition("fixture.provider", "검증장치", "fixture.group", "room:1"),),
    )


class ActionRegistryTests(TestCase):
    def test_inventory_collection_is_a_current_source_and_never_a_provider(self):
        p = package()
        for role in (RoleDefinition("provider", (ReferenceKind.INVENTORY,)),
                     RoleDefinition("source", (ReferenceKind.INVENTORY, ReferenceKind.ITEM)),
                     RoleDefinition("source", (ReferenceKind.INVENTORY,), scope=TargetScope.STORAGE)):
            with self.subTest(role=role), self.assertRaisesRegex(RegistryError, "Source"):
                self.compile(replace(p, actions=(replace(p.actions[0], roles=(role,)),)))
        source = RoleDefinition("source", (ReferenceKind.INVENTORY,), required=False)
        self.compile(replace(p, actions=(replace(p.actions[0], roles=(*p.actions[0].roles, source)),)))

    def compile(self, value=None, protected=()):
        return compile_manifest(PackageManifest((value or package(),)), protected)

    def paired_patterns(self, left, right, *, roles_left=None, roles_right=None):
        p = package()
        a = replace(p.actions[0], variants=(SyntaxVariant("normal", left),),
                    roles=roles_left or p.actions[0].roles)
        b = replace(a, id="fixture.second_action", variants=(SyntaxVariant("normal", right),),
                    roles=roles_right or a.roles)
        binding = replace(p.bindings[0], id="fixture.second_binding", action_id=b.id)
        return replace(p, actions=(a, b), bindings=(*p.bindings, binding))

    def test_different_regex_spellings_with_overlapping_languages_are_rejected(self):
        p = self.paired_patterns(r"(?P<provider>.+)", r"(?P<provider>[가-힣]+)")
        with self.assertRaises(RegistryError):
            self.compile(p)

    def test_same_action_different_variant_languages_are_checked_for_overlap(self):
        p = package()
        for left, right in (
            (r".+", r".+"),
            (r".+", r"[가-힣]+"),
            (r"\d+", r"[0-9]+"),
            (r".+", r"검증기"),
            (r"검증기", r"검증기"),
            (r"검증기+", r"검증기{1,3}"),
        ):
            action = replace(p.actions[0], variants=(
                SyntaxVariant("broad", f"(?P<provider>{left})"),
                SyntaxVariant("narrow", f"(?P<provider>{right})"),
            ))
            with self.subTest(left=left, right=right), self.assertRaises(RegistryError):
                self.compile(replace(p, actions=(action,)))
        # Provider 선언을 유지한 같은 Action에서 capture 이름만 바꾸어도 구분되지 않는다.
        subject = RoleDefinition("subject", (ReferenceKind.OBJECT,),
                                 default=DefaultTargetPolicy.FIRST_LEGACY_ORDER, required=False)
        action = replace(p.actions[0], roles=(*p.actions[0].roles, subject), variants=(
            SyntaxVariant("provider-name", r"(?P<provider>.+)"),
            SyntaxVariant("subject-name", r"(?P<subject>.+)"),
        ))
        with self.assertRaises(RegistryError):
            self.compile(replace(p, actions=(action,)))

    def all_pattern_package(self, normal=r"(?P<source>.+)에서 (?P<provider>.+)"):
        p = package()
        source = RoleDefinition("source", (ReferenceKind.CORPSE,), allow_all=True)
        action = replace(p.actions[0], roles=(*p.actions[0].roles, source), variants=(
            SyntaxVariant("ordinary-arbitrary-id", normal),
            SyntaxVariant("collect-arbitrary-id", "모든 " + normal, all_roles=("source",)),
        ))
        return replace(p, actions=(action,))

    def test_same_action_supported_disjoint_variants_and_explicit_suffix_remain_valid(self):
        p = package()
        for variants in (
            (SyntaxVariant("first", r"(?P<provider>사과)"),
             SyntaxVariant("second", r"(?P<provider>바나나)")),
            (SyntaxVariant("first", r"(?P<provider>[가-힣]+)"),
             SyntaxVariant("second", r"(?P<provider>[0-9]+)")),
            (SyntaxVariant("first", r"(?P<provider>.+)"),
             SyntaxVariant("second", r"(?P<provider>.+)", "확정", True)),
        ):
            self.compile(replace(p, actions=(replace(p.actions[0], variants=variants),)))

    def test_same_action_unknown_and_casefold_suffix_conflicts_have_pair_diagnostics(self):
        p = package()
        for pattern, suffixes, reason in (
            (r"(?P<provider>.+)", ("CHECK", "check"), "OVERLAP"),
            (r"(?P<provider>(?=가).+)", ("", ""), "UNKNOWN"),
            (r"(?P<provider>.+)(?P=provider)", ("", ""), "UNKNOWN"),
            (r"(?i:(?P<provider>.+))", ("", ""), "UNKNOWN"),
        ):
            action = replace(p.actions[0], variants=(SyntaxVariant("one", pattern, suffixes[0]),
                                                    SyntaxVariant("two", pattern, suffixes[1])))
            with self.subTest(pattern=pattern), self.assertRaises(RegistryError) as failure:
                self.compile(replace(p, actions=(action,)))
            message = str(failure.exception)
            for value in ("Verb=fixture.verb", "Provider=fixture.provider",
                          "Action=fixture.action/fixture.action", "Variant=one/two", reason):
                self.assertIn(value, message)

    def test_variant_metadata_is_validated_before_language_pairs(self):
        p = package()
        first = SyntaxVariant("first", r"(?P<provider>.+)")
        for second, reason in (
            (replace(first, pattern=r"(?P<provider>[가-힣]+)"), "Variant ID"),
            (SyntaxVariant("second", "("), "문법 정규식 오류"),
            (SyntaxVariant("second", 1), "문법 정규식은 문자열"),
        ):
            with self.subTest(variant=second), self.assertRaisesRegex(RegistryError, reason):
                self.compile(replace(p, actions=(replace(p.actions[0], variants=(first, second)),)))

    def test_normal_all_contract_uses_proven_ast_and_shared_runtime_guard(self):
        p = self.all_pattern_package()
        self.compile(p)
        action = p.actions[0]
        self.assertEqual(normal_all_guards(action, action.variants[0]), (("source", "모든 "),))
        self.assertEqual(normal_all_guards(action, action.variants[1]), ())
        # 자기 Provider도 source 역할은 별도로 선언하므로 같은 증명을 재사용한다.
        self.compile(replace(p, actions=(replace(action, provider_from="source"),)))

    def test_normal_all_contract_rejects_unsafe_capture_splits_and_unknown_patterns(self):
        cases = (
            r"(?P<source>[가-힣]+) (?P<provider>.+)",
            r"(?P<source>.+?) (?P<provider>.+)",
            r"(?P<source>.*) (?P<provider>.+)",
            r"(?P<provider>.+) (?P<source>.+)",
            r"(?P<source>.+)? (?P<provider>.+)",
            r"(?P<source>(?=가).+) (?P<provider>.+)",
            r"(?i:(?P<source>.+) (?P<provider>.+))",
        )
        for pattern in cases:
            p = self.all_pattern_package(pattern)
            action = p.actions[0]
            with self.subTest(pattern=pattern):
                self.assertEqual(normal_all_guards(action, action.variants[0]), ())
                with self.assertRaises(RegistryError):
                    self.compile(p)

    def test_normal_all_contract_cannot_escape_declaration_or_cross_action_boundaries(self):
        p = self.all_pattern_package()
        action = p.actions[0]
        ordinary, collective = action.variants
        for changed in (
            replace(collective, all_roles=()),
            replace(collective, confirmation_required=True),
            replace(collective, pattern=collective.pattern + " 추가"),
        ):
            with self.subTest(variant=changed), self.assertRaises(RegistryError):
                self.compile(replace(p, actions=(replace(action, variants=(ordinary, changed)),)))
        second = replace(action, id="fixture.other_action", variants=(collective,))
        binding = replace(p.bindings[0], id="fixture.other_binding", action_id=second.id)
        with self.assertRaises(RegistryError):
            self.compile(replace(p, actions=(replace(action, variants=(ordinary,)), second),
                                 bindings=(*p.bindings, binding)))
        provider = replace(p.actions[0].roles[0], allow_all=True)
        provider_action = replace(action, roles=(provider,), variants=(
            SyntaxVariant("ordinary", r"(?P<provider>.+)"),
            SyntaxVariant("collective", r"모든 (?P<provider>.+)", all_roles=("provider",)),
        ))
        with self.assertRaises(RegistryError):
            self.compile(replace(p, actions=(provider_action,)))
        # 양쪽 접미어가 정상이어도 확인 정책이 다르면 예약 prefix 계약을 공유하지 않는다.
        variants = (replace(ordinary, suffix="확정"),
                    replace(collective, suffix="확정", confirmation_required=True))
        with self.assertRaises(RegistryError):
            self.compile(replace(p, actions=(replace(action, variants=variants),)))

    def test_different_capture_positions_do_not_prove_type_disjointness(self):
        provider = RoleDefinition("provider", (ReferenceKind.OBJECT,))
        p = self.paired_patterns(
            r"(?P<provider>.+) (?P<subject>.+)", r"(?P<source>.+) (?P<provider>.+)",
            roles_left=(provider, RoleDefinition("subject", (ReferenceKind.ITEM,))),
            roles_right=(provider, RoleDefinition("source", (ReferenceKind.DOOR,))))
        with self.assertRaises(RegistryError):
            self.compile(p)

    def test_renamed_target_captures_with_valid_provider_are_still_ambiguous(self):
        provider = RoleDefinition("provider", (ReferenceKind.OBJECT,))
        p = self.paired_patterns(
            r"(?P<provider>.+)에게 (?P<subject>.+)", r"(?P<provider>.+)에게 (?P<source>.+)",
            roles_left=(provider, RoleDefinition("subject", (ReferenceKind.ITEM,))),
            roles_right=(provider, RoleDefinition("source", (ReferenceKind.ITEM,))))
        with self.assertRaises(RegistryError) as failure:
            self.compile(p)
        self.assertIn("OVERLAP", str(failure.exception))

    def test_supported_regex_languages_report_overlap_disjoint_and_unicode_digits(self):
        from world.actions.regex_overlap import Relation, compare_patterns

        cases = (
            (r".+", r".+", Relation.OVERLAP),
            (r"\d+", r"[0-9]+", Relation.OVERLAP),
            (r"[가-힣]+", r"[0-9]+", Relation.DISJOINT),
            (r"검증기", r".+", Relation.OVERLAP),
            (r"사과", r"바나나", Relation.DISJOINT),
            (r"검증기", r"검증기", Relation.OVERLAP),
            (r".+", r"[가-힣]+", Relation.OVERLAP),
            (r"검사", r"수리", Relation.DISJOINT),
            (r"[가-힣]+", r"[a-z]+", Relation.DISJOINT),
            (r"[가-힣]*", r"[a-z]*", Relation.OVERLAP),
            (r"(?:문|시체)\d+", r"시체[0-9]{1,3}", Relation.OVERLAP),
            (r"(?:문|시체)\d+", r"물품\d+", Relation.DISJOINT),
            (r"붕대(?: 2)?", r"붕대 2", Relation.OVERLAP),
            (r"붕대(?: 2)?", r"붕대 3", Relation.DISJOINT),
            (r"a{2,4}", r"a{3,5}", Relation.OVERLAP),
            (r"a{2,4}", r"a{5,6}", Relation.DISJOINT),
            (r"\d+", "٣４", Relation.OVERLAP),
            (r"\d+", r"[가-힣]+", Relation.DISJOINT),
            (r"\D+", r"[가-힣]+", Relation.OVERLAP),
            (r"[^가-힣]+", r"[가-힣]+", Relation.DISJOINT),
            (r".+", "\n", Relation.DISJOINT),
            (r"\s+", "\n", Relation.OVERLAP),
        )
        for left, right, expected in cases:
            with self.subTest(left=left, right=right):
                self.assertEqual(compare_patterns(left, right), expected)
                self.assertEqual(compare_patterns(right, left), expected)
                # escape나 newline을 변환하지 않고 같은 Provider/Verb/normal 등록 경계도 검사한다.
                declaration = self.paired_patterns(f"(?P<provider>{left})", f"(?P<provider>{right})")
                if expected == Relation.OVERLAP:
                    with self.assertRaises(RegistryError):
                        self.compile(declaration)
                else:
                    self.compile(declaration)

    def test_finite_supported_languages_match_complete_small_alphabet_oracle(self):
        import re
        from itertools import product

        from world.actions.regex_overlap import Relation, compare_patterns

        patterns = ("", "가", "나", "[가나]", "[^가나]", "가?나?", "가{1,2}",
                    "(?:가|나나)", "가(?:가|나)?", "[가나]{0,2}")
        strings = ["".join(letters) for size in range(4) for letters in product("가나x", repeat=size)]
        languages = {pattern: {text for text in strings if re.fullmatch(pattern, text)} for pattern in patterns}
        for left in patterns:
            for right in patterns:
                with self.subTest(left=left, right=right):
                    expected = Relation.OVERLAP if languages[left] & languages[right] else Relation.DISJOINT
                    self.assertEqual(compare_patterns(left, right), expected)

    def test_unknown_regex_features_fail_closed_with_registration_context(self):
        from world.actions.regex_overlap import Relation, compare_patterns

        unknown = (r"(?=가).+", r"(?<=가).+", r"(.)\1", r"\b가", r"가$", r"(?i)abc",
                   r"(?s:.)+", r"a{1000}", r"(?>가+)가", r"가++가")
        for pattern in unknown:
            with self.subTest(pattern=pattern):
                self.assertEqual(compare_patterns(pattern, ".+"), Relation.UNKNOWN)
        for pattern in (r"(?P<provider>(?=가).+)", r"(?P<provider>가$)", r"(?i:(?P<provider>abc))"):
            p = self.paired_patterns(r"(?P<provider>.+)", pattern)
            with self.subTest(pattern=pattern), self.assertRaises(RegistryError) as failure:
                self.compile(p)
            message = str(failure.exception)
            for value in ("fixture.verb", "fixture.provider", "fixture.action", "fixture.second_action", "normal", "UNKNOWN"):
                self.assertIn(value, message)
            self.assertIn("명시적으로 구분", message)
        for pattern in (r"(?P<provider>(?=가).+)", r"(?P<provider>.+)(?P=provider)"):
            with self.subTest(identical_unknown=pattern), self.assertRaises(RegistryError) as failure:
                self.compile(self.paired_patterns(pattern, pattern))
            self.assertIn("UNKNOWN", str(failure.exception))

    def test_disjoint_literal_actions_are_allowed_and_registration_never_executes_services(self):
        calls = []

        def observe(context):
            calls.append(context)
            return context

        p = self.paired_patterns(r"(?P<provider>검사)", r"(?P<provider>수리)")
        p = replace(p, services=(replace(p.services[0], handler=observe),))
        self.compile(p)
        self.assertEqual(calls, [])
        p = replace(p, actions=(p.actions[0], replace(p.actions[1], variants=(SyntaxVariant("normal", r"(?P<provider>[가-힣]+)"),))))
        with self.assertRaises(RegistryError) as failure:
            self.compile(p)
        self.assertIn("OVERLAP", str(failure.exception))
        self.assertEqual(calls, [])

    def test_suffix_casefold_collision_is_checked_but_distinct_suffixes_are_separate(self):
        p = self.paired_patterns(r"(?P<provider>.+)", r"(?P<provider>[가-힣]+)")
        a = replace(p.actions[0], variants=(SyntaxVariant("first", r"(?P<provider>.+)", "Confirm"),))
        b = replace(p.actions[1], variants=(SyntaxVariant("second", r"(?P<provider>[가-힣]+)", "confirm"),))
        with self.assertRaises(RegistryError):
            self.compile(replace(p, actions=(a, b)))
        b = replace(b, variants=(replace(b.variants[0], suffix="확정"),))
        self.compile(replace(p, actions=(a, b)))

    def test_only_explicit_required_argument_extension_preserves_overlapping_contract(self):
        from world.actions.regex_overlap import Relation, compare_patterns

        p = self.paired_patterns(r"(?P<provider>.*)", r"(?P<provider>.+) (?P<quantity>\d+)")
        b = replace(p.actions[1], arguments=(ArgumentDefinition("quantity", int),))
        p = replace(p, actions=(p.actions[0], b))
        self.assertEqual(compare_patterns(p.actions[0].variants[0].pattern, b.variants[0].pattern), Relation.OVERLAP)
        self.compile(p)
        self.compile(replace(p, actions=tuple(reversed(p.actions))))
        for declaration in (replace(b.arguments[0], required=False), replace(b.arguments[0], default=1)):
            with self.subTest(argument=declaration), self.assertRaises(RegistryError):
                self.compile(replace(p, actions=(p.actions[0], replace(b, arguments=(declaration,)))))
        for pattern in (r"(?P<provider>.+)", r"(?P<provider>.+) (?P<quantity>\d*)",
                        r"(?P<provider>.+)(?: (?P<quantity>\d+))?",
                        r"(?P<provider>.+) (?P<quantity>(?=\d)\d+)",
                        r"(?P<provider>.+) (?P<quantity>\d+)$",
                        r"(?i:(?P<provider>.+)) (?P<quantity>\d+)"):
            changed = replace(b, variants=(SyntaxVariant("normal", pattern),))
            with self.subTest(pattern=pattern), self.assertRaises(RegistryError):
                self.compile(replace(p, actions=(p.actions[0], changed)))

    def test_shared_verb_different_providers_and_services_without_registry_changes(self):
        p = package()
        p = replace(p, providers=p.providers + (
            ProviderDefinition("fixture.second", "다른장치", "fixture.other", "room:1"),),
            bindings=p.bindings + (ActionBinding("fixture.second_binding", "fixture.second",
                                                 "fixture.action", "fixture.service"),))
        index = self.compile(p)
        self.assertEqual(index.verbs_by_public_keys, {"검증": "fixture.verb", "살펴": "fixture.verb"})
        self.assertEqual(len(index.bindings_for_provider), 2)
        self.assertEqual(index.services["fixture.service"].handler("실행"), "실행")

    def test_compilation_and_nested_declarations_are_immutable(self):
        p = package()
        aliases = ["살펴"]
        verb = VerbDefinition("fixture.verb", "검증", aliases)
        aliases.append("외부변경")
        self.assertEqual(verb.aliases, ("살펴",))
        config = {"nested": [1, {"x": True}]}
        binding = ActionBinding("fixture.binding", "fixture.provider", "fixture.action",
                                "fixture.service", config)
        config["nested"].append(2)
        self.assertEqual(binding.config, (("nested", (1, (("x", True),))),))
        index = self.compile(p)
        with self.assertRaises(TypeError):
            index.actions["illegal"] = p.actions[0]
        with self.assertRaises(FrozenInstanceError):
            index.actions["fixture.action"].public = False

    def test_duplicate_ids_all_declaration_types_and_namespace(self):
        p = package()
        for field in ("verbs", "actions", "services", "bindings", "providers"):
            with self.subTest(field=field), self.assertRaises(RegistryError):
                self.compile(replace(p, **{field: getattr(p, field) * 2}))
        with self.assertRaises(RegistryError):
            compile_manifest(PackageManifest((p, p)))
        with self.assertRaises(RegistryError):
            self.compile(replace(p, services=(replace(p.services[0], id=p.actions[0].id),)))
        with self.assertRaises(RegistryError):
            self.compile(replace(p, id="unnamespaced"))

    def test_public_alias_conflict_and_engine_exit_global_names(self):
        p = package()
        for key in ("검증", "살펴"):
            with self.subTest(key=key), self.assertRaises(RegistryError):
                self.compile(p, (key,))
        with self.assertRaises(RegistryError):
            self.compile(replace(p, verbs=p.verbs + (
                VerbDefinition("fixture.other_verb", "다른검증", ("살펴",)),)))

    def test_missing_dependencies_cycles_and_cross_package_ownership(self):
        p = package()
        with self.assertRaises(RegistryError):
            self.compile(replace(p, dependencies=("missing.package",)))
        with self.assertRaises(RegistryError):
            compile_manifest(PackageManifest((replace(p, dependencies=("other.package",)),
                                              ContentPackage("other.package", dependencies=(p.id,)))))
        shared = ContentPackage("other.package", services=p.services)
        consumer = replace(p, services=())
        with self.assertRaises(RegistryError):
            compile_manifest(PackageManifest((consumer, shared)))
        compile_manifest(PackageManifest((replace(consumer, dependencies=(shared.id,)), shared)))

    def test_casefolded_public_keys_and_protected_names(self):
        p = package()
        with self.assertRaises(RegistryError):
            self.compile(replace(p, verbs=(VerbDefinition("fixture.upper", "Scan"),
                                          VerbDefinition("fixture.lower", "scan"))))
        with self.assertRaises(RegistryError):
            self.compile(replace(p, verbs=(replace(p.verbs[0], key="Help"),)), ("help",))
        index = self.compile(replace(p, verbs=(replace(p.verbs[0], key="Scan"),)))
        self.assertEqual(index.verbs_by_public_keys["scan"], "fixture.verb")

    def test_expanded_variant_keys_protect_engine_and_other_canonical_verbs(self):
        p = package()
        action = replace(p.actions[0], variants=(SyntaxVariant("confirmed", r"(?P<provider>.+)", "확정", True),))
        p = replace(p, actions=(action,))
        with self.assertRaises(RegistryError):
            self.compile(p, ("검증 확정",))
        with self.assertRaises(RegistryError):
            self.compile(replace(p, verbs=(*p.verbs, VerbDefinition("fixture.collision", "검증 확정"))))

    def test_missing_service_role_and_incompatible_typed_role(self):
        p = package()
        for change in (
            replace(p, services=()),
            replace(p, services=(replace(p.services[0], role_kinds=(
                RoleDefinition("subject", (ReferenceKind.OBJECT,)),)),)),
            replace(p, services=(replace(p.services[0], role_kinds=(
                RoleDefinition("provider", (ReferenceKind.DOOR,)),)),)),
        ):
            with self.assertRaises(RegistryError):
                self.compile(change)

    def test_invalid_role_argument_syntax_and_confirmation(self):
        p = package()
        a = p.actions[0]
        changes = (
            replace(a, provider_from="unknown"),
            replace(a, roles=(RoleDefinition("provider", ("object",)),)),
            replace(a, roles=(RoleDefinition("provider", (ReferenceKind.OBJECT,), "first"),)),
            replace(a, arguments=(ArgumentDefinition("count", float),)),
            replace(a, arguments=(ArgumentDefinition("count", int, minimum=4, maximum=2),)),
            replace(a, variants=(SyntaxVariant("normal", "["),)),
            replace(a, variants=(SyntaxVariant("normal", "(.+)"),)),
            replace(a, variants=(SyntaxVariant("normal", "(?P<unknown>.+)"),)),
            replace(a, variants=a.variants * 2),
            replace(a, variants=(SyntaxVariant("confirmed", ".*", confirmation_required=True),)),
        )
        for changed in changes:
            with self.subTest(action=changed), self.assertRaises(RegistryError):
                self.compile(replace(p, actions=(changed,)))

    def test_same_provider_ambiguous_handlers_rejected_not_first_wins(self):
        p = package()
        second = replace(p.actions[0], id="fixture.second_action")
        binding = replace(p.bindings[0], id="fixture.second_binding", action_id=second.id)
        with self.assertRaises(RegistryError):
            self.compile(replace(p, actions=p.actions + (second,), bindings=p.bindings + (binding,)))
        second = replace(second, variants=(SyntaxVariant("confirmed", r"(?P<provider>.+)", "확정", True),))
        self.compile(replace(p, actions=p.actions + (second,), bindings=p.bindings + (binding,)))

    def test_same_provider_different_typed_roles_and_explicit_variants(self):
        p = package()
        role = RoleDefinition("provider", (ReferenceKind.ITEM,))
        second = replace(p.actions[0], id="fixture.second_action", roles=(role,),
                         variants=p.actions[0].variants + (
                             SyntaxVariant("confirmed", r"(?P<provider>.+)", "확정", True),))
        service = ServiceDefinition("fixture.item_service", handler, (role,))
        binding = replace(p.bindings[0], id="fixture.item_binding", action_id=second.id,
                          service_id=service.id)
        self.compile(replace(p, actions=p.actions + (second,), services=p.services + (service,),
                             bindings=p.bindings + (binding,)))

    def test_renaming_capture_does_not_disambiguate_the_same_input_language(self):
        p = package()
        role = RoleDefinition("subject", (ReferenceKind.OBJECT,))
        second = replace(p.actions[0], id="fixture.second_action", roles=(role,),
                         variants=(SyntaxVariant("normal", r"(?P<subject>.+)"),))
        service = ServiceDefinition("fixture.subject_service", handler, (role,))
        binding = replace(p.bindings[0], id="fixture.second_binding", action_id=second.id,
                          service_id=service.id)
        with self.assertRaises(RegistryError):
            self.compile(replace(p, actions=p.actions + (second,), services=p.services + (service,),
                                 bindings=p.bindings + (binding,)))

    def test_service_config_schema_and_bool_not_integer(self):
        p = package()
        arg = ArgumentDefinition("cost", int, minimum=1, maximum=5)
        service = replace(p.services[0], config_schema=(arg,))
        for config in ((), (("cost", True),), (("cost", 0),), (("cost", 6),),
                       (("unknown", 1),), (("cost", 2), ("cost", 3))):
            with self.subTest(config=config), self.assertRaises(RegistryError):
                self.compile(replace(p, services=(service,), bindings=(replace(p.bindings[0], config=config),)))
        self.compile(replace(p, services=(service,), bindings=(replace(p.bindings[0], config=(("cost", 2),)),)))
        with self.assertRaises(RegistryError):
            validate_argument(arg, True)

    def test_static_same_name_requires_shared_group_or_distinct_name(self):
        p = package()
        other = replace(p.providers[0], id="fixture.second", group_id="fixture.other")
        with self.assertRaises(RegistryError):
            self.compile(replace(p, providers=p.providers + (other,)))
        self.compile(replace(p, providers=p.providers + (replace(other, group_id="fixture.group"),)))
        self.compile(replace(p, providers=p.providers + (replace(other, name="다른장치"),)))
        with self.assertRaises(RegistryError):
            self.compile(replace(p, providers=p.providers + (replace(other, name="검증 장치"),)))

    def test_compile_does_not_execute_handlers_or_discover_private_actions(self):
        p = package()
        calls = []
        service = replace(p.services[0], handler=lambda context: calls.append(context))
        index = self.compile(replace(p, services=(service,), actions=(replace(p.actions[0], public=False),)))
        self.assertFalse(index.actions["fixture.action"].public)
        self.assertEqual(calls, [])

    def test_reference_and_default_policy_are_typed_stable_values(self):
        ref = TargetReference(ReferenceKind.ITEM, "stable-uuid", "owner:1")
        self.assertEqual(ref.identity, "stable-uuid")
        with self.assertRaises(TypeError):
            TargetReference("item", "uuid", "owner:1")
        with self.assertRaises(ValueError):
            TargetReference(ReferenceKind.ITEM, "", "owner:1")
        self.assertEqual(RoleDefinition("subject", (ReferenceKind.ITEM,)).default,
                         DefaultTargetPolicy.REQUIRE_UNIQUE)

    def test_non_synchronous_handler_rejected_at_registration(self):
        async def asynchronous(context):
            return context

        def generator(context):
            yield context

        p = package()
        for callback in (None, asynchronous, generator):
            with self.subTest(callback=callback), self.assertRaises(RegistryError):
                self.compile(replace(p, services=(replace(p.services[0], handler=callback),)))

    def test_uninspectable_callable_handler_forms_are_rejected_before_execution(self):
        from twisted.internet.task import Clock

        clock = Clock()

        class CallableService:
            def __call__(self, context):
                clock.callLater(0, lambda: None)
                return context

            def bound(self, context):
                return context

        value = CallableService()
        p = package()
        for callback in (value, value.bound, partial(handler), lru_cache()(handler), len):
            with self.subTest(form=type(callback).__name__), self.assertRaises(RegistryError):
                self.compile(replace(p, services=(replace(p.services[0], handler=callback),)))
        self.assertEqual(clock.getDelayedCalls(), [])

    def test_default_arguments_closures_and_wrapped_helpers_cannot_hide_pending_work(self):
        from twisted.internet.task import Clock

        clock = Clock()

        def default_timer(context, timer=clock.callLater):
            timer(0, lambda: None)
            return context

        def keyword_timer(context, *, timer=clock.callLater):
            timer(0, lambda: None)
            return context

        async def asynchronous(context):
            return context

        def generator(context):
            yield context

        def default_async(context, callback=asynchronous):
            return callback(context)

        def keyword_generator(context, *, callback=generator):
            return callback(context)

        hidden = partial(default_timer)

        def closure_wrapper(context):
            return hidden(context)

        @wraps(asynchronous)
        def metadata_wrapper(context):
            return context

        p = package()
        for callback in (default_timer, keyword_timer, default_async, keyword_generator,
                         closure_wrapper, metadata_wrapper):
            with self.subTest(handler=callback.__name__), self.assertRaises(RegistryError):
                self.compile(replace(p, services=(replace(p.services[0], handler=callback),)))
        self.assertEqual(clock.getDelayedCalls(), [])

    def test_plain_synchronous_wrappers_and_defaults_remain_supported(self):
        def helper(context, *, prefix="정상"):
            return prefix + context

        @wraps(helper)
        def wrapped(context, callback=helper):
            return callback(context)

        p = package()
        index = self.compile(replace(p, services=(replace(p.services[0], handler=wrapped),)))
        self.assertEqual(index.services["fixture.service"].handler(" 실행"), "정상 실행")

    def test_nested_function_and_container_defaults_cannot_hide_scheduling(self):
        from twisted.internet.task import Clock

        clock = Clock()

        def nested(context):
            def helper():
                clock.callLater(0, lambda: None)
            helper()
            return context

        def container(context, callbacks=(clock.callLater,)):
            callbacks[0](0, lambda: None)
            return context

        p = package()
        for callback in (nested, container):
            with self.subTest(handler=callback.__name__), self.assertRaises(RegistryError):
                self.compile(replace(p, services=(replace(p.services[0], handler=callback),)))
        self.assertEqual(clock.getDelayedCalls(), [])

    def test_scoped_roles_require_typed_scope_and_existing_acyclic_source(self):
        p = package()
        provider = p.actions[0].roles[0]
        subject = RoleDefinition("subject", (ReferenceKind.ITEM,), scope=TargetScope.STORAGE)
        action = replace(p.actions[0], roles=(provider, subject))
        self.compile(replace(p, actions=(action,)))
        for bad in (
            replace(subject, scope="storage"), replace(subject, scope_from=None),
            replace(subject, scope_from="missing"), replace(subject, scope_from="subject"),
        ):
            with self.subTest(role=bad), self.assertRaises(RegistryError):
                self.compile(replace(p, actions=(replace(action, roles=(provider, bad)),)))
        cyclic_provider = replace(provider, scope=TargetScope.INSIDE, scope_from="subject")
        with self.assertRaises(RegistryError):
            self.compile(replace(p, actions=(replace(action, roles=(cyclic_provider, subject)),)))

    def test_explicit_service_scope_cannot_be_weakened_by_action_binding(self):
        p = package()
        provider = p.actions[0].roles[0]
        subject = RoleDefinition("subject", (ReferenceKind.ITEM,), scope=TargetScope.STORAGE)
        action = replace(p.actions[0], roles=(provider, subject))
        service = replace(p.services[0], role_kinds=(provider, subject))
        self.compile(replace(p, actions=(action,), services=(service,)))
        for bad in (replace(subject, scope=TargetScope.CURRENT),
                    replace(subject, scope=TargetScope.INSIDE)):
            with self.subTest(role=bad), self.assertRaises(RegistryError):
                self.compile(replace(p, actions=(replace(action, roles=(provider, bad)),), services=(service,)))
        generic = replace(service, role_kinds=(provider, replace(subject, scope=TargetScope.CURRENT)))
        self.compile(replace(p, actions=(action,), services=(generic,)))
