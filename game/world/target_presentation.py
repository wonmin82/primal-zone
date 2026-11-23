"""선택 번호를 세계 서술과 UI 제어용 표기로 나누어 표현한다."""

from world import text as ft
from world.loot_assets import asset_text
from world.targets import ordered


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


def selector_hint(objects, role, controls):
    if not objects:
        return ft.text("")
    selectable = [obj for obj in ordered(objects) if controls[obj.id] is not None]
    missing = "선택 번호를 확인할 수 없는 대상의 번호 안내는 제공하지 않습니다."
    if not selectable:
        return ft.text(missing)
    hint = ft.text(
        "대상 표시 ",
        ft.join(
            [ft.text("'", ft.token(role, controls[obj.id]), "'") for obj in selectable], ", "
        ),
        "를 확인할 수 있다.",
    )
    return ft.text(hint, " ", missing) if len(selectable) != len(objects) else hint


def presence(objects, role, unit, sentence, *, controls, source=False):
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
    numbered = [obj for obj in objects if controls[obj.id] != ("시체" if source else obj.key)]
    if numbered:
        lines.append(selector_hint(numbered, role, controls))
    return lines


def corpse_overview(corpses, caller, now, pool=None):
    from world.actions.loot_presentation import loot_display, visible_entries
    from world.observation import can_inspect_loot, context_for
    from world.selection_display import room_snapshot

    snapshot = room_snapshot(caller, now)
    controls = snapshot.labels
    lines = [ft.text("주변에 시체 ", count_word(len(corpses)), " 구가 남아 있다.")]
    if not can_inspect_loot(context_for(caller, observed_at=now)):
        lines.append("작은 전리품을 식별하기 어렵다. 광원을 사용하세요.")
        lines.append(selector_hint(corpses, "remains", controls))
        return ft.join(lines)
    display = loot_display(caller, now, snapshot=snapshot)
    for corpse in ordered(corpses):
        label = controls.get(corpse.pk)
        if label is None:
            lines.append(ft.text("선택 번호를 확인할 수 없는 ", ft.token("remains", corpse.key), "가 남아 있다."))
            continue
        entries = visible_entries(corpse, caller, now, display=display)
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
                ft.token("remains", label if label != "시체" else corpse.key),
                "에는 ",
                ft.join(items, ", ") if items else "전리품이 더는 없다",
                "가 남아 있다." if items else ".",
            )
        )
    return ft.join(lines)
