"""재시작·접근·정기 sweep이 같은 timestamp 기반 복구를 사용한다."""

from time import time

from typeclasses.enemies import Enemy, room_enemies
from typeclasses.loot import Corpse, room_loot
from typeclasses.parties import Party


def reconcile_room(room, now=None):
    now = time() if now is None else now
    for corpse in room_loot(room):
        corpse.reconcile(now)
    for enemy in room_enemies(room, alive_only=False):
        enemy.reconcile(now)


def reconcile_world(now=None, restart=False):
    now = time() if now is None else now
    from world.environment_state import reconcile_environment
    from world.facilities import reconcile_facilities

    reconcile_facilities()
    reconcile_environment(now, restart=restart)
    if restart:
        from typeclasses.explorers import Explorer

        for player in Explorer.objects.all():
            player.reconcile_lights(now, turn_off=True)
            player.leave_combat(now=now)
    for party in Party.objects.all():
        party.reconcile(now)
    for corpse in list(Corpse.objects.all()):
        corpse.reconcile(now)
        if corpse.pk:
            corpse.schedule_lifecycle()
    for enemy in Enemy.objects.all():
        # 빈 방의 살아 있는 적은 다음 입실/관찰까지 지연 계산한다.
        observed = enemy.location and any(getattr(obj, "push_state", None) and obj.sessions.count()
                                          for obj in enemy.location.contents)
        if enemy.db.state == "respawning" or enemy.db.combatants or observed:
            enemy.reconcile(now)
    # 보호 종료는 metadata를 삭제하지 않고 timestamp 비교만으로 FFA가 된다.
    from typeclasses.explorers import Explorer

    for player in Explorer.objects.all():
        if player.sessions.count():
            if restart:
                player.reconcile_recovery(now)
            player.reconcile_lights(now)
            player.push_state(observed_at=now)
