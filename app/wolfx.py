from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import websockets

from .config import get_system_config, settings
from .core import process_event
from .db import Database
from .models import EarthquakeEvent

LOGGER = logging.getLogger(__name__)


def _pick(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


def normalize_wolfx_message(data: dict[str, Any], source_hint: str = "") -> EarthquakeEvent | None:
    nested = data.get("Data") or data.get("data") or data
    source = str(_pick(data, "type", "source", "Source", default=source_hint or "wolfx"))
    event_id = str(_pick(nested, "EventID", "eventId", "id", "ID", default=""))
    latitude = _pick(nested, "Latitude", "latitude", "Lat", "lat")
    longitude = _pick(nested, "Longitude", "longitude", "Lon", "lon", "Lng", "lng")
    magnitude = _pick(nested, "Magnitude", "magnitude", "Magunitude", "magunitude", "Mag", "mag")
    epicenter = _pick(
        nested,
        "HypoCenter",
        "Hypocenter",
        "hypocenter",
        "Epicenter",
        "epicenter",
        "location",
        "Location",
        default="",
    )
    if latitude is None or longitude is None or magnitude is None or not epicenter:
        return None
    origin_time = _pick(nested, "OriginTime", "originTime", "ReportTime", "reportTime", "Time", "time")
    if not origin_time:
        origin_time = datetime.now(timezone.utc).isoformat()
    if not event_id:
        event_id = f"{source}:{origin_time}:{latitude}:{longitude}:{magnitude}"
    return EarthquakeEvent(
        event_id=event_id,
        source=source,
        report_num=int(_pick(nested, "ReportNum", "reportNum", "Serial", "serial", default=1) or 1),
        is_final=bool(_pick(nested, "Final", "isFinal", "is_final", default=False)),
        is_cancel=bool(_pick(nested, "Cancel", "isCancel", "is_cancel", default=False)),
        epicenter=str(epicenter),
        latitude=float(latitude),
        longitude=float(longitude),
        magnitude=float(magnitude),
        depth_km=float(_pick(nested, "Depth", "depth", "DepthKm", "depth_km", default=10) or 10),
        origin_time=str(origin_time),
        raw=data,
        test=False,
    )


class WolfxListener:
    def __init__(self, db: Database):
        self.db = db
        self.tasks: list[asyncio.Task] = []
        self.running = False

    def start(self) -> None:
        config = get_system_config()
        if self.tasks or not config["wolfx_enabled"]:
            return
        self.running = True
        self.db.set_state("listener_sources", {})
        self.db.set_state("listener", {"connected": False, "message": "starting", "sources": {}})
        for source, url in self._endpoints():
            self.tasks.append(asyncio.create_task(self._run_endpoint(source, url)))

    async def stop(self) -> None:
        self.running = False
        tasks = self.tasks
        for task in self.tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks = []

    def _endpoints(self) -> list[tuple[str, str]]:
        config = get_system_config()
        if config["wolfx_ws_url"]:
            urls = [item.strip() for item in str(config["wolfx_ws_url"]).split(",") if item.strip()]
            return [(url.rstrip("/").split("/")[-1] or "wolfx", url) for url in urls]
        endpoints = []
        for source in config["wolfx_sources"]:
            endpoints.append((source, f"{str(config['wolfx_ws_base']).rstrip('/')}/{source}"))
        return endpoints

    def _set_source_state(self, source: str, state: dict) -> None:
        current = self.db.get_state("listener_sources", {})
        current[source] = state
        connected = any(item.get("connected") for item in current.values())
        self.db.set_state("listener_sources", current)
        self.db.set_state(
            "listener",
            {
                "connected": connected,
                "message": "connected" if connected else "all sources disconnected",
                "sources": current,
            },
        )

    async def _run_endpoint(self, source: str, url: str) -> None:
        while self.running:
            try:
                self._set_source_state(source, {"connected": False, "message": "connecting", "url": url})
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=20,
                    compression=None,
                    user_agent_header="raspi-eew-hub/0.1",
                ) as ws:
                    self._set_source_state(source, {"connected": True, "message": "connected", "url": url})
                    async for message in ws:
                        try:
                            data = json.loads(message)
                        except json.JSONDecodeError:
                            continue
                        event = normalize_wolfx_message(data, source_hint=source)
                        if event:
                            await process_event(self.db, event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.warning("Wolfx listener error for %s: %s", source, exc)
                self._set_source_state(source, {"connected": False, "message": str(exc), "url": url})
                await asyncio.sleep(5)
