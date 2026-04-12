"""
sql_generator.py — LLM Call #1: natural language → DuckDB SQL.

Sends the schema string and the user's question to the LLM and returns
a single SELECT statement that DuckDB can execute against the in-memory
table named 'data'.

Key improvements over the basic version:
  - Chain-of-Thought (CoT) prompt: forces the model to reason step-by-step
    before writing SQL, which significantly improves accuracy.
  - Today's date is injected so the model can resolve "last month" correctly.
  - DuckDB-specific functions are explicitly requested (DATE_TRUNC, GROUP BY ALL).
  - Ambiguous questions trigger a JSON sentinel instead of a guess.
  - XML tags (<logic>/<sql>) isolate the final SQL from the reasoning trace.

Privacy: the full dataset never leaves this module — only the schema string
(column names, types, and sample values) is sent to the LLM API.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Final

from src.ambiguity_detector import parse_ambiguity
from src.config import DUCKDB_TABLE_NAME
from src.llm_client import LLMError, call_llm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class SQLGenerationError(Exception):
    """Raised when the LLM cannot produce a usable SQL query.

    Always carries a user-friendly message safe to show in the UI.
    """


class AmbiguousQuestionError(Exception):
    """Raised when the question is too vague to generate a reliable SQL query.

    The message contains the clarifying question to show to the user.
    Example: "Please specify what metric defines 'top' products."
    """


# ---------------------------------------------------------------------------
# Sentinel returned by the LLM when the question cannot be answered
# ---------------------------------------------------------------------------

CANNOT_ANSWER_SENTINEL: Final[str] = "CANNOT_ANSWER"

# ---------------------------------------------------------------------------
# System prompt — Chain-of-Thought version
#
# The model is asked to output TWO XML-tagged sections:
#   <logic>  — its step-by-step reasoning (discarded server-side)
#   <sql>    — the final SQL query (or a sentinel / ambiguity JSON)
#
# We discard the <logic> block so users only see a clean SQL output.
# The reasoning step dramatically improves accuracy on open-weight models.
# ---------------------------------------------------------------------------

SQL_SYSTEM_PROMPT: Final[str] = f"""You are an expert DuckDB SQL analyst.
The table name is always: {DUCKDB_TABLE_NAME}

Your job is to convert the user's question into a single DuckDB SELECT query.

Output your response in this EXACT format — always include both tags:

<logic>
a) What is the question asking? (change / comparison / breakdown / summary)
b) Which columns do I need from the schema?
c) What filters or time ranges apply? Use today's date to resolve relative terms like "last month" or "this week".
d) What aggregation or calculation is needed?
</logic>
<sql>
YOUR SQL QUERY HERE
</sql>

Rules for the SQL inside <sql> tags:
1. Only SELECT statements — never INSERT, UPDATE, DELETE, DROP, ALTER, or CREATE.
2. Use DuckDB syntax:
   - DATE_TRUNC('month', col) for time bucketing
   - GROUP BY ALL to group by all non-aggregated columns
   - SUM(col) FILTER (WHERE condition) for conditional aggregation
   - CTEs (WITH ...) for period-over-period comparisons
   - SUM(col) OVER () as a window function for % of total breakdowns
3. Column names must match the schema exactly — never invent a column.
4. Add ORDER BY when returning multiple rows.
5. Limit results to 500 rows with LIMIT 500.
6. If the question cannot be answered from the schema, put inside <sql>:
   CANNOT_ANSWER
7. If the question is ambiguous (e.g. "top products" — top by what metric?),
   put this JSON inside <sql> instead of SQL:
   {{"status": "ambiguous", "clarification_needed": "Your specific clarifying question here."}}
"""


# Multi-table prompt — used when 2 or 3 files are loaded.
# Single-file prompt above is untouched.
SQL_SYSTEM_PROMPT_MULTI: Final[str] = """You are an expert DuckDB SQL analyst working with MULTIPLE tables.

The available tables and their columns are described in the schema below.
Do NOT invent table names or column names — use only what is listed.

Output your response in this EXACT format:

<logic>
a) Which tables does this question need?
b) What is the JOIN key between them? (use the SYSTEM INFERRED JOIN KEYS if provided)
c) What filters, aggregations, or calculations are needed?
</logic>
<sql>
YOUR SQL QUERY HERE
</sql>

