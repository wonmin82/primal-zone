"""빈 격리 DB에 실제 dev.py setup만 수행한다. 플레이어 fixture를 만들지 않는다."""

import importlib.util
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    run = Path(os.environ["PRIMAL_SMOKE_RUN_DIR"]).resolve()
    if Path.cwd() != run / "game" or not (run / ".primal-smoke").is_file():
        raise RuntimeError("격리 fresh 경로가 아닙니다.")
    if (run / "evennia-smoke.sqlite3").exists():
        raise RuntimeError("fresh는 기존 DB를 사용할 수 없습니다.")
    (run / ".phase7c-fresh").touch()
    shutil.copyfile(ROOT / "scripts" / "phase7c_initial_setup.py",
                    run / "game/server/conf/phase7c_initial_setup.py")
    with (run / "game/server/conf/settings_smoke.py").open("a", encoding="utf-8") as file:
        file.write('\nNEW_ACCOUNT_REGISTRATION_ENABLED = True\n'
                   'INITIAL_SETUP_MODULE = "server.conf.phase7c_initial_setup"\n')
    (run / "scripts").mkdir()
    shutil.copyfile(ROOT / "scripts/dev.py", run / "scripts/dev.py")
    spec = importlib.util.spec_from_file_location("isolated_dev", run / "scripts/dev.py")
    dev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dev)
    original_run = dev.run

    def isolated_run(*args, **kwargs):
        # Launcher는 DJANGO_SETTINGS_MODULE 환경을 덮어쓴다. 같은 setup 절차의
        # migrate/collectstatic에만 명시적 격리 settings 인자를 전달한다.
        assert args[:2] == ("-m", "evennia") and args[2] in ("migrate", "collectstatic")
        return original_run(*args, "--settings", "settings_smoke", **kwargs)

    dev.run = isolated_run
    dev.setup()
    print("fresh schema만 생성: 일반 account/Explorer/ItemEntity/ledger 미생성")
