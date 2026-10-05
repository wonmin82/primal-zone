r"""
Evennia settings file.

The available options are found in the default settings file found
here:

https://www.evennia.com/docs/latest/Setup/Settings-Default.html

Remember:

Don't copy more from the default file than you actually intend to
change; this will make sure that you don't overload upstream updates
unnecessarily.

When changing a setting requiring a file system path (like
path/to/actual/file.py), use GAME_DIR and EVENNIA_DIR to reference
your game folder and the Evennia library folders respectively. Python
paths (path.to.module) should be given relative to the game's root
folder (typeclasses.foo) whereas paths within the Evennia library
needs to be given explicitly (evennia.foo).

If you want to share your game dir, including its settings, you can
put secret game- or server-specific settings in secret_settings.py.

"""

# Use the defaults from Evennia unless explicitly overridden
######################################################################
# Evennia base server config
######################################################################
# This is the name of your game. Make it catchy!
import os

from evennia.settings_default import *  # noqa: F403

SERVERNAME = "원시구역"
GAME_SLOGAN = "사냥하고, 강해지고, 잊힌 섬을 탐험하세요."
BASE_CHARACTER_TYPECLASS = "typeclasses.explorers.Explorer"
LANGUAGE_CODE = "ko"
TIME_ZONE = "Asia/Seoul"
# 게임 접속 서비스는 모든 IPv4 인터페이스에서 받는다. AMP 내부 연결은 loopback을 유지한다.
TELNET_ENABLED = True
TELNET_PORTS = [8700]
TELNET_INTERFACES = ["0.0.0.0"]
SSL_ENABLED = True
SSL_PORTS = [8703]
SSL_INTERFACES = ["0.0.0.0"]
SSH_ENABLED = True
SSH_PORTS = [8704]
SSH_INTERFACES = ["0.0.0.0"]
WEBSERVER_INTERFACES = ["0.0.0.0"]
WEBSERVER_PORTS = [(8701, 8705)]
WEBSOCKET_CLIENT_INTERFACE = "0.0.0.0"
WEBSOCKET_CLIENT_PORT = 8702
AMP_PORT = 8706
# Bind 주소와 HTTP Host는 별개다. LAN IP/hostname으로도 Web 접속을 허용한다.
ALLOWED_HOSTS = ["*"]
MULTISESSION_MODE = 0
MAX_NR_CHARACTERS = 1
NEW_ACCOUNT_REGISTRATION_ENABLED = True
AUTH_USERNAME_VALIDATORS = [
    {
        "NAME": "django.core.validators.RegexValidator",
        "OPTIONS": {
            "regex": r"^[가-힣A-Za-z0-9_]{2,24}$",
            "message": "이름은 한글·영문·숫자·밑줄 2~24자로 입력하세요.",
        },
    },
    {"NAME": "evennia.server.validators.EvenniaUsernameAvailabilityValidator"},
]
INPUT_FUNC_MODULES = ["evennia.server.inputfuncs", "server.conf.primal_inputfuncs"]
COMMAND_PARSER = "server.conf.cmdparser.cmdparser"
INSTALLED_APPS = [*INSTALLED_APPS, "world.item_entities.apps.ItemEntitiesConfig"]  # noqa: F405

# Optional PostgreSQL configuration for the private playtest.
if os.environ.get("PRIMAL_DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["PRIMAL_DB_NAME"],
            "USER": os.environ["PRIMAL_DB_USER"],
            "PASSWORD": os.environ["PRIMAL_DB_PASSWORD"],
            "HOST": os.environ.get("PRIMAL_DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("PRIMAL_DB_PORT", "5432"),
        }
    }


######################################################################
# Settings given in secret_settings.py override those in this file.
######################################################################
try:
    from server.conf.secret_settings import *  # noqa: F403
except ImportError:
    print("secret_settings.py file not found or failed to import.")