Rules for the SQL inside <sql> tags:
1. Only SELECT statements — never INSERT, UPDATE, DELETE, DROP, ALTER, or CREATE.
2. Always alias every table (e.g. FROM sales s LEFT JOIN catalog c ON s.product_id = c.product_id).
3. Default to LEFT JOIN — never use INNER JOIN unless you are certain both tables are complete.
4. Column names must match the schema exactly.
5. Add ORDER BY when returning multiple rows.
6. Limit results to 500 rows with LIMIT 500.
7. If the question cannot be answered from the schema, put inside <sql>:
   CANNOT_ANSWER
8. If the question is ambiguous, put this JSON inside <sql> instead of SQL:
   {"status": "ambiguous", "clarification_needed": "Your specific clarifying question here."}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_sql(question: str, schema_str: str, multi_table: bool = False) -> str:
    """Convert a natural-language question into a DuckDB SELECT query.

    Injects today's date into the prompt so the model can resolve
    relative time references like "last month" correctly.

    Args:
        question:   The user's plain-English question.
        schema_str: Schema context from schema_extractor (column names,
                    types, sample values). Never contains raw data.

    Returns:
        A DuckDB-compatible SELECT query string, OR the sentinel string
        "CANNOT_ANSWER" if the LLM says the question is unanswerable.

    Raises:
        AmbiguousQuestionError: If the LLM returns an ambiguity JSON.
                                Message contains the clarifying question.
        SQLGenerationError:     If the LLM call fails or returns empty.
    """
    if not question or not question.strip():
        raise SQLGenerationError("Question must not be empty.")
    if not schema_str or not schema_str.strip():
        raise SQLGenerationError("Schema string must not be empty.")

    # Inject today's date so the model resolves "last month" correctly
    today = date.today().isoformat()
    user_message = (
        f"Today's date: {today}\n\n"
        f"Schema:\n{schema_str}\n\n"
        f"Question: {question.strip()}"
    )

    try:
        prompt = SQL_SYSTEM_PROMPT_MULTI if multi_table else SQL_SYSTEM_PROMPT
        raw = call_llm(prompt, user_message)
    except LLMError as exc:
        raise SQLGenerationError(f"Could not generate SQL: {exc}") from exc

    # Extract the SQL from the <sql>...</sql> tags in the CoT response
    sql = _extract_sql_from_cot(raw)

    # Run the cleaned text through markdown fence removal
    sql = _clean_sql(sql)

    if not sql:
        raise SQLGenerationError(
            "The AI returned an empty response. Please rephrase your question."
        )

    # Check for the ambiguity sentinel (a JSON object instead of SQL)
    is_ambiguous, clarification = parse_ambiguity(sql)
    if is_ambiguous:
        raise AmbiguousQuestionError(clarification)

    logger.debug("Generated SQL: %s", sql[:120])
    return sql


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_sql_from_cot(raw: str) -> str:
    """Extract just the SQL from a Chain-of-Thought response.

    The model is instructed to wrap its SQL in <sql>...</sql> tags.
    If the tags are found, only the content inside them is returned.
    If no tags are found (e.g. older prompts), the whole string is returned
    so this function is backwards-compatible.

    Args:
        raw: The full raw response from the LLM.

    Returns:
        The SQL string, without any <logic> reasoning prefix.
    """
    match = re.search(r"<sql>(.*?)</sql>", raw, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Fallback: no XML tags found — return the whole response
    return raw.strip()


def _clean_sql(raw: str) -> str:
    """Strip markdown fences and extra whitespace from a SQL string.

    Despite the system prompt saying "no backticks", models sometimes
    wrap output in ```sql ... ``` fences. This removes them defensively.

    Args:
        raw: The raw SQL string (possibly with markdown fences).

    Returns:
        Cleaned SQL string, or CANNOT_ANSWER_SENTINEL if that was returned.
    """
    text = raw.strip()

    # Pass through the CANNOT_ANSWER sentinel unchanged
    if text.upper() == CANNOT_ANSWER_SENTINEL:
        return CANNOT_ANSWER_SENTINEL

    # Remove markdown code fences (```sql ... ``` or ``` ... ```)
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:] if lines[0].startswith("```") else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    return text