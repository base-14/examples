"""GenAI metric instruments (OTel semconv v1.40.0)."""

from typing import Any

from opentelemetry import metrics


class GenAIMetrics:
    def __init__(self) -> None:
        meter = metrics.get_meter("gen_ai.client")
        self._tokens = meter.create_histogram(
            "gen_ai.client.token.usage",
            unit="{token}",
            description="Tokens used per LLM call",
        )
        self._duration = meter.create_histogram(
            "gen_ai.client.operation.duration",
            unit="s",
            description="Duration of GenAI operations",
        )
        self._cost = meter.create_counter(
            "gen_ai.client.cost",
            unit="usd",
            description="Cost of GenAI operations in USD",
        )
        self._errors = meter.create_counter(
            "gen_ai.client.error.count",
            unit="{error}",
            description="GenAI errors by type",
        )

    def record_tokens(self, attrs: dict[str, Any], input_tokens: int, output_tokens: int) -> None:
        self._tokens.record(input_tokens, {**attrs, "gen_ai.token.type": "input"})
        self._tokens.record(output_tokens, {**attrs, "gen_ai.token.type": "output"})

    def record_duration(self, attrs: dict[str, Any], seconds: float) -> None:
        self._duration.record(seconds, attrs)

    def add_cost(self, attrs: dict[str, Any], usd: float) -> None:
        self._cost.add(usd, attrs)

    def add_error(self, attrs: dict[str, Any]) -> None:
        self._errors.add(1, attrs)


_metrics: GenAIMetrics | None = None


def get_metrics() -> GenAIMetrics:
    global _metrics
    if _metrics is None:
        _metrics = GenAIMetrics()
    return _metrics
