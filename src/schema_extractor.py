
"""
schema_extractor.py — Stage 2.

Reads an uploaded CSV or Excel file, infers column names and data types,
picks sample rows, and builds a schema string to send to the LLM.

The full dataset NEVER leaves this module — only the schema string and
sample rows are passed forward to the LLM pipeline.
"""

import pandas as pd
from src.config import MAX_SAMPLE_ROWS, DUCKDB_TABLE_NAME


class SchemaExtractionError(Exception):
    """Raised when a file cannot be read or schema cannot be inferred."""
    pass


def read_file(file) -> pd.DataFrame:
    """
    Read an uploaded CSV or Excel file into a Pandas DataFrame.

    Args:
        file: A file-like object from Streamlit's file_uploader.

    Returns:
        A Pandas DataFrame containing the file contents.

    Raises:
        SchemaExtractionError: If the file format is unsupported or unreadable.
    """
    filename: str = file.name.lower()

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(file)
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(file)
        else:
            raise SchemaExtractionError(
                f"Unsupported file type: {file.name}. "
                "Please upload a CSV or Excel file."
            )
    except SchemaExtractionError:
        raise
    except Exception as e:
        raise SchemaExtractionError(f"Could not read file '{file.name}': {e}")

    if df.empty:
        raise SchemaExtractionError("The uploaded file is empty.")

    if len(df.columns) == 0:
        raise SchemaExtractionError("No columns found in the uploaded file.")

    # Clean column names — strip whitespace, lowercase for consistency
    df.columns = [col.strip() for col in df.columns]

    return df


def infer_column_types(df: pd.DataFrame) -> dict[str, str]:
    """
    Map each DataFrame column to a human-readable type label.

    Pandas dtype categories are mapped to simpler labels so the LLM
    understands what kind of data each column holds.

    Args:
        df: The DataFrame to inspect.

    Returns:
        Dict mapping column name → type label string.
    """
    type_map = {}

    for col in df.columns:
        dtype = df[col].dtype

        if pd.api.types.is_datetime64_any_dtype(dtype):
            type_map[col] = "datetime"
        elif pd.api.types.is_bool_dtype(dtype):
            type_map[col] = "boolean"
        elif pd.api.types.is_integer_dtype(dtype):
            type_map[col] = "integer"
        elif pd.api.types.is_float_dtype(dtype):
            type_map[col] = "float"
        else:
            # Try to parse as datetime if it looks like a date string
            sample = df[col].dropna().head(5)
            if _looks_like_date(sample):
                df[col] = pd.to_datetime(df[col], errors="coerce")
                type_map[col] = "datetime"
            else:
                type_map[col] = "text"

    return type_map


def _looks_like_date(sample: pd.Series) -> bool:
    """
    Heuristic check: does a sample of string values look like dates?

    Args:
        sample: A small Series of string values to check.

    Returns:
        True if most values parse successfully as dates.
    """
    if sample.empty:
        return False

    parsed = 0
    for val in sample:
        try:
            pd.to_datetime(str(val))
            parsed += 1
        except Exception:
            pass

    # Require at least 80% to parse cleanly
    return (parsed / len(sample)) >= 0.8


def build_schema_string(
    df: pd.DataFrame,
    column_types: dict[str, str],
    filename: str,
) -> str:
    """
    Build a concise schema description string for the LLM prompt.

    Format:
        Table: data
        Source: filename.csv
        Rows: 1234  Columns: 5

        Columns:
          - date (datetime): 2026-01-01, 2026-01-08, 2026-01-15
          - region (text): North, South, East
          - revenue (float): 12000.0, 8500.0, 6200.0

    Args:
        df: The full DataFrame.
        column_types: Dict of column name → type label.
        filename: Original filename shown to the LLM for source transparency.

    Returns:
        A multi-line string describing the schema with sample values.
    """
    lines = [
        f"Table: {DUCKDB_TABLE_NAME}",
        f"Source: {filename}",
        f"Rows: {len(df)}  Columns: {len(df.columns)}",
        "",
        "Columns:",
    ]

    for col, col_type in column_types.items():
        # Get up to MAX_SAMPLE_ROWS non-null sample values
        samples = (
            df[col]
            .dropna()
            .head(MAX_SAMPLE_ROWS)
            .tolist()
        )
        sample_str = ", ".join(str(v) for v in samples)
        lines.append(f"  - {col} ({col_type}): {sample_str}")

    return "\n".join(lines)


def extract_schema(file) -> dict:
    """
    Main entry point for Stage 2.

    Reads the uploaded file and returns everything downstream stages need:
    the DataFrame (for DuckDB), the schema string (for the LLM), and
    metadata (for the UI).

    Args:
        file: File-like object from Streamlit file_uploader.

    Returns:
        Dict with keys:
            df          — full Pandas DataFrame
            schema_str  — schema string to pass to LLM prompts
            column_types — dict of column → type label
            filename    — original filename
            row_count   — number of rows
            col_count   — number of columns

    Raises:
        SchemaExtractionError: If the file cannot be read or is empty.
    """
    df = read_file(file)
    column_types = infer_column_types(df)
    schema_str = build_schema_string(df, column_types, file.name)

    return {
        "df": df,
        "schema_str": schema_str,
        "column_types": column_types,
        "filename": file.name,
        "row_count": len(df),
        "col_count": len(df.columns),
    }