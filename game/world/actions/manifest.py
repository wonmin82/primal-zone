"""설정에 명시된 패키지만 읽는다. 생산 콘텐츠의 전체 이전은 Phase 2다."""

from functools import lru_cache
from importlib import import_module

from django.conf import settings
from world.actions.registry import compile_manifest
from world.actions.schema import PackageManifest


def protected_names():
    from commands.aliases import ARGUMENT_SHORTCUTS, SHORTCUTS
    from commands.default_cmdsets import AccountCmdSet, CharacterCmdSet, UnloggedinCmdSet
    from world.content import DIRECTION_ALIASES, ROOMS

    names = set(SHORTCUTS) | set(ARGUMENT_SHORTCUTS) | set(DIRECTION_ALIASES)
    names.update(DIRECTION_ALIASES.values())
    for cmdset in (CharacterCmdSet(), AccountCmdSet(), UnloggedinCmdSet()):
        names.update(cmdset.get_all_cmd_keys_and_aliases())
    for room in ROOMS.values():
        names.update(room["exits"])
        names.update(room.get("blocked_exits", {}))
    names.update(name.lstrip(settings.CMD_IGNORE_PREFIXES) for name in tuple(names))
    return frozenset(name.casefold() for name in names)


@lru_cache(maxsize=8)
def compiled(paths):
    packages = tuple(import_module(path).PACKAGE for path in paths)
    return compile_manifest(PackageManifest(packages), protected_names())


def get_index():
    return compiled(tuple(getattr(settings, "ACTION_CONTENT_PACKAGES", ())))
