"""구매 catalog / 매입 category와 legacy/native source/sink 거래 경계."""

from dataclasses import dataclass

from world import rules
from world.content import ITEMS, SHOP_CATALOGS
from world.content.shops import accepts
from world.equipment_service import entity_runtime, resolve_item, selector_label
from world.item_entities import api
from world.item_entities.policy import can_item_operation
from world.item_entities.services import domain_errors, lock_character_items, selected
from world.multiplayer import world_change
from world.targets import item_selector


@dataclass(frozen=True)
class Sale:
    identity: str
    label: str
    quantity: int
    proceeds: int
    rounds: int = 0


def require_shop(character, shop):
    from world.observation import can_perceive, context_for

    if shop.location != character.location or not can_perceive(shop, context_for(character)):
        raise rules.RuleError("이곳에서 상점 상인을 찾지 못했습니다.")
    rules.require_peace(character.profile_snapshot())
    from world.content import ROOMS

    if not ROOMS.get(character.zone, {}).get("safe"):
        raise rules.RuleError("안전한 곳에서만 상점을 이용할 수 있습니다.")
    if shop.db.shop_id not in SHOP_CATALOGS:
        raise rules.RuleError("상점 판매 목록을 확인할 수 없습니다.")


def resale(item):
    identity = item.definition_id if hasattr(item, "definition_id") else item
    definition = ITEMS[identity]
    price = definition.get("resale_unit_value")
    if price is None:
        price = rules.resale_price(identity)
    if type(price) is not int or price < 0:
        raise rules.RuleError("매입 가격이 정의되지 않은 물건입니다.")
    if definition.get("magazine") and hasattr(item, "state"):
        from world.firearms import magazine_resale

        if item.state["rounds"] == 0:
            return magazine_resale(0, price, 0)
        ammo = next(key for key, data in ITEMS.items()
                    if data.get("ammo_type") == definition["magazine"]["ammo_type"])
        return magazine_resale(item.state["rounds"], price, resale(ammo))
    return price


def resolve_sale(character, value):
    return (resolve_item(character, value, "판매") if entity_runtime(character)
            else item_selector(value, ITEMS, "판매"))


def can_accept(shop_id, item):
    identity = item.definition_id if hasattr(item, "definition_id") else item
    return accepts(shop_id, ITEMS.get(identity, {}))


def valuation(character, shop, value):
    require_shop(character, shop)
    try:
        item = resolve_sale(character, value)
    except rules.RuleError:
        item = item_selector(value, ITEMS, "가치")
    if not can_accept(shop.db.shop_id, item):
        raise rules.RuleError("취급하지 않는 물건입니다.")
    return resale(item)


@domain_errors
def buy(character, shop, identity):
    with world_change():
        lock_character_items(character)
        require_shop(character, shop)
        if not entity_runtime(character):
            return character.change(lambda profile: rules.buy(profile, shop.db.shop_id, identity))
        profile = character.profile()
        if identity not in SHOP_CATALOGS[shop.db.shop_id]["purchase_catalog"]:
            raise rules.RuleError("취급하지 않는 물건입니다.")
        price = rules.purchase_price(identity)
        if profile["credits"] < price:
            raise rules.RuleError("보급칩이 부족합니다.")
        profile["credits"] -= price
        if ITEMS[identity].get("firearm_family"):
            from world.firearm_service import create_firearm

            create_firearm(identity, owner_object=character, mode="full_standard")
        else:
            api.create_item(identity, location_kind="inventory", owner_object=character)
        character.save_profile(profile)


@domain_errors
def sell(character, shop, value, quantity=1):
    with world_change():
        locked = lock_character_items(character)
        require_shop(character, shop)
        item = resolve_sale(character, value)
        if not can_accept(shop.db.shop_id, item):
            raise rules.RuleError("취급하지 않는 물건입니다.")
        if not entity_runtime(character):
            count, price = character.change(lambda profile: rules.sell(
                profile, shop.db.shop_id, item, all_items=quantity is None, quantity=quantity))
            return Sale(item, ITEMS[item]["name"], count, price)
        row = selected(locked, item)
        if row.location_kind != "inventory" or row.owner_object_id != character.pk:
            raise rules.RuleError("직접 소지한 물건만 판매할 수 있습니다. 장비는 먼저 해제하세요.")
        if not ITEMS[row.definition_id]["stackable"] and quantity != 1:
            raise rules.RuleError("스택만 수량 또는 모두 판매할 수 있습니다.")
        count = row.quantity if quantity is None else quantity
        price = resale(row) * count
        label = selector_label(character, row)
        rounds = row.state.get("rounds", 0)
        api.destroy_quantity(row, count, operation="sell")
        profile = character.profile()
        profile["credits"] += price
        character.save_profile(profile)
        return Sale(row.definition_id, label, count, price, rounds)


def shop_snapshot(character, shop, observed_at=None):
    """Web과 상품 목록의 구매 후보/매입 후보를 분리한다. 조회로 아이템을 만들지 않는다."""
    from world.equipment import context, inventory_rows

    catalog = SHOP_CATALOGS[shop.db.shop_id]["purchase_catalog"]
    sales = []
    profile = character.profile_snapshot()
    snapshot = context(profile)
    for row in inventory_rows(profile):
        quantity = row["count"]
        if snapshot.source == "legacy":
            quantity -= sum(item.definition_id == row["id"] for item in snapshot.items)
        elif row["equipped"]:
            continue
        if quantity <= 0 or row["location"] != "inventory" or not can_accept(shop.db.shop_id, row["id"]):
            continue
        try:
            item = resolve_sale(character, row["selector"])
            if not can_item_operation(item, "sell"):
                continue
            price = resale(item)
        except rules.RuleError:
            continue
        sales.append((row["selector"], quantity, price, ITEMS[row["id"]]["stackable"] or snapshot.source == "legacy"))
    return catalog, tuple(sales)
