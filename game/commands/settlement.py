"""실제 정산관에 위임하는 자원 정산 명령."""

from world import rules
from world.settlement import parse_salvage
from world.targets import names, parse_relation, parse_selector, resolve, room_objects

from commands.base import GameCommand


def officers(caller):
    from typeclasses.interactables import SettlementOfficer

    return [obj for obj in room_objects(caller) if isinstance(obj, SettlementOfficer)]


def resolve_officer(caller, action, name="", objects=None):
    objects = officers(caller) if objects is None else objects
    if not name.strip():
        if not objects:
            raise rules.RuleError("이곳에서 이용할 정산관을 찾지 못했습니다. '보기'로 주변을 살펴보세요.")
        if len(objects) > 1:
            raise rules.RuleError("정산관이 여러 명입니다. 대상 이름과 번호를 지정하세요.")
        return objects[0]
    known = [n for obj in objects for n in names(obj)]
    return resolve(objects, parse_selector(name, known), caller, action)[0]


class Exchange(GameCommand):
    category = "아이템·보급"
    input_style = "target"
    key = "교환"
    aliases = ["exchange"]
    usage = "회수부품 교환 · 회수부품 10개 교환 · 회수부품 모두 교환 · 정산관에게 회수부품 교환"
    summary = "주변 정산관에게 회수부품을 크레딧으로 정산합니다."

    def run(self):
        objects = officers(self.caller)
        name, resource = "", self.args
        if any(word.endswith("에게") for word in resource.split()):
            selector, resource = parse_relation(resource, "에게", [n for obj in objects for n in names(obj)])
            obj = resolve(objects, selector, self.caller, self.key)[0]
        else:
            obj = resolve_officer(self.caller, self.key, name, objects)
        obj.perform_action(self.caller, self.key, parse_salvage(resource))


class Rate(GameCommand):
    category = "아이템·보급"
    input_style = "target"
    key = "환율"
    aliases = ["rate"]
    usage = "환율 · 정산관 환율 · 자원 정산관 환율"
    summary = "주변 정산관에게 회수부품 정산율을 확인합니다."

    def run(self):
        resolve_officer(self.caller, self.key, self.args).perform_action(self.caller, self.key)
