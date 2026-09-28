"""재사용 월드의 DB·NDb 격리와 테스트용 해시의 인증 호환을 검증한다."""

import io
import pickle
import unittest
from weakref import WeakKeyDictionary

from django.contrib.auth.hashers import PBKDF2PasswordHasher, check_password, make_password
from django.test import SimpleTestCase, override_settings
from evennia import create_object, search_tag
from server.conf.test_runner import PrimalRemoteTestRunner
from typeclasses.enemies import room_enemies
from world.content import ENEMIES, ROOMS

from tests.base import WorldCommandTest


def raise_worker_error():
    raise RuntimeError("병렬 실패 전달 검증")


class ParallelFailureTests(SimpleTestCase):
    def test_worker_error_and_traceback_can_be_transferred(self):
        result = PrimalRemoteTestRunner().run(unittest.FunctionTestCase(raise_worker_error))
        events = pickle.loads(pickle.dumps(result.events))
        errors = [event for event in events if event[0] == "addError"]
        self.assertEqual(len(errors), 1)
        exception_type, exception, traceback = errors[0][2]
        self.assertIs(exception_type, RuntimeError)
        self.assertEqual(str(exception), "병렬 실패 전달 검증")
        self.assertIsNotNone(traceback)

    def test_subtest_failure_does_not_transfer_mutable_fixture_objects(self):
        class Probe(unittest.TestCase):
            def runTest(self):
                self.fixture = WeakKeyDictionary()
                with self.subTest(boundary="runtime-cache"):
                    self.fail("임시 객체를 가진 subTest 실패")

        probe = Probe()
        result = PrimalRemoteTestRunner().run(probe)
        # 실제 정리에서도 이벤트 기록 뒤 TestCase의 캐시 참조가 달라진다.
        probe.fixture = WeakKeyDictionary()
        events = pickle.loads(pickle.dumps(result.events))
        failures = [event for event in events if event[0] == "addSubTest"]
        self.assertEqual(len(failures), 1)
        self.assertIn("boundary='runtime-cache'", failures[0][2].id())
        exception_type, exception, traceback = failures[0][3]
        self.assertIs(exception_type, AssertionError)
        self.assertEqual(str(exception), "임시 객체를 가진 subTest 실패")
        self.assertIsNotNone(traceback)
        parent_result = unittest.TextTestResult(
            unittest.runner._WritelnDecorator(io.StringIO()), descriptions=True, verbosity=1,
        )
        parent_result.addSubTest(probe, failures[0][2], failures[0][3])
        self.assertEqual(len(parent_result.failures), 1)
        self.assertEqual(len(parent_result.errors), 0)


class WorldFixtureIsolationTests(WorldCommandTest):
    def setUp(self):
        super().setUp()
        self.rooms = self.world_rooms()

    def check_pristine_world(self):
        room = self.rooms["grass"]
        self.assertEqual(room.key, ROOMS["grass"]["name"])
        self.assertEqual({obj.key for obj in room.exits}, set(ROOMS["grass"]["exits"]))
        enemy = room_enemies(room)[0]
        self.assertEqual(enemy.db.hp, ENEMIES[enemy.db.enemy_id]["hp"])
        self.assertIsNone(enemy.ndb.fixture_marker)
        container = search_tag("shared_container", category="primal_interactable")[0]
        self.assertEqual(container.db.items, {})
        self.assertFalse(search_tag("fixture_marker", category="primal_test"))

    def mutate_world(self):
        room = self.rooms["grass"]
        room.key = "테스트에서 변경한 장소"
        enemy = room_enemies(room)[0]
        enemy.db.hp = 1
        enemy.ndb.fixture_marker = "이전 테스트의 임시 상태"
        room.exits[0].delete()
        container = search_tag("shared_container", category="primal_interactable")[0]
        container.db.items = {"bandage": 99}
        marker = create_object(key="격리 검증용 객체")
        marker.tags.add("fixture_marker", category="primal_test")

    def test_room_mutations_do_not_survive_rollback(self):
        self.check_pristine_world()
        self.mutate_world()

    def test_runtime_mutations_do_not_survive_rollback(self):
        # 정순·역순 모두 직전 테스트의 변형을 검사하도록 두 테스트가 상태를 남긴다.
        self.check_pristine_world()
        with self.assertNumQueries(1):
            rooms = self.world_rooms()
        self.assertEqual(set(rooms), set(ROOMS))
        self.assertEqual(rooms["grass"], self.rooms["grass"])
        self.mutate_world()


class PasswordHasherTests(SimpleTestCase):
    def test_fast_fixture_passwords_still_verify(self):
        encoded = make_password("fixture-password")
        self.assertTrue(encoded.startswith("md5$"))
        self.assertTrue(check_password("fixture-password", encoded))
        self.assertFalse(check_password("different-password", encoded))

    @override_settings(PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher",
        "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    ])
    def test_existing_pbkdf2_passwords_verify_with_explicit_auth_settings(self):
        hasher = PBKDF2PasswordHasher()
        encoded = hasher.encode("existing-password", hasher.salt())
        self.assertTrue(check_password("existing-password", encoded))
        self.assertFalse(check_password("different-password", encoded))
