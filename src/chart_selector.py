"""
chart_selector.py — Rule-based chart type selection and Plotly rendering.

No LLM is used here — chart type is chosen deterministically from the
shape and column types of the result DataFrame. This keeps it fast,
predictable, and fully testable without mocking.

Selection rules:
  1 row, 1 numeric col           → None  (caller shows a metric card)
  date col + numeric col         → line chart
  text col + numeric col         → bar chart (or pie if % shape detected)
  multiple numeric, no text      → None  (UI shows raw table)
  anything else                  → None  (UI shows raw table)

All charts share one light, neutral theme and the validated CHART_COLORS
palette so they read as one system.

Returns a Plotly Figure or None. Never raises — on any unexpected input
it logs a warning and returns None so the UI can fall back gracefully.
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.config import CHART_COLORS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception (internal only — never raised externally)
# ---------------------------------------------------------------------------


class ChartError(Exception):
    """Internal error during chart rendering. Caught internally; never surfaced."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def select_and_render(
    result_df: pd.DataFrame,
    question: str = "",
) -> Optional[go.Figure]:
    """Choose a chart type and return a styled Plotly Figure, or None.

    Inspects the shape and column dtypes of result_df and picks the most
    appropriate chart. Returns None when no chart is appropriate — the
    UI should handle None by showing a plain table or a big metric card.

    Args:
        result_df: The small DataFrame returned by sql_executor.execute_query().
        question:  The user's original question (used only for chart titles).

    Returns:
        A styled Plotly Figure, or None.
    """
    if result_df is None or result_df.empty:
        logger.debug("chart_selector: empty DataFrame — returning None")
        return None

    try:
        return _choose_chart(result_df, question)
    except Exception as exc:
        # Never crash the UI — log and return None
        logger.warning("chart_selector: unexpected error — %s", exc)
        return None


# ---------------------------------------------------------------------------
# Internal routing
# ---------------------------------------------------------------------------


def _choose_chart(df: pd.DataFrame, question: str) -> Optional[go.Figure]:
    """Apply selection rules and delegate to the appropriate chart renderer."""
    rows, cols = df.shape

    numeric_cols = _numeric_columns(df)
    date_cols = _date_columns(df)
    text_cols = _text_columns(df)

    # Rule 1 — single value → metric card (None, UI handles display)
    if rows == 1 and cols == 1 and len(numeric_cols) == 1:
        logger.debug("chart_selector: single metric — returning None")
        return None

    # Rule 1b — any single row → no chart; one bar or point says nothing the
    # number doesn't (the UI shows metric tiles instead)
    if rows == 1:
        logger.debug("chart_selector: single row — returning None")
        return None

    # Rule 2 — date + numeric → line chart (trend over time)
    # Require at least 2 rows — a single point produces a meaningless dot.
    if date_cols and numeric_cols and rows > 1:
        logger.debug("chart_selector: date+numeric → line chart")
        return _line_chart(df, date_cols[0], numeric_cols[0], question)

    # Rule 3 — text + numeric → bar chart (most common case)
    if text_cols and numeric_cols:
        # Rule 4 — few rows with values that look like percentages → pie chart
        if 2 <= rows <= 6 and _looks_like_percentages(df[numeric_cols[0]]):
            logger.debug("chart_selector: text+pct+few rows → pie chart")
            return _pie_chart(df, text_cols[0], numeric_cols[0], question)
        logger.debug("chart_selector: text+numeric → bar chart")
        return _bar_chart(df, text_cols[0], numeric_cols[0], question)

    # Rule 5 — multiple numeric, no text → return None (show table)
    if len(numeric_cols) >= 2 and not text_cols:
        logger.debug("chart_selector: multi-numeric — returning None (show table)")
        return None

    # Fallback — return None, UI shows the raw DataFrame as a table
    logger.debug("chart_selector: no rule matched — returning None")
    return None


# ---------------------------------------------------------------------------
# Shared chart theme — applied to every chart
# ---------------------------------------------------------------------------


def _apply_theme(fig: go.Figure, title: str = "") -> go.Figure:
    """Apply the shared light theme: transparent surface, quiet grid, ink text."""
    axis = dict(gridcolor="#ececf0", zerolinecolor="#d4d4d8", linecolor="#d4d4d8", showgrid=True)
    fig.update_layout(
        font_family="Inter, system-ui, sans-serif",
        font_color="#3f3f46",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        title_text=title if title else None,
        title_font_size=14,
        title_font_color="#18181b",
        margin=dict(l=12, r=12, t=40 if title else 12, b=12),
        xaxis=axis,
        yaxis=axis,
        showlegend=False,
        hoverlabel=dict(bgcolor="#ffffff", bordercolor="#e4e4e7", font_color="#18181b"),
    )
    return fig


# ---------------------------------------------------------------------------
# Chart renderers
# ---------------------------------------------------------------------------


def _bar_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
) -> go.Figure:
    """Render a horizontal bar chart sorted by value descending.

    Horizontal orientation makes long category labels readable.
    """
    sorted_df = df.sort_values(y_col, ascending=True)
    fig = px.bar(
        sorted_df,
        x=y_col,
        y=x_col,
        orientation="h",
        labels={y_col: _prettify(y_col), x_col: _prettify(x_col)},
        color_discrete_sequence=CHART_COLORS[:1],  # one series, one colour
    )
    fig = _apply_theme(fig, title)
    fig.update_traces(marker_line_width=0)
    # Hide the colour axis scale bar — not needed for single-colour bars
    fig.update_coloraxes(showscale=False)
    return fig


def _line_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
) -> go.Figure:
    """Render a line chart with markers, sorted by date ascending."""
    sorted_df = df.sort_values(x_col)
    fig = px.line(
        sorted_df,
        x=x_col,
        y=y_col,
        labels={y_col: _prettify(y_col), x_col: _prettify(x_col)},
        markers=True,
        color_discrete_sequence=CHART_COLORS[:1],
    )
    fig = _apply_theme(fig, title)
    fig.update_traces(line_width=2, marker_size=8)
    return fig


def _pie_chart(
    df: pd.DataFrame,
    names_col: str,
    values_col: str,
    title: str,
) -> go.Figure:
    """Render a pie chart for percentage-like breakdowns."""
    fig = px.pie(
        df,
        names=names_col,
        values=values_col,
        color_discrete_sequence=CHART_COLORS,
    )
    fig = _apply_theme(fig, title)
    fig.update_traces(marker_line_color="#ffffff", marker_line_width=2)
    # Show legend for pie charts — important for readability
    fig.update_layout(showlegend=True)
    return fig


# ---------------------------------------------------------------------------
# Column type helpers
# ---------------------------------------------------------------------------


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    """Return column names with numeric (int or float) dtype."""
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def _date_columns(df: pd.DataFrame) -> list[str]:
    """Return column names with datetime dtype."""
    return [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]


def _text_columns(df: pd.DataFrame) -> list[str]:
    """Return column names with object (string) dtype, excluding numeric/date."""
    return [
        c
        for c in df.columns
        if pd.api.types.is_object_dtype(df[c])
        or pd.api.types.is_string_dtype(df[c])
    ]


def _looks_like_percentages(series: pd.Series) -> bool:
    """Return True if values are plausibly percentage-like (0–100 range, sum ~100)."""
    if series.empty:
        return False
    total = series.sum()
    all_in_range = ((series >= 0) & (series <= 100)).all()
    sum_near_100 = 90 <= total <= 110
    return bool(all_in_range and sum_near_100)


def _prettify(col_name: str) -> str:
    """Convert snake_case column name to Title Case for chart labels."""
    return col_name.replace("_", " ").title()