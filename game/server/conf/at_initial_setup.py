"""Evennia 기본 실물과 Actor 월드를 Fresh DB에서 함께 확정한다."""


def prepare_world():
    from evennia.server.initial_setup import create_objects
    from evennia.server.models import ServerConfig
    from world.bootstrap import build_world, runtime_world_issues
    from world.world_format import initialize_world

    def build():
        create_objects()
        build_world()
        ServerConfig.objects.conf("last_initial_setup_step", "create_objects")

    return initialize_world(build, lambda: runtime_world_issues(installing=True))


def handle_setup(last_step=None):
    from evennia.server.initial_setup import handle_setup as evennia_setup
    from world.bootstrap import runtime_world_issues
    from world.world_format import require_ready

    if last_step is None:
        prepare_world()
        last_step = "create_objects"
    else:
        require_ready(runtime_world_issues)
    evennia_setup(last_step)


def at_initial_setup():
    """기본 초기화가 호출하는 후속 Hook."""
