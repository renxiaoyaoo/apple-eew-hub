from app.db import Database
from app.wolfx import normalize_wolfx_message, reconcile_catalog_event


def test_normalize_wolfx_message_accepts_common_fields():
    event = normalize_wolfx_message(
        {
            "type": "cenc_eew",
            "Data": {
                "EventID": "abc",
                "ReportNum": 2,
                "HypoCenter": "四川宜宾市珙县",
                "Latitude": 28.43,
                "Longitude": 104.71,
                "Magnitude": 5.9,
                "Depth": 10,
                "OriginTime": "2026-07-08T09:58:00+00:00",
            },
        }
    )
    assert event is not None
    assert event.event_id == "abc"
    assert event.source == "cenc_eew"
    assert event.report_num == 2
    assert event.epicenter == "四川宜宾市珙县"
    assert event.magnitude == 5.9


def test_normalize_wolfx_message_rejects_incomplete_payload():
    assert normalize_wolfx_message({"type": "heartbeat"}) is None


def test_normalize_wolfx_message_strips_report_suffix_from_event_id():
    event = normalize_wolfx_message(
        {
            "type": "sc_eew",
            "Data": {
                "EventID": "202607130103.0001_2",
                "ReportNum": 2,
                "HypoCenter": "四川阿坝州小金县",
                "Latitude": 31.0,
                "Longitude": 102.4,
                "Magnitude": 4.3,
                "Depth": 10,
                "OriginTime": "2026-07-13 01:03:28",
            },
        }
    )
    assert event is not None
    assert event.event_id == "202607130103.0001"


def test_normalize_wolfx_message_accepts_jma_slash_time():
    event = normalize_wolfx_message(
        {
            "type": "jma_eew",
            "Data": {
                "EventID": "20260820005028",
                "HypoCenter": "浦河沖",
                "Latitude": 42.0,
                "Longitude": 142.6,
                "Magnitude": 3.9,
                "Depth": 50,
                "OriginTime": "2026/08/20 00:50:21",
            },
        }
    )

    assert event is not None
    assert event.source == "jma_eew"
    assert event.origin_time == "2026-08-20T00:50:21"


def test_normalize_cenc_catalog_message_uses_endpoint_source():
    event = normalize_wolfx_message(
        {
            "type": "reviewed",
            "EventID": "AU.20260926050127.000",
            "time": "2026-09-26 05:01:27",
            "location": "四川宜宾市高县",
            "magnitude": "4.5",
            "depth": "5",
            "latitude": "28.52",
            "longitude": "104.67",
        },
        source_hint="cenc_eqlist",
    )

    assert event is not None
    assert event.source == "cenc_eqlist"
    assert event.is_final is True
    assert event.epicenter == "四川宜宾市高县"


def test_catalog_report_reuses_matching_early_warning_event(tmp_path):
    db = Database(tmp_path / "eew.sqlite3")
    db.init()
    db.execute(
        """
        INSERT INTO events
        (event_id, source, report_num, is_final, is_cancel, epicenter, latitude, longitude,
         magnitude, depth_km, origin_time, raw_json, test, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "eew-existing", "sc_eew", 2, 0, 0, "四川宜宾市高县", 28.52, 104.67,
            4.6, 5, "2026-09-26 05:01:20", "{}", 0, "now", "now",
        ),
    )
    event = normalize_wolfx_message(
        {
            "type": "reviewed", "EventID": "catalog-new", "time": "2026-09-26 05:01:27",
            "location": "四川宜宾市高县", "magnitude": 4.5, "depth": 5,
            "latitude": 28.52, "longitude": 104.67,
        },
        source_hint="cenc_eqlist",
    )

    reconciled = reconcile_catalog_event(db, event)

    assert reconciled.event_id == "eew-existing"
    assert reconciled.report_num == 3
