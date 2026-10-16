"""M01/M02 운영 콘텐츠 선언. 효과·후보 선택·웹은 공통 Action 경계로 연결한다."""

import re

from world.actions import room_npc_services as handlers
from world.actions.room_npc_presentation import render
from world.actions.schema import (
    ActionBinding,
    ActionDefinition,
    ArgumentDefinition,
    ContentPackage,
    DefaultTargetPolicy,
    ReferenceKind,
    RoleDefinition,
    ServiceDefinition,
    SyntaxVariant,
    VerbDefinition,
)
from world.content import ITEMS, SHOP_CATALOGS
from world.content.shops import accepts
from world.progression import ATTRIBUTES, SKILLS
from world.targets import normalized

PROVIDER = RoleDefinition("provider", (ReferenceKind.OBJECT,), required=False)
ITEM = RoleDefinition("subject", (ReferenceKind.ITEM,), DefaultTargetPolicy.FIRST_LEGACY_ORDER)
CONFIG = (ArgumentDefinition("effect", required=False), ArgumentDefinition("operation", required=False),
          ArgumentDefinition("peaceful", bool, default=True), ArgumentDefinition("changed", bool, default=True))
VERB_IDS = {'조사': 'inspect', '수리': 'repair', '열어': 'open', '닫아': 'close', '잠궈': 'lock', '풀어': 'unlock', '소각': 'burn', '회복': 'treat', '배워': 'learn', '배분': 'allocate', '휴식': 'rest', '목록': 'list', '사': 'buy', '팔아': 'sell', '가치': 'value', '재분배': 'retrain', '교환': 'exchange', '환율': 'rate'}
verbs, actions, bindings = [], [], []
services = [ServiceDefinition("room_npc.effect", handlers.object_effect, config_schema=CONFIG, presenter=render)]


def literal(value):
    """기존 find_id와 같은 공백·구두점·ASCII 대소문자 정규화를 선언한다."""
    ignored = r"[\s.\-_]*"
    tokens = []
    for char in normalized(value):
        tokens.append("[" + char + char.upper() + "]" if char.isascii() and char.isalpha() else re.escape(char))
    return ignored + ignored.join(tokens) + ignored


def verb(key, aliases=()):
    identity = "game." + VERB_IDS[key]
    from world.actions.room_npc_help import DIAGNOSTICS, HELP

    spec = HELP[key]
    verbs.append(VerbDefinition(identity, key, aliases, spec.summary, spec.usage, spec.category, spec.sections, **DIAGNOSTICS.get(key, {})))
    return identity


def effect(identity, key, provider, pattern, function, arguments=(), *, required=False, changed=True, variants=None,
           subjects=(), service="room_npc.effect"):
    role = RoleDefinition("provider", (ReferenceKind.OBJECT,), required=required)
    actions.append(ActionDefinition(identity, "game." + VERB_IDS[key], (role, *subjects),
                                    variants or (SyntaxVariant("normal", pattern),), arguments,
                                    help=f"현재 위치의 제공자에게 {key} 행동을 요청합니다."))
    bindings.append(ActionBinding(identity + ".binding", provider, identity, service,
                                  (("effect", function), ("operation", key), ("changed", changed))))


for key in ("조사", "수리", "열어", "닫아", "잠궈", "풀어", "소각", "회복", "배워", "배분"):
    verb(key)
for key, aliases in (("휴식", ("rest",)), ("목록", ("품목", "품", "목", "메뉴")),
                     ("사", ("구입",)), ("팔아", ("팔", "판")), ("가치", ("얼마",)),
                     ("재분배", ("재훈련",)), ("교환", ("exchange",)), ("환율", ("rate",))):
    verb(key, aliases)

for function in ("adminkeycabinet", "maintenancelog", "supplycache", "junglemarker", "watermarker",
                 "signaldevice", "junglecache", "emergencylightcache", "generator"):
    key = "수리" if function == "generator" else "조사"
    effect("world." + function, key, "world." + function, r"(?P<provider>.+)", function, required=True)

