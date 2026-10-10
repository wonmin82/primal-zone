"""공통 행동을 받는 영속 콘텐츠 객체. 진행 상태는 개인 규칙으로 변경한다."""

from evennia.objects.objects import DefaultObject
from world import rules
from world import text as ft
from world.content import ENEMIES, ITEMS, ROOMS, SALVAGE_CREDIT_RATE, SHOP_CATALOGS
from world.currency import format_currency
from world.distant_presentation import DistantPresence, DistantPresenceMixin
from world.progression import ATTRIBUTES, SKILLS


class ActionObject(DistantPresenceMixin, DefaultObject):
    distant_visible = False
    detectability = "subtle"
    actions = ()
    semantic_role = "object"
    presence = "가까이에서 살펴볼 수 있다."
    description = "탐사 중에 발견한 물건이다."

    def get_distant_presence(self, context):
        return DistantPresence(
            self.key,
            self.semantic_role,
            "명" if self.semantic_role == "npc" else "개",
            "멀리 서 있다." if self.semantic_role == "npc" else "멀리 보인다.",
        )

    def return_appearance(self, looker, **kwargs):
        return ft.sheet(
            ft.token(self.semantic_role, self.key), self.description, "", ft.actions(self.actions)
        )

    def at_object_creation(self):
        self.locks.add("get:false();puppet:false()")

    def supports_action(self, action):
        return action in self.actions

    def web_actions(self, caller, target, observed_at=None):
        """기존 Web control allowlist. 성장·보관 조작은 전용 UI/명령을 유지한다."""
        return [
            {"label": action, "command": target + " " + action}
            for action in (("봐",) if isinstance(self, Container) else self.actions)
            if action in ("대화", "조사", "수리", "봐", "회복", "휴식")
            and (action not in ("회복", "휴식") or self.available(caller, observed_at=observed_at))
        ]

    def perform_action(self, caller, action, args=None):
        from world.observation import can_perceive, context_for

        if self.location != caller.location or not self.supports_action(action):
            raise rules.RuleError("이곳에서 그 대상에게 할 수 없는 행동입니다.")
        if not can_perceive(self, context_for(caller)):
            raise rules.RuleError("지금은 그 대상을 식별할 수 없습니다. 광원을 사용하세요.")
        rules.require_peace(caller.profile())
        return self.act(caller, action, args)


class Commander(ActionObject):
    detectability = "conspicuous"
    distant_visible = True
    semantic_role = "npc"
    presence = "낡은 지도를 펼쳐 놓고 탐사대를 기다리고 있다."
    description = "탐사대를 지휘하는 책임자다. 낡은 지도와 무전기를 늘 곁에 두고 있다."
    actions = ("대화",)

    def act(self, caller, action, args):
        from world import presentation as view

        before = caller.profile()
        from world.credential_service import issuer_talk

        result, granted, boss_granted = issuer_talk(caller, "outpost_supply_pass", rules.commander_talk)
        after = caller.profile()
        if result == "start":
            body = ft.text(
                "  장비를 마련하고 관리동의 ",
                content_name("maintenance_log"),
                "을 찾아보게. ",
                content_name("generator"),
                "를 복구하고 ",
                ft.token("hostile", ENEMIES["alpha"]["name"]),
                "를 처치하면 통신탑을 되찾을 수 있네.",
            )
        elif result == "complete":
            body = ft.text(
                ft.token("success", "첫 탐사를 완수했다."),
                "\n통신탑에서 구조 신호가 퍼져 나간다.\n보고를 마치고 ",
                ft.token("reward", f"경험치 {after['xp'] - before['xp']}"),
                ", ",
                ft.token("reward", format_currency(after["credits"] - before["credits"])),
                ", ",
                ft.item("bandage"),
                " 3개를 받았다.",
            )
        else:
            body = view.quest(after)
        if granted:
            body = ft.text(body, "\n", ft.item("outpost_supply_pass"), "을 받았다." if result == "complete" else "을 무료로 재발급받았다.")
        if boss_granted:
            body = ft.text(body, "\n", ft.item("ridge_predator_mark"), "을 받았다.")
        caller.msg(ft.text(ft.token("npc", self.key), "\n\n", body))


