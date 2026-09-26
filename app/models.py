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
    default_city: str = Field(default="", max_length=80)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    min_magnitude: float = Field(default=4.5, ge=0, le=10)
    max_distance_km: float = Field(default=500, ge=1, le=20000)
    min_intensity: float = Field(default=2, ge=0, le=7)
    enabled: bool = True
    receive_tests: bool = True


class Device(DeviceIn):
    id: int
    created_at: str
    updated_at: str


class DevicePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    push_type: Literal["bark", "ntfy", "webhook"] | None = None
    bark_key: str | None = None
    push_url: str | None = None
    default_city: str | None = Field(default=None, max_length=80)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    min_magnitude: float | None = Field(default=None, ge=0, le=10)
    max_distance_km: float | None = Field(default=None, ge=1, le=20000)
    min_intensity: float | None = Field(default=None, ge=0, le=7)
    enabled: bool | None = None
    receive_tests: bool | None = None


class LocationUpdate(BaseModel):
    default_city: str = Field(default="", max_length=80)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class EarthquakeEvent(BaseModel):
    event_id: str
    source: str = "manual"
    report_num: int = 1
    is_final: bool = False
    is_cancel: bool = False
    epicenter: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    magnitude: float = Field(ge=0, le=10)
    depth_km: float = Field(default=10, ge=0, le=1000)
    origin_time: str = Field(default_factory=utc_now)
    raw: dict[str, Any] = Field(default_factory=dict)
    test: bool = False


class SimulationIn(BaseModel):
    source: str = "drill"
    epicenter: str = "四川宜宾市珙县"
    latitude: float = Field(default=28.43, ge=-90, le=90)
    longitude: float = Field(default=104.71, ge=-180, le=180)
    magnitude: float = Field(default=5.9, ge=0, le=10)
    depth_km: float = Field(default=10, ge=0, le=1000)
    target_city: str = "成都双流"
    target_latitude: float = Field(default=30.58, ge=-90, le=90)
    target_longitude: float = Field(default=103.92, ge=-180, le=180)
    countdown_seconds: int = Field(default=18, ge=0, le=3600)
    intensity: float = Field(default=3, ge=0, le=7)
    distance_km: float = Field(default=199, ge=0, le=20000)


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
    global_far_alert_enabled: bool | None = None
    source_health_alert_enabled: bool | None = None
    source_health_alert_after_minutes: int | None = None
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
