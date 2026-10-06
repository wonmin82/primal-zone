"""Smoke 전용 새 DB와 일반 계정 fixture. CLI harness의 자식 프로세스에서만 실행한다."""

import json
import sys


def setup(credentials):
    from django.conf import settings
    from server.conf.smoke_support import require_smoke

    # Django/Evennia 초기화나 migrate 전에 검사한다.
    require_smoke(settings)
    import django

    django.setup()
    from django.core.management import call_command

    call_command("migrate", interactive=False, verbosity=0)
    import evennia

    evennia._init()
    from evennia.accounts.models import AccountDB
    from evennia.server.initial_setup import create_objects
    from evennia.server.models import ServerConfig
    from evennia.utils.create import create_account
    from world import rules
    from world.bootstrap import build_world
    from world.item_runtime import initialize_fresh

    if AccountDB.objects.exists():
        raise RuntimeError("fixture는 비어 있는 새 smoke DB에서만 생성할 수 있습니다.")
    admin = AccountDB.objects.create_superuser("admin", "", None)
    admin.set_unusable_password()
    admin.save()
    create_objects()
    initialize_fresh()
    rooms = build_world()
    for name, password in credentials:
        # 공개 가입을 호출하지 않는다. 정상 Account/Character API와 일반 Player 권한을 쓴다.
        account = create_account(name, email="", password=password, typeclass=settings.BASE_ACCOUNT_TYPECLASS,
                                 permissions=settings.PERMISSION_ACCOUNT_DEFAULT)
        character, errors = account.create_character(location=rooms["staging_room"],
                                                      home=rooms["dock"])
        if errors or character is None:
            raise RuntimeError("smoke fixture character 생성에 실패했습니다.")
        from world.equipment_service import unequip_item
        from world.item_entities import api

        weapon = api.items_in_location("equipment", owner_object=character).get(slot="hands")
        unequip_item(character, str(weapon.pk))
        profile = character.profile()
        # 매입 후 재구매까지 포함한 Full 본부 서비스 동선의 준비금.
        profile["credits"] = 150
        profile["attributes"]["constitution"]["allocated"] = 4
        # 맨손 공격으로 양쪽 참여와 outsider 거절을 확인할 시간을 확보한다.

        profile["hp"] = rules.stats(profile)["max_hp"]
        profile["mental"] = 10
        if settings.PRIMAL_SMOKE_MODE == "full":
            # 진행 전제만 준비한다. 수리·정산·구매·패배 결과는 실제 명령으로 만든다.
            if name == credentials[0][0]:
                profile["inventory"]["scrap"] = 10
            if name == credentials[2][0]:
                # 자연회복으로 저체력 fixture가 오래 대기하며 과도하게 회복하지 않도록
                # 패배 검증자는 정상 Lv1 최대 HP를 쓴다. 실제 전투가 패배를 만든다.
                profile["attributes"]["constitution"]["allocated"] = 0
                profile["hp"] = 1
        character.save_profile(profile)
    call_command("collectstatic", interactive=False, verbosity=0)
    # 정상 초기 객체·정적 파일 준비를 마쳤다. 첫 시작의 자동 재시작은 필요하지 않다.
    ServerConfig.objects.conf("last_initial_setup_step", "done")
    print("새 SQLite DB / 월드 / 일반 fixture 계정 3개 준비 완료")


if __name__ == "__main__":
    setup(json.load(sys.stdin))
