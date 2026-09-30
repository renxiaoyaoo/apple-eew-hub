from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import get_system_config
from .core import process_event
from .db import Database
from .geo import haversine_km, parse_dt
from .models import EarthquakeEvent, utc_now
from .simple_ws import SimpleWebSocket

LOGGER = logging.getLogger(__name__)
REPORT_SUFFIX_RE = re.compile(r"^(\d{12}\.\d+)_\d+$")
WOLFX_TIME_FORMATS = (
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
)


def _pick(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


def canonical_wolfx_event_id(event_id: str) -> str:
    match = REPORT_SUFFIX_RE.match(event_id)
    return match.group(1) if match else event_id


def normalize_wolfx_time(value: Any, source: str = "") -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    text = str(value).strip()
    if text.endswith("Z"):
        return text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone(timedelta(hours=9 if source == "jma_eew" else 8)))
        return parsed.isoformat()
    except ValueError:
        pass
    for fmt in WOLFX_TIME_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
            offset = timezone(timedelta(hours=9 if source == "jma_eew" else 8))
            return parsed.replace(tzinfo=offset).isoformat()
        except ValueError:
            continue
    return text


def wolfx_endpoints(config: dict[str, Any] | None = None) -> list[tuple[str, str]]:
    config = config or get_system_config()
    if config["wolfx_ws_url"]:
        urls = [item.strip() for item in str(config["wolfx_ws_url"]).split(",") if item.strip()]
        return [(url.rstrip("/").split("/")[-1] or "wolfx", url) for url in urls]
    return [
        (source, f"{str(config['wolfx_ws_base']).rstrip('/')}/{source}")
        for source in config["wolfx_sources"]
    ]


def normalize_wolfx_message(data: dict[str, Any], source_hint: str = "") -> EarthquakeEvent | None:
    nested = data.get("Data") or data.get("data") or data
    source = source_hint or str(_pick(data, "type", "source", "Source", default="wolfx"))
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
    origin_time = normalize_wolfx_time(
        _pick(nested, "OriginTime", "originTime", "ReportTime", "reportTime", "Time", "time"),
        source,
    )
    if not event_id:
        event_id = f"{source}:{origin_time}:{latitude}:{longitude}:{magnitude}"
    else:
        event_id = canonical_wolfx_event_id(event_id)
    return EarthquakeEvent(
        event_id=event_id,
        source=source,
        report_num=int(_pick(nested, "ReportNum", "reportNum", "Serial", "serial", default=1) or 1),
        is_final=source.endswith("_eqlist") or bool(_pick(nested, "Final", "isFinal", "is_final", default=False)),
        is_cancel=bool(_pick(nested, "Cancel", "isCancel", "is_cancel", default=False)),
        epicenter=str(epicenter),
        latitude=float(latitude),
        longitude=float(longitude),
        magnitude=float(magnitude),
        depth_km=abs(float(_pick(nested, "Depth", "depth", "DepthKm", "depth_km", default=10) or 10)),
        origin_time=str(origin_time),
        raw=data,
        test=False,
    )


def reconcile_catalog_event(db: Database, event: EarthquakeEvent) -> EarthquakeEvent:
    if event.source != "cenc_eqlist":
        return event
    for row in db.query(
        """
        SELECT event_id, latitude, longitude, magnitude, origin_time, report_num
        FROM events WHERE test = 0 ORDER BY updated_at DESC LIMIT 100
        """
    ):
        try:
            time_gap = abs((parse_dt(event.origin_time) - parse_dt(row["origin_time"])).total_seconds())
        except (TypeError, ValueError):
            continue
        if time_gap > 120 or abs(event.magnitude - row["magnitude"]) > 1:
            continue
        if haversine_km(event.latitude, event.longitude, row["latitude"], row["longitude"]) > 30:
            continue
        return event.model_copy(update={"event_id": row["event_id"], "report_num": row["report_num"] + 1})
    return event


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
        return wolfx_endpoints()

    def _set_source_state(self, source: str, state: dict) -> None:
        current = self.db.get_state("listener_sources", {})
        current[source] = {**current.get(source, {}), **state}
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
        retry_delay = 5
        while self.running:
            try:
                self._set_source_state(source, {"connected": False, "message": "connecting", "url": url})
                async with SimpleWebSocket(url) as ws:
                    retry_delay = 5
                    self._set_source_state(source, {"connected": True, "message": "connected", "url": url})
                    async for message in ws:
                        try:
                            data = json.loads(message)
                            self._set_source_state(
                                source,
                                {"connected": True, "message": "connected", "url": url, "last_message_at": utc_now()},
                            )
                            event = normalize_wolfx_message(data, source_hint=source)
                            if event:
                                event = reconcile_catalog_event(self.db, event)
                                reason = "中国地震台网正式速报" if source == "cenc_eqlist" else "国内预警源"
                                self.db.record_observed_event(event, True, reason)
                                await process_event(self.db, event)
                        except (json.JSONDecodeError, TypeError, ValueError) as exc:
                            LOGGER.warning("Ignored invalid Wolfx message for %s: %s", source, exc)
                            continue
                if self.running:
                    self._set_source_state(source, {"connected": False, "message": "connection closed", "url": url})
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.warning("Wolfx listener error for %s: %s", source, exc)
                self._set_source_state(source, {"connected": False, "message": str(exc), "url": url})
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)
