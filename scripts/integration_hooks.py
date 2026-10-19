"""복사된 격리 서버에서만 설치되는 E2E-13 실제 서비스 실패 경계."""

import os

from server.conf.at_server_startstop import *  # noqa: F403
from server.conf.at_server_startstop import at_server_start as original_start


def at_server_start():
    from django.conf import settings
    from server.conf.smoke_support import require_smoke
    require_smoke(settings)
    original_start()
    if os.environ.get("PRIMAL_INTEGRATION_SCENARIO") == "E2E-11":
        install_party_clock(settings)
    if os.environ.get("PRIMAL_INTEGRATION_SCENARIO") != "E2E-13":
        return
    install_loot_rollback(settings)


def install_loot_rollback(settings):
    """격리 서버의 신규 Loot Service 뒤에만 상위 실패를 주입한다."""
    from dataclasses import replace

    from server.conf.smoke_support import require_smoke
    from world.actions import loot_content
    from world.actions.manifest import compiled

    require_smoke(settings)
    package = loot_content.PACKAGE
    original = next(service.handler for service in package.services if service.id == "loot.pickup")

    def rollback(context):
        from world.multiplayer import world_change
        from world.rules import RuleError

        with world_change():
            original(context)
            # 실제 안정 선택·권리·native 지급 후 상위 경계에서 실패한다.
            raise RuleError("격리 검증: 상위 변경 롤백")

    loot_content.PACKAGE = replace(package, services=tuple(
        replace(service, handler=rollback) if service.id == "loot.pickup" else service
        for service in package.services))
    compiled.cache_clear()


def install_party_clock(settings):
    """PR 전용 시각 인자 주입. 운영 상수·DB 시작시각·실제 세션은 바꾸지 않는다."""
    import json
    from pathlib import Path

    from typeclasses.parties import Party
    from typeclasses.scripts import WorldLifecycle
    control = Path(settings.PRIMAL_SMOKE_RUN_DIR)/'integration-control'
    original = WorldLifecycle.at_repeat
    def repeat(script, *args, **kwargs):
        result = original(script, *args, **kwargs)
        request = control/'request.json'
        if not request.exists():
            return result
        payload = json.loads(request.read_text(encoding='utf-8'))
        op = payload.get('operation')
        if payload != {'operation': op} or op not in ('party-before', 'party-at'):
            raise RuntimeError('허용되지 않은 시각 주입')
        party = Party.objects.get()
        since = party.state()['leader_offline_since']
        if since is None:
            raise RuntimeError('실제 마지막 Puppet 해제가 확인되지 않음')
        party.reconcile_leader(now=since + (599.999 if op == 'party-before' else 600))
        request.unlink()
        (control/'response.json').write_text(json.dumps({'ready': True, 'boundary': op}), encoding='utf-8')
        return result
    WorldLifecycle.at_repeat = repeat
