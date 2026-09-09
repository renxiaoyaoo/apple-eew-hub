import sqlite3

from app.db import Database


def test_sqlite_backup_contains_committed_wal_data(tmp_path):
    source = Database(tmp_path / "source.sqlite3")
    source.init()
    source.set_state("example", {"value": 42})
    target = tmp_path / "backup.sqlite3"

    source.backup(target)

    with sqlite3.connect(target) as conn:
        value = conn.execute("SELECT value FROM app_state WHERE key = 'example'").fetchone()[0]
    assert '"value": 42' in value
