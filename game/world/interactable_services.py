"""NPC/시설의 도메인 효과. Typeclass는 구성·표현만 제공한다.

기존 act/train의 게임 규칙과 출력 의미를 이곳으로 이동했다.
Action Gateway의 world_change 안에서 실행하고 출력은 최종 커밋 뒤 전달한다.
"""

from world import rules
from world import text as ft
from world.content import ENEMIES, ITEMS, ROOMS, SALVAGE_CREDIT_RATE, SHOP_CATALOGS
from world.currency import format_currency
from world.multiplayer import after_change
from world.progression import ATTRIBUTES, SKILLS


def notify(caller, message):
    after_change(lambda: caller.msg(message))


def content_name(identity):
    from typeclasses.interactables import content_name as name
    return name(identity)


def adminkeycabinet(provider, caller, action, args):
    from world.door_keys import issue_key
    return issue_key(caller, provider)


def maintenancelog(provider, caller, action, args):
    caller.change(rules.read_record)
    notify(caller, ft.text(content_name('maintenance_log'), '을 펼쳐 복구 절차를 읽었다.\n  ', ft.item('generator_repair_part'), ' 3개로 ', content_name('generator'), '를 수리하면 능선의 문을 열 수 있다.\n  ', ft.named('hostile', ENEMIES['alpha']['name'], '이/가'), ' 몸을 낮추면 다음 차례에는 ', ft.token('command', '견제'), '로 공격을 약화시키고 부상은 치료할 것.'))


def supplycache(provider, caller, action, args):
    profile = caller.profile_snapshot()
    generator_fixed = profile['quests']['radio_tower']['generator_fixed']
    existing_parts = profile['inventory'].get('generator_repair_part', 0)
    caller.change(rules.claim_cache)
    missing_parts = 0 if generator_fixed else max(0, 3 - existing_parts)
    notify(caller, ft.text(ft.token('object', provider.key), '에서 ', ft.item('bandage'), ' 2개', ft.text(', ', ft.item('generator_repair_part'), f' {missing_parts}개') if missing_parts else '', '와 ', ft.item('expedition_tag'), '를 찾아 챙겼다.', ' 정비용 회수부품은 기존 보유량을 포함해 3개를 확보했다.' if existing_parts and (not generator_fixed) else ''))


def generator(provider, caller, action, args):
    before = caller.profile()['xp']
    from world.facilities import restore_outpost_power
    restore_outpost_power(caller)
    gained = caller.profile()['xp'] - before
    body = ft.text(ft.named('object', provider.key, '이/가'), ' 다시 돌아가기 시작했다. 공용 조명에 전력이 들어왔다.')
    if gained:
        body = ft.text(body, ' 능선 진입문이 열렸다.\n복구 작업으로 ', ft.token('reward', f'경험치 {gained}'), '를 얻었다.')
    notify(caller, body)


def skilltrainer(provider, caller, action, skill):
    if action != '배워' or skill != provider.db.skill_id:
        raise rules.RuleError('이 교관이 담당하는 기술이 아니다.')
    before = rules.skill_rank(caller.profile(), skill)
    caller.change(lambda profile: rules.learn_skill(profile, skill, safe=provider.available(caller)))
    remaining = rules.point_pools(caller.profile())['skill_points']
    notify(caller, f"{provider.key}에게 {SKILLS[skill]['name']}{ft.particle(SKILLS[skill]['name'], '을/를')} 훈련받아 R{before}에서 R{before + 1}로 올랐고 기술 훈련이 {remaining}회 남았다.")


def attributetrainer(provider, caller, action, args):
    attribute, amount = args
    if action != '배분' or attribute != provider.db.attribute_id:
        raise rules.RuleError('이 교관이 담당하는 특성이 아니다.')
    before = 10 + rules.allocated(caller.profile(), attribute)
    caller.change(lambda profile: rules.allocate_attribute(profile, attribute, amount, safe=provider.available(caller)))
    remaining = rules.point_pools(caller.profile())['attribute_points']
    name = ATTRIBUTES[attribute]['name']
    notify(caller, f"{provider.key}에게 훈련받아 {name}{ft.particle(name)} {before}에서 {before + amount}{ft.particle(str(before + amount), '으로/로')} 올랐고 특성 포인트가 {remaining}점 남았다.")


def trainingmanager(provider, caller, action, scope):
    result = caller.change(lambda profile: rules.retrain(profile, scope, safe=provider.available(caller)))
    attributes, skills = (result['attribute_points'], result['skill_training'])
    message = {'attributes': f'특성 투자를 초기화해 특성 포인트 {attributes}점', 'skills': f'모든 기술을 R1로 초기화해 기술 훈련 {skills}회', 'all': f'특성과 기술을 모두 초기화해 특성 포인트 {attributes}점과 기술 훈련 {skills}회'}[result['scope']]
    notify(caller, f"{provider.key}{ft.particle(provider.key)} {message}{ft.particle(message, '을/를')} 다시 사용할 수 있게 했다.")


