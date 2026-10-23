"""Phase 3의 시설 대용 증거를 실제 Corpse·Item·Door 경계로 보완한다."""

from copy import deepcopy
from unittest.mock import patch

from django.test import TransactionTestCase, override_settings
from evennia import create_object
from evennia.objects.objects import DefaultRoom
from typeclasses.exits import Exit
from typeclasses.loot import Corpse
from world.actions.manifest import compiled, get_index
from world.actions.providers import ActionProviderObject
from world.actions.resolver import dispatch_text, select_role
from world.actions.schema import DefaultTargetPolicy, ReferenceKind, RoleDefinition
from world.content import ITEMS
from world.door_entities.models import Door
from world.item_entities import api
from world.item_entities.models import ItemEntity, ItemSequence
from world.multiplayer import world_change
from world.rules import RuleError
from world.selection_numbers.api import descriptor, label, number_for, records_for, verify
from world.selection_numbers.models import NumberScope, SelectionNumber

from tests.base import WorldCommandTest, clear_test_caches
from tests.item_entity_fixture import NativeItemTest
from tests.loot_entity_fixture import NativeLootTest


class Phase3CorpseTests(NativeLootTest):
    def test_first_corpse_removal_preserves_two_three_then_four_and_reset(self):
        """P3-R03-C01: 2번 삭제와 구별되는 실제 첫 시체 삭제 경계."""
        def corpse():
            return create_object(Corpse, key="회귀 시체", location=self.char1.location)

        second, third = corpse(), corpse()
        refs = [descriptor(obj).reference for obj in (self.source, second, third)]
        self.assertEqual([number_for(ref) for ref in refs], [1, 2, 3])
        self.source.delete()
        self.assertEqual([number_for(ref) for ref in refs], [None, 2, 3])
        fourth = corpse()
        self.assertEqual(number_for(descriptor(fourth).reference), 4)
        role = RoleDefinition("source", (ReferenceKind.CORPSE,))
        with self.assertRaises(RuleError):
            select_role(self.char1, role, "시체 1")
        for obj in (second, third, fourth):
            obj.delete()
        self.assertEqual(number_for(descriptor(corpse()).reference), 1)
        self.assertEqual(verify(), ())

    def test_corpse_delete_create_failure_restores_real_objects_and_counter(self):
        """P3-R05-C02: 실제 시체 삭제·생성의 상위 rollback과 allocator 복구."""
        original = descriptor(self.source).reference
        before = list(SelectionNumber.objects.order_by("pk").values())
        counters = list(NumberScope.objects.order_by("pk").values())
        source_id = self.source.pk
        with self.assertRaises(RuntimeError):
            with world_change():
                self.source.delete()
                create_object(Corpse, key="실패 시체", location=self.char1.location)
                raise RuntimeError("소유 테스트 트랜잭션 실패 주입")
        self.assertTrue(Corpse.objects.filter(pk=source_id).exists())
        self.assertEqual(number_for(original), 1)
        self.assertEqual(list(SelectionNumber.objects.order_by("pk").values()), before)
        self.assertEqual(list(NumberScope.objects.order_by("pk").values()), counters)
        fresh = create_object(Corpse, key="후속 시체", location=self.char1.location)
        self.assertEqual(number_for(descriptor(fresh).reference), 2)
        self.assertEqual(verify(), ())


class Phase3CorpseConcurrencyTests(TransactionTestCase):
    def tearDown(self):
        clear_test_caches()
        super().tearDown()

    def test_actual_corpse_last_delete_and_concurrent_creations_keep_counter(self):
        """P3-R05-C01: 공식 단일 서버/동일 SQLite 연결의 Corpse RLock 경합."""
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        from django.db import connections

        room = create_object(DefaultRoom, key="소유 경합 방")
        with patch("typeclasses.loot.delay"):
            original = create_object(Corpse, key="경합 시체", location=room)
            original_ref = descriptor(original).reference
            shared = connections["default"]
            shared.inc_thread_sharing()
            barrier = Barrier(2)

            def change(remove):
                connections["default"] = shared
                barrier.wait(timeout=10)
                with world_change():
                    if remove:
                        original.delete()
                    obj = create_object(Corpse, key="경합 시체", location=room)
                return descriptor(obj).reference

            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    a, b = pool.submit(change, True), pool.submit(change, False)
                    refs = (a.result(timeout=20), b.result(timeout=20))
            finally:
                shared.dec_thread_sharing()
            self.assertIsNone(number_for(original_ref))
            self.assertEqual(sorted(number_for(ref) for ref in refs), [2, 3])
            record = descriptor(Corpse.objects.get(pk=int(refs[0].identity)))
            scope = NumberScope.objects.get(scope_id=record.scope_id, group_id=record.group_id)
            self.assertEqual(scope.next_number, 4)
            self.assertEqual(Corpse.objects.filter(db_location=room).count(), 2)
            self.assertEqual(verify(), ())


