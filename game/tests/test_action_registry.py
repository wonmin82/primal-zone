"""게임/DB 없이 선언·등록 실패와 불변성 경계를 확인한다."""

from dataclasses import FrozenInstanceError, replace
from unittest import TestCase

from world.actions.registry import RegistryError, compile_manifest, validate_argument
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
    def compile(self, value=None, protected=()):
        return compile_manifest(PackageManifest((value or package(),)), protected)

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
