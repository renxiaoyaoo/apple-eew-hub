from app.wolfx import normalize_wolfx_message


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