class Container(ActionObject):
    """공용 스택 보관 공간. 개인 보관함은 caller의 profile만 사용한다."""

    distant_visible = True
    detectability = "conspicuous"
    personal = False
    actions = ("넣어", "꺼내")
    presence = "벽을 따라 놓여 있다. 물품을 맡기거나 꺼낼 수 있다."
    description = "탐사자들이 함께 쓰는 보관상자다. 넣은 물건은 누구나 꺼낼 수 있다."

    def at_object_creation(self):
        super().at_object_creation()
        self.db.items = {}

    def act(self, caller, action, args):
        from world.item_transfers import transfer

        identity, all_items = args
        return transfer(
            caller, identity, all_items=all_items, container=self, withdraw=action == "꺼내"
        )

    def return_appearance(self, looker, **kwargs):
        from evennia.utils.dbserialize import deserialize
        from world.equipment_service import entity_runtime
        from world.targets import labels, room_objects

        if entity_runtime(looker):
            from world.item_transfer_native import stored_items

            contents = {}
            for row in stored_items(looker, self):
                contents[row.definition_id] = contents.get(row.definition_id, 0) + row.quantity
        else:
            contents = looker.profile_snapshot()["storage"] if self.personal else deserialize(self.db.items)
        label = labels(room_objects(looker)).get(self.id, self.key)
        lines = [self.description]
        lines.extend(
            ft.text(ft.item(identity), f" ×{quantity}") for identity, quantity in contents.items()
        )
        if not contents:
            lines.append("비어 있다.")
        lines.append(ft.text("보관: ", ft.usage(f"{label}에 아이템이름 넣어", {"넣어"})))
        if contents:
            identity = next(iter(contents))
            lines.append(
                ft.text(
                    "회수: ",
                    ft.token("object", label),
                    "에서 ",
                    ft.item(identity),
                    " ",
                    ft.token("command", "꺼내"),
                    " · 아이템 뒤에 모두를 붙이면 스택 전부를 옮긴다.",
                )
            )
        return ft.compact(ft.token("object", label), *lines)


class PersonalLocker(Container):
    distant_visible = True
    personal = True
    description = "탐사자 개인의 물품을 보관한다. 같은 보관함을 사용해도 내용은 각자에게만 보인다."


class MaintenanceLog(ActionObject):
    distant_visible = False
    presence = "젖은 책상 위에 펼쳐져 있다."
    description = "발전기 복구 절차와 현장 전투 기록이 남아 있는 문서다."
    actions = ("조사",)

    def act(self, caller, action, args):
        caller.change(rules.read_record)
        caller.msg(
            ft.text(
                content_name("maintenance_log"),
                "을 펼쳐 복구 절차를 읽었다.\n  ",
                ft.item("generator_repair_part"),
                " 3개로 ",
                content_name("generator"),
                "를 수리하면 능선의 문을 열 수 있다.\n  ",
                ft.named("hostile", ENEMIES["alpha"]["name"], "이/가"),
                " 몸을 낮추면 다음 차례에는 ",
                ft.token("command", "견제"),
                "로 공격을 약화시키고 부상은 치료할 것.",
            )
        )


class SupplyCache(ActionObject):
    presence = "뒤집힌 수송차 틈에 걸려 있다."
    description = "누군가 남긴 보급품이 들어 있는 튼튼한 상자다."
    actions = ("조사",)

    def act(self, caller, action, args):
        profile = caller.profile_snapshot()
        generator_fixed = profile["quests"]["radio_tower"]["generator_fixed"]
        existing_parts = profile["inventory"].get("generator_repair_part", 0)
        caller.change(rules.claim_cache)
        missing_parts = 0 if generator_fixed else max(0, 3 - existing_parts)
        caller.msg(
            ft.text(
                ft.token("object", self.key), "에서 ", ft.item("bandage"), " 2개",
                ft.text(", ", ft.item("generator_repair_part"), f" {missing_parts}개") if missing_parts else "",
                "와 ", ft.item("expedition_tag"), "를 찾아 챙겼다.",
                " 정비용 회수부품은 기존 보유량을 포함해 3개를 확보했다." if existing_parts and not generator_fixed else "",
            )
        )


class Generator(ActionObject):
    detectability = "conspicuous"
    distant_visible = True
    presence = "낡은 외벽 너머로 희미한 경고등을 깜빡이고 있다."
    description = "능선 진입문에 전력을 공급하는 설비다. 정비기록과 부품이 필요하다."
    actions = ("수리",)

    def act(self, caller, action, args):
        before = caller.profile()["xp"]
        from world.facilities import restore_outpost_power

        restore_outpost_power(caller)
        gained = caller.profile()["xp"] - before
        body = ft.text(ft.named("object", self.key, "이/가"),
                       " 다시 돌아가기 시작했다. 공용 조명에 전력이 들어왔다.")
        if gained:
            body = ft.text(body, " 능선 진입문이 열렸다.\n복구 작업으로 ",
                           ft.token("reward", f"경험치 {gained}"), "를 얻었다.")
        caller.msg(body)


def _service_available(obj, caller, observed_at=None):
    from world.observation import can_perceive, context_for

    return (
        obj.location is not None and obj.location == caller.location
        and ROOMS.get(caller.zone, {}).get("safe", False)
        and not caller.profile_snapshot().get("combat_target")
        and can_perceive(obj, context_for(caller, observed_at=observed_at))
    )



