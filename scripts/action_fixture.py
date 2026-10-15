"""소유한 smoke DB에서만 Action 수직 검증 콘텐츠를 준비·관찰한다."""

import json
import os
import sys
from pathlib import Path


def main():
    run = Path(os.environ["PRIMAL_SMOKE_RUN_DIR"]).resolve()
    if not (run / ".primal-smoke").is_file() or Path.cwd().resolve() != run / "game":
        raise RuntimeError("격리 Action fixture 경로가 아닙니다.")
    if len(sys.argv) == 1:
        settings_file = run / "game/server/conf/settings_smoke.py"
        with settings_file.open("a", encoding="utf-8") as stream:
            stream.write("\nACTION_CONTENT_PACKAGES = ('world.actions.validation_content',)\n")
        from smoke_setup import setup

        setup(json.load(sys.stdin))
        from evennia import create_object
        from evennia.objects.models import ObjectDB
        from world.actions.providers import ActionProviderObject
        from world.multiplayer import world_change

        room = next(obj for obj in ObjectDB.objects.all() if obj.db.zone_id == "staging_room")
        with world_change():
            provider = create_object(ActionProviderObject, key="검증기", location=room,
                                     attributes=[("action_provider_id", "validation.instrument"),
                                                 ("selection_group_id", "validation.instruments")])
            provider.locks.add("view:true();call:true()")
        return
    import django

    django.setup()
    import evennia

    evennia._init()
    from django.conf import settings
    from evennia.objects.models import ObjectDB
    from evennia.utils.dbserialize import deserialize
    from server.conf.smoke_support import require_smoke
    from world.selection_numbers.api import descriptor, number_for, verify

    require_smoke(settings)
    provider = next(obj for obj in ObjectDB.objects.all() if obj.db.action_provider_id == "validation.instrument")
    events = [event for obj in ObjectDB.objects.all() for event in deserialize(obj.db.action_validation_events or [])]
    print(json.dumps({"events": events, "provider": str(provider.pk),
                      "number": number_for(descriptor(provider).reference), "issues": len(verify())}))


if __name__ == "__main__":
    main()
