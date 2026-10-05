"""DB와 무관한 권리 병합 계약. root identity가 독립 배정 단위를 나타낸다."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClaimContext:
    allocation_unit: str
    reserved_party: int | None
    reserved_player: int | None
    assigned_player: int | None
    protection_until: float


def same_claim_context(source, destination):
    return source == destination
