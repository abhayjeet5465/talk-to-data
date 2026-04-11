"""
answer_generator.py — Stage 4.
Converts SQL result DataFrame into plain-English explanation via LLM.
"""
from __future__ import annotations

"""
src/answer_generator.py — LLM Call #2: result rows → plain English answer.

Takes the small aggregated result DataFrame produced by sql_executor,
the user's original question, and the filename, then asks the LLM to
write a 2-3 sentence plain-English explanation.

Only the result rows (never the full dataset) are sent to the API,
preserving the privacy guarantee from REFERENCE.md §3.
"""

import logging
from typing import Final

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
# Limits on how many result rows are sent to the LLM
# Keeps token usage low and avoids accidental data leakage for large results
# ---------------------------------------------------------------------------

_MAX_RESULT_ROWS_TO_LLM: Final[int] = 50

# ---------------------------------------------------------------------------
# System prompt
# (also documented in docs/prompt_engineering.md)
# ---------------------------------------------------------------------------

ANSWER_SYSTEM_PROMPT: Final[str] = """You are a plain-English data analyst explaining query results to a non-technical business user.

Rules you MUST follow:
1. Write exactly 2-3 sentences. No more.
2. Use plain English — no SQL, no technical jargon, no bullet points.
3. Include the actual numbers from the results (rounded to 2 decimal places where needed).
4. Do not infer causes or make claims not supported by the data provided.
5. End your response with exactly: (Source: {filename}, {n} rows analysed)
   — replace {filename} and {n} with the real values provided.
6. Output ONLY the plain-English answer. No preamble, no markdown.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_answer(
    question: str,
    result_df: pd.DataFrame,
    filename: str,
) -> str:
    """Convert a query result DataFrame into a plain-English explanation.

    Sends the user's question, the result rows (up to 50), and the
    filename to the LLM and returns a 2-3 sentence answer that always
    cites the data source.

    Args:
        question:   The user's original plain-English question.
        result_df:  The small DataFrame returned by sql_executor.execute_query().
                    Only up to _MAX_RESULT_ROWS_TO_LLM rows are sent to
                    the API — never the full dataset.
        filename:   The original uploaded filename (e.g. "sales_data.csv").
                    Used in the mandatory source citation at the end.

    Returns:
        A 2-3 sentence plain-English answer string ending with
        "(Source: {filename}, {n} rows analysed)".

    Raises:
        AnswerGenerationError: If the LLM call fails or returns empty.
                               Message is user-friendly.
    """
    if not question or not question.strip():
        raise AnswerGenerationError("Question must not be empty.")
    if result_df is None:
        raise AnswerGenerationError("Result DataFrame must not be None.")
    if not filename or not filename.strip():
        raise AnswerGenerationError("Filename must not be empty.")

    row_count = len(result_df)

    # Truncate before sending to API — privacy + token budget
    rows_for_llm = result_df.head(_MAX_RESULT_ROWS_TO_LLM)
    result_str = rows_for_llm.to_string(index=False)

    user_message = (
        f"Question: {question.strip()}\n\n"
        f"Query results ({row_count} rows total, showing up to "
        f"{_MAX_RESULT_ROWS_TO_LLM}):\n{result_str}\n\n"
        f"Filename: {filename.strip()}\n"
        f"Total rows analysed: {row_count}"
    )

    try:
        answer = call_llm(ANSWER_SYSTEM_PROMPT, user_message)
    except LLMError as exc:
        raise AnswerGenerationError(
            f"Could not generate answer: {exc}"
        ) from exc

    if not answer:
        raise AnswerGenerationError(
            "The AI returned an empty answer. Please try again."
        )

    logger.debug("Generated answer: %s", answer[:120])
    return answer