class GrowthTrainer(ActionObject):
    detectability = "conspicuous"
    distant_visible = True
    semantic_role = "npc"
    available = _service_available

    @property
    def presence(self):
        return self.db.presence or "탐사자의 훈련을 지도하고 있다."

    @property
    def description(self):
        return self.db.description or "담당 분야의 훈련을 돕는 탐사대 교관이다."

    def return_appearance(self, looker, **kwargs):
        offer, commands = self.training_offer()
        return ft.sheet(ft.token("npc", self.key), self.description, "", offer, "",
                        ft.join([ft.usage(command, set(self.actions) | {"재훈련"}) for command in commands], "\n"))

    def act(self, caller, action, args):
        if action == "대화":
            caller.msg(ft.text(ft.token("npc", self.key), "\n\n", self.db.dialogue or "훈련에는 비용이 들지 않는다."))
        else:
            self.train(caller, action, args)


class SkillTrainer(GrowthTrainer):
    actions = ("대화", "배워")

    def training_offer(self):
        name = SKILLS[self.db.skill_id]["name"]
        return f"이 교관에게서 {name}{ft.particle(name, '을/를')} 배울 수 있다.", (name + " 배워",)

    def train(self, caller, action, skill):
        if action != "배워" or skill != self.db.skill_id:
            raise rules.RuleError("이 교관이 담당하는 기술이 아니다.")
        before = rules.skill_rank(caller.profile(), skill)
        caller.change(lambda profile: rules.learn_skill(profile, skill, safe=self.available(caller)))
        remaining = rules.point_pools(caller.profile())["skill_points"]
        caller.msg(f"{self.key}에게 {SKILLS[skill]['name']}{ft.particle(SKILLS[skill]['name'], '을/를')} 훈련받아 R{before}에서 R{before + 1}로 올랐고 기술 훈련이 {remaining}회 남았다.")

    def web_actions(self, caller, target, observed_at=None):
        if not self.available(caller, observed_at):
            return []
        skill = rules.skill_state(caller.profile_snapshot(), self.db.skill_id)
        return [{"label": skill["name"] + " 배워", "command": f"{target}에게 {skill['name']} 배워"}] if skill["can_learn"] else []


class AttributeTrainer(GrowthTrainer):
    actions = ("대화", "배분")

    def training_offer(self):
        name = ATTRIBUTES[self.db.attribute_id]["name"]
        return f"이 교관에게서 {name}{ft.particle(name, '을/를')} 배분할 수 있다.", (name + " 배분",)

    def train(self, caller, action, args):
        attribute, amount = args
        if action != "배분" or attribute != self.db.attribute_id:
            raise rules.RuleError("이 교관이 담당하는 특성이 아니다.")
        before = 10 + rules.allocated(caller.profile(), attribute)
        caller.change(lambda profile: rules.allocate_attribute(profile, attribute, amount, safe=self.available(caller)))
        remaining = rules.point_pools(caller.profile())["attribute_points"]
        name = ATTRIBUTES[attribute]['name']
        caller.msg(f"{self.key}에게 훈련받아 {name}{ft.particle(name)} {before}에서 {before + amount}{ft.particle(str(before + amount), '으로/로')} 올랐고 특성 포인트가 {remaining}점 남았다.")

    def web_actions(self, caller, target, observed_at=None):
        profile = caller.profile_snapshot()
        if not self.available(caller, observed_at) or rules.point_pools(profile)["attribute_points"] < 1 or rules.allocated(profile, self.db.attribute_id) >= 20:
            return []
        name = ATTRIBUTES[self.db.attribute_id]["name"]
        return [{"label": name + " +1 배분", "command": f"{target}에게 {name} 1 배분"}]


class TrainingManager(GrowthTrainer):
    actions = ("대화", "재분배")

    def training_offer(self):
        return "이 관리관에게서 특성이나 기술 투자를 다시 정리할 수 있다.", ("특성 재분배", "기술 재분배", "전체 재훈련")

    def train(self, caller, action, scope):
        result = caller.change(lambda profile: rules.retrain(profile, scope, safe=self.available(caller)))
        attributes, skills = result["attribute_points"], result["skill_training"]
        message = {
            "attributes": f"특성 투자를 초기화해 특성 포인트 {attributes}점",
            "skills": f"모든 기술을 R1로 초기화해 기술 훈련 {skills}회",
            "all": f"특성과 기술을 모두 초기화해 특성 포인트 {attributes}점과 기술 훈련 {skills}회",
        }[result["scope"]]
        caller.msg(f"{self.key}{ft.particle(self.key)} {message}{ft.particle(message, '을/를')} 다시 사용할 수 있게 했다.")

    def web_actions(self, caller, target, observed_at=None):
        if not self.available(caller, observed_at):
            return []
        return [{"label": text, "command": target + "에게 " + text} for text in ("특성 재분배", "기술 재분배", "전체 재훈련")]


