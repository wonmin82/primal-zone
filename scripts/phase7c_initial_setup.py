"""격리 fresh first boot: upstream 초기화는 실행하고 launcher 자동 reset만 생략한다.

Foreground owned process인 Harness에는 launcher의 자동 재시작 관리자가 없다.
이후 실제 정상 stop/start/relogin은 smoke_closeout의 계약으로 별도 검증한다.
"""


def handle_setup(last_step=None):
    from django.conf import settings
    from evennia.server import initial_setup
    from evennia.server.models import ServerConfig
    from server.conf.smoke_support import require_smoke

    require_smoke(settings)
    if last_step in ("done", -1):
        return
    steps = ("create_objects", "at_initial_setup", "collectstatic")
    start = steps.index(last_step) + 1 if last_step in steps else 0
    for step in steps[start:]:
        getattr(initial_setup, step)()
        ServerConfig.objects.conf("last_initial_setup_step", step)
    ServerConfig.objects.conf("last_initial_setup_step", "done")
