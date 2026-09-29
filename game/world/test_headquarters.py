"""본부 동선·폐쇄 방향과 무결성을 DB 없이 검증한다."""

from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from world import rules
from world.content import REGIONS, ROOMS
from world.content.headquarters import ROOMS as HQ_ROOMS
from world.content.integrity import errors, headquarters_errors
from world.navigation import blocked_exit_message
from world.quests import QUESTS


def content_targets():
    """순수 검사에 필요한 기존 hint/quest 대상의 최소 콘텐츠 fixture."""
    targets = {
        "shared_container": {"room": "storage_room", "actions": ["넣어", "꺼내"]},
        "personal_locker": {"room": "storage_room", "actions": ["넣어", "꺼내"]},
        "instructor": {"room": "training_room", "actions": ["대화", "배워", "배분", "재분배"]},
        "salvage_officer": {"room": "salvage_office", "actions": ["환율", "교환"]},
    }
    for shop_id, room in (("supply", "supply_shop"), ("weapon", "weapon_shop"), ("armor", "armor_shop")):
        targets[shop_id + "_shopkeeper"] = {"room": room, "typeclass": "Shopkeeper", "shop_id": shop_id, "actions": ["대화", "상점", "구매"]}
    for zone, room in ROOMS.items():
        for hint in room.get("hints", []):
            if "target" in hint:
                target = targets.setdefault(hint["target"], {"room": zone, "actions": []})
                if hint["action"] not in target["actions"]:
                    target["actions"].append(hint["action"])
    for quest in QUESTS.values():
        for _, target, role, _ in quest["steps"]:
            if role != "hostile":
                targets.setdefault(target, {"room": "dock", "actions": []})
    return targets


