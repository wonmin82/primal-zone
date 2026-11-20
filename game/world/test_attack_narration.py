"""PR-A 정적 선언과 테스트 전용 한국어 문장 미리보기."""

from dataclasses import FrozenInstanceError, replace
from unittest import TestCase

from world import text as ft
from world.actions.schema import ArgumentDefinition
from world.actors.hostile_content import HOSTILE_ACTORS
from world.actors.schema import AttackPhrase, CapabilityDescriptor, CombatNarrationSpec
from world.actors.validation import ActorDefinitionError, validate_definitions
from world.content import ITEMS
from world.content.final_items import BAREHAND_NARRATION
from world.content.integrity import item_attack_narration_errors

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


def player_prefix(name, target, *, barehand=False):
    return (
        ("text" if barehand else "item", name),
        ("text", f"{ft.particle(name, '으로/로')} "),
        ("hostile", target),
        ("text", f"{ft.particle(target, '을/를')} "),
    )


def actor_prefix(name, instrument):
    return (
        ("hostile", name),
        ("text", f"{ft.particle(name, '이/가')} {instrument}{ft.particle(instrument, '으로/로')} 당신을 "),
    )


def attack_preview(prefix, verb, punctuation, damage, *, incoming):
    """문장과 의미 범위를 고정하는 테스트 조합. 공식 Text 역할을 등록하지 않는다."""
    verb_role = "combat_verb_incoming" if incoming else "combat_verb_outgoing"
    damage_role = "damage_taken" if incoming else "damage_dealt"
    outcome = "를 입었다." if incoming else "를 입혔다."
    return (*prefix, (verb_role, verb + punctuation), ("text", " "),
            (damage_role, f"{damage} 피해"), ("text", outcome))


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
                        CombatNarrationSpec((replace(phrase, instrument="이빨!"),)),
                        CombatNarrationSpec((replace(phrase, verb=""),)),
                        CombatNarrationSpec((replace(phrase, verb="쓰러졌다"),)),
                        CombatNarrationSpec((replace(phrase, strong_verb="거세게 공격당했다"),)),
                        CombatNarrationSpec((replace(phrase, strong_verb=None),))):
            with self.subTest(invalid=invalid), self.assertRaises(ActorDefinitionError):
                validate_definitions((replace(actor, combat_narration=invalid),), caps)

        validate_definitions((replace(actor, combat_narration=CombatNarrationSpec(
            (AttackPhrase("고압 회로", "지졌다", "지졌다"), phrase),
        )),), caps)

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
                "총탄을 발사했다", "방아쇠를 당겼다", "쏘았다 적을", "쓰러졌다", "공격당했다",
            )),
        ):
            with self.subTest(invalid=invalid):
                self.assertTrue(item_attack_narration_errors("weapon", {**weapon, "combat_narration": invalid}))
        for identity in ("folding_shield", "portable_analyzer", "expedition_workwear", "bandage"):
            with self.subTest(identity=identity):
                definition = ITEMS[identity]
                self.assertEqual(item_attack_narration_errors(identity, definition), [])
                self.assertTrue(item_attack_narration_errors(identity, {**definition, "combat_narration": valid}))

    def assert_attack_preview(self, prefix, verbs, expected, *, damage, expected_damage, prefix_roles,
                              incoming=False):
        normal, heavy = verbs
        expected_attacks = (*expected, expected[1].removesuffix(".") + "!")
        expected_tail_roles = (("combat_verb_incoming", "text", "damage_taken", "text") if incoming else
                               ("combat_verb_outgoing", "text", "damage_dealt", "text"))
        for verb, punctuation, expected_attack in zip((normal, heavy, heavy), (".", ".", "!"),
                                                      expected_attacks, strict=True):
            preview = attack_preview(prefix, verb, punctuation, damage, incoming=incoming)
            self.assertEqual("".join(value for _, value in preview), f"{expected_attack} {expected_damage}")
            self.assertEqual(tuple(role for role, _ in preview), (*prefix_roles, *expected_tail_roles))
            self.assertEqual(tuple(value for _, value in preview[-4:]),
                             (verb + punctuation, " ", f"{damage} 피해",
                              expected_damage.removeprefix(f"{damage} 피해")))

    def test_weapon_and_barehand_sentence_snapshots(self):
        weapons = {identity: data for identity, data in ITEMS.items()
                   if data.get("equipment_properties", {}).get("role") == "weapon"}
        self.assertEqual(weapons.keys(), WEAPON_SENTENCES.keys())
        target = HOSTILE_ACTORS["scavenger"].name
        cases = [(data["name"], data["combat_narration"], WEAPON_SENTENCES[identity])
                 for identity, data in weapons.items()]
        cases.append(("맨손", BAREHAND_NARRATION, (
            ("맨손으로 어린청소룡을 때렸다.", "맨손으로 어린청소룡을 세게 때렸다."),
            ("맨손으로 어린청소룡을 후려쳤다.", "맨손으로 어린청소룡을 힘껏 후려쳤다."),
        )))
        for name, narration, expected in cases:
            with self.subTest(name=name):
                barehand = narration is BAREHAND_NARRATION
                prefix = player_prefix(name, target, barehand=barehand)
                for phrase, snapshot in zip(narration["normal"], expected, strict=True):
                    self.assert_attack_preview(prefix, (phrase["verb"], phrase["strong_verb"]), snapshot,
                                               damage=5, expected_damage="5 피해를 입혔다.",
                                               prefix_roles=("text" if barehand else "item", "text", "hostile", "text"))

        name = weapons["guard_carbine"]["name"]
        target = HOSTILE_ACTORS["sentinel"].name
        phrase = weapons["guard_carbine"]["combat_narration"]["normal"][1]
        prefix = player_prefix(name, target)
        self.assert_attack_preview(
            prefix, (phrase["verb"], phrase["strong_verb"]),
            ("경비카빈으로 고장난경비기를 쏘았다.", "경비카빈으로 고장난경비기를 쏘았다."),
            damage=8, expected_damage="8 피해를 입혔다.", prefix_roles=("item", "text", "hostile", "text"),
        )
        self.assertEqual(
            attack_preview(prefix, phrase["strong_verb"], "!", 8, incoming=False),
            (("item", "경비카빈"), ("text", "으로 "), ("hostile", "고장난경비기"), ("text", "를 "),
             ("combat_verb_outgoing", "쏘았다!"), ("text", " "), ("damage_dealt", "8 피해"), ("text", "를 입혔다.")),
        )

    def test_actor_sentence_snapshots_without_special_profile_duplication(self):
        self.assertEqual(HOSTILE_ACTORS.keys(), ACTOR_SENTENCES.keys())
        for identity, actor in HOSTILE_ACTORS.items():
            with self.subTest(identity=identity):
                spec = actor.combat_narration
                phrase, = spec.normal_attacks
                self.assertIsNone(spec.special_attack)
                self.assertIsNone(spec.telegraph)
                prefix = actor_prefix(actor.name, phrase.instrument)
                self.assert_attack_preview(prefix, (phrase.verb, phrase.strong_verb), ACTOR_SENTENCES[identity],
                                           damage=6, expected_damage="6 피해를 입었다.",
                                           prefix_roles=("hostile", "text"), incoming=True)

        hunter = HOSTILE_ACTORS["hunter"]
        phrase = hunter.combat_narration.normal_attacks[0]
        self.assertEqual(
            attack_preview(actor_prefix(hunter.name, phrase.instrument), phrase.verb, ".", 6, incoming=True),
            (("hostile", "갈퀴사냥룡"), ("text", "이 날카로운 발톱으로 당신을 "),
             ("combat_verb_incoming", "할퀴었다."), ("text", " "), ("damage_taken", "6 피해"), ("text", "를 입었다.")),
        )
