"""슬롯별 장비 행동의 실제 명령, 저장 및 표시 회귀 검사."""

from copy import deepcopy
from unittest.mock import Mock, patch

from commands.character import Help, Look
from commands.registry import COMMANDS
from evennia.utils.test_resources import EvenniaCommandTest
from typeclasses.explorers import Explorer
from world import presentation as view
from world import rules
from world.bootstrap import build_world
from world.content import EQUIPMENT_ACTIONS, ITEMS, SHOP


def tokens(message, role):
    return [s["text"] for s in message.segments if s["role"] == role]


class EquipmentTests(EvenniaCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.char1.location = build_world()["dock"]
        self.char1.push_state = Mock()

    def test_all_gear_commands_save_only_the_matching_slot_and_emit_item_role(self):
        self.char1.change(lambda p: p["inventory"].update({i: 1 for i in ITEMS}))
        for identity, data in ITEMS.items():
            action = EQUIPMENT_ACTIONS.get(data["slot"])
            if not action:
                continue
            with self.subTest(item=identity):
                before = deepcopy(self.char1.profile())
                with patch.object(self.char1, "msg") as message:
                    self.char1.execute_cmd(f"{data['name']} {action}")
                expected = deepcopy(before)
                expected["equipment"][data["slot"]] = identity
                self.assertEqual(self.char1.profile(), expected)
                output = message.call_args.args[0]
                self.assertIn(data["name"], tokens(output, "item"))
                self.assertIn(f"{action}했다.", output)

    def test_wrong_actions_and_legacy_alias_do_not_save(self):
        self.char1.change(lambda p: p["inventory"].update({i: 1 for i in ITEMS}))
        for identity, data in ITEMS.items():
            for slot, action in EQUIPMENT_ACTIONS.items():
                if slot == data["slot"]:
                    continue
                with self.subTest(item=identity, action=action):
                    before = self.char1.profile()
                    with patch.object(self.char1, "msg") as message:
                        self.char1.execute_cmd(f"{data['name']} {action}")
                    self.assertEqual(self.char1.profile(), before)
                    if data["slot"] in EQUIPMENT_ACTIONS:
                        self.assertIn(
                            f"{data['name']} {EQUIPMENT_ACTIONS[data['slot']]}",
                            str(message.call_args_list),
                        )
        for raw in ("무장 강철마체테", "착용 강화조끼", "강철마체테 equip"):
            before = self.char1.profile()
            with patch.object(self.char1, "msg") as message:
                self.char1.execute_cmd(raw)
            self.assertEqual(self.char1.profile(), before)
            self.assertIn("대상 뒤에 행동", str(message.call_args_list))

    def test_spaced_names_aliases_and_combat_restriction(self):
        self.char1.change(lambda p: p.update(credits=1000))
        for name, identity, alias in (
            ("강철 마체테", "blade", "WIELD"),
            ("강화 조끼", "armor", "wear"),
        ):
            self.char1.execute_cmd(f"{name} 구매")
            self.char1.execute_cmd(f"{name} {alias}")
            self.assertEqual(self.char1.profile()["equipment"][ITEMS[identity]["slot"]], identity)
        self.char1.change(lambda p: p.update(combat_target=123))
        before = self.char1.profile()
        for raw in ("낡은마체테 무장", "탐사조끼 착용"):
            with patch.object(self.char1, "msg") as message:
                self.char1.execute_cmd(raw)
            self.assertIn("전투 중", str(message.call_args_list))
            self.assertEqual(self.char1.profile(), before)

    def test_state_look_inventory_equipment_and_help_share_slot_actions(self):
        self.char1.change(lambda p: p["inventory"].update({i: 1 for i in ITEMS}))
        with patch.object(self.char1.sessions, "count", return_value=1):
            with patch.object(self.char1, "msg") as message:
                Explorer.push_state(self.char1)
        state = message.call_args.kwargs["pz_state"][0][0]
        for entry in state["inventory"]:
            data = ITEMS[entry["id"]]
            self.assertEqual(entry["slot"], data["slot"])
            self.assertEqual(entry["equip_action"], EQUIPMENT_ACTIONS.get(data["slot"]))
            if data["slot"] not in EQUIPMENT_ACTIONS:
                continue
            command = Look()
            command.caller, command.args = self.char1, data["name"]
            with patch.object(self.char1, "msg") as message:
                command.func()
            output = next(c.args[0] for c in message.call_args_list if c.args)
            self.assertEqual(tokens(output, "item"), [data["name"]])
            self.assertEqual(tokens(output, "command"), [entry["equip_action"]])
            self.assertNotIn("+0", output)
        bag = view.inventory(self.char1.profile())
        self.assertEqual(set(tokens(bag, "item")), {i["name"] for i in ITEMS.values()})
        for identity in ("jungle_blade", "tactical_vest"):
            self.char1.change(lambda p: rules.equip(p, identity, ITEMS[identity]["slot"]))
        self.assertIn("공격 +9 · 방어 +3", view.equipment(self.char1.profile()))
        self.assertTrue({ITEMS[i]["name"] for i in SHOP} <= set(tokens(view.shop(), "item")))
        for action, alias in (("무장", "wield"), ("착용", "wear")):
            registered = [c for c in COMMANDS if c.key == action]
            self.assertEqual(len(registered), 1)
            self.assertEqual(list(registered[0].aliases), [alias])
            command = Help()
            command.caller, command.args = self.char1, action
            with patch.object(self.char1, "msg") as message:
                command.run()
            self.assertIn(alias, tokens(message.call_args.args[0], "command"))
            self.assertIn(registered[0].usage, message.call_args.args[0])
