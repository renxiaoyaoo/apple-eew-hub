from datetime import datetime, timedelta, timezone

import pytest

from app.config import default_system_config, set_system_config
from app.db import Database
from app.source_health import SourceHealthMonitor


def insert_device(db: Database) -> None:
    db.execute(
        """
        INSERT INTO devices
        (name, push_type, bark_key, push_url, default_city, latitude, longitude,
         min_magnitude, max_distance_km, min_intensity, enabled, receive_tests,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("测试设备", "bark", "fake-key", "", "成都", 30.57, 104.06, 4.5, 500, 2, 1, 1, "now", "now"),
    )


@pytest.mark.anyio
async def test_source_outage_alerts_once_and_sends_recovery(tmp_path, monkeypatch):
    db = Database(tmp_path / "eew.sqlite3")
    db.init()
    insert_device(db)
    sent = []

    async def fake_dispatch(device, title, body, recovery=False):
        sent.append((title, body, recovery))
        return {"channel": device["push_type"], "ok": True, "status_code": 200, "latency_ms": 1, "message": "ok"}

    monkeypatch.setattr("app.source_health.dispatch_system_notification", fake_dispatch)
    set_system_config(
        {
            **default_system_config(),
            "wolfx_sources": ["sc_eew"],
            "global_enabled": False,
            "source_health_alert_enabled": True,
            "source_health_alert_after_seconds": 30,
        }
    )
    monitor = SourceHealthMonitor(db)
    started = datetime(2026, 9, 27, tzinfo=timezone.utc)
    db.set_state("listener", {"sources": {"sc_eew": {"connected": False}}})

    try:
        await monitor.check_once(started)
        await monitor.check_once(started + timedelta(seconds=31))
        await monitor.check_once(started + timedelta(seconds=60))
        assert len(sent) == 1
        assert sent[0][0] == "地震实时源异常"
        assert sent[0][2] is False

        db.set_state("listener", {"sources": {"sc_eew": {"connected": True}}})
        await monitor.check_once(started + timedelta(seconds=61))
        assert len(sent) == 2
        assert sent[1][0] == "地震实时源已恢复"
        assert sent[1][2] is True
    finally:
        set_system_config(default_system_config())