class Doctor(ActionObject):
    semantic_role = "npc"
    detectability = "conspicuous"
    presence = "탐사자의 부상을 살피며 회복을 준비하고 있다."
    description = "보급칩을 받고 부족한 HP를 회복하는 의무관이다. 정신력은 회복하지 않는다."
    actions = ("회복",)
    available = _service_available

    def quote(self, caller, requested=None):
        return rules.treatment_quote(caller.profile_snapshot(), requested,
                                     safe=ROOMS.get(caller.zone, {}).get("safe", False))

    def return_appearance(self, looker, **kwargs):
        lines = [self.description]
        if self.available(looker):
            try:
                restored, cost = self.quote(looker)
                lines.append(f"현재 HP {restored} 전체 회복 예상 비용: {cost}칩 (실행 시 재계산)")
            except rules.RuleError as error:
                lines.append(str(error))
            lines.append("회복 · 20 회복 · 의무관에게 20 회복 / 회복실 침대 휴식은 무료")
        return ft.sheet(ft.token(self.semantic_role, self.key), *lines)

    def web_actions(self, caller, target, observed_at=None):
        if not self.available(caller, observed_at):
            return []
        try:
            restored, cost = self.quote(caller)
        except rules.RuleError:
            return []
        return [{"label": f"HP {restored} 회복 · 예상 {cost}칩", "command": target + " 회복"}]

    def act(self, caller, action, args):
        quoted_hp, quoted_cost = self.quote(caller, args)
        caller.msg(f"요청 HP {quoted_hp} 회복 예상 비용: {quoted_cost}칩 (실행 시 재계산)")
        from world.multiplayer import world_change

        # 유료 서비스는 SP 자연회복 checkpoint와 분리한다. 조회/실패/성공 모두
        # 요청 자체가 정신력을 증가시키지 않으며 scheduler의 회복은 독립적이다.
        with world_change():
            profile = caller.profile()
            restored, cost = rules.treat(profile, args, safe=ROOMS.get(caller.zone, {}).get("safe", False))
            caller.save_profile(profile)
        caller.msg(f"HP {restored} 회복 · 비용 {cost}칩을 지불했습니다. 정신력은 회복하지 않습니다.")


class Bed(ActionObject):
    detectability = "conspicuous"
    presence = "깨끗한 시트와 담요로 정돈되어 있다."
    description = "몸을 눕히고 회복할 수 있는 의료용 침대다."
    actions = ("휴식",)
    available = _service_available

    def return_appearance(self, looker, **kwargs):
        return ft.sheet(ft.token(self.semantic_role, self.key), self.description, "",
                        ft.actions(self.actions if self.available(looker) else ()))

    def act(self, caller, action, args):
        caller.change(lambda profile: rules.rest(profile, safe=ROOMS.get(caller.zone, {}).get("safe", False)))
        caller.msg("침대에서 휴식하며 체력과 정신력을 모두 회복했습니다.")


class SettlementOfficer(ActionObject):
    semantic_role = "npc"
    detectability = "conspicuous"
    presence = "탐사에서 회수한 물자를 확인하며 정산을 준비하고 있다."
    description = "회수부품을 보급칩으로 정산하는 담당자다."
    actions = ("환율", "교환")

    available = _service_available

    def web_actions(self, caller, target, observed_at=None):
        if not self.available(caller, observed_at):
            return []
        actions = [{"label": "환율", "command": target + " 환율"}]
        if caller.profile_snapshot()["inventory"].get("scrap", 0) > 0:
            resource = ITEMS["scrap"]["name"]
            actions.append({"label": resource + " 모두 교환", "command": target + "에게 " + resource + " 모두 교환"})
        return actions

    def return_appearance(self, looker, **kwargs):
        from world.targets import labels, room_objects

        usage = ""
        if self.available(looker):
            target = labels(room_objects(looker))[self.id]
            usage = ft.join([ft.usage(command, set(self.actions)) for command in (
                f"{target} 환율", "회수부품 교환", "회수부품 10개 교환", "회수부품 모두 교환",
                f"{target}에게 회수부품 10개 교환",
            )], " · ")
        return ft.sheet(ft.token(self.semantic_role, self.key), self.description, "", usage)

    def act(self, caller, action, args):
        if not ROOMS.get(caller.zone, {}).get("safe", False):
            raise rules.RuleError("안전한 곳에서만 자원을 정산할 수 있습니다.")
        if action == "환율":
            caller.msg(ft.text(ft.item("scrap"), f" 1개 → {format_currency(SALVAGE_CREDIT_RATE)}"))
            return

        def settle(profile):
            quantity = profile["inventory"].get("scrap", 0) if args is None else args
            if args is None and not quantity:
                raise rules.RuleError("정산할 회수부품이 없습니다.")
            return quantity, rules.settle_salvage(profile, quantity)

        quantity, earned = caller.change(settle)
        caller.msg(ft.text(ft.item("scrap"), f" {quantity}개를 정산했다. {format_currency(earned)}을 받았다."))


