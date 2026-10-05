"""native 전리품과 legacy SSOT의 전체 rollback 검증 fixture."""

from copy import deepcopy
from unittest.mock import patch

from evennia import create_object
from typeclasses.loot import Corpse, DroppedLoot
from world import loot_service
from world.item_entities.models import ItemEntity, ItemSequence
from world.loot_entities.models import CurrencyLoot, CurrencyLootShare, LootClaim

from tests.item_entity_fixture import NativeItemTest


class NativeLootTest(NativeItemTest):
    def setUp(self):
        super().setUp()
        self.char2.location = self.char1.location
        self.enterContext(patch("typeclasses.loot.delay"))
        self.source = create_object(Corpse, key="시험 시체", location=self.char1.location)
        self.source.db.decay_at = 200
        loot_service.populate_source(self.source, [])

    def loot_item(self, identity="ammo_9", quantity=10, *, assigned=None, deadline=300, party=None):
        from world.item_entities import api

        row = api.create_item(identity, quantity=quantity, location_kind="corpse_loot", owner_object=self.source)
        loot_service.create_claim(row, reserved_player=self.char1 if party is None else None,
                                  reserved_party=party, assigned_player=assigned or self.char1,
                                  protection_until=deadline)
        return row

    def entry(self, row):
        return next(entry for entry in loot_service.loot_snapshot(self.source).entries
                    if entry.item_id == row.pk or entry.currency_id == row.pk)

    def all_state(self):
        return (
            [list(model.objects.order_by("pk").values())
             for model in (ItemEntity, LootClaim, CurrencyLoot, CurrencyLootShare)],
            [(obj.pk, obj.db.active_weapon_item_id, obj.db.active_light_item_id,
              deepcopy(dict(obj.profile()))) for obj in (self.char1, self.char2)],
            ItemSequence.objects.filter(pk=1).values_list("last_value", flat=True).first(),
            list(DroppedLoot.objects.values_list("pk", flat=True)),
            deepcopy(list(self.source.db.entries)),
        )
