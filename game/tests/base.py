"""테스트별 DB rollback과 Evennia runtime 캐시 격리, 클래스별 월드 준비."""

import gc
from unittest.mock import patch

from evennia.commands import cmdhandler
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel
from evennia.utils.test_resources import EvenniaCommandTest
from world.bootstrap import build_world


def clear_test_caches():
    """rollback 이후 NDb·명령 객체가 이전 DB 객체를 재사용하지 않게 한다."""
    pending = [SharedMemoryModel]
    seen = set()
    while pending:
        model = pending.pop()
        if model in seen:
            continue
        seen.add(model)
        subclasses = model.__subclasses__()
        if subclasses:
            pending.extend(subclasses)
        else:
            model.flush_instance_cache(force=True)
    # Evennia 6.1의 merge cache도 Command.obj를 통해 이전 객체를 유지한다.
    cmdhandler._CMDSET_MERGE_CACHE.clear()
    gc.collect()


class GameCommandTest(EvenniaCommandTest):
    """계정·세션 정리는 기존 훅을 사용하고 GC는 rollback 뒤 한 번 실행한다."""

    def tearDown(self):
        with patch("evennia.utils.test_resources.flush_cache"):
            super().tearDown()

    def _fixture_teardown(self):
        try:
            super()._fixture_teardown()
        finally:
            clear_test_caches()

    @classmethod
    def tearDownClass(cls):
        try:
            super().tearDownClass()
        finally:
            clear_test_caches()


class WorldCommandTest(GameCommandTest):
    """클래스 transaction에 월드를 준비하고 테스트에는 새 객체 참조를 제공한다."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls._world_room_ids = {zone: room.pk for zone, room in build_world().items()}
        clear_test_caches()

    def world_rooms(self):
        # ID만 공유한다. 각 테스트의 ORM/Attribute/NDb 객체는 공유하지 않는다.
        objects = ObjectDB.objects.in_bulk(self._world_room_ids.values())
        return {zone: objects[identity] for zone, identity in self._world_room_ids.items()}
