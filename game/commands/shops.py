"""현재 관찰 가능한 판매자 선택. 대상 번호와 조사는 공통 parser를 사용한다."""

from world import rules
from world.content import SHOP_CATALOGS
from world.targets import names, parse_selector, resolve, room_objects


def shopkeepers(caller):
    from typeclasses.interactables import Shopkeeper

    return [obj for obj in room_objects(caller) if isinstance(obj, Shopkeeper)]


def resolve_shopkeeper(caller, name="", item=None, objects=None, action="구매"):
    objects = shopkeepers(caller) if objects is None else objects
    if name.strip():
        known = [n for obj in objects for n in names(obj)]
        return resolve(objects, parse_selector(name, known), caller, "상품")[0]
    from world.content import ITEMS
    from world.content.shops import accepts

    candidates = [obj for obj in objects if item is None or (
        accepts(obj.db.shop_id, ITEMS.get(item, {})) if action in ("판매", "가치")
        else item in SHOP_CATALOGS.get(obj.db.shop_id, {}).get("purchase_catalog", ()))]
    if not candidates:
        raise rules.RuleError("이곳에서 해당 물건을 파는 상인을 찾지 못했습니다." if item else "이곳에서 상점 상인을 찾지 못했습니다.")
    if len(candidates) > 1:
        raise rules.RuleError("상인이 여러 명입니다. 판매자 이름과 번호를 지정하세요.")
    return candidates[0]
