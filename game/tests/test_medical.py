"""실제 의료 객체·관찰·명령·복귀와 원자적 패배 lifecycle."""

from copy import deepcopy
from random import Random
from unittest.mock import Mock, patch

from evennia import create_object, search_tag
from evennia.objects.models import ObjectDB
from evennia.utils.dbserialize import deserialize
from typeclasses.enemies import room_enemies
from typeclasses.explorers import Explorer
from typeclasses.interactables import INTERACTABLES, Bed, Doctor
from world import rules
from world.bootstrap import build_world, stale_definitions
from world.content import ROOMS
from world.content.integrity import errors
from world.observation import context_for
from world.room_hints import render
from world.state import multiplayer_state

from tests.base import WorldCommandTest


class MedicalCommandsTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        super().setUp()
        self.rooms = self.world_rooms()
        self.doctor = search_tag("doctor", category="primal_interactable")[0]
        self.bed = search_tag("infirmary_bed", category="primal_interactable")[0]
        for player in (self.char1, self.char2):
            player.location = self.rooms["infirmary"]
            player.home = self.rooms["dock"]
            player.push_state = Mock()
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))

    def command(self, value):
        with patch.object(self.char1, "msg") as output:
            self.char1.execute_cmd(value)
        return str(output.call_args_list)

    def test_bare_targeted_particles_alias_and_independent_rules(self):
        for raw in ("진료", "의무관 진료", "의무관에게 진료", "의사에게 진료", "의사 treat",
                    "휴식", "침대 휴식", "침대에서 휴식", "병상에서 휴식", "병상 rest"):
            with self.subTest(command=raw):
                self.char1.change(lambda p: p.update(hp=1))
                before = deepcopy(self.char1.profile())
                other = "rest" if "진료" in raw or "treat" in raw else "treat"
                with patch.object(rules, other) as separate, patch.object(rules, "first_aid") as bandage:
                    self.assertIn("체력을 모두 회복" if other == "rest" else "체력과 정신력을 모두 회복", self.command(raw))
                    separate.assert_not_called()
                    bandage.assert_not_called()
                before["hp"] = rules.stats(before)["max_hp"]
                self.assertEqual(self.char1.profile(), before)

    def test_full_hp_and_combat_rejections_preserve_saved_profile(self):
        for target in (None, 999):
            self.char1.change(lambda p: p.update(combat_target=target))
            before = deepcopy(self.char1.profile())
            for raw in ("진료", "침대 휴식"):
                expected = "전투 중입니다" if target else "이미 체력이 가득" if raw == "진료" else "이미 체력과 정신력이 가득"
                self.assertIn(expected, self.command(raw))
                self.assertEqual(self.char1.profile(), before)
            if target:
                self.assertTrue(all(not obj["actions"] for obj in multiplayer_state(self.char1)["interactables"]))
                self.assertEqual(render(context_for(self.char1)), "")

    def test_bare_ambiguity_hidden_objects_and_explicit_selector(self):
        for cls, original, action in ((Doctor, self.doctor, "진료"), (Bed, self.bed, "휴식")):
            extra = create_object(cls, key=original.key, location=self.char1.location)
            self.char1.change(lambda p: p.update(hp=1))
            before = deepcopy(self.char1.profile())
            self.assertIn("대상이 여러 개", self.command(action))
            self.assertEqual(self.char1.profile(), before)
            self.command(f"{original.key} 2 {action}")
            self.assertEqual(self.char1.profile()["hp"], 60)
            extra.locks.add("view:false()")
            self.char1.change(lambda p: p.update(hp=1))
            self.command(action)
            self.assertEqual(self.char1.profile()["hp"], 60)
            extra.delete()

    def test_hidden_and_removed_medical_objects_are_not_services_or_hints(self):
        self.char1.change(lambda p: p.update(hp=1))
        for obj, action in ((self.doctor, "진료"), (self.bed, "휴식")):
            obj.locks.add("view:false()")
            before = deepcopy(self.char1.profile())
            for raw in (action, f"{obj.key} {action}"):
                self.assertIn("대상", self.command(raw))
                self.assertEqual(self.char1.profile(), before)
            self.assertNotIn(obj.key, str(multiplayer_state(self.char1)["interactables"]))
            self.assertNotIn(action, render(context_for(self.char1)))
        self.doctor.locks.add("view:all()")
        self.bed.locks.add("view:all()")
        self.doctor.location = self.rooms["support_roof"]
        self.bed.location = self.rooms["support_roof"]
        for action in ("진료", "휴식"):
            self.assertIn("이용할 대상을 찾지", self.command(action))
        self.assertEqual(multiplayer_state(self.char1)["interactables"], [])
        self.assertEqual(render(context_for(self.char1)), "")

    def test_services_follow_actual_object_to_safe_room_and_reject_unsafe(self):
        for zone in ("storage_room", "grass"):
            self.char1.location = self.rooms[zone]
            self.doctor.location = self.char1.location
            self.bed.location = self.char1.location
            for action in ("진료", "휴식"):
                self.char1.change(lambda p: p.update(hp=1))
                before = deepcopy(self.char1.profile())
                with patch("world.observation.can_perceive", return_value=True):
                    output = self.command(action)
                    services = [obj for obj in multiplayer_state(self.char1)["interactables"]
                                if obj["name"] in ("의무관", "침대")]
                if ROOMS[zone].get("safe", False):
                    self.assertEqual(self.char1.profile()["hp"], 60)
                    self.assertTrue(all(obj["actions"] for obj in services))
                else:
                    self.assertIn("안전한 곳", output)
                    self.assertEqual(self.char1.profile(), before)
                    self.assertTrue(all(not obj["actions"] for obj in services))

    def test_web_presentation_and_distant_privacy_use_real_objects(self):
        state = multiplayer_state(self.char1)
        self.assertEqual({action["command"] for obj in state["interactables"] for action in obj["actions"]},
                         {"의무관 진료", "침대 휴식"})
        self.assertEqual(render(context_for(self.char1)), "의무관 진료 · 침대 휴식")
        appearance = str(self.char1.location.return_appearance(self.char1))
        self.assertIn("의무관", appearance)
        self.assertIn("침대", appearance)
        self.char1.location = self.rooms["support_2f_w1"]
        distant = self.command("북 보기")
        self.assertNotIn("의무관 진료", distant)
        self.assertNotIn("침대 휴식", distant)
        self.char1.location = self.rooms["dock"]
        before = deepcopy(self.char1.profile())
        for raw in ("휴식", "진료"):
            self.assertIn("이용할 대상을 찾지", self.command(raw))
            self.assertEqual(self.char1.profile(), before)
        self.assertEqual({obj["name"] for obj in multiplayer_state(self.char1)["interactables"]}, {"윤대장"})
        self.assertEqual(render(context_for(self.char1)), "윤대장 대화")

    def test_return_roof_elevator_medical_supply_purchase_and_expedition_paths(self):
        self.char1.location = self.rooms["grass"]
        self.command("귀환")
        self.assertEqual(self.char1.zone, "support_roof")
        self.assertEqual(self.char1.home, self.rooms["dock"])
        for raw in ("승강기", "2층", "서", "북"):
            self.command(raw)
        self.assertEqual(self.char1.zone, "infirmary")
        self.char1.change(lambda p: p.update(hp=1))
        self.command("휴식")
        self.assertEqual(self.char1.profile()["hp"], 60)
        for raw in ("남", "동", "승강기", "1층", "동", "북"):
            self.command(raw)
        self.assertEqual(self.char1.zone, "supply_shop")
        self.command("붕대 구매")
        self.assertEqual(self.char1.profile()["inventory"]["bandage"], 4)
        for raw in ("남", "서", "북", "서", "북"):
            self.command(raw)
        self.assertEqual(self.char1.zone, "grass")
        self.char1.change(lambda p: p.update(combat_target=999))
        before = deepcopy(self.char1.profile())
        self.assertIn("전투 중입니다", self.command("귀환"))
        self.assertEqual(self.char1.zone, "grass")
        self.assertEqual(self.char1.profile(), before)

    def test_bootstrap_medical_identity_aliases_and_integrity(self):
        count = ObjectDB.objects.count()
        for _ in range(2):
            build_world()
            self.assertEqual(ObjectDB.objects.count(), count)
            for identity, obj in (("doctor", self.doctor), ("infirmary_bed", self.bed)):
                current = search_tag(identity, category="primal_interactable")
                self.assertEqual([o.id for o in current], [obj.id])
                self.assertEqual(current[0].location, self.rooms["infirmary"])
                self.assertEqual(current[0].aliases.all(), INTERACTABLES[identity]["aliases"])
        self.assertEqual(stale_definitions(), [])
        self.assertEqual(errors(INTERACTABLES), [])
        for identity in ("doctor", "infirmary_bed"):
            for change in ({"room": "dock"}, {"actions": ("대화",)}):
                with patch.dict(INTERACTABLES[identity], change):
                    self.assertTrue(any(identity in issue for issue in errors(INTERACTABLES)))


