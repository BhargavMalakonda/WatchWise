"""
transcript.py
Fetches the transcript for a YouTube video as a single plain-text string.
Returns None (never raises) when no transcript is available.

Compatible with youtube-transcript-api >= 0.9 (instance-based API).
"""
from __future__ import annotations

from typing import Optional

from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)


def fetch_transcript(video_id: str) -> Optional[str]:
    """
    Return the transcript of *video_id* as plain text, or ``None`` if
    no transcript is available for any reason.

    Handles
    -------
    - Transcripts disabled for the video
    - No transcript found in any language
    - Video unavailable
    - Any other unexpected exception (swallowed, not raised)
    """
    try:
        api = YouTubeTranscriptApi()
        # fetch() tries 'en' first; fall back to any available language
        try:
            fetched = api.fetch(video_id)
        except (NoTranscriptFound, CouldNotRetrieveTranscript):
            # Try without a language preference to get whatever is available
            fetched = api.fetch(video_id, languages=[])

        # FetchedTranscript is iterable; each item has a .text attribute
        return " ".join(snippet.text for snippet in fetched).strip()

    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable,
            CouldNotRetrieveTranscript):
        return None

    except Exception:  # noqa: BLE001 — never crash the caller over a transcript
        return None
