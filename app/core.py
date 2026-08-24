from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from .db import Database
from .geo import estimate_arrival_seconds, estimate_intensity, haversine_km, intensity_text, wave_status
from .models import Decision, EarthquakeEvent, utc_now
from .push import dispatch_push
from .config import get_system_config, settings

LOGGER = logging.getLogger(__name__)
MAX_SCHEDULED_ARRIVAL_SECONDS = 1800
GLOBAL_LOCAL_MAX_DISTANCE_KM = 1000
FAR_FIELD_SOURCES = {"emsc_global", "jma_eew"}
BACKGROUND_TASKS: set[asyncio.Task] = set()
ARRIVAL_TASKS: dict[tuple[str, int], asyncio.Task] = {}


def is_global_local_distance(distance_km: float, device: dict) -> bool:
    return distance_km <= min(float(device["max_distance_km"]), GLOBAL_LOCAL_MAX_DISTANCE_KM)


def is_far_field_event(event: EarthquakeEvent, distance_km: float, device: dict) -> bool:
    return event.source in FAR_FIELD_SOURCES and not is_global_local_distance(distance_km, device)


def is_jma_forecast_only(event: EarthquakeEvent) -> bool:
    if event.source != "jma_eew":
        return False
    return event.raw.get("isWarn") is False


async def _dispatch_and_update_push(db: Database, push_id: int, device: dict, event: EarthquakeEvent, decision: Decision) -> None:
    try:
        result = await dispatch_push(device, event, decision)
    except Exception as exc:
        db.execute(
            """
            UPDATE pushes
            SET ok = 0, latency_ms = 0, message = ?
            WHERE id = ?
            """,
            (f"dispatch failed: {type(exc).__name__}", push_id),
        )
        raise
    db.execute(
        """
        UPDATE pushes
        SET channel = ?, ok = ?, status_code = ?, latency_ms = ?, message = ?
        WHERE id = ?
        """,
        (
            result["channel"],
            int(result["ok"]),
            result["status_code"],
            result["latency_ms"],
            result["message"],
            push_id,
        ),
    )


def _track_task(task: asyncio.Task) -> asyncio.Task:
    BACKGROUND_TASKS.add(task)

    def _done(done: asyncio.Task) -> None:
        BACKGROUND_TASKS.discard(done)
        try:
            done.result()
        except asyncio.CancelledError:
            return
        except Exception:
            LOGGER.exception("Background push task failed")

    task.add_done_callback(_done)
    return task


def _create_background_task(coro) -> asyncio.Task:
    return _track_task(asyncio.create_task(coro))


def _insert_pending_push(db: Database, event_id: str, device: dict, phase: str) -> int:
    cur = db.execute(
        """
        INSERT INTO pushes
        (event_id, device_id, push_phase, channel, ok, status_code, latency_ms, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            device["id"],
            phase,
            device["push_type"],
            0,
            None,
            0,
            "pending",
            utc_now(),
        ),
    )
    return int(cur.lastrowid)


def _insert_pending_push_conn(conn, event_id: str, device: dict, phase: str) -> int:
    cur = conn.execute(
        """
        INSERT INTO pushes
        (event_id, device_id, push_phase, channel, ok, status_code, latency_ms, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            device["id"],
            phase,
            device["push_type"],
            0,
            None,
            0,
            "pending",
            utc_now(),
        ),
    )
    return int(cur.lastrowid)


def _has_push(db: Database, event_id: str, device_id: int, phase: str) -> bool:
    return bool(
        db.one(
            "SELECT id FROM pushes WHERE event_id = ? AND device_id = ? AND push_phase = ? LIMIT 1",
            (event_id, device_id, phase),
        )
    )


def _has_push_conn(conn, event_id: str, device_id: int, phase: str) -> bool:
    return bool(
        conn.execute(
            "SELECT id FROM pushes WHERE event_id = ? AND device_id = ? AND push_phase = ? LIMIT 1",
            (event_id, device_id, phase),
        ).fetchone()
    )


def _should_schedule_arrival(event: EarthquakeEvent, decision: Decision) -> bool:
    if event.source in FAR_FIELD_SOURCES and decision.intensity <= 1:
        return False
    return 1 <= decision.arrival_seconds <= MAX_SCHEDULED_ARRIVAL_SECONDS


async def _dispatch_arrival_push_later(db: Database, device: dict, event: EarthquakeEvent, decision: Decision) -> None:
    key = (event.event_id, int(device["id"]))
    try:
        await asyncio.sleep(decision.arrival_seconds)
        if _has_push(db, event.event_id, device["id"], "arrival"):
            return
        arrival_decision = decision.model_copy(update={"arrival_seconds": 0, "status": "arrived"})
        push_id = _insert_pending_push(db, event.event_id, device, "arrival")
        await _dispatch_and_update_push(db, push_id, device, event, arrival_decision)
    finally:
        if ARRIVAL_TASKS.get(key) is asyncio.current_task():
            ARRIVAL_TASKS.pop(key, None)


