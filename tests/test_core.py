from app.core import decide_for_device, public_device
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