class Shopkeeper(ActionObject):
    semantic_role = "npc"
    detectability = "conspicuous"
    presence = "판매대에서 탐사 장비와 보급품을 정리하고 있다."
    description = "탐사자를 위한 물품을 보급칩으로 판매하는 상인이다."
    actions = ("대화", "목록", "사", "가치", "팔아")

    def available(self, caller, observed_at=None):
        return _service_available(self, caller, observed_at) and self.db.shop_id in SHOP_CATALOGS

    def web_actions(self, caller, target, observed_at=None):
        if not self.available(caller, observed_at):
            return []
        from world.shop_service import shop_snapshot

        catalog, sales = shop_snapshot(caller, self, observed_at)
        actions = [{"label": "목록", "command": target + " 목록"}]
        for item in catalog:
            name = ITEMS[item]["name"]
            unit = f" ×{ITEMS[item]['purchase_quantity']}발" if ITEMS[item].get("purchase_quantity", 1) != 1 else ""
            actions.extend(({"label": f"{name}{unit} · {format_currency(rules.purchase_price(item))} 사",
                             "command": f"{target}에게 {name} 사"},
                            {"label": name + " 가치", "command": f"{target}에게 {name} 가치"}))
        for name, quantity, price, stackable in sales:
            actions.append({"label": f"{name} · {format_currency(price)} 팔아", "command": f"{target}에게 {name} 팔아"})
            if stackable and quantity >= 2:
                actions.append({"label": f"{name} 모두 팔아 · 총 {format_currency(quantity * price)}",
                                "command": f"{target}에게 {name} 모두 팔아"})
        return actions

    def return_appearance(self, looker, **kwargs):
        from world.targets import labels, room_objects

        usage = ""
        if self.available(looker):
            target = labels(room_objects(looker))[self.id]
            usage = ft.join([ft.usage(command, set(self.actions)) for command in (
                f"{target} 목록", f"{target}에게 물건이름 사", f"{target}에게 물건이름 가치", f"{target}에게 물건이름 팔아",
            )], " · ")
        return ft.sheet(ft.token("npc", self.key), self.description, "", usage)

    def act(self, caller, action, args):
        from world import presentation as view

        if not ROOMS.get(caller.zone, {}).get("safe", False):
            raise rules.RuleError("안전한 곳에서만 상점을 이용할 수 있습니다.")
        if self.db.shop_id not in SHOP_CATALOGS:
            raise rules.RuleError("상점 판매 목록을 확인할 수 없습니다.")
        if action == "목록":
            caller.msg(view.shop(self.db.shop_id, self.key))
        elif action == "사":
            from world.shop_service import buy

            buy(caller, self, args)
            quantity = ITEMS[args].get("purchase_quantity", 1)
            caller.msg(ft.text(ft.item(args), f" {quantity}개를 받아 소지품에 넣었다."))
        elif action == "가치":
            from world.shop_service import valuation

            name, _quantity = args
            price = valuation(caller, self, name)
            from world.content.items import find_id
            from world.targets import parse_selector

            identity = find_id(ITEMS, parse_selector(name).name)
            try:
                purchase = rules.purchase_price(identity)
            except rules.RuleError:
                purchase = None
            caller.msg(ft.text(ft.token("npc", self.key), "은 ", ft.token("item", name), "의 가치를 평가한다.\n",
                               f"구매 기준가는 {format_currency(purchase)}이다.\n" if purchase else "",
                               "매입가는 ", ft.token("reward", format_currency(price)), "이다."))
        elif action == "팔아":
            from world.shop_service import sell

            result = sell(caller, self, *args)
            caller.msg(ft.text(ft.token("npc", self.key), "이 ", ft.token("item", result.label),
                               f" {result.quantity}개를 ", ft.token("reward", format_currency(result.proceeds)), "에 매입했다.",
                               f"\n잔탄 {result.rounds}발의 가치가 포함되었다." if result.rounds else ""))
        else:
            caller.msg(ft.text(ft.token("npc", self.key), "\n\n필요한 물품과 구매 단위는 판매 목록을 살펴보세요."))


class Incinerator(ActionObject):
    detectability = "conspicuous"
    description = "불필요한 물품을 폐기한다. 출입증은 소각 확정이 필요하며 원래 발급자에게 재발급받을 수 있다."
    presence = "밀폐된 소각로에서 낮은 열기가 느껴진다."
    actions = ("봐",)

    def act(self, caller, action, args):
        caller.msg(self.return_appearance(caller))


