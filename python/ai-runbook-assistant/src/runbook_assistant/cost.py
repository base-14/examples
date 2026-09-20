"""Token to USD cost, priced from the shared pricing table.

Rates in `_shared/pricing.json` are USD per 1M tokens. Providers return dated
snapshot ids and dash-minor ids; both normalise to the file's keys. Unknown
models cost 0.0, so cost is always a number and never raises.
"""

import json
import re
from pathlib import Path


def _load_pricing() -> dict[str, tuple[float, float]]:
    this_file = Path(__file__)
    for depth in (4, 2):
        if depth < len(this_file.parents):
            candidate = this_file.parents[depth] / "_shared" / "pricing.json"
            if candidate.exists():
                with candidate.open() as f:
                    data = json.load(f)
                return {
                    model: (float(info["input"]), float(info["output"]))
                    for model, info in data["models"].items()
                }
    raise FileNotFoundError(
        "pricing.json not found. Ensure _shared/pricing.json exists at the repo root "
        "and _shared/ is mounted into the container."
    )


PRICING: dict[str, tuple[float, float]] = _load_pricing()

_DATE_SUFFIX = re.compile(r"-\d{4}-\d{2}-\d{2}$|-\d{8}$")
_MINOR_VERSION = re.compile(r"-(\d+)-(\d+)$")


def _normalize(model: str) -> str:
    """Map a dated or dash-minor model id onto its pricing key."""
    return _MINOR_VERSION.sub(r"-\1.\2", _DATE_SUFFIX.sub("", model))


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = PRICING.get(model) or PRICING.get(_normalize(model))
    if not rates:
        return 0.0
    in_rate, out_rate = rates
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000