class Phase3ItemDoorTests(NativeItemTest):
    def state(self):
        # 빈 Inventory에서도 ItemSequence singleton이 존재한다고 가정하지 않는다.
        return (self.char1.profile_snapshot(), list(ItemEntity.objects.order_by("pk").values()),
                list(ItemSequence.objects.order_by("pk").values()))

    def test_item_two_alone_keeps_label_hole_and_reset(self):
        """P3-R18-C01/C02/C07/C11: 시설 record 대용 없이 Item 실물 번호·표시."""
        first, second = self.create("bandage", quantity=2), self.create("bandage", quantity=5)
        reference = descriptor(second).reference
        from world.equipment import inventory_rows

        initial = {row["identity"]: row for row in inventory_rows(self.char1.profile())}
        self.assertEqual(initial[str(first.pk)]["selector"], "붕대 1")
        self.assertEqual(initial[str(second.pk)]["selector"], "붕대 2")
        api.delete_item(first)
        record = next(record for record in records_for(self.char1, ReferenceKind.ITEM)
                      if record.reference == reference)
        self.assertEqual(label(record, 1), "붕대 2")
        # 실제 텍스트/Web 소지품 Presenter가 같은 UUID의 영속 번호와 수량을 결합한다.
        row = next(row for row in inventory_rows(self.char1.profile()) if row["identity"] == str(second.pk))
        self.assertEqual((row["selector"], row["count"], row["information_command"]),
                         ("붕대 2", 5, "붕대 2 정보"))
        self.assertEqual(second.quantity, 5)
        role = RoleDefinition("subject", (ReferenceKind.ITEM,), DefaultTargetPolicy.FIRST_LEGACY_ORDER)
        with self.assertRaises(RuleError):
            select_role(self.char1, role, "붕대 1")
        self.assertEqual(select_role(self.char1, role, "붕대 2"), (reference,))
        third = self.create("bandage")
        self.assertEqual(number_for(descriptor(third).reference), 3)
        api.delete_item(second)
        api.delete_item(third)
        fresh = self.create("bandage")
        self.assertEqual(number_for(descriptor(fresh).reference), 1)
        only = next(row for row in inventory_rows(self.char1.profile()) if row["identity"] == str(fresh.pk))
        # 단독 1의 생략은 허용 사항이지 의무가 아니다. 현재 구현은 숨은
        # 그룹원의 존재를 표시 차이로 노출하지 않도록 1도 명시한다.
        self.assertEqual(only["selector"], "붕대 1")
        fresh_record = next(record for record in records_for(self.char1, ReferenceKind.ITEM)
                            if record.reference == descriptor(fresh).reference)
        self.assertEqual(label(fresh_record, 1), "붕대 1")
        self.assertEqual(verify(), ())

    def test_item_definition_name_alias_change_preserves_uuid_group_and_counter(self):
        """P3-R26-C01: Item 표시 metadata만 바꿔도 번호 SSOT를 재발급하지 않는다."""
        item = self.create("bandage", quantity=4)
        identity = item.pk
        before = descriptor(item)
        counters = list(NumberScope.objects.order_by("pk").values())
        definition = deepcopy(ITEMS["bandage"])
        definition.update(name="개명 붕대", aliases=["새별칭"])
        with patch.dict(ITEMS, {"bandage": definition}):
            current = descriptor(item)
            self.assertEqual(current.reference, before.reference)
            self.assertEqual(current.group_id, before.group_id)
            self.assertEqual(current.name, "개명 붕대")
            self.assertIn("새별칭", current.aliases)
            role = RoleDefinition("subject", (ReferenceKind.ITEM,))
            self.assertEqual(select_role(self.char1, role, "새별칭"), (before.reference,))
            self.assertEqual(number_for(current.reference), 1)
            self.assertEqual(list(NumberScope.objects.order_by("pk").values()), counters)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 4)
        self.assertEqual(item.pk, identity)

    def test_two_door_numbers_aliases_resolve_exact_endpoint_not_other_side(self):
        """P3-R13-C01: 두 문 번호·별칭·실제 Endpoint ID를 같은 방에서 결합."""
        refs = []
        for i in range(2):
            outward = create_object(Exit, key=f"통로{i}", location=self.char1.location, destination=self.room2)
            inward = create_object(Exit, key=f"반대{i}", location=self.room2, destination=self.char1.location)
            Door.objects.create(door_id=f"p3_door_{i}", name=f"회귀 문{i}", aliases=[f"별칭문{i}"],
                                room_a=f"p3a{i}", room_b=f"p3b{i}", exit_a=outward, exit_b=inward,
                                direction_a=outward.key, direction_b=inward.key, state="CLOSED")
            refs.append(descriptor(outward).reference)
        role = RoleDefinition("subject", (ReferenceKind.DOOR,))
        for i, ref in enumerate(refs):
            self.assertEqual(number_for(ref), i + 1)
            self.assertEqual(select_role(self.char1, role, f"문 {i + 1}"), (ref,))
            self.assertEqual(select_role(self.char1, role, f"별칭문{i}"), (ref,))
        self.assertNotEqual(refs[0].identity, refs[1].identity)

    def test_missing_shop_public_bandage_buy_refuses_without_inventory_or_credit_change(self):
        """P3-R11-C01: 제공자가 없는 방의 실제 후치형 입력은 효과를 만들지 않는다."""
        self.connect_character(self.char1)
        before = self.state()
        with patch.object(self.char1, "msg") as output:
            done = []
            self.char1.execute_cmd("붕대 사", session=self.session).addCallback(lambda _: done.append(True))
            self.assertEqual(done, [True])
        self.assertEqual(self.state(), before)
        messages = "\n".join(str(call.args[0]) for call in output.call_args_list if call.args)
        self.assertIn("상점 상인을 찾지 못했습니다", messages)
        index = get_index()
        with self.assertRaises(RuleError):
            dispatch_text(self.char1, index, index.verbs_by_public_keys["사"], "붕대", "사")
        self.assertEqual(ItemEntity.objects.filter(owner_object=self.char1, definition_id="bandage").count(), 0)

    def test_real_enemy_death_reconcile_respawn_keeps_number_and_look_has_no_reward_effect(self):
        """P3-R23: 상태를 대입하는 대용 대신 실제 사망·관찰·reconcile 경로."""
        from random import Random

        from typeclasses.enemies import Enemy
        from world.content import ENEMIES
        from world.lifecycle import reconcile_room

        identity = next(key for key, value in ENEMIES.items() if not value.get("boss"))
        self.connect_character(self.char1)
        with patch("typeclasses.enemies.delay"), patch("typeclasses.loot.delay"), \
                patch("world.lifecycle.time", return_value=100):
            enemy = create_object(Enemy, key="회귀 적", location=self.char1.location,
                                  attributes=[("enemy_id", identity)])
            ref = descriptor(enemy).reference
            self.assertEqual(number_for(ref), 1)
            enemy.db.hp = 0
            enemy.finish_death(self.char1, now=100, rng=Random(1))
            self.assertEqual(enemy.db.state, "respawning")
            self.assertEqual(number_for(ref), 1)
            corpses = list(Corpse.objects.filter(db_location=self.char1.location))
            self.assertEqual(len(corpses), 1)
            corpse_ref = descriptor(corpses[0]).reference
            state = self.state()
            numbers = list(SelectionNumber.objects.order_by("pk").values())
            for _ in range(2):
                done = []
                self.char1.execute_cmd("봐", session=self.session).addCallback(lambda _: done.append(True))
                self.assertEqual(done, [True])
            self.assertEqual(self.state(), state)
            self.assertEqual(list(SelectionNumber.objects.order_by("pk").values()), numbers)
            deadline = enemy.db.respawn_at
            reconcile_room(self.char1.location, now=deadline)
            self.assertEqual(enemy.db.state, "alive")
            self.assertEqual(enemy.db.hp, ENEMIES[identity]["hp"])
            self.assertEqual(number_for(ref), 1)
            self.assertIsNone(number_for(corpse_ref))
            self.assertEqual(verify(), ())


