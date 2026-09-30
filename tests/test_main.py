import anyio

from app.config import default_system_config, set_system_config
from app.db import Database
from app.main import export_config, import_config, logs, status, update_system_config
from app.models import SystemConfigPatch


def test_logs_return_only_latest_decision_per_device(tmp_path, monkeypatch):
    database = Database(tmp_path / "eew.sqlite3")
    database.init()
    monkeypatch.setattr("app.main.db", database)
    database.execute(
        """
        INSERT INTO events
        (event_id, source, report_num, is_final, is_cancel, epicenter, latitude, longitude,
         magnitude, depth_km, origin_time, raw_json, test, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("event-1", "cenc_eew", 2, 0, 0, "测试震中", 30, 104, 5, 10, "2026-09-09T00:00:00+00:00", "{}", 0, "now", "now"),
    )
    for should_push in (0, 1):
        database.execute(
            """
            INSERT INTO decisions
            (event_id, device_id, distance_km, arrival_seconds, intensity, intensity_text,
             status, should_push, reason, pushed, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("event-1", 1, 100, 10, 2, "轻微震感", "pending", should_push, "test", 0, "now"),
        )

    result = anyio.run(logs, 100, 200, 200, 300)

    assert len(result["decisions"]) == 1
    assert result["decisions"][0]["should_push"] == 1
    assert result["counts"]["triggered_events"] == 1


def test_config_export_excludes_push_credentials(tmp_path, monkeypatch):
    database = Database(tmp_path / "eew.sqlite3")
    database.init()
    monkeypatch.setattr("app.main.db", database)
    database.execute(
        """
        INSERT INTO devices
        (name, push_type, bark_key, push_url, default_city, latitude, longitude,
         min_magnitude, max_distance_km, min_intensity, enabled, receive_tests,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "测试设备", "bark", "public-test-key", "https://push.example.test/topic",
            "成都", 30.57, 104.06, 4.5, 500, 2, 1, 1, "now", "now",
        ),
    )

    result = anyio.run(export_config)

    assert result["secrets_included"] is False
    assert "bark_key" not in result["devices"][0]
    assert "push_url" not in result["devices"][0]


def test_alert_style_update_does_not_restart_listeners(tmp_path, monkeypatch):
    database = Database(tmp_path / "eew.sqlite3")
    database.init()
    monkeypatch.setattr("app.main.db", database)

    class FakeListener:
        def __init__(self):
            self.stops = 0
            self.starts = 0

        async def stop(self):
            self.stops += 1

        def start(self):
            self.starts += 1

    wolfx = FakeListener()
    global_listener = FakeListener()
    monkeypatch.setattr("app.main.listener", wolfx)
    monkeypatch.setattr("app.main.global_listener", global_listener)
    set_system_config(default_system_config())
    try:
        anyio.run(update_system_config, SystemConfigPatch(alert_red_intensity=5))
    finally:
        set_system_config(default_system_config())

    assert (wolfx.stops, wolfx.starts) == (0, 0)
    assert (global_listener.stops, global_listener.starts) == (0, 0)


def test_status_only_counts_enabled_sources(tmp_path, monkeypatch):
    database = Database(tmp_path / "eew.sqlite3")
    database.init()
    monkeypatch.setattr("app.main.db", database)
    database.set_state("listener", {"sources": {"sc_eew": {"connected": True}}})
    database.set_state("global_listener", {"sources": {"emsc_global": {"connected": True}}})
    set_system_config(
        {
            **default_system_config(),
            "wolfx_sources": ["sc_eew"],
            "global_enabled": False,
        }
    )
    try:
        result = anyio.run(status)
    finally:
        set_system_config(default_system_config())

    assert result["sources"] == ["sc_eew"]
    assert result["listener"]["source_count"] == 1
    assert result["listener"]["connected_count"] == 1


def test_config_import_merges_and_preserves_push_credentials(tmp_path, monkeypatch):
    database = Database(tmp_path / "eew.sqlite3")
    database.init()
    monkeypatch.setattr("app.main.db", database)
    database.execute(
        """
        INSERT INTO devices
        (name, push_type, bark_key, push_url, default_city, latitude, longitude,
         min_magnitude, max_distance_km, min_intensity, enabled, receive_tests,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("测试设备", "bark", "kept-secret", "", "成都", 30.57, 104.06, 4.5, 500, 2, 1, 1, "now", "now"),
    )

    async def fake_backup():
        return {"ok": True, "path": "test-backup.sqlite3"}

    monkeypatch.setattr("app.main.backup", fake_backup)
    result = anyio.run(
        import_config,
        {
            "devices": [
                {
                    "name": "测试设备",
                    "push_type": "bark",
                    "default_city": "重庆",
                    "latitude": 29.56,
                    "longitude": 106.55,
                }
            ]
        },
    )

    saved = database.one("SELECT bark_key, default_city FROM devices WHERE name = ?", ("测试设备",))
    assert result["mode"] == "merge"
    assert saved == {"bark_key": "kept-secret", "default_city": "重庆"}
