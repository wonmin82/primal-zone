"""운영자가 단계별로 실행하는 아이템 maintenance 명령."""

import json

from django.core.management.base import BaseCommand, CommandError

from world import item_migration


class Command(BaseCommand):
    help = "아이템 전체 변환: dry-run/apply/verify/cutover를 분리하여 실행합니다."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        for mode in ("dry-run", "apply", "verify", "cutover"):
            group.add_argument("--" + mode, action="store_true")
        parser.add_argument("--accept-warnings", action="store_true")

    def handle(self, **options):
        import evennia
        evennia._init()
        mode = next(mode for mode in ("dry_run", "apply", "verify", "cutover") if options[mode])
        try:
            report = getattr(item_migration, mode)(**({"accept_warnings": options["accept_warnings"]} if mode == "cutover" else {}))
        except Exception as error:
            raise CommandError(str(error)) from error
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        if report["errors"]:
            raise CommandError("migration 검사 실패. 보고서의 source 오류를 확인하세요.")