services.append(ServiceDefinition("room_npc.door", handlers.door, config_schema=CONFIG, presenter=render))
for key in ("열어", "닫아", "잠궈", "풀어"):
    identity = "door." + VERB_IDS[key]
    actions.append(ActionDefinition(identity, "game." + VERB_IDS[key],
                                    (RoleDefinition("provider", (ReferenceKind.DOOR,)),),
                                    (SyntaxVariant("normal", r"(?P<provider>.+)"),),
                                    help="문 이름·방향·고정 번호로 문을 지정합니다. 대상 생략은 거절합니다."))
    bindings.append(ActionBinding(identity + ".binding", "world.door", identity, "room_npc.door", (("operation", key),)))

effect("medical.rest", "휴식", "world.bed", r"(?P<provider>.+?)(?:에서)?|", "bed")
# bare 숫자/부호 입력과 이름 기반 Provider 입력을 정적으로 비중첩인 Variant로 분리한다.
effect("medical.treat", "회복", "world.doctor", "", "doctor",
       (ArgumentDefinition("value", required=False),),
       variants=(SyntaxVariant("normal", r"(?P<provider>[^0-9+\-.].*?)(?:에게(?: (?P<value>[^ ]+))?)?"),
                 SyntaxVariant("amount", r"(?P<value>[0-9+\-.][^ ]*)?", show_control=False)))

effect("settlement.rate", "환율", "world.settlementofficer", r"(?P<provider>.+)|", "settlementofficer", changed=False)
services.append(ServiceDefinition("room_npc.settle", handlers.settle, config_schema=CONFIG, presenter=render))
salvage = RoleDefinition("source", (ReferenceKind.INVENTORY,), required=False, definition_ids=("scrap",))
# 집계 문법은 안정 Inventory Source와 UUID 집합 버전을 전달한다. 개별 Item 번호는 사용하지 않는다.
effect("settlement.exchange", "교환", "world.settlementofficer",
       r"(?:(?P<provider>.+)에게 )?(?:회수\s*부품|scrap)(?: (?P<value>[0-9]+)(?:개)?)?", "settlementofficer",
       (ArgumentDefinition("value", int, default=1, minimum=1), ArgumentDefinition("snapshot", default="")), subjects=(salvage,), service="room_npc.settle",
       variants=(SyntaxVariant("normal", r"(?:(?P<provider>.+)에게 )?(?:회수\s*부품|scrap)(?: (?P<value>[0-9]+)(?:개)?)?", show_control=False),))
effect("settlement.all", "교환", "world.settlementofficer",
       r"(?:(?P<provider>.+)에게 )?(?:회수\s*부품|scrap) 모두", "settlementofficer",
       (ArgumentDefinition("snapshot", default=""),), subjects=(salvage,), service="room_npc.settle")

for identity, data in SKILLS.items():
    effect("training.skill." + identity, "배워", "skill." + identity,
           r"(?:(?P<provider>.+)에게 )?(?:" + literal(data["name"]) + "|" + literal(identity) + ")",
           "skilltrainer", (ArgumentDefinition("value", default=identity, choices=(identity,)),))
for identity, data in ATTRIBUTES.items():
    effect("training.attribute." + identity, "배분", "attribute." + identity,
           r"(?:(?P<provider>.+)에게 )?(?:" + literal(data["name"]) + "|" + literal(identity) + r")(?: (?P<amount>[+-]?[0-9]+))?",
           "attributetrainer", (ArgumentDefinition("value", default=identity, choices=(identity,)), ArgumentDefinition("amount", int, default=1)))
for name, scope in (("특성", "attributes"), ("기술", "skills"), ("전체", "all")):
    effect("training.reset." + scope, "재분배", "world.trainingmanager",
           r"(?:(?P<provider>.+)에게 )?" + name, "trainingmanager", (ArgumentDefinition("value", default=scope, choices=(scope,)),))

