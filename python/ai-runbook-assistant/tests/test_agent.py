from typing import Any

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


class _ToolBindingFakeModel(FakeListChatModel):
    """FakeListChatModel that accepts bind_tools (the base raises
    NotImplementedError). It ignores the tools and returns a plain answer, so
    create_agent runs one model step and the agent loop ends — enough to assert
    the callback emits the root invoke_agent span without a real provider."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


def test_callback_produces_invoke_agent_span_with_fake_model():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    from langchain.agents import create_agent

    from runbook_assistant.telemetry.callback import OTelCallbackHandler
    from runbook_assistant.tools import query_metrics

    model = _ToolBindingFakeModel(responses=["checkout CPU is high; see runbook."])
    agent = create_agent(model=model, tools=[query_metrics])
    handler = OTelCallbackHandler(tracer=tracer, agent_name="runbook_assistant")

    agent.invoke(
        {"messages": [{"role": "user", "content": "why is checkout slow?"}]},
        config={"callbacks": [handler]},
    )
    names = [s.name for s in exporter.get_finished_spans()]
    assert "invoke_agent runbook_assistant" in names
