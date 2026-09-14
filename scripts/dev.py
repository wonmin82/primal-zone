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
        "command", choices=["setup", "start", "stop", "reload", "test", "check", "admin-password"]
    )
    command = parser.parse_args().command
    if command == "setup":
        setup()
    elif command == "test":
        ensure_secret()
        run("-m", "unittest", "world.test_rules")
        run("-m", "evennia", "test", "tests", "--settings", "settings", "--noinput")
    elif command == "check":
        run("-m", "ruff", "check", "game", "scripts", cwd=ROOT)
    elif command == "admin-password":
        run("-m", "evennia", "changepassword", "admin")
    else:
        run("-m", "evennia", command)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
