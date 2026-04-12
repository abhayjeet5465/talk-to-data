"""
sql_executor.py — Stage 4.
Validates SQL safety and executes against in-memory DuckDB table.
"""
from __future__ import annotations

"""
src/sql_executor.py — SQL safety validation and DuckDB execution.

Two responsibilities:
  1. Safety check: reject any SQL containing mutating keywords before
     it ever reaches DuckDB (blocklist from config.SQL_BLOCKLIST).
  2. Execution: run the validated SELECT query against the in-memory
     DuckDB connection and return results as a Pandas DataFrame.

The DuckDB connection is created once per file upload and stored in
Streamlit session_state by the caller (orchestrator / app.py).
See REFERENCE.md §8.3 for the correct DuckDB + Pandas pattern.
"""

import logging

import duckdb
import pandas as pd

from src.config import DUCKDB_TABLE_NAME, SQL_BLOCKLIST

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class SafetyError(Exception):
    """Raised when the SQL query contains a blocked keyword.

    Always carries a user-friendly message safe to show in the UI.
    """


class ExecutionError(Exception):
    """Raised when DuckDB fails to execute an otherwise safe query.

    Always carries a user-friendly message safe to show in the UI.
    """


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_dataframe(df: pd.DataFrame) -> duckdb.DuckDBPyConnection:
    """Load a Pandas DataFrame into a fresh in-memory DuckDB connection.

    Creates a new DuckDB connection and registers the DataFrame as a
    virtual table named 'data' (value from config.DUCKDB_TABLE_NAME).
    The connection should be stored in Streamlit session_state so it
    persists across questions without reloading the file.

    Args:
        df: The full dataset returned by schema_extractor.extract_schema().

    Returns:
        A live duckdb.DuckDBPyConnection with the DataFrame registered
        as table 'data'.

    Raises:
        ExecutionError: If the DataFrame cannot be registered (e.g. empty).
    """
    if df is None or df.empty:
        raise ExecutionError("Cannot load an empty DataFrame into DuckDB.")

    try:
        conn = duckdb.connect()           # in-memory, no file on disk
        conn.register(DUCKDB_TABLE_NAME, df)   # register as virtual table
        logger.debug(
            "Registered DataFrame as DuckDB table '%s' (%d rows, %d cols)",
            DUCKDB_TABLE_NAME,
            len(df),
            len(df.columns),
        )
        return conn
    except Exception as exc:
        raise ExecutionError(f"Failed to load data into DuckDB: {exc}") from exc


def load_multiple_dataframes(datasets: dict) -> duckdb.DuckDBPyConnection:
    """Load multiple DataFrames into a single in-memory DuckDB connection.

    Each key in datasets becomes the SQL table name. Used for multi-file mode.

    Args:
        datasets: dict mapping table_name (str) -> schema_info dict.
                  The DataFrame is read from datasets[name]["df"].

    Returns:
        A live DuckDB connection with all DataFrames registered as tables.

    Raises:
        ExecutionError: If any DataFrame cannot be registered.
    """
    try:
        conn = duckdb.connect()
        for table_name, info in datasets.items():
            conn.register(table_name, info["df"])
            logger.debug("Registered '%s' (%d rows)", table_name, len(info["df"]))
        return conn
    except Exception as exc:
        raise ExecutionError(f"Failed to load datasets into DuckDB: {exc}") from exc


def is_safe_sql(sql: str) -> bool:
    """Return True only if the SQL is a safe, read-only SELECT statement.

    Uses two layers of defence:
    1. sqlparse AST check — verifies the root statement type is SELECT.
       This catches mutations like UPDATE, DELETE, DROP even if obfuscated.
    2. Keyword blocklist — secondary fallback for edge cases the AST misses.

    Args:
        sql: The SQL string to check (may be multi-line).

    Returns:
        True if safe (is a SELECT with no blocked keywords).
        False if any check fails — fails closed (deny by default).
    """
    import re
    import sqlparse

    if not sql or not sql.strip():
        return False

    # ── Layer 1: AST structural check ─────────────────────────────────────
    # Parse the SQL and verify the root statement is exactly SELECT.
    try:
        statements = sqlparse.parse(sql.strip())
        if not statements:
            return False
        # Only allow a single statement — reject multi-statement payloads
        if len([s for s in statements if s.get_type()]) > 1:
            logger.warning("Blocked multi-statement SQL")
            return False
        stmt_type = statements[0].get_type()
        if stmt_type != "SELECT":
            logger.warning("Blocked non-SELECT statement type: %s", stmt_type)
            return False
    except Exception as exc:
        # If we cannot parse the SQL, deny it
        logger.warning("sqlparse failed — denying SQL: %s", exc)
        return False

    # ── Layer 2: Keyword blocklist (secondary defence) ────────────────────
    # Catches any blocked keywords that slip through the AST check.
    upper = sql.upper()
    for keyword in SQL_BLOCKLIST:
        # Word-boundary matching so "truncated_at" doesn't block "TRUNCATE"
        pattern = r"(?<![A-Z_])" + re.escape(keyword.upper()) + r"(?![A-Z_])"
        if re.search(pattern, upper):
            logger.warning("Blocked keyword found in SQL: %s", keyword)
            return False

    return True


def execute_query(
    conn: duckdb.DuckDBPyConnection,
    sql: str,
) -> pd.DataFrame:
    """Execute a validated SELECT query and return results as a DataFrame.

    This function assumes is_safe_sql() has already been called by the
    caller (orchestrator). It does NOT re-validate — that separation of
    concerns makes each function easier to test independently.

    Args:
        conn: A live DuckDB connection with the data table registered.
        sql:  A DuckDB-compatible SELECT query string.

    Returns:
        A Pandas DataFrame containing the query results. May be empty
        if the query matches zero rows (not an error).

    Raises:
        ExecutionError: If DuckDB raises any exception during execution.
                        The original DuckDB error is included in the
                        message to help with debugging.
    """
    try:
        result_df: pd.DataFrame = conn.execute(sql).df()
        logger.debug(
            "Query returned %d rows, %d columns",
            len(result_df),
            len(result_df.columns),
        )
        return result_df
    except Exception as exc:
        # Translate DuckDB errors into something the UI can display
        raise ExecutionError(
            f"Query failed: {exc}\n\nSQL attempted:\n{sql}"
        ) from exc