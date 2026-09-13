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
TELNET_ENABLED = False
WEBSERVER_INTERFACES = ["127.0.0.1"]
WEBSOCKET_CLIENT_INTERFACE = "127.0.0.1"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
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
