from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import default_system_config, get_system_config, set_system_config, settings
from .core import normalize_device, process_event, public_device
from .db import Database
from .global_quakes import GlobalQuakeListener
from .models import DeviceIn, DevicePatch, EarthquakeEvent, LocationUpdate, SimulationIn, SystemConfigPatch, TestPushIn, utc_now
from .push import send_bark
from .wolfx import WolfxListener

app = FastAPI(title=settings.app_name)
db = Database(settings.db_path)
listener = WolfxListener(db)
global_listener = GlobalQuakeListener(db)

PUBLIC_PATHS = {
    "/",
    "/api/health",
    "/api/status",
    "/api/latest-alert",
}


@app.middleware("http")
async def security_and_auth(request: Request, call_next):
    path = request.url.path
    if settings.auth_token and path.startswith("/api/") and path not in PUBLIC_PATHS:
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        if token != settings.auth_token:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


@app.on_event("startup")
async def startup() -> None:
    db.init()
    set_system_config(db.get_state("system_config", default_system_config()))
    listener.start()
    global_listener.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    await listener.stop()
    await global_listener.stop()


PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"

app.mount("/assets", StaticFiles(directory=PUBLIC_DIR / "assets"), name="assets")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "public" / "index.html")


@app.get("/event/{event_id}")
async def event_page(event_id: str) -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "public" / "index.html")


@app.get("/api/status")
async def status() -> dict:
    config = get_system_config()
    listener_state = db.get_state("listener", {"connected": False, "message": "not started", "sources": {}})
    global_state = db.get_state("global_listener", {"connected": False, "message": "not started", "sources": {}})
    merged_sources = {**(listener_state.get("sources") or {}), **(global_state.get("sources") or {})}
    listener_state = {
        **listener_state,
        "connected": bool(listener_state.get("connected") or global_state.get("connected")),
        "sources": merged_sources,
    }
    return {
        "app": settings.app_name,
        "time": utc_now(),
        "listener": listener_state,
        "sources": (*config["wolfx_sources"], "emsc_global"),
        "wolfx_configured": bool(config["wolfx_ws_url"] or config["wolfx_ws_base"]),
        "wolfx_ws_base": config["wolfx_ws_base"],
        "global_quake_min_magnitude": config["global_min_magnitude"],
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
        "device_count": db.one("SELECT COUNT(*) AS c FROM devices")["c"],
    }


@app.get("/api/health")
async def health() -> dict:
    db.one("SELECT 1 AS ok")
    return {"ok": True, "time": utc_now()}


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
    await listener.stop()
    await global_listener.stop()
    listener.start()
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
    return public_device(db.one("SELECT * FROM devices WHERE id = ?", (device_id,)))


@app.delete("/api/devices/{device_id}")
async def delete_device(device_id: int) -> dict:
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
    result = await send_bark(device["bark_key"], event, 0, 2, "轻微震感", 18, repeat_override=1)
    db.execute(
        """
        INSERT INTO pushes
        (event_id, device_id, channel, ok, status_code, latency_ms, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (event.event_id, device["id"], "bark", int(result["ok"]), result["status_code"], result["latency_ms"], result["message"], utc_now()),
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
        SELECT devices.name AS device_name, d.distance_km, d.arrival_seconds,
               d.intensity, d.intensity_text, d.status, d.should_push
        FROM decisions d
        JOIN devices ON devices.id = d.device_id
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
        "decisions": [{**item, "should_push": bool(item["should_push"])} for item in decisions],
    }


@app.get("/api/logs")
async def logs() -> dict:
    return {
        "events": db.query(
            """
            SELECT event_id, source, report_num, is_final, is_cancel, epicenter,
                   latitude, longitude, magnitude, depth_km, origin_time, test,
                   created_at, updated_at
            FROM events
            ORDER BY updated_at DESC
            LIMIT 100
            """
        ),
        "decisions": db.query("SELECT * FROM decisions ORDER BY id DESC LIMIT 200"),
        "pushes": db.query(
            """
            SELECT p.id, p.event_id, p.device_id, devices.name AS device_name,
                   events.epicenter, events.magnitude, events.test,
                   p.channel, p.ok, p.status_code, p.latency_ms, p.message, p.created_at
            FROM pushes p
            LEFT JOIN devices ON devices.id = p.device_id
            LEFT JOIN events ON events.event_id = p.event_id
            ORDER BY p.id DESC
            LIMIT 200
            """
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


@app.post("/api/backup")
async def backup() -> dict:
    backup_dir = settings.data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"eew-hub-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.sqlite3"
    shutil.copy2(settings.db_path, target)
    return {"ok": True, "path": str(target)}


@app.get("/api/config/export")
async def export_config() -> dict:
    devices = [normalize_device(row) for row in db.query("SELECT * FROM devices ORDER BY id")]
    return {
        "version": 1,
        "exported_at": utc_now(),
        "devices": [
            {
                key: value
                for key, value in device.items()
                if key not in {"id", "created_at", "updated_at"}
            }
            for device in devices
        ],
    }


@app.post("/api/config/import")
async def import_config(payload: dict) -> dict:
    devices = payload.get("devices")
    if not isinstance(devices, list):
        raise HTTPException(400, "devices must be a list")
    backup_result = await backup()
    db.execute("DELETE FROM devices")
    imported = 0
    for item in devices:
        device = DeviceIn(**item)
        await create_device(device)
        imported += 1
    return {"ok": True, "imported": imported, "backup": backup_result["path"]}
