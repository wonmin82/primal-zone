"""전리품 영속 경계. blob 호환은 조회 facade에만 있고 native는 모델만 갱신한다."""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from evennia import create_object
from evennia.objects.models import ObjectDB

from world import rules
from world.content import ITEMS
from world.content.economy import CURRENCY
from world.item_entities import api
from world.item_entities.models import ItemEntity
from world.loot_assets import currency_payouts, normalize_entry
from world.loot_claims import ClaimContext
from world.loot_entities.models import CurrencyLoot, CurrencyLootShare, LootClaim
from world.multiplayer import object_by_id, world_change


@dataclass(frozen=True)
class LootEntrySnapshot:
    kind: str
    identity: str
    quantity: int
    reserved_party: int | None = None
    reserved_player: int | None = None
    assigned_player: int | None = None
    protection_until: float = 0
    shares: tuple = ()
    item_id: object = None
    currency_id: int | None = None

    def as_entry(self):
        """기존 pure 권리/지급 helper와 UI가 쓰는 값. 영속 ID는 UI에 전달하지 않는다."""
        entry = dict(kind=self.kind, id=self.identity, quantity=self.quantity,
                     reserved_party=self.reserved_party, reserved_player=self.reserved_player,
                     assigned_player=self.assigned_player, protection_until=self.protection_until)
        if self.kind == "currency":
            entry.update(eligible_players=[identity for identity, _ in self.shares],
                         remaining_shares={identity: amount for identity, amount in self.shares if amount > 0})
        return entry


@dataclass(frozen=True)
class LootSourceSnapshot:
    native: bool
    entries: tuple[LootEntrySnapshot, ...]


def native_source(source):
    return source.db.loot_backend == "item_entities"


def has_native_assets(source):
    """marker와 무관한 실제 저장 검사. 잘못된 위치의 직접 owner 연결도 숨기지 않는다."""
    return (ItemEntity.objects.filter(owner_object=source).exists()
            or CurrencyLoot.objects.filter(owner_object=source).exists())


def _require_container(source):
    from typeclasses.loot import Corpse, DroppedLoot

    if not isinstance(source, (Corpse, DroppedLoot)):
        raise ValidationError("전리품 공간은 시체/바닥 물건이어야 합니다.")


def _require_native_source(source):
    _require_container(source)
    if not native_source(source):
        raise rules.RuleError("native 전리품 공간을 명시적으로 선택해야 합니다.")


def claim_context(item):
    claim = LootClaim.objects.filter(item_entity_id=api.item_id(item)).first()
    if claim is None:
        return None
    return ClaimContext(str(claim.item_entity_id), claim.reserved_party_id, claim.reserved_player_id,
                        claim.assigned_player_id, claim.protection_until)


def _item_snapshot(item):
    claim = claim_context(item)
    return LootEntrySnapshot("item", item.definition_id, item.quantity,
                             claim.reserved_party if claim else None,
                             claim.reserved_player if claim else None,
                             claim.assigned_player if claim else None,
                             claim.protection_until if claim else 0, item_id=item.pk)


def _currency_snapshot(row):
    return LootEntrySnapshot("currency", CURRENCY["id"], row.quantity,
                             row.reserved_party_id, row.reserved_player_id, None, row.protection_until,
                             tuple(row.shares.order_by("player_id").values_list("player_id", "remaining_amount")),
                             currency_id=row.pk)


def loot_snapshot(source):
    """조회는 expired 권리를 free로 해석할 수 있고 저장소를 변경하지 않는다."""
    from world.item_runtime import maintenance, native_runtime, require_runtime

    require_runtime()
    if native_runtime() and not maintenance.get() and not native_source(source):
        raise rules.RuleError("Item runtime migration required: 전리품 source가 변환되지 않았습니다.")
    if not native_source(source):
        entries = []
        for raw in source.db.entries or []:
            entry = normalize_entry(raw)
            shares = tuple((identity, entry["remaining_shares"].get(identity, 0))
                           for identity in entry.get("eligible_players", []))
            entries.append(LootEntrySnapshot(entry["kind"], entry["id"], entry["quantity"],
                                             entry["reserved_party"], entry["reserved_player"],
                                             entry["assigned_player"], entry["protection_until"], shares))
        return LootSourceSnapshot(False, tuple(entries))
    items = ItemEntity.objects.filter(owner_object=source, location_kind__in=("corpse_loot", "world_loot"))
    currency = CurrencyLoot.objects.filter(owner_object=source)
    return LootSourceSnapshot(True, tuple([*map(_item_snapshot, items), *map(_currency_snapshot, currency)]))


