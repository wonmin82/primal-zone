"""정적 선언과 공식 전투 Narration의 한국어 문장 계약."""

from dataclasses import FrozenInstanceError, replace
from unittest import TestCase

from world import combat_narration as narration
from world.actions.schema import ArgumentDefinition
from world.actors.hostile_content import HOSTILE_ACTORS
from world.actors.schema import AttackPhrase, CapabilityDescriptor, CombatNarrationSpec
from world.actors.validation import ActorDefinitionError, validate_definitions
from world.content import ITEMS
from world.content.final_items import BAREHAND_NARRATION
from world.content.integrity import item_attack_narration_errors
from world.equipment import item_snapshot

WEAPON_SENTENCES = {
    "explorer_machete": (
        ("탐사용 벌목도로 어린청소룡을 베었다.", "탐사용 벌목도로 어린청소룡을 크게 베었다."),
        ("탐사용 벌목도로 어린청소룡을 내리쳤다.", "탐사용 벌목도로 어린청소룡을 힘껏 내리쳤다."),
    ),
    "cutting_machete": (
        ("절단마체테로 어린청소룡을 베었다.", "절단마체테로 어린청소룡을 깊게 베었다."),
        ("절단마체테로 어린청소룡을 가로베었다.", "절단마체테로 어린청소룡을 세차게 가로베었다."),
    ),
    "pioneer_spear": (
        ("개척창으로 어린청소룡을 찔렀다.", "개척창으로 어린청소룡을 깊게 찔렀다."),
    ),
    "jungle_longblade": (
        ("정글장도로 어린청소룡을 베었다.", "정글장도로 어린청소룡을 크게 베었다."),
        ("정글장도로 어린청소룡을 가로베었다.", "정글장도로 어린청소룡을 세차게 가로베었다."),
    ),
    "shattering_spear": (
        ("파쇄창으로 어린청소룡을 찔렀다.", "파쇄창으로 어린청소룡을 힘껏 찔렀다."),
    ),
    "scout_pistol": (
        ("정찰권총으로 어린청소룡을 쏘았다.", "정찰권총으로 어린청소룡을 쏘았다."),
        ("정찰권총으로 어린청소룡을 사격했다.", "정찰권총으로 어린청소룡을 사격했다."),
    ),
    "tactical_pistol": (
        ("전술권총으로 어린청소룡을 사격했다.", "전술권총으로 어린청소룡을 사격했다."),
        ("전술권총으로 어린청소룡을 쏘았다.", "전술권총으로 어린청소룡을 쏘았다."),
    ),
    "guard_carbine": (
        ("경비카빈으로 어린청소룡을 사격했다.", "경비카빈으로 어린청소룡을 사격했다."),
        ("경비카빈으로 어린청소룡을 쏘았다.", "경비카빈으로 어린청소룡을 쏘았다."),
    ),
    "exploration_carbine": (
        ("탐사카빈으로 어린청소룡을 쏘았다.", "탐사카빈으로 어린청소룡을 쏘았다."),
        ("탐사카빈으로 어린청소룡을 사격했다.", "탐사카빈으로 어린청소룡을 사격했다."),
    ),
    "heavy_rifle": (
        ("중량소총으로 어린청소룡을 사격했다.", "중량소총으로 어린청소룡을 사격했다."),
        ("중량소총으로 어린청소룡을 쏘았다.", "중량소총으로 어린청소룡을 쏘았다."),
    ),
}

ACTOR_SENTENCES = {
    "scavenger": ("어린청소룡이 날카로운 이빨로 당신을 물었다.",
                  "어린청소룡이 날카로운 이빨로 당신을 세게 물었다."),
    "hunter": ("갈퀴사냥룡이 날카로운 발톱으로 당신을 할퀴었다.",
               "갈퀴사냥룡이 날카로운 발톱으로 당신을 깊게 할퀴었다."),
    "sentinel": ("고장난경비기가 금속 몸체로 당신을 들이받았다.",
                 "고장난경비기가 금속 몸체로 당신을 거칠게 들이받았다."),
    "alpha": ("능선의우두머리가 거대한 몸으로 당신을 덮쳤다.",
              "능선의우두머리가 거대한 몸으로 당신을 거세게 덮쳤다."),
    "dartclaw": ("날쌘발톱룡이 날카로운 발톱으로 당신을 할퀴었다.",
                 "날쌘발톱룡이 날카로운 발톱으로 당신을 거세게 할퀴었다."),
    "shellback": ("철갑등짐승이 육중한 몸으로 당신을 들이받았다.",
                  "철갑등짐승이 육중한 몸으로 당신을 강하게 들이받았다."),
    "stalker": ("그늘추적룡이 날카로운 이빨로 당신을 물었다.",
                "그늘추적룡이 날카로운 이빨로 당신을 깊게 물었다."),
    "jungle_apex": ("밀림의포식자가 거대한 발톱으로 당신을 할퀴었다.",
                    "밀림의포식자가 거대한 발톱으로 당신을 깊게 할퀴었다."),
}


