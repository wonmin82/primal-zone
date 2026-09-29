"""새 상호작용의 실제 postfix 명령·원자성·저장·기존 loot 회귀."""

from unittest.mock import Mock, patch

from evennia import create_object, search_tag
from evennia.utils.dbserialize import deserialize
from typeclasses.enemies import Enemy, room_enemies
from typeclasses.explorers import Explorer
from typeclasses.interactables import Container
from typeclasses.loot import DroppedLoot, room_loot, take_loot
from world import presentation as view
from world import rules
from world.content import ENEMIES, ITEMS, SHOP_CATALOGS
from world.item_transfers import transfer
from world.state import multiplayer_state
from world.targets import Mode, TargetSelector, parse_relation, parse_selector, stack_selector

from tests.base import WorldCommandTest


class ItemInteractionTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        for player in (self.char1, self.char2):
            player.location = self.rooms["storage_room"]
            player.push_state = Mock()
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))
        self.box = search_tag("shared_container", category="primal_interactable")[0]
        self.locker = search_tag("personal_locker", category="primal_interactable")[0]

    def command(self, value, caller=None):
        caller = caller or self.char1
        with patch.object(caller, "msg") as message:
            caller.execute_cmd(value)
        return str(message.call_args_list)

    def test_attack_alias_default_index_and_all_cardinality(self):
        self.char1.location = self.rooms["trail"]
        enemy = room_enemies(self.char1.location)[0]
        duplicate = create_object(Enemy, key=enemy.key, location=enemy.location)
        duplicate.db.enemy_id = enemy.db.enemy_id
        duplicate.db.hp = duplicate.db.max_hp = enemy.db.max_hp
        for action in ("공격", "때려"):
            self.command(enemy.key + " " + action)
            self.assertEqual(self.char1.combat_target(), enemy)
            self.char1.leave_combat()
        self.command(enemy.key + " 2 때려")
        self.assertEqual(self.char1.combat_target(), duplicate)
        self.char1.leave_combat()
        before = self.char1.profile()
        self.assertIn("한 대상을", self.command(enemy.key + " 모두 때려"))
        self.assertEqual(self.char1.profile(), before)

    def test_drop_creates_public_ground_and_existing_take_recovers_quantities(self):
        self.command("붕대 버려")
        dropped = room_loot(self.char1.location, False)[0]
        self.assertIsInstance(dropped, DroppedLoot)
        self.assertEqual(dropped.db.entries[0]["quantity"], 1)
        self.assertEqual(dropped.db.entries[0]["protection_until"], 0)
        self.assertIsNone(dropped.db.entries[0]["assigned_player"])
        self.assertEqual(self.char1.profile()["inventory"]["bandage"], 2)
        self.command("붕대 가져", self.char2)
        self.assertEqual(self.char2.profile()["inventory"]["bandage"], 4)
        self.command("붕대 모두 버려")
        self.assertNotIn("bandage", self.char1.profile()["inventory"])
        self.command("붕대 모두 가져")
        self.assertEqual(self.char1.profile()["inventory"]["bandage"], 2)
        self.assertEqual(room_loot(self.char1.location, False), [])

    def test_give_single_all_and_invalid_recipients_do_not_change_owners(self):
        self.char1.location = self.char2.location = self.rooms["dock"]
        self.command(f"{self.char2.key}에게 붕대 줘")
        self.assertEqual(
            (
                self.char1.profile()["inventory"]["bandage"],
                self.char2.profile()["inventory"]["bandage"],
            ),
            (2, 4),
        )
        self.command(f"{self.char2.key}에게 붕대 모두 줘")
        self.assertNotIn("bandage", self.char1.profile()["inventory"])
        self.assertEqual(self.char2.profile()["inventory"]["bandage"], 6)
        self.char1.change(lambda p: rules.add_item(p, "bandage"))
        for target in (self.char1.key, "윤대장", "없는탐사자", self.char2.key):
            if target == self.char2.key:
                self.char2.location = self.rooms["grass"]
            before = (self.char1.profile(), self.char2.profile())
            self.command(f"{target}에게 붕대 줘")
            self.assertEqual((self.char1.profile(), self.char2.profile()), before)

    def test_equipped_only_copy_is_blocked_for_every_transfer_and_extra_copies_move(self):
        for raw in (
            "낡은마체테 버려",
            f"{self.char2.key}에게 낡은마체테 줘",
            "보관상자에 낡은마체테 넣어",
            "개인 보관함에 낡은마체테 넣어",
        ):
            before = (self.char1.profile(), self.char2.profile(), deserialize(self.box.db.items))
            self.assertIn("해제", self.command(raw))
            self.assertEqual(
                (self.char1.profile(), self.char2.profile(), deserialize(self.box.db.items)), before
            )
        self.char1.change(lambda p: rules.add_item(p, "machete", 2))
        self.command("낡은마체테 버려")
        self.command("보관상자에 낡은마체테 모두 넣어")
        self.assertEqual(self.char1.profile()["inventory"]["machete"], 1)
        self.assertEqual(self.box.db.items, {"machete": 1})
        self.assertEqual(self.char1.profile()["equipment"]["weapon"], "machete")

    def test_quest_key_transfer_block_and_original_gate_lifecycle(self):
        def prepare(p):
            p["quests"]["radio_tower"]["claimed"] = True
            rules.jungle_talk(p)
            rules.jungle_mark(p, "watch_marked")
            rules.jungle_mark(p, "road_marked")

        self.char1.change(prepare)
        for raw in (
            "밀림 신호전지 버려",
            f"{self.char2.key}에게 밀림 신호전지 줘",
            "보관상자에 밀림 신호전지 넣어",
            "개인 보관함에 밀림 신호전지 넣어",
        ):
            before = (self.char1.profile(), self.char2.profile(), deserialize(self.box.db.items))
            self.command(raw)
            self.assertEqual(
                (self.char1.profile(), self.char2.profile(), deserialize(self.box.db.items)), before
            )
        self.assertFalse(self.char1.change(lambda p: rules.jungle_mark(p, "road_marked")))
        self.assertEqual(self.char1.profile()["inventory"]["jungle_cell"], 1)
        self.char1.change(rules.open_jungle_gate)
        self.assertNotIn("jungle_cell", self.char1.profile()["inventory"])

    def test_food_shop_actions_and_failure_immutability(self):
        self.char1.location = self.rooms["supply_shop"]
        self.char1.change(lambda p: p.update(hp=20, credits=50))
        for identity, action in (("field_ration", "먹어"), ("water", "마셔")):
            name = ITEMS[identity]["name"]
            self.assertIn(name, view.shop("supply", "보급관"))
            before = self.char1.profile()
            self.command(name + " 구매")
            self.assertEqual(self.char1.profile()["credits"], before["credits"] - SHOP_CATALOGS["supply"][identity])
            self.command(name + " " + action)
            self.assertEqual(self.char1.profile()["hp"], before["hp"] + ITEMS[identity]["heal"])
            self.assertEqual(self.char1.profile()["proficiencies"], before["proficiencies"])
            self.assertIn(action, view.item_appearance(identity))
        self.char1.change(lambda p: p["inventory"].update(field_ration=2, water=2))
        for raw in (
            "야전식량 마셔",
            "정제수 먹어",
            "붕대 먹어",
            "야전식량 모두 먹어",
            "정제수 모두 마셔",
            "붕대 2 버려",
        ):
            before = self.char1.profile()
            self.command(raw)
            self.assertEqual(self.char1.profile(), before)
        self.char1.change(lambda p: p.update(hp=60, credits=0))
        for raw in ("야전식량 먹어", "정제수 마셔", "야전식량 구매", "정제수 구매"):
            before = self.char1.profile()
            self.command(raw)
            self.assertEqual(self.char1.profile(), before)

    def test_empty_equipment_persists_and_unarmed_combat_works(self):
        inventory = self.char1.profile()["inventory"]
        for raw in ("낡은마체테 벗어", "탐사조끼 해제"):
            before = self.char1.profile()
            self.command(raw)
            self.assertEqual(self.char1.profile(), before)
        self.command("낡은마체테 해제")
        self.command("탐사조끼 벗어")
        self.char1.attributes.reset_cache()
        profile = self.char1.profile()
        self.assertEqual(profile["equipment"], {"weapon": None, "armor": None})
        self.assertEqual(profile["inventory"], inventory)
        self.assertEqual(rules.stats(profile)["attack"], 7)
        self.assertIn("무기 없음", view.status(self.char1.key, profile))
        self.assertIn("없음", view.equipment(profile))
        with (
            patch.object(self.char1.sessions, "count", return_value=1),
            patch.object(self.char1, "msg") as message,
        ):
            Explorer.push_state(self.char1)
        state = message.call_args.kwargs["pz_state"][0][0]
        self.assertEqual(state["equipment"], profile["equipment"])
        self.assertFalse(any(i["equipped"] for i in state["inventory"]))
        self.char1.location = self.rooms["grass"]
        enemy = room_enemies(self.char1.location)[0]
        self.command(enemy.key + " 때려")
        self.assertEqual(self.char1.combat_target(), enemy)
        damage, outcome = rules.player_attack(
            profile, enemy.db.enemy_id, 100, 2.5, Mock(randint=Mock(return_value=0))
        )
        self.assertEqual(damage, max(1, 7 - ENEMIES[enemy.db.enemy_id]["defense"]))
        output = view.outgoing_attack(profile, enemy.key, outcome, damage)
        self.assertIn("맨손", output)
        self.char1.leave_combat()

    def test_shared_container_single_all_persistence_and_duplicate_selector(self):
        second = create_object(Container, key=self.box.key, location=self.char1.location)
        self.command("보관상자 2에 붕대 넣어")
        self.assertEqual(second.db.items, {"bandage": 1})
        self.assertEqual(self.box.db.items, {})
        self.command("보관상자 2에 붕대 모두 넣어")
        self.assertEqual(second.db.items, {"bandage": 3})
        self.command("보관상자 2에서 붕대 꺼내")
        self.assertEqual(second.db.items, {"bandage": 2})
        second.attributes.reset_cache()
        self.assertEqual(second.db.items, {"bandage": 2})
        self.assertIn("붕대 ×2", second.return_appearance(self.char1))
        self.command("보관상자 2에서 붕대 모두 꺼내")
        self.assertEqual(second.db.items, {})
        self.assertEqual(self.char1.profile()["inventory"]["bandage"], 3)
        for raw in (
            "보관상자 모두에 붕대 넣어",
            "모든 보관상자에서 붕대 꺼내",
            "보관상자에서 붕대 꺼내",
        ):
            before = self.char1.profile()
            self.command(raw)
            self.assertEqual(self.char1.profile(), before)
        state = multiplayer_state(self.char1)
        boxes = [obj for obj in state["interactables"] if obj["name"] == "보관상자"]
        self.assertEqual(
            [obj["look_command"] for obj in boxes], ["보관상자 1 보기", "보관상자 2 보기"]
        )

    def test_personal_locker_contents_are_per_caller_and_survive_cache_reload(self):
        self.command("개인 보관함에 붕대 모두 넣어")
        self.assertEqual(self.char1.profile()["storage"], {"bandage": 3})
        self.assertNotIn("붕대", self.locker.return_appearance(self.char2))
        self.command("개인 보관함에 탐사조끼 넣어", self.char2)
        self.assertEqual(self.char2.profile()["storage"], {})
        self.command("개인 보관함에 붕대 넣어", self.char2)
        self.assertEqual(self.char2.profile()["storage"], {"bandage": 1})
        self.char1.attributes.reset_cache()
        self.assertEqual(self.char1.profile()["storage"], {"bandage": 3})
        self.assertIn("붕대 ×3", self.locker.return_appearance(self.char1))
        self.assertIn("붕대 ×1", self.locker.return_appearance(self.char2))
        self.command("개인 보관함에서 붕대 꺼내")
        self.command("개인 보관함에서 붕대 모두 꺼내")
        self.assertEqual(self.char1.profile()["storage"], {})
        self.assertEqual(self.char2.profile()["storage"], {"bandage": 1})
        self.assertEqual(self.locker.db.items, {})

    def test_shared_last_unit_serialization_and_late_failure_rollback(self):
        self.box.db.items = {"bandage": 1}
        transfer(self.char1, "bandage", container=self.box, withdraw=True)
        before = self.char2.profile()
        with self.assertRaises(rules.RuleError):
            transfer(self.char2, "bandage", container=self.box, withdraw=True)
        self.assertEqual(self.char2.profile(), before)
        self.assertEqual(self.box.db.items, {})
        first, second = self.char1.profile(), self.char2.profile()
        with patch.object(self.char2, "save_profile", side_effect=RuntimeError("save failure")):
            with self.assertRaises(RuntimeError):
                transfer(self.char1, "bandage", recipient=self.char2)
        self.assertEqual((self.char1.profile(), self.char2.profile()), (first, second))
        with patch(
            "typeclasses.loot.create_dropped_loot", side_effect=RuntimeError("create failure")
        ):
            with self.assertRaises(RuntimeError):
                transfer(self.char1, "bandage")
        self.assertEqual(self.char1.profile(), first)
        self.assertEqual(room_loot(self.char1.location, False), [])
        with patch.object(
            self.box.attributes, "add", side_effect=RuntimeError("container save failure")
        ):
            with self.assertRaises(RuntimeError):
                transfer(self.char1, "bandage", container=self.box)
        self.assertEqual(self.char1.profile(), first)
        self.assertEqual(self.box.db.items, {})

    def test_missing_items_and_recipient_combat_preserve_all_owners(self):
        for raw in (
            "회수부품 버려",
            f"{self.char2.key}에게 회수부품 줘",
            "보관상자에 회수부품 넣어",
            "개인 보관함에서 회수부품 꺼내",
        ):
            before = (self.char1.profile(), self.char2.profile(), deserialize(self.box.db.items))
            self.command(raw)
            self.assertEqual(
                (self.char1.profile(), self.char2.profile(), deserialize(self.box.db.items)), before
            )
        self.char2.change(lambda p: p.update(combat_target=123))
        before = (self.char1.profile(), self.char2.profile())
        self.assertIn("전투 중", self.command(f"{self.char2.key}에게 붕대 줘"))
        self.assertEqual((self.char1.profile(), self.char2.profile()), before)

    def test_help_and_state_expose_registered_actions_and_item_metadata(self):
        for action in ("때려", "버려", "줘", "먹어", "마셔", "벗어", "해제", "넣어", "꺼내"):
            output = self.command(action + " 도움말")
            self.assertIn("사용법", output)
            self.assertNotIn("등록된 명령을 찾을 수 없습니다", output)
        self.char1.change(lambda p: rules.add_item(p, "field_ration"))
        with (
            patch.object(self.char1.sessions, "count", return_value=1),
            patch.object(self.char1, "msg") as message,
        ):
            Explorer.push_state(self.char1)
        state = message.call_args.kwargs["pz_state"][0][0]
        inventory = {i["id"]: i for i in state["inventory"]}
        self.assertEqual(inventory["machete"]["remove_action"], "해제")
        self.assertEqual(inventory["vest"]["remove_action"], "벗어")
        self.assertEqual(inventory["field_ration"]["consume_action"], "먹어")
        boxes = [i for i in state["interactables"] if i["name"] in ("보관상자", "개인 보관함")]
        self.assertEqual(len(boxes), 2)
        for box in boxes:
            self.assertEqual(box["actions"], [{"label": "보기", "command": box["name"] + " 보기"}])

    def test_combat_restrictions_preserve_profiles_and_container(self):
        self.char1.change(lambda p: p.update(combat_target=123))
        for raw in (
            "붕대 버려",
            f"{self.char2.key}에게 붕대 줘",
            "보관상자에 붕대 넣어",
            "보관상자에서 붕대 꺼내",
            "낡은마체테 해제",
            "탐사조끼 벗어",
            "야전식량 먹어",
            "정제수 마셔",
        ):
            before = (self.char1.profile(), self.char2.profile(), deserialize(self.box.db.items))
            self.assertIn("전투 중", self.command(raw))
            self.assertEqual(
                (self.char1.profile(), self.char2.profile(), deserialize(self.box.db.items)), before
            )

    def test_relation_parser_reuses_suffix_modes_and_stack_rejects_indices(self):
        for value, particle in (
            ("개인 보관함 2에 붕대 모두", "에"),
            ("개인 보관함 2에서 붕대 모두", "에서"),
            ("탐사자 2에게 붕대 모두", "에게"),
        ):
            selector, item = parse_relation(value, particle)
            self.assertEqual(selector.mode, Mode.INDEX)
            self.assertEqual(selector.index, 2)
            self.assertEqual(stack_selector(item, ITEMS, "넣어"), ("bandage", True))
        self.assertEqual(
            parse_relation("장치 2에 붕대", "에", ["장치 2"])[0], TargetSelector("장치 2")
        )
        with self.assertRaises(rules.RuleError):
            stack_selector("붕대 2", ITEMS, "버려")
        self.assertEqual(parse_selector("붕대 모두").mode, Mode.ALL)

    def test_v4_load_migrates_without_overwriting_equipment_or_progress(self):
        old = self.char1.profile()
        old.update(version=4, hp=37, xp=333)
        old.pop("storage")
        old["equipment"]["weapon"] = None
        old["quests"]["radio_tower"]["claimed"] = True
        self.char1.db.profile = old
        self.char1.attributes.reset_cache()
        migrated = self.char1.profile()
        self.assertEqual(migrated, {**old, "version": rules.PROFILE_VERSION, "storage": {}, "light_sources": {}})
        self.assertEqual(self.char1.profile(), migrated)
        self.assertIn("맨손", view.outgoing_attack(migrated, "어린청소룡", {"action": "attack"}, 7))

    def test_ground_drop_remains_compatible_with_existing_loot_entry_api(self):
        transfer(self.char1, "bandage", all_items=True)
        received = take_loot(self.char2, corpse=False)
        self.assertEqual([(item, qty) for _, item, qty in received], [("bandage", 3)])
        self.assertEqual(self.char2.profile()["inventory"]["bandage"], 6)
