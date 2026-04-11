from __future__ import annotations

"""
tests/test_sql_pipeline.py — Unit tests for Stage 4 SQL pipeline.

Covers:
  - sql_generator.py  (generate_sql, _clean_sql)
  - sql_executor.py   (load_dataframe, is_safe_sql, execute_query)
  - answer_generator.py (generate_answer)

No real LLM calls are made — all LLM interactions are mocked.
No real files needed — DataFrames are built inline.

Run with:
    pytest tests/test_sql_pipeline.py -v
"""

import io
from unittest.mock import patch

import pandas as pd
import pytest

# ── modules under test ────────────────────────────────────────────────────
from src.sql_generator import (
    CANNOT_ANSWER_SENTINEL,
    SQLGenerationError,
    _clean_sql,
    generate_sql,
)
from src.sql_executor import (
    ExecutionError,
    SafetyError,
    execute_query,
    is_safe_sql,
    load_dataframe,
)
from src.answer_generator import AnswerGenerationError, generate_answer


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture()
def sample_df() -> pd.DataFrame:
    """Small DataFrame that mimics an uploaded CSV."""
    return pd.DataFrame(
        {
            "region": ["North", "South", "East"],
            "revenue": [10000.0, 8000.0, 12000.0],
            "units": [100, 80, 120],
        }
    )


@pytest.fixture()
def loaded_conn(sample_df):
    """DuckDB connection with sample_df already registered."""
    return load_dataframe(sample_df)


SCHEMA_STR = (
    "File: sales.csv | Rows: 3 | Columns: 3\n"
    "region (text), revenue (float), units (integer)\n"
    "Sample rows:\n"
    "North | 10000.0 | 100\n"
    "South | 8000.0  | 80\n"
)

QUESTION = "Which region had the highest revenue?"


# ===========================================================================
# sql_generator — _clean_sql helper
# ===========================================================================


def test_clean_sql_strips_backtick_fence():
    raw = "```sql\nSELECT * FROM data\n```"
    assert _clean_sql(raw) == "SELECT * FROM data"


def test_clean_sql_strips_plain_fence():
    raw = "```\nSELECT 1\n```"
    assert _clean_sql(raw) == "SELECT 1"


def test_clean_sql_passes_through_clean_sql():
    raw = "SELECT region FROM data ORDER BY revenue DESC"
    assert _clean_sql(raw) == raw


def test_clean_sql_passes_through_sentinel():
    assert _clean_sql("CANNOT_ANSWER") == CANNOT_ANSWER_SENTINEL


def test_clean_sql_strips_whitespace():
    raw = "  SELECT 1  \n"
    assert _clean_sql(raw) == "SELECT 1"


# ===========================================================================
# sql_generator — generate_sql
# ===========================================================================


def test_generate_sql_returns_string_on_success():
    with patch(
        "src.sql_generator.call_llm",
        return_value="SELECT region FROM data ORDER BY revenue DESC LIMIT 1",
    ):
        result = generate_sql(QUESTION, SCHEMA_STR)
    assert isinstance(result, str)
    assert "SELECT" in result.upper()


def test_generate_sql_returns_sentinel_when_llm_says_cannot_answer():
    with patch("src.sql_generator.call_llm", return_value="CANNOT_ANSWER"):
        result = generate_sql(QUESTION, SCHEMA_STR)
    assert result == CANNOT_ANSWER_SENTINEL


def test_generate_sql_raises_on_empty_question():
    with pytest.raises(SQLGenerationError):
        generate_sql("", SCHEMA_STR)


def test_generate_sql_raises_on_empty_schema():
    with pytest.raises(SQLGenerationError):
        generate_sql(QUESTION, "")


def test_generate_sql_raises_on_llm_failure():
    from src.llm_client import LLMError

    with patch("src.sql_generator.call_llm", side_effect=LLMError("all providers down")):
        with pytest.raises(SQLGenerationError):
            generate_sql(QUESTION, SCHEMA_STR)


def test_generate_sql_strips_markdown_fence_from_llm_output():
    """Defensively handles LLMs that wrap SQL in markdown fences."""
    with patch(
        "src.sql_generator.call_llm",
        return_value="```sql\nSELECT * FROM data\n```",
    ):
        result = generate_sql(QUESTION, SCHEMA_STR)
    assert not result.startswith("```")


