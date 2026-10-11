"""문 조작은 공통 대상 선택과 Door 서비스만 사용한다."""

from world import rules
from world import text as ft
from world.doors import operate

from commands.base import GameCommand


def sections(action):
    return (
        ("사용법", (f"문 이름 {action} · 방향 문 {action} · 문 번호 {action}",)),
        ("예시", (f"관리실 문 {action}", f"동 문 {action}", f"문 2 {action}")),
        ("실행 규칙", ("현재 방에서 감지 가능한 문을 이름·Alias·방향·번호로 선택합니다. 문이 하나일 때 '문'으로 선택할 수 있습니다.",
                       "관리실 잠금은 열쇠가 필요합니다. 내부에서는 열쇠 없이 래치로 풀 수 있습니다. 닫힌 문을 열거나 닫는 데 열쇠는 필요하지 않습니다.",
                       "열린 문은 60초 뒤 닫힙니다. 실제 통과하면 완료 시각부터 60초 연장하며, 중복 열기는 연장하지 않습니다.")),
        ("제한", ("비전투 상태에서만 조작합니다. 대상 생략·모호한 이름·모두 조작은 거절합니다.",
                 "잠긴 문은 먼저 풀고, 열린 문은 먼저 닫아야 잠글 수 있습니다. 회복실 문은 잠글 수 없습니다.")),
        ("관련 도움말", ("열어 도움", "닫아 도움", "잠궈 도움", "풀어 도움", "조사 도움", "봐 도움")),
    )


class DoorCommand(GameCommand):
    input_style = "target"
    read_only = True  # 실패 시 자연회복·상태 갱신을 저장하지 않는다.
    aliases = []

    def func(self):
        try:
            operate(self.caller, self.args, self.key)
        except rules.RuleError as error:
            self.caller.msg(ft.text(ft.token("error", str(error)), kind="error"))


class OpenDoor(DoorCommand):
    key = "열어"
    usage = "관리실 문 열어 · 동 문 열어 · 문 열어"
    summary = "현재 방의 닫힌 문을 열고 60초 자동 닫힘을 예약합니다."
    help_sections = sections(key)


class CloseDoor(DoorCommand):
    key = "닫아"
    usage = "관리실 문 닫아 · 문 2 닫아"
    summary = "현재 방의 열린 문을 닫고 자동 닫힘 예약을 취소합니다."
    help_sections = sections(key)


class LockDoor(DoorCommand):
    key = "잠궈"
    usage = "관리실 문 잠궈"
    summary = "열쇠로 현재 방의 닫힌 관리실 문을 잠급니다."
    help_sections = sections(key)


class UnlockDoor(DoorCommand):
    key = "풀어"
    usage = "관리실 문 풀어"
    summary = "열쇠 또는 관리실 내부 래치로 문의 잠금을 풉니다."
    help_sections = sections(key)


DOOR_COMMANDS = (OpenDoor, CloseDoor, LockDoor, UnlockDoor)
