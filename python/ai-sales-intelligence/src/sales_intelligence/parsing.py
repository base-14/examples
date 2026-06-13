"""JSON parsing utilities for LLM responses."""

import json
import re
from typing import Any, cast


def extract_json(text: str) -> dict[str, Any]:
    """Extract the first valid JSON object from an LLM response.

    Handles common LLM quirks:
    - Markdown code fences (```json ... ```)
    - Extra text before or after the JSON object
    - Trailing commas (removed before parsing)
    - Nested objects and escaped quotes in strings

    Raises:
        json.JSONDecodeError: If no valid JSON object is found.
    """
    text = text.strip()

    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    text = text.strip()

    # Try parsing the whole string first (fast path)
    try:
        return cast("dict[str, Any]", json.loads(text))
    except json.JSONDecodeError:
        pass

    # Find the first { ... } block and parse it
    start = text.find("{")
    if start == -1:
        raise json.JSONDecodeError("No JSON object found", text, 0)

    # Walk forward to find the matching closing brace
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    return cast("dict[str, Any]", json.loads(candidate))
                except json.JSONDecodeError:
                    # Remove trailing commas before } or ] and retry
                    fixed = re.sub(r",\s*([}\]])", r"\1", candidate)
                    return cast("dict[str, Any]", json.loads(fixed))

    raise json.JSONDecodeError("Unterminated JSON object", text, start)
