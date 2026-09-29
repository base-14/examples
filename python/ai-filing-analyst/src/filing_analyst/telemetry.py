"""Tracer, meter and logger providers for the API, and the attributes the exporter derives.

`configure_telemetry` runs before any agent is built. Every framework reads the global tracer
and meter providers, so its spans and metrics carry this resource. `StrandsTelemetry` is not used,
because it would install a meter provider with its own resource.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import uuid
from collections.abc import Callable, Iterator, Mapping, MutableMapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from fastapi import FastAPI
from opentelemetry import context as otel_context
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.attributes import BoundedAttributes
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.logging.constants import DEFAULT_LOGGING_FORMAT
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LogRecordProcessor, ReadWriteLogRecord
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogRecordExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import (
    SERVICE_INSTANCE_ID,
    SERVICE_NAME,
    OTELResourceDetector,
    Resource,
)
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.util import BoundedList
from opentelemetry.trace import StatusCode

from filing_analyst.config import framework_name


FALLBACK_SERVICE_NAME = "ai-filing-analyst"
APP_LOGGER_NAME = "filing_analyst"

CAPTURE_CONTENT_VARIABLE = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
SEMCONV_OPT_IN_VARIABLE = "OTEL_SEMCONV_STABILITY_OPT_IN"
UNREDACTED_TOKEN_PREFIX = "gen_ai_unredacted_attributes="
REDACT_ALL_TOKEN = UNREDACTED_TOKEN_PREFIX

MODEL_CALL_OPERATIONS = frozenset({"chat", "generate_content", "text_completion"})
MODEL_PROVIDER = "ollama"
FRAMEWORK_ATTRIBUTE = "base14.filing.framework"
GEN_AI_SPAN_PREFIXES = (
    "invoke_agent",
    "invoke_workflow",
    "invocation",
    "call_llm",
    "chat",
    "generate_content",
    "execute_tool",
)
GEN_AI_OPERATION_ATTRIBUTE = "gen_ai.operation.name"
GEN_AI_PROVIDER_ATTRIBUTE = "gen_ai.provider.name"
GEN_AI_AGENT_NAME_ATTRIBUTE = "gen_ai.agent.name"
GEN_AI_REQUEST_MODEL_ATTRIBUTE = "gen_ai.request.model"
GEN_AI_INPUT_TOKENS_ATTRIBUTE = "gen_ai.usage.input_tokens"
GEN_AI_OUTPUT_TOKENS_ATTRIBUTE = "gen_ai.usage.output_tokens"
ERROR_TYPE_ATTRIBUTE = "error.type"
EXCEPTION_TYPE_ATTRIBUTE = "exception.type"
QUESTION_ID_ATTRIBUTE = "base14.filing.question_id"
LOG_CORRELATION_VARIABLE = "OTEL_PYTHON_LOG_CORRELATION"
CONSOLE_HANDLER_NAME = "console"
CONSOLE_CORRELATION_FIELDS = ("otelTraceID", "otelSpanID", "otelTraceSampled", "otelServiceName")
EXCEPTION_STACKTRACE_ATTRIBUTE = "exception.stacktrace"
HTTP_STATUS_ATTRIBUTES = ("http.response.status_code", "http.status_code")
OTHER_ERROR_TYPE = "_OTHER"
TRUNCATION_LOGGER_NAME = "opentelemetry.attributes"
WRAPPER_EXCEPTION_TYPES = frozenset({"strands.types.exceptions.EventLoopException"})
CHAINED_EXCEPTION = re.compile(
    r"\n\n(?:The above exception was the direct cause of the following exception"
    r"|During handling of the above exception, another exception occurred):\n\n"
)
COST_ATTRIBUTE = "base14.gen_ai.cost"
COST_SIMULATED_ATTRIBUTE = "base14.gen_ai.cost.simulated"

_PRICING_SHARED_DEPTHS = (4, 2)

type DerivedValue = str | bool | int | float


@cache
def _pricing() -> dict[str, dict[str, float]]:
    """`_shared/pricing.json` from the repo root, or from `/app/_shared` in the container."""
    this_file = Path(__file__)
    for depth in _PRICING_SHARED_DEPTHS:
        if depth < len(this_file.parents):
            candidate = this_file.parents[depth] / "_shared" / "pricing.json"
            if candidate.exists():
                data = json.loads(candidate.read_text())
                return {
                    model: {"input": info["input"], "output": info["output"]}
                    for model, info in data["models"].items()
                }
    raise FileNotFoundError(
        "pricing.json not found. Ensure _shared/pricing.json exists at the repo root "
        "and _shared/ is mounted into the container."
    )


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> tuple[float, bool]:
    """Return `(cost, simulated)`. A model missing from `pricing.json`, which covers every
    local Ollama model, costs zero and is marked simulated."""
    pricing = _pricing().get(model)
    if pricing is None:
        return 0.0, True
    cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    return cost, False


def _as_token_count(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _cost_attributes(attributes: Mapping[str, object]) -> dict[str, DerivedValue]:
    if attributes.get(GEN_AI_OPERATION_ATTRIBUTE) not in MODEL_CALL_OPERATIONS:
        return {}
    model = attributes.get(GEN_AI_REQUEST_MODEL_ATTRIBUTE)
    if model is None:
        return {}
    cost, simulated = calculate_cost(
        str(model),
        _as_token_count(attributes.get(GEN_AI_INPUT_TOKENS_ATTRIBUTE)),
        _as_token_count(attributes.get(GEN_AI_OUTPUT_TOKENS_ATTRIBUTE)),
    )
    return {COST_ATTRIBUTE: cost, COST_SIMULATED_ATTRIBUTE: simulated}


def _error_type_attributes(span: ReadableSpan) -> dict[str, DerivedValue]:
    """An instrumentation's `_OTHER` gives way to a recorded exception, which names the type."""
    attributes = span.attributes or {}
    if span.status.status_code != StatusCode.ERROR:
        return {}
    if attributes.get(ERROR_TYPE_ATTRIBUTE, OTHER_ERROR_TYPE) != OTHER_ERROR_TYPE:
        return {}
    for event in span.events:
        exception_type = (event.attributes or {}).get(EXCEPTION_TYPE_ATTRIBUTE)
        if event.name == "exception" and exception_type is not None:
            stacktrace = (event.attributes or {}).get(EXCEPTION_STACKTRACE_ATTRIBUTE)
            if str(exception_type) in WRAPPER_EXCEPTION_TYPES and isinstance(stacktrace, str):
                return {ERROR_TYPE_ATTRIBUTE: _root_cause_type(stacktrace, str(exception_type))}
            return {ERROR_TYPE_ATTRIBUTE: str(exception_type)}
    for key in HTTP_STATUS_ATTRIBUTES:
        if key in attributes:
            return {ERROR_TYPE_ATTRIBUTE: str(attributes[key])}
    return {ERROR_TYPE_ATTRIBUTE: OTHER_ERROR_TYPE}


