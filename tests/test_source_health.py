from datetime import datetime, timedelta, timezone

import pytest

from app.config import default_system_config, set_system_config
from app.db import Database
from app.source_health import SourceHealthMonitor, source_health_snapshot


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


def test_legacy_seconds_setting_is_migrated_to_minutes():
    legacy = default_system_config()
    legacy.pop("source_health_alert_after_minutes")
    legacy["source_health_alert_after_seconds"] = 3600

    try:
        config = set_system_config(legacy)
        assert config["source_health_alert_after_minutes"] == 60
        assert "source_health_alert_after_seconds" not in config
    finally:
        set_system_config(default_system_config())


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
            "source_health_alert_after_minutes": 1,
        }
    )
    monitor = SourceHealthMonitor(db)
    started = datetime(2026, 9, 27, tzinfo=timezone.utc)
    db.set_state("listener", {"sources": {"sc_eew": {"connected": False}}})

    try:
        await monitor.check_once(started)
        await monitor.check_once(started + timedelta(seconds=61))
        await monitor.check_once(started + timedelta(seconds=90))
        assert len(sent) == 1
        assert sent[0][0] == "地震实时源异常"
        assert sent[0][2] is False

        db.set_state("listener", {"sources": {"sc_eew": {"connected": True}}})
        await monitor.check_once(started + timedelta(seconds=91))
        assert len(sent) == 2
        assert sent[1][0] == "地震实时源已恢复"
        assert sent[1][2] is True
    finally:
        set_system_config(default_system_config())


@pytest.mark.anyio
async def test_each_source_gets_its_own_outage_timer(tmp_path, monkeypatch):
    db = Database(tmp_path / "eew.sqlite3")
    db.init()
    insert_device(db)
    sent = []

    async def fake_dispatch(device, title, body, recovery=False):
        sent.append((title, body, recovery))
        return {"channel": "bark", "ok": True, "status_code": 200, "latency_ms": 1, "message": "ok"}

    monkeypatch.setattr("app.source_health.dispatch_system_notification", fake_dispatch)
    set_system_config(
        {
            **default_system_config(),
            "wolfx_sources": ["sc_eew", "cq_eew"],
            "global_enabled": False,
            "source_health_alert_after_minutes": 1,
        }
    )
    monitor = SourceHealthMonitor(db)
    started = datetime(2026, 10, 1, tzinfo=timezone.utc)
    try:
        db.set_state("listener", {"sources": {"sc_eew": {"connected": False}, "cq_eew": {"connected": True}}})
        await monitor.check_once(started)
        db.set_state("listener", {"sources": {"sc_eew": {"connected": True}, "cq_eew": {"connected": False}}})
        await monitor.check_once(started + timedelta(seconds=50))
        await monitor.check_once(started + timedelta(seconds=70))
        assert sent == []

        await monitor.check_once(started + timedelta(seconds=111))
        assert len(sent) == 1
        assert "重庆地震预警" in sent[0][1]
    finally:
        set_system_config(default_system_config())


def test_custom_wolfx_urls_are_the_expected_health_sources(tmp_path):
    db = Database(tmp_path / "eew.sqlite3")
    db.init()
    set_system_config(
        {
            **default_system_config(),
            "wolfx_ws_url": "wss://example.test/custom_a,wss://example.test/custom_b",
            "global_enabled": False,
        }
    )
    db.set_state(
        "listener",
        {"sources": {"custom_a": {"connected": True}, "custom_b": {"connected": False}}},
    )
    try:
        assert source_health_snapshot(db) == (["custom_a", "custom_b"], ["custom_b"])
    finally:
        set_system_config(default_system_config())
