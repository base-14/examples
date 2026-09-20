"""Embeddings client that emits an `embeddings {model}` span per call.

LangChain has no callback hook for embeddings, so the vector store's embedding
client is wrapped here instead. Ollama returns no token counts for embeddings,
so the span carries the request attributes and the duration metric only.
"""

import time
from collections.abc import Callable
from typing import Any

from langchain_core.embeddings import Embeddings
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from runbook_assistant.providers import server_endpoint
from runbook_assistant.telemetry.context import current_retrieval_context
from runbook_assistant.telemetry.metrics import get_metrics


class InstrumentedEmbeddings(Embeddings):
    """Wraps an embeddings client with GenAI semconv spans and metrics."""

    def __init__(
        self,
        inner: Embeddings,
        model: str,
        provider: str,
        base_url: str,
        tracer: trace.Tracer | None = None,
    ) -> None:
        self._inner = inner
        self._model = model
        self._provider = provider
        self._base_url = base_url
        self._tracer = tracer or trace.get_tracer("langchain.embeddings")
        self._metrics = get_metrics()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._traced(lambda: self._inner.embed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return self._traced(lambda: self._inner.embed_query(text))

    def _traced[T](self, call: Callable[[], T]) -> T:
        attrs: dict[str, Any] = {
            "gen_ai.operation.name": "embeddings",
            "gen_ai.provider.name": self._provider,
            "gen_ai.request.model": self._model,
        }
        address, port = server_endpoint(self._provider, self._base_url)
        span_attrs = dict(attrs)
        if address is not None:
            span_attrs["server.address"] = address
        if port is not None:
            span_attrs["server.port"] = port

        start = time.perf_counter()
        with self._tracer.start_as_current_span(
            f"embeddings {self._model}",
            context=current_retrieval_context.get(),
            kind=SpanKind.CLIENT,
            attributes=span_attrs,
        ) as span:
            try:
                return call()
            except Exception as exc:
                error_type = type(exc).__qualname__
                span.record_exception(exc)
                span.set_attribute("error.type", error_type)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                self._metrics.add_error({**attrs, "error.type": error_type})
                attrs["error.type"] = error_type
                raise
            finally:
                self._metrics.record_duration(attrs, time.perf_counter() - start)
