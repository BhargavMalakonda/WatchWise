"""
Tests for services/youtube_data.py
All YouTube API calls are mocked — no real network traffic.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from services.youtube_data import (
    YouTubeDataError,
    fetch_video_data,
    filter_low_value_comments,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_http_error(status: int, reason: str) -> HttpError:
    """Construct a googleapiclient HttpError without a real HTTP response."""
    resp = MagicMock()
    resp.status = status
    resp.reason = reason
    # HttpError reads .status via attribute access
    resp.status_code = status
    return HttpError(resp=resp, content=b"")


def _build_video_response(video_id: str, title: str, published_at: str) -> dict:
    return {
        "items": [
            {
                "id": video_id,
                "snippet": {
                    "title": title,
                    "publishedAt": published_at,
                },
            }
        ]
    }


def _build_comments_response(texts: list[str]) -> dict:
    return {
        "items": [
            {
                "snippet": {
                    "topLevelComment": {
                        "snippet": {"textDisplay": t}
                    }
                }
            }
            for t in texts
        ]
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

@patch("services.youtube_data._build_client")
def test_fetch_video_data_success(mock_build):
    """Happy path: returns title, upload date, and all comments."""
    mock_yt = MagicMock()
    mock_build.return_value = mock_yt

    # videos().list().execute()
    mock_yt.videos.return_value.list.return_value.execute.return_value = (
        _build_video_response("abc123", "My Test Video", "2024-01-15T10:00:00Z")
    )
    # commentThreads().list().execute()
    mock_yt.commentThreads.return_value.list.return_value.execute.return_value = (
        _build_comments_response([
            "Very helpful tutorial",
            "Thanks for sharing this!",
            "Best explanation I have seen so far.",
        ])
    )

    result = fetch_video_data("abc123")

    assert result.video_id == "abc123"
    assert result.title == "My Test Video"
    assert result.upload_date == "2024-01-15T10:00:00Z"
    assert result.comments == [
        "Very helpful tutorial",
        "Thanks for sharing this!",
        "Best explanation I have seen so far.",
    ]


@patch("services.youtube_data._build_client")
def test_fetch_video_data_not_found(mock_build):
    """Raises YouTubeDataError when the API returns an empty items list."""
    mock_yt = MagicMock()
    mock_build.return_value = mock_yt

    mock_yt.videos.return_value.list.return_value.execute.return_value = {"items": []}

    with pytest.raises(YouTubeDataError, match="not found"):
        fetch_video_data("nonexistent")


@patch("services.youtube_data._build_client")
def test_fetch_video_data_comments_disabled(mock_build):
    """Raises YouTubeDataError with a clear message when comments are disabled."""
    mock_yt = MagicMock()
    mock_build.return_value = mock_yt

    mock_yt.videos.return_value.list.return_value.execute.return_value = (
        _build_video_response("vid1", "Some Video", "2024-03-01T00:00:00Z")
    )
    # Simulate a 403 from the commentThreads endpoint
    mock_yt.commentThreads.return_value.list.return_value.execute.side_effect = (
        _make_http_error(403, "commentsDisabled")
    )

    with pytest.raises(YouTubeDataError, match="[Cc]omments are disabled"):
        fetch_video_data("vid1")


@patch("services.youtube_data._build_client")
def test_fetch_video_metadata_api_error(mock_build):
    """Raises YouTubeDataError when the video metadata request fails."""
    mock_yt = MagicMock()
    mock_build.return_value = mock_yt

    mock_yt.videos.return_value.list.return_value.execute.side_effect = (
        _make_http_error(500, "Internal Server Error")
    )

    with pytest.raises(YouTubeDataError, match="metadata"):
        fetch_video_data("vid2")


@patch("services.youtube_data._build_client")
def test_fetch_video_data_no_comments(mock_build):
    """Returns an empty comments list when the video has no comments yet."""
    mock_yt = MagicMock()
    mock_build.return_value = mock_yt

    mock_yt.videos.return_value.list.return_value.execute.return_value = (
        _build_video_response("vid3", "New Video", "2024-06-01T00:00:00Z")
    )
    mock_yt.commentThreads.return_value.list.return_value.execute.return_value = {
        "items": []
    }

    result = fetch_video_data("vid3")
    assert result.comments == []


# ── filter_low_value_comments tests ──────────────────────────────────────────

class TestFilterLowValueComments:

    # ── filtered out ──────────────────────────────────────────────────────────

    def test_removes_comment_under_15_chars(self):
        """Short throwaway comments are dropped."""
        assert filter_low_value_comments(["lol", "nice", "cool!", "great vid"]) == []

    def test_keeps_comment_exactly_15_chars_after_strip(self):
        """15 real (non-emoji, non-punctuation) chars passes through."""
        # "Thanks so mucho" = 15 alpha+space chars, no punctuation stripped
        assert filter_low_value_comments(["Thanks so mucho"]) == ["Thanks so mucho"]

    def test_removes_comment_exactly_14_real_chars(self):
        """14 real chars (boundary just below threshold) is removed."""
        # "Thanks so much" = 14 chars, all letters/spaces
        assert filter_low_value_comments(["Thanks so much"]) == []

    def test_removes_short_comment_with_leading_trailing_whitespace(self):
        """Whitespace is stripped before length check."""
        assert filter_low_value_comments(["   ok   "]) == []

    def test_removes_emoji_only_comment(self):
        """Comments that are only emoji are dropped."""
        assert filter_low_value_comments(["👍👍👍", "🔥🔥", "❤️"]) == []

    def test_removes_punctuation_only_comment(self):
        """Comments that are only punctuation are dropped."""
        assert filter_low_value_comments(["!!!", "???", "...", "---"]) == []

    def test_removes_mixed_emoji_punctuation_comment(self):
        """Mixed emoji + punctuation with no real text is dropped."""
        assert filter_low_value_comments(["👍👍!!!👍"]) == []

    def test_removes_comment_short_after_stripping_emoji(self):
        """A comment under 15 real chars even when emoji are stripped."""
        # "nice 🔥🔥🔥" → "nice" = 4 chars
        assert filter_low_value_comments(["nice 🔥🔥🔥"]) == []

    def test_removes_pure_timestamp_mmss(self):
        """Pure mm:ss timestamps are dropped."""
        assert filter_low_value_comments(["3:22", "0:45", "12:07"]) == []

    def test_removes_pure_timestamp_hhmmss(self):
        """Pure h:mm:ss timestamps are dropped."""
        assert filter_low_value_comments(["1:02:45", "2:30:00"]) == []

    def test_removes_timestamp_with_short_label(self):
        """Timestamp with a label under 15 real chars is dropped."""
        # "3:22 wow" → label "wow" = 3 chars
        assert filter_low_value_comments(["3:22 wow"]) == []

    def test_removes_watching_in_year(self):
        """'watching in [year]' variants are dropped."""
        cases = [
            "watching in 2024",
            "Watching in 2025",
            "still watching in 2023",
            "watching this in 2024",
        ]
        assert filter_low_value_comments(cases) == []

    def test_removes_whos_here_in_year(self):
        """'who's here in [year]' variants are dropped."""
        cases = [
            "who's here in 2024",
            "whos here in 2023",
            "who is here in 2025",
            "anyone here in 2024",
            "still here in 2024",
        ]
        assert filter_low_value_comments(cases) == []

    # ── kept ──────────────────────────────────────────────────────────────────

    def test_keeps_genuine_feedback(self):
        """Substantive feedback comments pass through unchanged."""
        comments = [
            "This tutorial really helped me understand async/await in Python.",
            "The explanation at 5:30 about decorators is the clearest I've seen.",
            "I've watched this three times and something new clicks each time.",
        ]
        assert filter_low_value_comments(comments) == comments

    def test_keeps_long_comment_with_emoji(self):
        """A long comment with emoji passes once text portion is >= 15 chars."""
        comment = "Great tutorial! 🔥 Learned a lot about Python decorators."
        assert filter_low_value_comments([comment]) == [comment]

    def test_keeps_timestamp_with_long_label(self):
        """A timestamp followed by >= 15 chars of real label is kept."""
        comment = "3:22 this is where it finally clicked for me"
        assert filter_low_value_comments([comment]) == [comment]

    def test_keeps_criticism_comment(self):
        """Critical comments with substance are kept."""
        comment = "The audio quality is really poor and hard to follow in places."
        assert filter_low_value_comments([comment]) == [comment]

    def test_preserves_original_order(self):
        """Surviving comments retain their original relative order."""
        comments = [
            "lol",                                                # filtered
            "This really helped me understand the topic better.",  # kept
            "👍👍👍",                                              # filtered
            "Excellent breakdown of the core concepts here.",      # kept
            "3:22",                                               # filtered
            "I finally get how closures work after watching this.", # kept
        ]
        result = filter_low_value_comments(comments)
        assert result == [
            "This really helped me understand the topic better.",
            "Excellent breakdown of the core concepts here.",
            "I finally get how closures work after watching this.",
        ]

    def test_empty_input_returns_empty(self):
        """Empty input returns empty output."""
        assert filter_low_value_comments([]) == []

    def test_all_genuine_comments_unchanged(self):
        """When all comments are substantive, the list is returned as-is."""
        comments = [
            "Really well structured — each section builds on the last.",
            "I appreciate how you explain the why, not just the how.",
        ]
        assert filter_low_value_comments(comments) == comments

    # ── integration: filter applied inside fetch_video_data ──────────────────

    @patch("services.youtube_data._build_client")
    def test_fetch_filters_low_value_comments(self, mock_build):
        """fetch_video_data applies the filter before returning VideoData."""
        mock_yt = MagicMock()
        mock_build.return_value = mock_yt

        mock_yt.videos.return_value.list.return_value.execute.return_value = (
            _build_video_response("vid1", "Test", "2024-01-01T00:00:00Z")
        )
        raw_comments = [
            "lol",                                                    # filtered: too short
            "watching in 2024",                                       # filtered: pattern
            "This tutorial is exactly what I needed to learn Python.", # kept
            "👍",                                                     # filtered: emoji only
            "who's here in 2025",                                     # filtered: pattern
            "The section on list comprehensions alone is worth it.",   # kept
        ]
        mock_yt.commentThreads.return_value.list.return_value.execute.return_value = (
            _build_comments_response(raw_comments)
        )

        result = fetch_video_data("vid1")

        assert result.comments == [
            "This tutorial is exactly what I needed to learn Python.",
            "The section on list comprehensions alone is worth it.",
        ]
