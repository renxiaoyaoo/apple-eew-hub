import anyio
import pytest

from app.core import ARRIVAL_TASKS, BACKGROUND_TASKS, decide_for_device, process_event, public_device, restore_scheduled_arrival_pushes
from app.db import Database
from app.models import EarthquakeEvent
from app.config import default_system_config, set_system_config


def device(**kwargs):
    base = {
        "id": 1,
        "name": "iPhone",
        "push_type": "bark",
        "bark_key": "secret-key",
        "push_url": "https://example.invalid/hook",
        "default_city": "成都双流",
        "latitude": 30.58,
        "longitude": 103.92,
        "min_magnitude": 4.5,
        "max_distance_km": 500,
        "min_intensity": 2,
        "enabled": 1,
        "receive_tests": 1,
    }
    base.update(kwargs)
    return base


def event(**kwargs):
    base = {
        "event_id": "evt",
        "source": "test",
        "epicenter": "四川宜宾市珙县",
        "latitude": 28.43,
        "longitude": 104.71,
        "magnitude": 5.9,
        "depth_km": 10,
        "origin_time": "2026-07-08T09:58:00+00:00",
        "test": True,
    }
    base.update(kwargs)
    return EarthquakeEvent(**base)


def test_decision_matches_drill_thresholds():
    decision = decide_for_device(event(), device(), {"distance_km": 199, "countdown_seconds": 18, "intensity": 3})
    assert decision.should_push is True
    assert decision.reason == "test drill"
    assert decision.intensity_text == "明显有感"


def test_test_drill_pushes_even_below_threshold():
    decision = decide_for_device(event(), device(), {"distance_km": 293, "countdown_seconds": 63, "intensity": 1})
    assert decision.should_push is True
    assert decision.reason == "test drill"


def test_global_major_earthquake_pushes_gently_when_far_away():
    decision = decide_for_device(
        event(test=False, source="emsc_global", magnitude=8.2, latitude=-38.2, longitude=-73.1),
        device(),
    )
    assert decision.should_push is True
    assert decision.reason == "global major earthquake"
    assert decision.intensity <= 1
    assert decision.intensity_text == "轻微震感"


def test_domestic_source_is_also_far_field_for_a_distant_device():
    decision = decide_for_device(
        event(test=False, source="cenc_eew", magnitude=7.2, latitude=31.0, longitude=104.0),
        device(latitude=-33.9, longitude=151.2),
    )
    assert decision.distance_km > 1000
    assert decision.should_push is True
    assert decision.reason == "global major earthquake"
    assert decision.intensity <= 1


def test_configured_global_major_threshold_controls_far_away_push():
    set_system_config({"global_min_magnitude": 7.0})
    try:
        decision = decide_for_device(
            event(test=False, source="emsc_global", magnitude=7.4, latitude=5.6, longitude=-76.6),
            device(max_distance_km=5000),
        )
    finally:
        set_system_config(default_system_config())

    assert decision.should_push is True
    assert decision.reason == "global major earthquake"
    assert decision.intensity <= 1


def test_global_far_alert_switch_only_disables_far_away_push():
    set_system_config({"global_min_magnitude": 7.0, "global_far_alert_enabled": False})
    try:
        far_decision = decide_for_device(
            event(test=False, source="emsc_global", magnitude=7.4, latitude=5.6, longitude=-76.6),
            device(max_distance_km=5000),
        )
        near_decision = decide_for_device(
            event(test=False, source="emsc_global", magnitude=7.4, latitude=30.59, longitude=103.93),
            device(max_distance_km=500),
        )
    finally:
        set_system_config(default_system_config())

    assert far_decision.should_push is False
    assert far_decision.reason == "global far alerts disabled"
    assert near_decision.should_push is True
    assert near_decision.reason == "global major earthquake"


def test_global_source_over_local_cap_does_not_match_local_threshold():
    set_system_config({"global_min_magnitude": 7.0, "global_far_alert_enabled": True})
    try:
        decision = decide_for_device(
            event(test=False, source="emsc_global", magnitude=6.8, latitude=3.8, longitude=96.0),
            device(max_distance_km=5000, min_magnitude=1, min_intensity=1),
        )
    finally:
        set_system_config(default_system_config())

    assert decision.distance_km > 1000
    assert decision.intensity <= 1
    assert decision.should_push is False
    assert decision.reason == "below threshold"


