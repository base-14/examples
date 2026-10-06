"""Per-model prices from the shared `_shared/pricing.json`."""

import json
import re
from pathlib import Path


def _load_pricing() -> dict[str, dict[str, float]]:
    this_file = Path(__file__)
    for depth in (4, 2):
        if depth < len(this_file.parents):
            candidate = this_file.parents[depth] / "_shared" / "pricing.json"
            if candidate.exists():
                with candidate.open() as f:
                    data = json.load(f)
                return {
                    model: {"input": info["input"], "output": info["output"]}
                    for model, info in data["models"].items()
                }
    raise FileNotFoundError(
        "pricing.json not found. Ensure _shared/pricing.json exists at the repo root "
        "and _shared/ is mounted into the container."
    )


PRICING: dict[str, dict[str, float]] = _load_pricing()

_MODEL_DATE_SUFFIX = re.compile(r"-\d{8}$")
_MODEL_MINOR_VERSION = re.compile(r"^(claude-(?:sonnet|opus|haiku))-(\d+)-(\d+)$")


def _normalize_model_id(model: str) -> str:
    """Map a provider-returned model ID to its pricing.json key.

    Providers return dated IDs (claude-sonnet-4-5-20250929) and dash-minor
    forms (claude-opus-4-6); pricing keys are dot-form (claude-opus-4.6).
    """
    stripped = _MODEL_DATE_SUFFIX.sub("", model)
    return _MODEL_MINOR_VERSION.sub(r"\1-\2.\3", stripped)


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost in USD for a model call. Unknown models cost 0.0."""
    pricing = PRICING.get(model) or PRICING.get(
        _normalize_model_id(model), {"input": 0.0, "output": 0.0}
    )
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
