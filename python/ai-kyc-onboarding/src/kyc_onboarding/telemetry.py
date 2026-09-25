"""Tracer, meter and logger providers, GenAI instrumentation, and derived span attributes.

The API and the worker both call `configure_telemetry` at startup and connect through
`create_temporal_client`.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from opentelemetry import metrics as otel_metrics
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.attributes import BoundedAttributes
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.environment_variables import OTEL_EXPORTER_OTLP_ENDPOINT
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_INSTANCE_ID as SERVICE_INSTANCE_ID_ATTRIBUTE
from opentelemetry.sdk.resources import SERVICE_NAME as SERVICE_NAME_ATTRIBUTE
from opentelemetry.sdk.resources import OTELResourceDetector, Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.util import BoundedList
from opentelemetry.trace import StatusCode
from opentelemetry.util.types import AttributeValue
from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from pydantic_ai.models.instrumented import InstrumentationSettings
from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.contrib.opentelemetry import (
    OpenTelemetryPlugin,
    ReplaySafeLoggerProvider,
    ReplaySafeMeterProvider,
    create_tracer_provider,
)
from temporalio.runtime import OpenTelemetryConfig, Runtime, TelemetryConfig

from kyc_onboarding.agents.prompts import PROMPT_VERSION_METADATA_KEY
from kyc_onboarding.attributes import PROMPT_VERSION_ATTRIBUTE


if TYPE_CHECKING:
    from kyc_onboarding.config import Settings

CHAT_OPERATION_NAME = "chat"
INVOKE_AGENT_OPERATION_NAME = "invoke_agent"
ERROR_TYPED_OPERATIONS = (CHAT_OPERATION_NAME, INVOKE_AGENT_OPERATION_NAME)
RUN_METADATA_ATTRIBUTE = "metadata"
ERROR_TYPE_ATTRIBUTE = "error.type"
EXCEPTION_TYPE_ATTRIBUTE = "exception.type"
GEN_AI_OPERATION_ATTRIBUTE = "gen_ai.operation.name"
GEN_AI_REQUEST_MODEL_ATTRIBUTE = "gen_ai.request.model"
GEN_AI_INPUT_TOKENS_ATTRIBUTE = "gen_ai.usage.input_tokens"
GEN_AI_OUTPUT_TOKENS_ATTRIBUTE = "gen_ai.usage.output_tokens"
COST_ATTRIBUTE = "base14.gen_ai.cost"
COST_SIMULATED_ATTRIBUTE = "base14.gen_ai.cost.simulated"

CASE_LOGGER_NAMES = ("kyc_onboarding", "temporalio.workflow", "temporalio.activity")

_PRICING_SHARED_DEPTHS = (4, 2)


def _load_pricing() -> dict[str, dict[str, float]]:
    """Load `_shared/pricing.json` from the repo root, or from `/app/_shared` in the
    container."""
    this_file = Path(__file__)
    for depth in _PRICING_SHARED_DEPTHS:
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


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> tuple[float, bool]:
    """Return `(cost, simulated)`. `simulated` is true for models missing from `pricing.json`,
    which covers every local Ollama model; their cost is zero."""
    pricing = PRICING.get(model)
    simulated = pricing is None
    if pricing is None:
        pricing = {"input": 0.0, "output": 0.0}
    cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    return cost, simulated


def _as_token_count(value: AttributeValue | None) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _cost_attributes(attributes: Mapping[str, AttributeValue]) -> dict[str, AttributeValue]:
    if attributes.get(GEN_AI_OPERATION_ATTRIBUTE) != CHAT_OPERATION_NAME:
        return {}
    model = attributes.get(GEN_AI_REQUEST_MODEL_ATTRIBUTE)
    if model is None:
        return {}
    input_tokens = _as_token_count(attributes.get(GEN_AI_INPUT_TOKENS_ATTRIBUTE))
    output_tokens = _as_token_count(attributes.get(GEN_AI_OUTPUT_TOKENS_ATTRIBUTE))
    cost, simulated = calculate_cost(str(model), input_tokens, output_tokens)
    return {COST_ATTRIBUTE: cost, COST_SIMULATED_ATTRIBUTE: simulated}


def _prompt_version_attributes(
    attributes: Mapping[str, AttributeValue],
) -> dict[str, AttributeValue]:
    if attributes.get(GEN_AI_OPERATION_ATTRIBUTE) != INVOKE_AGENT_OPERATION_NAME:
        return {}
    try:
        metadata = json.loads(str(attributes.get(RUN_METADATA_ATTRIBUTE)))
    except ValueError:
        return {}
    if not isinstance(metadata, dict) or PROMPT_VERSION_METADATA_KEY not in metadata:
        return {}
    return {PROMPT_VERSION_ATTRIBUTE: str(metadata[PROMPT_VERSION_METADATA_KEY])}


def _error_type_attributes(span: ReadableSpan) -> dict[str, AttributeValue]:
    attributes = span.attributes or {}
    if (
        attributes.get(GEN_AI_OPERATION_ATTRIBUTE) not in ERROR_TYPED_OPERATIONS
        or ERROR_TYPE_ATTRIBUTE in attributes
        or span.status.status_code != StatusCode.ERROR
    ):
        return {}
    for event in span.events:
        exception_type = (event.attributes or {}).get(EXCEPTION_TYPE_ATTRIBUTE)
        if event.name == "exception" and exception_type is not None:
            return {ERROR_TYPE_ATTRIBUTE: exception_type}
    return {}


def _with_derived_attributes(span: ReadableSpan) -> ReadableSpan:
    attributes = span.attributes or {}
    derived = {
        **_cost_attributes(attributes),
        **_prompt_version_attributes(attributes),
        **_error_type_attributes(span),
    }
    if not derived:
        return span
    merged = BoundedAttributes(attributes={**attributes, **derived})
    merged.dropped = span.dropped_attributes
    events = BoundedList.from_seq(None, span.events)
    events.dropped = span.dropped_events
    links = BoundedList.from_seq(None, span.links)
    links.dropped = span.dropped_links
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=merged,
        events=events,
        links=links,
        kind=span.kind,
        instrumentation_scope=span.instrumentation_scope,
        status=span.status,
        start_time=span.start_time,
        end_time=span.end_time,
    )


class CostAndErrorAttributingSpanExporter(SpanExporter):
    """Adds derived attributes to GenAI spans on their way to the wrapped exporter.

    `chat` spans get their cost. `invoke_agent` spans get `base14.prompt.version`, copied out
    of the run's `metadata` JSON. `chat` and `invoke_agent` spans with error status get
    `error.type` from their first recorded exception. Pydantic AI owns these spans, and a
    finished span's attributes are frozen, so each changed span is rebuilt instead, keeping
    its drop counts.
    """

    def __init__(self, wrapped: SpanExporter) -> None:
        self._wrapped = wrapped

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._wrapped.export([_with_derived_attributes(span) for span in spans])

    def shutdown(self) -> None:
        self._wrapped.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._wrapped.force_flush(timeout_millis)


def _capture_content_enabled() -> bool:
    return (
        os.environ.get("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true").lower()
        != "false"
    )


SERVICE_INSTANCE_ID = str(uuid.uuid4())

DEFAULT_OTLP_ENDPOINT = "http://localhost:4318"


def _resource(fallback_service_name: str) -> Resource:
    """`Resource.create` reads `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES`. When neither
    names the service, `fallback_service_name` replaces the SDK's `unknown_service`.
    `service.instance.id` is fresh per process, so a restarted worker's telemetry is told apart
    from the process it replaced."""
    resource = Resource.create({SERVICE_INSTANCE_ID_ATTRIBUTE: SERVICE_INSTANCE_ID})
    if OTELResourceDetector().detect().attributes.get(SERVICE_NAME_ATTRIBUTE):
        return resource
    return resource.merge(Resource({SERVICE_NAME_ATTRIBUTE: fallback_service_name}))


def service_name(fallback: str) -> str:
    return str(_resource(fallback).attributes[SERVICE_NAME_ATTRIBUTE])


def temporal_metrics_url() -> str:
    """The Temporal runtime's metrics exporter does not read `OTEL_EXPORTER_OTLP_ENDPOINT`, so
    it gets the URL the SDK's metric exporter would use."""
    endpoint = os.environ.get(OTEL_EXPORTER_OTLP_ENDPOINT) or DEFAULT_OTLP_ENDPOINT
    return f"{endpoint.rstrip('/')}/v1/metrics"


