"""Token → USD cost calculation with a small pricing table.

Pricing is USD per 1M tokens. Re-verify rates at build time. Unknown models
return 0.0 (cost is best-effort; never raises).
"""

import re


PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-2.5-flash": (0.30, 2.5),
}

_DATE_SUFFIX = re.compile(r"-\d{8}$")


def _normalize(model: str) -> str:
    """Strip a trailing dated suffix (claude-sonnet-4-6-20260101)."""
    return _DATE_SUFFIX.sub("", model)


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = PRICING.get(model) or PRICING.get(_normalize(model))
    if not rates:
        return 0.0
    in_rate, out_rate = rates
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000
