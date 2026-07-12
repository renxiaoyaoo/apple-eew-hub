from app.geo import estimate_intensity, haversine_km, intensity_text, parse_dt, wave_status


def test_haversine_chengdu_yibin_distance_is_reasonable():
    distance = haversine_km(28.43, 104.71, 30.58, 103.92)
    assert 240 <= distance <= 260


def test_intensity_text_mapping():
    assert intensity_text(1) == "轻微震感"
    assert intensity_text(3) == "明显有感"
    assert intensity_text(4) == "强烈有感"
    assert intensity_text(5) == "强烈震感，注意避险"


def test_wave_status_mapping():
    assert wave_status(18) == "pending"
    assert wave_status(0) == "arrived"
    assert wave_status(-130) == "passed"


def test_naive_wolfx_time_is_treated_as_china_time():
    assert parse_dt("2026-07-13 01:03:28").utcoffset().total_seconds() == 8 * 3600


def test_xiaojin_to_chengdu_m49_is_felt_intensity():
    intensity = estimate_intensity(4.9, 181, 10)
    assert intensity >= 2
