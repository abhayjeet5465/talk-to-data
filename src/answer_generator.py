"""
answer_generator.py — LLM Call #2: result rows → plain English + structured metadata.

Takes the small aggregated result DataFrame, the user's question, and the filename,
then asks the LLM to write a plain-English explanation AND return structured metadata
(which columns were used, what assumptions were made).

Design decisions:
  - generate_answer() still returns a plain string (str). This keeps ALL existing
    tests passing since they assert isinstance(result, str).
  - generate_answer_payload() is a new function that returns a structured
    AnswerPayload with the extra metadata for the XAI expander in the UI.
  - JSON parsing falls back gracefully — if the LLM returns plain text instead
    of JSON, we just use the text as the answer with empty metadata.

Privacy: only the result rows (small aggregated output) are sent to the API.
The full dataset never leaves the local DuckDB session.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Final, NamedTuple

import pandas as pd

from src.llm_client import LLMError, call_llm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class AnswerGenerationError(Exception):
    """Raised when the LLM cannot produce a plain-English answer.

    Always carries a user-friendly message safe to show in the UI.
    """


# ---------------------------------------------------------------------------
# Structured output type — carries the answer + XAI metadata
# ---------------------------------------------------------------------------


class AnswerPayload(NamedTuple):
    """Structured output from generate_answer_payload().

    Attributes:
        answer:       Plain-English answer string (always populated).
        columns_used: List of column names that drove the answer.
                      Empty list if the LLM didn't return structured JSON.
        assumptions:  Any temporal or contextual assumptions the LLM made.
                      Empty string if none.
    """
    answer: str
    columns_used: list[str]
    assumptions: str


# ---------------------------------------------------------------------------
# Limits — controls how many result rows are sent to the LLM
# ---------------------------------------------------------------------------

# Keeps token usage low and avoids accidental leakage for large results.
_MAX_RESULT_ROWS_TO_LLM: Final[int] = 50

# ---------------------------------------------------------------------------
# System prompt — asks for structured JSON output
#
# The JSON format gives us "columns_used" and "assumptions" fields for free,
# which power the XAI "How was this calculated?" expander in the UI.
# ---------------------------------------------------------------------------

ANSWER_SYSTEM_PROMPT: Final[str] = """You are a plain-English data analyst explaining results to a non-technical business user.

Output ONLY a valid JSON object — no markdown, no preamble, nothing else:
{
  "answer": "2-3 sentence plain-English explanation. Include actual numbers. End with: (Source: <filename>, <n> rows analysed)",
  "columns_used": ["exact_column_name_1", "exact_column_name_2"],
  "assumptions": "State any date or definition assumptions (e.g. 'last month = March 2026'). Use empty string if none."
}

Rules for the "answer" field:
- Plain English only — no SQL, no jargon, no bullet points.
- Include the actual numbers from the results (rounded where helpful).
- Do not infer causes or make claims not in the provided data.
- Always end with: (Source: <filename>, <n> rows analysed)

Rules for "columns_used":
- List only the column names that directly drove the answer.
- Use the exact column names from the result data.

Rules for "assumptions":
- If you resolved "last month" or a similar phrase, state the exact dates used.
- If no assumptions were needed, use an empty string "".
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_answer(question: str, result_df: pd.DataFrame, filename: str) -> str:
    """Convert a query result into a plain-English explanation string.

    This is the original public API — returns a plain str so all
    existing tests continue to pass without modification.

    For the structured AnswerPayload (with XAI metadata), use
    generate_answer_payload() instead.

    Args:
        question:   The user's original plain-English question.
        result_df:  The small DataFrame returned by sql_executor.
        filename:   The uploaded filename for the source citation.

    Returns:
        A plain-English answer string.

    Raises:
        AnswerGenerationError: If the LLM call fails or returns empty.
    """
    payload = generate_answer_payload(question, result_df, filename)
    return payload.answer


def generate_answer_payload(
    question: str,
    result_df: pd.DataFrame,
    filename: str,
) -> AnswerPayload:
    """Convert a query result into a structured AnswerPayload.

    Calls the LLM, parses the JSON response, and returns both the
    plain-English answer AND the XAI metadata (columns_used, assumptions).

    Args:
        question:   The user's original plain-English question.
        result_df:  The small DataFrame returned by sql_executor.
                    Only up to _MAX_RESULT_ROWS_TO_LLM rows are sent to
                    the API — never the full dataset.
        filename:   The uploaded filename for the source citation.

    Returns:
        An AnswerPayload namedtuple with answer, columns_used, assumptions.

    Raises:
        AnswerGenerationError: If the LLM call fails or returns empty.
    """
    if not question or not question.strip():
        raise AnswerGenerationError("Question must not be empty.")
    if result_df is None:
        raise AnswerGenerationError("Result DataFrame must not be None.")
    if not filename or not filename.strip():
        raise AnswerGenerationError("Filename must not be empty.")

    row_count = len(result_df)

    # Truncate before sending — privacy + token budget
    rows_for_llm = result_df.head(_MAX_RESULT_ROWS_TO_LLM)
    result_str = rows_for_llm.to_string(index=False)

    user_message = (
        f"Question: {question.strip()}\n\n"
        f"Query results ({row_count} rows total, showing up to {_MAX_RESULT_ROWS_TO_LLM}):\n"
        f"{result_str}\n\n"
        f"Filename: {filename.strip()}\n"
        f"Total rows analysed: {row_count}"
    )

    try:
        raw = call_llm(ANSWER_SYSTEM_PROMPT, user_message)
    except LLMError as exc:
        raise AnswerGenerationError(f"Could not generate answer: {exc}") from exc

    if not raw:
        raise AnswerGenerationError("The AI returned an empty answer. Please try again.")

    logger.debug("Raw answer response: %s", raw[:120])
    return _parse_answer_json(raw)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_answer_json(raw: str) -> AnswerPayload:
    """Parse the JSON response from the LLM into an AnswerPayload.

    Falls back gracefully: if JSON parsing fails (e.g. because the LLM
    returned plain text), the raw text is used as the answer and the
    columns_used/assumptions fields are left empty. This means the
    XAI expander will show nothing for metadata — acceptable fallback.

    Args:
        raw: The raw string returned by the LLM.

    Returns:
        An AnswerPayload with answer, columns_used, and assumptions.
    """
    text = raw.strip()

    # Remove markdown code fences if the model wrapped the JSON in them
    if text.startswith("```"):
        text = re.sub(r"```(?:json)?", "", text).strip("`\n ")

    try:
        data = json.loads(text)
        answer = str(data.get("answer", "")).strip()
        columns_used = [str(c) for c in data.get("columns_used", [])]
        assumptions = str(data.get("assumptions", "")).strip()
        return AnswerPayload(answer=answer, columns_used=columns_used, assumptions=assumptions)
    except (json.JSONDecodeError, AttributeError):
        # Graceful fallback — use raw text as the plain answer
        logger.debug("JSON parse failed — using raw text as answer")
        return AnswerPayload(answer=raw.strip(), columns_used=[], assumptions="")