class Pathfinder(ActionObject):
    detectability = "conspicuous"
    distant_visible = True
    semantic_role = "npc"
    presence = "젖은 지도 위에 선발대의 이동 경로를 표시하고 있다."
    description = "밀림에서 돌아온 선발대 길잡이다. 두 갈래 탐사로의 표식을 찾고 있다."
    actions = ("대화",)

    def act(self, caller, action, args):
        before = caller.profile()
        from world.credential_service import issuer_talk

        result, granted, boss_granted = issuer_talk(caller, "special_supply_pass", rules.jungle_talk)
        after = caller.profile()
        if result == "start":
            body = "관측소와 수몰 도로의 표식을 확인해 주세요. 두 기록을 맞추면 거목의 신호 장치가 연구구역 길을 열 겁니다."
        elif result == "complete":
            body = ft.text(
                ft.token("success", "밀림의 탐사를 마쳤다."), " 보고를 마치고 ",
                ft.token("reward", f"경험치 {after['xp'] - before['xp']}"), ", ",
                ft.token("reward", format_currency(after["credits"] - before["credits"])),
                ", ", ft.item("bandage"), " 3개를 받았다.",
            )
        else:
            from world import presentation as view
            body = view.quest(after)
        if granted:
            body = ft.text(body, "\n", ft.item("special_supply_pass"), "을 받았다." if result == "complete" else "을 무료로 재발급받았다.")
        if boss_granted:
            body = ft.text(body, "\n", ft.item("predator_scale_charm"), "을 받았다.")
        caller.msg(ft.text(ft.token("npc", self.key), "\n\n", body))


class JungleMarker(ActionObject):
    distant_visible = False
    presence = "나무와 돌에 선발대의 흔적이 남아 있다."
    description = "선발대가 길을 잃지 않도록 남긴 현장 표식이다."
    actions = ("조사",)
    quest_flag = None

    def act(self, caller, action, args):
        newly_marked = caller.change(lambda profile: rules.jungle_mark(profile, self.quest_flag))
        caller.msg(ft.text(ft.token("object", self.key), "을 살펴 선발대의 경로를 확인했다."))
        return newly_marked


class WatchMarker(JungleMarker):
    quest_flag = "watch_marked"


class WaterMarker(JungleMarker):
    quest_flag = "road_marked"

    def act(self, caller, action, args):
        if super().act(caller, action, args):
            caller.msg(ft.text("표식 아래에서 ", ft.item("jungle_cell"), "를 확보했다."))


class SignalDevice(ActionObject):
    detectability = "conspicuous"
    distant_visible = True
    presence = "출입문 옆에서 신호등을 깜빡이고 있다."
    description = "두 탐사 표식의 좌표를 맞추면 연구구역의 문을 열 수 있다."
    actions = ("조사",)

    def act(self, caller, action, args):
        caller.change(rules.open_jungle_gate)
        caller.msg(ft.text(ft.item("jungle_cell"), "로 ", ft.token("object", self.key), "의 좌표를 맞추자 연구구역의 문이 열렸다."))


class JungleCache(ActionObject):
    presence = "검은 물가에 반쯤 잠겨 있다."
    description = "선발대가 늪을 지날 때 남긴 작은 보급 주머니다."
    actions = ("조사",)

    def act(self, caller, action, args):
        caller.change(rules.claim_jungle_cache)
        caller.msg(ft.text(ft.token("object", self.key), "에서 ", ft.item("bandage"), " 2개, ", ft.item("battery"), " 2개와 ",
                           ft.item("mental_stability_module"), "을 찾아 챙겼다."))


class EmergencyLightCache(ActionObject):
    detectability = "conspicuous"
    presence = "수송차 옆에 놓여 있다. 어둠 속에서도 큼직한 반사 표식이 눈에 띈다."
    description = "탐사자용 손전등과 예비 전원이 든 비상 장비함이다. 각 탐사자가 한 번씩 받을 수 있다."
    actions = ("조사",)

    def act(self, caller, action, args):
        caller.change(rules.claim_emergency_light_cache)
        caller.msg(ft.text(ft.item("flashlight"), " 한 개와 ", ft.item("battery"), " 두 개를 챙겼다."))


def action_objects(room):
    from world.targets import ordered

    return ordered(obj for obj in room.contents if isinstance(obj, ActionObject)) if room else []


def instructor_for(caller, observed_at=None):
    from world.targets import room_objects

    return next(
        (obj for obj in room_objects(caller, observed_at=observed_at)
         if isinstance(obj, GrowthTrainer) and obj.available(caller, observed_at=observed_at)), None
    )


def growth_controls(caller, observed_at=None):
    """전용 패널도 실제 NPC가 생성한 명령만 사용한다. 중복 provider는 자동 선택하지 않는다."""
    from world.targets import labels, room_objects

    objects = room_objects(caller, observed_at=observed_at)
    targets = labels(objects)
    grouped = {}
    for obj in objects:
        if not isinstance(obj, GrowthTrainer) or not obj.available(caller, observed_at):
            continue
        key = obj.db.skill_id if isinstance(obj, SkillTrainer) else obj.db.attribute_id if isinstance(obj, AttributeTrainer) else "reset"
        grouped.setdefault(key, []).append(obj.web_actions(caller, targets[obj.id], observed_at))
    return {key: values[0] for key, values in grouped.items() if len(values) == 1}


