"""P3-R22-C01~03/R35-C02: 공통 실행기 수정 없이 선언만으로 확장한다."""

from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

from django.test import override_settings
from evennia import create_object
from server.conf.primal_inputfuncs import pz_action
from twisted.internet.defer import Deferred
from world.actions.gateway import ResultStatus, execute, from_web
from world.actions.manifest import compiled, get_index
from world.actions.presentation import action_controls, help_entries, reference_json
from world.actions.registry import RegistryError, compile_manifest
from world.actions.resolver import dispatch_text
from world.actions.schema import PackageManifest, VerbDefinition
from world.actions.scope import CMDSET_KEY, refresh
from world.multiplayer import world_change
from world.rules import RuleError
from world.selection_numbers.api import descriptor, number_for

from tests.item_entity_fixture import NativeItemTest
from tests.phase3_extension_fixture import PACKAGE, ExtensionBroker


@override_settings(ACTION_CONTENT_PACKAGES=("tests.phase3_extension_fixture",))
class Phase3ExtensionTests(NativeItemTest):
    def setUp(self):
        super().setUp()
        compiled.cache_clear()
        self.addCleanup(compiled.cache_clear)
        self.index = get_index()
        self.session.puppet = self.char1
        self.session.logged_in = True
        self.session.protocol_key = "websocket"
        self.char1.sessions.add(self.session)
        self.output = self.enterContext(patch.object(self.char1, "msg"))
        self.prompt = self.enterContext(patch.object(self.char1, "push_prompt", wraps=self.char1.push_prompt))
        profile = self.char1.profile_snapshot()
        profile["credits"] = 30
        self.char1.save_profile(profile)
        self.a = self.broker()

    def broker(self, name="중개인", definition="phase3.broker"):
        with world_change():
            npc = create_object(ExtensionBroker, key=name, location=self.char1.location,
                                attributes=[("action_provider_id", definition),
                                            ("selection_group_id", "phase3.brokers"),
                                            ("phase3_client_id", self.char1.pk),
                                            ("phase3_escrow", 0)])
            npc.locks.add("view:true();call:true();delete:true()")
            return npc

    def state(self, npc=None):
        npc = npc or self.a
        return (self.char1.profile_snapshot()["credits"], int(npc.db.phase3_escrow or 0),
                deepcopy(npc.db.phase3_receipt))

    def raw(self, command):
        self.prompt.reset_mock()
        self.output.reset_mock()
        done = []
        deferred = self.char1.execute_cmd(command, session=self.session)
        self.assertIsInstance(deferred, Deferred)
        deferred.addCallback(lambda result: done.append(True))
        self.assertEqual(done, [True], command)
        self.prompt.assert_called_once()

    def payload(self, action, npc=None, request="extension-request", **arguments):
        return {"action_id": action, "variant": "normal", "request_id": request,
                "roles": {"provider": [reference_json(descriptor(npc or self.a).reference)]},
                "arguments": arguments}

    def test_loader_help_actual_command_and_typed_web_have_distinct_persistent_effects(self):
        """R22-C01/C02: loader, 두 Service, 명령/웹, 지갑·원장·영수증."""
        self.assertEqual(set(self.index.services), {"phase3.deposit_service", "phase3.withdraw_service"})
        help_rows = help_entries(self.index, "phase3.mediate")
        self.assertEqual(len(help_rows), 2)
        self.assertTrue(all(row["aliases"] == ("중개",) for row in help_rows))
        refresh(self.char1)
        cmdset = next(cs for cs in self.char1.cmdset.cmdset_stack if cs.key == CMDSET_KEY)
        self.assertEqual(sum(command.key == "조율" for command in cmdset), 1)
        self.raw("중개인 예치 7 중개")
        self.assertEqual(self.state(), (23, 7, {"owner": self.char1.pk, "amount": 7}))
        payload = self.payload("phase3.deposit", quantity=3)
        pz_action(self.session, payload)
        self.assertEqual(self.state(), (20, 10, {"owner": self.char1.pk, "amount": 3}))
        pz_action(self.session, payload)
        self.assertEqual(self.state(), (20, 10, {"owner": self.char1.pk, "amount": 3}))
        invocation = from_web(self.payload("phase3.withdraw", request="return"), self.index)
        result = execute(self.char1, self.session, invocation, self.index)
        self.assertEqual(result.status, ResultStatus.CONFIRMATION)
        self.assertEqual(self.state()[0:2], (20, 10))
        confirmed = replace(invocation, variant_id="confirmed", request_id="return-confirm",
                            confirmation_token=result.confirmation_token)
        self.assertEqual(execute(self.char1, self.session, confirmed, self.index).status, ResultStatus.SUCCESS)
        self.assertEqual(self.state(), (30, 0, None))
        self.assertEqual(execute(self.char1, self.session, confirmed, self.index).status, ResultStatus.REFUSED)
        self.assertEqual(self.state(), (30, 0, None))
        self.raw("중개인 예치 2 조율")
        self.raw("중개인 반환 조율")
        self.assertEqual(self.state()[0:2], (28, 2))
        self.raw("중개인 반환 조율 확정")
        self.assertEqual(self.state(), (30, 0, None))

    def test_two_npcs_share_numbers_require_explicit_provider_and_never_fallback(self):
        """R35-C02/R22-C03: 이름/group/번호/가시성 변경 이후 같은 Provider."""
        b = self.broker(definition="phase3.second_broker")
        a_ref, b_ref = descriptor(self.a).reference, descriptor(b).reference
        self.assertEqual(descriptor(self.a).group_id, descriptor(b).group_id)
        self.assertEqual((number_for(a_ref), number_for(b_ref)), (1, 2))
        controls = action_controls(self.char1, self.index)
        self.assertEqual({row["label"] for row in controls}, {"중개인 1 조율", "중개인 2 조율"})
        self.assertEqual({row["action"]["roles"]["provider"][0]["identity"] for row in controls},
                         {str(self.a.pk), str(b.pk)})
        with self.assertRaises(RuleError):
            dispatch_text(self.char1, self.index, "phase3.mediate", "중개인 예치 7", "조율")
        self.raw("중개인 2 예치 7 조율")
        self.assertEqual(self.state()[0:2], (23, 0))
        self.assertEqual(int(b.db.phase3_escrow), 7)
        self.a.aliases.add("담당자")
        b.aliases.add("담당자")
        before = (self.state(), self.state(b))
        self.raw("담당자 예치 3 조율")
        self.assertEqual((self.state(), self.state(b)), before)
        b.locks.add("view:false()")
        self.raw("중개인 2 예치 3 조율")
        self.assertEqual((self.state(), self.state(b)), before)
        self.assertEqual((number_for(a_ref), number_for(b_ref)), (1, 2))
        self.assertFalse(any(row["action"]["roles"]["provider"] == [reference_json(b_ref)]
                             for row in action_controls(self.char1, self.index)))

    def test_permission_amount_confirmation_and_exception_rollback_preserve_real_state(self):
        """R22-C03: 자격·잔액 거절, 확인 우회, 저장 뒤 예외의 전체 Rollback."""
        before = self.state()
        for amount in (31, 100):
            invocation = from_web(self.payload("phase3.deposit", request=f"insufficient-{amount}",
                                               quantity=amount), self.index)
            self.assertEqual(execute(self.char1, self.session, invocation, self.index).status,
                             ResultStatus.REFUSED)
            self.assertEqual(self.state(), before)
        self.a.db.phase3_client_id = self.char2.pk
        invocation = from_web(self.payload("phase3.deposit", request="wrong-client", quantity=7), self.index)
        self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.REFUSED)
        self.assertEqual(self.state(), before)
        self.a.db.phase3_client_id = self.char1.pk
        self.a.db.phase3_fail = True
        invocation = from_web(self.payload("phase3.deposit", request="fail-after-save", quantity=7), self.index)
        self.assertEqual(execute(self.char1, self.session, invocation, self.index).status, ResultStatus.ERROR)
        self.assertEqual(self.state(), before)
        self.a.db.phase3_fail = False
        self.raw("중개인 예치 7 조율")
        before = self.state()
        invocation = from_web(self.payload("phase3.withdraw", request="forged-confirm"), self.index)
        forged = replace(invocation, variant_id="confirmed")
        self.assertEqual(execute(self.char1, self.session, forged, self.index).status, ResultStatus.REFUSED)
        self.assertEqual(self.state(), before)
        self.a.locks.add("call:false()")
        denied = from_web(self.payload("phase3.withdraw", request="denied"), self.index)
        self.assertEqual(execute(self.char1, self.session, denied, self.index).status, ResultStatus.REFUSED)
        self.assertEqual(self.state(), before)

    def test_real_prompt_blocks_both_new_services_then_restores_command_execution(self):
        """R22-C03: 실제 입력 Replace CmdSet 중 텍스트·Typed 요청 효과 0."""
        from evennia.utils.evmenu import get_input

        received = []

        def answer(caller, prompt, value):
            received.append(value)
            return value != "완료"

        before = self.state()
        get_input(self.char1, "확장성 검증 응답", answer, session=self.session)
        pz_action(self.session, self.payload("phase3.deposit", request="prompt", quantity=7))
        self.char1.execute_cmd("중개인 예치 7 조율", session=self.session)
        self.assertEqual(received, ["중개인 예치 7 조율"])
        self.assertEqual(self.state(), before)
        self.char1.execute_cmd("완료", session=self.session)
        self.assertIsNone(self.char1.ndb._getinput)
        self.raw("중개인 예치 7 조율")
        self.assertEqual(self.state()[0:2], (23, 7))

    def test_alias_collision_rejected_before_loader_or_service_mutates_state(self):
        """R22-C03: 콘텐츠의 공개 별칭 충돌을 등록에서 거절한다."""
        before = self.state()
        collision = replace(PACKAGE, verbs=(*PACKAGE.verbs,
                            VerbDefinition("phase3.collision", "다른조율", ("중개",))))
        with self.assertRaises(RegistryError):
            compile_manifest(PackageManifest((collision,)))
        self.assertEqual(self.state(), before)
        duplicate = replace(PACKAGE.actions[0], id="phase3.duplicate_deposit")
        conflicting_binding = replace(PACKAGE.bindings[0], id="phase3.conflicting_handler",
                                      action_id=duplicate.id, service_id="phase3.withdraw_service")
        collision = replace(PACKAGE, actions=(*PACKAGE.actions, duplicate),
                            bindings=(*PACKAGE.bindings, conflicting_binding))
        with self.assertRaises(RegistryError):
            compile_manifest(PackageManifest((collision,)))
        self.assertEqual(self.state(), before)
