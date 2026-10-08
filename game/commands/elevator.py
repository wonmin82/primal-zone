"""승강기를 사용할 수 있는 Room에서만 제공하는 명령 집합."""

from evennia import CmdSet
from world import elevator
from world.content.elevator import ELEVATOR_STOPS

from commands.base import GameCommand


class BoardElevator(GameCommand):
    key = "승강기"

    def run(self):
        elevator.board(self.caller)


class SelectFloor(GameCommand):
    def run(self):
        elevator.select_stop(self.caller, self.stop)


class Disembark(GameCommand):
    key = "내려"

    def run(self):
        elevator.disembark(self.caller)


class Stairs(GameCommand):
    key = "계단"
    input_style = "prefix"

    def run(self):
        from world.stairs import move

        move(self.caller, self.args.strip())


class ElevatorLandingCmdSet(CmdSet):
    key = "ElevatorLanding"

    def at_cmdset_creation(self):
        self.add(BoardElevator())
        self.add(Stairs())


class ElevatorInsideCmdSet(CmdSet):
    key = "ElevatorInside"

    def at_cmdset_creation(self):
        for stop, data in ELEVATOR_STOPS.items():
            self.add(SelectFloor(key=data["label"], stop=stop))
        self.add(Disembark())
