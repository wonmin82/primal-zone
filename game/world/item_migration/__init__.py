"""명시적 maintenance migration entry points (version 1)."""

def apply():
    from .workflow import apply as run

    return run()


def cutover(*, accept_warnings=False):
    from .workflow import cutover as run

    return run(accept_warnings=accept_warnings)


def dry_run():
    from .workflow import dry_run as run

    return run()


def verify():
    from .workflow import verify as run

    return run()

__all__ = ["apply", "cutover", "dry_run", "verify"]
