"""
Tests for core/security.py — rate limiting helpers, CORS origin list,
HTML sanitisation, comment cap, and prompt injection defence.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from core.security import (
    cap_comments,
    get_cors_origins,
    sanitize_comments,
    sanitize_text,
)


# ── HTML sanitisation ─────────────────────────────────────────────────────────

class TestSanitizeText:

    def test_plain_text_unchanged(self):
        """Text with no markup passes through unchanged."""
        assert sanitize_text("Great tutorial!") == "Great tutorial!"

    def test_strips_script_tag(self):
        """<script> tags are stripped; inner text stays (bleach strip=True behaviour)."""
        result = sanitize_text("<script>alert('xss')</script>Hello")
        assert "<script>" not in result
        assert "</script>" not in result
        # The tag is gone; the inner text remains — this is bleach's strip=True contract.
        # What matters for security is that the tag markup is removed before the LLM sees it.
        assert "Hello" in result

    def test_strips_anchor_tag_keeps_text(self):
        """<a> tags are stripped but the link text survives."""
        result = sanitize_text('<a href="http://evil.com">click here</a>')
        assert "<a" not in result
        assert "click here" in result

    def test_strips_img_tag(self):
        """<img> tags are stripped entirely."""
        result = sanitize_text('<img src="x" onerror="evil()">')
        assert "<img" not in result

    def test_strips_nested_tags(self):
        """Nested HTML is fully stripped."""
        result = sanitize_text("<b><i>bold italic</i></b>")
        assert "<b>" not in result
        assert "<i>" not in result
        assert "bold italic" in result

    def test_empty_string(self):
        assert sanitize_text("") == ""

    def test_html_entities_decoded(self):
        """HTML entities are decoded to real characters by bleach."""
        result = sanitize_text("&lt;p&gt;Hello&lt;/p&gt;")
        # bleach strips the resulting tags after entity decode
        assert "<p>" not in result
        assert "Hello" in result


class TestSanitizeComments:

    def test_sanitizes_every_comment(self):
        comments = [
            "Good video!",
            "<b>Amazing</b> tutorial",
            "<script>bad()</script>Helpful content",
        ]
        result = sanitize_comments(comments)
        assert result[0] == "Good video!"
        assert "<b>" not in result[1]
        assert "Amazing" in result[1]
        assert "<script>" not in result[2]
        assert "Helpful content" in result[2]

    def test_empty_list(self):
        assert sanitize_comments([]) == []


# ── Comment cap ───────────────────────────────────────────────────────────────

class TestCapComments:

    def test_under_limit_unchanged(self):
        comments = ["comment"] * 10
        assert cap_comments(comments) == comments

    def test_exactly_at_limit(self):
        from core.security import MAX_COMMENTS_TO_LLM
        comments = ["c"] * MAX_COMMENTS_TO_LLM
        assert len(cap_comments(comments)) == MAX_COMMENTS_TO_LLM

    def test_over_limit_truncated_silently(self):
        from core.security import MAX_COMMENTS_TO_LLM
        comments = [f"comment {i}" for i in range(MAX_COMMENTS_TO_LLM + 50)]
        result = cap_comments(comments)
        assert len(result) == MAX_COMMENTS_TO_LLM
        # First MAX_COMMENTS_TO_LLM are kept (relevance order preserved)
        assert result[0] == "comment 0"
        assert result[-1] == f"comment {MAX_COMMENTS_TO_LLM - 1}"

    def test_empty_list(self):
        assert cap_comments([]) == []


# ── CORS origins ──────────────────────────────────────────────────────────────

class TestGetCorsOrigins:

    def test_development_includes_localhost(self):
        with patch("core.security.CORS_ENV", "development"):
            origins = get_cors_origins()
        localhost_origins = [o for o in origins if "localhost" in o or "127.0.0.1" in o]
        assert len(localhost_origins) > 0

    def test_development_includes_extension_origin(self):
        with (
            patch("core.security.CORS_ENV", "development"),
            patch("core.security.EXTENSION_ID", "abcdefghijklmnopqrstuvwxyzabcdef"),
        ):
            origins = get_cors_origins()
        assert "chrome-extension://abcdefghijklmnopqrstuvwxyzabcdef" in origins

    def test_production_only_extension_origin(self):
        with (
            patch("core.security.CORS_ENV", "production"),
            patch("core.security.EXTENSION_ID", "abcdefghijklmnopqrstuvwxyzabcdef"),
        ):
            origins = get_cors_origins()
        assert origins == ["chrome-extension://abcdefghijklmnopqrstuvwxyzabcdef"]
        # No localhost origins in production
        assert not any("localhost" in o for o in origins)

    def test_unknown_cors_env_treated_as_development(self):
        """Any value other than 'production' falls back to dev origins."""
        with patch("core.security.CORS_ENV", "staging"):
            origins = get_cors_origins()
        assert any("localhost" in o for o in origins)


# ── Prompt injection defence — verified via prompt template content ───────────

class TestPromptInjectionDefence:

    def test_security_notice_present_in_prompt_template(self):
        """The prompt template contains the security notice block."""
        from services.llm_analysis import _PROMPT_TEMPLATE
        assert "SECURITY NOTICE" in _PROMPT_TEMPLATE
        assert "ignore previous instructions" in _PROMPT_TEMPLATE.lower()
        assert "untrusted" in _PROMPT_TEMPLATE.lower()

    def test_security_notice_appears_before_content_sections(self):
        """The security notice must precede the transcript/comments placeholders."""
        from services.llm_analysis import _PROMPT_TEMPLATE
        notice_pos = _PROMPT_TEMPLATE.index("SECURITY NOTICE")
        transcript_pos = _PROMPT_TEMPLATE.index("{transcript_text}")
        comments_pos = _PROMPT_TEMPLATE.index("{comments_list}")
        assert notice_pos < transcript_pos
        assert notice_pos < comments_pos

    def test_data_is_distinct_from_instructions(self):
        """The template uses clear delimiters around the security notice."""
        from services.llm_analysis import _PROMPT_TEMPLATE
        assert "END SECURITY NOTICE" in _PROMPT_TEMPLATE


# ── Sanitisation applied before LLM (integration check via route) ────────────

class TestSanitisationInPipeline:

    def test_html_in_comments_stripped_before_llm(self):
        """Comments with HTML tags are sanitised before reaching analyze_with_gemini."""
        from fastapi.testclient import TestClient
        from main import app
        from services.youtube_data import VideoData

        tc = TestClient(app, raise_server_exceptions=False)
        dirty_comments = ["<script>bad()</script>This is a solid tutorial about Python basics."]

        mock_video = VideoData(
            video_id="dQw4w9WgXcQ",
            title="Test",
            upload_date="2024-01-01T00:00:00Z",
            comments=dirty_comments,
        )

        captured = {}

        def capture_llm(**kwargs):
            captured["comments"] = kwargs.get("comments", [])
            return {
                "watch_score": 80,
                "score_breakdown": {"educational_value": 70, "community_trust": 80,
                                    "clarity": 75, "beginner_friendliness": 65},
                "outdated_risk": "low", "outdated_confidence": 80,
                "outdated_evidence": [], "misinformation_risk": "low",
                "misinformation_evidence": [], "community_evidence": [],
                "summary": "Fine.", "recommendation": "Recommended",
                "pros": [], "cons": [],
            }

        with (
            patch("routes.analyze.get_cached", return_value=None),
            patch("routes.analyze.set_cached"),
            patch("routes.analyze.get_daily_count", return_value=0),
            patch("routes.analyze.increment_daily_count"),
            patch("routes.analyze.fetch_video_data", return_value=mock_video),
            patch("routes.analyze.fetch_transcript", return_value="Some transcript text."),
            patch("routes.analyze.analyze_with_gemini", side_effect=lambda **kw: capture_llm(**kw)),
        ):
            resp = tc.post("/api/v1/analyze",
                           json={"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})

        assert resp.status_code == 200
        # The <script> tag markup must not have reached the LLM
        assert all("<script>" not in c for c in captured.get("comments", []))
        assert all("</script>" not in c for c in captured.get("comments", []))
