from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DeviceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    push_type: Literal["bark", "ntfy", "webhook"] = "bark"
    bark_key: str = ""
    push_url: str = ""
    default_city: str = ""
    latitude: float
    longitude: float
    min_magnitude: float = 4.5
    max_distance_km: float = 500
    min_intensity: float = 2
    enabled: bool = True
    receive_tests: bool = True


class Device(DeviceIn):
    id: int
    created_at: str
    updated_at: str


class DevicePatch(BaseModel):
    name: str | None = None
    push_type: Literal["bark", "ntfy", "webhook"] | None = None
    bark_key: str | None = None
    push_url: str | None = None
    default_city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    min_magnitude: float | None = None
    max_distance_km: float | None = None
    min_intensity: float | None = None
    enabled: bool | None = None
    receive_tests: bool | None = None


class LocationUpdate(BaseModel):
    default_city: str = ""
    latitude: float
    longitude: float


class EarthquakeEvent(BaseModel):
    event_id: str
    source: str = "manual"
    report_num: int = 1
    is_final: bool = False
    is_cancel: bool = False
    epicenter: str
    latitude: float
    longitude: float
    magnitude: float
    depth_km: float = 10
    origin_time: str = Field(default_factory=utc_now)
    raw: dict[str, Any] = Field(default_factory=dict)
    test: bool = False


class SimulationIn(BaseModel):
    source: str = "drill"
    epicenter: str = "四川宜宾市珙县"
    latitude: float = 28.43
    longitude: float = 104.71
    magnitude: float = 5.9
    depth_km: float = 10
    target_city: str = "成都双流"
    target_latitude: float = 30.58
    target_longitude: float = 103.92
    countdown_seconds: int = 18
    intensity: float = 3
    distance_km: float = 199


class TestPushIn(BaseModel):
    device_id: int


class SystemConfigPatch(BaseModel):
    wolfx_enabled: bool | None = None
    wolfx_ws_url: str | None = None
    wolfx_ws_base: str | None = None
    wolfx_sources: list[str] | None = None
    global_enabled: bool | None = None
    global_source_url: str | None = None
    global_min_magnitude: float | None = None
    alert_red_intensity: float | None = None
    alert_yellow_intensity: float | None = None
    bark_red_level: str | None = None
    bark_red_volume: str | None = None
    bark_red_sound: str | None = None
    bark_red_repeat: int | None = None
    bark_red_repeat_gap_seconds: float | None = None
    bark_yellow_level: str | None = None
    bark_yellow_volume: str | None = None
    bark_yellow_sound: str | None = None
    bark_yellow_repeat: int | None = None
    bark_yellow_repeat_gap_seconds: float | None = None
    bark_blue_level: str | None = None
    bark_blue_volume: str | None = None
    bark_blue_sound: str | None = None
    bark_blue_repeat: int | None = None
    bark_blue_repeat_gap_seconds: float | None = None


class Decision(BaseModel):
    device_id: int
    device_name: str
    distance_km: float
    arrival_seconds: int
    intensity: float
    intensity_text: str
    status: Literal["pending", "arrived", "passed"]
    should_push: bool
    reason: str
