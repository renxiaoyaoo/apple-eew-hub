import anyio
import pytest

from app.core import decide_for_device, process_event, public_device
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
        event(test=False, magnitude=8.2, latitude=-38.2, longitude=-73.1),
        device(),
    )
    assert decision.should_push is True
    assert decision.reason == "global major earthquake"
    assert decision.intensity <= 1
    assert decision.intensity_text == "轻微震感"


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
