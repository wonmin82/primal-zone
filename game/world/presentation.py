"""캐릭터 조회 화면. 수치와 이름은 기존 규칙/콘텐츠에서 읽는다."""

from world import rules
from world import text as ft
from world.content import EXCHANGE, ITEMS, SHOP
from world.progression import (
    ATTRIBUTES,
    PROFICIENCIES,
    PROFICIENCY_MAX_RANK,
    PROFICIENCY_XP_PER_RANK,
    SKILLS,
)


def equipment(profile):
    lines = []
    attack = defense = 0
    for slot, identity in profile["equipment"].items():
        item = ITEMS[identity]
        attack += item.get("attack", 0)
        defense += item.get("defense", 0)
        lines.extend(
            [
                "무기" if slot == "weapon" else "방어구",
                ft.text("  ", ft.item(identity)),
                f"  공격 +{item.get('attack', 0)} · 방어 +{item.get('defense', 0)}",
                "",
            ]
        )
    lines.append(f"장비 보정 : 공격 +{attack} · 방어 +{defense}")
    return ft.sheet("착용 장비", *lines)


def status(name, profile):
    values = rules.stats(profile)
    xp = (
        f"{profile['xp']} / {rules.xp_threshold(values['level'] + 1)}"
        if values["level"] < rules.MAX_LEVEL
        else f"{profile['xp']} (최고 등급)"
    )
    lines = [
        ft.row("등급", f"Lv.{values['level']}"),
        ft.row("체력", f"{profile['hp']} / {values['max_hp']}"),
        ft.row("경험치", xp),
        ft.row("크레딧", profile["credits"]),
        ft.row("처치", profile["kills"]),
        "",
        ft.row("공격", values["attack"]),
        ft.row("방어", values["defense"]),
        "",
        "[ 특성 ]",
        " · ".join(
            f"{v['name']} {profile['attributes'][k]['base'] + rules.allocated(profile, k)}"
            for k, v in ATTRIBUTES.items()
        ),
        "",
        "[ 착용 장비 ]",
    ]
    lines.extend(
        ft.row("무기" if slot == "weapon" else "방어구", ft.item(identity))
        for slot, identity in profile["equipment"].items()
    )
    return ft.sheet(ft.text(ft.token("player", name), "의 상태"), *lines)


def abilities(profile):
    lines = ["[ 특성 ]", ""]
    for key, data in ATTRIBUTES.items():
        entry = profile["attributes"][key]
        lines.extend(
            [
                ft.row(
                    data["name"],
                    f"{entry['base'] + entry['allocated']} (기본 {entry['base']} + 투자 {entry['allocated']})",
                ),
                ft.text("  ", ft.token("muted", data["description"])),
            ]
        )
    lines.extend(
        [
            "",
            f"남은 특성 포인트 : {rules.point_pools(profile)['attribute_points']}",
            "",
            "[ 숙련 ]",
            "",
        ]
    )
    lines.extend(
        ft.row(name, f"Rank {rules.proficiency_rank(profile, key)}")
        for key, name in PROFICIENCIES.items()
    )
    return ft.sheet("능력", *lines)


def experience(profile):
    level = rules.level_of(profile)
    remaining = (
        max(0, rules.xp_threshold(level + 1) - profile["xp"]) if level < rules.MAX_LEVEL else 0
    )
    lines = [
        f"캐릭터 Lv.{level}",
        ft.row(
            "경험치",
            f"{profile['xp']} / {rules.xp_threshold(level + 1)}"
            if level < rules.MAX_LEVEL
            else f"{profile['xp']} (최고 등급)",
        ),
        ft.row("다음 등급까지", remaining),
        "",
        "[ 숙련 ]",
    ]
    lines.extend(
        ft.row(
            name,
            f"Rank {rules.proficiency_rank(profile, key)} · XP {profile['proficiencies'][key]['xp']} / {PROFICIENCY_MAX_RANK * PROFICIENCY_XP_PER_RANK}",
        )
        for key, name in PROFICIENCIES.items()
    )
    return ft.sheet("경험치", *lines)


def skills(profile):
    lines = []
    for key, data in SKILLS.items():
        rank = rules.skill_rank(profile, key)
        next_rank = rank + 1
        # 기술명은 학습 대상이다. 행동 명령과 동일하다고 추측하지 않는다.
        lines.extend(
            [ft.row(data["name"], f"Rank {rank} / {data['max_rank']}"), f"  {data['description']}"]
        )
        if next_rank <= data["max_rank"]:
            lines.append(
                f"  다음 수련 : Lv.{data['requirements'][next_rank]} · {data['point_cost'][next_rank]}점 · {data['credit_cost'][next_rank]}크레딧"
            )
        else:
            lines.append("  최고 Rank")
        lines.append("")
    lines.extend(
        [
            f"남은 기술점수 : {rules.point_pools(profile)['skill_points']}",
            ft.text("교관에게 기술이름 ", ft.token("command", "배워")),
        ]
    )
    return ft.sheet("기술", *lines)


def inventory(profile):
    groups = {"장비": [], "소모품": [], "재료": [], "기타": []}
    for identity, count in profile["inventory"].items():
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
        groups[group].append(ft.text(ft.row(ft.item(identity), f"×{count}", 18), mark))
    lines = []
    for title, entries in groups.items():
        if entries:
            lines.extend([f"[ {title} ]", *entries, ""])
    return ft.sheet("소지품", *(lines or ["가방이 비어 있다."]))


def shop():
    lines = []
    for key, price in SHOP.items():
        exchange = (
            ft.text("\n  교환 : ", ft.item("scrap"), f" {EXCHANGE[key]}개")
            if key in EXCHANGE
            else ""
        )
        lines.append(
            ft.text(ft.row(ft.item(key), ft.token("reward", f"{price} 크레딧"), 18), exchange)
        )
    lines.extend(
        [
            "",
            ft.text(
                "물건이름 ",
                ft.token("command", "구매"),
                " · 물건이름 ",
                ft.token("command", "교환"),
                " (한 번에 1개)",
            ),
        ]
    )
    return ft.sheet("부두 보급소", *lines)


def quest(profile):
    from typeclasses.interactables import content_name

    from world.content import ENEMIES

    steps = [
        ("quest_started", ft.text(content_name("commander"), "에게 임무를 받음")),
        ("record_read", ft.text(content_name("maintenance_log"), "을 확인함")),
        ("generator_fixed", ft.text(content_name("generator"), "를 복구")),
        ("boss_defeated", ft.text(ft.token("hostile", ENEMIES["alpha"]["name"]), " 처치")),
        ("quest_claimed", ft.text(content_name("commander"), "에게 보고")),
    ]
    current = next((index for index, (key, _) in enumerate(steps) if not profile[key]), len(steps))
    lines = [
        "현재 목표",
        ft.text("  ", steps[current][1])
        if current < len(steps)
        else ft.token("success", "  첫 탐사를 완수했다."),
        "",
        "진행",
    ]
    for index, (key, description) in enumerate(steps):
        label = "[완료]" if profile[key] else "[진행]" if index == current else "[대기]"
        lines.append(
            ft.text(ft.token("success" if profile[key] else "muted", label), " ", description)
        )
    return ft.sheet("통신탑 복구", *lines)


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
        if key in data:
            lines.append(f"{label} +{data[key]}")
    actions = (
        ["착용"]
        if data["slot"] in ("weapon", "armor")
        else ["회복"]
        if identity == "bandage"
        else []
    )
    return ft.sheet(ft.item(identity), *lines, "", ft.actions(actions))
