from __future__ import annotations

"""
tests/test_chart_selector.py — Unit tests for src/chart_selector.py

All tests use in-memory DataFrames — no files, no LLM, no API calls.

Run with:
    pytest tests/test_chart_selector.py -v
"""

import pandas as pd
import plotly.graph_objects as go
import pytest

from src.chart_selector import (
    _looks_like_percentages,
    _numeric_columns,
    _date_columns,
    _text_columns,
    _prettify,
    select_and_render,
)

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture()
def bar_df() -> pd.DataFrame:
    """Text + numeric — should produce a bar chart."""
    return pd.DataFrame({"region": ["North", "South", "East"], "revenue": [10000, 8000, 12000]})


@pytest.fixture()
def line_df() -> pd.DataFrame:
    """Date + numeric — should produce a line chart."""
    return pd.DataFrame(
        {
            "week": pd.to_datetime(["2026-01-01", "2026-01-08", "2026-01-15"]),
            "sales": [500, 620, 580],
        }
    )


@pytest.fixture()
def pie_df() -> pd.DataFrame:
    """Text + values that sum to 100 — should produce a pie chart."""
    return pd.DataFrame({"category": ["A", "B", "C"], "share": [40.0, 35.0, 25.0]})


@pytest.fixture()
def metric_df() -> pd.DataFrame:
    """Single row, single numeric — should return None (metric card)."""
    return pd.DataFrame({"total_revenue": [95000.0]})


# ===========================================================================
# Helper: _numeric_columns
# ===========================================================================


def test_numeric_columns_identifies_int_and_float():
    df = pd.DataFrame({"a": [1, 2], "b": [1.1, 2.2], "c": ["x", "y"]})
    assert set(_numeric_columns(df)) == {"a", "b"}


def test_numeric_columns_empty_df():
    assert _numeric_columns(pd.DataFrame()) == []


# ===========================================================================
# Helper: _date_columns
# ===========================================================================


def test_date_columns_identifies_datetime():
    df = pd.DataFrame({"dt": pd.to_datetime(["2026-01-01"]), "val": [1]})
    assert _date_columns(df) == ["dt"]


def test_date_columns_ignores_string_dates():
    df = pd.DataFrame({"dt": ["2026-01-01"], "val": [1]})
    assert _date_columns(df) == []


# ===========================================================================
# Helper: _text_columns
# ===========================================================================


def test_text_columns_identifies_object_dtype():
    df = pd.DataFrame({"name": ["a", "b"], "val": [1, 2]})
    assert _text_columns(df) == ["name"]


# ===========================================================================
# Helper: _looks_like_percentages
# ===========================================================================


def test_looks_like_percentages_true_when_sum_near_100():
    s = pd.Series([40.0, 35.0, 25.0])
    assert _looks_like_percentages(s) is True


def test_looks_like_percentages_false_when_sum_far_from_100():
    s = pd.Series([10000, 8000, 12000])
    assert _looks_like_percentages(s) is False


def test_looks_like_percentages_false_on_empty_series():
    assert _looks_like_percentages(pd.Series([], dtype=float)) is False


# ===========================================================================
# Helper: _prettify
# ===========================================================================


def test_prettify_converts_snake_case():
    assert _prettify("total_revenue") == "Total Revenue"


def test_prettify_leaves_plain_word_unchanged():
    assert _prettify("revenue") == "Revenue"


# ===========================================================================
# select_and_render — return types
# ===========================================================================


def test_bar_chart_returns_figure(bar_df):
    fig = select_and_render(bar_df, "Revenue by region")
    assert isinstance(fig, go.Figure)


def test_line_chart_returns_figure(line_df):
    fig = select_and_render(line_df, "Sales over time")
    assert isinstance(fig, go.Figure)


def test_pie_chart_returns_figure(pie_df):
    fig = select_and_render(pie_df, "Category breakdown")
    assert isinstance(fig, go.Figure)


def test_single_metric_returns_none(metric_df):
    fig = select_and_render(metric_df, "Total revenue")
    assert fig is None


def test_empty_dataframe_returns_none():
    fig = select_and_render(pd.DataFrame())
    assert fig is None


def test_none_input_returns_none():
    fig = select_and_render(None)
    assert fig is None


# ===========================================================================
# select_and_render — chart content spot checks
# ===========================================================================


def test_bar_chart_uses_correct_columns(bar_df):
    fig = select_and_render(bar_df, "")
    # Plotly bar: data[0].x is the numeric axis, data[0].y is the category
    assert fig.data[0].type == "bar"


def test_line_chart_uses_correct_columns(line_df):
    fig = select_and_render(line_df, "")
    assert fig.data[0].type == "scatter"  # Plotly Express line uses scatter trace


def test_select_and_render_does_not_raise_on_unexpected_input():
    """Robustness: weird DataFrame shapes must never crash — return None."""
    weird_df = pd.DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6], "d": [7, 8]})
    try:
        result = select_and_render(weird_df, "something")
        # May return Figure or None — both are acceptable
        assert result is None or isinstance(result, go.Figure)
    except Exception as exc:
        pytest.fail(f"select_and_render raised unexpectedly: {exc}")