def _schedule_arrival_push(db: Database, device: dict, event: EarthquakeEvent, decision: Decision) -> bool:
    key = (event.event_id, int(device["id"]))
    existing = ARRIVAL_TASKS.get(key)
    if existing and not existing.done():
        existing.cancel()
    ARRIVAL_TASKS[key] = _create_background_task(_dispatch_arrival_push_later(db, device, event, decision))
    return True


def _elapsed_seconds(value: str) -> int:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))


def normalize_device(row: dict) -> dict:
    result = dict(row)
    result["enabled"] = bool(result["enabled"])
    result["receive_tests"] = bool(result["receive_tests"])
    return result


def public_device(row: dict) -> dict:
    result = normalize_device(row)
    result["bark_key_configured"] = bool(result.get("bark_key"))
    result["push_url_configured"] = bool(result.get("push_url"))
    result.pop("bark_key", None)
    result.pop("push_url", None)
    return result


def decide_for_device(event: EarthquakeEvent, device: dict, override: dict | None = None) -> Decision:
    config = get_system_config()
    global_major_magnitude = float(config["global_min_magnitude"])
    if override:
        distance = float(override.get("distance_km", 0))
        arrival = int(override.get("countdown_seconds", 0))
        intensity = float(override.get("intensity", 0))
    else:
        distance = haversine_km(event.latitude, event.longitude, device["latitude"], device["longitude"])
        arrival = estimate_arrival_seconds(event.origin_time, distance)
        intensity = estimate_intensity(event.magnitude, distance, event.depth_km)
        if is_far_field_event(event, distance, device):
            intensity = min(intensity, 1)
        elif distance > device["max_distance_km"] and event.magnitude >= global_major_magnitude:
            intensity = min(intensity, 1)
    text = intensity_text(intensity)
    status = wave_status(arrival)
    if event.is_cancel:
        should_push, reason = False, "cancel report"
    elif event.test and not device["receive_tests"]:
        should_push, reason = False, "device disabled test alerts"
    elif not device["enabled"]:
        should_push, reason = False, "device disabled"
    elif event.test:
        should_push, reason = True, "test drill"
    elif is_jma_forecast_only(event):
        should_push, reason = False, "jma forecast only"
    elif is_far_field_event(event, distance, device) and event.magnitude >= global_major_magnitude and not config["global_far_alert_enabled"]:
        should_push, reason = False, "global far alerts disabled"
    elif event.magnitude >= global_major_magnitude:
        should_push, reason = True, "global major earthquake"
    elif event.source in FAR_FIELD_SOURCES:
        if is_global_local_distance(distance, device) and event.magnitude >= device["min_magnitude"] and intensity >= max(2, device["min_intensity"]):
            should_push, reason = True, "global local threshold matched"
        else:
            should_push, reason = False, "below threshold"
    elif distance <= device["max_distance_km"] and event.magnitude >= device["min_magnitude"] and intensity >= device["min_intensity"]:
        should_push, reason = True, "threshold matched"
    elif intensity >= 2:
        should_push, reason = True, "felt intensity"
    else:
        should_push, reason = False, "below threshold"
    return Decision(
        device_id=device["id"],
        device_name=device["name"],
        distance_km=round(distance, 1),
        arrival_seconds=arrival,
        intensity=intensity,
        intensity_text=text,
        status=status,
        should_push=should_push,
        reason=reason,
    )


