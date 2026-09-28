from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from .config import settings
from .db import Database
from .models import utc_now

LOGGER = logging.getLogger(__name__)


class MaintenanceManager:
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
        while self.running:
            try:
                await asyncio.to_thread(self.run_once)
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Scheduled maintenance failed")
            await asyncio.sleep(3600)

    def run_once(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        state = self.db.get_state("maintenance", {})
        if state.get("last_backup_day") != today:
            backup_dir = settings.data_dir / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            target = backup_dir / f"eew-hub-auto-{today}.sqlite3"
            self.db.backup(target)
            state["last_backup_day"] = today
            state["last_backup_at"] = utc_now()
            self.db.set_state("maintenance", state)
        self._prune_backups()
        self._prune_map_cache()

    def _prune_backups(self) -> None:
        backup_dir = settings.data_dir / "backups"
        automatic = sorted(backup_dir.glob("eew-hub-auto-*.sqlite3"), reverse=True)
        for path in automatic[max(1, settings.backup_retention_days):]:
            path.unlink(missing_ok=True)

    def _prune_map_cache(self) -> None:
        cache_dir = settings.data_dir / "map-cache"
        if not cache_dir.exists():
            return
        files = sorted((path for path in cache_dir.rglob("*.png") if path.is_file()), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in files[max(100, settings.map_cache_max_files):]:
            path.unlink(missing_ok=True)
