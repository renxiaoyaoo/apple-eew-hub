from types import SimpleNamespace
from urllib.parse import unquote

import pytest

from app.models import Decision
from app.models import EarthquakeEvent
from app.push import bark_payload, ntfy_priority, push_text, send_webhook


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


def decision(**kwargs):
    base = {
        "device_id": 1,
        "device_name": "iPhone",
        "distance_km": 9000,
        "arrival_seconds": 0,
        "intensity": 1,
        "intensity_text": "轻微震感",
        "status": "passed",
        "should_push": True,
        "reason": "global major earthquake",
    }
    base.update(kwargs)
    return Decision(**base)


@pytest.mark.parametrize(
    ("magnitude", "title", "level", "volume", "priority"),
    [
        (7.4, "全球大震提醒：M7.4", "timeSensitive", None, "default"),
        (7.6, "全球强震提醒：M7.6", "critical", "4", "high"),
        (8.1, "全球特大地震提醒：M8.1", "critical", "10", "urgent"),
    ],
)
def test_far_global_bark_payload_uses_magnitude_tiers_without_local_countdown(magnitude, title, level, volume, priority):
    path, query = bark_payload(event(source="emsc_global", magnitude=magnitude), 9000, 1, "轻微震感", 0)
    decoded = unquote(path)

    assert title in decoded
    assert "秒后到达" not in decoded
    assert "横波已到达" not in decoded
    assert query["level"] == level
    if volume:
        assert query["volume"] == volume
    else:
        assert "volume" not in query
    assert "call" not in query
    assert ntfy_priority(event(source="emsc_global", magnitude=magnitude), decision()) == priority


def test_far_global_ntfy_and_webhook_text_does_not_use_local_countdown():
    title, body = push_text(event(source="emsc_global", magnitude=7.6, epicenter="COLOMBIA"), decision(distance_km=15000))

    assert title == "全球强震提醒：M7.6"
    assert "COLOMBIA" in body
    assert "远场提醒" in body
    assert "秒后到达" not in body
    assert "横波已到达" not in body


@pytest.mark.anyio
async def test_far_global_webhook_payload_uses_global_text(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        text = "ok"

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.push.httpx.AsyncClient", FakeClient)

    result = await send_webhook(
        "https://example.invalid/eew",
        event(source="emsc_global", magnitude=8.1, epicenter="GLOBAL TEST"),
        decision(distance_km=12000),
    )

    assert result["ok"] is True
    assert captured["json"]["title"] == "全球特大地震提醒：M8.1"
    assert "远场提醒" in captured["json"]["body"]
    assert "秒后到达" not in captured["json"]["body"]


def test_bark_payload_links_to_device_specific_detail(monkeypatch):
    monkeypatch.setattr("app.push.settings", SimpleNamespace(public_base_url="https://h-eew.example"))

    _, query = bark_payload(event(event_id="evt/1"), 80, 3, "明显有感", 12, device_id=7)

    assert query["url"] == "https://h-eew.example/event/evt%2F1?device_id=7"


def test_drill_bark_payload_is_marked():
    path, _ = bark_payload(event(source="drill", test=True), 80, 3, "明显有感", 12)
    decoded = unquote(path)

    assert decoded.startswith("演练：")
    assert "【演练】" in decoded
