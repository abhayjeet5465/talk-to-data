"""
orchestrator.py — Pipeline controller for Talk to Data.

Wires all pipeline stages into a single callable: run_query().

Flow:
  1. generate_sql()           — schema + question → SQL (Chain-of-Thought)
  2. is_safe_sql()            — AST + blocklist safety check
  3. execute_query()          — DuckDB execution
     └─ on failure: one self-correction attempt via generate_sql()
  4. generate_answer_payload() — result rows + question → plain English + XAI data
  5. select_and_render()      — result DataFrame → Plotly figure

Returns an AnswerResult dataclass. Never raises — all errors are
captured in AnswerResult.error so the Streamlit UI can display them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import duckdb
import pandas as pd
import plotly.graph_objects as go

from src.answer_generator import AnswerGenerationError, generate_answer, generate_answer_payload
from src.chart_selector import select_and_render
from src.sql_executor import ExecutionError, SafetyError, execute_query, is_safe_sql
from src.sql_generator import (
    CANNOT_ANSWER_SENTINEL,
    AmbiguousQuestionError,
    SQLGenerationError,
    generate_sql,
)

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
        answer:              Plain-English answer from the LLM.
        sql:                 The SQL query that was executed.
        chart:               Plotly Figure if a chart was rendered, else None.
        row_count:           Number of rows in the query result.
        col_count:           Number of columns in the query result.
        source_info:         Human-readable source line, e.g. "sales.csv · 24 rows".
        error:               User-friendly error message if anything failed.
        cannot_answer:       True if the LLM said the question is unanswerable.
        columns_used:        List of columns that drove the answer (for XAI expander).
        assumptions:         Any date/definition assumptions the LLM made.
        self_corrected:      True if the SQL failed and was auto-corrected.
        is_ambiguous:        True if the question was too vague for a reliable answer.
        clarification_needed: The clarifying question to show the user when ambiguous.
    """

    answer: str = ""
    sql: str = ""
    chart: Optional[go.Figure] = None
    row_count: int = 0
    col_count: int = 0
    source_info: str = ""
    error: str = ""
    cannot_answer: bool = False
    # XAI metadata — populated from the structured LLM response
    columns_used: list = field(default_factory=list)
    assumptions: str = ""
    # Self-correction — True if the initial SQL failed and was auto-fixed
    self_corrected: bool = False
    # Ambiguity — True if the question needed clarification
    is_ambiguous: bool = False
    clarification_needed: str = ""


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

    sql = ""
    self_corrected = False

    # ── Step 1: Generate SQL (Chain-of-Thought) ────────────────────────────
    try:
        sql = generate_sql(question, schema_str)
    except AmbiguousQuestionError as exc:
        # The question was too vague — ask the user to clarify
        return AnswerResult(is_ambiguous=True, clarification_needed=str(exc))
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

    # ── Step 3: Execute query — with one self-correction attempt ──────────
    try:
        result_df = execute_query(conn, sql)
    except ExecutionError as first_error:
        # The SQL had a runtime error (e.g. hallucinated column name).
        # Try once more: ask the LLM to fix the SQL using the error message.
        logger.warning("Query failed — attempting self-correction: %s", first_error)
        correction_question = (
            f"{question}\n\n"
            f"[CORRECTION] The previous SQL failed with this error:\n{first_error}\n"
            f"Previous SQL:\n{sql}\n\n"
            "Please write corrected SQL that fixes this error."
        )
        try:
            corrected_sql = generate_sql(correction_question, schema_str)
            if corrected_sql != CANNOT_ANSWER_SENTINEL and is_safe_sql(corrected_sql):
                result_df = execute_query(conn, corrected_sql)
                sql = corrected_sql
                self_corrected = True
                logger.info("Self-correction succeeded")
            else:
                return AnswerResult(sql=sql, error=str(first_error))
        except Exception:
            # Correction also failed — return the original error
            return AnswerResult(sql=sql, error=str(first_error))

    if result_df.empty:
        return AnswerResult(
            sql=sql,
            error="The query returned no rows. Try a broader question.",
        )

    # ── Step 4: Generate plain-English answer (with XAI metadata) ─────────
    try:
        payload = generate_answer_payload(question, result_df, filename)
    except AnswerGenerationError as exc:
        logger.error("Answer generation failed: %s", exc)
        # Return the SQL and data even if the answer step fails
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
        answer=payload.answer,
        sql=sql,
        chart=chart,
        row_count=len(result_df),
        col_count=len(result_df.columns),
        source_info=source_info,
        self_corrected=self_corrected,
        columns_used=list(payload.columns_used),
        assumptions=payload.assumptions,
    )