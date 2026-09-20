from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever
from opentelemetry.trace import SpanKind, StatusCode
from pydantic import ConfigDict

from runbook_assistant.embeddings import InstrumentedEmbeddings
from runbook_assistant.telemetry.callback import OTelCallbackHandler


class _FakeEmbeddings(Embeddings):
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.error:
            raise self.error
        return [[0.1, 0.2] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        if self.error:
            raise self.error
        return [0.1, 0.2]


def _wrap(inner: Embeddings) -> InstrumentedEmbeddings:
    return InstrumentedEmbeddings(
        inner=inner,
        model="embeddinggemma",
        provider="ollama",
        base_url="http://host.docker.internal:11434",
    )


def test_embed_query_emits_a_client_span(span_exporter):
    assert _wrap(_FakeEmbeddings()).embed_query("disk full") == [0.1, 0.2]

    span = next(s for s in span_exporter.get_finished_spans() if s.name.startswith("embeddings "))
    assert span.name == "embeddings embeddinggemma"
    assert span.kind is SpanKind.CLIENT
    assert span.attributes["gen_ai.operation.name"] == "embeddings"
    assert span.attributes["gen_ai.provider.name"] == "ollama"
    assert span.attributes["gen_ai.request.model"] == "embeddinggemma"
    assert span.attributes["server.address"] == "host.docker.internal"
    assert span.attributes["server.port"] == 11434


def test_embedding_failure_marks_the_span(span_exporter):
    with pytest.raises(ConnectionError):
        _wrap(_FakeEmbeddings(ConnectionError("ollama down"))).embed_documents(["a"])

    span = next(s for s in span_exporter.get_finished_spans() if s.name.startswith("embeddings "))
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["error.type"] == "ConnectionError"
    assert any(e.name == "exception" for e in span.events)


class _EmbeddingRetriever(BaseRetriever):
    """Retriever that embeds the query, the way the vector store does."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    embeddings: Any

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        self.embeddings.embed_query(query)
        return [Document(page_content="runbook")]


def test_embeddings_span_is_a_child_of_the_retrieval_span(span_exporter):
    handler = OTelCallbackHandler(agent_name="runbook_assistant", data_source_id="runbooks")
    retriever = _EmbeddingRetriever(embeddings=_wrap(_FakeEmbeddings()))

    retriever.invoke("disk full", config={"callbacks": [handler]})

    spans = span_exporter.get_finished_spans()
    embeddings = next(s for s in spans if s.name.startswith("embeddings "))
    retrieval = next(s for s in spans if s.name == "retrieval runbooks")
    assert embeddings.parent is not None
    assert embeddings.parent.span_id == retrieval.context.span_id
    assert embeddings.context.trace_id == retrieval.context.trace_id
