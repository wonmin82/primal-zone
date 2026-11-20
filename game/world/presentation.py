"""캐릭터 조회 화면. 수치와 이름은 기존 규칙/콘텐츠에서 읽는다."""

from world import equipment as eq
from world import rules
from world import text as ft
from world.content import EQUIPMENT_ACTIONS, ITEMS, SHOP_CATALOGS
from world.currency import format_currency
from world.progression import (
    ATTRIBUTES,
    SKILLS,
)


def _equipment_item_name(snapshot, item):
    return ft.text(ft.token("item", snapshot.label(item)), " [주무기]" if item is snapshot.active else "",
                   f" · {item.state_summary}" if item.state_summary else "")


def equipment(profile):
    snapshot = eq.context(profile)
    lines = []
    for slot, label in eq.SLOT_LABELS.items():
        selected = [item for item in snapshot.items if item.slot == slot]
        names = [_equipment_item_name(snapshot, item) for item in selected]
        lines.append(ft.row(label, ft.join(names, " · ") if names else "없음", 8))
    values = rules.stats(profile, snapshot)
    base = rules.stats(profile, eq.EquipmentSnapshot())
    lines.append(ft.row("보정", f"공격 +{values['attack'] - base['attack']:g} · 방어 +{values['defense'] - base['defense']:g}", 8))
    return ft.compact("장비", *lines)


def status(name, profile):
    snapshot = eq.context(profile)
    values = rules.stats(profile, snapshot)
    xp = (
        f"{profile['xp']}/{rules.xp_threshold(values['level'] + 1)}"
        if values["level"] < rules.MAX_LEVEL
        else f"{profile['xp']} (최고 등급)"
    )
    return ft.compact(
        "점수",
        f"체력 {profile['hp']}/{values['max_hp']} · 정신력 {profile['mental']}/{values['max_mental']}",
        f"공격 {values['attack']} · 방어 {values['defense']}",
        f"경험치 {xp} · 보급칩 {format_currency(profile['credits'])} · 처치 {profile['kills']}",
        "특성 | "
        + " ".join(
            f"{v['name']}{profile['attributes'][k]['base'] + rules.allocated(profile, k)}"
            for k, v in ATTRIBUTES.items()
        ),
        ft.text("장비 | ", ft.join([_equipment_item_name(snapshot, item)
                                   for item in snapshot.items], " · ") or "없음"),
        summary=ft.text(ft.token("player", name), f" · Lv.{values['level']}"),
    )


def abilities(profile):
    pools = rules.point_pools(profile)
    lines = []
    for key, data in ATTRIBUTES.items():
        invested = rules.allocated(profile, key)
        lines.append(ft.row(data["name"], f"{10 + invested} (10+{invested})" + (" MAX" if invested == 20 else ""), 8))
    lines.append("모든 특성을 완성했다." if pools["attribute_spent"] == 80 else f"남은 특성 포인트 {pools['attribute_points']}")
    lines.append(f"투자한 특성 {pools['attribute_spent']}/80")
    return ft.compact("능력", *lines)


def experience(profile):
    from world.progression import attribute_points

    level = rules.level_of(profile)
    if level == rules.MAX_LEVEL:
        return ft.compact("경험치", f"경험치 {profile['xp']:,}", "최고 레벨에 도달했다.", summary=f"Lv.{level} MAX")
    floor, ceiling = rules.xp_threshold(level), rules.xp_threshold(level + 1)
    lines = [f"현재 경험치 {profile['xp']:,}", f"현재 레벨 시작 {floor:,}", f"다음 레벨 {ceiling:,}",
             f"진행 {profile['xp'] - floor:,} / {ceiling - floor:,}", f"다음 레벨까지 {ceiling - profile['xp']:,}",
             f"Lv.{level + 1} 도달 시", "기술 훈련 +1"]
    points = attribute_points(level + 1) - attribute_points(level)
    if points:
        lines.append(f"특성 포인트 +{points}")
    return ft.compact("경험치", *lines, summary=f"Lv.{level}")


