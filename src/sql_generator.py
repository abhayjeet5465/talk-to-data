"""
sql_generator.py — Stage 4.
Converts natural language question + schema into a DuckDB SQL query via LLM.
"""
from __future__ import annotations

"""
src/sql_generator.py — LLM Call #1: natural language → SQL query.

Sends the schema string (column names, types, 3 sample rows) plus the
user's question to the LLM and returns a single SELECT statement that
DuckDB can execute against the in-memory table named 'data'.

The full dataset never leaves the process — only the schema string is
sent to the API (privacy guarantee from REFERENCE.md §3).
"""

import logging
from typing import Final

from src.llm_client import LLMError, call_llm
from src.config import DUCKDB_TABLE_NAME

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class SQLGenerationError(Exception):
    """Raised when the LLM cannot produce a usable SQL query.

    Always carries a user-friendly message safe to show in the UI.
    """


# ---------------------------------------------------------------------------
# Sentinel returned by the LLM when the question cannot be answered
# ---------------------------------------------------------------------------

CANNOT_ANSWER_SENTINEL: Final[str] = "CANNOT_ANSWER"

# ---------------------------------------------------------------------------
# System prompt
# (also documented in docs/prompt_engineering.md)
# ---------------------------------------------------------------------------

SQL_SYSTEM_PROMPT: Final[str] = f"""You are a SQL expert. Convert the user's natural-language question into a single DuckDB-compatible SELECT query.

Rules you MUST follow:
1. Output ONLY the raw SQL query — no markdown, no backticks, no explanation.
2. The table name is always: {DUCKDB_TABLE_NAME}
3. Use only SELECT statements — never INSERT, UPDATE, DELETE, DROP, or any mutation.
4. Use DuckDB SQL syntax (STRFTIME, DATE_TRUNC, EPOCH, etc. where needed).
5. Always add an ORDER BY clause when returning multiple rows.
6. If the question cannot be answered from the schema, output exactly: {CANNOT_ANSWER_SENTINEL}
7. Column names must match the schema exactly — do not invent columns.
8. Limit results to 500 rows maximum using LIMIT 500.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_sql(question: str, schema_str: str) -> str:
    """Convert a natural-language question into a DuckDB SELECT query.

    Sends the schema string and the user's question to the LLM (via
    llm_client.call_llm) and returns the SQL string.

    Args:
        question:   The user's plain-English question, e.g.
                    "Which region had the highest revenue last month?"
        schema_str: The schema context string produced by
                    schema_extractor.extract_schema() — column names,
                    types, and 3 sample rows. Never contains full data.

    Returns:
        A DuckDB-compatible SELECT query string, OR the sentinel string
        "CANNOT_ANSWER" if the LLM determines the question cannot be
        answered from the available schema.

    Raises:
        SQLGenerationError: If the LLM call fails or returns an empty
                            response. Message is user-friendly.
    """
    if not question or not question.strip():
        raise SQLGenerationError("Question must not be empty.")
    if not schema_str or not schema_str.strip():
        raise SQLGenerationError("Schema string must not be empty.")

    user_message = f"Schema:\n{schema_str}\n\nQuestion: {question.strip()}"

    try:
        raw = call_llm(SQL_SYSTEM_PROMPT, user_message)
    except LLMError as exc:
        raise SQLGenerationError(
            f"Could not generate SQL: {exc}"
        ) from exc

    sql = _clean_sql(raw)

    if not sql:
        raise SQLGenerationError(
            "The AI returned an empty response. Please rephrase your question."
        )

    logger.debug("Generated SQL: %s", sql)
    return sql


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clean_sql(raw: str) -> str:
    """Strip markdown fences and extra whitespace from the LLM response.

    Despite the system prompt saying "no backticks", models sometimes
    wrap output in ```sql ... ``` fences. This removes them defensively.

    Args:
        raw: The raw string returned by the LLM.

    Returns:
        Cleaned SQL string, or CANNOT_ANSWER_SENTINEL if that was returned.
    """
    text = raw.strip()

    # If the model returned the sentinel, pass it through unchanged
    if text.upper() == CANNOT_ANSWER_SENTINEL:
        return CANNOT_ANSWER_SENTINEL

    # Strip common markdown code fences
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove opening fence (```sql or ```)
        lines = lines[1:] if lines[0].startswith("```") else lines
        # Remove closing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    return text