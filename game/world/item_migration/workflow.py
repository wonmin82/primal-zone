"""명시적 dry-run/apply/verify/cutover와 offline 방어선."""

from contextlib import contextmanager
from pathlib import Path
from time import time

from django.conf import settings

from world.item_entities.models import ItemEntity, ItemMigrationLedger, ItemRuntime
from world.item_runtime import VERSION, maintenance, native_runtime
from world.loot_entities.models import CurrencyLoot, CurrencyLootShare, LootClaim
from world.multiplayer import world_change

from .scan import digest, json_state, ledger, plan, raw_source, sources


@contextmanager
def migration_context():
    token = maintenance.set(True)
    try:
        yield
    finally:
        maintenance.reset(token)


def require_offline():
    if getattr(settings, "ITEM_MIGRATION_TEST_OVERRIDE", False):
        from django.db import connection

        name = str(connection.settings_dict["NAME"])
        if connection.vendor != "sqlite" or not (name == ":memory:" or name.startswith("file:memorydb_") and "mode=memory" in name):
            raise ValueError("테스트 override는 격리 in-memory DB에서만 허용합니다.")
        return
    if not getattr(settings, "ITEM_MAINTENANCE", False):
        raise ValueError("서버를 정지하고 ITEM_MAINTENANCE=True를 설정해야 합니다.")
    folder = Path(settings.GAME_DIR) / "server"
    if any(folder.glob("*.pid")):
        raise ValueError("Evennia PID 파일이 남아 있습니다. 서버와 Portal 정지를 확인하세요.")
    from evennia.server.sessionhandler import SESSIONS

    if SESSIONS.count():
        raise ValueError("온라인 세션이 존재합니다. maintenance migration을 거절합니다.")


def dry_run():
    result = {"version": VERSION, "sources": [], "errors": []}
    for kind, obj in sources():
        try:
            result["sources"].append(plan(kind, obj))
        except Exception as failure:
            result["errors"].append(f"{kind}:{obj.pk}: {failure}")
    return result


def apply():
    require_offline()
    if native_runtime():
        raise ValueError("cutover 완료 world에는 apply를 다시 실행할 수 없습니다.")
    from .convert import convert_source

    report = {"version": VERSION, "sources": [], "errors": []}
    with migration_context():
        for kind, obj in sources():
            try:
                report["sources"].append(convert_source(kind, obj, time()))
            except Exception as failure:
                # source transaction 밖에서만 실패를 수집한다. 다음 source와 retry는 독립적이다.
                report["errors"].append(f"{kind}:{obj.pk}: {failure}")
    return report


def verify():
    errors = []
    with migration_context():
        for kind, obj in sources():
            record = ledger(kind, obj)
            if not record or not record.completed:
                errors.append(f"{kind}:{obj.pk}: source 변환이 완료되지 않았습니다.")
                continue
            try:
                raw = raw_source(kind, obj)
            except Exception as failure:
                errors.append(f"{kind}:{obj.pk}: {failure}")
                continue
            if record.source_digest != digest(raw):
                errors.append(f"{kind}:{obj.pk}: legacy source digest가 변경되었습니다.")
            if record.expected_state != json_state(obj):
                errors.append(f"{kind}:{obj.pk}: native source snapshot이 다릅니다.")
            from .audit import conversion_errors

            try:
                errors.extend(f"{kind}:{obj.pk}: {error}" for error in conversion_errors(kind, obj, record))
            except Exception as failure:
                errors.append(f"{kind}:{obj.pk}: conversion audit: {failure}")
            if kind == "explorer":
                from world.content.item_mapping import BOSS_REWARDS
                from world.equipment_service import entity_snapshot
                from world.item_entities import api
                from world.lighting_service import lighting_snapshot

                try:
                    snapshot = entity_snapshot(obj)
                    if obj.db.active_weapon_item_id and (not snapshot.active or str(snapshot.active.identity) != str(obj.db.active_weapon_item_id)):
                        errors.append(f"explorer:{obj.pk}: dangling active weapon")
                    lights = lighting_snapshot(obj, now=time())
                    enabled = [row for row in api.items_owned_by(obj) if row.state.get("enabled")]
                    if any(str(row.pk) != str(obj.db.active_light_item_id) for row in enabled) or obj.db.active_light_item_id and lights.active is None:
                        errors.append(f"explorer:{obj.pk}: active light invariant")
                    owned = {row.definition_id for row in api.items_owned_by(obj)}
                    for quest, reward in BOSS_REWARDS.items():
                        if raw_source(kind, obj)["quests"].get(quest, {}).get("claimed"):
                            credential = "outpost_supply_pass" if quest == "radio_tower" else "special_supply_pass"
                            if not {credential, reward} <= owned:
                                errors.append(f"explorer:{obj.pk}: entitlement missing")
                except Exception as failure:
                    errors.append(f"explorer:{obj.pk}: {failure}")
        for row in [*ItemEntity.objects.all(), *LootClaim.objects.all(), *CurrencyLoot.objects.all(), *CurrencyLootShare.objects.all()]:
            try:
                row.full_clean()
                if isinstance(row, ItemEntity) and row.unique_scope_key != row.scope_key():
                    raise ValueError("unique owner scope가 일치하지 않습니다.")
            except Exception as failure:
                errors.append(f"{row.__class__.__name__}:{row.pk}: {failure}")
    return {"version": VERSION, "errors": errors}


def cutover(*, accept_warnings=False):
    require_offline()
    with world_change():
        errors = verify()["errors"]
        if errors:
            raise ValueError("verify 실패: " + "; ".join(errors))
        if not accept_warnings and any(row.warnings for row in ItemMigrationLedger.objects.filter(migration_version=VERSION)):
            raise ValueError("migration warning을 검토한 후 --accept-warnings로 명시적으로 처리하세요.")
        ItemRuntime.objects.update_or_create(pk=1, defaults={"version": VERSION})
    return {"version": VERSION, "errors": []}
