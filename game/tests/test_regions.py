"""지역 콘텐츠 참조, 월드 동기화, 두 번째 탐사의 실제 동선을 검증한다."""

from copy import deepcopy
from random import Random
from unittest.mock import Mock, patch

from evennia import create_object
from evennia.utils.test_resources import EvenniaCommandTest
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from typeclasses.interactables import INTERACTABLES
from typeclasses.loot import Corpse, room_loot
from typeclasses.parties import invite, respond
from world import rules
from world.bootstrap import build_world, stale_definitions
from world.content import ENEMIES, REGIONS, ROOM_REGION, ROOMS
from world.content.integrity import errors


class RegionTests(EvenniaCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = build_world()
        for player in (self.char1, self.char2):
            player.location = self.rooms["dock"]
            player.home = self.rooms["dock"]
            player.push_state = Mock()
            self.enterContext(patch.object(player.sessions, "count", return_value=1))
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))

    def test_content_integrity_and_stable_first_region(self):
        self.assertEqual(errors(INTERACTABLES), [])
        self.assertEqual(len(REGIONS), 2)
        self.assertEqual(len(ROOMS), 15)
        self.assertEqual(
            set(REGIONS["outpost"]["rooms"]),
            {
                "dock",
                "grass",
                "wreck",
                "trail",
                "office",
                "generator",
                "marsh",
                "ridge",
            },
        )
        self.assertEqual(ROOM_REGION["jungle_nest"], "deep_jungle")
        self.assertEqual(
            len({key for room in ROOMS.values() for key in room["enemies"]}), len(ENEMIES)
        )
        self.assertEqual(stale_definitions(), [])

    def test_bootstrap_updates_static_content_without_resetting_runtime(self):
        room = self.rooms["jungle_road"]
        enemy = room_enemies(room)[0]
        enemy.db.hp = 7
        enemy.db.state = "respawning"
        enemy.db.respawn_at = 999999
        corpse = Corpse.from_enemy(
            enemy, {f"player:{self.char1.id}": {self.char1.id: 10}}, 100, Random(2)
        )
        other = room_enemies(self.rooms["jungle_watch"])[0]
        old_corpse = Corpse.from_enemy(
            other, {f"player:{self.char1.id}": {self.char1.id: 10}}, 100, Random(2)
        )
        old_corpse.reconcile(now=130)
        ground = room_loot(self.rooms["jungle_watch"], corpse=False)[0]
        self.char1.change(lambda profile: profile.update(credits=87))
        identity = enemy.id
        first = {key: obj.id for key, obj in self.rooms.items()}
        exits = sum(len(obj.exits) for obj in self.rooms.values())
        interactables = sum(
            len(
                [
                    obj
                    for obj in room.contents
                    if obj.is_typeclass("typeclasses.interactables.ActionObject", exact=False)
                ]
            )
            for room in self.rooms.values()
        )
        with patch.dict(ROOMS["jungle_road"], {"name": "수몰된 길", "desc": "변경된 정적 설명"}):
            build_world()
            self.assertEqual(room.key, "수몰된 길")
            self.assertEqual(room.db.desc, "변경된 정적 설명")
        updated = build_world()
        self.assertEqual({key: obj.id for key, obj in updated.items()}, first)
        self.assertEqual(sum(len(obj.exits) for obj in updated.values()), exits)
        self.assertEqual(
            sum(
                len(
                    [
                        obj
                        for obj in room.contents
                        if obj.is_typeclass("typeclasses.interactables.ActionObject", exact=False)
                    ]
                )
                for room in updated.values()
            ),
            interactables,
        )
        self.assertEqual(
            (enemy.id, enemy.db.hp, enemy.db.state, enemy.db.respawn_at),
            (identity, 7, "respawning", 999999),
        )
        self.assertEqual(room_loot(room)[0].id, corpse.id)
        self.assertEqual(room_loot(self.rooms["jungle_watch"], corpse=False)[0].id, ground.id)
        self.assertEqual(self.char1.profile()["credits"], 87)

    def test_bootstrap_syncs_enemy_max_hp_without_healing(self):
        enemy = room_enemies(self.rooms["jungle_road"])[0]
        self.assertEqual(enemy.db.max_hp, 92)
        enemy.db.hp = 37
        with patch.dict(ENEMIES["shellback"], {"hp": 100}):
            build_world()
            self.assertEqual((enemy.db.max_hp, enemy.db.hp), (100, 37))
        enemy.db.hp = 95
        with patch.dict(ENEMIES["shellback"], {"hp": 80}):
            build_world()
            self.assertEqual((enemy.db.max_hp, enemy.db.hp), (80, 80))

    def test_bootstrap_syncs_respawning_and_engaged_enemy_without_reset(self):
        enemy = room_enemies(self.rooms["jungle_road"])[0]
        enemy.db.state = "respawning"
        enemy.db.hp = 0
        enemy.db.respawn_at = 999999
        enemy.db.claim = "player:123"
        enemy.db.claim_last_activity = 100
        enemy.db.combatants = [self.char1.id]
        enemy.db.contribution = {self.char1.id: {"damage": 12, "last_action_at": 100}}
        enemy.db.threat = {self.char1.id: 12}
        enemy.db.enemy_round = 3
        enemy.db.next_attack_at = 102.5
        enemy.db.last_activity = 100
        before = (
            enemy.db.state, enemy.db.hp, enemy.db.respawn_at, enemy.db.claim,
            enemy.db.claim_last_activity, enemy.db.combatants, enemy.db.contribution,
            enemy.db.threat, enemy.db.enemy_round, enemy.db.next_attack_at,
            enemy.db.last_activity,
        )
        with patch.dict(ENEMIES["shellback"], {"hp": 100}):
            build_world()
            self.assertEqual(enemy.db.max_hp, 100)
            self.assertEqual(
                (
                    enemy.db.state, enemy.db.hp, enemy.db.respawn_at, enemy.db.claim,
                    enemy.db.claim_last_activity, enemy.db.combatants, enemy.db.contribution,
                    enemy.db.threat, enemy.db.enemy_round, enemy.db.next_attack_at,
                    enemy.db.last_activity,
                ),
                before,
            )
        enemy.db.state = "alive"
        enemy.db.hp = 37
        with patch.dict(ENEMIES["shellback"], {"hp": 110}):
            build_world()
            self.assertEqual((enemy.db.max_hp, enemy.db.hp), (110, 37))
            self.assertEqual((enemy.db.combatants, enemy.db.claim), ([self.char1.id], "player:123"))

    def test_bootstrap_syncs_exit_and_interactable_and_audits_removed_exit(self):
        road = self.rooms["jungle_road"]
        exit_north = next(obj for obj in road.exits if obj.key == "북")
        marker = next(obj for obj in road.contents if obj.key == "수위 표식")
        with (
            patch.dict(ROOMS["jungle_road"]["exits"], {"북": "jungle_watch"}),
            patch.dict(INTERACTABLES["water_marker"], {"name": "침수 표식", "aliases": ["침수"]}),
        ):
            build_world()
            self.assertEqual(exit_north.destination, self.rooms["jungle_watch"])
            self.assertEqual(marker.key, "침수 표식")
            self.assertIn("침수", marker.aliases.all())
        build_world()
        self.assertEqual(exit_north.destination, self.rooms["jungle_grove"])
        self.assertEqual(marker.key, "수위 표식")
        with patch.dict(ROOMS["jungle_road"]["exits"], {}, clear=True):
            self.assertIn(("primal_zone_exit", "jungle_road:북"), stale_definitions())
            self.assertIn(exit_north, road.exits)

    def test_spawn_can_move_without_changing_its_persistent_identity(self):
        edge_enemy = room_enemies(self.rooms["jungle_edge"])[0]
        edge_enemy.db.hp = 9
        with (
            patch.dict(ROOMS["jungle_edge"], {"enemies": []}),
            patch.dict(
                ROOMS["jungle_road"],
                {
                    "enemies": ["shellback", "dartclaw"],
                    "spawn_ids": {"dartclaw": "jungle_edge:dartclaw"},
                },
            ),
        ):
            self.assertEqual(errors(INTERACTABLES), [])
            build_world()
            self.assertEqual(edge_enemy.location, self.rooms["jungle_road"])
            self.assertEqual(edge_enemy.db.hp, 9)
            self.assertEqual(edge_enemy.db.spawn_id, "jungle_edge:dartclaw")
        build_world()
        self.assertEqual(edge_enemy.location, self.rooms["jungle_edge"])
        self.assertEqual(edge_enemy.db.hp, 9)

    def test_region_gate_objectives_and_reconnect(self):
        self.char1.location = self.rooms["ridge"]
        self.assertFalse(self.char1.move_to(self.rooms["jungle_edge"]))
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(claimed=True))
        self.assertTrue(self.char1.move_to(self.rooms["jungle_edge"]))
        self.assertEqual(self.char1.zone, "jungle_edge")
        self.char1.execute_cmd("선발대 길잡이 대화")
        self.assertTrue(self.char1.profile()["quests"]["deep_jungle"]["started"])
        self.char1.execute_cmd("북")
        self.assertEqual(self.char1.zone, "jungle_watch")
        self.char1.execute_cmd("관측 표식 조사")
        self.char1.execute_cmd("동")
        self.assertEqual(self.char1.zone, "jungle_grove")
        self.assertFalse(self.char1.move_to(self.rooms["jungle_gate"]))
        self.char1.execute_cmd("남")
        self.assertEqual(self.char1.zone, "jungle_road")
        self.char1.execute_cmd("수위 표식 조사")
        self.assertEqual(self.char1.profile()["inventory"]["jungle_cell"], 1)
        self.char1.execute_cmd("수위 표식 조사")
        self.assertEqual(self.char1.profile()["inventory"]["jungle_cell"], 1)
        self.char1.execute_cmd("북")
        self.char1.execute_cmd("신호 장치 조사")
        self.assertNotIn("jungle_cell", self.char1.profile()["inventory"])
        self.char1.execute_cmd("남")
        self.char1.execute_cmd("수위 표식 조사")
        self.assertNotIn("jungle_cell", self.char1.profile()["inventory"])
        self.char1.execute_cmd("북")
        self.assertTrue(self.char1.move_to(self.rooms["jungle_gate"]))
        self.char1.execute_cmd("북")
        self.assertEqual(self.char1.zone, "jungle_nest")
        self.assertEqual(self.char1.profile()["visited"][-1], "jungle_nest")
        saved = deepcopy(self.char1.profile())
        self.char1.db.profile = saved
        self.assertEqual(self.char1.profile()["quests"], saved["quests"])
        self.assertIn("포식자", self.char1.quest_text(saved))
        with patch.object(self.char1, "msg") as message:
            self.char1.execute_cmd("지도")
        self.assertIn("[깊은 밀림]", str(message.call_args_list))
        with patch.object(self.char1, "msg") as message:
            Explorer.push_state(self.char1)
        state = message.call_args.kwargs["pz_state"][0][0]
        self.assertEqual((state["region"], state["region_name"]), ("deep_jungle", "깊은 밀림"))

    def test_optional_branch_and_public_boss_rewards(self):
        self.char1.change(lambda p: p["quests"]["radio_tower"].update(claimed=True))
        self.char1.change(lambda p: p["quests"]["deep_jungle"].update(started=True))
        self.char1.location = self.rooms["jungle_fen"]
        self.char1.execute_cmd("늪지 보급품 조사")
        self.assertEqual(self.char1.profile()["inventory"]["bandage"], 5)
        self.char1.execute_cmd("늪지 보급품 조사")
        self.assertEqual(self.char1.profile()["inventory"]["bandage"], 5)
        boss = room_enemies(self.rooms["jungle_nest"])[0]
        self.assertEqual(boss.db.enemy_id, "jungle_apex")
        self.assertEqual(ENEMIES["jungle_apex"]["combat_mode"], "public")
        third = create_object(Explorer, key="세번째탐사자")
        third.push_state = Mock()
        self.enterContext(patch.object(third.sessions, "count", return_value=1))
        for player in (self.char1, self.char2, third):
            player.location = self.rooms["jungle_nest"]
        party = invite(self.char2, third, now=100)
        respond(third, True, now=101)
        for player in (self.char1, self.char2, third):
            boss.engage(player, now=100)
        boss.db.contribution = {
            self.char1.id: {
                "damage": 30,
                "last_action_at": 105,
                "group": f"player:{self.char1.id}",
            },
            self.char2.id: {"damage": 10, "last_action_at": 105, "group": f"party:{party.id}"},
            third.id: {"damage": 10, "last_action_at": 105, "group": f"party:{party.id}"},
        }
        boss.db.hp = 0
        boss.finish_death(self.char1, now=105, rng=Random(1))
        self.assertEqual([p.profile()["xp"] for p in (self.char1, self.char2, third)], [93, 31, 31])
        self.assertEqual(
            sum(p.profile()["credits"] - 20 for p in (self.char1, self.char2, third)), 58
        )
        self.assertTrue(
            all(
                p.profile()["quests"]["deep_jungle"]["boss_defeated"]
                for p in (self.char1, self.char2, third)
            )
        )
        self.assertEqual(len(room_loot(self.rooms["jungle_nest"])), 1)
        entries = room_loot(self.rooms["jungle_nest"])[0].db.entries
        self.assertEqual(len(entries), 2)
        self.assertEqual(
            {entry["reserved_player"] for entry in entries if entry["reserved_player"]},
            {self.char1.id},
        )
        self.assertEqual(
            {entry["reserved_party"] for entry in entries if entry["reserved_party"]}, {party.id}
        )
        boss.finish_death(self.char1, now=105, rng=Random(1))
        self.assertEqual(len(room_loot(self.rooms["jungle_nest"])), 1)
        self.char1.location = self.rooms["jungle_edge"]
        self.char1.execute_cmd("선발대 길잡이 대화")
        self.assertTrue(self.char1.profile()["quests"]["deep_jungle"]["claimed"])
        before = deepcopy(self.char1.profile())
        self.char1.execute_cmd("선발대 길잡이 대화")
        self.assertEqual(self.char1.profile(), before)

    def test_jungle_normal_enemy_uses_shared_corpse_and_existing_loot(self):
        from typeclasses.loot import take_loot

        self.char1.location = self.rooms["jungle_edge"]
        enemy = room_enemies(self.rooms["jungle_edge"])[0]
        enemy.engage(self.char1, now=100)
        enemy.db.hp = 1
        enemy.receive_attack(self.char1, now=102.5, rng=Random(3))
        self.assertEqual(self.char1.profile()["xp"], ENEMIES["dartclaw"]["xp"])
        self.assertEqual(len(room_loot(self.rooms["jungle_edge"])), 1)
        take_loot(self.char1, corpse=True, now=103)
        self.assertEqual(self.char1.profile()["inventory"]["scrap"], 1)

    def test_jungle_boss_telegraphs_on_its_own_round(self):
        self.char1.location = self.rooms["jungle_nest"]
        boss = room_enemies(self.rooms["jungle_nest"])[0]
        boss.engage(self.char1, now=100)
        boss.db.enemy_round = 2
        boss.db.next_attack_at = 102.5
        with patch.object(self.char1, "msg") as message:
            boss.enemy_tick(now=102.5, rng=Random(1))
        self.assertEqual(boss.db.enemy_round, 3)
        self.assertIn("도약할 자세", str(message.call_args_list))
        self.assertFalse(rules.boss_telegraph("jungle_apex", 2))
        self.assertTrue(rules.boss_telegraph("jungle_apex", 3))