# ===========================================================================
# sql_executor — load_dataframe
# ===========================================================================


def test_load_dataframe_returns_connection(sample_df):
    import duckdb

    conn = load_dataframe(sample_df)
    assert isinstance(conn, duckdb.DuckDBPyConnection)


def test_load_dataframe_table_is_queryable(sample_df):
    conn = load_dataframe(sample_df)
    result = conn.execute("SELECT COUNT(*) AS n FROM data").df()
    assert result["n"].iloc[0] == 3


def test_load_dataframe_raises_on_empty_df():
    with pytest.raises(ExecutionError):
        load_dataframe(pd.DataFrame())


# ===========================================================================
# sql_executor — is_safe_sql
# ===========================================================================


def test_is_safe_sql_allows_select():
    assert is_safe_sql("SELECT region, SUM(revenue) FROM data GROUP BY region") is True


def test_is_safe_sql_blocks_drop():
    assert is_safe_sql("DROP TABLE data") is False


def test_is_safe_sql_blocks_delete():
    assert is_safe_sql("DELETE FROM data WHERE region = 'North'") is False


def test_is_safe_sql_blocks_insert():
    assert is_safe_sql("INSERT INTO data VALUES (1, 2, 3)") is False


def test_is_safe_sql_blocks_update():
    assert is_safe_sql("UPDATE data SET revenue = 0") is False


def test_is_safe_sql_blocks_truncate():
    assert is_safe_sql("TRUNCATE TABLE data") is False


def test_is_safe_sql_case_insensitive():
    assert is_safe_sql("drop table data") is False


# ===========================================================================
# sql_executor — execute_query
# ===========================================================================


def test_execute_query_returns_dataframe(loaded_conn):
    result = execute_query(loaded_conn, "SELECT * FROM data ORDER BY revenue")
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 3


def test_execute_query_aggregation(loaded_conn):
    result = execute_query(
        loaded_conn,
        "SELECT SUM(revenue) AS total FROM data",
    )
    assert result["total"].iloc[0] == pytest.approx(30000.0)


def test_execute_query_raises_execution_error_on_bad_sql(loaded_conn):
    with pytest.raises(ExecutionError):
        execute_query(loaded_conn, "SELECT nonexistent_column FROM data")


def test_execute_query_empty_result_is_not_an_error(loaded_conn):
    """A query that matches zero rows returns empty DataFrame, not an error."""
    result = execute_query(
        loaded_conn,
        "SELECT * FROM data WHERE revenue > 999999",
    )
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0


# ===========================================================================
# answer_generator — generate_answer
# ===========================================================================

RESULT_DF = pd.DataFrame({"region": ["North"], "revenue": [10000.0]})
FILENAME = "sales.csv"
GOOD_ANSWER = "North had the highest revenue at 10,000. (Source: sales.csv, 1 rows analysed)"


def test_generate_answer_returns_string():
    with patch("src.answer_generator.call_llm", return_value=GOOD_ANSWER):
        result = generate_answer(QUESTION, RESULT_DF, FILENAME)
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_answer_raises_on_empty_question():
    with pytest.raises(AnswerGenerationError):
        generate_answer("", RESULT_DF, FILENAME)


def test_generate_answer_raises_on_none_dataframe():
    with pytest.raises(AnswerGenerationError):
        generate_answer(QUESTION, None, FILENAME)


def test_generate_answer_raises_on_empty_filename():
    with pytest.raises(AnswerGenerationError):
        generate_answer(QUESTION, RESULT_DF, "")


def test_generate_answer_raises_on_llm_failure():
    from src.llm_client import LLMError

    with patch(
        "src.answer_generator.call_llm",
        side_effect=LLMError("all providers down"),
    ):
        with pytest.raises(AnswerGenerationError):
            generate_answer(QUESTION, RESULT_DF, FILENAME)


def test_generate_answer_passes_filename_to_llm():
    """The filename must appear in the message sent to the LLM."""
    captured = {}

    def _capture(system_prompt, user_message):
        captured["user_message"] = user_message
        return GOOD_ANSWER

    with patch("src.answer_generator.call_llm", side_effect=_capture):
        generate_answer(QUESTION, RESULT_DF, FILENAME)

    assert FILENAME in captured["user_message"]