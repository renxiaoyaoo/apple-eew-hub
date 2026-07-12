from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

CHINA_TZ = timezone(timedelta(hours=8))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def parse_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CHINA_TZ)
    return dt


def estimate_arrival_seconds(origin_time: str, distance_km: float, wave_speed_km_s: float = 3.5) -> int:
    elapsed = (datetime.now(timezone.utc) - parse_dt(origin_time)).total_seconds()
    return int(round(distance_km / wave_speed_km_s - elapsed))


def estimate_intensity(magnitude: float, distance_km: float, depth_km: float) -> float:
    hypocentral = max(1.0, math.sqrt(distance_km**2 + depth_km**2))
    value = 1.7 * magnitude - 2.4 * math.log10(hypocentral) - 0.8
    return max(0.0, round(value, 1))


def intensity_text(intensity: float) -> str:
    if intensity >= 5:
        return "强烈震感，注意避险"
    if intensity >= 4:
        return "强烈有感"
    if intensity >= 3:
        return "明显有感"
    return "轻微震感"


def wave_status(arrival_seconds: int) -> str:
    if arrival_seconds > 0:
        return "pending"
    if arrival_seconds > -120:
        return "arrived"
    return "passed"
