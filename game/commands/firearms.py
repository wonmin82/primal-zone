"""총기 명령은 공통 selector와 영속 facade를 사용한다."""

from world import firearm_service as service
from world import rules
from world.content import ITEMS
from world.equipment_service import resolve_item, selector_label
from world.targets import parse_relation

from commands.base import GameCommand


def relation(character, value, particle):
    known = [name for key, data in ITEMS.items() for name in (key, data["name"], *data.get("aliases", ()))]
    selector, other = parse_relation(value, particle, known)
    text = selector.name + (f" {selector.index}" if selector.index else "")
    from world.targets import require_single

    require_single(selector, "장전")
    return resolve_item(character, text, "장전"), other


class Reload(GameCommand):
    key = "재장전"
    category = "전투·회복"
    input_style = "target"
    usage = "탐사카빈 재장전"
    summary = "잔탄이 가장 많은 소지 탄창으로 교체합니다. 성공 시 전투 기회 하나를 사용합니다."

    def run(self):
        item = resolve_item(self.caller, self.args, self.key)
        changed = service.reload(self.caller, item)
        self.caller.msg(f"{selector_label(self.caller, item)}: " + ("재장전했다." if changed else "현재 탄창을 유지한다."))


class LoadMagazine(Reload):
    key = "장전"
    usage = "탐사카빈에 카빈표준 장전"
    summary = "총기와 탄창을 각각 지정하여 교체합니다."

    def run(self):
        item, text = relation(self.caller, self.args, "에")
        magazine = resolve_item(self.caller, text, self.key)
        changed = service.reload(self.caller, item, magazine)
        self.caller.msg("탄창을 장전했다." if changed else "현재 탄창을 유지한다.")


class FillMagazine(Reload):
    key = "채워"
    category = "아이템·보급"
    usage = "카빈표준 채워"
    summary = "비전투 중 소지한 호환 탄약으로 탄창을 채웁니다."

    def run(self):
        item = resolve_item(self.caller, self.args, self.key)
        count = service.load_ammo(self.caller, item)
        self.caller.msg(f"탄창에 {count}발을 넣었다.")


def load_loose(character, item, text):
    ammo = resolve_item(character, text, "넣어")
    count = service.load_ammo(character, item, ammo)
    character.msg(f"탄창에 {count}발을 넣었다.")


def unload(character, item, text):
    from world.targets import item_selector, normalized

    if normalized(text) == "탄창":
        service.unload_magazine(character, item)
        character.msg("탄창을 꺼냈다.")
    else:
        identity = item_selector(text, ITEMS, "꺼내")
        ammo_type = ITEMS[identity].get("ammo_type")
        if ammo_type is None:
            raise rules.RuleError("탄창 또는 정확한 탄약 이름을 지정하세요.")
        count = service.unload_ammo(character, item, ammo_type)
        character.msg(f"탄창에서 {count}발을 전부 꺼냈다.")