INTERACTABLES = {
    "outpost_equipment_shopkeeper": {"room": "outpost_equipment", "typeclass": "Shopkeeper", "name": "전초 장비관", "aliases": ["장비관"], "shop_id": "outpost_equipment"},
    "outpost_weapon_shopkeeper": {"room": "outpost_weapon", "typeclass": "Shopkeeper", "name": "전초 병기관", "aliases": ["병기관"], "shop_id": "outpost_weapon"},
    "incinerator": {"room": "salvage_office", "typeclass": "Incinerator", "name": "폐기물 소각기", "aliases": ["소각기"]},
    "supply_shopkeeper": {"room": "supply_shop", "typeclass": "Shopkeeper", "name": "보급관", "aliases": ["보급상인"], "shop_id": "supply"},
    "weapon_shopkeeper": {"room": "weapon_shop", "typeclass": "Shopkeeper", "name": "무기상", "aliases": ["무기 상인"], "shop_id": "weapon"},
    "armor_shopkeeper": {"room": "armor_shop", "typeclass": "Shopkeeper", "name": "방어구상", "aliases": ["방어구 상인"], "shop_id": "armor"},
    "salvage_officer": {"room": "salvage_office", "typeclass": "SettlementOfficer", "name": "자원 정산관", "aliases": ["정산관"]},
    "doctor": {"room": "infirmary", "typeclass": "Doctor", "name": "의무관", "aliases": ["의사"]},
    "infirmary_bed": {"room": "recovery_room", "typeclass": "Bed", "name": "침대", "aliases": ["병상"]},
    "emergency_light_cache": {"room": "wreck", "typeclass": "EmergencyLightCache", "name": "비상장비함", "aliases": ["비상함", "장비함"]},
    "shared_container": {"room": "storage_room", "typeclass": "Container", "name": "보관상자", "aliases": []},
    "personal_locker": {"room": "storage_room", "typeclass": "PersonalLocker", "name": "개인 보관함", "aliases": ["보관함"]},
    "commander": {"room": "dock", "typeclass": "Commander", "name": "윤대장", "aliases": ["대장"]},
    "instructor": {"room": "training_office", "typeclass": "TrainingManager", "name": "훈련관리관", "aliases": ["훈련관", "관리관"]},
    "maintenance_log": {"room": "office", "typeclass": "MaintenanceLog", "name": "정비기록", "aliases": ["기록"]},
    "supply_cache": {"room": "wreck", "typeclass": "SupplyCache", "name": "보급상자", "aliases": ["상자"]},
    "generator": {"room": "generator", "typeclass": "Generator", "name": "발전기", "aliases": []},
    "pathfinder": {"room": "jungle_edge", "typeclass": "Pathfinder", "name": "선발대 길잡이", "aliases": ["길잡이"]},
    "watch_marker": {"room": "jungle_watch", "typeclass": "WatchMarker", "name": "관측 표식", "aliases": ["표식"]},
    "water_marker": {"room": "jungle_road", "typeclass": "WaterMarker", "name": "수위 표식", "aliases": ["표식"]},
    "signal_device": {"room": "jungle_grove", "typeclass": "SignalDevice", "name": "신호 장치", "aliases": ["장치"]},
    "jungle_cache": {"room": "jungle_fen", "typeclass": "JungleCache", "name": "늪지 보급품", "aliases": ["보급품"]},
}


for skill, room, name in (
    ("attack", "training_room", "전투교관"), ("defense", "survival_training_room", "방호교관"),
    ("heavy", "training_room", "타격교관"), ("heal", "medical_training_room", "의무교관"),
    ("shooting", "shooting_range", "사격교관"), ("insight", "shooting_range", "정밀전술교관"),
    ("suppress", "tactics_room", "전술교관"), ("breathing", "survival_training_room", "정신훈련관"),
):
    INTERACTABLES["trainer_" + skill] = {"room": room, "typeclass": "SkillTrainer", "name": name, "aliases": [], "skill_id": skill}
for attribute, room, name in (
    ("strength", "training_room", "근력교관"), ("agility", "shooting_range", "기동교관"),
    ("constitution", "survival_training_room", "체력교관"), ("wisdom", "tactics_room", "분석교관"),
):
    INTERACTABLES["trainer_" + attribute] = {"room": room, "typeclass": "AttributeTrainer", "name": name, "aliases": [], "attribute_id": attribute}


