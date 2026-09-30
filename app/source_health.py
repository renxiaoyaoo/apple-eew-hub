from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from .config import get_system_config
from .core import normalize_device
from .db import Database
from .models import utc_now
from .push import dispatch_system_notification
from .wolfx import wolfx_endpoints

SOURCE_NAMES = {
    "sc_eew": "四川地震预警",
    "cq_eew": "重庆地震预警",
    "cenc_eew": "中国地震台网预警",
    "cenc_eqlist": "中国地震台网正式速报",
    "fj_eew": "福建地震预警",
    "jma_eew": "日本气象厅",
    "all_eew": "Wolfx 全部预警",
    "emsc_global": "EMSC 全球地震",
}
STATE_KEY = "source_health_alert"
HISTORY_KEY = "source_health_history"
RETRY_SECONDS = 900
LOGGER = logging.getLogger(__name__)


def source_health_snapshot(db: Database) -> tuple[list[str], list[str]]:
    config = get_system_config()
    expected = [source for source, _ in wolfx_endpoints(config)] if config["wolfx_enabled"] else []
    if config["global_enabled"]:
        expected.append("emsc_global")
    wolfx = db.get_state("listener", {}).get("sources", {})
    global_sources = db.get_state("global_listener", {}).get("sources", {})
    states = {**wolfx, **global_sources}
    disconnected = [name for name in expected if not states.get(name, {}).get("connected")]
    return expected, disconnected


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class SourceHealthMonitor:
    def __init__(self, db: Database):
        self.db = db
        self.task: asyncio.Task | None = None
        self.running = False

    def start(self) -> None:
        if self.task:
            return
        self.running = True
        self.task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self.running = False
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.task = None

    async def _run(self) -> None:
        await asyncio.sleep(10)
        while self.running:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Source health check failed")
            await asyncio.sleep(30)

    async def _notify(self, title: str, body: str, recovery: bool) -> list[dict]:
        devices = [normalize_device(row) for row in self.db.query("SELECT * FROM devices WHERE enabled = 1 ORDER BY id")]
        if not devices:
            return []
        return await asyncio.gather(
            *(dispatch_system_notification(device, title, body, recovery) for device in devices)
        )

    def _record_history(self, title: str, body: str, results: list[dict]) -> None:
        history = self.db.get_state(HISTORY_KEY, [])
        history.insert(
            0,
            {
                "title": title,
                "body": body,
                "ok": sum(bool(item.get("ok")) for item in results),
                "total": len(results),
                "created_at": utc_now(),
            },
        )
        self.db.set_state(HISTORY_KEY, history[:50])

    async def check_once(self, now: datetime | None = None) -> None:
        config = get_system_config()
        if not config["source_health_alert_enabled"]:
            self.db.set_state(STATE_KEY, {})
            return
        now = now or datetime.now(timezone.utc)
        expected, disconnected = source_health_snapshot(self.db)
        state = self.db.get_state(STATE_KEY, {})
        if not expected:
            self.db.set_state(STATE_KEY, {})
            return

        source_states = dict(state.get("sources") or {})
        if not source_states and state.get("outage_started_at"):
            source_states = {
                name: {
                    "outage_started_at": state.get("outage_started_at"),
                    "notified": bool(state.get("notified")),
                    "last_attempt_at": state.get("last_attempt_at"),
                }
                for name in state.get("failed_sources") or disconnected
            }

        recovered = [
            name
            for name, source_state in source_states.items()
            if name in expected and name not in disconnected and source_state.get("notified")
        ]
        for name in list(source_states):
            if name not in disconnected:
                source_states.pop(name, None)

        due: list[tuple[str, int]] = []
        threshold_seconds = config["source_health_alert_after_minutes"] * 60
        for name in disconnected:
            source_state = dict(source_states.get(name) or {})
            started_at = _parse_time(source_state.get("outage_started_at")) or now
            last_attempt = _parse_time(source_state.get("last_attempt_at"))
            elapsed = (now - started_at).total_seconds()
            retry_due = not last_attempt or (now - last_attempt).total_seconds() >= RETRY_SECONDS
            source_state["outage_started_at"] = started_at.isoformat()
            source_state["notified"] = bool(source_state.get("notified"))
            if elapsed >= threshold_seconds and not source_state["notified"] and retry_due:
                due.append((name, max(1, round(elapsed / 60))))
            source_states[name] = source_state

        if due:
            names = "、".join(SOURCE_NAMES.get(name, name) for name, _ in due)
            minutes = min(minutes for _, minutes in due)
            title = "地震实时源异常"
            body = f"{names}已连续离线约{minutes}分钟，预警覆盖可能不完整。请检查服务器网络。"
            results = await self._notify(title, body, recovery=False)
            self._record_history(title, body, results)
            delivered = any(item.get("ok") for item in results)
            for name, _ in due:
                source_states[name]["last_attempt_at"] = now.isoformat()
                source_states[name]["notified"] = delivered

        if recovered:
            names = "、".join(SOURCE_NAMES.get(name, name) for name in recovered)
            title = "地震实时源已恢复"
            body = f"{names}已恢复连接，实时预警覆盖正常。"
            results = await self._notify(title, body, recovery=True)
            self._record_history(title, body, results)

        next_state = {
            "sources": source_states,
            "failed_sources": disconnected,
            "notified": any(item.get("notified") for item in source_states.values()),
        }
        self.db.set_state(STATE_KEY, next_state if source_states else {})
