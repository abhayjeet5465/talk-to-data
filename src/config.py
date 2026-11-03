"""
config.py — Central configuration loader.
All other modules import from here. Nothing reads os.environ directly.
"""

import os
import re
import unicodedata
from dotenv import load_dotenv

load_dotenv()

# Groq (Primary LLM)
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL_PRIMARY: str = os.getenv("GROQ_MODEL_PRIMARY", "openai/gpt-oss-120b")
GROQ_MODEL_FALLBACK: str = os.getenv("GROQ_MODEL_FALLBACK", "openai/gpt-oss-20b")

# Gemini (Fallback LLM)
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

# App settings
MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
MAX_SAMPLE_ROWS: int = int(os.getenv("MAX_SAMPLE_ROWS", "3"))
SQL_TIMEOUT_SECONDS: int = int(os.getenv("SQL_TIMEOUT_SECONDS", "10"))
ENABLE_DEBUG_SQL: bool = os.getenv("ENABLE_DEBUG_SQL", "false").lower() == "true"

# Internal constants
APP_TITLE: str = "Talk to Data"
APP_SUBTITLE: str = "Ask plain-English questions about any dataset"
DUCKDB_TABLE_NAME: str = "data"

SQL_BLOCKLIST: list[str] = [
    "DROP", "DELETE", "INSERT", "UPDATE", "ALTER",
    "CREATE", "TRUNCATE", "EXEC", "EXECUTE",
    "--", ";--", "PRAGMA", "ATTACH",
]


def validate_config() -> list[str]:
    """Returns a list of warnings for any missing API keys."""
    warnings = []
    if not GROQ_API_KEY:
        warnings.append("GROQ_API_KEY is not set — primary LLM unavailable.")
    if not GEMINI_API_KEY:
        warnings.append("GEMINI_API_KEY is not set — fallback LLM unavailable.")
    return warnings


# NatWest official brand colours — used in all Plotly charts
# Source: https://www.schemecolor.com/natwest-logo-colors.php
NATWEST_COLORS: list[str] = [
    "#401664",  # Dark Grape (primary purple)
    "#EE2033",  # Funky Red (primary red)
    "#F78E99",  # Fresh Light Red (light pink)
    "#C20000",  # Guardsman Red (dark red)
    "#6a1a99",  # Mid Purple
    "#8B4BA8",  # Light Purple
]


def slugify_table_name(filename: str) -> str:
    """Convert a raw filename into a safe, valid SQL table identifier.

    Strips the file extension, normalises unicode, replaces spaces and
    special characters with underscores, and ensures the name does not
    start with a digit (SQL identifiers cannot start with a number).

    Example:
        '2026 Sales Data.xlsx'  ->  'tbl_2026_sales_data'
        'product catalog.csv'   ->  'product_catalog'
    """
    # Drop the file extension
    name = filename.rsplit(".", 1)[0]

    # Normalise unicode -> closest ASCII equivalent (e.g. naïve -> naive)
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")

    # Lowercase and replace anything that isn't alphanumeric/space/hyphen
    name = re.sub(r"[^\w\s-]", "", name).strip().lower()

    # Collapse spaces and hyphens into single underscores
    name = re.sub(r"[-\s]+", "_", name)

    # SQL identifiers cannot start with a digit
    if re.match(r"^[0-9]", name):
        name = "tbl_" + name

    return name or "tbl_data"