"""프로젝트/미관리/DefaultExit와 인자를 허용한 custom Exit의 실제 dispatcher 경계."""

from unittest.mock import Mock, patch

from evennia import create_object
from evennia.objects.models import ObjectDB
from evennia.objects.objects import DefaultExit, ExitCommand
from evennia.typeclasses.models import Attribute
from typeclasses.exits import Exit
from typeclasses.explorers import Explorer
from world.item_entities.models import ItemEntity, ItemRuntime, ItemSequence

from tests.base import WorldCommandTest


class HookExitCommand(ExitCommand):
    def at_pre_cmd(self):
        self.caller.db.exit_hook_ran = True


class PermissiveExit(DefaultExit):
    exit_command = HookExitCommand

    def create_exit_cmdset(self, obj):
        cmdset = super().create_exit_cmdset(obj)
        for command in cmdset:
            command.arg_regex = None
        return cmdset


class ExitPolicyTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        super().setUp()
        self.rooms = self.world_rooms()
        self.origin = self.rooms["hq_stairs_4f"]
        self.char1.location = self.origin
        self.char1.push_state = Mock()

    def snapshot(self):
        return {model._meta.label: list(model.objects.order_by("pk").values())
                for model in (ObjectDB, Attribute, ItemEntity, ItemSequence, ItemRuntime)}

    def test_unmanaged_default_and_permissive_exits_reject_arguments_before_hooks(self):
        for cls, name, alias in ((Exit, "사유통로", "private"),
                                 (DefaultExit, "기본통로", "base"),
                                 (PermissiveExit, "북", "n")):
            with self.subTest(typeclass=cls):
                obj = create_object(cls, key=name, aliases=[alias], location=self.origin,
                                    destination=self.rooms["hq_stairs_5f"])
                self.assertEqual(obj.tags.all(), [])
                self.char1.change(lambda p: p.update(hp=1, command_shortcuts={"실패": [name + " 잘못된인자"]}))
                before = self.snapshot()
                with patch("typeclasses.explorers.time", return_value=160):
                    for raw in (name + " 잘못된인자", alias + " 잘못된인자", "실패",
                                name + " 잘못된인자, 실패 해"):
                        self.char1.execute_cmd(raw)
                        self.assertEqual(self.char1.location, self.origin, raw)
                        self.assertEqual(self.snapshot(), before, raw)
                    if name == "북":
                        self.char1.execute_cmd("ㅂ 잘못된인자")
                        self.assertEqual(self.snapshot(), before)
                self.char1.execute_cmd(alias)
                self.assertEqual(self.char1.zone, "hq_stairs_5f")
                self.char1.location = self.origin
                self.char1.execute_cmd(name)
                self.assertEqual(self.char1.zone, "hq_stairs_5f")
                self.char1.location = self.origin
                obj.delete()

    def test_permissive_exit_does_not_capture_postfix_observation_or_normal_commands(self):
        from world import text as ft

        obj = create_object(PermissiveExit, key="북", aliases=["n"], location=self.origin,
                            destination=self.rooms["hq_stairs_5f"])
        with patch.object(obj, "return_appearance", return_value=ft.text("실제 관찰 결과")) as appearance:
            for raw in ("북 보기", "북 봐", "n 보기"):
                with patch.object(self.char1, "msg") as output:
                    self.char1.execute_cmd(raw)
                self.assertIn("실제 관찰 결과", str(output.call_args_list))
                self.assertEqual(self.char1.location, self.origin, raw)
                self.assertFalse(self.char1.db.exit_hook_ran, raw)
            self.assertEqual(appearance.call_count, 3)
        for raw in ("상태", "'북 잘못된인자"):
            self.char1.execute_cmd(raw)
            self.assertEqual(self.char1.location, self.origin, raw)
            self.assertFalse(self.char1.db.exit_hook_ran, raw)
