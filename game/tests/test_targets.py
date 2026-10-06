from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock, patch

from commands.character import Look
from evennia import create_object
from typeclasses.enemies import Enemy, room_enemies
from typeclasses.explorers import Explorer
from typeclasses.interactables import SupplyCache
from typeclasses.loot import Corpse, DroppedLoot, room_loot, take_loot
from typeclasses.parties import invite, respond
from world import rules
from world.state import multiplayer_state
from world.targets import (
    Mode,
    TargetSelector,
    labels,
    names,
    ordered,
    parse_loot,
    parse_selector,
    resolve,
)

from tests.base import WorldCommandTest


class SelectorGrammarTests(TestCase):
    def test_modes_spaces_and_numeric_names(self):
        self.assertEqual(parse_selector("갈퀴 사냥룡").mode, Mode.DEFAULT)
        self.assertEqual(
            parse_selector("갈퀴 사냥룡 2"), TargetSelector("갈퀴 사냥룡", Mode.INDEX, 2)
        )
        self.assertEqual(parse_selector("회수 부품 모두"), TargetSelector("회수 부품", Mode.ALL))
        known = ["장치 2"]
        self.assertEqual(parse_selector("장치 2", known), TargetSelector("장치 2"))
        self.assertEqual(parse_selector("장치 2 3", known), TargetSelector("장치 2", Mode.INDEX, 3))
        self.assertEqual(parse_selector("장치 2 모두", known), TargetSelector("장치 2", Mode.ALL))

    def test_exclusive_modes_positive_index_and_no_prefix_all(self):
        for value in (
            "갈퀴사냥룡 2 모두",
            "갈퀴사냥룡 모두 2",
            "시체 3 모두",
            "시체 0",
            "전체 회수부품",
            "모든 갈퀴사냥룡",
            "모두",
        ):
            with self.subTest(value=value), self.assertRaises(rules.RuleError):
                parse_selector(value)

    def test_source_and_shorthand_normalize_to_same_model(self):
        for value in ("모두", "전리품 모두"):
            self.assertEqual(parse_loot(value).target, TargetSelector("전리품", Mode.ALL))
        for prefix, source in (
            ("시체에서", TargetSelector("시체")),
            ("시체 2에서", TargetSelector("시체", Mode.INDEX, 2)),
            ("모든 시체에서", TargetSelector("시체", Mode.ALL)),
        ):
            for value in ("모두", "전리품 모두", "회수 부품 모두"):
                request = parse_loot(prefix + " " + value)
                self.assertEqual(request.source, source)
                self.assertEqual(request.target.mode, Mode.ALL)
        self.assertEqual(parse_loot("시체 2에서 회수 부품 2").target.index, 2)

    def test_source_all_requires_target_all_and_rejects_old_syntax(self):
        for value in (
            "모든 시체에서 회수부품",
            "모든 시체에서 회수부품 2",
            "시체 모두에서 모두",
            "전체 시체에서 모두",
            "시체에서 전체 붕대",
            "전체 회수부품",
        ):
            with self.subTest(value=value), self.assertRaises(rules.RuleError):
                parse_loot(value)


class TargetIntegrationTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        for player in (self.char1, self.char2):
            player.location = self.rooms["grass"]
            player.push_state = Mock()
            self.enterContext(patch.object(player.sessions, "count", return_value=1))
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))
        for module in ("commands.character", "typeclasses.zone_rooms", "world.lifecycle", "typeclasses.loot", "typeclasses.enemies", "typeclasses.explorers"):
            self.enterContext(patch(f"{module}.time", return_value=100))

    def duplicate_enemies(self):
        enemy = room_enemies(self.char1.location)[0]
        for _ in range(2):
            obj = create_object(Enemy, key=enemy.key, location=enemy.location)
            obj.db.enemy_id = enemy.db.enemy_id
            obj.db.max_hp = obj.db.hp = enemy.db.max_hp
        return room_enemies(self.char1.location)

    def entry(self, item="scrap", quantity=3, player=None, party=None):
        player = player or self.char1
        return {
            "item": item,
            "quantity": quantity,
            "reserved_player": player.id if not party else None,
            "reserved_party": party.id if party else None,
            "assigned_player": player.id,
            "protection_until": 200,
        }

    def source(self, entries=None, corpse=True, name="갈퀴사냥룡의 시체"):
        obj = create_object(
            Corpse if corpse else DroppedLoot, key=name, location=self.char1.location
        )
        obj.db.entries = entries or [self.entry()]
        if corpse:
            obj.db.decay_at = 130
        return obj

    def take(self, args, now=100):
        return take_loot(self.char1, now=now, request=parse_loot(args))

    def look(self, args):
        command = Look()
        command.caller, command.args = self.char1, args
        with patch.object(self.char1, "msg") as message:
            command.func()
        return message.call_args.args[0]

    def test_default_index_all_look_and_attack_ordering(self):
        enemies = self.duplicate_enemies()
        for index, enemy in enumerate(enemies, 1):
            enemy.db.hp = index * 5
        self.assertIn("체력 5 /", self.look(enemies[0].key))
        self.assertNotIn("체력 10 /", self.look(enemies[0].key))
        self.assertIn("체력 10 /", self.look(enemies[0].key + " 2"))
        output = self.look(enemies[0].key + " 모두")
        for index in range(1, 4):
            self.assertIn(f"체력 {index * 5} /", output)
        state = multiplayer_state(self.char1, 100)
        for enemy, control in zip(enemies, state["enemies"]):
            self.char1.execute_cmd(control["attack_command"])
            self.assertEqual(self.char1.combat_target(), enemy)
            self.char1.leave_combat()
        for _ in range(3):
            self.char1.execute_cmd(enemies[0].key + " 공격")
            self.assertEqual(self.char1.combat_target(), enemies[0])
        self.char1.leave_combat()
        before = self.char1.profile()
        with patch.object(self.char1, "msg") as message:
            self.char1.execute_cmd(enemies[0].key + " 모두 공격")
        self.assertIn("한 대상을", str(message.call_args_list))
        self.assertEqual(self.char1.profile(), before)
        self.assertTrue(all(not enemy.db.combatants for enemy in enemies))

    def test_duplicate_room_prose_visibility_and_no_speculative_claim_skip(self):
        enemies = self.duplicate_enemies()
        output = self.char1.location.return_appearance(self.char1)
        self.assertIn("세 마리가", output)
        for index in range(1, 4):
            self.assertIn(f"'{enemies[0].key} {index}'", output)
        self.assertNotIn("적 1 ·", output)
        enemies[0].engage(self.char2, now=100)
        self.char1.execute_cmd(enemies[0].key + " 공격")
        self.assertIsNone(self.char1.combat_target())
        self.char1.execute_cmd(enemies[0].key + " 2 공격")
        self.assertEqual(self.char1.combat_target(), enemies[1])
        self.char1.leave_combat()
        enemies[1].locks.add("view:false()")
        state = multiplayer_state(self.char1, 100)
        self.assertEqual([e["id"] for e in state["enemies"]], [enemies[0].id, enemies[2].id])
        self.assertEqual(state["enemies"][1]["label"], enemies[2].key + " 2")

    def test_action_object_default_index_all_cardinality_and_no_reward_skip(self):
        objects = [
            create_object(SupplyCache, key="보급상자", location=self.char1.location)
            for _ in range(3)
        ]
        selector = parse_selector("보급상자")
        self.assertEqual(resolve(objects[::-1], selector, self.char1), [objects[0]])
        self.char1.execute_cmd("보급상자 2 조사")
        self.assertTrue(self.char1.profile()["discoveries"]["supply_cache"])
        before = self.char1.profile()
        self.char1.execute_cmd("보급상자 조사")
        self.assertEqual(self.char1.profile(), before)
        state = multiplayer_state(self.char1, 100)
        self.assertEqual(state["interactables"][1]["actions"][0]["command"], "보급상자 2 조사")
        for action in ("대화", "조사", "수리"):
            self.char1.execute_cmd("보급상자 모두 " + action)
            self.assertEqual(self.char1.profile(), before)

    def test_numeric_display_name_is_not_forced_to_index(self):
        obj = create_object(SupplyCache, key="장치 2", location=self.char1.location)
        selector = parse_selector("장치 2", names(obj))
        self.assertEqual(resolve([obj], selector, self.char1), [obj])
        self.assertIn(obj.key, self.look("장치 2"))

    def test_corpse_global_numbering_all_prose_and_decay_renumber(self):
        corpses = [self.source(), self.source(), self.source(name="밀림의포식자의 시체")]
        for index, corpse in enumerate(corpses, 1):
            corpse.db.entries = [self.entry(quantity=index)]
            if index > 1:
                corpse.db.decay_at = 200
        self.assertIn("×1", self.look("시체"))
        self.assertIn("×2", self.look("시체 2"))
        self.assertIn("밀림의포식자의 시체", self.look("시체 3"))
        overview = self.look("시체 모두")
        self.assertIn("주변에 시체 세 구", overview)
        self.assertNotIn("[시체 1]", overview)
        room = self.char1.location.return_appearance(self.char1)
        self.assertIn("갈퀴사냥룡의 시체 두 구", room)
        self.assertIn("'시체 3'", room)
        self.assertNotIn("시체 1 ·", room)
        corpses[0].reconcile(130)
        state = multiplayer_state(self.char1, 130)
        self.assertEqual(
            [source["id"] for source in state["corpses"]], [corpses[1].id, corpses[2].id]
        )
        self.assertEqual([source["label"] for source in state["corpses"]], ["시체 1", "시체 2"])

    def test_named_corpse_overview_keeps_room_global_source_numbers(self):
        self.source()
        self.source(name="밀림의포식자의 시체")
        self.source()
        output = self.look("갈퀴사냥룡의 시체 모두")
        self.assertIn("첫 번째 갈퀴사냥룡의 시체", output)
        self.assertIn("세 번째 갈퀴사냥룡의 시체", output)
        self.assertIn("'시체 1'", output)
        self.assertIn("'시체 3'", output)
        self.assertNotIn("'시체 2'", output)

    def test_single_corpse_detail_provides_executable_source_command(self):
        corpse = self.source()
        control = multiplayer_state(self.char1, 100)["corpses"][0]
        output = self.look("시체")
        self.assertIn("지정: 시체", output)
        self.assertIn("회수: " + control["take_command"], output)
        self.assertNotIn("시체 1", output)
        self.assertNotIn("가능한 행동 : 가져", output)
        self.assertIn({"role": "command", "text": "가져"}, output.segments)
        self.char1.execute_cmd(control["take_command"])
        self.assertEqual(corpse.db.entries, [])
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 3)
        empty = self.look("시체")
        self.assertIn("남은 전리품이 없다", empty)
        self.assertNotIn("회수:", empty)

    def test_numbered_corpse_detail_matches_controls_and_current_order(self):
        a, b, c = self.source(), self.source(), self.source(name="밀림의포식자의 시체")
        b.db.decay_at = c.db.decay_at = 200
        control = multiplayer_state(self.char1, 100)["corpses"][1]
        self.assertEqual(control["id"], b.id)
        output = self.look(control["look_command"].removesuffix(" 보기"))
        self.assertIn("지정: 시체 2", output)
        self.assertIn("회수: " + control["take_command"], output)
        self.char1.execute_cmd(control["take_command"])
        self.assertTrue(a.db.entries)
        self.assertFalse(b.db.entries)
        self.assertTrue(c.db.entries)
        a.reconcile(130)
        control = multiplayer_state(self.char1, 130)["corpses"][0]
        self.assertEqual(control["id"], b.id)
        self.assertEqual(control["label"], "시체 1")
        self.assertIn("지정: 시체 1", self.look("시체 1"))
        self.assertFalse(b.attributes.has("selector"))
        self.assertFalse(b.attributes.has("index"))

    def test_ground_detail_matches_entry_command_and_renumbers(self):
        a = self.source(corpse=False, name="회수부품")
        b = self.source(corpse=False, name="회수부품")
        control = multiplayer_state(self.char1, 100)["ground_loot"][1]["loot"][0]
        output = self.look("회수부품 2")
        self.assertIn("회수: " + control["take_command"], output)
        self.assertNotIn("가능한 행동 : 가져", output)
        self.assertIn({"role": "command", "text": "가져"}, output.segments)
        self.char1.execute_cmd(control["take_command"])
        self.assertEqual(a.db.entries[0]["quantity"], 3)
        self.assertEqual(b.db.entries[0]["quantity"], 2)
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 1)
        for _ in range(3):
            self.take("회수부품")
        control = multiplayer_state(self.char1, 100)["ground_loot"][0]["loot"][0]
        self.assertEqual(control["take_command"], "회수부품 가져")
        self.assertIn("회수: 회수부품 가져", self.look("회수부품"))

    def test_corpse_ttl_selects_current_pool_and_never_duplicates(self):
        a, b, c = self.source(), self.source(), self.source(name="밀림의포식자의 시체")
        b.db.decay_at = c.db.decay_at = 200
        a.reconcile(130)
        state = multiplayer_state(self.char1, 130)
        self.assertEqual([source["label"] for source in state["corpses"]], ["시체 1", "시체 2"])
        self.assertEqual([source["id"] for source in state["corpses"]], [b.id, c.id])
        self.take("시체 2에서 모두", 130)
        self.assertEqual(c.db.entries, [])
        self.assertTrue(b.db.entries)
        with self.assertRaises(rules.RuleError):
            self.take("시체 2에서 모두", 130)
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 3)
        self.assertEqual(len(room_loot(self.char1.location, False)), 1)
        a.reconcile(131)
        self.assertEqual(len(room_loot(self.char1.location, False)), 1)

    def test_default_and_index_source_quantity_scope(self):
        a = self.source([self.entry(), self.entry("bandage", 2)])
        b = self.source([self.entry(), self.entry("bandage", 2)])
        self.take("시체에서 회수 부품")
        self.assertEqual(a.db.entries[0]["quantity"], 2)
        self.assertEqual(b.db.entries[0]["quantity"], 3)
        self.take("시체에서 회수부품 모두")
        self.assertEqual([e["id"] for e in a.db.entries], ["bandage"])
        self.take("시체에서 모두")
        self.assertEqual(a.db.entries, [])
        self.assertEqual(len(b.db.entries), 2)
        self.take("시체 2에서 회수부품")
        self.assertEqual(b.db.entries[0]["quantity"], 2)
        self.take("시체 2에서 회수부품 모두")
        self.take("시체 2에서 전리품 모두")
        self.assertEqual(b.db.entries, [])
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 6)

    def test_all_sources_matching_items_and_all_loot(self):
        a = self.source([self.entry(), self.entry("bandage", 2)])
        b = self.source([self.entry(), self.entry("bandage", 2)])
        self.take("모든 시체에서 회수부품 모두")
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 6)
        self.assertEqual([e["id"] for e in a.db.entries], ["bandage"])
        self.assertEqual([e["id"] for e in b.db.entries], ["bandage"])
        self.take("모든 시체에서 모두")
        self.assertEqual(a.db.entries, [])
        self.assertEqual(b.db.entries, [])
        self.assertEqual(self.char1.profile()["inventory"]["bandage"], 7)

    def test_index_entry_ground_quantity_and_shorthand(self):
        a = self.source(corpse=False)
        b = self.source([self.entry(quantity=4), self.entry("bandage", 2)], corpse=False)
        state = multiplayer_state(self.char1, 100)
        self.assertEqual(state["ground_loot"][1]["loot"][0]["take_command"], "회수부품 2 가져")
        self.take("회수 부품 2")
        self.assertEqual(a.db.entries[0]["quantity"], 3)
        self.assertEqual(b.db.entries[0]["quantity"], 3)
        self.take("회수부품")
        self.assertEqual(a.db.entries[0]["quantity"], 2)
        self.take("회수부품 모두")
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 7)
        self.take("모두")
        self.assertEqual(room_loot(self.char1.location, False), [])

    def test_entry_index_and_default_do_not_skip_protected_items(self):
        source = self.source([self.entry(player=self.char2), self.entry(quantity=2)])
        before = self.char1.profile()
        with self.assertRaises(rules.RuleError):
            self.take("시체에서 회수부품")
        self.assertEqual(self.char1.profile(), before)
        controls = multiplayer_state(self.char1, 100)["corpses"][0]["loot"]
        self.assertEqual(controls[1]["take_command"], "시체에서 회수부품 2 가져")
        self.take("시체에서 회수부품 2")
        self.assertEqual([e["quantity"] for e in source.db.entries], [3, 1])
        self.take("시체에서 회수부품 모두")
        self.assertEqual([e["quantity"] for e in source.db.entries], [3])
        source.db.decay_at = 300
        self.take("시체에서 모두", 200)
        self.assertEqual(source.db.entries, [])
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 5)

    def test_take_reconciles_expiring_source_before_number_resolution(self):
        a, b, c = self.source(), self.source(), self.source()
        b.db.decay_at = c.db.decay_at = 200
        self.take("시체 2에서 모두", 130)
        self.assertEqual([obj.id for obj in room_loot(self.char1.location)], [b.id, c.id])
        self.assertTrue(b.db.entries)
        self.assertFalse(c.db.entries)
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 3)
        self.assertEqual(len(room_loot(self.char1.location, False)), 1)
        a.reconcile(131)
        with self.assertRaises(rules.RuleError):
            self.take("시체 2에서 모두", 131)
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 3)

    def test_party_protected_partial_success_and_expiry(self):
        party = invite(self.char1, self.char2)
        respond(self.char2, True)
        other = create_object(Explorer, key="외부탐사자", location=self.char1.location)
        a = self.source([self.entry(party=party), self.entry("armor", 1, self.char2, party)])
        b = self.source([self.entry(player=other)])
        c = self.source([self.entry("bandage", 2, self.char2, party)])
        original = deepcopy(list(b.db.entries))
        self.take("모든 시체에서 모두")
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 3)
        self.assertEqual(self.char2.profile()["inventory"]["reinforced_vest"], 1)
        self.assertEqual(self.char2.profile()["inventory"]["bandage"], 5)
        self.assertEqual(list(b.db.entries), original)
        self.assertEqual(a.db.entries, [])
        self.assertEqual(c.db.entries, [])
        with self.assertRaises(rules.RuleError):
            self.take("시체 2에서 모두")
        # 만료된 시체는 바닥으로 옮겨져서 같은 보호 만료 시각을 사용한다.
        self.take("회수부품 모두", 201)
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 6)

    def test_multi_source_transaction_failure_and_failed_grammar_leave_state(self):
        party = invite(self.char1, self.char2)
        respond(self.char2, True)
        a = self.source([self.entry(party=party)])
        b = self.source([self.entry("armor", 1, self.char2, party)])
        before = [self.char1.profile(), self.char2.profile()]
        with patch.object(self.char2, "save_profile", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                self.take("모든 시체에서 모두")
        self.assertEqual([self.char1.profile(), self.char2.profile()], before)
        self.assertTrue(a.db.entries and b.db.entries)
        for args in (
            "모든 시체에서 회수부품",
            "시체 2 모두에서 모두",
            "전체 회수부품",
            "시체에서 전체 붕대",
        ):
            with self.assertRaises(rules.RuleError):
                self.take(args)
        self.assertEqual([self.char1.profile(), self.char2.profile()], before)

    def test_equipment_all_rejected_and_buttons_resolve_to_same_sources(self):
        before = self.char1.profile()
        for raw in ("탐사용 벌목도 모두 무장", "탐사대 작업복 모두 착용"):
            self.char1.execute_cmd(raw)
            self.assertEqual(self.char1.profile(), before)
        sources = [self.source(), self.source()]
        state = multiplayer_state(self.char1, 100)
        self.char1.execute_cmd(state["corpses"][1]["take_command"])
        self.assertTrue(sources[0].db.entries)
        self.assertFalse(sources[1].db.entries)
        self.assertEqual(ordered(sources), sources)
        self.assertEqual(labels(sources, lambda obj: "시체")[sources[1].id], "시체 2")
