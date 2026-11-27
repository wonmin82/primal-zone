"""한 번의 Action 표현 안에서만 관찰용 조회를 재사용한다."""

import copy
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from world.actions.schema import TargetReference

if TYPE_CHECKING:
    from world.firearms import FirearmSnapshot, MagazineSnapshot
    from world.item_entities.models import ItemEntity

_MISSING = object()


@dataclass
class _ScopedPresentationReads:
    records: dict = field(default_factory=dict)
    entities: dict[TargetReference, object] = field(default_factory=dict)
    load_controls: dict[tuple[TargetReference, str], list[dict]] = field(default_factory=dict)
    magazines: dict[UUID, "MagazineSnapshot"] = field(default_factory=dict)
    firearms: dict[UUID, "FirearmSnapshot"] = field(default_factory=dict)
    compatible_magazines: dict[str, tuple["MagazineSnapshot", ...]] = field(default_factory=dict)
    inventory_versions: dict[tuple[str, ...], tuple[str, tuple[tuple[str, int], ...]]] = field(default_factory=dict)
    transfer_children: dict[frozenset[UUID], dict[UUID, list["ItemEntity"]]] = field(default_factory=dict)
    mounted_magazines: dict[UUID, "ItemEntity | None"] = field(default_factory=dict)

    def resolve_entity(self, reference):
        from world.selection_numbers.api import resolve_reference

        if reference not in self.entities:
            self.entities[reference] = resolve_reference(reference)
        return self.entities[reference]

    def loaded_magazine_item(self, firearm):
        from django.db import connection
        from world.content import ITEMS
        from world.item_entities.models import ItemEntity

        magazines = self.mounted_magazines
        if firearm.pk not in magazines:
            candidates = {row.pk for row in self.entities.values() if isinstance(row, ItemEntity)
                          and row.owner_object_id == firearm.owner_object_id and row.parent_item_id is None
                          and row.location_kind in ("inventory", "equipment")
                          and ITEMS[row.definition_id].get("firearm_family")}
            missing = sorted((candidates | {firearm.pk}) - magazines.keys())
            batch_size = (connection.features.max_query_params or 1000) - 1
            loaded = {}
            for offset in range(0, len(missing), batch_size):
                batch = missing[offset:offset + batch_size]
                rows = ItemEntity.objects.filter(parent_item_id__in=batch, socket="magazine")
                loaded.update(dict.fromkeys(batch))
                loaded.update({row.parent_item_id: row for row in rows})
            magazines.update(loaded)
        return magazines[firearm.pk]


@dataclass
class _DoorPresentation:
    observed_at: float
    targets: dict
    actions: dict = field(default_factory=dict)


@dataclass
class _PresentationContext:
    caller: object
    profile: object = _MISSING
    availability: dict = field(default_factory=dict)
    doors: dict = field(default_factory=dict)
    scoped_reads: dict[tuple[int | None, float | None], _ScopedPresentationReads] = field(default_factory=dict)
    observations: dict = field(default_factory=dict)


_current = ContextVar("action_presentation_context", default=None)


@contextmanager
def presentation_scope(caller):
    """중첩 호출도 독립 범위를 만들고 예외 시 이전 범위를 복원한다."""
    token = _current.set(_PresentationContext(caller))
    try:
        yield
    finally:
        _current.reset(token)


def profile_snapshot(caller):
    context = _current.get()
    if context is None or context.caller is not caller:
        return caller.profile_snapshot()
    if context.profile is _MISSING:
        context.profile = caller.profile_snapshot()
    # EquipmentProfile의 부가 context도 보존하며 소비자 간 mutable 공유를 막는다.
    return copy.deepcopy(context.profile)


def scoped_reads(caller, observed_at):
    """현재 표시 호출의 호출자·장소·관찰 시각에 실물과 순수 계산을 한정한다."""
    context = _current.get()
    if context is None or context.caller is not caller:
        return _ScopedPresentationReads()
    key = (caller.db_location_id, observed_at)
    if key not in context.scoped_reads:
        context.scoped_reads[key] = _ScopedPresentationReads()
    return context.scoped_reads[key]


def observation_snapshot(caller, observed_at):
    from world.observation import context_for

    context = _current.get()
    if context is None or context.caller is not caller:
        return context_for(caller, observed_at=observed_at)
    key = (caller.db_location_id, observed_at)
    if key not in context.observations:
        context.observations[key] = context_for(caller, observed_at=observed_at)
    return context.observations[key]


def available(provider, caller, observed_at):
    if not hasattr(provider, "available"):
        return True
    context = _current.get()
    if context is None or context.caller is not caller or observed_at is None:
        return provider.available(caller, observed_at)
    key = (id(provider), caller.db_location_id, observed_at)
    if key not in context.availability:
        from typeclasses.actors import Actor
        from typeclasses.interactables import Shopkeeper

        state = {}
        if isinstance(provider, (Actor, Shopkeeper)):
            state = {"get_profile": lambda: profile_snapshot(caller),
                     "get_observation": lambda: observation_snapshot(caller, observed_at)}
        # 객체 참조도 보존하여 범위 안에서 id 재사용을 방지한다.
        context.availability[key] = (provider, provider.available(caller, observed_at, **state))
    return context.availability[key][1]


def door_action_labels(caller, endpoint_id, observed_at):
    """같은 화면 요청의 관찰 시각에서만 문 후보와 버튼 여부를 재사용한다."""
    from world import doors

    context = _current.get()
    views = context.doors if context is not None and context.caller is caller else {}
    key = (caller.db_location_id, observed_at)
    if key not in views:
        now = doors.time() if observed_at is None else observed_at
        targets = {target.exit_pk: target for target in doors.current_doors(caller, now)}
        views[key] = _DoorPresentation(now, targets)
    view = views[key]
    target = view.targets.get(endpoint_id)
    if target is None:
        return frozenset()
    if endpoint_id not in view.actions:
        view.actions[endpoint_id] = frozenset({
            row["label"] for row in doors.actions_for(caller, target, view.observed_at)
        })
    return view.actions[endpoint_id]
