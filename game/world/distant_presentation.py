"""관찰 경로와 무관한 읽기 전용 원거리 표시. 로컬 selector와 lifecycle은 사용하지 않는다."""

from dataclasses import dataclass, field
from time import time

from world import text as ft
from world.content import ROOMS
from world.target_presentation import count_word
from world.targets import ordered


@dataclass(frozen=True)
class DistantViewContext:
    viewer: object
    source_room: object
    target_room: object
    via: object | None = None
    direction: str | None = None
    distance: int = 1
    observed_at: float = field(default_factory=lambda: time())


@dataclass(frozen=True)
class DistantPresence:
    name: str
    role: str
    unit: str
    sentence: str


class DistantPresenceMixin:
    """기본은 숨김. typeclass 또는 객체의 distant_visible attribute로 정책을 정한다."""

    distant_visible = False
    distant_role = "object"
    distant_unit = "개"
    distant_sentence = "멀리 보인다."

    def is_distant_visible(self, context):
        enabled = (
            self.db.distant_visible
            if self.attributes.has("distant_visible")
            else self.distant_visible
        )
        return (
            enabled
            and self != context.viewer
            and self.location == context.target_room
            and self.access(context.viewer, "view")
        )

    def get_distant_presence(self, context):
        return DistantPresence(
            self.key, self.distant_role, self.distant_unit, self.distant_sentence
        )


def direction_phrase(direction):
    """실제 Exit key의 자연어 표현만 만든다. alias나 출구 데이터를 다시 정의하지 않는다."""
    if direction in {"북", "남", "동", "서", "북동", "북서", "남동", "남서", "위", "아래", "안"}:
        return direction + "쪽으로"
    if direction == "밖":
        return "바깥쪽으로"
    return direction + " 너머로"


def distant_appearance(context):
    room = context.target_room
    if not room.access(context.viewer, "view"):
        return ft.text("그 너머는 살펴볼 수 없다.")
    definition = ROOMS.get(room.db.zone_id)
    description = definition["desc"] if definition else (room.db.desc or "")
    heading = (
        ft.text(
            ft.token("direction", direction_phrase(context.direction)),
            " ",
            ft.named("title", room.key, "이/가"),
            " 이어진다.",
        )
        if context.direction
        else ft.text("멀리 ", ft.named("title", room.key, "이/가"), " 보인다.")
    )
    groups = {}
    for obj in ordered(room.contents):
        visibility = getattr(obj, "is_distant_visible", None)
        presence = getattr(obj, "get_distant_presence", None)
        if visibility and presence and obj.access(context.viewer, "view") and visibility(context):
            summary = presence(context)
            if summary is not None:
                groups[summary] = groups.get(summary, 0) + 1
    lines = [heading, "", description, ""]
    for summary, count in groups.items():
        lines.append(
            ft.text(
                ft.token(summary.role, summary.name),
                " ",
                count_word(count),
                " ",
                summary.unit,
                ft.particle(summary.unit),
                " ",
                summary.sentence,
            )
        )
    if not groups:
        lines.append("그 밖에 눈에 띄는 것은 없다.")
    return ft.join(lines)
