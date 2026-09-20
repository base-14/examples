"""The open retrieval span's context, shared with the embeddings client.

LangChain has no callback for embeddings, so the embedding client cannot see
the retrieval run it belongs to and would otherwise parent its span on whatever
is ambient, usually the HTTP server span. The callback handler publishes the
retrieval span's context here while the retrieval run is open.
"""

from contextvars import ContextVar

from opentelemetry.context import Context


current_retrieval_context: ContextVar[Context | None] = ContextVar(
    "current_retrieval_context", default=None
)
