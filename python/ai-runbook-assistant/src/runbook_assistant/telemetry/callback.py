"""Custom OpenTelemetry callback handler for LangChain.

Translates LangChain's run lifecycle (run_id / parent_run_id tree) into an OTel
span tree carrying GenAI semantic convention attributes and metrics. Parent
context is taken from the stored parent span, NOT the ambient context, because
callbacks may fire across threads / await boundaries.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from runbook_assistant.config import get_settings
from runbook_assistant.cost import calculate_cost
from runbook_assistant.llm import FALLBACK, SERVED_MODEL, SERVED_PROVIDER
from runbook_assistant.pii import scrub
from runbook_assistant.providers import semconv_name, server_endpoint
from runbook_assistant.telemetry.context import current_retrieval_context
from runbook_assistant.telemetry.metrics import get_metrics


INPUT_MAX_CHARS = 1000
SYSTEM_MAX_CHARS = 500
OUTPUT_MAX_CHARS = 2000

DETAILS_EVENT = "gen_ai.client.inference.operation.details"


class _RunState:
    __slots__ = (
        "max_tokens",
        "messages",
        "model",
        "owns_span",
        "provider",
        "span",
        "start",
        "temperature",
    )

    def __init__(self, span: Span, start: float, owns_span: bool = True) -> None:
        self.span = span
        self.start = start
        self.owns_span = owns_span
        self.provider = "unknown"
        self.model = "unknown"
        self.temperature: float | None = None
        self.max_tokens: int | None = None
        self.messages: list[dict[str, str]] = []


class OTelCallbackHandler(BaseCallbackHandler):
    def __init__(
        self,
        *,
        tracer: trace.Tracer | None = None,
        agent_name: str = "agent",
        data_source_id: str = "knowledge_base",
        conversation_id: str | None = None,
        data_source_address: str | None = None,
        data_source_port: int | None = None,
    ) -> None:
        self._tracer = tracer or trace.get_tracer("langchain.callback")
        self._agent_name = agent_name
        self._data_source_id = data_source_id
        self._conversation_id = conversation_id
        self._data_source_address = data_source_address
        self._data_source_port = data_source_port
        self._runs: dict[UUID, _RunState] = {}
        self._metrics = get_metrics()
        settings = get_settings()
        self._capture = settings.capture_content
        self._ollama_base_url = settings.ollama_base_url

    def _parent_ctx(self, parent_run_id: UUID | None) -> otel_context.Context | None:
        if parent_run_id is not None and parent_run_id in self._runs:
            return trace.set_span_in_context(self._runs[parent_run_id].span)
        return None

    def _start(self, run_id: UUID, parent_run_id: UUID | None, name: str, kind: SpanKind) -> Span:
        span = self._tracer.start_span(name, context=self._parent_ctx(parent_run_id), kind=kind)
        self._runs[run_id] = _RunState(span, time.perf_counter())
        return span

    def _end(self, run_id: UUID) -> _RunState | None:
        state = self._runs.pop(run_id, None)
        if state is not None and state.owns_span:
            state.span.end()
        return state

    def _error(self, run_id: UUID, error: BaseException) -> None:
        state = self._runs.pop(run_id, None)
        if state is None or not state.owns_span:
            return
        span = state.span
        span.record_exception(error)
        span.set_attribute("error.type", type(error).__qualname__)
        span.set_status(Status(StatusCode.ERROR, str(error)))
        span.end()

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if parent_run_id is None:
            span = self._start(run_id, None, f"invoke_agent {self._agent_name}", SpanKind.INTERNAL)
            span.set_attribute("gen_ai.operation.name", "invoke_agent")
            span.set_attribute("gen_ai.agent.name", self._agent_name)
            if self._conversation_id:
                span.set_attribute("gen_ai.conversation.id", self._conversation_id)
            if tags:
                span.set_attribute("langchain.tags", list(tags))
        else:
            # Skip the span for intermediate LangGraph nodes; pass-through keeps
            # child spans nested under the nearest real ancestor.
            parent = self._runs.get(parent_run_id)
            if parent is not None:
                self._runs[run_id] = _RunState(parent.span, parent.start, owns_span=False)

    def on_chain_end(self, outputs: dict[str, Any], *, run_id: UUID, **kwargs: Any) -> None:
        self._end(run_id)

    def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._error(run_id, error)

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._start_llm(run_id, parent_run_id, metadata, messages_to_dicts(messages))

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._start_llm(
            run_id,
            parent_run_id,
            metadata,
            [{"role": "user", "content": p} for p in prompts],
        )

    def _start_llm(
        self,
        run_id: UUID,
        parent_run_id: UUID | None,
        metadata: dict[str, Any] | None,
        messages: list[dict[str, str]],
    ) -> None:
        meta = metadata or {}
        model = str(meta.get("ls_model_name", "unknown"))
        provider = semconv_name(str(meta.get("ls_provider", "unknown")))
        span = self._start(run_id, parent_run_id, f"chat {model}", SpanKind.CLIENT)
        span.set_attribute("gen_ai.operation.name", "chat")
        self._set_provider(span, provider, model)
        temperature = meta.get("ls_temperature")
        if temperature is not None:
            span.set_attribute("gen_ai.request.temperature", temperature)
        max_tokens = meta.get("ls_max_tokens")
        if max_tokens is not None:
            span.set_attribute("gen_ai.request.max_tokens", max_tokens)

        state = self._runs[run_id]
        state.provider = provider
        state.model = model
        state.temperature = temperature
        state.max_tokens = max_tokens
        if self._capture:
            state.messages = [{"role": m["role"], "content": scrub(m["content"])} for m in messages]

    def _set_provider(self, span: Span, provider: str, model: str) -> None:
        span.set_attribute("gen_ai.provider.name", provider)
        span.set_attribute("gen_ai.request.model", model)
        address, port = server_endpoint(provider, self._ollama_base_url)
        if address is not None:
            span.set_attribute("server.address", address)
        if port is not None:
            span.set_attribute("server.port", port)

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        state = self._runs.pop(run_id, None)
        if state is None:
            return
        served = response.llm_output or {}
        switch = served.get(FALLBACK)
        provider = str(served.get(SERVED_PROVIDER, state.provider))
        model = str(served.get(SERVED_MODEL, state.model))
        elapsed = time.perf_counter() - state.start
        if switch:
            # The primary provider failed, so it keeps a span of its own and the
            # provider that answered gets a second span beside it.
            self._fail_primary(state, switch)
            elapsed -= float(switch["primary_seconds"])
            span = self._start_fallback_span(parent_run_id, state, provider, model, switch)
        else:
            span = state.span

        in_tok, out_tok, finish, resp_model, resp_id = _usage_from_result(response)
        if resp_model:
            span.set_attribute("gen_ai.response.model", resp_model)
        if resp_id:
            span.set_attribute("gen_ai.response.id", resp_id)
        if finish:
            span.set_attribute("gen_ai.response.finish_reasons", [finish])
        span.set_attribute("gen_ai.usage.input_tokens", in_tok)
        span.set_attribute("gen_ai.usage.output_tokens", out_tok)

        attrs: dict[str, Any] = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": provider,
            "gen_ai.request.model": model,
        }
        self._metrics.record_tokens(attrs, in_tok, out_tok)
        self._metrics.record_duration(attrs, elapsed)
        cost = calculate_cost(model, in_tok, out_tok)
        span.set_attribute("base14.gen_ai.cost_usd", cost)
        self._metrics.add_cost(attrs, cost)

        self._emit_details(span, state, _output_text(response))
        self._record_fallback(span, parent_run_id, switch)
        span.end()

    def _fail_primary(self, state: _RunState, switch: dict[str, Any]) -> None:
        """Close the primary provider's span as failed, at the moment it gave up."""
        span = state.span
        exc = switch.get("exception")
        error_type = str(switch["error.type"])
        if isinstance(exc, BaseException):
            span.record_exception(exc)
        span.set_attribute("error.type", error_type)
        span.set_status(Status(StatusCode.ERROR, str(exc) if exc else error_type))
        self._metrics.record_duration(
            {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": state.provider,
                "gen_ai.request.model": state.model,
                "error.type": error_type,
            },
            float(switch["primary_seconds"]),
        )
        self._emit_details(span, state, None)
        span.end(end_time=int(switch["switched_ns"]))

    def _start_fallback_span(
        self,
        parent_run_id: UUID | None,
        state: _RunState,
        provider: str,
        model: str,
        switch: dict[str, Any],
    ) -> Span:
        """Open the span for the provider that answered, beside the failed one."""
        span = self._tracer.start_span(
            f"chat {model}",
            context=self._parent_ctx(parent_run_id),
            kind=SpanKind.CLIENT,
            start_time=int(switch["switched_ns"]),
        )
        span.set_attribute("gen_ai.operation.name", "chat")
        self._set_provider(span, provider, model)
        if state.temperature is not None:
            span.set_attribute("gen_ai.request.temperature", state.temperature)
        if state.max_tokens is not None:
            span.set_attribute("gen_ai.request.max_tokens", state.max_tokens)
        return span

    def _emit_details(self, span: Span, state: _RunState, output: str | None) -> None:
        """One inference event per call, only when content capture is on."""
        if not self._capture:
            return
        inputs = [m for m in state.messages if m["role"] != "system"]
        systems = [m["content"] for m in state.messages if m["role"] == "system"]
        attributes: dict[str, Any] = {}
        if inputs:
            attributes["gen_ai.input.messages"] = json.dumps(inputs)[:INPUT_MAX_CHARS]
        if systems:
            attributes["gen_ai.system_instructions"] = "\n".join(systems)[:SYSTEM_MAX_CHARS]
        if output:
            attributes["gen_ai.output.messages"] = json.dumps(
                [{"role": "assistant", "content": scrub(output)}]
            )[:OUTPUT_MAX_CHARS]
        if attributes:
            span.add_event(DETAILS_EVENT, attributes)

    def _record_fallback(
        self, span: Span, parent_run_id: UUID | None, switch: dict[str, Any] | None
    ) -> None:
        """Report a provider switch on the parent without failing it."""
        if not switch:
            return
        parent = self._runs.get(parent_run_id) if parent_run_id else None
        target = parent.span if parent is not None else span
        target.add_event(
            "provider_fallback",
            {
                "gen_ai.provider.name": str(switch["from"]),
                "base14.gen_ai.fallback.provider": str(switch["to"]),
                "error.type": str(switch["error.type"]),
            },
        )
        target.set_attribute("gen_ai.fallback.triggered", True)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        state = self._runs.get(run_id)
        if state is not None:
            self._metrics.record_duration(
                {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.provider.name": state.provider,
                    "gen_ai.request.model": state.model,
                    "error.type": type(error).__qualname__,
                },
                time.perf_counter() - state.start,
            )
            self._emit_details(state.span, state, None)
        self._metrics.add_error(
            {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": state.provider if state else "unknown",
                "gen_ai.request.model": state.model if state else "unknown",
                "error.type": type(error).__qualname__,
            }
        )
        self._error(run_id, error)

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        name = (serialized or {}).get("name") or "tool"
        span = self._start(run_id, parent_run_id, f"execute_tool {name}", SpanKind.INTERNAL)
        span.set_attribute("gen_ai.operation.name", "execute_tool")
        span.set_attribute("gen_ai.tool.name", name)
        span.set_attribute("gen_ai.tool.type", "function")
        call_id = kwargs.get("tool_call_id")
        if call_id:
            span.set_attribute("gen_ai.tool.call.id", str(call_id))
        if self._capture and input_str:
            span.set_attribute("gen_ai.tool.call.arguments", scrub(input_str))

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._end(run_id)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._error(run_id, error)
        parent = self._runs.get(parent_run_id) if parent_run_id else None
        if parent is not None:
            parent.span.add_event("tool_execution_failed", {"error.type": type(error).__qualname__})

    def on_retriever_start(
        self,
        serialized: dict[str, Any],
        query: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        span = self._start(
            run_id, parent_run_id, f"retrieval {self._data_source_id}", SpanKind.CLIENT
        )
        span.set_attribute("gen_ai.operation.name", "retrieval")
        span.set_attribute("gen_ai.data_source.id", self._data_source_id)
        if self._data_source_address:
            span.set_attribute("server.address", self._data_source_address)
        if self._data_source_port:
            span.set_attribute("server.port", self._data_source_port)
        if self._capture and query:
            span.set_attribute("gen_ai.retrieval.query.text", scrub(query))
        current_retrieval_context.set(trace.set_span_in_context(span))

    def on_retriever_end(self, documents: Sequence[Any], *, run_id: UUID, **kwargs: Any) -> None:
        current_retrieval_context.set(None)
        state = self._runs.get(run_id)
        if state is not None:
            state.span.set_attribute("app.retrieval.chunk_count", len(documents or []))
        self._end(run_id)

    def on_retriever_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        current_retrieval_context.set(None)
        self._error(run_id, error)
        parent = self._runs.get(parent_run_id) if parent_run_id else None
        if parent is not None:
            parent.span.record_exception(error)
            parent.span.add_event(
                "rag_retrieval_degraded", {"error.type": type(error).__qualname__}
            )


def messages_to_dicts(messages: list[list[Any]]) -> list[dict[str, str]]:
    roles = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}
    out: list[dict[str, str]] = []
    for batch in messages:
        for m in batch:
            content = getattr(m, "content", "")
            text = content if isinstance(content, str) else str(content)
            mtype = getattr(m, "type", "") or "user"
            out.append({"role": roles.get(mtype, mtype), "content": text})
    return out