def test_nearby_magnitude_threshold_pushes_even_when_estimated_intensity_is_low():
    decision = decide_for_device(
        event(test=False, source="cq_eew", epicenter="四川内江市隆昌市", magnitude=4.6, latitude=29.22, longitude=105.205, depth_km=12),
        device(latitude=30.653431, longitude=104.015044, min_magnitude=4.5, max_distance_km=500, min_intensity=2),
    )

    assert decision.distance_km < 200
    assert decision.intensity < 2
    assert decision.should_push is True
    assert decision.reason == "local magnitude threshold matched"


def test_far_jma_m6_warning_does_not_match_loose_local_threshold():
    set_system_config({"global_min_magnitude": 7.0, "global_far_alert_enabled": True})
    try:
        decision = decide_for_device(
            event(
                test=False,
                source="jma_eew",
                epicenter="茨城県南部",
                latitude=36.0,
                longitude=140.1,
                magnitude=6.4,
                depth_km=80,
                origin_time="2026-08-23T02:00:39",
            ),
            device(max_distance_km=5000, min_magnitude=1, min_intensity=1),
        )
    finally:
        set_system_config(default_system_config())

    assert decision.distance_km > 1000
    assert decision.intensity <= 1
    assert decision.should_push is False
    assert decision.reason == "below threshold"


def test_near_jma_warning_still_uses_local_thresholds():
    decision = decide_for_device(
        event(
            test=False,
            source="jma_eew",
            epicenter="茨城県南部",
            latitude=36.0,
            longitude=140.1,
            magnitude=6.4,
            depth_km=80,
            origin_time="2026-08-23T02:00:39",
        ),
        device(latitude=35.9, longitude=140.0, max_distance_km=500, min_magnitude=4.5, min_intensity=2),
    )

    assert decision.distance_km <= 1000
    assert decision.should_push is True


def test_jma_forecast_only_does_not_push_even_nearby():
    decision = decide_for_device(
        event(
            test=False,
            source="jma_eew",
            epicenter="茨城県南部",
            latitude=36.0,
            longitude=140.1,
            magnitude=6.4,
            depth_km=80,
            origin_time="2026-08-23T02:00:39",
            raw={"isWarn": False},
        ),
        device(latitude=35.9, longitude=140.0, max_distance_km=500, min_magnitude=4.5, min_intensity=2),
    )

    assert decision.should_push is False
    assert decision.reason == "jma forecast only"


def test_global_major_earthquake_uses_local_intensity_when_device_is_nearby():
    decision = decide_for_device(
        event(test=False, magnitude=8.2, latitude=35.0, longitude=140.0),
        device(latitude=35.2, longitude=140.2, max_distance_km=500),
    )
    assert decision.should_push is True
    assert decision.intensity > 1
    assert decision.reason == "global major earthquake"


def test_device_can_disable_test_alerts():
    decision = decide_for_device(event(), device(receive_tests=0), {"distance_km": 199, "countdown_seconds": 18, "intensity": 3})
    assert decision.should_push is False
    assert decision.reason == "device disabled test alerts"


def test_public_device_redacts_push_secrets():
    exposed = public_device(device())
    assert "bark_key" not in exposed
    assert "push_url" not in exposed
    assert exposed["bark_key_configured"] is True
    assert exposed["push_url_configured"] is True


