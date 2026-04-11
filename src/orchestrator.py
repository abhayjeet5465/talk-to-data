"""
orchestrator.py — wires all pipeline stages into a single callable function.
"""
from __future__ import annotations

"""
src/orchestrator.py — Pipeline controller for Talk to Data.

Wires all stages into a single callable: run_query().

Flow (from REFERENCE.md §3):
  1. generate_sql()      — schema + question → SQL
  2. is_safe_sql()       — blocklist check
  3. execute_query()     — DuckDB execution
  4. generate_answer()   — result rows + question → plain English
  5. select_and_render() — result DataFrame → Plotly figure

Returns an AnswerResult dataclass. Never raises — all errors are
captured in AnswerResult.error so the UI can display them gracefully.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import duckdb
import pandas as pd
import plotly.graph_objects as go

from src.answer_generator import AnswerGenerationError, generate_answer
from src.chart_selector import select_and_render
from src.sql_executor import ExecutionError, SafetyError, execute_query, is_safe_sql
from src.sql_generator import CANNOT_ANSWER_SENTINEL, SQLGenerationError, generate_sql

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class AnswerResult:
    """Container for one complete question→answer cycle.

    All fields have safe defaults so callers can always access them
    without checking for None first (except chart and error).

    Attributes:
        answer:      Plain-English answer from answer_generator, or "".
        sql:         The SQL query that was executed, or "".
        chart:       Plotly Figure if a chart was rendered, else None.
        row_count:   Number of rows in the query result.
        col_count:   Number of columns in the query result.
        source_info: Human-readable source line, e.g. "sales.csv · 24 rows".
        error:       User-friendly error message if anything failed, else "".
        cannot_answer: True if the LLM said the question is unanswerable.
    """

    answer: str = ""
    sql: str = ""
    chart: Optional[go.Figure] = None
    row_count: int = 0
    col_count: int = 0
    source_info: str = ""
    error: str = ""
    cannot_answer: bool = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_query(
    question: str,
    schema_str: str,
    conn: duckdb.DuckDBPyConnection,
    filename: str,
) -> AnswerResult:
    """Run the full question→answer pipeline and return an AnswerResult.

    This is the single entry point called by app.py. All exceptions are
    caught here and returned in AnswerResult.error — the Streamlit UI
    must never see a Python traceback.

    Args:
        question:   The user's plain-English question.
        schema_str: Schema context string from schema_extractor.
        conn:       Live DuckDB connection from sql_executor.load_dataframe(),
                    stored in Streamlit session_state between questions.
        filename:   Original uploaded filename for source citation.

    Returns:
        An AnswerResult with all fields populated. On failure, .error
        contains a user-friendly message and all other fields are empty/None.
    """
    if not question or not question.strip():
        return AnswerResult(error="Please enter a question.")

    # ── Step 1: Generate SQL ───────────────────────────────────────────────
    try:
        sql = generate_sql(question, schema_str)
    except SQLGenerationError as exc:
        logger.error("SQL generation failed: %s", exc)
        return AnswerResult(error=str(exc))

    # ── Step 1b: Handle unanswerable questions ─────────────────────────────
    if sql == CANNOT_ANSWER_SENTINEL:
        return AnswerResult(
            cannot_answer=True,
            error=(
                "This question can't be answered from the available data. "
                "Try rephrasing or ask about a column that exists in the file."
            ),
        )

    # ── Step 2: Safety check ───────────────────────────────────────────────
    if not is_safe_sql(sql):
        logger.warning("Blocked unsafe SQL: %s", sql[:120])
        return AnswerResult(
            sql=sql,
            error="The generated query contained unsafe operations and was blocked.",
        )

    # ── Step 3: Execute query ──────────────────────────────────────────────
    try:
        result_df = execute_query(conn, sql)
    except ExecutionError as exc:
        logger.error("Query execution failed: %s", exc)
        return AnswerResult(sql=sql, error=str(exc))

    if result_df.empty:
        return AnswerResult(
            sql=sql,
            error="The query returned no rows. Try a broader question.",
        )

    # ── Step 4: Generate plain-English answer ─────────────────────────────
    try:
        answer = generate_answer(question, result_df, filename)
    except AnswerGenerationError as exc:
        logger.error("Answer generation failed: %s", exc)
        # Still return the SQL and data even if answer fails
        return AnswerResult(
            sql=sql,
            row_count=len(result_df),
            col_count=len(result_df.columns),
            error=str(exc),
        )

    # ── Step 5: Render chart ───────────────────────────────────────────────
    chart = select_and_render(result_df, question)

    source_info = f"{filename} · {len(result_df)} rows analysed"

    return AnswerResult(
        answer=answer,
        sql=sql,
        chart=chart,
        row_count=len(result_df),
        col_count=len(result_df.columns),
        source_info=source_info,
    )