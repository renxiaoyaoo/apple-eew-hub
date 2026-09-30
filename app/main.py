from __future__ import annotations

import json
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import (
    default_system_config,
    get_system_config,
    set_system_config,
    settings,
)
from .core import (
    cancel_all_arrival_pushes,
    cancel_device_arrival_pushes,
    normalize_device,
    process_event,
    public_device,
    restore_pending_pushes,
    restore_scheduled_arrival_pushes,
)
from .db import Database
from .global_quakes import GlobalQuakeListener
from .maintenance import MaintenanceManager
from .models import (
    Decision,
    DeviceIn,
    DevicePatch,
    EarthquakeEvent,
    LocationUpdate,
    SimulationIn,
    SystemConfigPatch,
    TestPushIn,
    utc_now,
)
from .push import dispatch_push
from .source_health import SourceHealthMonitor
from .wolfx import WolfxListener, wolfx_endpoints

os.umask(0o077)

db = Database(settings.db_path)
listener = WolfxListener(db)
global_listener = GlobalQuakeListener(db)
source_health_monitor = SourceHealthMonitor(db)
maintenance_manager = MaintenanceManager(db)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    config = set_system_config(db.get_state("system_config", default_system_config()))
    db.set_state("system_config", config)
    restore_pending_pushes(db)
    restore_scheduled_arrival_pushes(db)
    listener.start()
    global_listener.start()
    source_health_monitor.start()
    maintenance_manager.start()
    try:
        yield
    finally:
        cancel_all_arrival_pushes()
        await maintenance_manager.stop()
        await source_health_monitor.stop()
        await listener.stop()
        await global_listener.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

PUBLIC_PATHS = {
    "/api/health",
}
MAX_MAP_TILE_BYTES = 2 * 1024 * 1024


def enabled_source_names(config: dict) -> list[str]:
    names = [source for source, _ in wolfx_endpoints(config)] if config["wolfx_enabled"] else []
    if config["global_enabled"]:
        names.append("emsc_global")
    return list(dict.fromkeys(names))


@app.middleware("http")
async def security_and_auth(request: Request, call_next):
    path = request.url.path
    if settings.auth_token and path.startswith("/api/") and path not in PUBLIC_PATHS:
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        if not secrets.compare_digest(token, settings.auth_token):
            response = JSONResponse({"detail": "unauthorized"}, status_code=401)
        else:
            response = await call_next(request)
    else:
        response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=()"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; "
        f"form-action 'self'; frame-ancestors {settings.frame_ancestors}"
    )
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"

app.mount("/assets", StaticFiles(directory=PUBLIC_DIR / "assets"), name="assets")
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")


@app.get("/map-tiles/{z}/{x}/{y}.png")
async def map_tile(z: int, x: int, y: int) -> Response:
    if not 0 <= z <= 19 or not 0 <= x < 2**z or not 0 <= y < 2**z:
        raise HTTPException(404, "tile not found")
    target = settings.data_dir / "map-cache" / str(z) / str(x) / f"{y}.png"
    if target.exists():
        return FileResponse(target, media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})
    url = settings.map_tile_url.format(z=z, x=x, y=y)
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True, proxy=settings.map_http_proxy or None) as client:
            async with client.stream(
                "GET",
                url,
                headers={"User-Agent": "Apple-EEW-Hub/0.2 (+https://github.com/renxiaoyaoo/apple-eew-hub)"},
            ) as upstream:
                upstream.raise_for_status()
                content_type = upstream.headers.get("content-type", "").lower()
                if not content_type.startswith("image/"):
                    raise HTTPException(502, "map tile response is not an image")
                content = bytearray()
                async for chunk in upstream.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_MAP_TILE_BYTES:
                        raise HTTPException(502, "map tile response is too large")
    except httpx.HTTPError as exc:
        raise HTTPException(502, "map tile unavailable") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f".{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return Response(bytes(content), media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "public" / "index.html")


@app.get("/event/{event_id}")
async def event_page(event_id: str) -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "public" / "index.html")


@app.get("/history")
async def history_page() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "public" / "index.html")


@app.get("/catalog")
async def catalog_page() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "public" / "index.html")


@app.get("/pushes")
async def pushes_page() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "public" / "index.html")


@app.get("/rules")
async def rules_page() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "public" / "index.html")


