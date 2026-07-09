from app.global_quakes import normalize_emsc_message


def test_normalize_emsc_message_accepts_standing_order_payload():
    event = normalize_emsc_message(
        {
            "action": "create",
            "data": {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [142.37, 38.32, 24]},
                "properties": {
                    "unid": "20260709_000001",
                    "time": "2026-07-09T03:21:00.000Z",
                    "mag": 7.8,
                    "flynn_region": "Near East Coast of Honshu, Japan",
                },
            },
        }
    )
    assert event is not None
    assert event.event_id == "emsc:20260709_000001"
    assert event.source == "emsc_global"
    assert event.epicenter == "Near East Coast of Honshu, Japan"
    assert event.latitude == 38.32
    assert event.longitude == 142.37
    assert event.depth_km == 24
    assert event.magnitude == 7.8


def test_normalize_emsc_message_rejects_below_global_threshold():
    assert normalize_emsc_message({"data": {"properties": {"mag": 6.9}}}) is None
