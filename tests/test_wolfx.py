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