class Phase3EnemySelectionTests(NativeItemTest):
    def setUp(self):
        super().setUp()
        from typeclasses.enemies import Enemy
        from world.content import ENEMIES

        for module in ("commands.character", "world.lifecycle", "typeclasses.enemies", "world.observation"):
            self.enterContext(patch(module + ".time", return_value=100))
        for module in ("typeclasses.enemies", "typeclasses.loot"):
            self.enterContext(patch(module + ".delay"))
        self.connect_character(self.char1)
        identity = next(key for key, value in ENEMIES.items() if not value.get("boss"))
        self.enemies = [create_object(Enemy, key="회귀 사냥감", location=self.char1.location,
                                     attributes=[("enemy_id", identity)]) for _ in range(2)]
        for enemy in self.enemies:
            enemy.db.hp = enemy.db.max_hp = ENEMIES[identity]["hp"]
        self.refs = [descriptor(enemy).reference for enemy in self.enemies]
        self.assertEqual([number_for(ref) for ref in self.refs], [1, 2])

    def command(self, value):
        with patch.object(self.char1, "msg") as output:
            done = []
            self.char1.execute_cmd(value, session=self.session).addCallback(lambda _: done.append(True))
            self.assertEqual(done, [True])
        return "\n".join(str(call.args[0]) for call in output.call_args_list if call.args)

    def test_public_attack_dead_number_does_not_fallback_to_live_two(self):
        from random import Random

        first, second = self.enemies
        first.db.hp = 0
        first.finish_death(self.char1, now=100, rng=Random(1))
        self.assertEqual(first.db.state, "respawning")
        before = self.char1.profile_snapshot()
        numbers = list(SelectionNumber.objects.order_by("pk").values())
        with patch.object(self.char1, "start_combat", wraps=self.char1.start_combat) as start:
            self.command("회귀 사냥감 1 공격")
            start.assert_not_called()
            self.assertEqual(self.char1.profile_snapshot(), before)
            self.command("회귀 사냥감 2 공격")
            start.assert_called_once_with(second)
        self.assertEqual(self.char1.profile_snapshot()["combat_target"], second.pk)
        self.assertEqual([number_for(ref) for ref in self.refs], [1, 2])
        self.assertEqual(list(SelectionNumber.objects.order_by("pk").values()), numbers)

    def test_two_alone_labels_and_public_web_look_keep_same_enemy_id(self):
        from world.state import multiplayer_state
        from world.targets import labels, room_objects

        first, second = self.enemies
        first.db.state = "respawning"
        first.db.respawn_at = 1000
        self.assertEqual(labels(room_objects(self.char1))[second.pk], "회귀 사냥감 2")
        rows = multiplayer_state(self.char1, now=100)["enemies"]
        self.assertEqual([(row["id"], row["label"], row["attack_command"], row["look_command"]) for row in rows],
                         [(second.pk, "회귀 사냥감 2", "회귀 사냥감 2 공격", "회귀 사냥감 2 봐")])
        self.assertNotIn("체력", self.command("회귀 사냥감 1 봐"))
        self.assertIn("체력", self.command(rows[0]["look_command"]))

    def test_player_visibility_keeps_canonical_number_without_hidden_fallback(self):
        from world.state import multiplayer_state
        from world.targets import labels, room_objects

        first, second = self.enemies
        # A는 1/2를 보고 B는 2만 본다. 번호·Counter 저장값은 양쪽 공통이다.
        first.locks.add(f"view:id({self.char1.pk})")
        before = list(SelectionNumber.objects.order_by("pk").values())
        counters = list(NumberScope.objects.order_by("pk").values())
        self.assertEqual(labels(room_objects(self.char1))[second.pk], "회귀 사냥감 2")
        self.assertEqual(labels(room_objects(self.char2))[second.pk], "회귀 사냥감 2")
        rows_a = multiplayer_state(self.char1, now=100)["enemies"]
        rows_b = multiplayer_state(self.char2, now=100)["enemies"]
        self.assertEqual([row["id"] for row in rows_a], [first.pk, second.pk])
        self.assertEqual([(row["id"], row["label"]) for row in rows_b], [(second.pk, "회귀 사냥감 2")])
        from world.targets import parse_selector, resolve

        with self.assertRaises(RuleError):
            resolve(room_objects(self.char2), parse_selector("회귀 사냥감 1"), self.char2)
        self.assertEqual(resolve(room_objects(self.char2), parse_selector("회귀 사냥감 2"), self.char2), [second])
        self.assertEqual(list(SelectionNumber.objects.order_by("pk").values()), before)
        self.assertEqual(list(NumberScope.objects.order_by("pk").values()), counters)

    def test_default_enemy_legacy_first_and_numeric_real_name_are_preserved(self):
        first, second = self.enemies
        with patch.object(self.char1, "start_combat") as start:
            self.command("회귀 사냥감 공격")
            start.assert_called_once_with(first)
            start.reset_mock()
            second.key = "회귀 사냥감 1"
            self.command("회귀 사냥감 1 공격")
            start.assert_called_once_with(second)

    def test_fresh_bootstrap_enemy_is_numbered_before_observation_and_rebuild_keeps_id(self):
        from typeclasses.enemies import room_enemies
        from world.bootstrap import build_world

        rooms = build_world()
        enemy = room_enemies(rooms["grass"])[0]
        reference = descriptor(enemy).reference
        self.assertEqual(number_for(reference), 1)
        before = list(SelectionNumber.objects.order_by("pk").values())
        self.assertEqual(build_world()["grass"].pk, rooms["grass"].pk)
        self.assertEqual(room_enemies(rooms["grass"])[0].pk, enemy.pk)
        self.assertEqual(number_for(reference), 1)
        self.assertEqual(list(SelectionNumber.objects.order_by("pk").values()), before)

    def test_shared_alias_and_number_across_enemy_groups_refuses_public_attack(self):
        from typeclasses.enemies import Enemy

        first, second = self.enemies
        second.delete()
        other = create_object(Enemy, key="다른 사냥감", location=first.location,
                              attributes=[("enemy_id", first.db.enemy_id),
                                          ("selection_group_id", "p3:other-enemies")])
        other.db.hp = other.db.max_hp = first.db.max_hp
        first.aliases.add("공유 사냥감")
        other.aliases.add("공유 사냥감")
        self.assertEqual([number_for(descriptor(obj).reference) for obj in (first, other)], [1, 1])
        with patch.object(self.char1, "start_combat") as start:
            self.command("공유 사냥감 1 공격")
            start.assert_not_called()

    def test_enemy_and_facility_shared_alias_does_not_fallback_to_enemy(self):
        from typeclasses.interactables import SupplyCache

        first = self.enemies[0]
        facility = create_object(SupplyCache, key="경합 보급함", location=first.location)
        first.aliases.add("공유 표적")
        facility.aliases.add("공유 표적")
        self.assertEqual([number_for(descriptor(obj).reference) for obj in (first, facility)], [1, 1])
        with patch.object(self.char1, "start_combat") as start:
            self.command("공유 표적 1 공격")
            start.assert_not_called()

    def test_party_attack_dead_number_refuses_and_default_ambiguity_is_preserved(self):
        from typeclasses.parties import create_party

        self.enterContext(patch("typeclasses.parties.time", return_value=100))
        create_party(self.char1, now=100)
        first, second = self.enemies
        with patch("typeclasses.parties.Party.attack") as attack:
            self.command("회귀 사냥감 일행공격")
            attack.assert_not_called()
            first.db.state = "respawning"
            first.db.respawn_at = 1000
            self.command("회귀 사냥감 1 일행공격")
            attack.assert_not_called()
            self.command("회귀 사냥감 2 일행공격")
            attack.assert_called_once_with(self.char1, second)

    def test_public_say_deleted_npc_number_is_not_replaced_by_remaining_two(self):
        from typeclasses.interactables import Commander

        npcs = [create_object(Commander, key="윤대장", location=self.char1.location) for _ in range(2)]
        self.assertEqual([number_for(descriptor(npc).reference) for npc in npcs], [1, 2])
        npcs[0].delete()
        with patch("world.npc_dialogue.execute") as execute:
            self.command("윤대장 1에게 임무 말")
            execute.assert_not_called()
            self.command("윤대장 2에게 임무 말")
            self.assertEqual(execute.call_count, 1)
            self.assertEqual(execute.call_args.args[1], npcs[1])

    def test_numeric_real_enemy_name_wins_earlier_alias(self):
        first, second = self.enemies
        first.aliases.add("사냥감 1")
        second.key = "사냥감 1"
        with patch.object(self.char1, "start_combat") as start:
            self.command("사냥감 1 공격")
            start.assert_called_once_with(second)
        from typeclasses.parties import create_party

        create_party(self.char1, now=100)
        with patch("typeclasses.parties.Party.attack") as attack:
            self.command("사냥감 1 일행공격")
            attack.assert_called_once_with(self.char1, second)

    def test_duplicate_numeric_real_enemy_name_refuses_instead_of_default_first(self):
        for enemy in self.enemies:
            enemy.key = "사냥감 1"
        with patch.object(self.char1, "start_combat") as start:
            self.command("사냥감 1 공격")
            start.assert_not_called()

    def test_public_say_numeric_real_npc_name_is_not_broadcast_as_unknown_target(self):
        from typeclasses.interactables import Commander

        npc = create_object(Commander, key="관측 책임자 1", location=self.char1.location)
        with patch("world.npc_dialogue.execute") as execute:
            self.command("관측 책임자 1에게 임무 말")
            self.assertEqual(execute.call_count, 1)
            self.assertEqual(execute.call_args.args[1], npc)

    def test_unsupported_numeric_real_name_does_not_select_enemy_alias(self):
        from typeclasses.interactables import SupplyCache

        self.enemies[0].aliases.add("관측 장치 1")
        create_object(SupplyCache, key="관측 장치 1", location=self.char1.location)
        with patch.object(self.char1, "start_combat") as start:
            self.command("관측 장치 1 공격")
            start.assert_not_called()

    def test_provider_discovery_does_not_observe_unrelated_enemies(self):
        from typeclasses.interactables import SupplyCache
        from world.actions.resolver import provided, role_records

        # Enemy에는 번호가 있지만 운영 Action Provider Binding은 없다.
        index = get_index()
        with patch("world.observation.context_for", side_effect=AssertionError("불필요한 Enemy 관찰")), \
                patch("world.actions.resolver.role_records", wraps=role_records) as discovered:
            self.assertEqual(provided(self.char1, index), ())
        kinds = set(discovered.call_args.args[1].kinds)
        self.assertNotIn(ReferenceKind.ENEMY, kinds)
        # 현재 공용 Binding 전체가 선언한 Provider kind를 빠짐없이 관찰한다.
        # Inventory/화폐 등이 Subject인 경우는 Provider로 오인하지 않는다.
        for binding in index.bindings.values():
            action = index.actions[binding.action_id]
            if action.public:
                for role in action.roles:
                    if role.name == "provider":
                        self.assertLessEqual(set(role.kinds), kinds)
        source = create_object(SupplyCache, key="관찰 경계 상자", location=self.char1.location)
        reference = descriptor(source).reference
        source.locks.add("view:false()")
        self.assertNotIn(reference, {ref for ref, _ in provided(self.char1, get_index())})
        source.locks.add("view:all()")
        self.assertIn(reference, {ref for ref, _ in provided(self.char1, get_index())})

    def test_role_kind_filter_keeps_shared_cache_and_number_state_separate(self):
        from world.actions.resolver import role_records

        before = list(SelectionNumber.objects.order_by("pk").values())
        counters = list(NumberScope.objects.order_by("pk").values())
        cache = {}
        role_records(self.char1, RoleDefinition("provider", (ReferenceKind.OBJECT,)), cache=cache)
        enemy_role = RoleDefinition("subject", (ReferenceKind.ENEMY,))
        self.assertEqual({record.reference for record in role_records(self.char1, enemy_role, cache=cache)}, set(self.refs))
        self.assertEqual(records_for(self.char1, ReferenceKind.ENEMY),
                         records_for(self.char1, kinds=(ReferenceKind.ENEMY,)))
        self.assertEqual(list(SelectionNumber.objects.order_by("pk").values()), before)
        self.assertEqual(list(NumberScope.objects.order_by("pk").values()), counters)


