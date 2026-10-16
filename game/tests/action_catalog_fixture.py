"""공개 어휘/문서 검사 전용 카탈로그. 실행 Scope나 접근 권한을 부여하지 않는다."""

from commands.action_command import DynamicActionCommand
from commands.default_cmdsets import CharacterCmdSet
from world.actions.manifest import get_index
from world.actions.presentation import help_metadata


def public_action_catalog():
    """운영 Compiled Index와 실제 Command 어댑터를 정적 parser 검사에 연결한다.

    반환 CmdSet은 문서 예시의 공개 문법 검사에만 사용한다. 캐릭터의 CmdSet에
    설치하지 않으며 실제 실행은 기존 Scope Composer와 Gateway 검증을 따른다.
    """
    cmdset = CharacterCmdSet()
    entries = help_metadata(get_index())
    for entry in entries:
        command = DynamicActionCommand(key=entry.key, aliases=entry.aliases)
        command.verb_id = entry.id
        cmdset.add(command)
    return cmdset, entries
