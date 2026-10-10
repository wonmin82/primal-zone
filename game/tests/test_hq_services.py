"""보관·훈련 이전과 실제 객체 기반 권한, bootstrap 저장 데이터 보존."""

from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock, patch

from evennia import search_tag
from evennia.objects.models import ObjectDB
from evennia.utils.dbserialize import deserialize
from typeclasses.explorers import Explorer
from typeclasses.interactables import INTERACTABLES, instructor_for
from world.bootstrap import build_world, stale_definitions
from world.environment_state import snapshot_for
from world.state import multiplayer_state

from tests.base import GameCommandTest, WorldCommandTest


class ServiceRelocationTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()
        self.services = {key: search_tag(key, category="primal_interactable")[0]
                         for key in ("shared_container", "personal_locker", "instructor")}
        for player in (self.char1, self.char2):
            player.location = self.rooms["storage_room"]
            player.push_state = Mock()
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))

    def command(self, value):
        with patch.object(self.char1, "msg") as output:
            self.char1.execute_cmd(value)
        return str(output.call_args_list)

    def state(self):
        with patch.object(self.char1.sessions, "count", return_value=1), patch.object(self.char1, "msg") as output:
            Explorer.push_state(self.char1, observed_at=100)
        return output.call_args.kwargs["pz_state"][0][0]

    def test_actual_storage_objects_drive_commands_presentation_and_web(self):
        for identity in ("shared_container", "personal_locker"):
            self.assertEqual(self.services[identity].location, self.rooms["storage_room"])
        state = multiplayer_state(self.char1)
        self.assertEqual({obj["name"] for obj in state["interactables"]}, {"보관상자", "개인 보관함"})
        for name in ("보관상자", "개인 보관함"):
            self.assertIn(name, self.command("봐"))
            self.command(f"{name}에 붕대 넣어")
            self.command(f"{name}에서 붕대 꺼내")
        self.assertEqual(self.char1.profile()["inventory"]["bandage"], 3)
        self.assertEqual(self.char1.profile()["storage"], {})
        box = self.services["shared_container"]
        self.assertEqual(box.db.items, {})
        box.location = self.rooms["support_roof"]
        before = deepcopy(self.char1.profile())
        self.assertIn("대상 뒤에 '에'를 붙이고", self.command("보관상자에 붕대 넣어"))
        self.assertEqual(self.char1.profile(), before)
        self.assertNotIn("보관상자", {obj["name"] for obj in multiplayer_state(self.char1)["interactables"]})
        self.char1.location = box.location
        self.command("보관상자에 붕대 넣어")
        self.assertEqual(box.db.items, {"bandage": 1})

    def test_dock_has_no_storage_or_training_targets_and_failures_preserve_profile(self):
        # 이 검사는 서비스 실패의 불변성을 본다. 실제 10초 회복 경계와 분리한다.
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        self.char1.location = self.rooms["dock"]
        self.char1.reconcile_recovery(emit_prompt=False)
        before = deepcopy(self.char1.profile())
        for raw in ("보관상자에 붕대 넣어", "보관상자에서 붕대 꺼내",
                    "개인 보관함에 붕대 넣어", "개인 보관함에서 붕대 꺼내",
                    "강타 배워", "힘 1 배분", "전체 재훈련", "탐사대 훈련관 대화"):
            with self.subTest(command=raw):
                output = self.command(raw)
                self.assertTrue("대상" in output or "주변" in output or "교관이 없다" in output)
                self.assertNotIn("보관실에서만", output)
                self.assertEqual(self.char1.profile(), before)
        self.assertIsNone(instructor_for(self.char1))
        self.assertFalse(self.state()["training_available"])
        self.assertEqual({obj["name"] for obj in self.state()["interactables"]}, {"윤대장"})

    def test_service_paths_reuse_cardinal_movement_and_elevator(self):
        self.char1.location = self.rooms["hq_concourse"]
        for command in ("계단", "위", "나가기", "서", "북"):
            self.command(command)
        self.assertEqual(self.char1.zone, "storage_room")
        self.command("보관상자에 붕대 넣어")
        self.assertEqual(self.services["shared_container"].db.items, {"bandage": 1})
        for command in ("남", "동", "승강기", "4층", "서", "북"):
            self.command(command)
        self.assertEqual(self.char1.zone, "training_room")
        self.assertIn(INTERACTABLES["trainer_strength"]["dialogue"], self.command("근력교관 대화"))
        self.assertTrue(self.state()["training_available"])
        self.command("힘 1 배분")
        self.assertEqual(self.char1.profile()["attributes"]["strength"]["allocated"], 1)
        self.assertIn("support_elevator", self.char1.profile()["visited"])

    def test_training_follows_actual_npc_safe_room_and_peace(self):
        from world import rules
        # 훈련 권한 실패의 불변성을 실제 10초 자연회복 경계와 분리한다.
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        self.char1.reconcile_recovery(emit_prompt=False)
        instructor = search_tag('trainer_heavy', category='primal_interactable')[0]
        self.char1.change(lambda p: p.update(xp=rules.xp_threshold(2)))
        self.char1.location = instructor.location
        self.assertTrue(instructor.available(self.char1))
        instructor.location = self.rooms['support_roof']
        before = deepcopy(self.char1.profile())
        self.command('강타 배워')
        self.assertEqual(self.char1.profile(), before)
        self.char1.location = instructor.location
        self.assertIs(instructor_for(self.char1), instructor)
        self.assertTrue(self.state()['training_available'])
        self.command('강타 배워')
        self.assertEqual(self.char1.profile()['skills']['heavy'], 2)
        self.assertEqual(self.char1.profile()['credits'], before['credits'])
        instructor.location = self.rooms['grass']
        self.char1.location = instructor.location
        self.assertFalse(instructor.available(self.char1))
        before = deepcopy(self.char1.profile())
        self.command('강타 배워')
        self.assertEqual(self.char1.profile(), before)
        instructor.location = self.rooms['training_room']
        self.char1.location = instructor.location
        self.char1.change(lambda p: p.update(combat_target=999))
        before = deepcopy(self.char1.profile())
        for command in ('강타 배워', '힘 1 배분'):
            self.assertIn('전투 중', self.command(command))
            self.assertEqual(self.char1.profile(), before)
        self.assertFalse(self.state()['training_available'])

    def test_training_visibility_agrees_with_commands_and_web(self):
        # 시야/권한 실패의 전체 profile 불변 검사를 자연회복 시각과 분리한다.
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        instructor = search_tag('trainer_heavy', category='primal_interactable')[0]
        self.char1.location = self.rooms['support_roof']
        instructor.location = self.char1.location
        self.char1.reconcile_recovery(emit_prompt=False)
        before = deepcopy(self.char1.profile())
        instructor.locks.add('view:false()')
        self.assertIsNone(instructor_for(self.char1))
        self.assertFalse(instructor.available(self.char1))
        self.assertFalse(self.state()['training_available'])
        self.assertNotIn(instructor.key, {obj['name'] for obj in self.state()['interactables']})
        self.command('강타 배워')
        self.assertEqual(self.char1.profile(), before)
        instructor.locks.add('view:all()')
        instructor.db.detectability = 'subtle'
        poor = replace(snapshot_for(self.char1.location, 100), visibility='poor', ambient_light='dark')
        with patch('world.environment_state.snapshot_for', return_value=poor):
            self.assertIsNone(instructor_for(self.char1, observed_at=100))
            self.assertFalse(self.state()['training_available'])
            self.command('강타 배워')
            self.assertEqual(self.char1.profile(), before)
        self.assertIs(instructor_for(self.char1), instructor)
        self.assertTrue(self.state()['training_available'])