def _usage_from_result(response: LLMResult) -> tuple[int, int, str | None, str | None, str | None]:
    """Extract (input_tokens, output_tokens, finish_reason, response_model, response_id)."""
    in_tok = out_tok = 0
    finish: str | None = None
    resp_model: str | None = None
    resp_id: str | None = None
    try:
        gen = response.generations[0][0]
        msg = getattr(gen, "message", None)
        usage = getattr(msg, "usage_metadata", None) if msg else None
        if usage:
            in_tok = int(usage.get("input_tokens", 0))
            out_tok = int(usage.get("output_tokens", 0))
        meta = getattr(msg, "response_metadata", {}) if msg else {}
        # Ollama uses done_reason; cloud providers use stop_reason/finish_reason.
        finish = meta.get("done_reason") or meta.get("stop_reason") or meta.get("finish_reason")
        resp_model = meta.get("model_name") or meta.get("model")
        # Only a provider-issued id; LangChain's own run id is not a response id.
        resp_id = meta.get("id")
    except IndexError, AttributeError:
        pass
    if (in_tok == 0 and out_tok == 0) and response.llm_output:
        tu = response.llm_output.get("token_usage") or response.llm_output.get("usage") or {}
        in_tok = int(tu.get("prompt_tokens", tu.get("input_tokens", 0)))
        out_tok = int(tu.get("completion_tokens", tu.get("output_tokens", 0)))
    return in_tok, out_tok, finish, resp_model, resp_id


def _output_text(response: LLMResult) -> str | None:
    try:
        gen = response.generations[0][0]
        msg = getattr(gen, "message", None)
        content = getattr(msg, "content", None) if msg else getattr(gen, "text", None)
        if not content:
            return None
        return content if isinstance(content, str) else str(content)
    except IndexError, AttributeError:
        return None
