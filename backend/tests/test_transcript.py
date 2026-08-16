"""
Tests for services/transcript.py
YouTubeTranscriptApi is fully mocked — no real network traffic.

Compatible with youtube-transcript-api >= 0.9 (instance-based fetch API).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

from services.transcript import fetch_transcript


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_snippets(texts: list[str]):
    """Build a list of mock snippet objects with a .text attribute."""
    snippets = []
    for t in texts:
        s = MagicMock()
        s.text = t
        snippets.append(s)
    return snippets


# ── Tests ─────────────────────────────────────────────────name──────────────────

@patch("services.transcript.YouTubeTranscriptApi")
def test_fetch_transcript_success(MockApi):
    """Happy path: joins snippet texts into a single string."""
    instance = MockApi.return_value
    instance.fetch.return_value = _make_snippets(
        ["Hello world", "This is a test.", "Goodbye."]
    )

    result = fetch_transcript("vid1")

    assert result == "Hello world This is a test. Goodbye."
    instance.fetch.assert_called_once_with("vid1")


@patch("services.transcript.YouTubeTranscriptApi")
def test_fetch_transcript_disabled(MockApi):
    """Returns None when transcripts are disabled."""
    instance = MockApi.return_value
    instance.fetch.side_effect = TranscriptsDisabled("vid2")

    assert fetch_transcript("vid2") is None


@patch("services.transcript.YouTubeTranscriptApi")
def test_fetch_transcript_not_found(MockApi):
    """Returns None when no transcript exists in any language."""
    instance = MockApi.return_value
    instance.fetch.side_effect = NoTranscriptFound("vid3", [], {})

    assert fetch_transcript("vid3") is None


@patch("services.transcript.YouTubeTranscriptApi")
def test_fetch_transcript_video_unavailable(MockApi):
    """Returns None when the video itself is unavailable."""
    instance = MockApi.return_value
    instance.fetch.side_effect = VideoUnavailable("vid4")

    assert fetch_transcript("vid4") is None


@patch("services.transcript.YouTubeTranscriptApi")
def test_fetch_transcript_could_not_retrieve(MockApi):
    """Returns None for CouldNotRetrieveTranscript (network / parsing error)."""
    instance = MockApi.return_value
    instance.fetch.side_effect = CouldNotRetrieveTranscript("vid5")

    assert fetch_transcript("vid5") is None


@patch("services.transcript.YouTubeTranscriptApi")
def test_fetch_transcript_unexpected_error(MockApi):
    """Returns None instead of propagating unexpected exceptions."""
    instance = MockApi.return_value
    instance.fetch.side_effect = RuntimeError("Unexpected network failure")

    assert fetch_transcript("vid6") is None


@patch("services.transcript.YouTubeTranscriptApi")
def test_fetch_transcript_empty(MockApi):
    """Returns an empty string when the transcript has no snippets."""
    instance = MockApi.return_value
    instance.fetch.return_value = []

    result = fetch_transcript("vid7")
    assert result == ""
