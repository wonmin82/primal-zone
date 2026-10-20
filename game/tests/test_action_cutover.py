"""M06의 현재 Provider 표현과 승인된 전역 명령·단일 실행 경로 회귀."""

from dataclasses import replace
from unittest.mock import Mock, patch

from commands.help_pages import help_page, with_action_help
from commands.registry import COMMANDS
from evennia import create_object
from typeclasses.interactables import ActionObject, Doctor, Incinerator, SupplyCache
from world.actions.manifest import get_index
from world.actions.presentation import action_controls, help_metadata, provider_controls
from world.item_entities.models import ItemEntity
from world.selection_numbers.models import NumberScope, SelectionNumber
from world.state import multiplayer_state

from tests.base import WorldCommandTest
from tests.item_entity_fixture import NativeItemTest


class ActionCutoverTests(NativeItemTest, WorldCommandTest):
    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        self.char1.location = self.rooms["infirmary"]
        self.connect_character(self.char1)
        self.index = get_index()
        self.doctor = next(obj for obj in self.char1.location.contents if isinstance(obj, Doctor))
        self.char1.change(lambda profile: profile.update(hp=1, credits=1000))

    def raw(self, command):
        with patch.object(self.char1, "msg") as output:
            completed = []
            self.char1.execute_cmd(command).addCallback(lambda _: completed.append(True))
            self.assertEqual(completed, [True])
        return "\n".join(str(call.args[0]) for call in output.call_args_list if call.args)

    def snapshot(self):
        return (self.char1.profile_snapshot(), list(ItemEntity.objects.order_by("pk").values()),
                list(NumberScope.objects.order_by("pk").values()),
                list(SelectionNumber.objects.order_by("pk").values()),
                dict(self.char1.ndb.action_confirmations or {}))

    def test_global_commands_remain_and_migrated_verbs_have_one_registered_entry(self):
        keys = {command.key for command in COMMANDS}
        self.assertTrue({"봐", "말", "도움", "버려", "줘"} <= keys)
        migrated = {verb.key for verb in self.index.verbs.values()}
        self.assertFalse(keys & migrated)
        entries = with_action_help(COMMANDS)
        self.assertEqual(len([entry.key for entry in entries]), len({entry.key for entry in entries}))
        self.assertFalse(hasattr(SupplyCache, "act"))
        self.assertFalse(hasattr(Incinerator, "act"))
        self.assertFalse(hasattr(ActionObject, "perform_action"))
        from commands.action_command import DynamicActionCommand
        from world.actions.scope import CMDSET_KEY, refresh

        # 실제 현재 제공자가 만드는 CmdSet도 동사마다 Command 하나만 등록한다.
        for zone in ("infirmary", "supply_shop", "storage_room", "wreck", "training_office"):
            self.char1.location = self.rooms[zone]
            refresh(self.char1)
            commands = [command for cmdset in self.char1.cmdset.cmdset_stack
                        if cmdset.key == CMDSET_KEY for command in cmdset]
            self.assertTrue(commands, zone)
            self.assertTrue(all(isinstance(command, DynamicActionCommand) for command in commands))
            self.assertEqual(len(commands), len({command.verb_id for command in commands}), zone)
            state = multiplayer_state(self.char1)
            rows = [*state["action_controls"],
                    *(action for obj in state["interactables"] for action in obj["actions"])]
            for row in rows:
                if "action" in row:
                    payload = row["action"]
                    self.assertIn(payload["action_id"], self.index.actions)
                    self.assertIn(payload["variant"],
                                  {variant.id for variant in self.index.actions[payload["action_id"]].variants})
                    self.assertTrue(all("identity" in reference and "scope_id" in reference
                                        for references in payload["roles"].values() for reference in references))
                else:
                    self.assertTrue(row.get("command", "").endswith(" 봐") or
                                    row.get("command", "").startswith("'"), row)

    def test_public_help_alias_suffix_and_standard_sections_follow_index(self):
        sections = ("사용법", "예시", "실행 규칙", "제한", "관련 도움말")
        for verb in help_metadata(self.index):
            page = help_page(verb.key, COMMANDS)
            self.assertIn(verb.summary, page)
            self.assertEqual([line for line in page.splitlines() if line in sections], list(sections))
            for alias in verb.aliases:
                with self.subTest(verb=verb.key, alias=alias):
                    self.assertEqual(help_page(alias, COMMANDS), page)
        self.assertEqual(self.raw("시2 도움"), self.raw("가져 도움"))

    def test_compiled_binding_not_legacy_actions_controls_object_description(self):
        self.char1.location = self.rooms["wreck"]
        cache = next(obj for obj in self.char1.location.contents if isinstance(obj, SupplyCache))
        with patch.object(SupplyCache, "actions", ("없는행동",)):
            self.assertEqual(cache.current_actions(self.char1), ("조사",))
            self.assertIn("가능한 행동 : 조사", self.raw(cache.key + " 봐"))
            self.assertNotIn("없는행동", self.raw(cache.key + " 봐"))
        without = replace(self.index, bindings={}, bindings_for_provider={})
        with patch("world.actions.manifest.get_index", return_value=without):
            self.assertNotIn("가능한 행동 : 조사", self.raw(cache.key + " 봐"))

    def test_view_call_unavailable_and_combat_hide_controls_without_execution(self):
        self.assertIn("회복", self.doctor.current_actions(self.char1))
        self.doctor.locks.add("call:false()")
        self.assertEqual(provider_controls(self.char1, self.doctor), [])
        self.assertNotIn("회복 · 20 회복", self.raw("의무관 봐"))
        row = next(row for row in multiplayer_state(self.char1)["interactables"] if row["name"] == self.doctor.key)
        self.assertFalse(any("action" in action for action in row["actions"]))
        self.doctor.locks.add("call:all();view:false()")
        self.assertEqual(provider_controls(self.char1, self.doctor), [])
        self.doctor.locks.add("view:all()")
        self.doctor.db.action_available = False
        self.assertEqual(provider_controls(self.char1, self.doctor), [])
        self.doctor.db.action_available = True
        self.char1.change(lambda profile: profile.update(combat_target=999999))
        self.assertEqual(provider_controls(self.char1, self.doctor), [])

    def test_repeated_look_help_controls_are_readonly_and_text_web_use_same_service(self):
        before = self.snapshot()
        with patch("world.interactable_services.doctor", wraps=__import__(
                "world.interactable_services", fromlist=["doctor"]).doctor) as effect:
            for _ in range(2):
                self.raw("의무관 봐")
                self.raw("회복 도움")
                action_controls(self.char1, self.index)
            effect.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        self.raw("의무관에게 20 회복")
        self.assertEqual(self.char1.profile_snapshot()["hp"], 21)
        row = next(row for row in provider_controls(self.char1, self.doctor)
                   if row["action"]["action_id"] == "medical.treat")
        from server.conf.primal_inputfuncs import pz_action

        payload = {**row["action"], "request_id": "m06-medical-once"}
        pz_action(self.session, payload)
        after = self.snapshot()
        pz_action(self.session, payload)
        self.assertEqual(self.snapshot(), after)
        self.assertEqual(after[0]["hp"], 60)

    def test_historical_provider_attribute_keeps_typed_gateway_and_no_duplicate_ui(self):
        obj = create_object(ActionObject, key="호환 보급함", location=self.char1.location,
                            attributes=[("action_provider_id", "world.supplycache")])
        rows = provider_controls(self.char1, obj)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"]["action_id"], "world.supplycache")
        state = multiplayer_state(self.char1)
        entry = next(entry for entry in state["interactables"] if entry["name"] == obj.key)
        self.assertEqual(entry["actions"], rows)
        self.assertFalse(any(row["action"]["roles"]["provider"][0]["identity"] == str(obj.pk)
                             for row in state["action_controls"]))

    def test_room_hint_only_checks_its_verb_and_keeps_current_provider_guards(self):
        from typeclasses.interactables import Shopkeeper
        from world.observation import context_for
        from world.room_hints import render

        self.char1.location = self.rooms["weapon_shop"]
        shop = next(obj for obj in self.char1.location.contents if isinstance(obj, Shopkeeper))
        service = self.index.services["room_npc.buy"]
        unrelated = Mock(wraps=service.presenter)
        index = replace(self.index, services={**self.index.services,
                                             service.id: replace(service, presenter=unrelated)})
        before = self.snapshot()
        with patch("world.actions.manifest.get_index", return_value=index):
            self.assertEqual(render(context_for(self.char1)), "무기상 목록")
        # 목록 힌트에 구매 버튼 전체 생성은 필요하지 않다. 실제 서비스는 실행하지 않는다.
        self.assertEqual(unrelated.call_count, 0)
        self.assertEqual(self.snapshot(), before)
        shop.locks.add("call:false()")
        self.assertEqual(render(context_for(self.char1)), "")
        shop.locks.add("call:all()")
        shop.db.action_available = False
        self.assertEqual(render(context_for(self.char1)), "")