for identity, presence, description, dialogue in (
    ("trainer_attack", "훈련생의 자세를 바로잡으며 기본 동작을 반복시키고 있다.", "기본 공격과 실전 동작을 다듬는 전투 훈련을 담당한다.", "서두르지 말고 발부터 안정시키세요. 익숙한 동작을 정확히 반복하는 것이 실전의 시작입니다."),
    ("trainer_defense", "보호판을 두드리며 충격을 흘리는 자세를 보여 주고 있다.", "피해를 흘리고 충격을 줄이는 방호 훈련을 담당한다.", "충격을 정면으로 버티려고만 하지 마세요. 몸의 각도와 발의 위치가 버틸 힘을 만들어 줍니다."),
    ("trainer_heavy", "무게추를 옮기며 짧게 힘을 모으는 동작을 보여 주고 있다.", "순간적으로 힘을 집중하는 전투 훈련을 담당하는 교관이다.", "세게 휘두르는 것과 강하게 때리는 건 다릅니다. 힘을 모으는 순간이 짧을수록 빈틈도 줄어듭니다."),
    ("trainer_heal", "처치 모형 곁에서 부상 대응 절차를 지도하고 있다.", "전투 중 부상을 살피고 치료하는 훈련을 담당한다.", "상처가 깊어지기 전에 동료의 상태를 살피세요. 무리한 공격보다 제때의 치료가 탐사대를 지켜 줍니다."),
    ("trainer_shooting", "사격선에서 총기 자세와 표적을 번갈아 확인하고 있다.", "안전한 총기 취급과 정확한 사격 동작을 지도한다.", "방아쇠를 당기기 전에 자세와 사선을 확인하세요. 흔들리지 않는 한 발이 급한 여러 발보다 낫습니다."),
    ("trainer_insight", "표적에 표시된 취약 지점을 짚으며 움직임을 설명하고 있다.", "상대의 움직임과 취약 지점을 읽는 전투 분석을 지도한다.", "공격을 잠시 멈추고 상대의 버릇을 보세요. 작은 빈틈을 읽으면 다음 공격의 기회를 더 잘 살릴 수 있습니다."),
    ("trainer_suppress", "모형 사이를 움직이며 상대를 압박하는 동작을 설명하고 있다.", "상대의 공격 흐름을 끊고 압박하는 전술 훈련을 담당한다.", "견제는 상대의 다음 행동을 어렵게 만드는 일입니다. 동료와 압박을 나누되 자신의 빈틈도 살피세요."),
    ("trainer_breathing", "조용히 호흡을 맞추며 훈련생의 긴장을 풀어 주고 있다.", "전투 중 호흡과 정신 집중을 유지하는 훈련을 담당한다.", "정신력이 바닥난 뒤에 숨을 고르려 하면 늦습니다. 공격할 순간과 호흡을 가다듬을 순간을 구분하세요."),
    ("trainer_strength", "들어 올린 중량을 천천히 내려놓으며 자세를 보여 주고 있다.", "근력과 힘 전달을 효율적으로 사용하는 훈련을 담당한다.", "무게를 버티는 힘과 전달하는 힘을 함께 기르세요. 기본 자세를 지켜야 몸을 다치지 않습니다."),
    ("trainer_agility", "표적 사이에 놓인 발판을 빠르게 오가고 있다.", "균형을 잡고 빠르게 움직이는 기동 훈련을 담당한다.", "빠른 발보다 먼저 필요한 건 다음 발을 둘 자리입니다. 시선을 들고 균형을 유지하세요."),
    ("trainer_constitution", "훈련생의 호흡과 회복 상태를 살피고 있다.", "긴 탐사를 버틸 체력과 몸의 안정성을 기르는 훈련을 담당한다.", "지치기 전에 자신의 몸을 알아야 합니다. 꾸준한 훈련과 충분한 휴식이 긴 탐사를 버티게 해 줍니다."),
    ("trainer_wisdom", "지형 모형에 표시를 옮기며 주변 상황을 설명하고 있다.", "위험한 상황에서 주변 정보를 빠르게 정리하고 올바른 판단을 내리는 훈련을 담당한다.", "눈앞의 움직임만 쫓지 마세요. 상대와 주변 상황을 함께 읽어야 다음 행동을 먼저 준비할 수 있습니다."),
    ("instructor", "탐사자의 훈련 기록을 펼쳐 놓고 다음 계획을 정리하고 있다.", "탐사자들의 훈련 기록과 성장 계획을 관리한다.", "투자 방향을 다시 정하고 싶다면 찾아오세요. 특성 재분배, 기술 재분배와 전체 재훈련에는 비용이 들지 않습니다."),
):
    INTERACTABLES[identity].update(presence=presence, description=description, dialogue=dialogue)


for definition in INTERACTABLES.values():
    definition["actions"] = globals()[definition["typeclass"]].actions


def content_name(identity):
    """콘텐츠 정의의 실제 이름과 타입으로 대화/임무에서 대상을 표현한다."""
    definition = INTERACTABLES[identity]
    cls = globals()[definition["typeclass"]]
    return ft.token(cls.semantic_role, definition["name"])