@app.get("/settings")
async def settings_page() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "public" / "index.html")


@app.get("/api/status")
async def status() -> dict:
    config = get_system_config()
    listener_state = db.get_state("listener", {"connected": False, "message": "not started", "sources": {}})
    global_state = db.get_state("global_listener", {"connected": False, "message": "not started", "sources": {}})
    expected_sources = enabled_source_names(config)
    all_sources = {**(listener_state.get("sources") or {}), **(global_state.get("sources") or {})}
    merged_sources = {
        name: all_sources.get(name, {"connected": False, "message": "not started"})
        for name in expected_sources
    }
    connected_count = sum(bool(item.get("connected")) for item in merged_sources.values())
    source_count = len(merged_sources)
    listener_state = {
        **listener_state,
        "connected": bool(source_count and connected_count == source_count),
        "degraded": bool(connected_count and connected_count < source_count),
        "connected_count": connected_count,
        "source_count": source_count,
        "sources": merged_sources,
    }
    return {
        "app": settings.app_name,
        "time": utc_now(),
        "listener": listener_state,
        "sources": expected_sources,
        "wolfx_configured": bool(config["wolfx_ws_url"] or config["wolfx_ws_base"]),
        "wolfx_ws_base": config["wolfx_ws_base"],
        "global_quake_min_magnitude": config["global_min_magnitude"],
        "global_far_alert_enabled": config["global_far_alert_enabled"],
        "retention": {
            "max_events": settings.max_events,
            "max_decisions": settings.max_decisions,
            "max_pushes": settings.max_pushes,
        },
        "alert_levels": {
            "red_intensity": config["alert_red_intensity"],
            "yellow_intensity": config["alert_yellow_intensity"],
            "bark": {
                "red": {"level": config["bark_red_level"], "volume": config["bark_red_volume"], "sound": config["bark_red_sound"], "repeat": config["bark_red_repeat"]},
                "yellow": {"level": config["bark_yellow_level"], "volume": config["bark_yellow_volume"], "sound": config["bark_yellow_sound"], "repeat": config["bark_yellow_repeat"]},
                "blue": {"level": config["bark_blue_level"], "volume": config["bark_blue_volume"], "sound": config["bark_blue_sound"], "repeat": config["bark_blue_repeat"]},
            },
        },
        "auth_enabled": bool(settings.auth_token),
        "source_health_alert": db.get_state("source_health_alert", {}),
        "device_count": db.one("SELECT COUNT(*) AS c FROM devices")["c"],
    }


@app.get("/api/health")
async def health() -> dict:
    db.one("SELECT 1 AS ok")
    config = get_system_config()
    wolfx_state = db.get_state("listener", {"connected": False, "sources": {}})
    global_state = db.get_state("global_listener", {"connected": False, "sources": {}})
    expected_sources = enabled_source_names(config)
    all_sources = {**(wolfx_state.get("sources") or {}), **(global_state.get("sources") or {})}
    sources = {
        name: all_sources.get(name, {"connected": False, "message": "not started"})
        for name in expected_sources
    }
    return {
        "ok": True,
        "ready": bool(sources) and all(item.get("connected") for item in sources.values()),
        "connected_count": sum(bool(item.get("connected")) for item in sources.values()),
        "source_count": len(sources),
        "time": utc_now(),
        "sources": {
            name: {
                "connected": bool(item.get("connected")),
                "last_message_at": item.get("last_message_at"),
            }
            for name, item in sources.items()
        },
    }


@app.get("/api/system-config")
async def system_config() -> dict:
    return get_system_config()


@app.patch("/api/system-config")
async def update_system_config(payload: SystemConfigPatch) -> dict:
    current = get_system_config()
    updates = {key: value for key, value in payload.model_dump().items() if value is not None}
    try:
        config = set_system_config({**current, **updates})
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.set_state("system_config", config)
    wolfx_keys = {"wolfx_enabled", "wolfx_ws_url", "wolfx_ws_base", "wolfx_sources"}
    global_keys = {"global_enabled", "global_source_url"}
    if wolfx_keys.intersection(updates):
        await listener.stop()
        listener.start()
    if global_keys.intersection(updates):
        await global_listener.stop()
        global_listener.start()
    return config


@app.get("/api/devices")
async def list_devices() -> list[dict]:
    return [public_device(row) for row in db.query("SELECT * FROM devices ORDER BY id")]


