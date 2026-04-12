
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
                # dayfirst=True handles DD/MM/YYYY format common in UK/EU datasets.
                # format='mixed' lets pandas try multiple formats within the same column.
                df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True, format="mixed")
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
            # dayfirst=True so that DD/MM/YYYY dates (e.g. '13/02/2010') parse correctly
            pd.to_datetime(str(val), dayfirst=True)
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
    """Build a concise schema description string for the LLM prompt.

    Enriched format includes:
    - Column name, type, and sample values (always)
    - min / max for numeric columns (helps LLM write valid range filters)
    - Full unique value list for low-cardinality text columns (≤15 unique values)
      This prevents the LLM from guessing category names like "North" vs "North Region"

    Args:
        df:           The full DataFrame.
        column_types: Dict of column name → type label.
        filename:     Original filename shown to the LLM for source transparency.

    Returns:
        A multi-line string describing the schema with enriched sample values.
    """
    lines = [
        f"Table: {DUCKDB_TABLE_NAME}",
        f"Source: {filename}",
        f"Rows: {len(df)}  Columns: {len(df.columns)}",
        "",
        "Columns:",
    ]

    for col, col_type in column_types.items():
        col_data = df[col].dropna()

        if col_type in ("integer", "float"):
            # For numeric columns: show sample values + min and max
            samples = col_data.head(MAX_SAMPLE_ROWS).tolist()
            sample_str = ", ".join(str(v) for v in samples)
            try:
                min_val = col_data.min()
                max_val = col_data.max()
                lines.append(
                    f"  - {col} ({col_type}): {sample_str}"
                    f" | min={min_val:.2f}, max={max_val:.2f}"
                )
            except Exception:
                lines.append(f"  - {col} ({col_type}): {sample_str}")

        elif col_type == "text":
            unique_vals = col_data.unique()
            if len(unique_vals) <= 15:
                # Low cardinality — show ALL unique values so the LLM knows
                # exactly what values exist in this column (e.g. region names)
                val_list = sorted(str(v) for v in unique_vals[:20])
                lines.append(f"  - {col} ({col_type}): all values = {val_list}")
            else:
                # High cardinality — just show 3 samples
                samples = col_data.head(MAX_SAMPLE_ROWS).tolist()
                sample_str = ", ".join(str(v) for v in samples)
                lines.append(f"  - {col} ({col_type}): {sample_str}")

        else:
            # datetime, boolean — show sample values only
            samples = col_data.head(MAX_SAMPLE_ROWS).tolist()
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


# ---------------------------------------------------------------------------
# Multi-file helpers (additive — single-file path above is untouched)
# ---------------------------------------------------------------------------


def infer_join_keys(datasets: dict) -> list[str]:
    """Find columns with the same name and compatible types across tables.

    Args:
        datasets: dict mapping table_name -> schema_info dict
                  (as returned by extract_schema).

    Returns:
        List of hint strings, e.g.
        ["sales.product_id <-> catalog.product_id (type: text)"]
    """
    hints = []
    table_names = list(datasets.keys())

    for i in range(len(table_names)):
        for j in range(i + 1, len(table_names)):
            t1, t2 = table_names[i], table_names[j]
            cols1 = datasets[t1]["column_types"]
            cols2 = datasets[t2]["column_types"]

            for col in cols1:
                if col in cols2 and cols1[col] == cols2[col]:
                    hints.append(
                        f"{t1}.{col} <-> {t2}.{col} (type: {cols1[col]})"
                    )

    return hints


def build_unified_schema(datasets: dict) -> str:
    """Build a single schema string covering all loaded tables.

    Formats each table with its name, source file, row/col counts, and
    columns, then appends auto-detected join-key hints.

    Args:
        datasets: dict mapping table_name -> schema_info dict.

    Returns:
        A multi-line string ready to inject into the LLM prompt.
    """
    lines = [
        f"DATABASE SCHEMA: {len(datasets)} active table(s).",
        "",
    ]

    for i, (table_name, info) in enumerate(datasets.items(), start=1):
        lines.append(f"Table {i}: {table_name}  (source: {info['filename']})")
        lines.append(f"Rows: {info['row_count']}  Columns: {info['col_count']}")
        lines.append("Columns:")
        for col, col_type in info["column_types"].items():
            lines.append(f"  - {col} ({col_type})")
        lines.append("")

    join_hints = infer_join_keys(datasets)
    if join_hints:
        lines.append("SYSTEM INFERRED JOIN KEYS (use these for ON clauses):")
        for hint in join_hints:
            lines.append(f"  * {hint}")
    else:
        lines.append("SYSTEM INFERRED JOIN KEYS: none detected automatically.")

    return "\n".join(lines)