"""
test_schema_extractor.py — Unit tests for the schema extractor.

Run with: pytest tests/ -v
"""

import io
import pytest
import pandas as pd
from src.schema_extractor import (
    read_file,
    infer_column_types,
    build_schema_string,
    extract_schema,
    SchemaExtractionError,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def make_csv_file(content: str, filename: str = "test.csv"):
    """Create a fake file object from a CSV string."""
    f = io.BytesIO(content.encode())
    f.name = filename
    return f


def make_sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "date": ["2026-01-01", "2026-01-08", "2026-01-15"],
        "region": ["North", "South", "East"],
        "revenue": [12000.0, 8500.0, 6200.0],
        "units": [240, 170, 124],
    })


# ── read_file ──────────────────────────────────────────────────────────────

def test_read_csv_returns_dataframe():
    csv = "date,region,revenue\n2026-01-01,North,12000\n2026-01-08,South,8500"
    f = make_csv_file(csv)
    df = read_file(f)
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["date", "region", "revenue"]
    assert len(df) == 2


def test_read_unsupported_format_raises():
    f = make_csv_file("data", filename="data.txt")
    with pytest.raises(SchemaExtractionError, match="Unsupported file type"):
        read_file(f)


def test_read_empty_csv_raises():
    f = make_csv_file("")
    with pytest.raises(SchemaExtractionError):
        read_file(f)


def test_column_names_are_stripped():
    csv = " date , region , revenue \n2026-01-01,North,12000"
    f = make_csv_file(csv)
    df = read_file(f)
    assert list(df.columns) == ["date", "region", "revenue"]


# ── infer_column_types ─────────────────────────────────────────────────────

def test_infer_integer_and_float_types():
    df = pd.DataFrame({"units": [1, 2, 3], "revenue": [1.1, 2.2, 3.3]})
    types = infer_column_types(df)
    assert types["units"] == "integer"
    assert types["revenue"] == "float"


def test_infer_text_type():
    df = pd.DataFrame({"region": ["North", "South", "East"]})
    types = infer_column_types(df)
    assert types["region"] == "text"


def test_infer_datetime_type():
    df = pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-01-08"])})
    types = infer_column_types(df)
    assert types["date"] == "datetime"


# ── build_schema_string ────────────────────────────────────────────────────

def test_schema_string_contains_filename():
    df = make_sample_df()
    types = infer_column_types(df)
    schema = build_schema_string(df, types, "sales.csv")
    assert "sales.csv" in schema


def test_schema_string_contains_all_columns():
    df = make_sample_df()
    types = infer_column_types(df)
    schema = build_schema_string(df, types, "test.csv")
    for col in df.columns:
        assert col in schema


def test_schema_string_contains_row_count():
    df = make_sample_df()
    types = infer_column_types(df)
    schema = build_schema_string(df, types, "test.csv")
    assert "Rows: 3" in schema


# ── extract_schema (integration) ───────────────────────────────────────────

def test_extract_schema_returns_all_keys():
    csv = "date,region,revenue\n2026-01-01,North,12000\n2026-01-08,South,8500"
    f = make_csv_file(csv)
    result = extract_schema(f)
    for key in ["df", "schema_str", "column_types", "filename", "row_count", "col_count"]:
        assert key in result


def test_extract_schema_row_and_col_counts():
    csv = "date,region,revenue\n2026-01-01,North,12000\n2026-01-08,South,8500"
    f = make_csv_file(csv)
    result = extract_schema(f)
    assert result["row_count"] == 2
    assert result["col_count"] == 3