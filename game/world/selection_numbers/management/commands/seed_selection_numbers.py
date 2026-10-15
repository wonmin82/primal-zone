"""번호 maintenance는 명시적인 CLI만 제공한다. 서버 시작/조회에서 자동 실행하지 않는다."""

from django.core.management.base import BaseCommand, CommandError

from world.selection_numbers.api import backfill, verify


class Command(BaseCommand):
    help = "영속 선택 번호를 검사하거나 백업 후 명시적으로 초기 할당합니다."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--backup")
        parser.add_argument("--verify", action="store_true")

    def handle(self, *args, **options):
        if options["verify"]:
            if options["apply"] or options["backup"]:
                raise CommandError("verify는 쓰기 옵션과 함께 사용할 수 없습니다.")
            issues = verify()
            self.stdout.write(f"번호 검증 오류: {len(issues)}")
            if issues:
                raise CommandError("번호 상태가 실물/Scope와 일치하지 않습니다.")
            return
        if options["apply"] and not options["backup"]:
            raise CommandError("apply에는 새 SQLite 백업 파일 경로가 필요합니다.")
        result = backfill(dry_run=not options["apply"], backup_path=options["backup"])
        self.stdout.write(f"후보: {result['candidates']}, 검증 오류: {len(result['issues'])}, 쓰기: {result['written']}")
