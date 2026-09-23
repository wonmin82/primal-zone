"""캐릭터 조회 화면. 수치와 이름은 기존 규칙/콘텐츠에서 읽는다."""

from world import rules
from world import text as ft
from world.content import EQUIPMENT_ACTIONS, EXCHANGE, ITEMS, SHOP
from world.progression import (
    ATTRIBUTES,
    PROFICIENCIES,
    SKILLS,
)


def equipment(profile):
    lines = []
    attack = defense = 0
    for slot, identity in profile["equipment"].items():
        data = ITEMS[identity]
        attack += data.get("attack", 0)
        defense += data.get("defense", 0)
        bonuses = [
            f"{label} +{data[key]}"
            for key, label in (("attack", "공격"), ("defense", "방어"))
            if data.get(key, 0)
        ]
        lines.append(
            ft.row(
                "무기" if slot == "weapon" else "방어구",
                ft.join([ft.item(identity), *bonuses], " · "),
                8,
            )
        )
    lines.append(ft.row("보정", f"공격 +{attack} · 방어 +{defense}", 8))
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
        f"체력 {profile['hp']}/{values['max_hp']} · 공격 {values['attack']} · 방어 {values['defense']}",
        f"경험치 {xp} · 크레딧 {profile['credits']} · 처치 {profile['kills']}",
        "특성 | "
        + " ".join(
            f"{v['name']}{profile['attributes'][k]['base'] + rules.allocated(profile, k)}"
            for k, v in ATTRIBUTES.items()
        ),
        ft.text("장비 | ", ft.join([ft.item(i) for i in profile["equipment"].values()], " · ")),
        summary=ft.text(ft.token("player", name), f" · Lv.{values['level']}"),
    )


def abilities(profile):
    attributes = [
        f"{data['name']} {profile['attributes'][key]['base'] + rules.allocated(profile, key)} "
        f"({profile['attributes'][key]['base']}+{rules.allocated(profile, key)})"
        for key, data in ATTRIBUTES.items()
    ]
    lines = [ft.join(attributes[i : i + 2], " · ") for i in range(0, len(attributes), 2)]
    lines.extend(
        [
            f"남은 특성 포인트 {rules.point_pools(profile)['attribute_points']}",
            "",
            ft.text(
                "[숙련] ",
                ft.join(
                    [
                        f"{name} R{rules.proficiency_rank(profile, key)}"
                        for key, name in PROFICIENCIES.items()
                    ],
                    " · ",
                ),
            ),
        ]
    )
    return ft.compact("능력", *lines)


def experience(profile):
    level = rules.level_of(profile)
    progress = (
        f"XP {profile['xp']}/{rules.xp_threshold(level + 1)} · 다음 {rules.xp_threshold(level + 1) - profile['xp']}"
        if level < rules.MAX_LEVEL
        else f"XP {profile['xp']} · 최고 등급"
    )
    return ft.compact(
        "경험치",
        ft.text(
            "숙련 | ",
            ft.join(
                [
                    f"{name} R{rules.proficiency_rank(profile, key)} XP{profile['proficiencies'][key]['xp']}"
                    for key, name in PROFICIENCIES.items()
                ],
                " · ",
            ),
        ),
        summary=f"Lv.{level} · {progress}",
    )


def skills(profile):
    lines = []
    for key, data in SKILLS.items():
        rank = rules.skill_rank(profile, key)
        next_rank = rank + 1
        learning = (
            f"다음 Lv{data['requirements'][next_rank]}/{data['point_cost'][next_rank]}점/{data['credit_cost'][next_rank]}C"
            if next_rank <= data["max_rank"]
            else "최고 Rank"
        )
        # 기존 설명을 그대로 사용한다. 모바일에서는 한 항목 안에서 자연스럽게 줄바꿈한다.
        lines.append(
            f"{data['name']} R{rank}/{data['max_rank']} · {data['description']} · {learning}"
        )
    lines.append(ft.text("학습: 교관에게 기술이름 ", ft.token("command", "배워"), " · C=크레딧"))
    return ft.compact(
        "기술", *lines, summary=f"남은 점수 {rules.point_pools(profile)['skill_points']}"
    )


