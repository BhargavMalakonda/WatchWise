"""
Tests for services/cache.py
Uses tmp SQLite databases — no filesystem side effects outside tmp_path.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.cache import (
    get_cached,
    get_daily_count,
    increment_daily_count,
    set_cached,
)


# ── Fixture: isolated per-test database ──────────────────────────────────────

@pytest.fixture()
def db(tmp_path: Path) -> Path:
    return tmp_path / "test_cache.db"


# ── Analysis cache tests ──────────────────────────────────────────────────────

def test_get_cached_miss(db: Path):
    """Returns None for a video that has never been cached."""
    assert get_cached("new_video", db_path=db) is None


def test_set_and_get_cached(db: Path):
    """A freshly cached result round-trips correctly."""
    payload = {"watch_score": 80, "recommendation": "Recommended"}
    set_cached("vid1", payload, db_path=db)

    result = get_cached("vid1", db_path=db)
    assert result == payload


def test_cached_entry_is_overwritten(db: Path):
    """set_cached on the same video_id overwrites the previous entry."""
    set_cached("vid1", {"watch_score": 50}, db_path=db)
    set_cached("vid1", {"watch_score": 90}, db_path=db)

    assert get_cached("vid1", db_path=db) == {"watch_score": 90}


def test_stale_entry_returns_none(db: Path, monkeypatch: pytest.MonkeyPatch):
    """An entry older than 7 days is treated as a cache miss."""
    import services.cache as cache_module

    set_cached("vid_stale", {"watch_score": 60}, db_path=db)

    stale_now = datetime.now(tz=timezone.utc) + timedelta(days=8)
    monkeypatch.setattr(cache_module, "datetime", _FakeDatetime(stale_now))

    assert get_cached("vid_stale", db_path=db) is None


def test_fresh_entry_within_ttl(db: Path, monkeypatch: pytest.MonkeyPatch):
    """An entry 6 days old (within TTL) is returned normally."""
    import services.cache as cache_module

    set_cached("vid_fresh", {"watch_score": 70}, db_path=db)

    still_fresh = datetime.now(tz=timezone.utc) + timedelta(days=6)
    monkeypatch.setattr(cache_module, "datetime", _FakeDatetime(still_fresh))

    assert get_cached("vid_fresh", db_path=db) == {"watch_score": 70}


def test_multiple_videos_isolated(db: Path):
    """Different video_ids do not interfere with each other."""
    set_cached("v1", {"score": 1}, db_path=db)
    set_cached("v2", {"score": 2}, db_path=db)

    assert get_cached("v1", db_path=db) == {"score": 1}
    assert get_cached("v2", db_path=db) == {"score": 2}
    assert get_cached("v3", db_path=db) is None


def test_cache_key_includes_analysis_version(db: Path, monkeypatch: pytest.MonkeyPatch):
    """Changing ANALYSIS_VERSION makes old entries invisible."""
    import services.cache as cache_module

    monkeypatch.setattr(cache_module, "ANALYSIS_VERSION", "v1")
    # Patch _cache_key to use the monkeypatched version
    set_cached("vid1", {"watch_score": 55}, db_path=db)

    # Bump version — same video_id should now be a miss
    monkeypatch.setattr(cache_module, "ANALYSIS_VERSION", "v2")
    assert get_cached("vid1", db_path=db) is None


# ── Quota tests ───────────────────────────────────────────────────────────────

def test_get_daily_count_zero_on_fresh_db(db: Path):
    """Returns 0 when no quota rows exist for today."""
    assert get_daily_count(db_path=db) == 0


def test_increment_daily_count_returns_new_count(db: Path):
    """increment_daily_count returns the incremented value."""
    assert increment_daily_count(db_path=db) == 1
    assert increment_daily_count(db_path=db) == 2
    assert increment_daily_count(db_path=db) == 3


def test_get_daily_count_after_increments(db: Path):
    """get_daily_count reflects previous increments."""
    increment_daily_count(db_path=db)
    increment_daily_count(db_path=db)
    assert get_daily_count(db_path=db) == 2


def test_quota_isolated_per_day(db: Path, monkeypatch: pytest.MonkeyPatch):
    """Counts for different dates do not bleed into each other."""
    import services.cache as cache_module

    monkeypatch.setattr(cache_module, "_today_utc", lambda: "2024-01-01")
    increment_daily_count(db_path=db)
    increment_daily_count(db_path=db)

    monkeypatch.setattr(cache_module, "_today_utc", lambda: "2024-01-02")
    assert get_daily_count(db_path=db) == 0


# ── Helper ────────────────────────────────────────────────────────────────────

class _FakeDatetime:
    def __init__(self, fixed_now: datetime):
        self._now = fixed_now

    def now(self, tz=None):
        return self._now if tz is not None else self._now.replace(tzinfo=None)

    def fromisoformat(self, s: str) -> datetime:
        return datetime.fromisoformat(s)

    def __getattr__(self, name: str):
        return getattr(datetime, name)
