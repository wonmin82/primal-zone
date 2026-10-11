"""브라우저 재접속의 실제 Puppet ID만 격리 SQLite에서 읽는다. 변경/RPC 없음."""

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path


def sessions():
    run = Path(os.environ['PRIMAL_SMOKE_RUN_DIR']).resolve()
    database = Path(os.environ['PRIMAL_BROWSER_DB']).resolve()
    if (run.parent != (Path(__file__).resolve().parents[1]/'work/smoke').resolve()
            or not (run/'.primal-smoke').is_file()
            or database != run/'evennia-smoke.sqlite3'):
        raise RuntimeError('격리 실행과 DB 경로 불일치')
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True, timeout=5)) as connection:
        rows = connection.execute('SELECT db_key, db_sessid FROM objects_objectdb '
                                  'WHERE db_typeclass_path = ?', ('typeclasses.explorers.Explorer',))
        return {name: [value for value in (ids or '').split(',') if value] for name, ids in rows}


if __name__ == '__main__':
    print(json.dumps(sessions(), ensure_ascii=False))
