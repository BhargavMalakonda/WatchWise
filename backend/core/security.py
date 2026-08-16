"""
security.py
Centralises all security wiring for the WatchWise backend:

  - slowapi rate limiter (10 req/min per IP on /analyze by default)
  - CORS origin list (dev vs. production)
  - HTML sanitisation helper (strips tags from untrusted text)
  - Comment/transcript count cap (defence-in-depth, silent, no error)
"""
from __future__ import annotations

import re
from typing import List

import bleach
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.config import CORS_ENV, EXTENSION_ID, RATE_LIMIT_ANALYZE

# ── Rate limiter ──────────────────────────────────────────────────────────────
# Uses the client's IP address as the rate-limit key.
# Mount this on the FastAPI app in main.py.
limiter = Limiter(key_func=get_remote_address, default_limits=[])

# The decorator to apply to the /analyze endpoint.
# Reads the limit string from config so it can be overridden in .env.
analyze_rate_limit = RATE_LIMIT_ANALYZE   # e.g. "10/minute"


# ── CORS origins ──────────────────────────────────────────────────────────────

def get_cors_origins() -> List[str]:
    """
    Local-first model: every user runs their own backend and gets their
    own randomly-assigned Chrome extension ID on 'Load Unpacked', so we
    can't allowlist a single fixed origin. Allow any chrome-extension://
    origin plus localhost, since this backend is only ever reachable on
    the user's own machine.
    """
    return ["*"]


# ── HTML sanitisation ─────────────────────────────────────────────────────────

def sanitize_text(text: str) -> str:
    """
    Strip all HTML tags from *text* and return clean plain text.

    YouTube's plainText comment format should never contain HTML, but
    defence-in-depth means we strip tags before any text reaches the LLM.
    Uses bleach.clean() with no allowed tags to remove everything,
    then bleach.linkify=False prevents re-injection via URLs.
    """
    # bleach.clean with no allowed tags strips all markup
    cleaned = bleach.clean(text, tags=[], attributes={}, strip=True)
    return cleaned


def sanitize_comments(comments: List[str]) -> List[str]:
    """Sanitize every comment string in *comments* in place, return new list."""
    return [sanitize_text(c) for c in comments]


# ── Comment count cap (defence-in-depth) ─────────────────────────────────────
# The YouTube API already caps at maxResults=100 per page (one page fetched),
# so this limit of 500 is defence-in-depth for future pagination or test data.
# Silently truncates; no error or user-facing message.
MAX_COMMENTS_TO_LLM: int = 500


def cap_comments(comments: List[str]) -> List[str]:
    """
    Return at most MAX_COMMENTS_TO_LLM comments, keeping the leading
    (highest-relevance) ones.  Silent — no exception, no log message.
    """
    return comments[:MAX_COMMENTS_TO_LLM]