def source_entries(source):
    return [entry.as_entry() for entry in loot_snapshot(source).entries]


def lock_sources(sources, caller=None, extra_owners=()):
    """모든 owner → UUID item → claim → currency → share의 공통 순서. 선택 후 재검증한다."""
    if any(source is None or source.pk is None for source in sources):
        raise rules.RuleError("전리품 출처가 사라졌습니다.")
    owners = {owner.pk for owner in sources} | set(extra_owners)
    if caller:
        owners.add(caller.pk)
        if caller.db.party_id:
            owners.add(caller.db.party_id)
    roots = list(ItemEntity.objects.filter(owner_object_id__in=[source.pk for source in sources]))
    claims = list(LootClaim.objects.filter(item_entity__in=roots))
    currency = list(CurrencyLoot.objects.filter(owner_object__in=sources))
    for row in [*claims, *currency]:
        owners.update(identity for identity in (row.reserved_party_id, row.reserved_player_id,
                                                getattr(row, "assigned_player_id", None)) if identity)
    owners.update(CurrencyLootShare.objects.filter(currency_loot__in=currency).values_list("player_id", flat=True))
    locked_owners = {}
    for identity in sorted(owners):
        obj = ObjectDB.objects.select_for_update().filter(pk=identity).first()
        if obj is None:
            raise rules.RuleError("전리품 공간이나 지급 대상이 사라졌습니다.")
        locked_owners[identity] = obj
    current_claims = LootClaim.objects.filter(item_entity__owner_object__in=sources)
    current_currency = CurrencyLoot.objects.filter(owner_object__in=sources)
    current_refs = {identity for row in [*current_claims, *current_currency]
                    for identity in (row.reserved_party_id, row.reserved_player_id,
                                     getattr(row, "assigned_player_id", None)) if identity}
    current_refs.update(CurrencyLootShare.objects.filter(currency_loot__in=current_currency)
                        .values_list("player_id", flat=True))
    if not current_refs <= owners:
        # lock 순서를 뒤집어 새 owner를 추가하지 않는다. 호출자가 fresh snapshot으로 재시도한다.
        raise rules.RuleError("전리품 지급 대상이 바뀌었습니다. 다시 선택하세요.")
    # owner lock 이후 집합을 다시 읽어 동시에 추가된 loot/inventory도 포함한다.
    identities = set()
    for owner in locked_owners.values():
        identities.update(api.items_owned_by(owner).values_list("pk", flat=True))
    api.lock_items(identities)
    list(LootClaim.objects.select_for_update().filter(item_entity_id__in=identities).order_by("item_entity_id"))
    currencies = list(CurrencyLoot.objects.select_for_update().filter(owner_object__in=sources).order_by("pk"))
    list(CurrencyLootShare.objects.select_for_update().filter(currency_loot__in=currencies)
         .order_by("currency_loot_id", "player_id"))
    return locked_owners


def _reservation(entry):
    return dict(reserved_party_id=entry.get("reserved_party"),
                reserved_player_id=entry.get("reserved_player"),
                protection_until=entry.get("protection_until", 0))


def create_claim(item, *, reserved_party=None, reserved_player=None, assigned_player=None, protection_until=0):
    """신뢰된 generation API. 기존 claim을 덮어쓰지 않으며 root 위치를 잠근다."""
    with world_change():
        current = api._current(item)
        if current.parent_item_id is not None or current.location_kind not in ("corpse_loot", "world_loot"):
            raise ValidationError("권리는 시체/바닥의 실물 root에만 연결합니다.")
        _require_native_source(current.owner_object)
        extras = [obj.pk for obj in (reserved_party, reserved_player, assigned_player) if obj is not None]
        expected = (current.location_kind, current.owner_object_id)
        lock_sources([current.owner_object], extra_owners=extras)
        current = api._current(item)
        if (current.location_kind, current.owner_object_id) != expected:
            raise rules.RuleError("전리품 출처가 바뀌었습니다. 다시 선택하세요.")
        claim = LootClaim(item_entity=current, reserved_party=reserved_party, reserved_player=reserved_player,
                          assigned_player=assigned_player, protection_until=protection_until)
        claim.save()
        return claim


