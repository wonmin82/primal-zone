"""최종 native runtime의 보상·거래·광원·총기·전리품 경계."""

from copy import deepcopy
from random import Random
from time import time
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.test import override_settings
from evennia import search_tag
from evennia.utils.dbserialize import deserialize
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from typeclasses.loot import Corpse
from world import (
    credential_service,
    equipment_service,
    firearm_service,
    item_migration,
    lighting_service,
    rules,
    shop_service,
)
from world.content import ENEMIES, ITEMS
from world.content.item_mapping import BOSS_REWARDS
from world.incinerator_service import incinerate
from world.item_entities import api
from world.item_entities.models import ItemEntity, ItemSequence
from world.loot_entities.models import CurrencyLoot
from world.loot_service import loot_snapshot, pickup

from tests.base import WorldCommandTest


class Phase6RuntimeTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        self.enterContext(patch("typeclasses.explorers.time", return_value=time()))
        for module in ("explorers", "enemies", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))
        for player in (self.char1, self.char2):
            player.push_state = Mock()
            player.schedule_recovery = Mock()
            self.enterContext(patch.object(player.sessions, "count", return_value=1))
        self.assertEqual(item_migration.apply()["errors"], [])
        self.assertEqual(item_migration.verify()["errors"], [])
        item_migration.cutover()
        self.enterContext(override_settings(ITEM_MIGRATION_AUDIT=False))
        self.char1.location = self.rooms["weapon_shop"]
        self.char1.change(lambda p: p.update(credits=2000))
        self.archived = deepcopy(deserialize(self.char1.db.profile))

    def state(self):
        return (deserialize(self.char1.db.profile), list(ItemEntity.objects.order_by("sequence").values()),
                ItemSequence.objects.get(pk=1).last_value, self.char1.db.active_weapon_item_id, self.char1.db.active_light_item_id)

    def obj(self, identity):
        return search_tag(identity, category="primal_interactable")[0]

    def assert_archived_items(self):
        saved = deserialize(self.char1.db.profile)
        for field in ("inventory", "equipment", "storage", "light_sources"):
            self.assertEqual(saved[field], self.archived[field])

    def test_final_shields_and_offhands_use_native_hands_with_wear_command(self):
        active = self.char1.db.active_weapon_item_id
        for identity in ("folding_shield", "portable_analyzer", "composite_shield",
                         "tactical_analyzer", "emergency_injector"):
            with self.subTest(item=identity):
                row = api.create_item(identity, location_kind="inventory", owner_object=self.char1)
                self.char1.execute_cmd(f"{ITEMS[identity]['name']} 착용")
                row.refresh_from_db()
                self.assertEqual((row.location_kind, row.slot), ("equipment", "hands"))
                self.assertEqual(equipment_service.hand_usage(self.char1), 2)
                self.assertEqual(self.char1.db.active_weapon_item_id, active)
                self.char1.execute_cmd(f"{ITEMS[identity]['name']} 벗어")
                row.refresh_from_db()
                self.assertEqual((row.location_kind, row.slot), ("inventory", None))
                self.assert_archived_items()

    def test_native_ammo_bundle_firearm_package_sale_and_burn(self):
        shop = self.obj("weapon_shopkeeper")
        shop_service.buy(self.char1, shop, "ammo_556")
        self.assertEqual(self.char1.profile()["inventory"]["ammo_556"], 20)
        self.assertEqual(self.char1.profile()["credits"], 1940)
        shop_service.buy(self.char1, shop, "guard_carbine")
        firearm = api.items_owned_by(self.char1).get(definition_id="guard_carbine")
        magazine = firearm.children.get()
        self.assertEqual((magazine.definition_id, magazine.state), ("mag_556_standard", {"rounds": 20}))
        before = self.state()
        with self.assertRaises(rules.RuleError):
            shop_service.sell(self.char1, shop, "경비카빈")
        self.assertEqual(self.state(), before)
        firearm_service.unload_magazine(self.char1, firearm)
        sale = shop_service.sell(self.char1, shop, "카빈표준")
        self.assertEqual(sale.proceeds, 42)
        self.assertEqual(sale.rounds, 20)
        shop_service.sell(self.char1, shop, "경비카빈")
        self.assertFalse(api.items_owned_by(shop).exists())
        self.char1.location = self.rooms["salvage_office"]
        ammo = api.items_owned_by(self.char1).get(definition_id="ammo_556")
        identity = (ammo.pk, ammo.sequence)
        incinerate(self.char1, "5.56mm 카빈탄 3개")
        ammo.refresh_from_db()
        self.assertEqual((ammo.pk, ammo.sequence, ammo.quantity), (*identity, 17))
        self.assert_archived_items()

    def test_native_lighting_and_combat_consume_only_entity_state(self):
        light = api.create_item("flashlight", owner_object=self.char1, location_kind="inventory")
        battery = api.create_item("battery", owner_object=self.char1, location_kind="inventory")
        now = time()
        lighting_service.insert_power(self.char1, light, battery, now=now)
        lighting_service.switch(self.char1, light, True, now=now)
        self.assertIsNotNone(lighting_service.lighting_snapshot(self.char1, now=now + 120).active)
        firearm = firearm_service.create_firearm("scout_pistol", owner_object=self.char1, mode="full_standard")
        starter = api.items_in_location("equipment", owner_object=self.char1).get(slot="hands")
        equipment_service.unequip_item(self.char1, starter)
        equipment_service.equip_item(self.char1, firearm)
        profile = self.char1.profile()
        profile.update(combat_target=1, next_attack_at=0)
        _, outcome = firearm_service.player_attack(self.char1, profile, "scavenger", now, 2.5, Random(1))
        self.assertTrue(outcome["shot_fired"])
        self.assertEqual(firearm.children.get().state["rounds"], 11)
        self.char1.save_profile(profile)
        self.assert_archived_items()

    def test_enemy_partial_firearm_generation_and_native_pickup(self):
        self.char1.location = self.rooms["generator"]
        enemy = room_enemies(self.rooms["generator"])[0]
        # resource 불발, special 경비카빈 branch, 잔탄 경계의 deterministic RNG.
        rng = Mock(random=Mock(side_effect=[.99, .10]), randint=Mock(return_value=4))
        corpse = Corpse.from_enemy(enemy, {f"player:{self.char1.pk}": {self.char1.pk: 1}}, time(), rng)
        self.assertEqual(deserialize(corpse.db.entries), [])
        self.assertEqual(corpse.db.loot_backend, "item_entities")
        gun = api.items_owned_by(corpse).get(definition_id="guard_carbine")
        self.assertEqual((gun.children.get().definition_id, gun.children.get().state["rounds"]), ("mag_556_short", 4))
        entry = next(entry for entry in loot_snapshot(corpse).entries if entry.kind == "item")
        pickup(corpse, entry, self.char1, 1, now=time())
        gun.refresh_from_db()
        self.assertEqual((gun.location_kind, gun.owner_object_id), ("inventory", self.char1.pk))
        self.assertEqual(gun.children.get().state["rounds"], 4)
        self.assertTrue(CurrencyLoot.objects.filter(owner_object=corpse).exists())
        self.assert_archived_items()

    def test_unique_rewards_atomic_repeat_safe_and_policy(self):
        for quest, identity in BOSS_REWARDS.items():
            credential = "outpost_supply_pass" if quest == "radio_tower" else "special_supply_pass"
            operation = rules.commander_talk if quest == "radio_tower" else rules.jungle_talk
            self.char1.change(lambda p: p["quests"][quest].update(started=True, boss_defeated=True, **({"generator_fixed": True} if quest == "radio_tower" else {})))
            before = self.state()
            original = api.create_item
            def fail(definition, **kwargs):
                if definition == identity:
                    raise RuntimeError("unique create")
                return original(definition, **kwargs)
            with patch.object(api, "create_item", side_effect=fail), self.assertRaises(RuntimeError):
                credential_service.issuer_talk(self.char1, credential, operation)
            self.assertEqual(self.state(), before)
            with patch.object(self.char1, "save_profile", side_effect=RuntimeError("save")), self.assertRaises(RuntimeError):
                credential_service.issuer_talk(self.char1, credential, operation)
            self.assertEqual(self.state(), before)
            self.assertEqual(credential_service.issuer_talk(self.char1, credential, operation), ("complete", True, True))
            row = api.items_owned_by(self.char1).get(definition_id=identity)
            after = self.state()
            credential_service.issuer_talk(self.char1, credential, operation)
            self.assertEqual(self.state(), after)
            for action in ("drop", "give", "sell", "burn", "consume", "loot", "unknown"):
                with self.subTest(action=action), self.assertRaises(ValidationError):
                    api.delete_item(row, operation=action)
            api.move_item_tree(row, location_kind="equipment", slot=ITEMS[identity]["equipment_properties"]["slot"], owner_object=self.char1, operation="equip")
            api.move_item_tree(row, location_kind="personal_storage", owner_object=self.char1, operation="store")
        self.assert_archived_items()

    def test_both_fixed_discoveries_are_one_time_and_keep_existing_rewards(self):
        self.char1.change(rules.claim_cache)
        self.char1.change(rules.claim_jungle_cache)
        self.assertEqual(self.char1.profile()["inventory"]["expedition_tag"], 1)
        self.assertEqual(self.char1.profile()["inventory"]["generator_repair_part"], 3)
        self.assertEqual(self.char1.profile()["inventory"]["mental_stability_module"], 1)
        self.assertGreater(self.char1.profile()["inventory"]["bandage"], 3)
        before = self.state()
        for operation in (rules.claim_cache, rules.claim_jungle_cache):
            with self.assertRaises(rules.RuleError):
                self.char1.change(operation)
            self.assertEqual(self.state(), before)

    def test_native_quest_submission_consumes_resources_without_legacy_write(self):
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(started=True, record_read=True))
        self.char1.change(rules.claim_cache)
        self.assertEqual(self.char1.profile()["inventory"]["generator_repair_part"], 3)
        self.char1.change(rules.fix_generator)
        self.assertFalse(api.items_owned_by(self.char1).filter(definition_id="generator_repair_part").exists())
        self.char1.change(lambda p: p["quests"]["deep_jungle"].update(started=True, watch_marked=True, road_marked=True))
        api.create_item("jungle_cell", owner_object=self.char1, location_kind="inventory")
        self.char1.change(rules.open_jungle_gate)
        self.assertFalse(api.items_owned_by(self.char1).filter(definition_id="jungle_cell").exists())
        self.assert_archived_items()

    def test_native_missing_profile_does_not_fall_back_or_write(self):
        self.char1.db.profile = None
        for query in (self.char1.profile, self.char1.profile_snapshot):
            with self.assertRaises(rules.RuleError):
                query()
            self.assertIsNone(self.char1.db.profile)

    def test_boss_late_eligible_join_preserves_damage_and_no_downscale(self):
        boss = room_enemies(self.rooms["ridge"])[0]
        for player in (self.char1, self.char2):
            player.location = boss.location
            boss.engage(player, now=100)
        boss.receive_attack(self.char1, now=102.5, rng=Random(1))
        old_hp = boss.db.hp
        self.assertEqual(boss.db.max_hp, 170)
        boss.receive_attack(self.char2, now=102.5, rng=Random(1))
        damage = boss.db.contribution[self.char2.pk]["damage"]
        self.assertEqual(boss.db.max_hp, int(170 * 1.75))
        self.assertEqual(boss.db.hp, old_hp + int(170 * 1.75) - 170 - damage)
        self.assertEqual(ENEMIES["alpha"]["attack"], 17)
        self.char2.leave_combat(now=103)
        boss.scale_boss(103)
        self.assertEqual(boss.db.max_hp, int(170 * 1.75))


    def test_owner_changing_transfer_rejects_unique_but_preserves_personal_storage(self):
        from world.item_transfer_native import transfer

        self.char1.location = self.rooms["storage_room"]
        self.char2.location = self.char1.location
        personal, shared = self.obj("personal_locker"), self.obj("shared_container")
        for identity in BOSS_REWARDS.values():
            row = api.create_item(identity, owner_object=self.char1, location_kind="inventory")
            original = (row.pk, row.sequence)
            transfer(self.char1, ITEMS[identity]["name"], container=personal)
            row.refresh_from_db()
            self.assertEqual((row.location_kind, row.owner_object_id), ("personal_storage", self.char1.pk))
            transfer(self.char1, ITEMS[identity]["name"], container=personal, withdraw=True)
            row.refresh_from_db()
            self.assertEqual((row.pk, row.sequence, row.location_kind), (*original, "inventory"))
            for kwargs in ({"container": shared}, {"recipient": self.char2}):
                before = self.state()
                with self.assertRaises(rules.RuleError):
                    transfer(self.char1, ITEMS[identity]["name"], **kwargs)
                self.assertEqual(before, self.state())
            # 기존 비정상 공용 row는 자동 귀속/복구 없이 양쪽 player 회수를 막는다.
            api.move_item_tree(row, location_kind="shared_storage", owner_object=shared)
            for player in (self.char1, self.char2):
                before = self.state()
                with self.assertRaises(rules.RuleError):
                    transfer(player, ITEMS[identity]["name"], container=shared, withdraw=True)
                self.assertEqual(before, self.state())
        ordinary = api.create_item("scrap", quantity=2, owner_object=self.char1, location_kind="inventory")
        transfer(self.char1, "회수부품 모두", container=shared)
        transfer(self.char2, "회수부품 모두", container=shared, withdraw=True)
        ordinary.refresh_from_db()
        self.assertEqual((ordinary.owner_object_id, ordinary.quantity), (self.char2.pk, 2))

    def test_fresh_cache_repair_parts_cannot_be_lost_and_submit_leaves_scrap(self):
        from evennia import create_object
        from world.item_inventory import consume
        from world.item_transfer_native import transfer
        from world.settlement import parse_salvage

        player = create_object(Explorer, key="새 진행 탐사자", location=self.rooms["dock"])
        player.push_state, player.schedule_recovery = Mock(), Mock()
        cache = self.obj("supply_cache")
        player.location = cache.location
        with patch.object(player, "msg") as output:
            cache.act(player, "조사", None)
            self.assertIn("정비용 회수부품", str(output.call_args_list))
            self.assertIn("탐사인식표", str(output.call_args_list))
        self.assertEqual(player.profile()["inventory"]["generator_repair_part"], 3)
        self.assertNotIn("scrap", player.profile()["inventory"])
        def state():
            return (deserialize(player.db.profile), list(ItemEntity.objects.order_by("sequence").values()),
                    ItemSequence.objects.get(pk=1).last_value, player.db.active_weapon_item_id, player.db.active_light_item_id)
        for shop_id in ("supply_shopkeeper", "weapon_shopkeeper", "armor_shopkeeper", "outpost_weapon_shopkeeper", "outpost_equipment_shopkeeper"):
            shop = self.obj(shop_id)
            player.location = shop.location
            for action, arg in ((shop_service.buy, "generator_repair_part"), (shop_service.sell, "정비부품"), (shop_service.valuation, "정비부품")):
                before = state()
                with self.assertRaises(rules.RuleError):
                    action(player, shop, arg)
                self.assertEqual(before, state())
        player.location = self.rooms["salvage_office"]
        for action in (lambda: incinerate(player, "정비부품"), lambda: consume(player, "generator_repair_part", 1),
                       lambda: parse_salvage("정비용 회수부품")):
            before = state()
            with self.assertRaises((rules.RuleError, ValidationError)):
                action()
            self.assertEqual(before, state())
        player.location = self.rooms["storage_room"]
        self.char2.location = player.location
        for kwargs in ({}, {"recipient": self.char2}, {"container": self.obj("personal_locker")}, {"container": self.obj("shared_container")}):
            before = state()
            with self.assertRaises(rules.RuleError):
                transfer(player, "정비부품", **kwargs)
            self.assertEqual(before, state())
        scrap = api.create_item("scrap", quantity=7, owner_object=player, location_kind="inventory")
        player.change(lambda p: p["quests"]["radio_tower"].update(started=True, record_read=True))
        player.change(rules.fix_generator)
        self.assertTrue(player.profile()["quests"]["radio_tower"]["generator_fixed"])
        self.assertFalse(api.items_owned_by(player).filter(definition_id="generator_repair_part").exists())
        scrap.refresh_from_db()
        self.assertEqual(scrap.quantity, 7)

    def test_final_report_messages_only_announce_actual_unique_grants(self):
        for quest, npc_id, credential in (("radio_tower", "commander", "outpost_supply_pass"),
                                          ("deep_jungle", "pathfinder", "special_supply_pass")):
            npc = self.obj(npc_id)
            self.char1.location = npc.location
            self.char1.change(lambda p: p["quests"][quest].update(started=True, boss_defeated=True, **({"generator_fixed": True} if quest == "radio_tower" else {})))
            identity = BOSS_REWARDS[quest]
            with patch.object(self.char1, "msg") as output:
                npc.perform_action(self.char1, "대화")
                message = str(output.call_args_list)
                for token in (ITEMS[identity]["name"], ITEMS[credential]["name"], "경험치", "칩", "3개"):
                    self.assertIn(token, message)
                output.reset_mock()
                npc.perform_action(self.char1, "대화")
                self.assertNotIn(ITEMS[identity]["name"], str(output.call_args_list))
                api.delete_item(api.items_owned_by(self.char1).get(definition_id=credential), operation="burn")
                output.reset_mock()
                npc.perform_action(self.char1, "대화")
                message = str(output.call_args_list)
                self.assertIn("재발급", message)
                self.assertNotIn(ITEMS[identity]["name"], message)
                self.assertEqual(api.items_owned_by(self.char1).filter(definition_id=identity).count(), 1)


    def test_existing_entitlements_do_not_repeat_cache_parts_or_report_credential(self):
        cache = self.obj("supply_cache")
        self.char1.location = cache.location
        with patch.object(self.char1, "msg") as output:
            cache.perform_action(self.char1, "조사")
            self.assertIn("기존 보유량을 포함해 3개", str(output.call_args_list))
            self.assertNotIn("0개", str(output.call_args_list))
        self.assertEqual(sum(row.quantity for row in api.items_owned_by(self.char1) if row.definition_id == "generator_repair_part"), 3)
        credential_service.grant_credential(self.char1, "outpost_supply_pass")
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(started=True, generator_fixed=True, boss_defeated=True))
        commander = self.obj("commander")
        self.char1.location = commander.location
        with patch.object(self.char1, "msg") as output:
            commander.perform_action(self.char1, "대화")
            message = str(output.call_args_list)
            self.assertIn("능선포식자표식", message)
            self.assertNotIn("전초 보급구역 출입증", message)
