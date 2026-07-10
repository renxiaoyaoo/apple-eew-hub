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

ALLOWED_BARK_LEVELS = {"critical", "timeSensitive", "active", "passive"}


def get_system_config() -> dict[str, Any]:
    return {**default_system_config(), **_system_config}


def set_system_config(config: dict[str, Any]) -> dict[str, Any]:
    global _system_config
    merged = {**default_system_config(), **config}
    merged["wolfx_sources"] = [str(item).strip() for item in merged.get("wolfx_sources", []) if str(item).strip()]
    merged["global_min_magnitude"] = float(merged.get("global_min_magnitude") or 7.5)
    merged["alert_red_intensity"] = float(merged.get("alert_red_intensity") or 4)
    merged["alert_yellow_intensity"] = float(merged.get("alert_yellow_intensity") or 2)
    if not 5 <= merged["global_min_magnitude"] <= 10:
        raise ValueError("global_min_magnitude must be between 5 and 10")
    if not 0 <= merged["alert_yellow_intensity"] <= 7:
        raise ValueError("alert_yellow_intensity must be between 0 and 7")
    if not 0 <= merged["alert_red_intensity"] <= 7:
        raise ValueError("alert_red_intensity must be between 0 and 7")
    if merged["alert_yellow_intensity"] > merged["alert_red_intensity"]:
        raise ValueError("yellow intensity cannot be higher than red intensity")
    if merged.get("wolfx_ws_base") and not str(merged["wolfx_ws_base"]).startswith(("ws://", "wss://")):
        raise ValueError("wolfx_ws_base must start with ws:// or wss://")
    for url in str(merged.get("wolfx_ws_url") or "").split(","):
        url = url.strip()
        if url and not url.startswith(("ws://", "wss://")):
            raise ValueError("wolfx_ws_url values must start with ws:// or wss://")
    if merged.get("global_source_url") and not str(merged["global_source_url"]).startswith(("ws://", "wss://")):
        raise ValueError("global_source_url must start with ws:// or wss://")
    for key in ("bark_red_level", "bark_yellow_level", "bark_blue_level"):
        if merged.get(key) not in ALLOWED_BARK_LEVELS:
            raise ValueError(f"{key} is not a supported Bark level")
    for key in ("bark_red_repeat", "bark_yellow_repeat", "bark_blue_repeat"):
        merged[key] = max(1, int(float(merged.get(key) or 1)))
        if merged[key] > 5:
            raise ValueError(f"{key} must be 5 or less")
    for key in ("bark_red_repeat_gap_seconds", "bark_yellow_repeat_gap_seconds", "bark_blue_repeat_gap_seconds"):
        merged[key] = max(0.0, float(merged.get(key) or 0))
        if merged[key] > 5:
            raise ValueError(f"{key} must be 5 seconds or less")
    _system_config = merged
    return get_system_config()