def inventory(profile):
    groups = {"장비": [], "소모품": [], "재료": [], "기타": []}
    for identity, count in profile["inventory"].items():
        if count <= 0:
            continue
        slot = ITEMS[identity]["slot"]
        group = (
            "장비"
            if slot in ("weapon", "armor")
            else "소모품"
            if slot == "consumable"
            else "재료"
            if slot == "material"
            else "기타"
        )
        mark = ft.token("success", " [착용]") if identity in profile["equipment"].values() else ""
        groups[group].append(ft.text(ft.item(identity), f"×{count}", mark))
    lines = [
        ft.text(f"[{title}] ", ft.join(entries, " · "))
        for title, entries in groups.items()
        if entries
    ]
    return ft.compact("가방", *lines, summary="" if lines else "비어 있다.")


def shop():
    lines = []
    for key, price in SHOP.items():
        parts = [ft.item(key), ft.token("reward", f"{price}C")]
        if key in EXCHANGE:
            parts.append(ft.text("교환 ", ft.item("scrap"), f" {EXCHANGE[key]}개"))
        lines.append(ft.join(parts, " · "))
    lines.append(
        ft.text(
            "물건이름 ",
            ft.token("command", "구매"),
            " · 물건이름 ",
            ft.token("command", "교환"),
            " · C=크레딧 (1개씩)",
        )
    )
    return ft.compact("부두 보급소", *lines)


def quest(profile):
    from typeclasses.interactables import content_name

    from world.content import ENEMIES

    steps = [
        ("quest_started", ft.text(content_name("commander"), "에게 임무 수령")),
        ("record_read", ft.text(content_name("maintenance_log"), " 확인")),
        ("generator_fixed", ft.text(content_name("generator"), " 복구")),
        ("boss_defeated", ft.text(ft.token("hostile", ENEMIES["alpha"]["name"]), " 처치")),
        ("quest_claimed", ft.text(content_name("commander"), "에게 보고")),
    ]
    current = next((i for i, (key, _) in enumerate(steps) if not profile[key]), len(steps))
    lines = []
    for index, (key, description) in enumerate(steps):
        mark, role = (
            ("+", "success")
            if profile[key]
            else (">", "command")
            if index == current
            else ("-", "muted")
        )
        lines.append(ft.text(ft.token(role, mark), " ", description))
    return ft.compact(
        "임무",
        *lines,
        summary=f"통신탑 복구 · {sum(bool(profile[k]) for k, _ in steps)}/{len(steps)}",
    )


def outgoing_attack(profile, enemy_name, outcome, damage):
    if outcome["action"] == "error":
        return ft.text(ft.token("error", "! "), outcome["message"], kind="error")
    if outcome["action"] == "heal":
        return healing(outcome["amount"])
    verb = "강하게 내리쳐" if outcome["action"] == "heavy" else "공격해"
    return ft.text(
        ft.item(profile["equipment"]["weapon"]),
        ft.particle(ITEMS[profile["equipment"]["weapon"]]["name"], "으로/로"),
        " ",
        ft.named("hostile", enemy_name, "을/를"),
        f" {verb} {damage}의 피해를 입혔다.",
        " 이어서 방어 자세를 취했다." if outcome["action"] == "guard" else "",
    )


def healing(amount):
    return ft.text(ft.item("bandage"), f"를 꺼내 상처를 감았다. 체력이 {amount} 회복되었다.")


def reward(xp, credits):
    return ft.text(
        "이번 사냥으로 ",
        ft.token("reward", f"경험치 {xp}"),
        ", ",
        ft.token("reward", f"{credits}크레딧"),
        "을 얻었다.",
    )


def item_appearance(identity):
    data = ITEMS[identity]
    lines = [data.get("description", "탐사 중 사용하는 물품이다.")]
    for key, label in (("attack", "공격"), ("defense", "방어"), ("heal", "회복")):
        if data.get(key):
            lines.append(f"{label} +{data[key]}")
    actions = (
        [EQUIPMENT_ACTIONS[data["slot"]]]
        if data["slot"] in EQUIPMENT_ACTIONS
        else ["회복"]
        if identity == "bandage"
        else []
    )
    return ft.sheet(ft.item(identity), *lines, "", ft.actions(actions))