def create_currency(source, quantity, *, shares=None, reserved_party=None, reserved_player=None,
                    protection_until=0):
    """shares는 원래 eligible 모두를 포함하며 0도 보존한다."""
    with world_change():
        _require_native_source(source)
        shares = {} if shares is None else shares
        extras = [player.pk for player in shares] + [obj.pk for obj in (reserved_party, reserved_player) if obj]
        lock_sources([source], extra_owners=extras)
        if protection_until > 0 and sum(shares.values()) != quantity:
            raise ValidationError("보호 화폐의 초기 지분 합은 수량과 같아야 합니다.")
        row = CurrencyLoot(owner_object=source, quantity=quantity, reserved_party=reserved_party,
                           reserved_player=reserved_player, protection_until=protection_until)
        row.save()
        for player, amount in sorted(shares.items(), key=lambda pair: pair[0].pk):
            CurrencyLootShare(currency_loot=row, player=player, remaining_amount=amount).save()
        return row


def populate_source(source, entries):
    """명시적인 native generation. 기존 blob 변환/조회 hook으로 호출하지 않는다."""
    from typeclasses.loot import Corpse

    with world_change():
        _require_container(source)
        entries = [{**normalize_entry(entry), "acquisition": entry.get("acquisition", {})} for entry in entries]
        refs = {identity for entry in entries
                for identity in (entry["reserved_party"], entry["reserved_player"], entry["assigned_player"],
                                 *entry.get("eligible_players", [])) if identity}
        lock_sources([source], extra_owners=refs)
        if source.db.entries or has_native_assets(source):
            raise rules.RuleError("비어 있는 전리품 공간만 native로 선택할 수 있습니다.")
        source.db.loot_backend = "item_entities"
        location = "corpse_loot" if isinstance(source, Corpse) else "world_loot"
        for entry in entries:
            if entry["kind"] not in ("item", "currency"):
                raise rules.RuleError("실물과 보급칩만 전리품으로 생성할 수 있습니다.")
            if entry["kind"] == "currency":
                shares = {object_by_id(identity): entry["remaining_shares"].get(identity, 0)
                          for identity in entry["eligible_players"]}
                create_currency(source, entry["quantity"], shares=shares,
                                reserved_party=object_by_id(entry["reserved_party"]),
                                reserved_player=object_by_id(entry["reserved_player"]),
                                protection_until=entry["protection_until"])
            else:
                # 실제 drop 내용은 기존 registry 그대로이며 총기 drop에 full 탄창을 덧붙이지 않는다.
                from world.content import ITEMS
                from world.firearm_service import create_firearm

                if entry["id"] not in ITEMS:
                    raise ValidationError("등록되지 않은 아이템 정의입니다.")
                amounts = [entry["quantity"]] if ITEMS[entry["id"]]["stackable"] else [1] * entry["quantity"]
                for amount in amounts:
                    item = (create_firearm(entry["id"], owner_object=source, location_kind=location, **entry["acquisition"])
                            if ITEMS[entry["id"]].get("firearm_family") else
                            api.create_item(entry["id"], quantity=amount, location_kind=location, owner_object=source))
                    if entry["protection_until"] or any(entry.get(field) for field in
                                                         ("reserved_party", "reserved_player", "assigned_player")):
                        LootClaim(item_entity=item, assigned_player_id=entry["assigned_player"],
                                  **_reservation(entry)).save()


def _current_entry(source, selected):
    if not native_source(source):
        raise rules.RuleError("이 전리품은 legacy 호환 경로를 사용해야 합니다.")
    for entry in loot_snapshot(source).entries:
        if (entry.item_id, entry.currency_id) == (selected.item_id, selected.currency_id):
            if (entry.reserved_party, entry.reserved_player, entry.assigned_player, entry.protection_until) != (
                    selected.reserved_party, selected.reserved_player, selected.assigned_player, selected.protection_until):
                raise rules.RuleError("전리품 권리가 바뀌었습니다. 다시 선택하세요.")
            if (entry.quantity, entry.shares) != (selected.quantity, selected.shares):
                raise rules.RuleError("전리품 수량이나 지분이 바뀌었습니다. 다시 선택하세요.")
            return entry
    raise rules.RuleError("전리품의 출처가 바뀌었거나 이미 회수되었습니다.")


