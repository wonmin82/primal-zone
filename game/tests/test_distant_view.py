"""보기 alias, 실제 Exit 관찰과 원거리 정보/부작용 경계 검증."""

from copy import deepcopy
from unittest.mock import Mock, patch

from evennia import create_object, search_tag
from evennia.objects.objects import DefaultObject
from evennia.utils.dbserialize import deserialize
from typeclasses.enemies import Enemy, room_enemies
from typeclasses.exits import Exit
from typeclasses.explorers import Explorer
from typeclasses.interactables import Container, MaintenanceLog, PersonalLocker
from typeclasses.loot import Corpse, DroppedLoot
from typeclasses.zone_rooms import ZoneRoom
from world import rules
from world.content import ENEMIES, ROOMS
from world.distant_presentation import DistantViewContext, direction_phrase

from tests.base import WorldCommandTest


class DistantViewTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        super().setUp()
        for module in ("typeclasses.enemies", "typeclasses.explorers", "typeclasses.loot"):
            self.enterContext(patch(module + ".delay"))
        # 관찰과 명령의 회복 경계를 같은 시각으로 고정해 실제 시계 경합을 배제한다.
        for module in (
            "commands.character", "typeclasses.zone_rooms", "world.lifecycle",
            "typeclasses.explorers",
            "typeclasses.enemies",
            "typeclasses.loot",
            "world.distant_presentation",
        ):
            self.enterContext(patch(module + ".time", return_value=100))
        self.rooms = self.world_rooms()
        self.char1.location = self.rooms["grass"]
        self.char2.location = self.rooms["dock"]
        self.char1.push_state = Mock()
        self.char2.push_state = Mock()

    def command(self, value):
        with patch.object(self.char1, "msg") as message:
            self.char1.execute_cmd(value)
        call = message.call_args
        output = call.args[0] if call.args else call.kwargs["text"]
        return output[0] if isinstance(output, tuple) else output

    def enemy(self, room, identity="hunter"):
        obj = create_object(Enemy, key=ENEMIES[identity]["name"], location=room)
        obj.db.enemy_id = identity
        obj.db.hp = obj.db.max_hp = ENEMIES[identity]["hp"]
        return obj

    def corpse(self, room, decay=130):
        obj = create_object(Corpse, key="갈퀴사냥룡의 시체", location=room)
        obj.db.decay_at = decay
        obj.db.entries = [
            {
                "item": "scrap",
                "quantity": 7,
                "reserved_player": self.char1.id,
                "reserved_party": None,
                "assigned_player": self.char1.id,
                "protection_until": 200,
            }
        ]
        return obj

    def context(self, room, **kwargs):
        return DistantViewContext(self.char1, self.char1.location, room, observed_at=100, **kwargs)

    def test_alias_preserves_default_index_all_for_enemy_corpse_and_other_targets(self):
        room = self.rooms["trail"]
        self.char1.location = room
        self.enemy(room)
        self.enemy(room)
        self.corpse(room)
        self.corpse(room)
        for target in (
            "갈퀴사냥룡",
            "갈퀴사냥룡 2",
            "갈퀴사냥룡 모두",
            "시체",
            "시체 2",
            "시체 모두",
        ):
            with self.subTest(target=target):
                normal = self.command(target + " 보기")
                alias = self.command(target + " 봐")
                self.assertEqual(str(alias), str(normal))
                self.assertEqual(alias.segments, normal.segments)
        self.char1.location = self.rooms["dock"]
        for target in ("보관상자", "개인 보관함", "윤대장", "탐사용 벌목도"):
            self.assertEqual(self.command(target + " 봐"), self.command(target + " 보기"))
        self.assertEqual(self.command("봐"), self.command("보기"))
        self.assertIn("봐", self.command("보기 도움말"))
        self.assertIn("북 봐", self.command("봐 도움말"))

    def test_existing_direction_keys_and_aliases_use_the_same_preview(self):
        for zone in ("dock", "grass", "wreck"):
            self.char1.location = self.rooms[zone]
            for exit_obj in self.char1.location.exits:
                destination = exit_obj.destination
                expected = self.command(exit_obj.key + " 보기")
                for name in (exit_obj.key, *exit_obj.aliases.all()):
                    for action in ("보기", "봐"):
                        with self.subTest(zone=zone, name=name, action=action):
                            output = self.command(name + " " + action)
                            self.assertEqual(output, expected)
                            self.assertIn(destination.key, output)
                            self.assertIn(ROOMS[destination.db.zone_id]["desc"], output)
                            self.assertEqual(self.char1.location, self.rooms[zone])
                self.assertTrue(any(s["role"] == "direction" for s in expected.segments))

    def test_distant_summary_groups_living_enemies_and_unexpired_corpses_only(self):
        target = self.rooms["trail"]
        self.enemy(target)
        dead = self.enemy(target)
        dead.db.state = "respawning"
        dead.db.respawn_at = 90  # 재생성 시각이 지나도 관찰이 respawn을 실행하지 않는다.
        self.corpse(target)
        self.corpse(target)
        expired = self.corpse(target, decay=100)
        output = self.command("북 봐")
        self.assertIn("갈퀴사냥룡 두 마리", output)
        self.assertIn("갈퀴사냥룡의 시체 두 구", output)
        for secret in (
            "갈퀴사냥룡 1",
            "갈퀴사냥룡 2",
            "시체 1",
            "시체 2",
            "체력",
            "HP",
            "배정",
            "보호",
            "회수부품",
            "가져",
            "공격",
        ):
            self.assertNotIn(secret, output)
        self.assertEqual(dead.db.state, "respawning")
        self.assertIsNotNone(expired.pk)
        self.assertTrue(expired in target.contents)
        self.assertEqual(
            [s["text"] for s in output.segments if s["role"] == "hostile"], ["갈퀴사냥룡"]
        )
        self.assertEqual(
            [s["text"] for s in output.segments if s["role"] == "remains"], ["갈퀴사냥룡의 시체"]
        )
        self.assertFalse(any(s["role"] in ("item", "command") for s in output.segments))

    def test_npc_containers_and_anonymous_players_do_not_expose_contents(self):
        self.char1.location = self.rooms["support_2f_w1"]
        self.char2.location = self.rooms["storage_room"]
        self.char1.profile()  # 아래 spy 이전에 기본 캐릭터 상태만 준비한다.
        self.char1.change(lambda p: p["storage"].update(scrap=17))
        box = search_tag("shared_container", category="primal_interactable")[0]
        box.db.items = {"bandage": 9, "water": 8}
        floor = create_object(DroppedLoot, key="회수부품", location=self.rooms["storage_room"])
        floor.db.entries = [{"item": "scrap", "quantity": 7}]
        with (
            patch.object(
                self.char1, "profile", side_effect=AssertionError("remote profile access")
            ),
            patch.object(
                PersonalLocker, "return_appearance", side_effect=AssertionError("contents access")
            ),
        ):
            output = self.command("북 봐")
        for name in ("보관상자", "개인 보관함", "탐사자 한 명"):
            self.assertIn(name, output)
        for secret in (
            self.char2.key,
            "붕대",
            "정제수",
            "회수부품",
            "넣어",
            "꺼내",
            "대화",
            "체력",
            "파티",
        ):
            self.assertNotIn(secret, output)
        self.assertEqual(box.db.items, {"bandage": 9, "water": 8})
        self.assertTrue(any(s["role"] == "object" for s in output.segments))
        self.char1.location = self.rooms["support_4f_w1"]
        output = self.command("북 봐")
        self.assertIn("타격교관", output)
        self.assertTrue(any(s["role"] == "npc" for s in output.segments))
        for secret in ("배워", "배분", "재분배", "강타", "Rank", "대화"):
            self.assertNotIn(secret, output)

    def test_preview_changes_no_profile_or_world_state_and_runs_no_local_hooks(self):
        target = self.rooms["trail"]
        self.corpse(target, decay=90)
        enemy = room_enemies(target)[0]
        enemy.db.claim = "player:123"
        enemy.db.combatants = [123]
        enemy.db.contribution = {123: {"damage": 11}}
        box = create_object(Container, key="검증보관상자", location=target)
        box.db.items = {"water": 4}
        before_profile = deepcopy(self.char1.profile())
        objects = [*self.char1.location.contents, *target.contents]
        before = {
            obj.id: [(a.key, deserialize(a.value)) for a in obj.attributes.all()] for obj in objects
        }
        contents = [obj.id for obj in target.contents]
        exit_obj = next(e for e in self.char1.location.exits if e.key == "북")
        self.char1.push_state.reset_mock()
        with (
            patch(
                "world.lifecycle.reconcile_room", side_effect=AssertionError("lifecycle mutation")
            ),
            patch.object(
                target, "return_appearance", side_effect=AssertionError("local appearance")
            ),
            patch.object(exit_obj, "at_desc", side_effect=AssertionError("trigger")),
        ):
            output = self.command("북 봐")
        self.assertIn(target.key, output)
        self.assertEqual(self.char1.profile(), before_profile)
        self.assertEqual([obj.id for obj in target.contents], contents)
        self.assertEqual(
            {
                obj.id: [(a.key, deserialize(a.value)) for a in obj.attributes.all()]
                for obj in objects
            },
            before,
        )
        self.char1.push_state.assert_not_called()

    def test_view_access_and_content_override_are_respected(self):
        target = self.rooms["trail"]
        enemy = room_enemies(target)[0]
        enemy.locks.add("view:false()")
        hidden = create_object(Container, key="숨겨진상자", location=target)
        hidden.db.distant_visible = False
        record = create_object(MaintenanceLog, key="작은종이", location=target)
        output = target.return_distant_appearance(self.context(target))
        for name in (enemy.key, hidden.key, record.key):
            self.assertNotIn(name, output)
        self.assertIn("눈에 띄는 것은 없다", output)
        record.db.distant_visible = True
        self.assertIn(record.key, target.return_distant_appearance(self.context(target)))
        target.locks.add("view:false()")
        with patch.object(
            record, "get_distant_presence", side_effect=AssertionError("hidden room read")
        ):
            output = self.command("북 봐")
        self.assertNotIn(target.key, output)
        self.assertNotIn(record.key, output)

    def test_empty_preview_and_non_exit_context_without_viewer_or_small_items(self):
        room = create_object(ZoneRoom, key="먼관측지")
        room.db.desc = "관측지의 고요한 풍경이다."
        item = create_object(DefaultObject, key="작은물건", location=room)
        output = room.return_distant_appearance(self.context(room, distance=3, via="sensor"))
        self.assertIn(room.db.desc, output)
        self.assertIn("눈에 띄는 것은 없다", output)
        self.assertNotIn(item.key, output)
        self.char1.location = room
        output = room.return_distant_appearance(self.context(room))
        self.assertNotIn("탐사자", output)  # 자신의 존재도 자동 제외한다.
        exit_obj = create_object(Exit, key="위", location=self.rooms["grass"], destination=room)
        self.char1.location = self.rooms["grass"]
        self.assertIn("위쪽으로", exit_obj.return_appearance(self.char1))
        self.assertIn("너머로", direction_phrase("비상통로"))
        self.assertEqual(direction_phrase("밖"), "바깥쪽으로")
        exit_obj.destination = None
        self.assertIn("살펴볼 수 없다", exit_obj.return_appearance(self.char1))

    def test_local_precision_and_action_scope_are_unchanged_after_preview(self):
        target = self.rooms["trail"]
        self.enemy(target)
        self.corpse(target)
        self.corpse(target)
        preview = self.command("북 봐")
        self.assertNotIn("갈퀴사냥룡 2", preview)
        self.assertNotIn(target.db.zone_id, self.char1.profile()["visited"])
        before = self.char1.profile()
        self.command("갈퀴사냥룡 2 때려")
        self.assertEqual(self.char1.profile(), before)
        self.assertTrue(all(not obj.db.combatants for obj in room_enemies(target)))
        self.char1.execute_cmd("북")
        self.assertEqual(self.char1.location, target)
        self.assertIn(target.db.zone_id, self.char1.profile()["visited"])
        output = self.command("보기")
        self.assertIn("'갈퀴사냥룡 2'", output)
        self.assertIn("'시체 2'", output)
        self.assertIn("체력", self.command("갈퀴사냥룡 2 봐"))
        self.assertIn("회수부품", self.command("시체 2 봐"))

    def test_gate_preview_does_not_unlock_or_traverse(self):
        for source, destination, reason in (
            ("marsh", "ridge", "잠긴 진입문"),
            ("ridge", "jungle_edge", "아직 자세히 살펴볼 수 없다"),
            ("jungle_grove", "jungle_gate", "닫힌 출입문"),
        ):
            with self.subTest(destination=destination):
                self.char1.location = self.rooms[source]
                target = self.rooms[destination]
                box = create_object(Container, key="관찰차단상자", location=target)
                box.db.items = {"water": 3}
                self.corpse(target)
                before_profile = deepcopy(self.char1.profile())
                before = {
                    obj.id: [(a.key, deserialize(a.value)) for a in obj.attributes.all()]
                    for obj in target.contents
                }
                with patch.object(
                    target,
                    "return_distant_appearance",
                    side_effect=AssertionError("blocked room read"),
                ):
                    output = self.command("북 봐")
                self.assertIn(reason, output)
                if destination == "jungle_edge":
                    for physical_gate in ("진입문", "출입문", "닫힌 문", "문이 잠겨"):
                        self.assertNotIn(physical_gate, output)
                for secret in (target.key, ROOMS[destination]["desc"], box.key, "시체", "탐사자"):
                    self.assertNotIn(secret, output)
                self.assertFalse(
                    any(
                        s["role"] in ("hostile", "npc", "remains", "player")
                        for s in output.segments
                    )
                )
                requirement = ROOMS[destination]["requires"]
                with patch.object(self.char1, "msg") as message:
                    self.char1.execute_cmd("북")
                message.assert_any_call(requirement["message"])
                self.assertEqual(self.char1.location, self.rooms[source])
                self.assertEqual(self.char1.profile(), before_profile)
                self.char1.change(
                    lambda p: p["quests"][requirement["quest"]].update({requirement["flag"]: True})
                )
                unlocked = deepcopy(self.char1.profile())
                output = self.command("북 봐")
                self.assertIn(target.key, output)
                self.assertIn(ROOMS[destination]["desc"], output)
                self.assertIn(box.key, output)
                self.assertNotIn(requirement["observe_message"], output)
                self.assertEqual(self.char1.profile(), unlocked)
                self.assertEqual(self.char1.location, self.rooms[source])
                self.assertEqual(
                    {
                        obj.id: [(a.key, deserialize(a.value)) for a in obj.attributes.all()]
                        for obj in target.contents
                    },
                    before,
                )
                self.char1.execute_cmd("북")
                self.assertEqual(self.char1.location, target)

    def test_observation_message_is_optional_and_fallback_does_not_read_destination(self):
        self.char1.location = self.rooms["ridge"]
        target = self.rooms["jungle_edge"]
        requirement = dict(ROOMS["jungle_edge"]["requires"])
        requirement.pop("observe_message")
        before = deepcopy(self.char1.profile())
        with (
            patch.dict(ROOMS["jungle_edge"], {"requires": requirement}),
            patch.object(
                target,
                "return_distant_appearance",
                side_effect=AssertionError("blocked room read"),
            ),
        ):
            output = self.command("북 봐")
            self.assertIn("아직 자세히 살펴볼 수 없다", output)
            for secret in (target.key, ROOMS["jungle_edge"]["desc"], "진입문", "닫힌 문"):
                self.assertNotIn(secret, output)
            with patch.object(self.char1, "msg") as message:
                self.char1.execute_cmd("북")
            message.assert_any_call(requirement["message"])
        self.assertEqual(self.char1.profile(), before)
        self.assertEqual(self.char1.location, self.rooms["ridge"])

    def test_observation_override_keeps_entry_locked_and_respects_room_access(self):
        self.char1.location = self.rooms["marsh"]
        exit_obj = next(e for e in self.char1.location.exits if e.key == "북")
        target = self.rooms["ridge"]
        before = deepcopy(self.char1.profile())
        exit_obj.db.blocks_distant_view = False
        self.assertIn(target.key, self.command("북 봐"))
        self.char1.execute_cmd("북")
        self.assertEqual(self.char1.location, self.rooms["marsh"])
        self.assertEqual(self.char1.profile(), before)
        target.locks.add("view:false()")
        self.assertNotIn(target.key, self.command("북 봐"))
        self.assertEqual(self.char1.profile(), before)

    def test_gate_observation_uses_readonly_profile_snapshot_including_legacy_progress(self):
        self.char1.location = self.rooms["marsh"]
        legacy = rules.new_profile()
        legacy.update(version=3, generator_fixed=False, quest_claimed=False)
        legacy.pop("quests")
        legacy.pop("storage")
        self.char1.db.profile = legacy
        with patch.object(
            self.char1, "profile", side_effect=AssertionError("profile migration write")
        ):
            self.assertIn("진입문에 막혀", self.command("북 봐"))
        self.assertEqual(deserialize(self.char1.db.profile), legacy)
        legacy["generator_fixed"] = True
        self.char1.db.profile = legacy
        with patch.object(
            self.char1, "profile", side_effect=AssertionError("profile migration write")
        ):
            self.assertIn(self.rooms["ridge"].key, self.command("북 봐"))
        self.assertEqual(deserialize(self.char1.db.profile), legacy)

    def test_action_objects_are_hidden_by_default_and_current_opt_ins_are_explicit(self):
        from typeclasses import interactables

        room = self.rooms["office"]
        generic = create_object(interactables.ActionObject, key="새비밀장치", location=room)
        context = self.context(room)
        self.assertFalse(generic.is_distant_visible(context))
        self.assertNotIn(generic.key, room.return_distant_appearance(context))
        generic.db.distant_visible = True
        self.assertIn(generic.key, room.return_distant_appearance(context))
        visible = {
            "Commander",
            "TrainingManager", "SkillTrainer", "AttributeTrainer",
            "Pathfinder",
            "Container",
            "PersonalLocker",
            "Generator",
            "SignalDevice",
        }
        for definition in interactables.INTERACTABLES.values():
            cls = getattr(interactables, definition["typeclass"])
            obj = create_object(cls, key=definition["name"], location=room)
            self.assertEqual(
                bool(obj.is_distant_visible(context)), cls.__name__ in visible, cls.__name__
            )

    def test_enemy_local_and_distant_metadata_survive_alive_to_corpse_transition(self):
        room = self.rooms["jungle_road"]
        self.char1.location = room
        self.enemy(room, "shellback")
        enemies = room_enemies(room)
        definition = ENEMIES["shellback"]
        local = self.command("보기")
        remote = room.return_distant_appearance(self.context(room))
        self.assertIn("철갑등짐승 두 마리", local)
        self.assertIn(definition["presence"], local)
        self.assertIn(definition["distant_presence"], remote)
        self.assertNotIn(definition["presence"], remote)
        self.assertIn("옛 도로", ROOMS["jungle_road"]["desc"])
        self.assertNotIn("짐승이 천천히 움직인다", ROOMS["jungle_road"]["desc"])
        for enemy in enemies:
            enemy.db.hp = 0
            enemy.db.state = "respawning"
            enemy.db.respawn_at = 200
        corpse = create_object(Corpse, key="철갑등짐승의 시체", location=room)
        corpse.db.decay_at = 130
        corpse.db.entries = []
        local = self.command("보기")
        remote = room.return_distant_appearance(self.context(room))
        for output in (local, remote):
            self.assertIn(corpse.key, output)
            self.assertIn(ROOMS["jungle_road"]["desc"], output)
            self.assertFalse(any(s["role"] == "hostile" for s in output.segments))
            self.assertNotIn(definition["presence"], output)
            self.assertNotIn(definition["distant_presence"], output)
