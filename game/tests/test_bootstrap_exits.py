"""관리 태그의 소유권과 읽기 전용 bootstrap 충돌 검증."""

from unittest.mock import Mock, patch

from evennia import create_object, search_tag
from evennia.objects.models import ObjectDB
from evennia.typeclasses.models import Attribute
from evennia.typeclasses.tags import Tag
from typeclasses.exits import Exit
from typeclasses.explorers import Explorer
from typeclasses.zone_rooms import ZoneRoom
from world.bootstrap import CATEGORY, EXIT_CATEGORY, build_world, validate_managed_exits
from world.item_entities.models import ItemEntity, ItemRuntime, ItemSequence

from tests.base import WorldCommandTest


class BootstrapExitTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        super().setUp()
        self.rooms = self.world_rooms()
        self.char1.push_state = Mock()

    def snapshot(self):
        models = (ObjectDB, Attribute, Tag, ObjectDB.db_tags.through, ItemEntity, ItemSequence, ItemRuntime)
        return {model._meta.label: list(model.objects.order_by("pk").values()) for model in models}

    def assert_conflict_preserves_database(self, expression):
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, expression):
            build_world()
        self.assertEqual(self.snapshot(), before)

    def test_managed_exit_updates_in_place_and_missing_exit_is_created_once(self):
        existing = search_tag("hq_concourse:북", category=EXIT_CATEGORY)[0]
        identity = existing.id
        existing.destination = self.rooms["dock"]
        missing = search_tag("hq_concourse:동", category=EXIT_CATEGORY)[0]
        missing.delete()
        build_world()
        self.assertEqual(existing.id, identity)
        self.assertEqual(existing.destination, self.rooms["staging_room"])
        created = search_tag("hq_concourse:동", category=EXIT_CATEGORY)[0].id
        count = ObjectDB.objects.count()
        build_world()
        self.assertEqual(ObjectDB.objects.count(), count)
        self.assertEqual(search_tag("hq_concourse:동", category=EXIT_CATEGORY)[0].id, created)

    def test_same_direction_unmanaged_exit_blocks_before_any_world_change(self):
        managed = search_tag("hq_concourse:북", category=EXIT_CATEGORY)[0]
        managed.delete()
        custom = create_object(Exit, key="북", aliases=["사유 통로"],
                               location=self.rooms["hq_concourse"], destination=self.rooms["dock"])
        custom.tags.add("custom", category="another_system")
        self.rooms["hq_concourse"].db.desc = "보존할 옛 설명"
        retired = create_object(ZoneRoom, key="이전 복도")
        retired.db.zone_id = "support_1f_c"
        retired.tags.add("support_1f_c", category=CATEGORY)
        self.char1.location = retired
        self.char1.home = retired
        self.char1.db.prelogout_location = retired
        npc = search_tag("instructor", category="primal_interactable")[0]
        npc.location = retired
        self.assert_conflict_preserves_database(rf"hq_concourse.*북.*#{custom.id}.*{self.rooms['dock'].key}")
        self.assertEqual(self.char1.location, retired)
        self.assertEqual(npc.location, retired)
        self.assertEqual(custom.aliases.all(), ["사유 통로"])
        self.assertFalse(custom.tags.get(category=EXIT_CATEGORY))
        self.assertEqual(custom.destination, self.rooms["dock"])

    def test_alias_collision_with_existing_managed_exit_is_rejected(self):
        custom = create_object(Exit, key="사유 통로", aliases=["N"],
                               location=self.rooms["hq_concourse"], destination=self.rooms["dock"])
        self.assert_conflict_preserves_database(rf"hq_concourse.*북.*#{custom.id}")

    def test_direction_shortcut_collision_is_rejected(self):
        custom = create_object(Exit, key="ㅂ", location=self.rooms["hq_concourse"], destination=self.rooms["dock"])
        self.assert_conflict_preserves_database(rf"hq_concourse.*북.*#{custom.id}")

    def test_unmanaged_exit_in_blocked_direction_is_not_deleted(self):
        custom = create_object(Exit, key="남", location=self.rooms["support_5f_c"], destination=self.rooms["dock"])
        self.assert_conflict_preserves_database(rf"support_5f_c.*남.*#{custom.id}")
        self.assertTrue(ObjectDB.objects.filter(pk=custom.id).exists())

    def test_duplicate_managed_identity_is_rejected(self):
        duplicate = create_object(Exit, key="북", location=self.rooms["hq_concourse"], destination=self.rooms["dock"])
        duplicate.tags.add("hq_concourse:북", category=EXIT_CATEGORY)
        self.assert_conflict_preserves_database("identity 중복")

    def test_multiple_managed_tags_and_wrong_room_are_rejected(self):
        existing = search_tag("hq_concourse:북", category=EXIT_CATEGORY)[0]
        existing.tags.add("staging_room:남", category=EXIT_CATEGORY)
        self.assert_conflict_preserves_database("태그/위치 충돌")
        existing.tags.remove("staging_room:남", category=EXIT_CATEGORY)
        existing.location = self.rooms["dock"]
        self.assert_conflict_preserves_database("태그/위치 충돌")

    def test_preflight_is_read_only_for_valid_database(self):
        before = self.snapshot()
        validate_managed_exits()
        self.assertEqual(self.snapshot(), before)
