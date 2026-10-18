"""슬롯별 장비 행동의 실제 명령, 저장 및 표시 회귀 검사."""

from copy import deepcopy
from unittest.mock import Mock, patch

from commands.character import Help, Look
from commands.registry import COMMANDS
from typeclasses.explorers import Explorer
from world import presentation as view
from world import rules
from world.actions.manifest import get_index
from world.actions.presentation import action_controls
from world.content import EQUIPMENT_ACTIONS, ITEMS, SHOP_CATALOGS
from world.equipment_service import equip_item, equipped_items, unequip_item
from world.item_entities.models import ItemEntity
from world.item_inventory import grant
from world.multiplayer import world_change

from tests.action_control_fixture import selection_label
from tests.base import WorldCommandTest
from tests.item_entity_fixture import NativeItemTest


def tokens(message, role):
    return [s["text"] for s in message.segments if s["role"] == role]


class EquipmentTests(NativeItemTest, WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        super().setUp()
        self.rooms = self.world_rooms()
        self.char1.location = self.rooms["dock"]
        self.char1.push_state = Mock()
        self.session.puppet = self.char1
        self.session.logged_in = True
        self.char1.sessions.add(self.session)
        # NativeItemTest의 동적 test_pistol은 도메인 전용 fixture이며 운영 Manifest 대상이 아니다.
        self.production_items = {key: data for key, data in ITEMS.items() if key != "test_pistol"}

    def all_items(self):
        # Fixture의 최종 실물 집합을 한 번 확정한다. 개별 사용자 명령의 검증은 아래에서 분리한다.
        with world_change():
            return {identity: grant(self.char1, identity)[0] for identity in self.production_items}

    def clear_equipment(self):
        for row in list(equipped_items(self.char1)):
            unequip_item(self.char1, row)

    def item(self, identity):
        return ItemEntity.objects.filter(owner_object=self.char1, definition_id=identity,
                                         location_kind__in=("inventory", "equipment")).first()

    def test_all_gear_commands_save_only_the_matching_slot_and_emit_item_role(self):
        rows = self.all_items()
        for identity, data in self.production_items.items():
            action = EQUIPMENT_ACTIONS.get(data["slot"])
            if not action:
                continue
            with self.subTest(item=identity):
                self.clear_equipment()
                before = {row.pk: (row.location_kind, row.slot, deepcopy(row.state), row.quantity)
                          for row in ItemEntity.objects.all()}
                archive = deepcopy(self.char1.db.profile)
                with patch.object(self.char1, "msg") as message:
                    self.char1.execute_cmd(f"{data['name']} {action}")
                row = rows[identity]
                row.refresh_from_db()
                slot = data["equipment_properties"]["slot"]
                self.assertEqual((row.location_kind, row.slot), ("equipment", slot))
                self.assertEqual(list(equipped_items(self.char1).values_list("pk", flat=True)), [row.pk])
                expected = {**before, row.pk: ("equipment", slot, before[row.pk][2], before[row.pk][3])}
                self.assertEqual({entry.pk: (entry.location_kind, entry.slot, entry.state, entry.quantity)
                                  for entry in ItemEntity.objects.all()}, expected)
                # Archive의 legacy 장비 dict를 authority로 쓰거나 이중 저장하지 않는다.
                self.assertEqual(self.char1.db.profile["equipment"], archive["equipment"])
                output = next(call.args[0] for call in message.call_args_list if call.args and
                              f"{action}했다." in str(call.args[0]))
                self.assertIn(selection_label(row), tokens(output, "item"))
                self.assertIn(f"{action}했다.", output)

    def test_wrong_actions_and_legacy_alias_do_not_save(self):
        self.all_items()
        for identity, data in self.production_items.items():
            for slot, action in EQUIPMENT_ACTIONS.items():
                if slot == data["slot"]:
                    continue
                with self.subTest(item=identity, action=action):
                    before = self.atomic_state()
                    with patch.object(self.char1, "msg") as message:
                        self.char1.execute_cmd(f"{data['name']} {action}")
                    self.assertEqual(self.atomic_state(), before)
                    if data["slot"] in EQUIPMENT_ACTIONS:
                        self.assertIn(
                            f"{data['name']} {EQUIPMENT_ACTIONS[data['slot']]}",
                            str(message.call_args_list),
                        )
        for raw in ("무장 절단마체테", "착용 강화방호조끼", "절단마체테 equip"):
            before = self.atomic_state()
            with patch.object(self.char1, "msg") as message:
                self.char1.execute_cmd(raw)
            self.assertEqual(self.atomic_state(), before)
            self.assertIn("대상 뒤에 행동", str(message.call_args_list))

    def test_closeout_weapon_swap_requires_explicit_unequip(self):
        # 이전 단일 weapon 칸 대신 native의 양손 장비로 손 공간을 채워 동일한 자동 교체 금지를 검사한다.
        previous = self.create("pioneer_spear")
        target = self.create("cutting_machete")
        equip_item(self.char1, previous, "weapon")
        before = self.atomic_state()
        with patch.object(self.char1, "msg") as message:
            self.char1.execute_cmd("절단마체테 무장")
        self.assertIn("먼저 기존 장비를 해제", str(message.call_args_list))
        self.assertEqual(self.atomic_state(), before)
        self.char1.execute_cmd("개척창 해제")
        self.assertFalse(equipped_items(self.char1).exists())
        self.assertIsNone(Explorer.profile(self.char1).equipment_context.active)
        self.char1.execute_cmd("절단마체테 무장")
        self.assertEqual(list(equipped_items(self.char1).values_list("pk", flat=True)), [target.pk])
        self.assertIn(selection_label(target) + " [주무기]", view.equipment(self.char1.profile()))

    def test_spaced_names_aliases_and_combat_restriction(self):
        self.char1.change(lambda p: p.update(credits=1000))
        for name, identity, alias in (
            ("절단마체테", "cutting_machete", "WIELD"),
            ("강화방호조끼", "reinforced_vest", "입어"),
        ):
            self.char1.location = self.rooms["weapon_shop" if identity == "cutting_machete" else "armor_shop"]
            self.char1.execute_cmd(f"{name} 사")
            self.clear_equipment()
            self.char1.execute_cmd(f"{name} {alias}")
            self.assertTrue(equipped_items(self.char1).filter(definition_id=identity).exists())
        self.char1.change(lambda p: p.update(combat_target=123))
        # 기존 장비가 소지 중이어야 전투 제한을 실제 장착 도메인에서 확인한다.
        for identity in ("explorer_machete", "expedition_workwear"):
            grant(self.char1, identity)
        before = self.atomic_state()
        for raw in ("탐사용 벌목도 무장", "탐사대 작업복 착용"):
            with patch.object(self.char1, "msg") as message:
                self.char1.execute_cmd(raw)
            self.assertIn("전투 중", str(message.call_args_list))
            self.assertEqual(self.atomic_state(), before)

    def test_state_look_inventory_equipment_and_help_share_slot_actions(self):
        self.all_items()
        with patch.object(self.char1.sessions, "count", return_value=1):
            with patch.object(self.char1, "msg") as message:
                Explorer.push_state(self.char1)
        state = message.call_args.kwargs["pz_state"][0][0]
        index = get_index()
        controls = action_controls(self.char1, index)
        for entry in state["inventory"]:
            if entry["location"] == "inside":
                continue
            data = ITEMS[entry["id"]]
            self.assertEqual(entry["slot"], data.get("equipment_properties", {}).get("slot", data["slot"]))
            self.assertEqual(entry["equip_action"], EQUIPMENT_ACTIONS.get(data["slot"]))
            if data["slot"] not in EQUIPMENT_ACTIONS:
                continue
            command = Look()
            command.caller, command.args = self.char1, data["name"]
            with patch.object(self.char1, "msg") as message:
                command.func()
            output = next(c.args[0] for c in message.call_args_list if c.args)
            self.assertEqual(tokens(output, "item"), [entry["selector"]])
            # Native의 상세 관찰은 d33e3ef 이전부터 description/state이고, 과거 adapter의
            # Action 안내 형식도 순수 presentation 회귀로 별도 보존한다.
            legacy = view.item_appearance(entry["id"])
            self.assertEqual(tokens(legacy, "command"), [entry["equip_action"]])
            self.assertTrue(any(c["action"]["roles"]["provider"][0]["identity"] == entry["identity"]
                                and index.verbs[index.actions[c["action"]["action_id"]].verb_id].key == entry["equip_action"]
                                for c in controls))
            self.assertNotIn("+0", output)
        bag = view.inventory(self.char1.profile())
        self.assertEqual(set(tokens(bag, "item")), {row["selector"] for row in state["inventory"]})
        self.clear_equipment()
        for identity in ("jungle_longblade", "tactical_protective_suit"):
            equip_item(self.char1, self.item(identity))
        self.assertIn(selection_label(self.item("jungle_longblade")) + " [주무기]", view.equipment(self.char1.profile()))
        self.assertEqual((rules.stats(self.char1.profile())["attack"], rules.stats(self.char1.profile())["defense"]), (14, 4))
        for shop_id, catalog in SHOP_CATALOGS.items():
            self.assertEqual({ITEMS[i]["name"] for i in catalog["purchase_catalog"]}, set(tokens(view.shop(shop_id, "상인"), "item")))
        for action, aliases in (("무장", ["wield"]), ("착용", ["입어", "입"])):
            self.assertFalse(any(c.key == action for c in COMMANDS))
            registered = [verb for verb in get_index().verbs.values() if verb.key == action]
            self.assertEqual(len(registered), 1)
            self.assertCountEqual(registered[0].aliases, aliases)
            command = Help()
            command.caller, command.args = self.char1, action
            with patch.object(self.char1, "msg") as message:
                command.run()
            for alias in aliases:
                self.assertIn(alias, tokens(message.call_args.args[0], "command"))
            self.assertIn(registered[0].usage, message.call_args.args[0])
