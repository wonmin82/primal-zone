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


def equipment(profile):
    snapshot = eq.context(profile)
    lines = []
    for slot, label in eq.SLOT_LABELS.items():
        selected = [item for item in snapshot.items if item.slot == slot]
        names = [ft.text(ft.token("item", snapshot.label(item)), " [주무기]" if item is snapshot.active else "")
                 for item in selected]
        lines.append(ft.row(label, ft.join(names, " · ") if names else "없음", 8))
    values = rules.stats(profile)
    base = rules.stats(profile, eq.EquipmentSnapshot())
    lines.append(ft.row("보정", f"공격 +{values['attack'] - base['attack']:g} · 방어 +{values['defense'] - base['defense']:g}", 8))
    return ft.compact("장비", *lines)


def status(name, profile):
    values = rules.stats(profile)
    xp = (
        f"{profile['xp']}/{rules.xp_threshold(values['level'] + 1)}"
        if values["level"] < rules.MAX_LEVEL
        else f"{profile['xp']} (최고 등급)"
    )
    return ft.compact(
        "상태",
        f"체력 {profile['hp']}/{values['max_hp']} · 정신력 {profile['mental']}/{values['max_mental']}",
        f"공격 {values['attack']} · 방어 {values['defense']}",
        f"경험치 {xp} · 보급칩 {format_currency(profile['credits'])} · 처치 {profile['kills']}",
        "특성 | "
        + " ".join(
            f"{v['name']}{profile['attributes'][k]['base'] + rules.allocated(profile, k)}"
            for k, v in ATTRIBUTES.items()
        ),
        ft.text("장비 | ", ft.join([ft.token("item", eq.context(profile).label(item))
                                   for item in eq.context(profile).items], " · ") or "없음"),
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
        groups[group].append(ft.text(ft.token("item", row["selector"]), f"×{row['count']}", ft.token("success", mark) if mark else ""))
    lines = [ft.text(f"[{title}] ", ft.join(entries, " · ")) for title, entries in groups.items() if entries]
    return ft.compact("소지품", "", *(lines or ["비어 있다."]), summary=format_currency(profile["credits"]))


def shop(shop_id, seller):
    lines = []
    for key in SHOP_CATALOGS[shop_id]:
        parts = [ft.item(key), ft.token("reward", format_currency(rules.purchase_price(key)))]
        lines.append(ft.join(parts, " · "))
    lines.append(
        ft.text(
            "물건이름 ",
            ft.token("command", "구매"),
            " (1개씩)",
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


def support_result(outcome, recipient=None, combat=False):
    action, amount = outcome["action"], outcome["amount"]
    if action == "bandage":
        return ft.text(ft.item("bandage"), f" 하나를 사용해 HP {amount}{ft.particle(amount, '을/를')} 회복했다.")
    if action == "breathing":
        return ft.text(("공격을 멈추고 " if combat else "") + f"호흡을 가다듬어 정신력 {amount}{ft.particle(amount, '을/를')} 회복했다.")
    subject = ft.text(ft.named("player", recipient, "을/를"), " 치료해") if recipient else "상처를 치료해"
    return ft.text(subject, f" HP {amount}{ft.particle(amount, '을/를')} 회복", "시키고" if recipient else "하고", f" 정신력 {outcome['cost']}{ft.particle(outcome['cost'], '을/를')} 소모했다.")


def outgoing_attack(profile, enemy_name, outcome, damage):
    action = outcome["action"]
    if action == "error":
        return ft.text(ft.token("error", "! "), outcome["message"], kind="error")
    if action in ("heal", "breathing", "bandage"):
        return support_result(outcome, outcome.get("recipient"), combat=True)
    if action == "insight":
        return ft.text(ft.token("hostile", enemy_name), f"의 빈틈을 간파해 다음 공격의 방어 관통이 {outcome['penetration']:.0%}, 피해가 {outcome['bonus']:.0%} 증가한다.")
    prefix = "간파한 빈틈에 " if outcome.get("insight") else ""
    if action == "heavy":
        return ft.text(prefix, ft.token("hostile", enemy_name), f"에게 강타를 적중시켜 {damage} 피해를 입혔다.")
    if action == "shooting":
        return ft.text(prefix, ft.named("hostile", enemy_name, "을/를"), f" 사격해 {damage} 피해를 입혔다.")
    if action == "suppress":
        effect = outcome["suppression"]
        status = outcome.get("suppression_status", "applied")
        suffix = {
            "applied": f"입히고 다음 {effect['attacks']}회 공격력을 {effect['reduction'] * 100:g}% 낮췄다.",
            "refreshed": f"입히고 자신의 견제 효과를 다음 {effect['attacks']}회 공격까지 연장했다.",
            "upgraded": f"입히고 자신의 견제 효과를 다음 {effect['attacks']}회 공격력 {effect['reduction'] * 100:g}% 감소로 강화했다.",
            "preserved": "입혔지만 기존의 더 강한 견제 효과가 유지됐다.",
        }[status]
        return ft.text(prefix, ft.named("hostile", enemy_name, "을/를"), f" 견제해 {damage} 피해를 {suffix}")
    active = eq.context(profile).active
    weapon = active.definition_id if active else None
    weapon_name = ITEMS[weapon]["name"] if weapon else "맨손"
    return ft.text(prefix, ft.item(weapon) if weapon else weapon_name, ft.particle(weapon_name, "으로/로"), " ", ft.named("hostile", enemy_name, "을/를"), f" 공격해 {damage} 피해를 입혔다.")


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
