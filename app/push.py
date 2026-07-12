from __future__ import annotations

import asyncio
import time
from urllib.parse import quote

import httpx

from .config import get_system_config, settings
from .models import Decision, EarthquakeEvent

PUSH_ICON_URL = "https://cdn-icons-png.flaticon.com/512/12688/12688039.png"


def bark_tier(intensity: float) -> str:
    config = get_system_config()
    if intensity >= config["alert_red_intensity"]:
        return "red"
    if intensity >= config["alert_yellow_intensity"]:
        return "yellow"
    return "blue"


def bark_level(intensity: float) -> dict[str, str]:
    config = get_system_config()
    tier = bark_tier(intensity)
    if tier == "red":
        payload = {"level": config["bark_red_level"], "sound": config["bark_red_sound"]}
        if config["bark_red_volume"]:
            payload["volume"] = config["bark_red_volume"]
        return payload
    if tier == "yellow":
        payload = {"level": config["bark_yellow_level"], "sound": config["bark_yellow_sound"]}
        if config["bark_yellow_volume"]:
            payload["volume"] = config["bark_yellow_volume"]
        return payload
    payload = {"level": config["bark_blue_level"], "sound": config["bark_blue_sound"]}
    if config["bark_blue_volume"]:
        payload["volume"] = config["bark_blue_volume"]
    return payload


def bark_repeat(intensity: float) -> tuple[int, float]:
    config = get_system_config()
    tier = bark_tier(intensity)
    return int(config[f"bark_{tier}_repeat"]), float(config[f"bark_{tier}_repeat_gap_seconds"])


def bark_title(event: EarthquakeEvent, intensity: float, arrival_seconds: int) -> str:
    tier = bark_tier(intensity)
    if event.source == "emsc_global" and intensity <= 1:
        return f"全球特大地震提醒：M{event.magnitude:.1f}"
    if tier == "red":
        return f"强震预警：{arrival_seconds}秒后到达" if arrival_seconds > 0 else "强震预警：横波已到达"
    if tier == "yellow":
        return f"地震预警：{arrival_seconds}秒后到达" if arrival_seconds > 0 else "地震预警：横波已到达"
    return f"地震提醒：{arrival_seconds}秒后到达" if arrival_seconds > 0 else "地震提醒：横波已到达"


def bark_payload(event: EarthquakeEvent, distance_km: float, intensity: float, text: str, arrival_seconds: int) -> tuple[str, dict[str, str]]:
    tier = bark_tier(intensity)
    title = bark_title(event, intensity, arrival_seconds)
    if event.source == "emsc_global" and intensity <= 1:
        body = f"{event.epicenter}，距你约{distance_km:.0f}km。远距离预警提醒，不显示本地倒计时。"
    else:
        body = (
            f"{event.epicenter} M{event.magnitude:.1f}，距你{distance_km:.0f}km，"
            f"预计烈度{intensity:g}：{text}。勿乘电梯，保护头部。"
        )
    query = {
        **bark_level(intensity),
        "group": "earthquake",
        "icon": PUSH_ICON_URL,
        "isArchive": "1",
    }
    if tier == "red" and arrival_seconds > 0:
        query["call"] = "1"
    if settings.public_base_url:
        query["url"] = settings.public_base_url.rstrip("/") + f"/event/{quote(event.event_id)}"
    return f"{quote(title)}/{quote(body)}", query


async def send_bark(
    bark_key: str,
    event: EarthquakeEvent,
    distance_km: float,
    intensity: float,
    text: str,
    arrival_seconds: int,
    repeat_override: int | None = None,
) -> dict:
    if not bark_key:
        return {"channel": "bark", "ok": False, "status_code": None, "latency_ms": 0, "message": "missing Bark key"}
    path, query = bark_payload(event, distance_km, intensity, text, arrival_seconds)
    url = f"{settings.bark_base_url.rstrip('/')}/{quote(bark_key.strip(), safe='')}/{path}"
    repeat, gap = bark_repeat(intensity)
    if repeat_override is not None:
        repeat = max(1, repeat_override)
        gap = 0
    started = time.perf_counter()
    results = []
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            for index in range(repeat):
                if index:
                    await asyncio.sleep(gap)
                resp = await client.get(url, params=query)
                results.append(resp)
        latency_ms = int((time.perf_counter() - started) * 1000)
        ok_count = sum(1 for item in results if 200 <= item.status_code < 300)
        ok = ok_count > 0
        last = results[-1]
        return {
            "channel": "bark",
            "ok": ok,
            "status_code": last.status_code,
            "latency_ms": latency_ms,
            "message": f"ok {ok_count}/{repeat}" if ok else last.text[:300],
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {"channel": "bark", "ok": False, "status_code": None, "latency_ms": latency_ms, "message": str(exc)[:300]}


def push_text(event: EarthquakeEvent, decision: Decision) -> tuple[str, str]:
    title = f"地震预警：{decision.arrival_seconds}秒后到达" if decision.arrival_seconds > 0 else "地震预警：横波已到达"
    body = (
        f"{event.epicenter} M{event.magnitude:.1f}，距你{decision.distance_km:.0f}km，"
        f"预计烈度{decision.intensity:g}：{decision.intensity_text}。勿乘电梯，保护头部。"
    )
    return title, body


async def send_ntfy(url: str, event: EarthquakeEvent, decision: Decision) -> dict:
    if not url:
        return {"channel": "ntfy", "ok": False, "status_code": None, "latency_ms": 0, "message": "missing ntfy URL"}
    title, body = push_text(event, decision)
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(
                url,
                content=body.encode("utf-8"),
                headers={"Title": title, "Priority": "urgent", "Tags": "warning"},
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        ok = 200 <= resp.status_code < 300
        return {"channel": "ntfy", "ok": ok, "status_code": resp.status_code, "latency_ms": latency_ms, "message": "ok" if ok else resp.text[:300]}
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {"channel": "ntfy", "ok": False, "status_code": None, "latency_ms": latency_ms, "message": str(exc)[:300]}


async def send_webhook(url: str, event: EarthquakeEvent, decision: Decision) -> dict:
    if not url:
        return {"channel": "webhook", "ok": False, "status_code": None, "latency_ms": 0, "message": "missing webhook URL"}
    title, body = push_text(event, decision)
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(
                url,
                json={"title": title, "body": body, "event": event.model_dump(), "decision": decision.model_dump()},
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        ok = 200 <= resp.status_code < 300
        return {"channel": "webhook", "ok": ok, "status_code": resp.status_code, "latency_ms": latency_ms, "message": "ok" if ok else resp.text[:300]}
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {"channel": "webhook", "ok": False, "status_code": None, "latency_ms": latency_ms, "message": str(exc)[:300]}


async def dispatch_push(device: dict, event: EarthquakeEvent, decision: Decision) -> dict:
    if device["push_type"] == "ntfy":
        return await send_ntfy(device.get("push_url", ""), event, decision)
    if device["push_type"] == "webhook":
        return await send_webhook(device.get("push_url", ""), event, decision)
    return await send_bark(
        device.get("bark_key", ""),
        event,
        decision.distance_km,
        decision.intensity,
        decision.intensity_text,
        decision.arrival_seconds,
    )
