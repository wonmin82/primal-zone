"""inventory 영역의 명시적 게임 명령."""

from world import rules
from world.content import EXCHANGE, ITEMS, SHOP, find_id

from commands.base import GameCommand


class Inventory(GameCommand):
    category = "보급"
    usage = "가방"
    summary = "전체 소지품을 확인합니다."
    key = "가방"
    aliases = ["i", "인벤토리"]

    def run(self):
        profile = self.caller.profile()
        lines = ["|g소지품|n"]
        for key, count in profile["inventory"].items():
            item = ITEMS[key]
            equipped = " [착용]" if key in profile["equipment"].values() else ""
            bonus = (
                f" 공격 +{item.get('attack', 0)} / 방어 +{item.get('defense', 0)}"
                if item["slot"] in ("weapon", "armor")
                else ""
            )
            lines.append(f"{item['name']} ×{count}{equipped}{bonus}")
        self.caller.msg("\n".join(lines))


class Equip(GameCommand):
    category = "보급"
    usage = "강철 마체테 착용"
    summary = "소유한 장비를 착용합니다."
    input_style = "target"
    key = "착용"
    aliases = ["equip"]

    def run(self):
        item = find_id(ITEMS, self.args.strip())
        if not item:
            raise rules.RuleError("사용법: 강철마체테 착용")
        self.caller.change(lambda profile: rules.equip(profile, item))
        self.caller.msg(f"{ITEMS[item]['name']} 착용 완료.")


class Shop(GameCommand):
    category = "보급"
    usage = "상점"
    summary = "부두의 판매·교환 가격을 확인합니다."
    key = "상점"
    aliases = ["shop"]

    def run(self):
        self.at_dock()
        lines = ["|g부두 보급소|n"]
        for key, price in SHOP.items():
            exchange = f" / 회수부품 {EXCHANGE[key]}개" if key in EXCHANGE else ""
            lines.append(f"{ITEMS[key]['name']}: {price} 크레딧{exchange}")
        lines.append("붕대 구매 · 강철마체테 구매 · 강화조끼 교환 (한 번에 1개)")
        self.caller.msg("\n".join(lines))


class Buy(GameCommand):
    category = "보급"
    usage = "붕대 구매"
    summary = "크레딧으로 물건을 구매합니다."
    input_style = "target"
    key = "구매"
    aliases = ["buy"]
    exchange = False

    def run(self):
        self.at_dock()
        item = find_id(ITEMS, self.args.strip())
        if not item:
            raise rules.RuleError("물건 이름을 확인하세요. 예: 붕대 구매")
        self.caller.change(lambda profile: rules.buy(profile, item, exchange=self.exchange))
        self.caller.msg(f"{ITEMS[item]['name']} 1개를 받았습니다.")


class Exchange(Buy):
    category = "보급"
    usage = "강화 조끼 교환"
    summary = "회수부품으로 장비를 교환합니다."
    key = "교환"
    aliases = ["exchange"]
    exchange = True


class Take(GameCommand):
    category = "전리품"
    usage = "시체에서 모두 가져 · 시체에서 아이템 가져 · 모두 가져 · 아이템 가져"
    summary = "권한에 따라 배정된 전리품을 분배합니다."
    key = "가져"
    input_style = "target"

    def run(self):
        from typeclasses.loot import take_loot
        from world.lifecycle import reconcile_room

        reconcile_room(self.caller.location)

        text = self.args.strip()
        corpse = text.startswith("시체에서 ")
        if corpse:
            text = text[len("시체에서 ") :].strip()
        item = None if text == "모두" else find_id(ITEMS, text)
        if text != "모두" and not item:
            raise rules.RuleError(
                "시체에서 모두 가져 · 시체에서 강화 조끼 가져 · 모두 가져 · 회수 부품 가져"
            )
        take_loot(self.caller, item, corpse=corpse)


class Equipment(GameCommand):
    key = "장비"
    category = "성장"
    summary = "현재 착용한 무기와 방어구만 확인합니다."

    def run(self):
        profile = self.caller.profile()
        self.caller.msg(
            "착용 장비\n"
            + "\n".join(
                f"{ITEMS[item]['name']} · 공격 +{ITEMS[item].get('attack', 0)} · 방어 +{ITEMS[item].get('defense', 0)}"
                for item in profile["equipment"].values()
            )
        )
