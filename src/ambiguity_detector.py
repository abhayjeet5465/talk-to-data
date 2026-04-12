"""
ambiguity_detector.py — Parses the ambiguity sentinel returned by the LLM.

When the SQL generator cannot answer a question because it is too vague,
it returns this JSON string inside a <sql> tag instead of SQL:
    {"status": "ambiguous", "clarification_needed": "Please specify..."}

This module detects that JSON and extracts the clarification message.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def parse_ambiguity(text: str) -> tuple[bool, str]:
    """Check whether the LLM returned an ambiguity sentinel instead of SQL.

    Args:
        text: The string extracted from the <sql> tag by the SQL generator.
              This is either real SQL or an ambiguity JSON object.

    Returns:
        (True, clarification_message) if the text is an ambiguity sentinel.
        (False, "")                   for any normal SQL string.
    """
    text = text.strip()

    # Quick exit — real SQL will never start with '{'.
    if not text.startswith("{"):
        return False, ""

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Looks like JSON but is not — treat as SQL.
        return False, ""

    if isinstance(data, dict) and data.get("status") == "ambiguous":
        message = data.get("clarification_needed", "Could you clarify your question?")
        logger.debug("Ambiguity detected: %s", message)
        return True, message

    return False, ""
