"""SQLite storage. One short-lived connection per call; WAL so the scheduler thread and API do not block."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT UNIQUE NOT NULL,
  platform TEXT NOT NULL,
  brief TEXT NOT NULL,
  draft TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  rule_report TEXT NOT NULL DEFAULT '{}',
  trace TEXT NOT NULL DEFAULT '[]',
  scheduled_at TEXT,
  published_at TEXT,
  publish_ref TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  campaign_id INTEGER,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaigns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  brief TEXT NOT NULL,
  platform TEXT NOT NULL,
  cron TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS oauth_states (
  state TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  verifier TEXT NOT NULL,
  expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS oauth_tokens (
  provider TEXT PRIMARY KEY,
  blob TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,
  event TEXT NOT NULL,
  post_id INTEGER,
  detail TEXT NOT NULL DEFAULT ''
);
"""

JSON_COLS = ("rule_report", "trace")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    out = dict(row)
    for col in JSON_COLS:
        if col in out:
            out[col] = json.loads(out[col] or "null")
    return out


def audit(actor: str, event: str, post_id: int | None = None, detail: str = "") -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO audit (ts, actor, event, post_id, detail) VALUES (?,?,?,?,?)",
            (now_iso(), actor, event, post_id, detail[:500]),
        )
