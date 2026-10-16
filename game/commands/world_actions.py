"""world_actions 영역의 명시적 게임 명령."""


from commands.base import GameCommand


class Return(GameCommand):
    category = "이동·탐사"
    usage = "귀환"
    summary = "비전투 상태에서 본부 옥상으로 돌아갑니다."
    key = "귀환"
    aliases = ["home"]

    def run(self):
        from world.bootstrap import get_room

        self.peaceful()
        self.caller.move_to(get_room("support_roof"), quiet=True)
