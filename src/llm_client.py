from __future__ import annotations

"""
src/llm_client.py — LLM API wrapper for Talk to Data.

Provides a single entry point: call_llm(system_prompt, user_message) -> str

Fallback chain (mirrors the architecture in REFERENCE.md §9):
  1. Groq  llama-3.3-70b-versatile  (primary — fastest free inference)
  2. Groq  llama-3.1-8b-instant     (secondary — higher rate limit)
  3. Gemini gemini-2.5-flash        (tertiary — different provider)

On every HTTP 429 (rate limit) the next provider is tried automatically.
Any other exception is re-raised as LLMError with a user-friendly message
so the Streamlit UI can display it without showing a traceback.

Privacy note: this module never sees the raw dataset — it only receives
the prompts built by sql_generator.py and answer_generator.py.
"""

import time
import logging
from typing import Optional

import groq  # groq==0.13.1

# Suppress the google-generativeai end-of-life FutureWarning.
# We intentionally stay on 0.8.x — see REFERENCE.md §8.2 for why.
import warnings
warnings.filterwarnings(
    "ignore",
    message="All support for the `google.generativeai` package has ended",
)

import google.generativeai as genai  # google-generativeai==0.8.5

from src.config import (
    GROQ_API_KEY,
    GROQ_MODEL_PRIMARY,
    GROQ_MODEL_FALLBACK,
    GEMINI_API_KEY,
    GEMINI_MODEL,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Raised when all LLM providers fail or return unusable output.

    Always carries a user-friendly message safe to display in the UI.
    """


# ---------------------------------------------------------------------------
# Retry / delay settings
# ---------------------------------------------------------------------------

# Seconds to wait before retrying the same provider after a 429.
# Kept short for hackathon demos; increase for production.
_RETRY_DELAY_SECONDS: float = 1.0

# Maximum characters accepted as a valid response.
# Protects against accidental huge responses consuming memory.
_MAX_RESPONSE_CHARS: int = 8_000


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _call_groq(
    system_prompt: str,
    user_message: str,
    model: str,
) -> str:
    """Make a single chat completion call to the Groq API.

    Args:
        system_prompt: Instruction text placed in the system role.
        user_message:  The user's question or payload.
        model:         Groq model identifier (e.g. llama-3.3-70b-versatile).

    Returns:
        The model's reply as a plain string.

    Raises:
        groq.RateLimitError: HTTP 429 — caller should fall back.
        groq.APIError:       Any other Groq API error.
    """
    client = groq.Groq(api_key=GROQ_API_KEY)
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.0,   # Deterministic SQL / short answers
        max_tokens=1024,
    )
    text = completion.choices[0].message.content or ""
    return text.strip()


def _call_gemini(
    system_prompt: str,
    user_message: str,
) -> str:
    """Make a single generate_content call to the Gemini API.

    Uses google-generativeai==0.8.5 (older SDK — do NOT upgrade to 1.x,
    see REFERENCE.md §8.2 for the breaking-change warning).

    Args:
        system_prompt: Prepended to the user message as context.
        user_message:  The user's question or payload.

    Returns:
        The model's reply as a plain string.

    Raises:
        Exception: Any error from the Gemini SDK.
    """
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=system_prompt,
    )
    response = model.generate_content(user_message)
    text = response.text or ""
    return text.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def call_llm(
    system_prompt: str,
    user_message: str,
    *,
    _groq_primary_override: Optional[str] = None,
    _groq_fallback_override: Optional[str] = None,
) -> str:
    """Call an LLM with automatic provider fallback.

    Tries providers in order until one succeeds:
        1. Groq  (GROQ_MODEL_PRIMARY  — llama-3.3-70b-versatile)
        2. Groq  (GROQ_MODEL_FALLBACK — llama-3.1-8b-instant)
        3. Gemini (GEMINI_MODEL       — gemini-2.5-flash)

    On HTTP 429 the next provider is tried. Any other Groq error or any
    Gemini error is caught and wrapped in LLMError.

    Args:
        system_prompt: Instruction text for the model's system role.
        user_message:  The user-facing payload (schema + question, or
                       result rows + question).
        _groq_primary_override:  Used in unit tests to inject a model name.
        _groq_fallback_override: Used in unit tests to inject a model name.

    Returns:
        The model's reply as a plain string (stripped of leading/trailing
        whitespace).

    Raises:
        LLMError: When all three providers are exhausted or all fail with
                  non-rate-limit errors. The message is user-friendly and
                  safe to display directly in the Streamlit UI.
    """
    if not system_prompt:
        raise LLMError("system_prompt must not be empty.")
    if not user_message:
        raise LLMError("user_message must not be empty.")

    primary_model = _groq_primary_override or GROQ_MODEL_PRIMARY
    fallback_model = _groq_fallback_override or GROQ_MODEL_FALLBACK

    errors: list[str] = []

    # ── Step 1: Groq primary model ─────────────────────────────────────────
    try:
        logger.debug("Calling Groq primary model: %s", primary_model)
        result = _call_groq(system_prompt, user_message, model=primary_model)
        if result:
            return result.strip()[:_MAX_RESPONSE_CHARS]
    except groq.RateLimitError:
        logger.warning("Groq primary hit rate limit (429). Trying fallback model.")
        errors.append(f"Groq {primary_model}: rate limited")
        time.sleep(_RETRY_DELAY_SECONDS)
    except groq.APIError as exc:
        logger.error("Groq primary API error: %s", exc)
        errors.append(f"Groq {primary_model}: {exc}")

    # ── Step 2: Groq fallback (smaller, higher rate limit) ─────────────────
    try:
        logger.debug("Calling Groq fallback model: %s", fallback_model)
        result = _call_groq(system_prompt, user_message, model=fallback_model)
        if result:
            return result.strip()[:_MAX_RESPONSE_CHARS]
    except groq.RateLimitError:
        logger.warning("Groq fallback also rate limited. Switching to Gemini.")
        errors.append(f"Groq {fallback_model}: rate limited")
        time.sleep(_RETRY_DELAY_SECONDS)
    except groq.APIError as exc:
        logger.error("Groq fallback API error: %s", exc)
        errors.append(f"Groq {fallback_model}: {exc}")

    # ── Step 3: Gemini (different provider, separate rate limits) ──────────
    try:
        logger.debug("Calling Gemini model: %s", GEMINI_MODEL)
        result = _call_gemini(system_prompt, user_message)
        if result:
            return result.strip()[:_MAX_RESPONSE_CHARS]
    except Exception as exc:  # Gemini SDK raises broad Exception types
        logger.error("Gemini error: %s", exc)
        errors.append(f"Gemini {GEMINI_MODEL}: {exc}")

    # ── All providers failed ────────────────────────────────────────────────
    error_summary = " | ".join(errors) if errors else "Unknown failure"
    raise LLMError(
        "All AI providers are currently unavailable. Please try again in a "
        f"moment. (Details: {error_summary})"
    )