class HeadquartersRulesTests(TestCase):
    def test_service_layout_is_checked_without_room_based_authorization(self):
        targets = content_targets()
        self.assertEqual(errors(targets), [])
        for identity in ("shared_container", "personal_locker", "instructor", "doctor", "infirmary_bed", "salvage_officer"):
            for wrong in ("dock", "missing_room", "support_roof"):
                with self.subTest(identity=identity, wrong=wrong), patch.dict(targets[identity], room=wrong):
                    self.assertTrue(any(f"{identity}: 본부 서비스" in issue for issue in errors(targets)))
        del targets["instructor"]
        self.assertTrue(any("instructor: 본부 서비스" in issue for issue in errors(targets)))

    def test_hub_layout_and_prepared_rooms_are_valid(self):
        self.assertEqual(len(HQ_ROOMS), 26)
        self.assertEqual(errors(content_targets()), [])
        self.assertEqual(ROOMS["staging_room"]["exits"], {"남": "hq_concourse"})
        self.assertEqual(ROOMS["hq_concourse"]["exits"], {
            "북": "staging_room", "서": "dock", "남": "support_1f_c",
        })
        self.assertEqual(ROOMS["support_1f_c"]["exits"], {
            "서": "support_1f_w1", "동": "support_1f_e1", "북": "hq_concourse",
        })
        self.assertEqual(ROOMS["support_1f_c"]["blocked_exits"], {"남": "남쪽 출입문은 현재 폐쇄되어 있다."})
        self.assertEqual(ROOMS["dock"]["exits"], {"북": "grass", "동": "hq_concourse"})
        self.assertEqual(ROOMS["support_roof"]["exits"], {})
        for zone, room in HQ_ROOMS.items():
            self.assertTrue(room["safe"])
            self.assertEqual(room["enemies"], [])
            if zone == "infirmary":
                self.assertEqual(room["hints"], [{"target": "doctor", "action": "치료"},
                                                  {"target": "infirmary_bed", "action": "휴식"}])
            elif zone == "salvage_office":
                self.assertEqual(room["hints"], [{"target": "salvage_officer", "action": "환율"}])
            elif zone in ("supply_shop", "weapon_shop", "armor_shop"):
                self.assertEqual(room["hints"], [{"target": zone.replace("_shop", "_shopkeeper"), "action": "상점"}])
            else:
                self.assertFalse(room.get("hints"))

    def test_each_floor_has_five_corridors_and_facilities_have_single_returns(self):
        for floor in (1, 2, 3):
            row = [f"support_{floor}f_{position}" for position in ("w2", "w1", "c", "e1", "e2")]
            self.assertEqual(len([zone for zone in HQ_ROOMS if zone.startswith(f"support_{floor}f_")]), 5)
            for left, right in zip(row, row[1:]):
                self.assertEqual(ROOMS[left]["exits"]["동"], right)
                self.assertEqual(ROOMS[right]["exits"]["서"], left)
        for facility, corridor in (
            ("salvage_office", "support_1f_w2"), ("storage_room", "support_1f_w1"),
            ("supply_shop", "support_1f_e1"), ("infirmary", "support_2f_w1"),
            ("training_room", "support_2f_e1"), ("armor_shop", "support_3f_w1"),
            ("weapon_shop", "support_3f_e1"),
        ):
            self.assertEqual(ROOMS[corridor]["exits"]["북"], facility)
            self.assertEqual(ROOMS[facility]["exits"], {"남": corridor})

    def test_blocked_direction_projection_is_read_only_and_reuses_aliases(self):
        before = deepcopy(ROOMS)
        count = 0
        for zone, room in HQ_ROOMS.items():
            for direction, message in room.get("blocked_exits", {}).items():
                count += 1
                self.assertNotIn(direction, room["exits"])
                self.assertEqual(blocked_exit_message(zone, direction), message)
        self.assertEqual(count, 22)
        for direction in ("남", "s", " S "):
            self.assertEqual(blocked_exit_message("support_1f_c", direction), "남쪽 출입문은 현재 폐쇄되어 있다.")
        self.assertIsNone(blocked_exit_message("support_1f_c", "북"))
        self.assertIsNone(blocked_exit_message("unknown", "북"))
        self.assertIsNone(blocked_exit_message("support_1f_c", "남 모두"))
        self.assertEqual(ROOMS, before)

    def test_invalid_destination_and_non_opposite_return_are_detected(self):
        with patch.dict(ROOMS["hq_concourse"]["exits"], 남="missing_room"):
            self.assertTrue(any("대상 Room이 없습니다" in issue for issue in errors(content_targets())))
        with patch.dict(ROOMS["storage_room"]["exits"], 남="support_1f_w2"):
            self.assertTrue(any("되돌아오는 출구" in issue for issue in errors(content_targets())))
        with patch.dict(ROOMS["support_1f_c"], exits={"서": "support_1f_w1", "동": "support_1f_e1", "남": "hq_concourse"}):
            self.assertTrue(any("hq_concourse:남: 되돌아오는 출구" in issue for issue in errors(content_targets())))

    def test_blocked_direction_conflicts_and_invalid_messages_are_detected(self):
        with patch.dict(ROOMS["support_1f_c"]["exits"], 남="staging_room"):
            self.assertTrue(any("실제 출구와 폐쇄 출입구가 겹칩니다" in issue for issue in errors(content_targets())))
        for message in (None, "", "   ", 1, {}):
            with self.subTest(message=message), patch.dict(ROOMS["support_1f_c"]["blocked_exits"], 남=message):
                self.assertTrue(any("폐쇄 출입구 문구" in issue for issue in errors(content_targets())))
        with patch.dict(ROOMS["support_1f_c"], blocked_exits=[]):
            self.assertTrue(any("blocked_exits는" in issue for issue in errors(content_targets())))
        with patch.dict(ROOMS["support_1f_c"]["blocked_exits"], 위="출입 제한 구역이다."):
            self.assertTrue(any("폐쇄 출입구 방향" in issue for issue in errors(content_targets())))

    def test_extra_staging_exit_wrong_facility_and_duplicate_membership_are_detected(self):
        with patch.dict(ROOMS["staging_room"]["exits"], 동="dock"):
            self.assertTrue(any("staging_room" in issue for issue in headquarters_errors()))
        with patch.dict(ROOMS["support_1f_e2"]["exits"], 북="storage_room"):
            self.assertTrue(any("시설 Room은 지정 복도" in issue for issue in headquarters_errors()))
        with patch.dict(REGIONS["headquarters"], rooms=(*REGIONS["headquarters"]["rooms"], "support_1f_c")):
            issues = errors(content_targets())
            self.assertTrue(any("Room ID가 중복" in issue for issue in issues))
            self.assertTrue(any("정확히 하나의 Region" in issue for issue in issues))

    def test_new_start_discovery_and_existing_profile_migration_are_separate(self):
        self.assertEqual(rules.new_profile()["visited"], ["staging_room"])
        old = rules.new_profile()
        old.update(version=5, visited=["dock", "grass"], credits=77)
        before = deepcopy(old)
        migrated = rules.migrate_profile(old)
        self.assertEqual(migrated["visited"], ["dock", "grass"])
        self.assertEqual(migrated["credits"], 77)
        self.assertEqual(old, before)
