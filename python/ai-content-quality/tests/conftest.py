from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import content_quality.telemetry as telemetry_mod


# Registered here, before any test module imports content_quality.main, so the
# tracer and the metric instruments that content_quality.services.llm and
# content_quality.services.analyzer create at import time write into these
# in-memory collectors. OTEL_SDK_DISABLED is left unset: that flag makes the
# OTel API return no-op tracers/meters regardless of which provider is
# registered, which would defeat these in-memory collectors.
SPAN_EXPORTER = InMemorySpanExporter()
METRIC_READER = InMemoryMetricReader()

_tracer_provider = TracerProvider()
_tracer_provider.add_span_processor(SimpleSpanProcessor(SPAN_EXPORTER))
trace.set_tracer_provider(_tracer_provider)
metrics.set_meter_provider(MeterProvider(metric_readers=[METRIC_READER]))


# content_quality.main calls setup_telemetry(...) at import time, which would
# otherwise build real OTLP exporters pointed at a collector that isn't
# running. Stub it out only for that one import: main.py binds the name via
# `from content_quality.telemetry import setup_telemetry`, so the patch only
# needs to be active while that import statement executes.
def _noop_setup_telemetry(*_args: object, **_kwargs: object) -> tuple[trace.Tracer, metrics.Meter]:
    return trace.get_tracer("test"), metrics.get_meter("test")


with patch.object(telemetry_mod, "setup_telemetry", _noop_setup_telemetry):
    from content_quality.main import app

from content_quality.models.responses import (  # noqa: E402
    ContentIssue,
    ImprovementSuggestion,
    ImproveResult,
    ReviewResult,
    ScoreBreakdown,
    ScoreResult,
)


@pytest.fixture
def span_exporter() -> InMemorySpanExporter:
    """In-memory span exporter, cleared before each test that uses it."""
    SPAN_EXPORTER.clear()
    return SPAN_EXPORTER


@pytest.fixture
def metric_reader() -> InMemoryMetricReader:
    """In-memory metric reader for tests that assert on recorded metrics."""
    return METRIC_READER


@pytest.fixture
def mock_analyzer() -> AsyncMock:
    analyzer = AsyncMock()
    analyzer.review.return_value = ReviewResult(
        issues=[
            ContentIssue(
                type="grammar",
                description="Missing comma after introductory phrase",
                location="sentence 1",
                severity="low",
            )
        ],
        summary="Minor grammar issue found",
        overall_quality="good",
    )
    analyzer.improve.return_value = ImproveResult(
        suggestions=[
            ImprovementSuggestion(
                original="This is very good",
                improved="This is effective",
                reason="Avoid vague qualifiers",
            )
        ],
        summary="One suggestion for clarity",
    )
    analyzer.score.return_value = ScoreResult(
        score=82,
        breakdown=ScoreBreakdown(clarity=85, accuracy=80, engagement=82, originality=78),
        summary="Good quality content overall",
    )
    return analyzer


@pytest.fixture
def client(mock_analyzer: AsyncMock) -> TestClient:
    app.state.analyzer = mock_analyzer
    return TestClient(app)
