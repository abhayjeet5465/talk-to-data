"""
verify_setup.py — Run this after setup to confirm everything is working.
Usage: python scripts/verify_setup.py
"""

import sys
import importlib


def check(label, fn):
    try:
        fn()
        print(f"  OK  {label}")
    except Exception as e:
        print(f"  FAIL  {label} — {e}")


print("\nTalk to Data — Setup Verification\n" + "=" * 40)

# Check imports
for pkg in ["streamlit", "pandas", "duckdb", "groq", "plotly", "dotenv"]:
    check(f"import {pkg}", lambda p=pkg: importlib.import_module(p))

# Check config
def check_config():
    sys.path.insert(0, ".")
    from src.config import validate_config, GROQ_API_KEY, GEMINI_API_KEY
    warnings = validate_config()
    if warnings:
        for w in warnings:
            print(f"  WARN  {w}")
    else:
        print("  OK  API keys found")

check("src.config loads", check_config)

print("\nDone. Fix any FAIL items before proceeding to Stage 2.\n")