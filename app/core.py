from __future__ import annotations

import asyncio
import json

from .db import Database
from .geo import estimate_arrival_seconds, estimate_intensity, haversine_km, intensity_text, wave_status
from .models import Decision, EarthquakeEvent, utc_now
from .push import dispatch_push
from .config import settings

GLOBAL_MAJOR_MAGNITUDE = 7.5


async def _dispatch_and_update_push(db: Database, push_id: int, device: dict, event: EarthquakeEvent, decision: Decision) -> None:
    result = await dispatch_push(device, event, decision)
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
    if override:
        distance = float(override.get("distance_km", 0))
        arrival = int(override.get("countdown_seconds", 0))
        intensity = float(override.get("intensity", 0))
    else:
        distance = haversine_km(event.latitude, event.longitude, device["latitude"], device["longitude"])
        arrival = estimate_arrival_seconds(event.origin_time, distance)
        intensity = estimate_intensity(event.magnitude, distance, event.depth_km)
        if distance > device["max_distance_km"] and event.magnitude >= GLOBAL_MAJOR_MAGNITUDE:
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
    elif event.magnitude >= GLOBAL_MAJOR_MAGNITUDE:
        should_push, reason = True, "global major earthquake"
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
    db.execute(
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
    devices = [normalize_device(row) for row in db.query("SELECT * FROM devices ORDER BY id")]
    decisions: list[Decision] = []
    for device in devices:
        decision = decide_for_device(event, device, override)
        decisions.append(decision)
        already_pushed = db.one(
            "SELECT id FROM pushes WHERE event_id = ? AND device_id = ? LIMIT 1",
            (event.event_id, device["id"]),
        )
        db.execute(
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
                int(bool(already_pushed)),
                utc_now(),
            ),
        )
        if decision.should_push and not already_pushed:
            cur = db.execute(
                """
                INSERT INTO pushes
                (event_id, device_id, channel, ok, status_code, latency_ms, message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    device["id"],
                    device["push_type"],
                    0,
                    None,
                    0,
                    "pending",
                    utc_now(),
                ),
            )
            asyncio.create_task(_dispatch_and_update_push(db, cur.lastrowid, device, event, decision))
    db.set_state("latest_alert", {"event": event.model_dump(), "decisions": [d.model_dump() for d in decisions]})
    db.prune_logs(settings.max_events, settings.max_decisions, settings.max_pushes)
    return decisions
