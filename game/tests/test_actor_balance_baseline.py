"""전환 전 main에서 확보한 8종·15 Spawn·고정 RNG 결과의 Golden 기준선."""

import json
from dataclasses import replace
from pathlib import Path
from random import Random
from unittest import TestCase

from world import rules
from world.actors.content import ACTOR_SPAWNS, ACTORS, CAPABILITIES
from world.actors.spawn import ensure_spawn
from world.actors.validation import ActorDefinitionError, validate_definitions
from world.bootstrap import CATEGORY
from world.combat_contracts import Combatant
from world.content import ENEMIES, ROOMS, spawn_id_for
from world.multiplayer import world_change

from tests.base import GameCommandTest


class ActorBalanceBaselineTests(TestCase):
    def test_original_content_spawns_and_fixed_rng_combat_are_preserved(self):
        baseline = json.loads((Path(__file__).parent / "fixtures" / "actor_v16_baseline.json").read_text(encoding="utf-8"))
        # 과거 기준선은 보존하고 이번에 Actor Narration으로 옮긴 표현 필드만 비교에서 제외한다.
        former_profile_text = {"special_verb", "telegraph"}
        expected_enemies = {
            identity: {key: value for key, value in profile.items() if key not in former_profile_text}
            for identity, profile in baseline["enemies"].items()
        }
        self.assertEqual(ENEMIES, expected_enemies)
        hostiles = {actor.id: actor for actor in ACTORS.values() if "combat" in actor.capabilities}
        self.assertEqual(set(hostiles), set(ENEMIES))
        self.assertEqual(validate_definitions(ACTORS, CAPABILITIES, ACTOR_SPAWNS, room_ids=ROOMS), ACTORS)
        self.assertEqual({actor.id: actor.level for actor in hostiles.values()}, {
            "scavenger": 1, "hunter": 2, "sentinel": 3, "alpha": 4,
            "dartclaw": 5, "shellback": 6, "stalker": 7, "jungle_apex": 10,
        })
        self.assertEqual({actor.id for actor in ACTORS.values() if actor.classification == "machine"},
                         {"sentinel"})
        for actor in hostiles.values():
            self.assertEqual(actor.defaults["combat_state"]["hp"], ENEMIES[actor.id]["hp"])
        spawns = {spawn_id_for(zone, enemy): {"room": zone, "enemy_id": enemy}
                  for zone, room in ROOMS.items() for enemy in room.get("enemies", ())}
        self.assertEqual(spawns, baseline["spawns"])
        self.assertEqual({spawn.id: {"room": spawn.room_id, "enemy_id": spawn.actor_id}
                          for spawn in ACTOR_SPAWNS.values() if spawn.actor_id in hostiles}, baseline["spawns"])
        for enemy, expected in baseline["fixed_rng_84"].items():
            with self.subTest(enemy=enemy):
                damage, outcome = rules.player_attack(rules.new_profile(), enemy, 100, 2.5, rng=Random(84))
                self.assertEqual([damage, outcome], expected["player"])
                self.assertEqual(rules.enemy_attack(rules.new_profile(), enemy, 1, 100, rng=Random(84)), expected["enemy"])

    def test_special_period_requires_static_phrase_and_telegraph(self):
        for identity in ("alpha", "jungle_apex"):
            actor = ACTORS[identity]
            spec = actor.combat_narration
            for field in ("special_attack", "telegraph"):
                with self.subTest(actor=identity, field=field), self.assertRaisesRegex(
                    ActorDefinitionError, "특수 공격 주기에는 공격 문구와 예고가 필요합니다",
                ):
                    broken = replace(actor, combat_narration=replace(spec, **{field: None}))
                    validate_definitions((broken,), CAPABILITIES)
            for legacy_field in ("special_verb", "telegraph"):
                profile = {**actor.profiles["combat"], legacy_field: "구형 문구"}
                with self.subTest(actor=identity, field=legacy_field), self.assertRaisesRegex(
                    ActorDefinitionError, "미선언 Profile 설정",
                ):
                    validate_definitions((replace(actor, profiles={"combat": profile}),), CAPABILITIES)


class HostileActorSpawnTests(GameCommandTest):
    def test_registered_hostile_spawn_preserves_identity_and_combat_state(self):
        spawn = next(spawn for spawn in ACTOR_SPAWNS.values() if spawn.actor_id == "scavenger")
        self.room1.db.zone_id = spawn.room_id
        self.room1.tags.add(spawn.room_id, category=CATEGORY)

        actor = ensure_spawn(spawn, self.room1)
        combatant = Combatant(actor)
        self.assertEqual((actor.hp, actor.max_hp), (24, 24))
        with world_change():
            combatant.apply(lambda state: state.update(hp=7))
            actor.location = self.room2

        restored = ensure_spawn(spawn, self.room1)
        self.assertEqual(restored.pk, actor.pk)
        self.assertEqual(restored.location, self.room2)
        self.assertEqual((restored.hp, restored.max_hp), (7, 24))
        self.assertFalse(restored.attributes.has("hp"))
