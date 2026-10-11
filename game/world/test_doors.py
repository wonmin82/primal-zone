"""Door 정적 정의는 실제 DB 검사와 분리한다."""

from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from world.content.doors import DOORS
from world.content.integrity import door_errors
from world.test_headquarters import content_targets


class DoorDefinitionTests(TestCase):
    def test_fixed_definitions_and_cabinet_validation_without_database(self):
        targets = content_targets()
        self.assertEqual(door_errors(targets), [])
        for field, value in (("room", "dock"), ("actions", []), ("typeclass", "Object")):
            with self.subTest(field=field), patch.dict(targets["hq_admin_key_cabinet"], {field: value}):
                self.assertTrue(door_errors(targets))

    def test_state_policy_and_endpoint_conflicts_fail_static_validation(self):
        for identity, overrides in (("hq_admin_door", {"initial_state": "OPEN"}),
                                    ("hq_admin_door", {"inside_room_id": "dock"}),
                                    ("recovery_room_door", {"lockable": True}),
                                    ("recovery_room_door", {"endpoints": DOORS["hq_admin_door"]["endpoints"]})):
            definitions = deepcopy(DOORS)
            definitions[identity].update(overrides)
            with self.subTest(identity=identity, overrides=overrides), patch.dict(DOORS, definitions, clear=True):
                self.assertTrue(door_errors(content_targets()))
