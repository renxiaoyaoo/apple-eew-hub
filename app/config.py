from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Settings:
    app_name: str = "Raspberry Pi EEW Hub"
    data_dir: Path = Path(os.getenv("EEW_DATA_DIR", "/data"))
    wolfx_ws_url: str = os.getenv("WOLFX_WS_URL", "")
    wolfx_ws_base: str = os.getenv("WOLFX_WS_BASE", "wss://ws-api.wolfx.jp")
    wolfx_sources: tuple[str, ...] = tuple(
        s.strip()
        for s in os.getenv(
            "WOLFX_SOURCES", "all_eew"
        ).split(",")
        if s.strip()
    )
    bark_base_url: str = os.getenv("BARK_BASE_URL", "http://bark-server:18762")
    auth_token: str = os.getenv("EEW_AUTH_TOKEN", "")
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "")
    listener_enabled: bool = os.getenv("WOLFX_LISTENER_ENABLED", "1") == "1"
    global_listener_enabled: bool = os.getenv("GLOBAL_QUAKE_LISTENER_ENABLED", "1") == "1"
    global_quake_source_url: str = os.getenv("GLOBAL_QUAKE_SOURCE_URL", "wss://www.seismicportal.eu/standing_order/websocket")
    global_quake_min_magnitude: float = float(os.getenv("GLOBAL_QUAKE_MIN_MAGNITUDE", "7.5"))
    alert_red_intensity: float = float(os.getenv("ALERT_RED_INTENSITY", "4"))
    alert_yellow_intensity: float = float(os.getenv("ALERT_YELLOW_INTENSITY", "2"))
    bark_red_level: str = os.getenv("BARK_RED_LEVEL", "critical")
    bark_red_volume: str = os.getenv("BARK_RED_VOLUME", "8")
    bark_red_sound: str = os.getenv("BARK_RED_SOUND", "alarm")
    bark_red_repeat: int = int(os.getenv("BARK_RED_REPEAT", "3"))
    bark_red_repeat_gap_seconds: float = float(os.getenv("BARK_RED_REPEAT_GAP_SECONDS", "1.2"))
    bark_yellow_level: str = os.getenv("BARK_YELLOW_LEVEL", "critical")
    bark_yellow_volume: str = os.getenv("BARK_YELLOW_VOLUME", "4")
    bark_yellow_sound: str = os.getenv("BARK_YELLOW_SOUND", "alarm")
    bark_yellow_repeat: int = int(os.getenv("BARK_YELLOW_REPEAT", "2"))
    bark_yellow_repeat_gap_seconds: float = float(os.getenv("BARK_YELLOW_REPEAT_GAP_SECONDS", "1"))
    bark_blue_level: str = os.getenv("BARK_BLUE_LEVEL", "timeSensitive")
    bark_blue_volume: str = os.getenv("BARK_BLUE_VOLUME", "")
    bark_blue_sound: str = os.getenv("BARK_BLUE_SOUND", "alarm")
    bark_blue_repeat: int = int(os.getenv("BARK_BLUE_REPEAT", "1"))
    bark_blue_repeat_gap_seconds: float = float(os.getenv("BARK_BLUE_REPEAT_GAP_SECONDS", "0"))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "eew-hub.sqlite3"


settings = Settings()


def default_system_config() -> dict[str, Any]:
    return {
        "wolfx_enabled": settings.listener_enabled,
        "wolfx_ws_url": settings.wolfx_ws_url,
        "wolfx_ws_base": settings.wolfx_ws_base,
        "wolfx_sources": list(settings.wolfx_sources),
        "global_enabled": settings.global_listener_enabled,
        "global_source_url": settings.global_quake_source_url,
        "global_min_magnitude": settings.global_quake_min_magnitude,
        "alert_red_intensity": settings.alert_red_intensity,
        "alert_yellow_intensity": settings.alert_yellow_intensity,
        "bark_red_level": settings.bark_red_level,
        "bark_red_volume": settings.bark_red_volume,
        "bark_red_sound": settings.bark_red_sound,
        "bark_red_repeat": settings.bark_red_repeat,
        "bark_red_repeat_gap_seconds": settings.bark_red_repeat_gap_seconds,
        "bark_yellow_level": settings.bark_yellow_level,
        "bark_yellow_volume": settings.bark_yellow_volume,
        "bark_yellow_sound": settings.bark_yellow_sound,
        "bark_yellow_repeat": settings.bark_yellow_repeat,
        "bark_yellow_repeat_gap_seconds": settings.bark_yellow_repeat_gap_seconds,
        "bark_blue_level": settings.bark_blue_level,
        "bark_blue_volume": settings.bark_blue_volume,
        "bark_blue_sound": settings.bark_blue_sound,
        "bark_blue_repeat": settings.bark_blue_repeat,
        "bark_blue_repeat_gap_seconds": settings.bark_blue_repeat_gap_seconds,
    }


_system_config: dict[str, Any] = default_system_config()


def get_system_config() -> dict[str, Any]:
    return {**default_system_config(), **_system_config}


def set_system_config(config: dict[str, Any]) -> dict[str, Any]:
    global _system_config
    merged = {**default_system_config(), **config}
    merged["wolfx_sources"] = [str(item).strip() for item in merged.get("wolfx_sources", []) if str(item).strip()]
    merged["global_min_magnitude"] = float(merged.get("global_min_magnitude") or 7.5)
    merged["alert_red_intensity"] = float(merged.get("alert_red_intensity") or 4)
    merged["alert_yellow_intensity"] = float(merged.get("alert_yellow_intensity") or 2)
    for key in ("bark_red_repeat", "bark_yellow_repeat", "bark_blue_repeat"):
        merged[key] = max(1, int(float(merged.get(key) or 1)))
    for key in ("bark_red_repeat_gap_seconds", "bark_yellow_repeat_gap_seconds", "bark_blue_repeat_gap_seconds"):
        merged[key] = max(0.0, float(merged.get(key) or 0))
    _system_config = merged
    return get_system_config()