def doctor(provider, caller, action, args):
    if args is not None:
        if not args.isascii() or not args.isdecimal() or len(args) > 7 or not 1 <= int(args) <= rules.MAX_TREAT_HP:
            raise rules.RuleError('회복량은 1~1,000,000 사이의 정수로 입력하세요.')
        args = int(args)
    quoted_hp, quoted_cost = provider.quote(caller, args)
    notify(caller, f'요청 HP {quoted_hp} 회복 예상 비용: {quoted_cost}칩 (실행 시 재계산)')
    from world.multiplayer import world_change
    with world_change():
        profile = caller.profile()
        restored, cost = rules.treat(profile, args, safe=ROOMS.get(caller.zone, {}).get('safe', False))
        caller.save_profile(profile)
    notify(caller, f'HP {restored} 회복 · 비용 {cost}칩을 지불했습니다. 정신력은 회복하지 않습니다.')


def bed(provider, caller, action, args):
    caller.change(lambda profile: rules.rest(profile, safe=ROOMS.get(caller.zone, {}).get('safe', False)))
    notify(caller, '침대에서 휴식하며 체력과 정신력을 모두 회복했습니다.')


def settlementofficer(provider, caller, action, args):
    if not ROOMS.get(caller.zone, {}).get('safe', False):
        raise rules.RuleError('안전한 곳에서만 자원을 정산할 수 있습니다.')
    if action == '환율':
        notify(caller, ft.text(ft.item('scrap'), f' 1개 → {format_currency(SALVAGE_CREDIT_RATE)}'))
        return

    def settle(profile):
        quantity = profile['inventory'].get('scrap', 0) if args is None else args
        if args is None and (not quantity):
            raise rules.RuleError('정산할 회수부품이 없습니다.')
        return (quantity, rules.settle_salvage(profile, quantity))
    quantity, earned = caller.change(settle)
    notify(caller, ft.text(ft.item('scrap'), f' {quantity}개를 정산했다. {format_currency(earned)}을 받았다.'))


def shopkeeper(provider, caller, action, args):
    from world import presentation as view
    if not ROOMS.get(caller.zone, {}).get('safe', False):
        raise rules.RuleError('안전한 곳에서만 상점을 이용할 수 있습니다.')
    if provider.db.shop_id not in SHOP_CATALOGS:
        raise rules.RuleError('상점 판매 목록을 확인할 수 없습니다.')
    if action == '목록':
        notify(caller, view.shop(provider.db.shop_id, provider.key))
    elif action == '사':
        from world.shop_service import buy
        buy(caller, provider, args)
        quantity = ITEMS[args].get('purchase_quantity', 1)
        notify(caller, ft.text(ft.item(args), f' {quantity}개를 받아 소지품에 넣었다.'))
    elif action == '가치':
        from world.shop_service import valuation
        name, _quantity = args
        price = valuation(caller, provider, name)
        from world.content.items import find_id
        from world.targets import parse_selector
        identity = name.definition_id if hasattr(name, 'definition_id') else find_id(ITEMS, parse_selector(name).name)
        if hasattr(name, 'definition_id'):
            from world.equipment_service import selector_label
            name = selector_label(caller, name)
        try:
            purchase = rules.purchase_price(identity)
        except rules.RuleError:
            purchase = None
        notify(caller, ft.text(ft.token('npc', provider.key), '은 ', ft.token('item', name), '의 가치를 평가한다.\n', f'구매 기준가는 {format_currency(purchase)}이다.\n' if purchase else '', '매입가는 ', ft.token('reward', format_currency(price)), '이다.'))
    elif action == '팔아':
        from world.shop_service import sell
        result = sell(caller, provider, *args)
        notify(caller, ft.text(ft.token('npc', provider.key), '이 ', ft.token('item', result.label), f' {result.quantity}개를 ', ft.token('reward', format_currency(result.proceeds)), '에 매입했다.', f'\n잔탄 {result.rounds}발의 가치가 포함되었다.' if result.rounds else ''))
    else:
        raise rules.RuleError('지원하지 않는 상점 행동입니다.')


def junglemarker(provider, caller, action, args):
    newly_marked = caller.change(lambda profile: rules.jungle_mark(profile, provider.quest_flag))
    notify(caller, ft.text(ft.token('object', provider.key), '을 살펴 선발대의 경로를 확인했다.'))
    return newly_marked


def watermarker(provider, caller, action, args):
    if junglemarker(provider, caller, action, args):
        notify(caller, ft.text('표식 아래에서 ', ft.item('jungle_cell'), '를 확보했다.'))


def signaldevice(provider, caller, action, args):
    caller.change(rules.open_jungle_gate)
    notify(caller, ft.text(ft.item('jungle_cell'), '로 ', ft.token('object', provider.key), '의 좌표를 맞추자 연구구역의 문이 열렸다.'))


def junglecache(provider, caller, action, args):
    caller.change(rules.claim_jungle_cache)
    notify(caller, ft.text(ft.token('object', provider.key), '에서 ', ft.item('bandage'), ' 2개, ', ft.item('battery'), ' 2개와 ', ft.item('mental_stability_module'), '을 찾아 챙겼다.'))


def emergencylightcache(provider, caller, action, args):
    caller.change(rules.claim_emergency_light_cache)
    notify(caller, ft.text(ft.item('flashlight'), ' 한 개와 ', ft.item('battery'), ' 두 개를 챙겼다.'))
