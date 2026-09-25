import os
from unittest.mock import patch

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.instrumented import InstrumentationSettings, instrument_model

from kyc_onboarding.telemetry import _capture_content_enabled


PROMPT_TEXT = "the applicant's secret passphrase is orion-9"
RESPONSE_TEXT = "the response contains vega-7"


def _respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart(RESPONSE_TEXT)])


def _run_agent_chat_span(*, include_content: bool) -> dict[str, object]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    settings = InstrumentationSettings(tracer_provider=provider, include_content=include_content)
    model = instrument_model(FunctionModel(_respond, model_name="probe"), settings)
    agent = Agent(model)

    agent.run_sync(PROMPT_TEXT)

    (chat_span,) = [s for s in exporter.get_finished_spans() if s.name.startswith("chat ")]
    assert chat_span.attributes is not None
    return dict(chat_span.attributes)


def test_content_capture_enabled_records_prompt_and_completion_text() -> None:
    attributes = _run_agent_chat_span(include_content=True)

    assert PROMPT_TEXT in str(attributes["gen_ai.input.messages"])
    assert RESPONSE_TEXT in str(attributes["gen_ai.output.messages"])


def test_content_capture_disabled_omits_prompt_and_completion_text() -> None:
    attributes = _run_agent_chat_span(include_content=False)

    assert PROMPT_TEXT not in str(attributes["gen_ai.input.messages"])
    assert RESPONSE_TEXT not in str(attributes["gen_ai.output.messages"])


def test_capture_content_enabled_by_default() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", None)
        assert _capture_content_enabled() is True


def test_capture_content_disabled_by_false() -> None:
    with patch.dict(os.environ, {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false"}):
        assert _capture_content_enabled() is False


def test_capture_content_disabled_is_case_insensitive() -> None:
    with patch.dict(os.environ, {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "FALSE"}):
        assert _capture_content_enabled() is False


def test_capture_content_enabled_for_other_values() -> None:
    with patch.dict(os.environ, {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"}):
        assert _capture_content_enabled() is True