class AttackNarrationTests(TestCase):
    def test_actor_narration_is_required_and_immutable_for_combat(self):
        base = HOSTILE_ACTORS["scavenger"]
        actor = replace(base, profiles={"combat": {"hp": 24}})
        capability = CapabilityDescriptor("combat", ("combat",), (("combat", (ArgumentDefinition("hp", int),)),))
        caps = {"combat": capability}
        validate_definitions((actor,), caps)
        validate_definitions((replace(actor, capabilities=(), profiles={}, defaults={}, combat_narration=None),), caps)
        phrase = actor.combat_narration.normal_attacks[0]
        with self.assertRaises(FrozenInstanceError):
            phrase.verb = "때렸다"
        with self.assertRaises(FrozenInstanceError):
            actor.combat_narration.normal_attacks = ()

        for invalid in (None, {"normal_attacks": (phrase,)}, CombatNarrationSpec(()),
                        CombatNarrationSpec([phrase]), CombatNarrationSpec((phrase, phrase)),
                        CombatNarrationSpec((("이빨", "물었다", "물었다"),)),
                        CombatNarrationSpec((replace(phrase, instrument=5),)),
                        CombatNarrationSpec((replace(phrase, instrument="날카로운 발톱으로"),)),
                        CombatNarrationSpec((replace(phrase, instrument="날카로운 이빨로"),)),
                        CombatNarrationSpec((replace(phrase, instrument="금속 몸체로"),)),
                        CombatNarrationSpec((replace(phrase, instrument="쇠이빨로"),)),
                        CombatNarrationSpec((replace(phrase, instrument="금속몸체로"),)),
                        CombatNarrationSpec((replace(phrase, instrument="날카로운 꼬리로"),)),
                        CombatNarrationSpec((replace(phrase, instrument="날카로운 꼬리 로"),)),
                        CombatNarrationSpec((replace(phrase, instrument="등의 가시로"),)),
                        CombatNarrationSpec((replace(phrase, instrument="이빨!"),)),
                        CombatNarrationSpec((replace(phrase, verb=""),)),
                        CombatNarrationSpec((replace(phrase, verb="달렸다"),)),
                        CombatNarrationSpec((replace(phrase, verb="당신을 물었다"),)),
                        CombatNarrationSpec((replace(phrase, verb="물었다!"),)),
                        CombatNarrationSpec((replace(phrase, verb="쓰러졌다"),)),
                        CombatNarrationSpec((replace(phrase, strong_verb="거세게 공격당했다"),)),
                        CombatNarrationSpec((replace(phrase, verb="구타당했다"),)),
                        CombatNarrationSpec((replace(phrase, strong_verb=None),))):
            with self.subTest(invalid=invalid), self.assertRaises(ActorDefinitionError):
                validate_definitions((replace(actor, combat_narration=invalid),), caps)

        for valid, expected in (
            (AttackPhrase("고압 회로", "지졌다", "세게 지졌다"),
             ("어린청소룡이 고압 회로로 당신을 지졌다.", "어린청소룡이 고압 회로로 당신을 세게 지졌다.")),
            (AttackPhrase("휴대 화로", "그을렸다", "깊게 그을렸다"),
             ("어린청소룡이 휴대 화로로 당신을 그을렸다.", "어린청소룡이 휴대 화로로 당신을 깊게 그을렸다.")),
        ):
            with self.subTest(valid=valid):
                validate_definitions((replace(actor, combat_narration=CombatNarrationSpec((valid, phrase))),), caps)
                self.assert_attack_messages(
                    lambda damage: narration.incoming(actor.name, CombatNarrationSpec((valid,)), False, damage, 40, 1),
                    expected, (valid.verb, valid.strong_verb), ("hostile", "text"), incoming=True,
                )

    def test_invalid_item_declarations_are_rejected_by_role_and_shape(self):
        weapon = {"equipment_properties": {"slot": "hands", "role": "weapon"}}
        phrase = {"verb": "쏘았다", "strong_verb": "쏘았다"}
        valid = {"normal": (phrase,)}
        self.assertEqual(item_attack_narration_errors("weapon", {**weapon, "combat_narration": valid}), [])
        self.assertTrue(item_attack_narration_errors("weapon", weapon))
        for invalid in (
            None, {}, {"normal": ()}, {"normal": [phrase]}, {"normal": (phrase, phrase)},
            {"normal": (("쏘았다", "쏘았다"),)}, {"normal": ({"verb": "쏘았다"},)},
            {"normal": ({**phrase, "extra": "쏘았다"},)}, {**valid, "special": None},
            *({"normal": ({**phrase, "strong_verb": value},)} for value in (
                1, "", " 쏘았다", "크게  쏘았다", "크게\t쏘았다", "쏘았다!", "쏜다",
                "총탄을 발사했다", "방아쇠를 당겼다", "쏘았다 적을", "쓰러졌다", "공격당했다", "빠르게 달렸다",
                "거세게 제압당했다", "폭행당했다",
            )),
        ):
            with self.subTest(invalid=invalid):
                self.assertTrue(item_attack_narration_errors("weapon", {**weapon, "combat_narration": invalid}))
        for identity in ("folding_shield", "portable_analyzer", "expedition_workwear", "bandage"):
            with self.subTest(identity=identity):
                definition = ITEMS[identity]
                self.assertEqual(item_attack_narration_errors(identity, definition), [])
                self.assertTrue(item_attack_narration_errors(identity, {**definition, "combat_narration": valid}))

    def assert_attack_messages(self, render, expected, verbs, prefix_roles, *, incoming=False):
        normal, heavy = verbs
        expected_attacks = (*expected, expected[1].removesuffix(".") + "!")
        tail_roles = (("combat_verb_incoming", "text", "damage_taken", "text") if incoming else
                      ("combat_verb_outgoing", "text", "damage_dealt", "text"))
        ending = "를 입었다." if incoming else "를 입혔다."
        for damage, expected_attack, verb, end in zip((5, 6, 12), expected_attacks, (normal, heavy, heavy),
                                                     (".", ".", "!"), strict=True):
            message = render(damage)
            self.assertEqual(message, f"{expected_attack} {damage} 피해{ending}")
            self.assertEqual(tuple(part["role"] for part in message.segments), (*prefix_roles, *tail_roles))
            self.assertEqual(tuple(part["text"] for part in message.segments[-4:]),
                             (verb + end, " ", f"{damage} 피해", ending))

    def test_weapon_and_barehand_sentence_snapshots(self):
        weapons = {identity: data for identity, data in ITEMS.items()
                   if data.get("equipment_properties", {}).get("role") == "weapon"}
        self.assertEqual(weapons.keys(), WEAPON_SENTENCES.keys())
        target = HOSTILE_ACTORS["scavenger"].name
        cases = [(item_snapshot(identity, data), data["combat_narration"], WEAPON_SENTENCES[identity])
                 for identity, data in weapons.items()]
        cases.append((None, BAREHAND_NARRATION, (
            ("맨손으로 어린청소룡을 때렸다.", "맨손으로 어린청소룡을 세게 때렸다."),
            ("맨손으로 어린청소룡을 후려쳤다.", "맨손으로 어린청소룡을 힘껏 후려쳤다."),
        )))
        for weapon, spec, expected in cases:
            with self.subTest(weapon=weapon):
                prefix_roles = ("text" if weapon is None else "item", "text", "hostile", "text")
                for index, (phrase, snapshot) in enumerate(zip(spec["normal"], expected, strict=True), 1):
                    self.assert_attack_messages(
                        lambda damage: narration.outgoing(target, weapon, {"action": "attack"}, damage, 40, index),
                        snapshot, (phrase["verb"], phrase["strong_verb"]), prefix_roles,
                    )
                repeated_first = narration.outgoing(target, weapon, {"action": "attack"}, 5, 40, len(expected) + 1)
                self.assertEqual(repeated_first, f"{expected[0][0]} 5 피해를 입혔다.")

        firearm = item_snapshot("guard_carbine", weapons["guard_carbine"])
        message = narration.outgoing("고장난경비기", firearm, {"action": "attack"}, 10, 30, 2)
        self.assertEqual(message, "경비카빈으로 고장난경비기를 쏘았다! 10 피해를 입혔다.")
        self.assertEqual(tuple((part["role"], part["text"]) for part in message.segments),
                         (("item", "경비카빈"), ("text", "으로 "), ("hostile", "고장난경비기"), ("text", "를 "),
                          ("combat_verb_outgoing", "쏘았다!"), ("text", " "), ("damage_dealt", "10 피해"),
                          ("text", "를 입혔다.")))

    def test_actor_sentence_snapshots_without_special_profile_duplication(self):
        self.assertEqual(HOSTILE_ACTORS.keys(), ACTOR_SENTENCES.keys())
        for identity, actor in HOSTILE_ACTORS.items():
            with self.subTest(identity=identity):
                spec = actor.combat_narration
                phrase, = spec.normal_attacks
                self.assertNotIn("special_verb", actor.profiles["combat"])
                self.assertNotIn("telegraph", actor.profiles["combat"])
                self.assert_attack_messages(
                    lambda damage: narration.incoming(actor.name, spec, False, damage, 40, 1),
                    ACTOR_SENTENCES[identity], (phrase.verb, phrase.strong_verb), ("hostile", "text"), incoming=True,
                )

        hunter = HOSTILE_ACTORS["hunter"]
        message = narration.incoming(hunter.name, hunter.combat_narration, False, 6, 60, 1)
        self.assertEqual(tuple((part["role"], part["text"]) for part in message.segments),
                         (("hostile", "갈퀴사냥룡"), ("text", "이 날카로운 발톱으로 당신을 "),
                          ("combat_verb_incoming", "할퀴었다."), ("text", " "),
                          ("damage_taken", "6 피해"), ("text", "를 입었다.")))
