from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .models import utc_now


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS devices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  push_type TEXT NOT NULL DEFAULT 'bark',
  bark_key TEXT NOT NULL DEFAULT '',
  push_url TEXT NOT NULL DEFAULT '',
  default_city TEXT NOT NULL DEFAULT '',
  latitude REAL NOT NULL,
  longitude REAL NOT NULL,
  min_magnitude REAL NOT NULL DEFAULT 4.5,
  max_distance_km REAL NOT NULL DEFAULT 500,
  min_intensity REAL NOT NULL DEFAULT 2,
  enabled INTEGER NOT NULL DEFAULT 1,
  receive_tests INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  report_num INTEGER NOT NULL,
  is_final INTEGER NOT NULL,
  is_cancel INTEGER NOT NULL,
  epicenter TEXT NOT NULL,
  latitude REAL NOT NULL,
  longitude REAL NOT NULL,
  magnitude REAL NOT NULL,
  depth_km REAL NOT NULL,
  origin_time TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  test INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL,
  device_id INTEGER NOT NULL,
  distance_km REAL NOT NULL,
  arrival_seconds INTEGER NOT NULL,
  intensity REAL NOT NULL,
  intensity_text TEXT NOT NULL,
  status TEXT NOT NULL,
  should_push INTEGER NOT NULL,
  reason TEXT NOT NULL,
  pushed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pushes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL,
  device_id INTEGER NOT NULL,
  push_phase TEXT NOT NULL DEFAULT 'initial',
  channel TEXT NOT NULL,
  ok INTEGER NOT NULL,
  status_code INTEGER,
  latency_ms INTEGER,
  message TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        device_columns = {row["name"] for row in conn.execute("PRAGMA table_info(devices)").fetchall()}
        if "push_url" not in device_columns:
            conn.execute("ALTER TABLE devices ADD COLUMN push_url TEXT NOT NULL DEFAULT ''")
        push_columns = {row["name"] for row in conn.execute("PRAGMA table_info(pushes)").fetchall()}
        if "push_phase" not in push_columns:
            conn.execute("ALTER TABLE pushes ADD COLUMN push_phase TEXT NOT NULL DEFAULT 'initial'")
        conn.commit()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self.connect() as conn:
            cur = conn.execute(sql, tuple(params))
            conn.commit()
            return cur

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]

    def one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def set_state(self, key: str, value: Any) -> None:
        now = utc_now()
        self.execute(
            """
            INSERT INTO app_state (key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, json.dumps(value, ensure_ascii=False), now),
        )

    def get_state(self, key: str, default: Any = None) -> Any:
        row = self.one("SELECT value FROM app_state WHERE key = ?", (key,))
        if not row:
            return default
        return json.loads(row["value"])

    def prune_logs(self, max_events: int, max_decisions: int, max_pushes: int) -> None:
        self.execute(
            """
            DELETE FROM decisions
            WHERE id NOT IN (
              SELECT id FROM decisions ORDER BY id DESC LIMIT ?
            )
            """,
            (max_decisions,),
        )
        self.execute(
            """
            DELETE FROM pushes
            WHERE id NOT IN (
              SELECT id FROM pushes ORDER BY id DESC LIMIT ?
            )
            """,
            (max_pushes,),
        )
        self.execute(
            """
            DELETE FROM events
            WHERE event_id NOT IN (
              SELECT event_id FROM events ORDER BY updated_at DESC LIMIT ?
            )
            """,
            (max_events,),
        )
