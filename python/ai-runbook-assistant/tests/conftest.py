import pytest
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.genai.langchain import LangChainInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from runbook_assistant.telemetry.genai_spans import (
    DataSource,
    GenAISpanExporter,
    RunAttributesProcessor,
)


# Registered at import, before any test module builds an agent or a metric
# instrument, so the global tracer and meter write into these collectors, through
# the same processor and exporter the app uses.
SPAN_EXPORTER = InMemorySpanExporter()
METRIC_READER = InMemoryMetricReader()

_tracer_provider = TracerProvider()
_tracer_provider.add_span_processor(
    RunAttributesProcessor(DataSource(id="runbooks", address="postgres", port=5432))
)
_tracer_provider.add_span_processor(SimpleSpanProcessor(GenAISpanExporter(SPAN_EXPORTER)))
trace.set_tracer_provider(_tracer_provider)
metrics.set_meter_provider(MeterProvider(metric_readers=[METRIC_READER]))
LangChainInstrumentor().instrument()


def _settings_env_names() -> set[str]:
    """Env var names that map to Settings fields (so unit tests can isolate
    from a developer's ambient shell, e.g. an exported SCOUT_ENVIRONMENT)."""
    from runbook_assistant.config import Settings

    names: set[str] = set()
    for name, field in Settings.model_fields.items():
        names.add(name.upper())
        alias = getattr(field, "alias", None)
        if alias:
            names.add(alias)
            names.add(alias.upper())
    return names


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch):
    from runbook_assistant.config import Settings, get_settings

    for env_name in _settings_env_names():
        monkeypatch.delenv(env_name, raising=False)
    # ignore a local .env so unit tests assert code defaults
    monkeypatch.setitem(Settings.model_config, "env_file", None)

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def span_exporter() -> InMemorySpanExporter:
    SPAN_EXPORTER.clear()
    return SPAN_EXPORTER


@pytest.fixture
def capture_content(monkeypatch):
    """Re-instruments with `SPAN_ONLY` capture. The instrumentation reads the variable
    once, when it is instrumented, so setting it inside a test changes nothing on its own."""
    monkeypatch.setenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "SPAN_ONLY")
    LangChainInstrumentor().uninstrument()
    LangChainInstrumentor().instrument()
    yield
    monkeypatch.delenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT")
    LangChainInstrumentor().uninstrument()
    LangChainInstrumentor().instrument()


@pytest.fixture
def anthropic_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
