"""공식 전투 문장과 의미 역할의 경계 검증."""

from unittest import TestCase

from world import combat_narration as narration
from world.actors.hostile_content import HOSTILE_ACTORS
from world.content import ITEMS
from world.equipment import item_snapshot


def weapon(identity):
    return item_snapshot(identity, ITEMS[identity])


class CombatNarrationTests(TestCase):
    def assert_message(self, message, sentence, emphasized):
        self.assertEqual(message, sentence)
        self.assertEqual(
            [(part["role"], part["text"]) for part in message.segments if part["role"] != "text"],
            emphasized,
        )

    def test_damage_strength_thresholds_use_applied_damage(self):
        for damage, maximum, verb in (
            (0, 60, "찔렀다."),
            (8, 60, "찔렀다."),
            (9, 60, "깊게 찔렀다."),
            (17, 60, "깊게 찔렀다."),
            (18, 60, "깊게 찔렀다!"),
            (9, 30, "깊게 찔렀다."),
            (10, 30, "깊게 찔렀다!"),
        ):
            with self.subTest(damage=damage, maximum=maximum):
                message = narration.outgoing("갈퀴사냥룡", weapon("pioneer_spear"), {"action": "attack"},
                                             damage, maximum, 1)
                self.assert_message(
                    message, f"개척창으로 갈퀴사냥룡을 {verb} {damage} 피해를 입혔다.",
                    [("item", "개척창"), ("hostile", "갈퀴사냥룡"), ("combat_verb_outgoing", verb),
                     ("damage_dealt", f"{damage} 피해")],
                )

    def test_technique_strength_retains_skill_and_weapon(self):
        for action, identity, target, phrase, strong in (
            ("heavy", "jungle_longblade", "갈퀴사냥룡", "강타를 가했다", "강타를 힘껏 가했다"),
            ("shooting", "guard_carbine", "고장난경비기", "집중 사격했다", "매섭게 집중 사격했다"),
        ):
            arms = weapon(identity)
            subject = {"heavy": "정글장도로 갈퀴사냥룡에게 ", "shooting": "경비카빈으로 고장난경비기를 "}[action]
            for damage, verb in ((12, phrase + "."), (15, strong + "."), (30, strong + "!")):
                with self.subTest(action=action, damage=damage):
                    self.assert_message(
                        narration.outgoing(target, arms, {"action": action}, damage, 100, 2),
                        f"{subject}{verb} {damage} 피해를 입혔다.",
                        [("item", arms.name), ("hostile", target), ("combat_verb_outgoing", verb),
                         ("damage_dealt", f"{damage} 피해")],
                    )

    def test_suppression_uses_four_confirmed_effect_results(self):
        for status, attacks, reduction, suffix in (
            ("applied", 2, .10, "다음 2회 공격력이 10% 감소한다."),
            ("refreshed", 2, .12, "자신의 견제 효과를 다음 2회 공격까지 연장했다. 공격력 12% 감소 효과가 유지된다."),
            ("upgraded", 3, .125, "자신의 견제 효과를 다음 3회 공격의 공격력 12.5% 감소로 강화했다."),
            ("preserved", 1, .2, "기존의 더 강한 견제 효과(공격력 20% 감소, 남은 1회)가 유지됐다."),
        ):
            with self.subTest(status=status):
                outcome = {"action": "suppress", "suppression": {"attacks": attacks, "reduction": reduction},
                           "suppression_status": status}
                noun = "공격력이" if status == "applied" else "공격력"
                self.assert_message(
                    narration.outgoing("갈퀴사냥룡", weapon("pioneer_spear"), outcome, 7, 60, 2),
                    f"갈퀴사냥룡을 견제했다. 7 피해를 입혔다. {suffix}",
                    [("hostile", "갈퀴사냥룡"), ("combat_verb_outgoing", "견제했다."), ("damage_dealt", "7 피해"),
                     ("status_debuff", f"{noun} {reduction * 100:g}% 감소")],
                )

    def test_insight_without_damage_and_next_attack(self):
        result = {"action": "insight", "penetration": .20, "bonus": .15}
        self.assert_message(
            narration.outgoing("갈퀴사냥룡", None, result, 0, 60, 1),
            "갈퀴사냥룡의 빈틈을 간파했다. 다음 공격의 방어 관통이 20%, 피해가 15% 증가한다.",
            [("hostile", "갈퀴사냥룡"), ("status_buff", "방어 관통이 20%"), ("status_buff", "피해가 15% 증가")],
        )
        result = {"action": "attack", "insight": True}
        self.assertEqual(
            narration.outgoing("갈퀴사냥룡", weapon("jungle_longblade"), result, 18, 60, 1),
            "간파한 빈틈을 노려 정글장도로 갈퀴사냥룡을 크게 베었다! 18 피해를 입혔다.",
        )

    def test_special_attacks_use_actor_declaration_and_damage_strength(self):
        for key, normal, severe, warning in (
            ("alpha", "능선의우두머리가 돌진해 당신을 들이받았다.", "능선의우두머리가 돌진해 당신을 거세게 들이받았다!",
             "! 능선의우두머리가 몸을 낮추고 돌진할 자세를 취한다."),
            ("jungle_apex", "밀림의포식자가 몸을 날려 당신을 덮쳤다.", "밀림의포식자가 몸을 날려 당신을 거세게 덮쳤다!",
             "! 밀림의포식자가 숨을 고르며 도약할 자세를 취한다."),
        ):
            with self.subTest(key=key):
                actor = HOSTILE_ACTORS[key]
                spec = actor.combat_narration
                for damage, attack, verb in ((6, normal, spec.special_attack.verb + "."),
                                             (42, severe, spec.special_attack.strong_verb + "!")):
                    self.assert_message(
                        narration.incoming(actor.name, spec, True, damage, 60, 3),
                        f"{attack} {damage} 피해를 입었다.",
                        [("hostile", actor.name), ("combat_verb_incoming", verb), ("damage_taken", f"{damage} 피해")],
                    )
                self.assert_message(narration.telegraph(actor.name, spec), warning,
                                    [("warning", "! "), ("hostile", actor.name)])

    def test_duel_displays_both_amounts_from_duel_health(self):
        alpha = HOSTILE_ACTORS["alpha"]
        self.assert_message(
            narration.outgoing(alpha.name, weapon("pioneer_spear"), {"action": "attack"}, 12, 100, 1, duel=True),
            "개척창으로 능선의우두머리를 찔렀다. 상대의 대련 체력에 12 피해를 입혔다.",
            [("item", "개척창"), ("hostile", alpha.name), ("combat_verb_outgoing", "찔렀다."), ("damage_dealt", "12 피해")],
        )
        sentinel = HOSTILE_ACTORS["sentinel"]
        self.assert_message(
            narration.incoming(sentinel.name, sentinel.combat_narration, False, 9, 100, 1, duel=True),
            "고장난경비기가 금속 몸체로 당신을 들이받았다. 대련 체력이 9 감소했다.",
            [("hostile", sentinel.name), ("combat_verb_incoming", "들이받았다."), ("damage_taken", "9")],
        )
        self.assertEqual(
            narration.outgoing(alpha.name, weapon("pioneer_spear"), {"action": "heavy"}, 12, 100, 1, duel=True),
            "개척창으로 능선의우두머리에게 강타를 가했다. 상대의 대련 체력에 12 피해를 입혔다.",
        )

    def test_errors_and_unknown_attack_data_cannot_fall_back(self):
        for warning in (
            "총기에 발사할 탄약이 없다. 재장전하세요.",
            "정신력이 부족합니다.",
            "아직 기술을 다시 사용할 수 없습니다.",
        ):
            with self.subTest(warning=warning):
                result = narration.outgoing("갈퀴사냥룡", None, {"action": "error", "message": warning}, 0, 60, 1)
                self.assert_message(result, "! " + warning, [("error", "! ")])
                self.assertEqual(result.kind, "error")
        with self.assertRaises(ValueError):
            narration.outgoing("갈퀴사냥룡", None, {"action": "unknown"}, 0, 60, 1)
        with self.assertRaises(KeyError):
            narration.outgoing("갈퀴사냥룡", weapon("folding_shield"), {"action": "attack"}, 1, 60, 1)
        hunter = HOSTILE_ACTORS["hunter"]
        with self.assertRaises(ValueError):
            narration.incoming(hunter.name, hunter.combat_narration, True, 1, 60, 1)