def configure_tracing(fallback_service_name: str) -> None:
    provider = create_tracer_provider(resource=_resource(fallback_service_name))
    exporter = CostAndErrorAttributingSpanExporter(OTLPSpanExporter())
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


def configure_metrics(fallback_service_name: str) -> None:
    reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    provider = MeterProvider(resource=_resource(fallback_service_name), metric_readers=[reader])
    otel_metrics.set_meter_provider(ReplaySafeMeterProvider(provider))


def install_logging(provider: LoggerProvider) -> None:
    """Route standard logging into `provider` through the replay-safe wrapper. Case loggers
    log at INFO. Temporal's loggers keep their details on record attributes, so a log body
    is the case line alone."""
    replay_safe_provider = ReplaySafeLoggerProvider(provider)
    set_logger_provider(replay_safe_provider)
    logging.getLogger().addHandler(LoggingHandler(logger_provider=replay_safe_provider))
    for name in CASE_LOGGER_NAMES:
        logging.getLogger(name).setLevel(logging.INFO)
    workflow.logger.workflow_info_on_message = False
    activity.logger.activity_info_on_message = False


def configure_logging(fallback_service_name: str) -> None:
    provider = LoggerProvider(resource=_resource(fallback_service_name))
    provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    install_logging(provider)


def configure_instrumentation() -> None:
    Agent.instrument_all(InstrumentationSettings(include_content=_capture_content_enabled()))
    PsycopgInstrumentor().instrument()


def configure_telemetry(fallback_service_name: str) -> None:
    """Export to `OTEL_EXPORTER_OTLP_ENDPOINT` as `OTEL_SERVICE_NAME`, or as
    `fallback_service_name` when that is unset."""
    configure_tracing(fallback_service_name)
    configure_metrics(fallback_service_name)
    configure_logging(fallback_service_name)
    configure_instrumentation()


def instrument_fastapi_app(app: FastAPI) -> None:
    FastAPIInstrumentor.instrument_app(app)


def build_temporal_runtime() -> Runtime:
    return Runtime(
        telemetry=TelemetryConfig(
            metrics=OpenTelemetryConfig(url=temporal_metrics_url(), http=True),
        )
    )


async def create_temporal_client(settings: Settings) -> Client:
    """Connect with the plugins every entrypoint needs. `PydanticAIPlugin` registers the agent
    activities and `OpenTelemetryPlugin` adds the Temporal spans. The runtime exports
    Temporal SDK metrics to the same collector."""
    return await Client.connect(
        settings.temporal_address,
        runtime=build_temporal_runtime(),
        plugins=[PydanticAIPlugin(), OpenTelemetryPlugin(add_temporal_spans=True)],
    )