def skills(profile):
    from world.progression import TOTAL_SKILL_TRAINING

    pools = rules.point_pools(profile)
    lines, group = [], None
    for key, data in SKILLS.items():
        if data["group"] != group:
            group = data["group"]
            lines.append(f"[{group}]")
        rank = rules.skill_rank(profile, key)
        lines.append(ft.row(data["name"], f"R{rank}/{data['max_rank']}" + (" MAX" if rank == data["max_rank"] else ""), 12))
    lines.append(f"투자한 훈련 {pools['skill_spent']}/{TOTAL_SKILL_TRAINING}")
    summary = "모든 기술을 완성했다." if pools["skill_spent"] == TOTAL_SKILL_TRAINING else f"남은 기술 훈련 {pools['skill_points']}"
    return ft.compact("기술", *lines, summary=f"Lv.{rules.level_of(profile)} · {summary}")


def inventory(profile):
    groups = {"장비": [], "소모품": [], "재료": [], "기타": []}
    for row in eq.inventory_rows(profile):
        slot = row["slot"]
        group = "장비" if slot in eq.SLOT_CAPACITY else "소모품" if slot == "consumable" else "재료" if slot == "material" else "기타"
        mark = " [착용]" if row["equipped"] else ""
        if row["active_weapon"]:
            mark += " [주무기]"
        groups[group].append(ft.text(ft.token("item", row["selector"]), f"×{row['count']}",
                                    ft.token("success", mark) if mark else "",
                                    f" · {row['state_summary']}" if row["state_summary"] else "",
                                    " [장전]" if row["location"] == "inside" else ""))
    lines = [ft.text(f"[{title}] ", ft.join(entries, " · ")) for title, entries in groups.items() if entries]
    return ft.compact("가진거", "", *(lines or ["비어 있다."]), summary=format_currency(profile["credits"]))


def shop(shop_id, seller):
    lines = []
    for key in SHOP_CATALOGS[shop_id]["purchase_catalog"]:
        parts = [ft.item(key), ft.token("reward", format_currency(rules.purchase_price(key)))]
        if ITEMS[key].get("purchase_quantity", 1) != 1:
            parts.append(f"{ITEMS[key]['purchase_quantity']}발 묶음")
        lines.append(ft.join(parts, " · "))
    lines.append(
        ft.text(
            "물건이름 ",
            ft.token("command", "사"),
            " (표시된 구매 단위)",
        )
    )
    return ft.compact(ft.token("npc", seller), *lines)


def quest(profile):
    from typeclasses.interactables import content_name

    from world.content import ENEMIES
    from world.quests import QUESTS, next_step

    lines = []
    for identity, data in QUESTS.items():
        if not data.get("visible_from_start") and not profile["quests"][identity]["started"]:
            continue
        steps = data["steps"]
        current = next_step(profile, identity)
        done = sum(bool(profile["quests"][identity][flag]) for flag, *_ in steps)
        lines.append(f"{data['name']} · {done}/{len(steps)}")
        if done == len(steps):
            continue
        for index, (flag, target, role, suffix) in enumerate(steps):
            mark, mark_role = (
                ("+", "success") if profile["quests"][identity][flag]
                else (">", "command") if index == current else ("-", "muted")
            )
            name = (
                ft.token("hostile", ENEMIES[target]["name"])
                if role == "hostile" else content_name(target)
            )
            lines.append(ft.text(ft.token(mark_role, mark), " ", name, suffix))
    return ft.compact("임무", *lines)


def _recovered(resource, role, amount, ending=" 회복됐다."):
    if amount <= 0:
        return ft.text(f"{resource}은 회복되지 않았다.")
    return ft.text(f"{resource}이 ", ft.token(role, amount), ending)