@override_settings(ACTION_CONTENT_PACKAGES=("world.actions.validation_content",))
class Phase3NumericNameTests(NativeItemTest):
    def setUp(self):
        super().setUp()
        compiled.cache_clear()
        self.addCleanup(compiled.cache_clear)
        self.connect_character(self.char1)

    def test_duplicate_numeric_real_name_refuses_then_visible_alias_selects_exact_object(self):
        """P3-R36-C01/C02: 숫자 실명 안내와 가시성 변경 뒤 비공개 대안 비노출."""
        objects = []
        for alias in ("첫기기", "둘기기"):
            obj = create_object(ActionProviderObject, key="검증기 1", location=self.char1.location,
                                attributes=[("action_provider_id", "validation.instrument"),
                                            ("selection_group_id", "validation.instruments")])
            obj.locks.add("call:true();view:true();delete:true()")
            obj.aliases.add(alias)
            objects.append(obj)
        role = RoleDefinition("provider", (ReferenceKind.OBJECT,))
        numbers = list(SelectionNumber.objects.order_by("pk").values())
        counters = list(NumberScope.objects.order_by("pk").values())
        profile = self.char1.profile_snapshot()
        items = list(ItemEntity.objects.order_by("pk").values())
        with self.assertRaises(RuleError) as ambiguous:
            select_role(self.char1, role, "검증기 1")
        self.assertIn("다른 고유 이름을 지정하세요", str(ambiguous.exception))
        self.assertNotIn("첫기기", str(ambiguous.exception))
        self.assertNotIn("둘기기", str(ambiguous.exception))
        self.assertEqual(select_role(self.char1, role, "둘기기"), (descriptor(objects[1]).reference,))
        hidden = descriptor(objects[1]).reference
        objects[1].locks.add("view:false()")
        with self.assertRaises(RuleError) as unavailable:
            select_role(self.char1, role, "둘기기")
        for sensitive in ("둘기기", "검증기 1", hidden.identity, hidden.scope_id):
            self.assertNotIn(sensitive, str(unavailable.exception))
        # 실제 공개 Command도 숨긴 대상의 이름·번호·참조를 대안으로 제안하면 안 된다.
        with patch.object(self.char1, "msg") as output:
            completed = []
            self.char1.execute_cmd("둘기기 검측", session=self.session).addCallback(lambda _: completed.append(True))
            self.assertEqual(completed, [True])
        messages = "\n".join(str(call.args[0]) for call in output.call_args_list
                             if call.args and getattr(call.args[0], "kind", None) != "prompt")
        self.assertTrue(messages)
        for sensitive in ("둘기기", "검증기 1", "identity", hidden.scope_id, "#" + hidden.identity):
            self.assertNotIn(sensitive, messages)
        self.assertFalse(self.char1.db.action_validation_events)
        self.assertEqual(select_role(self.char1, role, "첫기기"), (descriptor(objects[0]).reference,))
        self.assertEqual(list(SelectionNumber.objects.order_by("pk").values()), numbers)
        self.assertEqual(list(NumberScope.objects.order_by("pk").values()), counters)
        self.assertEqual(self.char1.profile_snapshot(), profile)
        self.assertEqual(list(ItemEntity.objects.order_by("pk").values()), items)