async def process_event(db: Database, event: EarthquakeEvent, override: dict | None = None) -> list[Decision]:
    now = utc_now()
    current = db.one("SELECT report_num, is_final, is_cancel FROM events WHERE event_id = ?", (event.event_id,))
    if current and event.report_num < current["report_num"] and not event.is_cancel:
        stored = db.query(
            """
            SELECT d.device_id, devices.name AS device_name, d.distance_km, d.arrival_seconds,
                   d.intensity, d.intensity_text, d.status, d.should_push, d.reason
            FROM decisions d
            JOIN devices ON devices.id = d.device_id
            WHERE d.event_id = ?
            ORDER BY d.id DESC
            """,
            (event.event_id,),
        )
        return [Decision(**{**row, "should_push": bool(row["should_push"])}) for row in stored]
    devices = [normalize_device(row) for row in db.query("SELECT * FROM devices ORDER BY id")]
    decisions: list[Decision] = []
    dispatches = []
    arrivals = []
    with db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO events
            (event_id, source, report_num, is_final, is_cancel, epicenter, latitude, longitude,
             magnitude, depth_km, origin_time, raw_json, test, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
              source=excluded.source, report_num=excluded.report_num, is_final=excluded.is_final,
              is_cancel=excluded.is_cancel, epicenter=excluded.epicenter, latitude=excluded.latitude,
              longitude=excluded.longitude, magnitude=excluded.magnitude, depth_km=excluded.depth_km,
              origin_time=excluded.origin_time, raw_json=excluded.raw_json, test=excluded.test,
              updated_at=excluded.updated_at
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
        for device in devices:
            decision = decide_for_device(event, device, override)
            decisions.append(decision)
            already_pushed = _has_push_conn(conn, event.event_id, device["id"], "initial")
            conn.execute(
                """
                INSERT INTO decisions
                (event_id, device_id, distance_km, arrival_seconds, intensity, intensity_text,
                 status, should_push, reason, pushed, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    device["id"],
                    decision.distance_km,
                    decision.arrival_seconds,
                    decision.intensity,
                    decision.intensity_text,
                    decision.status,
                    int(decision.should_push),
                    decision.reason,
                    int(already_pushed),
                    utc_now(),
                ),
            )
            if decision.should_push:
                if not already_pushed:
                    push_id = _insert_pending_push_conn(conn, event.event_id, device, "initial")
                    dispatches.append((push_id, device, decision))
                if _should_schedule_arrival(event, decision) and not _has_push_conn(conn, event.event_id, device["id"], "arrival"):
                    arrivals.append((device, decision))
        latest_alert = {"event": event.model_dump(), "decisions": [d.model_dump() for d in decisions]}
        conn.execute(
            """
            INSERT INTO app_state (key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            ("latest_alert", json.dumps(latest_alert, ensure_ascii=False), utc_now()),
        )
        conn.execute(
            "DELETE FROM decisions WHERE id NOT IN (SELECT id FROM decisions ORDER BY id DESC LIMIT ?)",
            (settings.max_decisions,),
        )
        conn.execute(
            "DELETE FROM pushes WHERE id NOT IN (SELECT id FROM pushes ORDER BY id DESC LIMIT ?)",
            (settings.max_pushes,),
        )
        conn.execute(
            "DELETE FROM events WHERE event_id NOT IN (SELECT event_id FROM events ORDER BY updated_at DESC LIMIT ?)",
            (settings.max_events,),
        )
        conn.execute(
            "DELETE FROM observed_events WHERE event_id NOT IN (SELECT event_id FROM observed_events ORDER BY updated_at DESC LIMIT ?)",
            (settings.max_events,),
        )
    for push_id, device, decision in dispatches:
        _create_background_task(_dispatch_and_update_push(db, push_id, device, event, decision))
    for device, decision in arrivals:
        _schedule_arrival_push(db, device, event, decision)
    return decisions


def restore_scheduled_arrival_pushes(db: Database) -> int:
    rows = db.query(
        """
        SELECT d.event_id, d.device_id, d.distance_km, d.arrival_seconds, d.intensity,
               d.intensity_text, d.status, d.should_push, d.reason, d.created_at,
               devices.id AS dev_id, devices.name AS device_name, devices.push_type,
               devices.bark_key, devices.push_url, devices.default_city,
               devices.latitude AS dev_latitude, devices.longitude AS dev_longitude,
               devices.min_magnitude, devices.max_distance_km, devices.min_intensity,
               devices.enabled, devices.receive_tests,
               events.source, events.report_num, events.is_final, events.is_cancel,
               events.epicenter, events.latitude, events.longitude, events.magnitude,
               events.depth_km, events.origin_time, events.raw_json, events.test
        FROM decisions d
        JOIN devices ON devices.id = d.device_id
        JOIN events ON events.event_id = d.event_id
        WHERE d.should_push = 1
        ORDER BY d.id DESC
        LIMIT ?
        """,
        (settings.max_decisions,),
    )
    scheduled = 0
    seen: set[tuple[str, int]] = set()
    for row in rows:
        key = (row["event_id"], row["device_id"])
        if key in seen:
            continue
        seen.add(key)
        if _has_push(db, row["event_id"], row["device_id"], "arrival"):
            continue
        remaining = int(row["arrival_seconds"]) - _elapsed_seconds(row["created_at"])
        if remaining < 1 or remaining > MAX_SCHEDULED_ARRIVAL_SECONDS:
            continue
        event = EarthquakeEvent(
            event_id=row["event_id"],
            source=row["source"],
            report_num=row["report_num"],
            is_final=bool(row["is_final"]),
            is_cancel=bool(row["is_cancel"]),
            epicenter=row["epicenter"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            magnitude=row["magnitude"],
            depth_km=row["depth_km"],
            origin_time=row["origin_time"],
            raw=json.loads(row["raw_json"]),
            test=bool(row["test"]),
        )
        decision = Decision(
            device_id=row["device_id"],
            device_name=row["device_name"],
            distance_km=row["distance_km"],
            arrival_seconds=remaining,
            intensity=row["intensity"],
            intensity_text=row["intensity_text"],
            status=row["status"],
            should_push=bool(row["should_push"]),
            reason=row["reason"],
        )
        device = normalize_device(
            {
                "id": row["dev_id"],
                "name": row["device_name"],
                "push_type": row["push_type"],
                "bark_key": row["bark_key"],
                "push_url": row["push_url"],
                "default_city": row["default_city"],
                "latitude": row["dev_latitude"],
                "longitude": row["dev_longitude"],
                "min_magnitude": row["min_magnitude"],
                "max_distance_km": row["max_distance_km"],
                "min_intensity": row["min_intensity"],
                "enabled": row["enabled"],
                "receive_tests": row["receive_tests"],
            }
        )
        if _schedule_arrival_push(db, device, event, decision):
            scheduled += 1
    return scheduled
