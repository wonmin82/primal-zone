"""
Exits

Exits are connectors between Rooms. An exit always has a destination property
set and has a single command defined on itself with the same name as its key,
for allowing Characters to traverse the exit to its destination.

"""

from evennia.objects.objects import DefaultExit
from world import text as ft
from world.distant_presentation import DistantViewContext

from .objects import ObjectParent


class Exit(ObjectParent, DefaultExit):
    """
    Exits are connectors between rooms. Exits are normal Objects except
    they defines the `destination` property and overrides some hooks
    and methods to represent the exits.

    See mygame/typeclasses/objects.py for a list of
    properties and methods available on all Objects child classes like this.

    """

    def return_appearance(self, looker, **kwargs):
        destination = self.destination
        appearance = getattr(destination, "return_distant_appearance", None)
        if not appearance:
            return ft.text("그 너머는 살펴볼 수 없다.")
        return appearance(
            DistantViewContext(
                viewer=looker,
                source_room=looker.location,
                target_room=destination,
                via=self,
                direction=self.key,
            )
        )
