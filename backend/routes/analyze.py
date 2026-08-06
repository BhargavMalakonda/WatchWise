"""
routes/analyze.py
POST /analyze  — full analysis pipeline with provider routing, quota, and caching.

Request flow
------------
1. Validate URL → extract video_id
2. Cache hit?  → return immediately (quota not charged)
3. Provider routing:
   a. provider="gemini" + api_key supplied → use caller's key, skip quota
   b. provider="server" (default)          → check quota, 429 if exhausted
4. Parallel fetch: video metadata+comments × transcript
5. Sanitise + cap comments; sanitise transcript  (defence-in-depth)
6. LLM analysis (with the resolved API key)
7. set_cached() → return (quota already incremented in step 3b)

Security invariant
------------------
The caller-supplied api_key is held only in local variables for the
duration of this request.  It is NEVER:
  - logged or included in exception messages
  - stored in the cache or SQLite
  - echoed back in any HTTP response body or header
Error handlers explicitly avoid referencing the key even indirectly.
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, HTTPException, Request

from core.config import DEFAULT_DAILY_QUOTA, GEMINI_API_KEY
from core.security import (
    analyze_rate_limit,
    cap_comments,
    limiter,
    sanitize_comments,
    sanitize_text,
)
from models.schemas import AnalyzeRequest, AnalyzeResponse
from services.cache import get_cached, get_daily_count, increment_daily_count, set_cached
from services.llm_analysis import LLMAnalysisError, analyze_with_gemini
from services.transcript import fetch_transcript
from services.youtube_data import YouTubeDataError, fetch_video_data
from services.category_filter import should_analyze  #change01
router = APIRouter()

# ── Video-ID extraction ───────────────────────────────────────────────────────

_SHORTS_RE = re.compile(r"/shorts/([A-Za-z0-9_-]{11})")
_WATCH_RE = re.compile(r"/watch")


def _extract_video_id(url: str) -> Optional[str]:
    """
    Parse a YouTube URL and return the 11-character video ID, or None.

    Handles:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/shorts/VIDEO_ID
    """
    parsed = urlparse(url)

    # youtu.be/<id>
    if parsed.netloc == "youtu.be":
        vid = parsed.path.lstrip("/")
        return vid if len(vid) == 11 else None

    # /shorts/<id>
    shorts_match = _SHORTS_RE.search(parsed.path)
    if shorts_match:
        return shorts_match.group(1)

    # /watch?v=<id>
    if _WATCH_RE.search(parsed.path):
        qs = parse_qs(parsed.query)
        ids = qs.get("v", [])
        return ids[0] if ids else None

    return None


# ── Pipeline ──────────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=AnalyzeResponse)
@limiter.limit(analyze_rate_limit)
async def analyze_video(request: Request, body: AnalyzeRequest) -> AnalyzeResponse:
    """
    Full analysis pipeline with provider routing, daily quota, and caching.
    """
    # ── 1. Extract video ID ───────────────────────────────────────────────────
    video_id = _extract_video_id(body.video_url)
    if not video_id:
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not extract a YouTube video ID from the provided URL. "
                "Expected a URL in the form https://www.youtube.com/watch?v=VIDEO_ID, "
                "https://youtu.be/VIDEO_ID, or https://www.youtube.com/shorts/VIDEO_ID."
            ),
        )

    # ── 2. Cache check (quota-free) ───────────────────────────────────────────
    cached = get_cached(video_id)
    if cached is not None:
        return AnalyzeResponse(**cached)

    # ── 3. Resolve the API key to use; gate quota for server provider ─────────
    # NOTE: resolved_key is intentionally never included in any log message,
    # exception detail, or stored anywhere — see module docstring.
    if body.provider == "gemini":
        if not body.api_key:
            raise HTTPException(
                status_code=400,
                detail=(
                    "provider='gemini' requires an api_key. "
                    "Please supply your Gemini API key in the request body."
                ),
            )
        resolved_key: str = body.api_key
        use_quota = False
    else:
        # provider="server" — use the server's key subject to daily quota
        resolved_key = GEMINI_API_KEY
        daily_count = get_daily_count()
        if daily_count >= DEFAULT_DAILY_QUOTA:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"The server's daily analysis quota ({DEFAULT_DAILY_QUOTA}) has been reached. "
                    "Try again after midnight UTC, or supply your own Gemini API key "
                    "by setting provider='gemini' and api_key in the request."
                ),
            )
        use_quota = True

    # ── 4. Parallel fetch: metadata+comments × transcript ────────────────────

    loop = asyncio.get_running_loop()

    try:
        # Step 1: Fetch metadata only
        video_data = await loop.run_in_executor(
            None,
            fetch_video_data,
            video_id,
        )
    except YouTubeDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Step 2: Skip obvious non-educational content
    decision = should_analyze(video_data.category_id)

    if not decision.allowed:
        raise HTTPException(
            status_code=422,
            detail=(
                f"This video belongs to the '{decision.category_name}' category. "
                "WatchWise currently analyzes educational and informational content only."
            ),
        )

    # Step 3: Only now fetch the transcript
    transcript = await loop.run_in_executor(
        None,
        fetch_transcript,
        video_id,
    )

    if transcript is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No transcript is available for video '{video_id}'. "
                "WatchWise requires a transcript to perform a reliable analysis."
            ),
        )

    # ── 5. Sanitise + cap untrusted content (defence-in-depth) ───────────────
    # Strip any HTML tags from comments and transcript before they reach the LLM.
    # Cap comment count silently — the YouTube API already limits to 100, but
    # this is a forward-compatible guard requiring no error or user message.
    clean_comments = cap_comments(sanitize_comments(video_data.comments))
    clean_transcript = sanitize_text(transcript)

    # ── 6. LLM analysis ───────────────────────────────────────────────────────
    # Increment quota BEFORE the LLM call so that even a failed call counts
    # against budget (prevents quota exhaustion bypass via repeated failures).
    if use_quota:
        increment_daily_count()

    try:
        result_dict = await loop.run_in_executor(
            None,
            lambda: analyze_with_gemini(
                title=video_data.title,
                upload_date=video_data.upload_date,
                transcript=clean_transcript,
                comments=clean_comments,
                api_key=resolved_key,
            ),
        )
    except LLMAnalysisError as exc:
        # LLMAnalysisError.args may contain the raw Gemini response but
        # never the caller's key — still safe to surface.
        raise HTTPException(
            status_code=502,
            detail=f"Analysis failed: {exc}",
        ) from exc
    finally:
        # Explicitly delete the key reference so it doesn't linger in the
        # frame's locals beyond this point, even on the error path.
        del resolved_key

    # ── 7. Validate, cache, return ────────────────────────────────────────────
    try:
        response = AnalyzeResponse(**result_dict)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Gemini returned a response that doesn't match the expected schema.",
        ) from exc

    # set_cached() is only reached on the fully successful path.
    set_cached(video_id, result_dict)
    return response