@app.post("/api/devices")
async def create_device(payload: DeviceIn) -> dict:
    now = utc_now()
    cur = db.execute(
        """
        INSERT INTO devices
        (name, push_type, bark_key, push_url, default_city, latitude, longitude, min_magnitude,
         max_distance_km, min_intensity, enabled, receive_tests, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.name,
            payload.push_type,
            payload.bark_key,
            payload.push_url,
            payload.default_city,
            payload.latitude,
            payload.longitude,
            payload.min_magnitude,
            payload.max_distance_km,
            payload.min_intensity,
            int(payload.enabled),
            int(payload.receive_tests),
            now,
            now,
        ),
    )
    return public_device(db.one("SELECT * FROM devices WHERE id = ?", (cur.lastrowid,)))


@app.patch("/api/devices/{device_id}")
async def patch_device(device_id: int, payload: DevicePatch) -> dict:
    current = db.one("SELECT * FROM devices WHERE id = ?", (device_id,))
    if not current:
        raise HTTPException(404, "device not found")
    values = payload.model_dump(exclude_unset=True)
    if not values:
        return public_device(current)
    assignments = []
    params = []
    for key, value in values.items():
        assignments.append(f"{key} = ?")
        params.append(int(value) if isinstance(value, bool) else value)
    assignments.append("updated_at = ?")
    params.append(utc_now())
    params.append(device_id)
    db.execute(f"UPDATE devices SET {', '.join(assignments)} WHERE id = ?", params)
    arrival_sensitive_fields = {"latitude", "longitude", "min_magnitude", "max_distance_km", "min_intensity", "enabled", "receive_tests"}
    if arrival_sensitive_fields.intersection(values):
        cancel_device_arrival_pushes(device_id)
    return public_device(db.one("SELECT * FROM devices WHERE id = ?", (device_id,)))


@app.delete("/api/devices/{device_id}")
async def delete_device(device_id: int) -> dict:
    cancel_device_arrival_pushes(device_id)
    db.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    return {"ok": True}


@app.post("/api/devices/{device_id}/location")
async def update_location(device_id: int, payload: LocationUpdate) -> dict:
    updated = await patch_device(
        device_id,
        DevicePatch(default_city=payload.default_city, latitude=payload.latitude, longitude=payload.longitude),
    )
    return {"ok": True, "device": updated}


@app.post("/api/test-push")
async def test_push(payload: TestPushIn) -> dict:
    device = db.one("SELECT * FROM devices WHERE id = ?", (payload.device_id,))
    if not device:
        raise HTTPException(404, "device not found")
    event = EarthquakeEvent(
        event_id=f"test-push-{uuid4().hex}",
        source="test",
        epicenter="测试预警",
        latitude=device["latitude"],
        longitude=device["longitude"],
        magnitude=4.5,
        depth_km=10,
        test=True,
    )
    now = utc_now()
    db.execute(
        """
        INSERT INTO events
        (event_id, source, report_num, is_final, is_cancel, epicenter, latitude, longitude,
         magnitude, depth_km, origin_time, raw_json, test, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.event_id,
            event.source,
            event.report_num,
            int(event.is_final),
            int(event.is_cancel),
            event.epicenter,
            event.latitude,
            event.longitude,
            event.magnitude,
            event.depth_km,
            event.origin_time,
            json.dumps(event.raw, ensure_ascii=False),
            int(event.test),
            now,
            now,
        ),
    )
    decision = Decision(
        device_id=device["id"],
        device_name=device["name"],
        distance_km=0,
        arrival_seconds=18,
        intensity=2,
        intensity_text="轻微震感",
        status="pending",
        should_push=True,
        reason="test push",
        device_city=device["default_city"],
        device_latitude=device["latitude"],
        device_longitude=device["longitude"],
    )
    result = await dispatch_push(device, event, decision, repeat_override=1)
    db.execute(
        """
        INSERT INTO decisions
        (event_id, device_id, distance_km, arrival_seconds, intensity, intensity_text,
         status, should_push, reason, pushed, device_city, device_latitude,
         device_longitude, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.event_id, device["id"], 0, 18, 2, "轻微震感", "pending", 1,
            "test push", int(result["ok"]), device["default_city"], device["latitude"],
            device["longitude"], now,
        ),
    )
    db.execute(
        """
        INSERT INTO pushes
        (event_id, device_id, push_phase, channel, ok, status_code, latency_ms, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (event.event_id, device["id"], "test", result["channel"], int(result["ok"]), result["status_code"], result["latency_ms"], result["message"], utc_now()),
    )
    return result


@app.post("/api/simulate")
async def simulate(payload: SimulationIn) -> dict:
    event = EarthquakeEvent(
        event_id=f"drill-{uuid4().hex}",
        source=payload.source,
        epicenter=payload.epicenter,
        latitude=payload.latitude,
        longitude=payload.longitude,
        magnitude=payload.magnitude,
        depth_km=payload.depth_km,
        test=True,
        raw=payload.model_dump(),
    )
    decisions = await process_event(
        db,
        event,
        override={
            "distance_km": payload.distance_km,
            "countdown_seconds": payload.countdown_seconds,
            "intensity": payload.intensity,
        },
    )
    return {"event": event, "decisions": decisions}


@app.get("/api/latest-alert")
async def latest_alert() -> dict:
    return db.get_state("latest_alert", {})


@app.get("/api/alerts/{event_id}")
async def alert_by_id(event_id: str) -> dict:
    event = db.one("SELECT * FROM events WHERE event_id = ?", (event_id,))
    if not event:
        raise HTTPException(404, "event not found")
    decisions = db.query(
        """
        SELECT d.device_id, devices.name AS device_name, d.distance_km, d.arrival_seconds,
               d.intensity, d.intensity_text, d.status, d.should_push, d.reason, d.created_at,
               d.device_city, d.device_latitude, d.device_longitude
        FROM decisions d
        LEFT JOIN devices ON devices.id = d.device_id
        WHERE d.event_id = ?
        ORDER BY d.id DESC
        """,
        (event_id,),
    )
    return {
        "event": {
            "event_id": event["event_id"],
            "source": event["source"],
            "epicenter": event["epicenter"],
            "latitude": event["latitude"],
            "longitude": event["longitude"],
            "magnitude": event["magnitude"],
            "depth_km": event["depth_km"],
            "origin_time": event["origin_time"],
            "test": bool(event["test"]),
        },
        "decisions": [
            {**item, "device_name": item["device_name"] or "已删除的 Apple 设备", "should_push": bool(item["should_push"])}
            for item in decisions
        ],
    }


@app.get("/api/logs")
async def logs(
    events_limit: int = Query(100, ge=0, le=settings.max_events),
    decisions_limit: int = Query(200, ge=0, le=settings.max_decisions),
    pushes_limit: int = Query(200, ge=0, le=settings.max_pushes),
    observed_limit: int = Query(300, ge=0, le=settings.max_events),
) -> dict:
    return {
        "counts": {
            "events": db.one("SELECT COUNT(*) AS c FROM events")["c"],
            "decisions": db.one("SELECT COUNT(*) AS c FROM decisions")["c"],
            "pushes": db.one("SELECT COUNT(*) AS c FROM pushes")["c"],
            "triggered_events": db.one(
                """
                SELECT COUNT(DISTINCT d.event_id) AS c FROM decisions d
                WHERE d.should_push = 1 AND d.id = (
                  SELECT MAX(latest.id) FROM decisions latest
                  WHERE latest.event_id = d.event_id AND latest.device_id = d.device_id
                )
                """
            )["c"],
            "notified_events": db.one("SELECT COUNT(DISTINCT event_id) AS c FROM pushes WHERE ok = 1")["c"],
            "observed_events": db.one("SELECT COUNT(*) AS c FROM observed_events")["c"],
            "observed_recorded": db.one("SELECT COUNT(*) AS c FROM observed_events WHERE recorded = 1")["c"],
        },
        "events": db.query(
            """
            SELECT event_id, source, report_num, is_final, is_cancel, epicenter,
                   latitude, longitude, magnitude, depth_km, origin_time, test,
                   created_at, updated_at
            FROM events
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (events_limit,),
        ),
        "decisions": db.query(
            """
            SELECT d.* FROM decisions d
            WHERE d.id = (
              SELECT MAX(latest.id) FROM decisions latest
              WHERE latest.event_id = d.event_id AND latest.device_id = d.device_id
            )
            ORDER BY d.id DESC LIMIT ?
            """,
            (decisions_limit,),
        ),
        "pushes": db.query(
            """
            SELECT p.id, p.event_id, p.device_id, devices.name AS device_name,
                   events.epicenter, events.magnitude, events.test,
                   p.push_phase, p.channel, p.ok, p.status_code, p.latency_ms, p.message, p.created_at
            FROM pushes p
            LEFT JOIN devices ON devices.id = p.device_id
            LEFT JOIN events ON events.event_id = p.event_id
            ORDER BY p.id DESC
            LIMIT ?
            """,
            (pushes_limit,),
        ),
        "observed_events": db.query(
            """
            SELECT event_id, source, epicenter, latitude, longitude, magnitude, depth_km,
                   origin_time, recorded, reason, created_at, updated_at
            FROM observed_events
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (observed_limit,),
        ),
    }


@app.delete("/api/logs")
async def clear_logs() -> dict:
    backup_result = await backup()
    db.execute("DELETE FROM pushes")
    db.execute("DELETE FROM decisions")
    db.execute("DELETE FROM events")
    db.execute("DELETE FROM app_state WHERE key = ?", ("latest_alert",))
    return {"ok": True, "backup": backup_result["path"]}


@app.delete("/api/logs/pushes")
async def clear_push_logs() -> dict:
    backup_result = await backup()
    db.execute("DELETE FROM pushes")
    return {"ok": True, "backup": backup_result["path"]}


@app.delete("/api/logs/events")
async def clear_event_logs() -> dict:
    backup_result = await backup()
    db.execute("DELETE FROM pushes")
    db.execute("DELETE FROM decisions")
    db.execute("DELETE FROM events")
    db.execute("DELETE FROM app_state WHERE key = ?", ("latest_alert",))
    return {"ok": True, "backup": backup_result["path"]}


@app.post("/api/backup")
async def backup() -> dict:
    backup_dir = settings.data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"eew-hub-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.sqlite3"
    db.backup(target)
    return {"ok": True, "path": str(target)}


@app.get("/api/config/export")
async def export_config() -> dict:
    devices = [normalize_device(row) for row in db.query("SELECT * FROM devices ORDER BY id")]
    return {
        "version": 1,
        "exported_at": utc_now(),
        "secrets_included": False,
        "note": "推送凭据不会写入配置导出；完整恢复请使用 SQLite 备份。",
        "devices": [
            {
                key: value
                for key, value in device.items()
                if key not in {"id", "created_at", "updated_at", "bark_key", "push_url"}
            }
            for device in devices
        ],
    }


@app.post("/api/config/import")
async def import_config(payload: dict) -> dict:
    devices = payload.get("devices")
    if not isinstance(devices, list):
        raise HTTPException(400, "devices must be a list")
    validated = [DeviceIn(**item) for item in devices]
    names = [device.name for device in validated]
    if len(names) != len(set(names)):
        raise HTTPException(400, "device names must be unique")
    backup_result = await backup()
    cancel_all_arrival_pushes()
    now = utc_now()
    with db.transaction() as conn:
        for device in validated:
            existing = conn.execute("SELECT * FROM devices WHERE name = ? ORDER BY id LIMIT 1", (device.name,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE devices SET push_type = ?, bark_key = ?, push_url = ?, default_city = ?,
                      latitude = ?, longitude = ?, min_magnitude = ?, max_distance_km = ?,
                      min_intensity = ?, enabled = ?, receive_tests = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        device.push_type, device.bark_key or existing["bark_key"],
                        device.push_url or existing["push_url"], device.default_city,
                        device.latitude, device.longitude, device.min_magnitude,
                        device.max_distance_km, device.min_intensity, int(device.enabled),
                        int(device.receive_tests), now, existing["id"],
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO devices
                    (name, push_type, bark_key, push_url, default_city, latitude, longitude, min_magnitude,
                     max_distance_km, min_intensity, enabled, receive_tests, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        device.name, device.push_type, device.bark_key, device.push_url, device.default_city,
                        device.latitude, device.longitude, device.min_magnitude, device.max_distance_km,
                        device.min_intensity, int(device.enabled), int(device.receive_tests), now, now,
                    ),
                )
    return {"ok": True, "imported": len(validated), "mode": "merge", "backup": backup_result["path"]}
