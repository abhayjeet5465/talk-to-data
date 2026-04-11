from __future__ import annotations

"""
tests/test_llm_client.py — Unit tests for src/llm_client.py

All tests use monkeypatching / unittest.mock so no real API calls are made.
The test strategy mirrors the test_schema_extractor.py pattern used in Stage 2:
  - happy path
  - each fallback step
  - full exhaustion → LLMError
  - edge-case inputs

Run with:
    pytest tests/test_llm_client.py -v
"""

from unittest.mock import MagicMock, patch

import pytest

# The module under test
from src.llm_client import LLMError, call_llm


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = "You are a helpful assistant. Output ONLY the answer."
USER_MESSAGE = "What is 2 + 2?"
GOOD_RESPONSE = "4"


def _make_groq_completion(text: str) -> MagicMock:
    """Build a mock object that mimics groq.Completion structure."""
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    return completion


# ---------------------------------------------------------------------------
# Happy path — Groq primary succeeds on first call
# ---------------------------------------------------------------------------


def test_primary_groq_success():
    """Primary Groq model responds correctly — no fallback needed."""
    with patch("src.llm_client._call_groq", return_value=GOOD_RESPONSE) as mock_groq:
        result = call_llm(SYSTEM_PROMPT, USER_MESSAGE)

    assert result == GOOD_RESPONSE
    # Only one call should have been made (primary)
    assert mock_groq.call_count == 1


# ---------------------------------------------------------------------------
# Fallback to Groq secondary on 429
# ---------------------------------------------------------------------------


def test_fallback_to_groq_secondary_on_rate_limit():
    """When primary Groq hits 429, the fallback Groq model is tried."""
    import groq as groq_module

    call_count = 0

    def _side_effect(system_prompt, user_message, model):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise groq_module.RateLimitError(
                message="rate limited", response=MagicMock(), body={}
            )
        return GOOD_RESPONSE

    with patch("src.llm_client._call_groq", side_effect=_side_effect):
        with patch("src.llm_client.time.sleep"):  # skip delay in tests
            result = call_llm(SYSTEM_PROMPT, USER_MESSAGE)

    assert result == GOOD_RESPONSE
    assert call_count == 2  # primary + secondary


# ---------------------------------------------------------------------------
# Fallback to Gemini when both Groq models are rate-limited
# ---------------------------------------------------------------------------


def test_fallback_to_gemini_when_both_groq_rate_limited():
    """Both Groq models hit 429 → Gemini is tried and succeeds."""
    import groq as groq_module

    def _groq_always_rate_limit(system_prompt, user_message, model):
        raise groq_module.RateLimitError(
            message="rate limited", response=MagicMock(), body={}
        )

    with patch("src.llm_client._call_groq", side_effect=_groq_always_rate_limit):
        with patch("src.llm_client._call_gemini", return_value=GOOD_RESPONSE) as mock_gemini:
            with patch("src.llm_client.time.sleep"):
                result = call_llm(SYSTEM_PROMPT, USER_MESSAGE)

    assert result == GOOD_RESPONSE
    assert mock_gemini.call_count == 1


# ---------------------------------------------------------------------------
# All providers fail → LLMError raised
# ---------------------------------------------------------------------------


def test_llm_error_raised_when_all_providers_fail():
    """LLMError is raised with a user-friendly message when every provider fails."""
    import groq as groq_module

    def _groq_fail(system_prompt, user_message, model):
        raise groq_module.RateLimitError(
            message="rate limited", response=MagicMock(), body={}
        )

    def _gemini_fail(system_prompt, user_message):
        raise Exception("Gemini quota exceeded")

    with patch("src.llm_client._call_groq", side_effect=_groq_fail):
        with patch("src.llm_client._call_gemini", side_effect=_gemini_fail):
            with patch("src.llm_client.time.sleep"):
                with pytest.raises(LLMError) as exc_info:
                    call_llm(SYSTEM_PROMPT, USER_MESSAGE)

    # Message must be user-friendly (no raw exception type names exposed)
    assert "unavailable" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Non-rate-limit Groq error falls through cleanly
# ---------------------------------------------------------------------------


def test_groq_api_error_falls_through_to_gemini():
    """A non-429 Groq APIError on the primary should still fall to Gemini."""
    import groq as groq_module

    def _groq_api_error(system_prompt, user_message, model):
        raise groq_module.APIError(
            message="internal server error", request=MagicMock(), body={}
        )

    with patch("src.llm_client._call_groq", side_effect=_groq_api_error):
        with patch("src.llm_client._call_gemini", return_value=GOOD_RESPONSE):
            result = call_llm(SYSTEM_PROMPT, USER_MESSAGE)

    assert result == GOOD_RESPONSE


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_empty_system_prompt_raises_llm_error():
    """Empty system_prompt must raise LLMError immediately (before any API call)."""
    with pytest.raises(LLMError):
        call_llm("", USER_MESSAGE)


def test_empty_user_message_raises_llm_error():
    """Empty user_message must raise LLMError immediately."""
    with pytest.raises(LLMError):
        call_llm(SYSTEM_PROMPT, "")


# ---------------------------------------------------------------------------
# Response truncation guard
# ---------------------------------------------------------------------------


def test_response_is_truncated_to_max_chars():
    """Responses longer than _MAX_RESPONSE_CHARS must be truncated."""
    from src.llm_client import _MAX_RESPONSE_CHARS

    huge_response = "x" * (_MAX_RESPONSE_CHARS + 500)

    with patch("src.llm_client._call_groq", return_value=huge_response):
        result = call_llm(SYSTEM_PROMPT, USER_MESSAGE)

    assert len(result) == _MAX_RESPONSE_CHARS


# ---------------------------------------------------------------------------
# Whitespace stripping
# ---------------------------------------------------------------------------


def test_response_whitespace_is_stripped():
    """Leading/trailing whitespace in the model response must be stripped."""
    with patch("src.llm_client._call_groq", return_value="  4  \n"):
        result = call_llm(SYSTEM_PROMPT, USER_MESSAGE)

    assert result == "4"


# ---------------------------------------------------------------------------
# LLMError is catchable as a plain Exception
# ---------------------------------------------------------------------------


def test_llm_error_is_subclass_of_exception():
    """LLMError must be a standard Exception so callers can catch it easily."""
    assert issubclass(LLMError, Exception)


# ---------------------------------------------------------------------------
# call_llm returns a string (type contract)
# ---------------------------------------------------------------------------


def test_call_llm_returns_str():
    """Return type must always be str (not bytes, not None)."""
    with patch("src.llm_client._call_groq", return_value="hello"):
        result = call_llm(SYSTEM_PROMPT, USER_MESSAGE)

    assert isinstance(result, str)