class Phase3VisibilityTests(NativeItemTest, WorldCommandTest):
    def test_darkness_then_real_native_light_discovery_hides_counts_without_renumbering(self):
        """P3-R15-C02: 실제 밤/폭풍→광원 발견 전후 Room·봐·Web·진단 공통 경계."""
        from random import Random

        from evennia import create_script
        from typeclasses.enemies import Enemy, room_enemies
        from typeclasses.scripts import WorldLifecycle
        from world import environment, lighting_service
        from world.content import ENEMIES
        from world.environment_state import snapshot_for
        from world.state import multiplayer_state

        for module in ("commands.character", "typeclasses.zone_rooms", "world.lifecycle",
                       "typeclasses.enemies", "typeclasses.loot", "world.observation"):
            self.enterContext(patch(module + ".time", return_value=100))
        for module in ("typeclasses.enemies", "typeclasses.loot"):
            self.enterContext(patch(module + ".delay"))
        self.connect_character(self.char1)
        self.char1.location = self.world_rooms()["grass"]
        original = room_enemies(self.char1.location)[0]
        identity, name = original.db.enemy_id, original.key
        # 역사적 build_world fixture는 생성 뒤 enemy_id를 설정한다. 이 테스트의
        # 두 실물은 처음부터 identity를 선언해 native 번호 발급 경계를 거친다.
        for obj in list(room_enemies(self.char1.location)):
            obj.delete()
        script = create_script(WorldLifecycle, autostart=False)
        state = environment.new_environment(100, Random(3))
        state["clock"]["game_epoch"] = 22 * 3600
        state["zones"]["island"].update(weather="storm", next_change_at=100000)
        script.db.environment = state
        self.assertEqual(snapshot_for(self.char1.location, 100).visibility, "poor")

        flashlight = self.create("flashlight")
        battery = self.create("battery")
        lighting_service.insert_power(self.char1, flashlight, battery, 40)
        def command(value):
            with patch.object(self.char1, "msg") as output:
                done = []
                self.char1.execute_cmd(value, session=self.session).addCallback(lambda _: done.append(True))
                self.assertEqual(done, [True])
            return "\n".join(str(call.args[0]) for call in output.call_args_list
                             if call.args and getattr(call.args[0], "kind", None) != "prompt")

        # 오류는 사용자 입력을 반향할 수 있으므로 서로 다른 이름의 문구를
        # 비교하지 않는다. 정확히 같은 입력의 실물 부재/어둠 속 존재를 비교한다.
        absent_diagnostics = {number: command(f"{name} {number} 봐") for number in (1, 2)}
        objects = [create_object(Enemy, key=name, location=self.char1.location,
                                 attributes=[("enemy_id", identity)]) for _ in range(2)]
        for obj in objects:
            obj.db.hp = obj.db.max_hp = ENEMIES[identity]["hp"]
        enemy, other = objects
        refs = [descriptor(obj).reference for obj in objects]
        numbers = [number_for(ref) for ref in refs]
        self.assertEqual(numbers, [1, 2])
        saved_numbers = list(SelectionNumber.objects.filter(kind="enemy").order_by("pk").values())
        saved_counters = list(NumberScope.objects.filter(group_id__startswith="enemy:").order_by("pk").values())
        hidden_room = str(self.char1.location.return_appearance(self.char1, observed_at=100))
        hidden_look = command("봐")
        hidden_web = multiplayer_state(self.char1, now=100)
        self.assertEqual(hidden_web["enemies"], [])
        self.assertEqual(records_for(self.char1, ReferenceKind.ENEMY), ())
        for output in (hidden_room, hidden_look, str(hidden_web)):
            self.assertNotIn(enemy.key, output)
            self.assertNotIn(f"{enemy.key} 2", output)
        for number in numbers:
            diagnostic = command(f"{enemy.key} {number} 봐")
            self.assertEqual(diagnostic, absent_diagnostics[number])
            self.assertNotIn("체력", diagnostic)
            self.assertNotIn(refs[number - 1].scope_id, diagnostic)

        # view lock을 조작하지 않고 native 광원의 실제 전원/점등 서비스로 발견한다.
        lighting_service.switch(self.char1, flashlight, True, 40)
        visible_room = str(self.char1.location.return_appearance(self.char1, observed_at=100))
        visible_look = command("봐")
        visible_web = multiplayer_state(self.char1, now=100)
        self.assertIn(enemy.key, visible_room)
        self.assertIn(enemy.key, visible_look)
        shown = {str(row["id"]): row for row in visible_web["enemies"]}
        for obj, ref, number in zip((enemy, other), refs, numbers):
            self.assertEqual(shown[str(obj.pk)]["label"], f"{enemy.key} {number}")
            self.assertIn(enemy.key, command(f"{enemy.key} {number} 봐"))
            self.assertEqual(number_for(ref), number)
        self.assertEqual(list(SelectionNumber.objects.filter(kind="enemy").order_by("pk").values()), saved_numbers)
        self.assertEqual(list(NumberScope.objects.filter(group_id__startswith="enemy:").order_by("pk").values()), saved_counters)
