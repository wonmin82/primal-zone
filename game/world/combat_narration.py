"""확정된 전투 결과를 한국어 문장과 의미 세그먼트로 표현한다."""

from world import text as ft
from world.content import ITEMS
from world.content.final_items import BAREHAND_NARRATION


def _candidate(phrases, round_index):
    if not (type(round_index) is int or type(round_index) is float and round_index.is_integer()) or round_index < 1:
        raise ValueError("공격 문구의 회차는 1 이상의 정수값이어야 합니다.")
    if not phrases:
        raise ValueError("공격 문구 후보가 없습니다.")
    return phrases[(int(round_index) - 1) % len(phrases)]


def _attack_style(damage, max_hp):
    if damage >= 10 and damage * 100 >= max_hp * 30:
        return True, "!"
    return damage > 0 and damage * 100 >= max_hp * 15, "."


def _weapon_prefix(weapon):
    if weapon is None:
        return ft.text("맨손", "으로 ")
    return ft.text(ft.token("item", weapon.name), f"{ft.particle(weapon.name, '으로/로')} ")


def _suppression(effect, status):
    attacks = effect["attacks"]
    percent = f"{effect['reduction'] * 100:g}%"
    reduction = f"공격력 {percent} 감소"
    if status == "preserved":
        return ft.text(" 기존의 더 강한 견제 효과(", ft.token("status_debuff", reduction),
                       f", 남은 {attacks}회)가 유지됐다.")
    if status == "refreshed":
        return ft.text(f" 자신의 견제 효과를 다음 {attacks}회 공격까지 연장했다. ",
                       ft.token("status_debuff", reduction), " 효과가 유지된다.")
    if status == "upgraded":
        return ft.text(f" 자신의 견제 효과를 다음 {attacks}회 공격의 ",
                       ft.token("status_debuff", reduction), "로 강화했다.")
    if status == "applied":
        return ft.text(f" 다음 {attacks}회 ", ft.token("status_debuff", f"공격력이 {percent} 감소"), "한다.")
    raise ValueError(f"알 수 없는 견제 결과: {status}")


def outgoing(target, weapon, outcome, damage, max_hp, round_index, *, duel=False):
    """공격 시점 장비와 확정된 적용 피해·기술 결과를 표시한다."""
    action = outcome["action"]
    name = ft.token("hostile", target)
    if action == "error":
        return ft.text(ft.token("error", "! "), outcome["message"], kind="error")
    if action == "insight":
        return ft.text(name, "의 빈틈을 간파했다. 다음 공격의 ",
                       ft.token("status_buff", f"방어 관통이 {outcome['penetration']:.0%}"), ", ",
                       ft.token("status_buff", f"피해가 {outcome['bonus']:.0%} 증가"), "한다.")

    strong, end = _attack_style(damage, max_hp)
    target_object = f"{ft.particle(target, '을/를')} "
    if action == "attack":
        narration = BAREHAND_NARRATION if weapon is None else ITEMS[weapon.definition_id]["combat_narration"]
        phrase = _candidate(narration["normal"], round_index)
        parts = (_weapon_prefix(weapon), name, target_object)
        verb = phrase["strong_verb" if strong else "verb"]
    elif action == "heavy":
        parts = (_weapon_prefix(weapon), name, "에게 ")
        verb = "강타를 힘껏 가했다" if strong else "강타를 가했다"
    elif action == "shooting":
        parts = (_weapon_prefix(weapon), name, target_object)
        verb = "매섭게 집중 사격했다" if strong else "집중 사격했다"
    elif action == "suppress":
        parts = (name, target_object)
        verb = "견제했다"
    else:
        raise ValueError(f"알 수 없는 전투 행동: {action}")

    prefix = ("간파한 빈틈을 노려 ",) if outcome.get("insight") else ()
    damage_prefix = " 상대의 대련 체력에 " if duel else " "
    result = ft.text(*prefix, *parts, ft.token("combat_verb_outgoing", verb + end),
                     damage_prefix, ft.token("damage_dealt", f"{damage} 피해"), "를 입혔다.")
    if action == "suppress":
        return ft.text(result, _suppression(outcome["suppression"], outcome["suppression_status"]))
    return result


def incoming(actor_name, spec, charged, damage, max_hp, round_index, *, duel=False):
    """Actor 정적 표현과 확정된 피격 결과를 표시한다."""
    strong, end = _attack_style(damage, max_hp)
    if charged:
        phrase = spec.special_attack
        if phrase is None:
            raise ValueError("확정된 특수 공격에 대응하는 Actor 문구가 없습니다.")
        instrument = phrase.prelude
    else:
        phrase = _candidate(spec.normal_attacks, round_index)
        instrument = f"{phrase.instrument}{ft.particle(phrase.instrument, '으로/로')}"

    verb = phrase.strong_verb if strong else phrase.verb
    attack = ft.text(ft.token("hostile", actor_name), f"{ft.particle(actor_name)} {instrument} 당신을 ",
                     ft.token("combat_verb_incoming", verb + end))
    if duel:
        return ft.text(attack, " 대련 체력이 ", ft.token("damage_taken", damage), " 감소했다.")
    return ft.text(attack, " ", ft.token("damage_taken", f"{damage} 피해"), "를 입었다.")


def telegraph(actor_name, spec):
    if spec.telegraph is None:
        raise ValueError("확정된 특수 공격 예고에 대응하는 Actor 문구가 없습니다.")
    return ft.text(ft.token("warning", "! "), ft.token("hostile", actor_name),
                   f"{ft.particle(actor_name)} {spec.telegraph}")
