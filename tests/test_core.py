import anyio
import pytest

from app.core import decide_for_device, process_event, public_device
from app.db import Database
from app.models import EarthquakeEvent


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
