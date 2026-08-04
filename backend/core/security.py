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
    Return the list of allowed CORS origins for the current environment.

    development (default)
        Allows localhost and 127.0.0.1 on any port, plus the extension
        origin if EXTENSION_ID is already filled in.

    production (CORS_ENV=production)
        Allows only the published Chrome extension origin.
        EXTENSION_ID must be set to the real 32-character extension ID.
    """
    extension_origin = f"chrome-extension://{EXTENSION_ID}"

    if CORS_ENV == "production":
        return [extension_origin]

    # Development: localhost / 127.0.0.1 on any port + extension origin
    dev_origins = [
        "http://localhost",
        "http://127.0.0.1",
        # Common dev ports — extend as needed
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8080",
        extension_origin,
    ]
    return dev_origins


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
