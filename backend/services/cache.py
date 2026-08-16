"""
cache.py
SQLite-backed analysis cache and daily quota counter.

Cache keys are f"{video_id}_{ANALYSIS_VERSION}" so that prompt/schema
changes automatically invalidate old entries without a manual purge.

Quota counter resets at midnight UTC via a date column.

This module is intentionally unaware of HTTP semantics — callers are
responsible for only invoking set_cached() on a fully successful result.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.config import ANALYSIS_VERSION, DEFAULT_DAILY_QUOTA

# ── Configuration ─────────────────────────────────────────────────────────────
CACHE_TTL_DAYS: int = 7

# Database lives next to this file; override DB_PATH in tests via keyword arg
DB_PATH: Path = Path(__file__).parent.parent / "watchwise_cache.db"


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_cache (
            cache_key TEXT PRIMARY KEY,
            result    TEXT NOT NULL,
            cached_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_quota (
            quota_date TEXT PRIMARY KEY,
            count      INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()


def _is_fresh(cached_at_str: str) -> bool:
    """Return True if the timestamp is within CACHE_TTL_DAYS."""
    cached_at = datetime.fromisoformat(cached_at_str)
    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)
    return datetime.now(tz=timezone.utc) - cached_at < timedelta(days=CACHE_TTL_DAYS)


def _cache_key(video_id: str) -> str:
    """Combine video ID and analysis version into a single cache key."""
    return f"{video_id}_{ANALYSIS_VERSION}"


def _today_utc() -> str:
    """Return today's UTC date as an ISO-8601 string (YYYY-MM-DD)."""
    return datetime.now(tz=timezone.utc).date().isoformat()


# ── Cache public API ──────────────────────────────────────────────────────────

def get_cached(
    video_id: str,
    *,
    db_path: Path = DB_PATH,
) -> Optional[Dict[str, Any]]:
    """
    Return the cached analysis dict for *video_id* at the current
    ANALYSIS_VERSION, or ``None`` if absent or stale (> CACHE_TTL_DAYS).
    """
    key = _cache_key(video_id)
    with _get_connection(db_path) as conn:
        _ensure_tables(conn)
        row = conn.execute(
            "SELECT result, cached_at FROM analysis_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()

    if row is None:
        return None
    if not _is_fresh(row["cached_at"]):
        return None
    return json.loads(row["result"])


def set_cached(
    video_id: str,
    result: Dict[str, Any],
    *,
    db_path: Path = DB_PATH,
) -> None:
    """
    Persist *result* under the versioned cache key with the current UTC
    timestamp.  Overwrites any existing entry for the same key.

    Must only be called after a fully successful analysis — this module
    does not inspect the result or enforce that constraint itself.
    """
    key = _cache_key(video_id)
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    with _get_connection(db_path) as conn:
        _ensure_tables(conn)
        conn.execute(
            """
            INSERT INTO analysis_cache (cache_key, result, cached_at)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                result    = excluded.result,
                cached_at = excluded.cached_at
            """,
            (key, json.dumps(result), now_iso),
        )
        conn.commit()


# ── Quota public API ──────────────────────────────────────────────────────────

def get_daily_count(*, db_path: Path = DB_PATH) -> int:
    """
    Return the number of server-key analyses run today (UTC).
    Returns 0 if no row exists for today.
    """
    today = _today_utc()
    with _get_connection(db_path) as conn:
        _ensure_tables(conn)
        row = conn.execute(
            "SELECT count FROM daily_quota WHERE quota_date = ?",
            (today,),
        ).fetchone()
    return row["count"] if row else 0


def increment_daily_count(*, db_path: Path = DB_PATH) -> int:
    """
    Atomically increment today's server-key analysis count (UTC).
    Returns the new count after incrementing.
    """
    today = _today_utc()
    with _get_connection(db_path) as conn:
        _ensure_tables(conn)
        conn.execute(
            """
            INSERT INTO daily_quota (quota_date, count) VALUES (?, 1)
            ON CONFLICT(quota_date) DO UPDATE SET count = count + 1
            """,
            (today,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT count FROM daily_quota WHERE quota_date = ?",
            (today,),
        ).fetchone()
    return row["count"]
