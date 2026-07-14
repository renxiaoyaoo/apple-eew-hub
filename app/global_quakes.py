from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import websockets

from .config import get_system_config
from .core import decide_for_device, normalize_device, process_event
from .db import Database
from .models import EarthquakeEvent

LOGGER = logging.getLogger(__name__)


def _pick(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


def _origin_time(value: Any) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    return str(value)


def normalize_emsc_message(message: dict[str, Any]) -> EarthquakeEvent | None:
    payload = message.get("data") or message
    props = payload.get("properties") or {}
    geometry = payload.get("geometry") or {}
    coords = geometry.get("coordinates") or []

    magnitude = _pick(props, "mag", "magnitude")
    if magnitude is None:
        return None

    latitude = _pick(props, "lat", "latitude")
    longitude = _pick(props, "lon", "longitude")
    depth_km = _pick(props, "depth", "depth_km")
    if len(coords) >= 2:
        longitude = coords[0]
        latitude = coords[1]
        if depth_km is None and len(coords) >= 3 and coords[2] not in (None, ""):
            depth_km = coords[2]
    depth_km = abs(float(depth_km if depth_km not in (None, "") else 10))
    if latitude is None or longitude is None:
        return None

    unid = _pick(props, "unid", "eventid", "id", default=payload.get("id"))
    origin_time = _origin_time(_pick(props, "time", "origin_time"))
    if not unid:
        unid = f"{origin_time}:{latitude}:{longitude}:{magnitude}"

    action = str(message.get("action") or props.get("action") or "").lower()
    epicenter = str(_pick(props, "flynn_region", "place", "region", default="全球地震"))
    return EarthquakeEvent(
        event_id=f"emsc:{unid}",
        source="emsc_global",
        report_num=1,
        is_final=action in {"update", "confirmed"},
        is_cancel=action in {"delete", "cancel", "cancelled"},
        epicenter=epicenter,
        latitude=float(latitude),
        longitude=float(longitude),
        magnitude=float(magnitude),
        depth_km=depth_km,
        origin_time=origin_time,
        raw=message,
        test=False,
    )


def should_record_global_event(db: Database, event: EarthquakeEvent) -> bool:
    if event.magnitude >= get_system_config()["global_min_magnitude"]:
        return True
    devices = [normalize_device(row) for row in db.query("SELECT * FROM devices WHERE enabled = 1 ORDER BY id")]
    for device in devices:
        decision = decide_for_device(event, device)
        record_intensity = max(2, device["min_intensity"])
        if decision.should_push:
            return True
        if decision.distance_km <= device["max_distance_km"] and event.magnitude >= device["min_magnitude"] and decision.intensity >= record_intensity:
            return True
    return False


class GlobalQuakeListener:
    def __init__(self, db: Database):
        self.db = db
        self.task: asyncio.Task | None = None
        self.running = False

    def start(self) -> None:
        config = get_system_config()
        if self.task or not config["global_enabled"]:
            return
        self.running = True
        self._set_state(False, "starting")
        self.task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.task = None

    def _set_state(self, connected: bool, message: str) -> None:
        self.db.set_state(
            "global_listener",
            {
                "connected": connected,
                "message": message,
                "sources": {
                    "emsc_global": {
                        "connected": connected,
                        "message": message,
                        "url": get_system_config()["global_source_url"],
                    }
                },
            },
        )

    async def _run(self) -> None:
        while self.running:
            try:
                await self._connect()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.warning("Global quake websocket error: %s", exc)
                self._set_state(False, str(exc))
                await asyncio.sleep(5)

    async def _connect(self) -> None:
        self._set_state(False, "connecting")
        async with websockets.connect(
            get_system_config()["global_source_url"],
            ping_interval=15,
            ping_timeout=20,
            compression=None,
            user_agent_header="raspi-eew-hub/0.1",
        ) as ws:
            self._set_state(True, "connected")
            async for raw_message in ws:
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    continue
                event = normalize_emsc_message(message)
                if event and should_record_global_event(self.db, event):
                    await process_event(self.db, event)
