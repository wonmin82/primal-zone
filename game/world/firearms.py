"""총기·탄창 snapshot과 선택·가격 계산. DB와 Evennia에 의존하지 않는다."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MagazineSnapshot:
    identity: str
    definition_id: str
    sequence: int
    family: str
    ammo_type: str
    capacity: int
    rounds: int


@dataclass(frozen=True)
class FirearmSnapshot:
    identity: str
    definition_id: str
    family: str
    magazine: MagazineSnapshot | None = None

    @property
    def ready(self):
        return self.magazine is not None and self.magazine.rounds > 0


def automatic_magazine(firearm, candidates):
    compatible = [mag for mag in candidates if mag.family == firearm.family and mag.rounds > 0]
    best = min(compatible, key=lambda mag: (-mag.rounds, mag.sequence), default=None)
    if firearm.magazine and (best is None or firearm.magazine.rounds >= best.rounds):
        return None
    return best


def magazine_resale(rounds, empty_resale, ammo_resale):
    return empty_resale + rounds * ammo_resale


def needs_shot(action, weapon_type):
    return weapon_type == "firearm" and action in ("attack", "shooting", "suppress")