services.extend((ServiceDefinition("room_npc.buy", handlers.buy, config_schema=CONFIG, presenter=render),
                 ServiceDefinition("room_npc.value", handlers.value, config_schema=CONFIG, presenter=render),
                 ServiceDefinition("room_npc.sell", handlers.sell, config_schema=CONFIG, presenter=render),
                 ServiceDefinition("room_npc.burn", handlers.burn, config_schema=CONFIG, presenter=render)))
for shop, catalog in SHOP_CATALOGS.items():
    effect("shop.menu." + shop, "목록", "shop." + shop, r"(?P<provider>.+)|", "shopkeeper", changed=False)
    accepted = tuple(identity for identity, data in ITEMS.items() if accepts(shop, data))
    identity = "shop.sell." + shop
    subject = RoleDefinition("subject", (ReferenceKind.ITEM,), DefaultTargetPolicy.FIRST_LEGACY_ORDER,
                             definition_ids=accepted)
    actions.append(ActionDefinition(identity, "game.sell", (PROVIDER, subject),
                                    (SyntaxVariant("normal", r"(?:(?P<provider>.+)에게 )?(?P<subject>.+?)(?: (?P<count>[0-9]+개|모두))?"),),
                                    (ArgumentDefinition("count", default="1"),),
                                    help="소지한 실제 ItemEntity를 1개·N개·모두 판매합니다. 장비는 먼저 해제하세요."))
    bindings.append(ActionBinding(identity + ".binding", "shop." + shop, identity, "room_npc.sell"))

for item, data in ITEMS.items():
    for key, method, shops in (
        ("사", "buy", tuple(shop for shop, c in SHOP_CATALOGS.items() if item in c["purchase_catalog"])),
        ("가치", "value", tuple(shop for shop in SHOP_CATALOGS if accepts(shop, data))),
    ):
        if not shops:
            continue
        identity = "shop." + method + "." + item
        names = tuple(dict.fromkeys((data["name"], item, *data.get("aliases", ()))))
        pattern = r"(?:(?P<provider>.+)에게 )?(?:" + "|".join(literal(name) for name in names) + ")"
        roles = (PROVIDER,)
        variants = (SyntaxVariant("normal", pattern + (r"(?: (?P<count>[0-9]+개|모두))?" if method == "value" else "")),)
        if method == "value":
            roles = (PROVIDER, RoleDefinition("subject", (ReferenceKind.ITEM,), DefaultTargetPolicy.FIRST_LEGACY_ORDER,
                                              required=False, definition_ids=(item,)))
            item_pattern = "(?:" + "|".join(literal(name) for name in names) + ")"
            variants += (SyntaxVariant("numbered", r"(?:(?P<provider>.+)에게 )?(?P<subject>" + item_pattern + r" [0-9]+)(?: (?P<count>[0-9]+개|모두))?", show_control=False),)
        actions.append(ActionDefinition(identity, "game." + VERB_IDS[key], roles, variants,
                                        (ArgumentDefinition("value", default=item, choices=(item,)), *((ArgumentDefinition("count", default="1"),) if method == "value" else ())), help=f"상인에게 {data['name']} {key}"))
        for shop in shops:
            bindings.append(ActionBinding(identity + "." + shop, "shop." + shop, identity, "room_npc." + method))

actions.append(ActionDefinition("incinerator.burn", "game.burn", (PROVIDER, ITEM),
                                (SyntaxVariant("normal", r"(?P<subject>.+?)(?: (?P<count>[0-9]+개|모두))?"),
                                 SyntaxVariant("confirmed", r"(?P<subject>.+)", suffix="확정", confirmation_required=True)),
                                (ArgumentDefinition("count", default="1"),),
                                help="직접 소지한 물품을 폐기합니다. 출입증은 명시적인 소각 확정이 필요합니다."))
bindings.append(ActionBinding("incinerator.burn.binding", "world.incinerator", "incinerator.burn", "room_npc.burn"))

PACKAGE = ContentPackage("game.room_npc", tuple(verbs), tuple(actions), tuple(services), tuple(bindings))
