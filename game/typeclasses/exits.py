"""
Exits

Exits are connectors between Rooms. An exit always has a destination property
set and has a single command defined on itself with the same name as its key,
for allowing Characters to traverse the exit to its destination.

"""

from evennia.objects.objects import DefaultExit, ExitCommand
from world import text as ft
from world.content import ROOMS
from world.distant_presentation import DistantViewContext, direction_phrase
from world.navigation import blocked_exit_message, entry_block

from .objects import ObjectParent


class ExactExitCommand(ExitCommand):
    """모든 출구의 공통 인자 경계. 보기 계열은 별도 명령으로 파싱된다."""

    read_only = True  # 회복 정산은 성공할 이동의 world_change 안에서 수행한다.

    def func(self):
        if self.args.strip():
            self.caller.msg(ft.token("error", "출구 이름만 입력하세요."))
            return
        return super().func()


class Exit(ObjectParent, DefaultExit):
    """
    Exits are connectors between rooms. Exits are normal Objects except
    they defines the `destination` property and overrides some hooks
    and methods to represent the exits.

    See mygame/typeclasses/objects.py for a list of
    properties and methods available on all Objects child classes like this.

    """

    blocks_distant_view = True
    exit_command = ExactExitCommand

    def at_traverse(self, traversing_object, target_location, **kwargs):
        message = blocked_exit_message(self.location.db.zone_id, self.key)
        if message:
            traversing_object.msg(ft.text(message))
            return
        from world.access import can_enter, entry_message

        if not can_enter(traversing_object, target_location):
            traversing_object.msg(entry_message(traversing_object, target_location))
            return
        return super().at_traverse(traversing_object, target_location, **kwargs)

    def can_observe_through(self, context):
        """진행 조건과 시야는 별개다. 투명한 경계는 attribute/override로 관찰을 허용한다."""
        blocks = (
            self.db.blocks_distant_view
            if self.attributes.has("blocks_distant_view")
            else self.blocks_distant_view
        )
        zone = context.target_room.db.zone_id
        if not blocks or not ROOMS.get(zone, {}).get("requires"):
            return True
        return entry_block(context.viewer.profile_snapshot(), zone) is None

    def return_appearance(self, looker, **kwargs):
        message = blocked_exit_message(self.location.db.zone_id, self.key)
        if message:
            return ft.text(message)
        destination = self.destination
        appearance = getattr(destination, "return_distant_appearance", None)
        if not appearance:
            return ft.text("그 너머는 살펴볼 수 없다.")
        context = DistantViewContext(
            viewer=looker,
            source_room=looker.location,
            target_room=destination,
            via=self,
            direction=self.key,
            **({"observed_at": kwargs["observed_at"]} if "observed_at" in kwargs else {}),
        )
        if not self.can_observe_through(context):
            requirement = ROOMS.get(destination.db.zone_id, {}).get("requires") or {}
            message = requirement.get("observe_message")
            if not message:
                return ft.text("그 방향은 아직 자세히 살펴볼 수 없다.")
            return ft.text(
                ft.token("direction", direction_phrase(self.key)),
                " ",
                message,
            )
        return appearance(context)
