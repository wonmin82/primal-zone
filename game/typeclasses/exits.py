"""
Exits

Exits are connectors between Rooms. An exit always has a destination property
set and has a single command defined on itself with the same name as its key,
for allowing Characters to traverse the exit to its destination.

"""

from evennia.objects.objects import DefaultExit
from world import text as ft
from world.content import ROOMS
from world.distant_presentation import DistantViewContext, direction_phrase
from world.navigation import entry_block

from .objects import ObjectParent


class Exit(ObjectParent, DefaultExit):
    """
    Exits are connectors between rooms. Exits are normal Objects except
    they defines the `destination` property and overrides some hooks
    and methods to represent the exits.

    See mygame/typeclasses/objects.py for a list of
    properties and methods available on all Objects child classes like this.

    """

    blocks_distant_view = True

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
        )
        if not self.can_observe_through(context):
            return ft.text(
                ft.token("direction", direction_phrase(self.key)),
                " 난 길은 닫힌 진입문에 막혀 있다.",
            )
        return appearance(context)
