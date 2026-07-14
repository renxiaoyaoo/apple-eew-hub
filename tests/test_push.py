from types import SimpleNamespace
from urllib.parse import unquote

from app.models import EarthquakeEvent
from app.push import bark_payload


def event(**kwargs):
    base = {
        "event_id": "evt",
        "source": "sc_eew",
        "epicenter": "四川阿坝州小金县",
        "latitude": 31.0,
        "longitude": 102.4,
        "magnitude": 6.5,
        "depth_km": 10,
        "origin_time": "2026-07-13 01:03:28",
        "test": False,
    }
    base.update(kwargs)
    return EarthquakeEvent(**base)


def test_red_bark_payload_uses_call_and_critical_level():
    path, query = bark_payload(event(), 80, 5, "强烈震感，注意避险", 12)
    decoded = unquote(path)

    assert path.startswith("%E5%BC%BA%E9%9C%87%E9%A2%84%E8%AD%A6")
    assert "12秒后到达" in decoded
    assert query["level"] == "critical"
    assert query["call"] == "1"
    assert query["volume"] == "10"


def test_red_arrival_payload_does_not_use_call():
    path, query = bark_payload(event(), 80, 5, "强烈震感，注意避险", 0)

    assert "%E6%A8%AA%E6%B3%A2%E5%B7%B2%E5%88%B0%E8%BE%BE" in path
    assert query["level"] == "critical"
    assert "call" not in query


def test_blue_global_payload_does_not_use_local_countdown():
    path, query = bark_payload(event(source="emsc_global", magnitude=8.1), 9000, 1, "轻微震感", 0)

    assert "%E5%85%A8%E7%90%83%E7%89%B9%E5%A4%A7%E5%9C%B0%E9%9C%87%E6%8F%90%E9%86%92" in path
    assert "call" not in query


def test_bark_payload_links_to_device_specific_detail(monkeypatch):
    monkeypatch.setattr("app.push.settings", SimpleNamespace(public_base_url="https://h-eew.example"))

    _, query = bark_payload(event(event_id="evt/1"), 80, 3, "明显有感", 12, device_id=7)

    assert query["url"] == "https://h-eew.example/event/evt%2F1?device_id=7"
