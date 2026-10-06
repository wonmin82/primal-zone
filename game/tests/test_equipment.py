"""슬롯별 장비 행동의 실제 명령, 저장 및 표시 회귀 검사."""

from copy import deepcopy
from unittest.mock import Mock, patch

from commands.character import Help, Look
from commands.registry import COMMANDS
from typeclasses.explorers import Explorer
from world import presentation as view
from world import rules
from world.content import EQUIPMENT_ACTIONS, ITEMS, SHOP_CATALOGS

from tests.base import WorldCommandTest


def tokens(message, role):
    return [s["text"] for s in message.segments if s["role"] == role]


class EquipmentTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        super().setUp()
        self.rooms = self.world_rooms()
        self.char1.location = self.rooms["dock"]
        self.char1.push_state = Mock()

    def test_all_gear_commands_save_only_the_matching_slot_and_emit_item_role(self):
        self.char1.change(lambda p: p["inventory"].update({i: 1 for i in ITEMS}))
        for identity, data in ITEMS.items():
            action = EQUIPMENT_ACTIONS.get(data["slot"])
            if not action:
                continue
            with self.subTest(item=identity):
                old = self.char1.profile()["equipment"].get(data["slot"])
                if old:
                    self.char1.change(lambda p: rules.unequip(p, old, data["slot"]))
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
        for raw in ("무장 절단마체테", "착용 강화방호조끼", "절단마체테 equip"):
            before = self.char1.profile()
            with patch.object(self.char1, "msg") as message:
                self.char1.execute_cmd(raw)
            self.assertEqual(self.char1.profile(), before)
            self.assertIn("대상 뒤에 행동", str(message.call_args_list))

    def test_closeout_weapon_swap_requires_explicit_unequip(self):
        self.char1.change(lambda p: p["inventory"].update(cutting_machete=1))
        before = deepcopy(self.char1.profile())
        with patch.object(self.char1, "msg") as message:
            self.char1.execute_cmd("절단마체테 무장")
        self.assertIn("먼저 기존 장비를 해제", str(message.call_args_list))
        self.assertEqual(self.char1.profile(), before)
        self.char1.execute_cmd("탐사용 벌목도 해제")
        self.assertIsNone(self.char1.profile()["equipment"]["weapon"])
        self.assertIsNone(Explorer.profile(self.char1).equipment_context.active)
        self.char1.execute_cmd("절단마체테 무장")
        self.assertEqual(self.char1.profile()["equipment"]["weapon"], "cutting_machete")
        self.assertIn("절단마체테 [주무기]", view.equipment(self.char1.profile()))

    def test_spaced_names_aliases_and_combat_restriction(self):
        self.char1.change(lambda p: p.update(credits=1000))
        for name, identity, alias in (
            ("절단마체테", "cutting_machete", "WIELD"),
            ("강화방호조끼", "armor", "wear"),
        ):
            self.char1.location = self.rooms["weapon_shop" if identity == "cutting_machete" else "armor_shop"]
            self.char1.execute_cmd(f"{name} 구매")
            slot = ITEMS[identity]["slot"]
            self.char1.change(lambda p: rules.unequip(p, p["equipment"][slot], slot))
            self.char1.execute_cmd(f"{name} {alias}")
            self.assertEqual(self.char1.profile()["equipment"][ITEMS[identity]["slot"]], identity)
        self.char1.change(lambda p: p.update(combat_target=123))
        before = self.char1.profile()
        for raw in ("탐사용 벌목도 무장", "탐사대 작업복 착용"):
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
            self.assertEqual(entry["slot"], {"weapon": "hands", "armor": "body"}.get(data["slot"], data["slot"]))
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
        for identity in ("jungle_longblade", "tactical_protective_suit"):
            slot = ITEMS[identity]["slot"]
            self.char1.change(lambda p: rules.unequip(p, p["equipment"][slot], slot))
            self.char1.change(lambda p: rules.equip(p, identity, slot))
        self.assertIn(ITEMS["jungle_longblade"]["name"] + " [주무기]", view.equipment(self.char1.profile()))
        self.assertEqual((rules.stats(self.char1.profile())["attack"], rules.stats(self.char1.profile())["defense"]), (16, 3))
        for shop_id, catalog in SHOP_CATALOGS.items():
            self.assertEqual({ITEMS[i]["name"] for i in catalog["purchase_catalog"]}, set(tokens(view.shop(shop_id, "상인"), "item")))
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