def support_result(outcome, recipient=None, *, bandage_label=None):
    action, amount = outcome["action"], outcome["amount"]
    if action == "bandage":
        if bandage_label is None:
            label, use = ITEMS["bandage"]["name"], " 하나를 사용했다. "
        else:
            label, use = bandage_label, f"{ft.particle(bandage_label, '을/를')} 사용했다. "
        return ft.text(ft.token("item", label), use, _recovered("체력", "hp_recovered", amount))
    if action == "breathing":
        return ft.text("호흡을 가다듬었다. ", _recovered("정신력", "mental_recovered", amount))
    if action != "heal":
        raise ValueError(f"알 수 없는 지원 결과: {action}")
    if recipient is None:
        subject = "상처를 치료했다. " if amount > 0 else "치료를 시도했다. "
    else:
        subject = ft.text(ft.named("player", recipient, "을/를"),
                          " 치료했다. " if amount > 0 else " 치료하려 했다. ",
                          ft.token("player", recipient), "의 ")
    cost = outcome["cost"]
    cost_text = f"정신력 {cost}{ft.particle(cost, '을/를')} 소모했다."
    if amount <= 0:
        return ft.text(subject, _recovered("체력", "hp_recovered", amount), " ", cost_text)
    return ft.text(subject, _recovered("체력", "hp_recovered", amount, " 회복되고 "), cost_text)


def received_healing(healer, amount):
    return ft.text(ft.token("player", healer), "의 치료로 ", _recovered("체력", "hp_recovered", amount))


def consumable_recovery(label, operation, amount):
    verb = {"eat": " 먹었다. ", "drink": " 마셨다. "}[operation]
    return ft.text(ft.named("item", label, "을/를"), verb, _recovered("체력", "hp_recovered", amount))


def emergency_recovery(final_hp):
    return ft.text("응급 처치로 체력이 ", ft.token("hp_recovered", final_hp),
                   ft.particle(final_hp, "으로/로"), " 회복됐다. 추가 회복이 필요하다.")


def medical_recovery(amount, cost):
    return ft.text(_recovered("체력", "hp_recovered", amount),
                   f" 비용 {cost}칩을 지불했습니다. 정신력은 회복하지 않습니다.")


def rest_recovery(hp, mental):
    results = []
    if hp > 0:
        results.append(_recovered("체력", "hp_recovered", hp))
    if mental > 0:
        results.append(_recovered("정신력", "mental_recovered", mental))
    return ft.text("침대에서 휴식했다. ", ft.join(results, " "))


def reward(xp):
    return ft.text(
        "이번 사냥으로 ",
        ft.token("reward", f"경험치 {xp}"),
        "을 얻었다. 보급칩은 시체에서 회수할 수 있다.",
    )


def item_appearance(identity, *, light_status=None):
    data = ITEMS[identity]
    lines = [data.get("description", "탐사 중 사용하는 물품이다.")]
    if data.get("light_source"):
        if light_status is not None:
            lines.append(light_status)
        lines.append(ft.usage(f"{data['name']} 확인 · {data['name']} 켜 · {data['name']} 꺼", {"확인", "켜", "꺼"}))
        lines.append(f"전원 삽입: {data['name']}에 <전원 소스> 넣어")
    if data.get("power_source"):
        lines.append(f"사용 시간 약 {data['power_source']['capacity_seconds'] / 60:g}분 · 호환 광원에 넣어 사용한다.")
    for key, label in (("attack", "공격"), ("defense", "방어"), ("heal", "회복")):
        if data.get(key):
            lines.append(f"{label} +{data[key]}")
    actions = (
        ["확인", "켜", "꺼"]
        if data.get("light_source")
        else [EQUIPMENT_ACTIONS[data["slot"]]]
        if data["slot"] in EQUIPMENT_ACTIONS
        else ["붕대 사용"]
        if identity == "bandage"
        else [data["consume_action"]]
        if data.get("consume_action")
        else []
    )
    return ft.sheet(ft.item(identity), *lines, "", ft.actions(actions))
