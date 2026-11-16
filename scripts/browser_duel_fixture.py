"""격리 브라우저 서버의 복사본에서만 등록되는 대련 교관."""

from dataclasses import replace
from types import MappingProxyType


def with_duel_instructor(actors):
    trainer = next(actor for actor in actors.values() if actor.action_provider_id == "world.trainingmanager")
    combat = {"combat_mode": "public", "hp": 1000, "attack": 0, "defense": 0, "xp": 0, "currency": 0}
    fixture = replace(
        trainer, id="browser_duel_instructor", name="검증대련교관", aliases=(),
        capabilities=(*trainer.capabilities, "combat", "duel"),
        profiles={**trainer.profiles, "combat": combat},
        defaults={**trainer.defaults, "combat_state": {"hp": combat["hp"]}},
    )
    return MappingProxyType({**actors, fixture.id: fixture})
