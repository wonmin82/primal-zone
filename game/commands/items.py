"""아이템 이전·소비·장비 해제. 조사는 공통 selector helper에서 추출한다."""


from commands.base import GameCommand


class Drop(GameCommand):
    key = "버려"
    category = "아이템·보급"
    input_style = "target"
    usage = "붕대 버려 · 붕대 모두 버려 · 20칩 버려 · 칩 모두 버려"
    summary = "장착분을 남기고 물건 하나 또는 스택 전부를 공개된 바닥에 옮깁니다."
    aliases = ["drop"]
    action = "drop"

    def func(self):
        from world.actions.global_actions import invoke

        return invoke(self.caller, self.session, self.action, query=self.args)


class Give(Drop):
    key = "줘"
    aliases = ["give"]
    action = "give"
    usage = "탐사자에게 붕대 줘 · 탐사자에게 붕대 모두 줘 · 탐사자에게 20칩 줘 · 탐사자에게 칩 모두 줘"
    summary = "같은 장소의 다른 비전투 탐사자에게 물건을 건넵니다."