def _root_cause_type(stacktrace: str, fallback: str) -> str:
    """Strands wraps every failure in its event loop in one exception type. The formatted
    stacktrace lists the chain root first, and its last line is `type: message`."""
    first = CHAINED_EXCEPTION.split(stacktrace, maxsplit=1)[0].rstrip().splitlines()
    if not first:
        return fallback
    root = first[-1].split(":", 1)[0].strip()
    return root.removeprefix("builtins.") or fallback


def _provider_attributes(
    attributes: Mapping[str, object], provider: str | None
) -> dict[str, DerivedValue]:
    if provider is None or attributes.get(GEN_AI_OPERATION_ATTRIBUTE) not in MODEL_CALL_OPERATIONS:
        return {}
    if attributes.get(GEN_AI_PROVIDER_ATTRIBUTE) == provider:
        return {}
    return {GEN_AI_PROVIDER_ATTRIBUTE: provider}


def _with_derived_attributes(span: ReadableSpan, provider: str | None = None) -> ReadableSpan:
    attributes = span.attributes or {}
    derived = {
        **_cost_attributes(attributes),
        **_error_type_attributes(span),
        **_provider_attributes(attributes, provider),
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
    """Adds derived attributes to spans on their way to the wrapped exporter.

    Model call spans get their cost and the simulated flag. With `provider` set, they also get
    that `gen_ai.provider.name`, for frameworks that report the client library in place of the
    server it reached, or no provider at all. Spans with error status and no
    `error.type` get it from their first recorded exception, because Strands records the
    exception but sets no `error.type`. A failed span with no exception takes its HTTP status
    code, and any other takes the semconv fallback `_OTHER`. A finished span's attributes are frozen, so each changed
    span is rebuilt, keeping its drop counts.
    """

    def __init__(self, wrapped: SpanExporter, provider: str | None = None) -> None:
        self._wrapped = wrapped
        self._provider = provider

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._wrapped.export(
            [_with_derived_attributes(span, self._provider) for span in spans]
        )

    def shutdown(self) -> None:
        self._wrapped.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._wrapped.force_flush(timeout_millis)


def apply_content_capture_setting(environ: MutableMapping[str, str] | None = None) -> None:
    """Map `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false` onto Strands' redaction.

    Strands does not read the capture variable. It redacts message content, tool arguments and
    tool results when `OTEL_SEMCONV_STABILITY_OPT_IN` carries `gen_ai_unredacted_attributes=`,
    and an empty list after the `=` redacts all of them. A list the reader set is kept. Strands
    reads the opt-in once, when its tracer is first built, so this runs before any agent.
    """
    env = os.environ if environ is None else environ
    if env.get(CAPTURE_CONTENT_VARIABLE, "true").strip().lower() != "false":
        return
    tokens = [token.strip() for token in env.get(SEMCONV_OPT_IN_VARIABLE, "").split(",")]
    tokens = [token for token in tokens if token]
    if any(token.startswith(UNREDACTED_TOKEN_PREFIX) for token in tokens):
        return
    env[SEMCONV_OPT_IN_VARIABLE] = ",".join([*tokens, REDACT_ALL_TOKEN])


SERVICE_INSTANCE = str(uuid.uuid4())


def build_resource() -> Resource:
    """`Resource.create` reads `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES`. When neither
    names the service, `ai-filing-analyst` replaces the SDK's `unknown_service`. The instance ID
    is fresh per process, and `base14.filing.framework` names the agent framework in use."""
    resource = Resource.create(
        {SERVICE_INSTANCE_ID: SERVICE_INSTANCE, FRAMEWORK_ATTRIBUTE: framework_name()}
    )
    if OTELResourceDetector().detect().attributes.get(SERVICE_NAME):
        return resource
    return resource.merge(Resource({SERVICE_NAME: FALLBACK_SERVICE_NAME}))


def build_tracer_provider(
    exporter: SpanExporter,
    resource: Resource,
    processor: Callable[[SpanExporter], SpanProcessor] = BatchSpanProcessor,
) -> TracerProvider:
    """The SDK reads `OTEL_SDK_DISABLED`, the sampler variables and
    `OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT` itself; the batch processor reads the `OTEL_BSP_*`
    variables."""
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(AgentRunAttributesProcessor())
    provider.add_span_processor(processor(exporter))
    return provider


def build_meter_provider(reader: MetricReader, resource: Resource) -> MeterProvider:
    return MeterProvider(resource=resource, metric_readers=[reader])


def build_logger_provider(exporter: LogRecordExporter, resource: Resource) -> LoggerProvider:
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(QuestionIdLogProcessor())
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    return provider


type AttributeValue = str | int


@dataclass(frozen=True)
class AgentRunAttributes:
    """The attributes of one question's agent run. `question` goes on every GenAI span of the
    run; `by_agent` and `by_model` add an agent's prompt version and model digest to the spans
    that name that agent or that model when they start."""

    question: Mapping[str, AttributeValue]
    by_agent: Mapping[str, Mapping[str, AttributeValue]] = field(default_factory=dict)
    by_model: Mapping[str, Mapping[str, AttributeValue]] = field(default_factory=dict)


_agent_run: ContextVar[AgentRunAttributes | None] = ContextVar("agent_run", default=None)


@contextmanager
def agent_run_attributes(run: AgentRunAttributes) -> Iterator[None]:
    token = _agent_run.set(run)
    try:
        yield
    finally:
        _agent_run.reset(token)


def _bare_model(model: str) -> str:
    """LiteLLM names a model with its route, such as `ollama_chat/qwen3.5:9B`."""
    return model.rsplit("/", 1)[-1]


def _agent_or_model(
    run: AgentRunAttributes, span_name: str, attributes: Mapping[str, object]
) -> Mapping[str, AttributeValue]:
    """The agent's or model's attributes, found from the span's attributes or, when the
    framework sets those after the span starts, from its name, such as `invoke_agent analyst`
    or `generate_content ollama_chat/qwen3.5:9B`."""
    named = span_name.split(" ", 1)[1] if " " in span_name else ""
    for agent in (attributes.get(GEN_AI_AGENT_NAME_ATTRIBUTE), named):
        if isinstance(agent, str) and agent in run.by_agent:
            return run.by_agent[agent]
    for model in (attributes.get(GEN_AI_REQUEST_MODEL_ATTRIBUTE), named):
        if isinstance(model, str) and _bare_model(model) in run.by_model:
            return run.by_model[_bare_model(model)]
    return {}


class AgentRunAttributesProcessor(SpanProcessor):
    """Adds the question's attributes to the GenAI spans of frameworks that have no per-agent
    trace attributes. An attribute the framework already set when the span started is kept."""

    def on_start(self, span: Span, parent_context: otel_context.Context | None = None) -> None:
        run = _agent_run.get()
        if run is None or not span.name.startswith(GEN_AI_SPAN_PREFIXES):
            return
        attributes = span.attributes or {}
        added: dict[str, AttributeValue] = dict(run.question)
        added.update(_agent_or_model(run, span.name, attributes))
        span.set_attributes({key: value for key, value in added.items() if key not in attributes})


_question_id: ContextVar[str | None] = ContextVar("question_id", default=None)


@contextmanager
def question_logging(question_id: str) -> Iterator[None]:
    """Log records written inside, including from tool threads, carry the question ID."""
    token = _question_id.set(question_id)
    try:
        yield
    finally:
        _question_id.reset(token)


class QuestionIdFilter(logging.Filter):
    """Hands the OTLP handler a copy of the record with the question ID, and without the
    console correlation fields, which repeat the record's own trace context."""

    def filter(self, record: logging.LogRecord) -> logging.LogRecord:
        exported = copy.copy(record)
        for name in CONSOLE_CORRELATION_FIELDS:
            exported.__dict__.pop(name, None)
        question_id = _question_id.get()
        if question_id is not None:
            setattr(exported, QUESTION_ID_ATTRIBUTE, question_id)
        return exported


class QuestionIdLogProcessor(LogRecordProcessor):
    """Adds the question ID to log records that frameworks emit straight to the logger
    provider, such as GenAI inference events, which the logging filter never sees."""

    def on_emit(self, log_record: ReadWriteLogRecord) -> None:
        question_id = _question_id.get()
        record = log_record.log_record
        attributes = dict(record.attributes or {})
        if question_id is not None and QUESTION_ID_ATTRIBUTE not in attributes:
            record.attributes = {**attributes, QUESTION_ID_ATTRIBUTE: question_id}

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def install_logging(provider: LoggerProvider) -> None:
    """Route standard logging into `provider`. The example's loggers log at INFO, and each
    record written for a question carries its ID as an attribute."""
    set_logger_provider(provider)
    handler = LoggingHandler(logger_provider=provider)
    handler.addFilter(QuestionIdFilter())
    logging.getLogger().addHandler(handler)
    logging.getLogger(TRUNCATION_LOGGER_NAME).setLevel(logging.ERROR)
    logging.getLogger(APP_LOGGER_NAME).setLevel(logging.INFO)


def correlate_console_logs() -> None:
    """With `OTEL_PYTHON_LOG_CORRELATION=true`, console log lines carry the trace and span ID.
    The logging instrumentation adds them to each record, and a console handler prints them in
    its default format. The console handler goes on the root logger first, so the
    instrumentation's own `basicConfig` does nothing. Contrib 0.63b1, which ADK pins, injects the
    IDs only with `set_logging_format`; later releases also take `inject_trace_context`. Its own
    OTLP handler stays off, because the root logger already has one."""
    if os.environ.get(LOG_CORRELATION_VARIABLE, "false").strip().lower() != "true":
        return
    console = logging.StreamHandler()
    console.name = CONSOLE_HANDLER_NAME
    console.setFormatter(logging.Formatter(DEFAULT_LOGGING_FORMAT))
    logging.getLogger().addHandler(console)
    LoggingInstrumentor().instrument(
        set_logging_format=True,
        inject_trace_context=True,
        enable_log_auto_instrumentation=False,
    )


def instrument_libraries() -> None:
    """psycopg is instrumented globally. httpx is instrumented per client by the SEC client,
    because the Ollama client also uses httpx and its calls are already `chat` spans."""
    PsycopgInstrumentor().instrument()


def configure_telemetry() -> None:
    """Export over OTLP to `OTEL_EXPORTER_OTLP_ENDPOINT`, with every exporter, processor and
    reader setting read from the standard variables."""
    apply_content_capture_setting()
    resource = build_resource()
    trace.set_tracer_provider(
        build_tracer_provider(
            CostAndErrorAttributingSpanExporter(OTLPSpanExporter(), MODEL_PROVIDER), resource
        )
    )
    metrics.set_meter_provider(
        build_meter_provider(PeriodicExportingMetricReader(OTLPMetricExporter()), resource)
    )
    install_logging(build_logger_provider(OTLPLogExporter(), resource))
    correlate_console_logs()
    instrument_libraries()


def instrument_fastapi_app(app: FastAPI) -> None:
    FastAPIInstrumentor.instrument_app(app)
