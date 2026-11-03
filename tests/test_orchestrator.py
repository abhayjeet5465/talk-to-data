from __future__ import annotations

"""
tests/test_orchestrator.py — Unit tests for src/orchestrator.py

All LLM calls and DuckDB interactions are mocked so tests run instantly
with no API keys needed.

Run with:
    pytest tests/test_orchestrator.py -v
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.orchestrator import AnswerResult, run_query
from src.sql_generator import CANNOT_ANSWER_SENTINEL
from src.sql_executor import load_dataframe
from src.answer_generator import AnswerPayload

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

QUESTION = "Which region had the highest revenue?"
SCHEMA_STR = "File: sales.csv | Rows: 3\nregion (text), revenue (float)"
FILENAME = "sales.csv"
GOOD_SQL = "SELECT region, revenue FROM data ORDER BY revenue DESC LIMIT 1"
GOOD_ANSWER = "North had the highest revenue at 10,000. (Source: sales.csv, 1 rows analysed)"


@pytest.fixture()
def conn():
    """Real in-memory DuckDB connection with minimal sample data."""
    df = pd.DataFrame({"region": ["North", "South"], "revenue": [10000.0, 8000.0]})
    return load_dataframe(df)


# ---------------------------------------------------------------------------
# Happy path — full pipeline succeeds
# ---------------------------------------------------------------------------


def test_run_query_returns_answer_result(conn):
    good_payload = AnswerPayload(answer=GOOD_ANSWER, columns_used=["region", "revenue"], assumptions="")
    with patch("src.orchestrator.generate_sql", return_value=GOOD_SQL):
        with patch("src.orchestrator.generate_answer_payload", return_value=good_payload):
            result = run_query(QUESTION, SCHEMA_STR, conn, FILENAME)

    assert isinstance(result, AnswerResult)
    assert result.answer == GOOD_ANSWER
    assert result.sql == GOOD_SQL
    assert result.error == ""


def test_run_query_populates_source_info(conn):
    good_payload = AnswerPayload(answer=GOOD_ANSWER, columns_used=[], assumptions="")
    with patch("src.orchestrator.generate_sql", return_value=GOOD_SQL):
        with patch("src.orchestrator.generate_answer_payload", return_value=good_payload):
            result = run_query(QUESTION, SCHEMA_STR, conn, FILENAME)

    assert FILENAME in result.source_info
    assert "1 row analysed" in result.source_info


def test_run_query_populates_row_and_col_counts(conn):
    good_payload = AnswerPayload(answer=GOOD_ANSWER, columns_used=[], assumptions="")
    with patch("src.orchestrator.generate_sql", return_value=GOOD_SQL):
        with patch("src.orchestrator.generate_answer_payload", return_value=good_payload):
            result = run_query(QUESTION, SCHEMA_STR, conn, FILENAME)

    assert result.row_count >= 1
    assert result.col_count >= 1


# ---------------------------------------------------------------------------
# Empty question
# ---------------------------------------------------------------------------


def test_empty_question_returns_error(conn):
    result = run_query("", SCHEMA_STR, conn, FILENAME)
    assert result.error != ""
    assert result.answer == ""


def test_whitespace_question_returns_error(conn):
    result = run_query("   ", SCHEMA_STR, conn, FILENAME)
    assert result.error != ""


# ---------------------------------------------------------------------------
# SQL generation failure
# ---------------------------------------------------------------------------


def test_sql_generation_error_returns_error_result(conn):
    from src.sql_generator import SQLGenerationError

    with patch("src.orchestrator.generate_sql", side_effect=SQLGenerationError("LLM down")):
        result = run_query(QUESTION, SCHEMA_STR, conn, FILENAME)

    assert result.error != ""
    assert result.answer == ""


def test_cannot_answer_sentinel_sets_flag(conn):
    with patch("src.orchestrator.generate_sql", return_value=CANNOT_ANSWER_SENTINEL):
        result = run_query(QUESTION, SCHEMA_STR, conn, FILENAME)

    assert result.cannot_answer is True
    assert result.error != ""


# ---------------------------------------------------------------------------
# Unsafe SQL blocked
# ---------------------------------------------------------------------------


def test_unsafe_sql_is_blocked(conn):
    with patch("src.orchestrator.generate_sql", return_value="DROP TABLE data"):
        result = run_query(QUESTION, SCHEMA_STR, conn, FILENAME)

    assert result.error != ""
    assert "blocked" in result.error.lower() or "unsafe" in result.error.lower()


# ---------------------------------------------------------------------------
# Query execution failure
# ---------------------------------------------------------------------------


def test_execution_error_returns_error_result(conn):
    from src.sql_executor import ExecutionError

    with patch("src.orchestrator.generate_sql", return_value=GOOD_SQL):
        with patch("src.orchestrator.execute_query", side_effect=ExecutionError("bad sql")):
            result = run_query(QUESTION, SCHEMA_STR, conn, FILENAME)

    assert result.error != ""
    assert result.sql == GOOD_SQL   # SQL should still be shown


# ---------------------------------------------------------------------------
# Answer generation failure — partial result still returned
# ---------------------------------------------------------------------------


def test_answer_generation_error_returns_sql_in_result(conn):
    from src.answer_generator import AnswerGenerationError

    with patch("src.orchestrator.generate_sql", return_value=GOOD_SQL):
        with patch(
            "src.orchestrator.generate_answer_payload",
            side_effect=AnswerGenerationError("LLM down"),
        ):
            result = run_query(QUESTION, SCHEMA_STR, conn, FILENAME)

    assert result.sql == GOOD_SQL
    assert result.error != ""


# ---------------------------------------------------------------------------
# AnswerResult dataclass defaults
# ---------------------------------------------------------------------------


def test_answer_result_default_values():
    r = AnswerResult()
    assert r.answer == ""
    assert r.sql == ""
    assert r.chart is None
    assert r.row_count == 0
    assert r.col_count == 0
    assert r.source_info == ""
    assert r.error == ""
    assert r.cannot_answer is False

# ---------------------------------------------------------------------------
# Chat memory — earlier turns reach SQL generation, not the answer
# ---------------------------------------------------------------------------


def test_context_is_sent_to_sql_generation_only(conn):
    payload = AnswerPayload(answer=GOOD_ANSWER, columns_used=["region"], assumptions="")
    context = "User: total revenue by region?"
    with patch("src.orchestrator.generate_sql", return_value=GOOD_SQL) as gen, patch(
        "src.orchestrator.generate_answer_payload", return_value=payload
    ) as answer:
        run_query("what about the top one?", SCHEMA_STR, conn, FILENAME, context=context)

    sent = gen.call_args.args[0]
    assert sent.startswith(context) and sent.endswith("Current question: what about the top one?")
    assert answer.call_args.args[0] == "what about the top one?"


def test_no_context_leaves_question_unchanged(conn):
    with patch("src.orchestrator.generate_sql", return_value=CANNOT_ANSWER_SENTINEL) as gen:
        run_query(QUESTION, SCHEMA_STR, conn, FILENAME)
    assert gen.call_args.args[0] == QUESTION