class MedicalDefeatTests(WorldCommandTest):
    character_typeclass = Explorer

    def setUp(self):
        self.enterContext(patch("typeclasses.explorers.time", return_value=100))
        super().setUp()
        self.rooms = self.world_rooms()
        for player in (self.char1, self.char2):
            player.location = self.rooms["ridge"]
            player.home = self.rooms["dock"]
            player.push_state = Mock()
            self.enterContext(patch.object(player.sessions, "count", return_value=1))
        for module in ("enemies", "explorers", "loot"):
            self.enterContext(patch(f"typeclasses.{module}.delay"))
        self.enemy = room_enemies(self.char1.location)[0]

    def prepare(self):
        self.char1.change(lambda p: p.update(hp=1, credits=50, storage={"bandage": 2}))
        self.enemy.engage(self.char1, now=100)
        self.enemy.engage(self.char2, now=100)
        self.enemy.db.threat = {self.char1.id: 10, self.char2.id: 1}
        self.enemy.db.contribution = {self.char1.id: {"damage": 10}, self.char2.id: {"damage": 1}}
        self.char1.ndb.combat_task = Mock()

    def test_defeat_is_minimal_preserves_progress_and_other_combatants(self):
        self.prepare()
        before = deepcopy(self.char1.profile())
        other = deepcopy(self.char2.profile())
        enemy_hp = self.enemy.db.hp
        task = self.char1.ndb.combat_task
        with patch.object(rules, "treat") as treat, patch.object(rules, "rest") as rest:
            self.enemy.enemy_tick(now=102.5, rng=Random(1))
            treat.assert_not_called()
            rest.assert_not_called()
        self.assertEqual(self.char1.zone, "infirmary")
        self.assertEqual(self.char1.home, self.rooms["dock"])
        before.update(hp=rules.DEFEAT_RECOVERY_HP, credits=40, combat_target=None, queued_action="attack", guard_until=0)
        before["visited"].append("infirmary")
        before["recovery"]["updated_at"] = 102.5
        self.assertEqual(self.char1.profile(), before)
        task.remove.assert_called_once()
        self.assertIsNone(self.char1.ndb.combat_task)
        self.assertNotIn(self.char1.id, self.enemy.db.combatants)
        self.assertNotIn(self.char1.id, self.enemy.db.threat)
        self.assertNotIn(self.char1.id, self.enemy.db.contribution)
        self.assertIn(self.char2.id, self.enemy.db.combatants)
        self.assertEqual(self.char2.profile(), other)
        self.assertEqual(self.enemy.db.hp, enemy_hp)
        self.enemy.enemy_tick(now=105, rng=Random(1))
        self.assertLess(self.char2.profile()["hp"], other["hp"])

    def test_failed_move_rolls_back_damage_penalty_membership_profile_and_callbacks(self):
        for partial_move in (False, True):
            self.prepare()
            before = deepcopy(self.char1.profile())
            enemy_before = {key: deserialize(self.enemy.attributes.get(key))
                            for key in ("combatants", "threat", "contribution", "enemy_round", "next_attack_at")}
            original = self.char1.move_to

            def fail(destination, **kwargs):
                if partial_move:
                    original(destination, **kwargs)
                return False

            self.char1.push_state.reset_mock()
            task = self.char1.ndb.combat_task
            with patch.object(self.char1, "move_to", side_effect=fail), patch.object(self.char1, "msg") as output:
                with self.assertRaises(RuntimeError):
                    self.enemy.enemy_tick(now=102.5, rng=Random(1))
                self.assertNotIn("구조했습니다", str(output.call_args_list))
            self.assertEqual(self.char1.profile(), before)
            self.assertEqual(deserialize(self.char1.db.profile), before)
            self.assertEqual(self.char1.location, self.rooms["ridge"])
            self.assertEqual(ObjectDB.objects.get(pk=self.char1.pk).db_location_id, self.rooms["ridge"].pk)
            self.assertIn(self.char1, self.rooms["ridge"].contents)
            self.assertNotIn(self.char1, self.rooms["infirmary"].contents)
            for key, value in enemy_before.items():
                self.assertEqual(deserialize(self.enemy.attributes.get(key)), value)
            task.remove.assert_not_called()
            self.char1.push_state.assert_not_called()

    def test_defeat_pushes_infirmary_state_and_zero_loss_message_is_natural(self):
        self.prepare()
        self.char1.change(lambda p: p.update(credits=0))
        self.char1.push_state = lambda: Explorer.push_state(self.char1, observed_at=102.5)
        with patch.object(self.char1, "msg") as output:
            self.enemy.enemy_tick(now=102.5, rng=Random(1))
        payloads = [call.kwargs["pz_state"][0][0] for call in output.call_args_list if "pz_state" in call.kwargs]
        self.assertTrue(payloads)
        self.assertTrue(all((s["zone"], s["hp"], s["combat_target"]) == ("infirmary", rules.DEFEAT_RECOVERY_HP, None)
                            for s in payloads))
        self.assertNotIn("0칩을 잃", str(output.call_args_list))
        self.char2.push_state.assert_called()
