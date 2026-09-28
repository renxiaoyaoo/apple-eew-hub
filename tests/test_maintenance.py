from types import SimpleNamespace

from app.db import Database
from app.maintenance import MaintenanceManager


def test_daily_backup_is_created_and_old_automatic_backups_are_pruned(tmp_path, monkeypatch):
    database = Database(tmp_path / "eew.sqlite3")
    database.init()
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for day in ("20260101", "20260102", "20260103"):
        (backup_dir / f"eew-hub-auto-{day}.sqlite3").write_bytes(b"old")
    monkeypatch.setattr(
        "app.maintenance.settings",
        SimpleNamespace(data_dir=tmp_path, backup_retention_days=2, map_cache_max_files=100),
    )

    MaintenanceManager(database).run_once()

    automatic = list(backup_dir.glob("eew-hub-auto-*.sqlite3"))
    assert len(automatic) == 2
    assert any(path.stat().st_size > 3 for path in automatic)