def pickup(source, selected, caller, quantity, *, now):
    """권리를 lock 후 재검증하고 실물/화폐와 모든 지급 대상을 함께 갱신한다."""
    from typeclasses.loot import can_take_entry, recipient_for_item

    from world.equipment_service import entity_runtime

    with world_change():
        lock_sources([source], caller)
        if source.location != caller.location:
            raise rules.RuleError("같은 장소의 전리품만 회수할 수 있습니다.")
        current = _current_entry(source, selected)
        entry = current.as_entry()
        if type(quantity) is not int or not 0 < quantity <= current.quantity:
            raise rules.RuleError("회수할 수량을 확인하세요.")
        if not can_take_entry(entry, caller, now):
            raise rules.RuleError("다른 탐사자의 보호된 전리품입니다.")
        if current.kind == "currency":
            rules.require_peace(caller.profile())
            payouts = currency_payouts(entry, quantity, caller.pk, now)
            received = []
            for identity, amount in sorted(payouts.items()):
                if not amount:
                    continue
                recipient = object_by_id(identity)
                if recipient is None:
                    raise rules.RuleError("보급칩을 받을 탐사자를 확인할 수 없습니다.")
                profile = recipient.profile()
                profile["credits"] += amount
                recipient.save_profile(profile)
                received.append((recipient, CURRENCY["id"], amount))
            row = CurrencyLoot.objects.get(pk=current.currency_id)
            for share in row.shares.order_by("player_id"):
                share.remaining_amount = (share.remaining_amount - payouts.get(share.player_id, 0)
                                          if now < row.protection_until else 0)
                share.save()
            if row.quantity == quantity:
                row.shares.all().delete()
                row.delete()
            else:
                row.quantity -= quantity
                row.save()
            return received
        recipient = recipient_for_item(entry, caller, now)
        if recipient is None or not entity_runtime(recipient):
            raise rules.RuleError("실물 전리품은 ItemEntity 소지품을 사용하는 지급 대상이 필요합니다.")
        source_item = ItemEntity.objects.get(pk=current.item_id)
        if quantity < source_item.quantity:
            # claim 없는 fragment는 이 transaction에서 즉시 inventory로 이동한다.
            item = api.split_stack(source_item, quantity, allow_claimed=True)
        else:
            item = source_item
            LootClaim.objects.filter(item_entity=item).delete()
        item = api.move_item_tree(item, location_kind="inventory", owner_object=recipient,
                                  operation="loot", expected_source=(item.location_kind, source.pk))
        if ITEMS[item.definition_id]["stackable"]:
            for candidate in ItemEntity.objects.filter(owner_object=recipient, location_kind="inventory").exclude(pk=item.pk):
                maximum = ITEMS[item.definition_id]["max_stack"]
                if api.same_merge_context(item, candidate) and (maximum is None or candidate.quantity + item.quantity <= maximum):
                    api.merge_stack(item, candidate)
                    break
        return [(recipient, current.identity, quantity)]


def reconcile_claims(source, *, now):
    if not native_source(source):
        return 0
    with world_change():
        lock_sources([source])
        deleted, _ = LootClaim.objects.filter(item_entity__owner_object=source, protection_until__lte=now).delete()
        return deleted


def decay_source(source, *, now):
    """한 entry당 한 바닥 공간. root/tree/claim과 화폐 share는 원래 identity를 유지한다."""
    from typeclasses.loot import DroppedLoot

    from world.loot_assets import asset_name

    with world_change():
        lock_sources([source])
        dropped = []
        for entry in loot_snapshot(source).entries:
            owner = create_object(DroppedLoot, key=asset_name(entry.as_entry()), location=source.location)
            owner.db.loot_backend = "item_entities"
            owner.db.source_spawn = source.db.source_spawn
            if entry.kind == "item":
                api.move_item_tree(entry.item_id, location_kind="world_loot", owner_object=owner,
                                   expected_source=("corpse_loot", source.pk))
            else:
                row = CurrencyLoot.objects.get(pk=entry.currency_id)
                row.owner_object = owner
                row.save()
            dropped.append(owner)
        return dropped


def integrity_errors(source):
    """출처의 marker/실제 저장과 모델을 검사한다. 자동 복구나 전체 scan은 하지 않는다."""
    issues = []
    from world.item_migration.scan import digest, ledger, raw_source

    kind = "corpse" if source.db_typeclass_path == "typeclasses.loot.Corpse" else "dropped"
    record = ledger(kind, source)
    archived = bool(record and record.completed and record.source_digest == digest(raw_source(kind, source)))
    if native_source(source) and source.db.entries and not archived:
        issues.append("native 전리품 공간에 legacy entry가 남았습니다.")
    if not native_source(source) and has_native_assets(source):
        issues.append("legacy 전리품 공간에 native 전리품 row가 존재합니다.")
    rows = [*LootClaim.objects.filter(item_entity__owner_object=source),
            *CurrencyLoot.objects.filter(owner_object=source),
            *CurrencyLootShare.objects.filter(currency_loot__owner_object=source)]
    for row in rows:
        try:
            row.full_clean()
        except ValidationError as error:
            issues.extend(error.messages)
    return issues