@pytest.mark.anyio
async def test_process_event_sends_initial_and_arrival_push(tmp_path, monkeypatch):
    async def fake_dispatch(device_row, event_row, decision):
        return {
            "channel": "bark",
            "ok": True,
            "status_code": 200,
            "latency_ms": 1,
            "message": f"sent {decision.arrival_seconds}",
        }

    monkeypatch.setattr("app.core.dispatch_push", fake_dispatch)
    db = Database(tmp_path / "eew.sqlite3")
    db.init()
    db.execute(
        """
        INSERT INTO devices
        (name, push_type, bark_key, push_url, default_city, latitude, longitude,
         min_magnitude, max_distance_km, min_intensity, enabled, receive_tests, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "iPhone",
            "bark",
            "fake-key",
            "",
            "成都",
            30.58,
            103.92,
            4.5,
            500,
            2,
            1,
            1,
            "now",
            "now",
        ),
    )

    await process_event(db, event(), {"distance_km": 199, "countdown_seconds": 1, "intensity": 3})
    await anyio.sleep(1.2)

    rows = db.query("SELECT push_phase, ok, message FROM pushes ORDER BY id")
    assert [row["push_phase"] for row in rows] == ["initial", "arrival"]
    assert [row["message"] for row in rows] == ["sent 1", "sent 0"]


@pytest.mark.anyio
async def test_background_push_failure_is_recorded_and_cleaned_up(tmp_path, monkeypatch, caplog):
    async def failing_dispatch(device_row, event_row, decision):
        raise RuntimeError("push backend down")

    monkeypatch.setattr("app.core.dispatch_push", failing_dispatch)
    monkeypatch.setattr("app.core.PUSH_RETRY_DELAYS", (0, 0, 0))
    db = Database(tmp_path / "eew.sqlite3")
    db.init()
    db.execute(
        """
        INSERT INTO devices
        (name, push_type, bark_key, push_url, default_city, latitude, longitude,
         min_magnitude, max_distance_km, min_intensity, enabled, receive_tests, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("iPhone", "bark", "fake-key", "", "成都", 30.58, 103.92, 4.5, 500, 2, 1, 1, "now", "now"),
    )

    await process_event(db, event(), {"distance_km": 199, "countdown_seconds": 0, "intensity": 3})
    await anyio.sleep(0.1)

    assert not BACKGROUND_TASKS
    assert "Background push task failed" in caplog.text
    row = db.one("SELECT ok, message FROM pushes")
    assert row["ok"] == 0
    assert row["message"] == "dispatch failed: RuntimeError"


@pytest.mark.anyio
async def test_failed_push_is_retried_before_being_recorded(tmp_path, monkeypatch):
    attempts = 0

    async def flaky_dispatch(device_row, event_row, decision):
        nonlocal attempts
        attempts += 1
        return {
            "channel": "bark",
            "ok": attempts == 3,
            "status_code": 200 if attempts == 3 else 503,
            "latency_ms": 1,
            "message": "ok" if attempts == 3 else "temporary failure",
        }

    monkeypatch.setattr("app.core.dispatch_push", flaky_dispatch)
    monkeypatch.setattr("app.core.PUSH_RETRY_DELAYS", (0, 0, 0))
    db = Database(tmp_path / "eew.sqlite3")
    db.init()
    db.execute(
        """
        INSERT INTO devices
        (name, push_type, bark_key, push_url, default_city, latitude, longitude,
         min_magnitude, max_distance_km, min_intensity, enabled, receive_tests, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("iPhone", "bark", "fake-key", "", "成都", 30.58, 103.92, 4.5, 500, 2, 1, 1, "now", "now"),
    )
    await process_event(db, event(event_id="retry-event"), {"distance_km": 199, "countdown_seconds": 0, "intensity": 3})
    await anyio.sleep(0.1)

    assert attempts == 3
    assert db.one("SELECT ok, message FROM pushes")["ok"] == 1


def test_decision_captures_device_location_snapshot():
    decision = decide_for_device(event(), device(), {"distance_km": 199, "countdown_seconds": 18, "intensity": 3})
    assert decision.device_city == "成都双流"
    assert decision.device_latitude == 30.58
    assert decision.device_longitude == 103.92


def test_restore_scheduled_arrival_pushes_reschedules_pending_arrival(tmp_path, monkeypatch):
    captured = []

    def fake_schedule(db_arg, device_arg, event_arg, decision_arg):
        captured.append((device_arg, event_arg, decision_arg))
        return True

    monkeypatch.setattr("app.core._schedule_arrival_push", fake_schedule)
    db = Database(tmp_path / "eew.sqlite3")
    db.init()
    db.execute(
        """
        INSERT INTO devices
        (name, push_type, bark_key, push_url, default_city, latitude, longitude,
         min_magnitude, max_distance_km, min_intensity, enabled, receive_tests, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("iPhone", "bark", "fake-key", "", "成都", 30.58, 103.92, 4.5, 500, 2, 1, 1, "now", "now"),
    )
    anyio.run(process_event, db, event(event_id="restore-event"), {"distance_km": 199, "countdown_seconds": 120, "intensity": 3})
    BACKGROUND_TASKS.clear()
    captured.clear()

    scheduled = restore_scheduled_arrival_pushes(db)

    assert scheduled == 1
    assert len(captured) == 1
    restored_device, restored_event, _ = captured[0]
    assert restored_device["latitude"] == 30.58
    assert restored_device["longitude"] == 103.92
    assert restored_event.latitude == 28.43
    assert restored_event.longitude == 104.71


def test_process_event_does_not_schedule_duplicate_arrival_tasks(tmp_path, monkeypatch):
    captured = []

    class FakeTask:
        def __init__(self, coro):
            self.coro = coro
            self.cancelled = False
            self.coro.close()

        def done(self):
            return False

        def cancel(self):
            self.cancelled = True

    def fake_create(coro):
        task = FakeTask(coro)
        captured.append(task)
        return task

    monkeypatch.setattr("app.core._create_background_task", fake_create)
    db = Database(tmp_path / "eew.sqlite3")
    db.init()
    db.execute(
        """
        INSERT INTO devices
        (name, push_type, bark_key, push_url, default_city, latitude, longitude,
         min_magnitude, max_distance_km, min_intensity, enabled, receive_tests, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("iPhone", "bark", "fake-key", "", "成都", 30.58, 103.92, 4.5, 500, 2, 1, 1, "now", "now"),
    )
    try:
        anyio.run(process_event, db, event(event_id="multi-report", report_num=1), {"distance_km": 199, "countdown_seconds": 120, "intensity": 3})
        anyio.run(process_event, db, event(event_id="multi-report", report_num=2), {"distance_km": 199, "countdown_seconds": 90, "intensity": 3})
    finally:
        ARRIVAL_TASKS.clear()

    assert len(captured) == 3
    assert captured[1].cancelled is True
    assert captured[2].cancelled is False
    rows = db.query("SELECT push_phase FROM pushes ORDER BY id")
    assert [row["push_phase"] for row in rows] == ["initial"]


def test_cancel_report_cancels_pending_arrival(tmp_path, monkeypatch):
    captured = []

    class FakeTask:
        def __init__(self, coro):
            self.cancelled = False
            coro.close()

        def done(self):
            return False

        def cancel(self):
            self.cancelled = True

    def fake_create(coro):
        task = FakeTask(coro)
        captured.append(task)
        return task

    monkeypatch.setattr("app.core._create_background_task", fake_create)
    db = Database(tmp_path / "eew.sqlite3")
    db.init()
    db.execute(
        """
        INSERT INTO devices
        (name, push_type, bark_key, push_url, default_city, latitude, longitude,
         min_magnitude, max_distance_km, min_intensity, enabled, receive_tests, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("iPhone", "bark", "fake-key", "", "成都", 30.58, 103.92, 4.5, 500, 2, 1, 1, "now", "now"),
    )
    try:
        anyio.run(process_event, db, event(event_id="cancel-event", report_num=1), {"distance_km": 199, "countdown_seconds": 120, "intensity": 3})
        arrival_task = ARRIVAL_TASKS[("cancel-event", 1)]
        anyio.run(process_event, db, event(event_id="cancel-event", report_num=2, is_cancel=True), {"distance_km": 199, "countdown_seconds": 90, "intensity": 3})
        assert arrival_task.cancelled is True
        assert ("cancel-event", 1) not in ARRIVAL_TASKS
    finally:
        ARRIVAL_TASKS.clear()


def test_global_event_within_1000km_is_not_reclassified_by_device_radius():
    decision = decide_for_device(
        event(test=False, source="emsc_global", magnitude=7.2, latitude=31.3, longitude=104.0),
        device(max_distance_km=50),
    )

    assert 50 < decision.distance_km < 1000
    assert decision.intensity > 1
