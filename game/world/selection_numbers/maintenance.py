"""운영자가 명시적으로 요청한 번호 seed/backfill의 백업 경계."""

import sqlite3
from contextlib import closing
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import connection


def backup_database(target):
    target = Path(target).resolve()
    source = Path(connection.settings_dict["NAME"]).resolve()
    if connection.vendor != "sqlite" or connection.in_atomic_block or str(connection.settings_dict["NAME"]).startswith("file:") or connection.settings_dict["NAME"] == ":memory:":
        raise ValidationError("명시적인 file-backed SQLite maintenance에서만 백업할 수 있습니다.")
    if target == source or target.exists():
        raise ValidationError("백업 파일은 기존 파일을 덮어쓸 수 없습니다.")
    connection.ensure_connection()
    # O_EXCL로 기존 사용자 파일을 보호한다. SQLite backup API는 WAL 변경도 포함한다.
    with target.open("xb"):
        pass
    with closing(sqlite3.connect(target)) as backup:
        connection.connection.backup(backup)
