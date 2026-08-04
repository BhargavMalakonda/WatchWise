"""
youtube_data.py
Fetches video metadata and top comments from the YouTube Data API v3.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from core.config import YOUTUBE_API_KEY


@dataclass
class VideoData:
    video_id: str
    title: str
    upload_date: str          # ISO-8601 string, e.g. "2023-04-12T18:00:00Z"
    comments: List[str] = field(default_factory=list)


class YouTubeDataError(Exception):
    """Raised when the YouTube API returns an unrecoverable error."""


def _build_client():
    """Build the YouTube API client.  Separated so tests can patch it."""
    return build("youtube", "v3", developerKey=YOUTUBE_API_KEY, cache_discovery=False)


# ── Comment filtering ─────────────────────────────────────────────────────────

# Unicode categories that count as "not real text":
#   So = Symbol, other   Sm = Symbol, math   Sk = Symbol, modifier
#   Po = Punctuation, other  Ps/Pe = open/close punct  Pd = dash
#   Cc = control chars   Cf = format chars   Zs = space separators
_NON_TEXT_CATEGORIES = frozenset({"So", "Sm", "Sk", "Po", "Ps", "Pe", "Pd",
                                   "Cc", "Cf", "Zs"})

# Pure timestamp: optional hours, mandatory mm:ss, optional label
_TIMESTAMP_RE = re.compile(r"^(\d{1,2}:)?\d{1,2}:\d{2}(\s+\S.*)?$")

# "watching in 2024", "watching this in 2024", etc.
_WATCHING_IN_RE = re.compile(
    r"watch\w*\s+(this\s+)?in\s+\d{4}", re.IGNORECASE
)

# "who's here in 2024", "who else is here in 2024", "anyone here in 2024"
_WHOS_HERE_RE = re.compile(
    r"(who('?s|\s+is|se?)\s+.*here|anyone\s+here|still\s+here)\s+in\s+\d{4}",
    re.IGNORECASE,
)


def _strip_emoji_and_whitespace(text: str) -> str:
    """Return *text* with emoji/symbols removed; regular spaces are preserved."""
    # Only remove characters in non-text categories that are NOT plain ASCII space
    return "".join(
        ch for ch in text
        if ch == " " or unicodedata.category(ch) not in _NON_TEXT_CATEGORIES
    ).strip()


def _is_only_emoji_or_punctuation(text: str) -> bool:
    """True when *text* contains no letters or digits — only emoji, punctuation, whitespace."""
    stripped = text.strip()
    if not stripped:
        return True
    # Keep if there's at least one letter or digit
    return not any(ch.isalpha() or ch.isdigit() for ch in stripped)


def filter_low_value_comments(comments: List[str]) -> List[str]:
    """
    Remove low-signal comments from *comments*, preserving original order.

    Filtered out:
    - Under 15 characters after stripping whitespace and emoji
    - Pure timestamps (e.g. "3:22", "1:02:45")
    - "watching in [year]" / "watching this in [year]" variants
    - "who's here in [year]" / "anyone here in [year]" variants
    - Comments that are only emoji and/or punctuation

    Parameters
    ----------
    comments:
        Raw comment strings in relevance order.

    Returns
    -------
    Filtered list in the same order.
    """
    kept: List[str] = []
    for comment in comments:
        stripped_text = comment.strip()

        # 1. Only emoji / punctuation (check before length, catches "👍👍👍")
        if _is_only_emoji_or_punctuation(stripped_text):
            continue

        # 2. Too short after removing emoji and whitespace
        text_only = _strip_emoji_and_whitespace(stripped_text)
        if len(text_only) < 15:
            continue

        # 3. Pure timestamp (possibly with a label like "3:22 best part")
        #    We keep timestamps with substantial labels; strip pure ones only
        if _TIMESTAMP_RE.match(stripped_text):
            # Allow if there's enough non-timestamp text following the timestamp
            label_match = re.match(r"^(\d{1,2}:)?\d{1,2}:\d{2}\s*(.*)", stripped_text)
            label = label_match.group(2).strip() if label_match else ""
            if len(_strip_emoji_and_whitespace(label)) < 15:
                continue

        # 4. "watching in [year]" pattern
        if _WATCHING_IN_RE.search(stripped_text):
            continue

        # 5. "who's here in [year]" pattern
        if _WHOS_HERE_RE.search(stripped_text):
            continue

        kept.append(comment)
    return kept


def fetch_video_data(video_id: str) -> VideoData:
    """
    Return title, upload date, and up to 100 top comments for *video_id*.

    Raises
    ------
    YouTubeDataError
        If the video does not exist, comments are disabled, or the API
        returns any other HTTP error.
    """
    youtube = _build_client()

    # ── 1. Video metadata ────────────────────────────────────────────────────
    try:
        video_response = (
            youtube.videos()
            .list(part="snippet", id=video_id)
            .execute()
        )
    except HttpError as exc:
        raise YouTubeDataError(
            f"YouTube API error while fetching video metadata: {exc.reason}"
        ) from exc

    items = video_response.get("items", [])
    if not items:
        raise YouTubeDataError(
            f"Video '{video_id}' not found. It may be private, deleted, or the ID is wrong."
        )

    snippet = items[0]["snippet"]
    title: str = snippet.get("title", "")
    upload_date: str = snippet.get("publishedAt", "")

    # ── 2. Comments (up to 100, ordered by relevance) ────────────────────────
    comments: List[str] = []
    try:
        comments_response = (
            youtube.commentThreads()
            .list(
                part="snippet",
                videoId=video_id,
                maxResults=100,
                order="relevance",
                textFormat="plainText",
            )
            .execute()
        )
        for item in comments_response.get("items", []):
            text: Optional[str] = (
                item.get("snippet", {})
                .get("topLevelComment", {})
                .get("snippet", {})
                .get("textDisplay")
            )
            if text:
                comments.append(text)

    except HttpError as exc:
        # 403 with "commentsDisabled" reason means comments are turned off
        if exc.status_code == 403:
            raise YouTubeDataError(
                f"Comments are disabled for video '{video_id}'."
            ) from exc
        raise YouTubeDataError(
            f"YouTube API error while fetching comments: {exc.reason}"
        ) from exc

    return VideoData(
        video_id=video_id,
        title=title,
        upload_date=upload_date,
        comments=filter_low_value_comments(comments),
    )