class ServiceMigrationTests(GameCommandTest):
    character_typeclass = Explorer

    def test_bootstrap_moves_existing_objects_and_preserves_every_owner(self):
        keys = ("shared_container", "personal_locker", "instructor")
        with patch.dict(INTERACTABLES, {key: {**INTERACTABLES[key], "room": "dock"} for key in keys}):
            rooms = build_world()
        objects = {key: search_tag(key, category="primal_interactable")[0] for key in keys}
        self.assertTrue(all(obj.location == rooms["dock"] for obj in objects.values()))
        objects["shared_container"].db.items = {"bandage": 4, "field_ration": 2}
        self.char1.change(lambda p: p["storage"].update(bandage=2))
        self.char2.change(lambda p: p["storage"].update(water=3))
        self.char1.location = rooms["dock"]
        self.char2.location = rooms["training_room"]
        profiles = [deepcopy(player.profile()) for player in (self.char1, self.char2)]
        ids = {key: obj.id for key, obj in objects.items()}
        count = ObjectDB.objects.count()
        room_ids = {zone: room.id for zone, room in rooms.items()}
        for _ in range(2):
            rebuilt = build_world()
            self.assertEqual({zone: room.id for zone, room in rebuilt.items()}, room_ids)
            self.assertEqual(ObjectDB.objects.count(), count)
            for key, obj in objects.items():
                tagged = search_tag(key, category="primal_interactable")
                self.assertEqual([entry.id for entry in tagged], [ids[key]])
                self.assertEqual(obj.location, rooms[INTERACTABLES[key]["room"]])
                self.assertEqual(set(obj.aliases.all()), set(INTERACTABLES[key]["aliases"]))
            self.assertEqual(deserialize(objects["shared_container"].db.items), {"bandage": 4, "field_ration": 2})
            self.assertEqual([player.profile() for player in (self.char1, self.char2)], profiles)
            self.assertEqual([self.char1.location, self.char2.location], [rooms["dock"], rooms["training_room"]])
        locker = objects["personal_locker"]
        self.char1.location = self.char2.location = rooms["storage_room"]
        self.assertIn("붕대 ×2", locker.return_appearance(self.char1))
        self.assertNotIn("정제수", locker.return_appearance(self.char1))
        self.assertIn("정제수 ×3", locker.return_appearance(self.char2))
        self.assertNotIn("붕대", locker.return_appearance(self.char2))
        self.assertEqual(stale_definitions(), [])
