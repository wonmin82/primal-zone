"""Fresh 증거는 read-only. 유일한 준비 mutation은 반복 사냥 대신 명시적 칩 지급이다."""

import argparse
import json
from pathlib import Path


def initialize():
    from django.conf import settings
    from server.conf.smoke_support import require_smoke

    require_smoke(settings)
    if not (Path(settings.PRIMAL_SMOKE_RUN_DIR) / ".phase7c-fresh").is_file():
        raise RuntimeError("fresh 격리 marker가 없습니다.")
    import django

    django.setup()
    import evennia

    evennia._init()


def inspect():
    from evennia.accounts.models import AccountDB
    from evennia.utils.dbserialize import deserialize
    from typeclasses.explorers import Explorer
    from world.item_entities import api
    from world.item_entities.models import ItemMigrationLedger, ItemRuntime

    return {"label": "TEST / FRESH NATIVE", "runtime": list(ItemRuntime.objects.values()),
            "ledger_count": ItemMigrationLedger.objects.count(),
            "accounts": list(AccountDB.objects.values_list("username", flat=True)),
            "players": {p.key: {"id": p.pk, "zone": p.zone, "runtime_version": p.db.item_runtime_version,
                                "legacy": {k: deserialize(p.db.profile).get(k) for k in
                                           ("inventory", "equipment", "storage", "light_sources")},
                                "items": list(api.items_owned_by(p).order_by("sequence").values(
                                    "id", "definition_id", "quantity", "sequence", "owner_object_id", "location_kind", "slot", "parent_item_id", "state"))}
                        for p in Explorer.objects.all()}}


def fund():
    from typeclasses.explorers import Explorer

    player = Explorer.objects.get(db_key="검증가")
    profile = player.profile()
    if profile["xp"] != 0 or profile["credits"] != 20 or player.db.phase7c_funded:
        raise RuntimeError("가입 직후 단 한 번만 반복 grind를 칩 준비금으로 대체합니다.")
    profile["credits"] += 900
    player.save_profile(profile)
    player.db.phase7c_funded = True
    return {"label": "TEST / FRESH NATIVE", "funding": 900, "xp_injected": 0,
            "quest_or_item_reward_injected": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("inspect", "fund"))
    args = parser.parse_args()
    initialize()
    print(json.dumps(inspect() if args.action == "inspect" else fund(), ensure_ascii=False, default=str))
