"""
Tests for services/llm_analysis.py
Gemini client is fully mocked — no real API calls.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from services.llm_analysis import LLMAnalysisError, analyze_with_gemini

# ── Shared fixtures ───────────────────────────────────────────────────────────

VALID_RESULT = {
    "watch_score": 80,
    "score_breakdown": {
        "educational_value": 75,
        "community_trust": 85,
        "clarity": 78,
        "beginner_friendliness": 70,
    },
    "outdated_risk": "low",
    "outdated_confidence": 90,
    "outdated_evidence": [],
    "misinformation_risk": "low",
    "misinformation_evidence": [],
    "community_evidence": ["Several viewers described the explanations as clear and well-paced"],
    "summary": "A solid tutorial with positive community reception.",
    "recommendation": "Recommended",
    "pros": ["Clear explanations", "Up-to-date content"],
    "cons": [],
}

CALL_ARGS = dict(
    title="Learn Python in 10 Minutes",
    upload_date="2024-03-01T00:00:00Z",
    transcript="Welcome to this tutorial. Today we cover Python basics.",
    comments=["Great video!", "Very helpful."],
    api_key="test-api-key",
)


def _mock_client(response_text: str):
    """Return a patched _build_client that always returns *response_text*."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = response_text
    mock_client.models.generate_content.return_value = mock_response
    return mock_client


# ── Tests ─────────────────────────────────────────────────────────────────────

@patch("services.llm_analysis._build_client")
def test_analyze_success_clean_json(mock_build):
    """Happy path: Gemini returns clean JSON on the first attempt."""
    mock_build.return_value = _mock_client(json.dumps(VALID_RESULT))

    result = analyze_with_gemini(**CALL_ARGS)

    assert result["watch_score"] == 80
    assert result["recommendation"] == "Recommended"
    assert result["outdated_risk"] == "low"
    assert "score_breakdown" in result
    assert result["score_breakdown"]["clarity"] == 78
    # Should only call generate_content once
    mock_build.return_value.models.generate_content.assert_called_once()


@patch("services.llm_analysis._build_client")
def test_analyze_success_with_markdown_fences(mock_build):
    """Gemini wraps JSON in ```json … ``` fences — should be stripped cleanly."""
    fenced = f"```json\n{json.dumps(VALID_RESULT)}\n```"
    mock_build.return_value = _mock_client(fenced)

    result = analyze_with_gemini(**CALL_ARGS)

    assert result["watch_score"] == 80


@patch("services.llm_analysis._build_client")
def test_analyze_retry_on_first_invalid_json(mock_build):
    """First response is garbage; retry succeeds with valid JSON."""
    mock_client = MagicMock()
    valid_resp = MagicMock()
    valid_resp.text = json.dumps(VALID_RESULT)
    invalid_resp = MagicMock()
    invalid_resp.text = "Sure! Here is the analysis: ..."

    # First call → invalid, second call → valid
    mock_client.models.generate_content.side_effect = [invalid_resp, valid_resp]
    mock_build.return_value = mock_client

    result = analyze_with_gemini(**CALL_ARGS)

    assert result["watch_score"] == 80
    assert mock_client.models.generate_content.call_count == 2


@patch("services.llm_analysis._build_client")
def test_analyze_raises_after_two_failures(mock_build):
    """Both attempts return invalid JSON — LLMAnalysisError is raised."""
    bad_resp = MagicMock()
    bad_resp.text = "Not JSON at all."
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = bad_resp
    mock_build.return_value = mock_client

    with pytest.raises(LLMAnalysisError, match="invalid JSON"):
        analyze_with_gemini(**CALL_ARGS)

    assert mock_client.models.generate_content.call_count == 2


@patch("services.llm_analysis._build_client")
def test_prompt_contains_title_and_comments(mock_build):
    """The prompt sent to Gemini includes the video title and comment text."""
    mock_build.return_value = _mock_client(json.dumps(VALID_RESULT))

    analyze_with_gemini(**CALL_ARGS)

    call_kwargs = mock_build.return_value.models.generate_content.call_args
    prompt_sent = call_kwargs.kwargs.get("contents") or call_kwargs.args[0]
    assert "Learn Python in 10 Minutes" in prompt_sent
    assert "Great video!" in prompt_sent


@patch("services.llm_analysis._build_client")
def test_transcript_truncated_at_configured_limit(mock_build):
    """Transcripts longer than TRANSCRIPT_MAX_CHARS are truncated before sending."""
    import services.llm_analysis as llm_mod

    mock_build.return_value = _mock_client(json.dumps(VALID_RESULT))

    # Temporarily lower the limit so the test doesn't need a huge string
    original_limit = llm_mod.TRANSCRIPT_MAX_CHARS
    llm_mod.TRANSCRIPT_MAX_CHARS = 100
    try:
        long_transcript = "x" * 200
        analyze_with_gemini(
            title="T",
            upload_date="2024-01-01",
            transcript=long_transcript,
            comments=[],
            api_key="test-api-key",
        )
    finally:
        llm_mod.TRANSCRIPT_MAX_CHARS = original_limit

    call_kwargs = mock_build.return_value.models.generate_content.call_args
    prompt_sent = call_kwargs.kwargs.get("contents") or call_kwargs.args[0]
    # 200 x's must NOT appear; only up to 100 should be in the prompt
    assert "x" * 200 not in prompt_sent
    assert "x" * 100 in prompt_sent


@patch("services.llm_analysis._build_client")
def test_no_comments_uses_placeholder(mock_build):
    """When comments list is empty, the placeholder text appears in the prompt."""
    mock_build.return_value = _mock_client(json.dumps(VALID_RESULT))

    analyze_with_gemini(
        title="T",
        upload_date="2024-01-01",
        transcript="some transcript",
        comments=[],
        api_key="test-api-key",
    )

    call_kwargs = mock_build.return_value.models.generate_content.call_args
    prompt_sent = call_kwargs.kwargs.get("contents") or call_kwargs.args[0]
    assert "(no comments available)" in prompt_sent
