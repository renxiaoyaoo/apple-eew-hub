from app.db import Database
from app.global_quakes import global_record_reason, normalize_emsc_message, should_record_global_event


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


def test_normalize_emsc_message_uses_positive_depth_from_properties():
    event = normalize_emsc_message(
        {
            "data": {
                "geometry": {"coordinates": [125.1655, 5.3269, -67.9]},
                "properties": {
                    "unid": "mindanao",
                    "mag": 6.2,
                    "depth": 67.9,
                    "flynn_region": "MINDANAO, PHILIPPINES",
                },
            }
        }
    )

    assert event is not None
    assert event.depth_km == 67.9


def test_normalize_emsc_message_rejects_below_global_threshold():
    event = normalize_emsc_message(
        {
            "data": {
                "geometry": {"coordinates": [140.0, 35.0, 10]},
                "properties": {"unid": "nearby", "mag": 6.9, "flynn_region": "Japan"},
            }
        }
    )
    assert event is not None
    assert event.magnitude == 6.9


def insert_device(db: Database, **kwargs):
    base = {
        "name": "iPhone",
        "push_type": "bark",
        "bark_key": "fake-key",
        "push_url": "",
        "default_city": "成都",
        "latitude": 30.5728,
        "longitude": 104.0668,
        "min_magnitude": 1,
        "max_distance_km": 5000,
        "min_intensity": 2,
        "enabled": 1,
        "receive_tests": 1,
    }
    base.update(kwargs)
    db.execute(
        """
        INSERT INTO devices
        (name, push_type, bark_key, push_url, default_city, latitude, longitude,
         min_magnitude, max_distance_km, min_intensity, enabled, receive_tests, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            base["name"],
            base["push_type"],
            base["bark_key"],
            base["push_url"],
            base["default_city"],
            base["latitude"],
            base["longitude"],
            base["min_magnitude"],
            base["max_distance_km"],
            base["min_intensity"],
            base["enabled"],
            base["receive_tests"],
            "now",
            "now",
        ),
    )


def test_should_not_record_far_low_intensity_global_small_quake(tmp_path):
    db = Database(tmp_path / "eew.sqlite3")
    db.init()
    insert_device(db)
    event = normalize_emsc_message(
        {
            "data": {
                "geometry": {"coordinates": [117.92, -9.19, 10]},
                "properties": {"unid": "sumbawa", "mag": 2.6, "flynn_region": "SUMBAWA REGION, INDONESIA"},
            }
        }
    )

    assert event is not None
    assert should_record_global_event(db, event) is False


def test_should_not_record_far_low_intensity_mindanao_event(tmp_path):
    db = Database(tmp_path / "eew.sqlite3")
    db.init()
    insert_device(db)
    event = normalize_emsc_message(
        {
            "data": {
                "geometry": {"coordinates": [125.1655, 5.3269, -67.9]},
                "properties": {"unid": "mindanao", "mag": 6.2, "depth": 67.9, "flynn_region": "MINDANAO, PHILIPPINES"},
            }
        }
    )

    assert event is not None
    assert should_record_global_event(db, event) is False


def test_far_low_intensity_event_can_be_kept_in_observed_catalog(tmp_path):
    db = Database(tmp_path / "eew.sqlite3")
    db.init()
    insert_device(db)
    event = normalize_emsc_message(
        {
            "data": {
                "geometry": {"coordinates": [125.1655, 5.3269, -67.9]},
                "properties": {"unid": "mindanao", "mag": 6.2, "depth": 67.9, "flynn_region": "MINDANAO, PHILIPPINES"},
            }
        }
    )

    assert event is not None
    should_record = should_record_global_event(db, event)
    db.record_observed_event(event, should_record, global_record_reason(db, event))
    observed = db.one("SELECT event_id, recorded, reason, depth_km FROM observed_events WHERE event_id = ?", (event.event_id,))
    promoted = db.one("SELECT event_id FROM events WHERE event_id = ?", (event.event_id,))

    assert should_record is False
    assert observed is not None
    assert observed["recorded"] == 0
    assert observed["reason"] == "仅监听到"
    assert observed["depth_km"] == 67.9
    assert promoted is None


def test_should_record_global_major_quake_even_when_far(tmp_path):
    db = Database(tmp_path / "eew.sqlite3")
    db.init()
    insert_device(db)
    event = normalize_emsc_message(
        {
            "data": {
                "geometry": {"coordinates": [-72.73, -35.91, 35]},
                "properties": {"unid": "major", "mag": 8.1, "flynn_region": "Chile"},
            }
        }
    )

    assert event is not None
    assert should_record_global_event(db, event) is True
