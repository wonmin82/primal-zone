"""선택 번호를 세계 서술과 UI 제어용 표기로 나누어 표현한다."""

from world import text as ft
from world.loot_assets import asset_text
from world.targets import labels, ordered


def count_word(count):
    return {
        1: "한",
        2: "두",
        3: "세",
        4: "네",
        5: "다섯",
        6: "여섯",
        7: "일곱",
        8: "여덟",
        9: "아홉",
        10: "열",
    }.get(count, str(count))


def selector_hint(objects, role, source=False, pool=None):
    if len(objects) < 2:
        return ft.text("")
    controls = labels(
        pool if pool is not None else objects, lambda obj: "시체" if source else obj.key
    )
    return ft.text(
        "현재 보이는 순서대로 ",
        ft.join(
            [ft.text("'", ft.token(role, controls[obj.id]), "'") for obj in ordered(objects)], ", "
        ),
        " 같은 표기로 구분해 지정할 수 있다.",
    )


def presence(objects, role, unit, sentence, source=False, pool=None):
    groups = {}
    for obj in ordered(objects):
        groups.setdefault(obj.key, []).append(obj)
    lines = []
    for name, group in groups.items():
        if len(group) == 1:
            lines.append(ft.text(ft.named(role, name, "이/가"), " ", sentence))
        else:
            lines.append(
                ft.text(
                    ft.token(role, name),
                    " ",
                    count_word(len(group)),
                    " ",
                    unit,
                    ft.particle(unit),
                    " ",
                    sentence,
                )
            )
    if source and len(objects) > 1:
        lines.append(selector_hint(objects, role, source=True))
    elif not source:
        for group in groups.values():
            if len(group) > 1:
                lines.append(selector_hint(group, role, pool=pool))
    return lines


def corpse_overview(corpses, caller, now, pool=None):
    from world.observation import can_inspect_loot, context_for
    from world.state import loot_entries

    lines = [ft.text("주변에 시체 ", count_word(len(corpses)), " 구가 남아 있다.")]
    if not can_inspect_loot(context_for(caller, observed_at=now)):
        lines.append("작은 전리품을 식별하기 어렵다. 광원을 사용하세요.")
        lines.append(selector_hint(corpses, "remains", source=True, pool=pool))
        return ft.join(lines)
    pool = ordered(corpses if pool is None else pool)
    for corpse in ordered(corpses):
        index = pool.index(corpse) + 1
        entries = loot_entries(corpse, caller, now)
        items = []
        for entry in entries:
            rights = (
                ft.text(
                    " (",
                    ft.token("player", entry["assigned_name"]),
                    "에게 배정",
                    ", 회수 가능" if entry["can_take"] else ", 보호 중",
                    ")",
                )
                if entry["protected"]
                else " (자유 획득)"
            )
            items.append(
                ft.text(asset_text(entry) if entry["kind"] == "currency"
                        else ft.text(ft.item(entry["id"]), " ", count_word(entry["quantity"]), " 개"), rights)
            )
        lines.append(
            ft.text(
                "첫 번째 " if index == 1 else count_word(index) + " 번째 ",
                ft.token("remains", corpse.key),
                "에는 ",
                ft.join(items, ", ") if items else "전리품이 더는 없다",
                "가 남아 있다." if items else ".",
            )
        )
    lines.append(selector_hint(corpses, "remains", source=True, pool=pool))
    return ft.join(lines)
