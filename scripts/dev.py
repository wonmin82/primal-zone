"""Portable local developer commands. Run with the project's Python environment."""

import argparse
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "game"


def run(*args, cwd=GAME):
    subprocess.run(
        [sys.executable, *args], cwd=cwd, check=True, env={**os.environ, "PYTHONUTF8": "1"}
    )


def ensure_secret():
    (GAME / "server" / "logs").mkdir(parents=True, exist_ok=True)
    target = GAME / "server" / "conf" / "secret_settings.py"
    if not target.exists():
        target.write_text(
            "# Local only. Never commit this file.\nSECRET_KEY = "
            + repr(secrets.token_urlsafe(48))
            + "\n",
            encoding="utf-8",
        )


def setup():
    ensure_secret()
    run("-m", "evennia", "migrate", "--noinput")
    os.chdir(GAME)
    sys.path.insert(0, str(GAME))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.conf.settings")
    import django

    django.setup()
    import evennia

    evennia._init()
    from evennia.accounts.models import AccountDB

    if not AccountDB.objects.filter(pk=1).exists():
        if AccountDB.objects.exists():
            raise RuntimeError("Account #1 is missing. Restore the database before proceeding.")
        admin = AccountDB.objects.create_superuser("admin", "", None)
        admin.set_unusable_password()
        admin.save()
        print("Local admin created with password sign-in disabled. Use admin-password if needed.")
    run("-m", "evennia", "collectstatic", "--noinput")
    print("Setup complete. Start the server, then create a regular explorer in the browser.")


def main():
    parser = argparse.ArgumentParser(description="Primal Zone local development")
    parser.add_argument(
        "command", choices=["setup", "start", "stop", "reload", "test", "check", "admin-password",
                            "smoke", "smoke-full", "migrate-items"]
    )
    parser.add_argument("test_labels", nargs="*", help="선택한 Evennia 테스트 경로")
    parser.add_argument("--parallel", type=int, help="통합 테스트 프로세스 수 (기본 최대 4)")
    parser.add_argument("--reverse", action="store_true", help="테스트 순서를 뒤집어 격리 확인")
    mode_group = parser.add_mutually_exclusive_group()
    for mode in ("dry-run", "apply", "verify", "cutover"):
        mode_group.add_argument("--" + mode, action="store_true")
    parser.add_argument("--accept-warnings", action="store_true")
    args = parser.parse_args()
    command = args.command
    modes = [mode for mode in ("dry-run", "apply", "verify", "cutover") if getattr(args, mode.replace("-", "_"))]
    if (command == "migrate-items") != bool(modes) or args.accept_warnings and command != "migrate-items":
        parser.error("migrate-items에는 정확히 하나의 migration mode가 필요합니다.")
    if command != "test" and (args.test_labels or args.parallel is not None or args.reverse):
        parser.error("테스트 경로와 --parallel/--reverse는 test에만 사용할 수 있습니다.")
    if args.parallel is not None and args.parallel < 1:
        parser.error("--parallel은 1 이상의 정수여야 합니다.")
    if command == "migrate-items":
        run("-m", "evennia", "migrate_items", "--" + modes[0], *(["--accept-warnings"] if args.accept_warnings else []))
    elif command == "setup":
        setup()
    elif command == "test":
        ensure_secret()
        if not args.test_labels:
            run("-m", "unittest", "discover", "-s", "world", "-p", "test_*.py")
        workers = args.parallel or min(4, os.process_cpu_count() or 1)
        options = ["--reverse"] if args.reverse else []
        run(
            "-m", "evennia", "test", *(args.test_labels or ["tests"]),
            "--settings", "settings_test", "--noinput", "--parallel", str(workers),
            "--timing", *options,
        )
    elif command == "check":
        run("-m", "ruff", "check", "game", "scripts", cwd=ROOT)
    elif command in ("smoke", "smoke-full"):
        run(str(ROOT / "scripts" / "smoke.py"), "--mode",
            "full" if command == "smoke-full" else "quick", cwd=ROOT)
    elif command == "admin-password":
        run("-m", "evennia", "changepassword", "admin")
    else:
        run("-m", "evennia", command)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
