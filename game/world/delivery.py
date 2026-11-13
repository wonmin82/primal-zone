"""확정 결과의 순서와 수신자를 보존하는 경량 Commit 후 전달 계약."""

from dataclasses import dataclass

from world.multiplayer import _deferred_guard, _enqueue_after_change, after_change


@dataclass(frozen=True)
class Delivery:
    result_id: str
    kind: str
    recipients: tuple
    messages: tuple

    def __post_init__(self):
        if not self.result_id or not self.kind:
            raise ValueError("전달할 결과의 식별자와 종류가 필요합니다.")
        object.__setattr__(self, "recipients", tuple(dict.fromkeys(self.recipients)))
        object.__setattr__(self, "messages", tuple(self.messages))


def deliver_after_commit(delivery, *, permitted=None, on_error=None):
    """한 수신자 실패가 다른 수신자나 이미 확정된 게임 효과를 재실행하지 않는다."""
    def send():
        for recipient in delivery.recipients:
            try:
                if permitted is not None and not permitted(recipient):
                    continue
                for message in delivery.messages:
                    recipient.msg(message, kind=delivery.kind)
            except Exception:
                if on_error is not None:
                    try:
                        on_error(delivery.result_id, recipient)
                    except Exception:
                        pass

    guard = _deferred_guard.get()
    if guard is None or guard.delegates_to_effect():
        after_change(send)
        return

    # 조회 효과는 명시적 메시지만 넘길 수 있다. 임의 후속 Hook은 등록 단계에서 검증한다.
    if permitted is not None or on_error is not None:
        guard.reject_deferred()
    from world.actions.effects import deliver_read_only

    _enqueue_after_change(lambda: deliver_read_only(send))
