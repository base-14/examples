"""pgvector retriever backed by local Ollama embeddings (embeddinggemma)."""

from pathlib import Path
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever
from opentelemetry import trace


class CountingRetriever(VectorStoreRetriever):
    """Records how many chunks came back on the retrieval span, which is current while it runs."""

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun, **kwargs: Any
    ) -> list[Document]:
        docs = super()._get_relevant_documents(query, run_manager=run_manager, **kwargs)
        trace.get_current_span().set_attribute("app.retrieval.chunk_count", len(docs))
        return docs


def _runbook_dir() -> Path:
    return Path(__file__).parent / "data" / "runbooks"


def build_retriever(connection_string: str) -> tuple[Any, Any]:
    from langchain_ollama import OllamaEmbeddings
    from langchain_postgres import PGVector

    from runbook_assistant.config import get_settings
    from runbook_assistant.embeddings import InstrumentedEmbeddings

    s = get_settings()
    embeddings = InstrumentedEmbeddings(
        inner=OllamaEmbeddings(model=s.embedding_model, base_url=s.ollama_base_url),
        model=s.embedding_model,
        provider="ollama",
        base_url=s.ollama_base_url,
    )
    store = PGVector(
        embeddings=embeddings,
        collection_name="runbooks",
        connection=connection_string,
        use_jsonb=True,
    )
    return CountingRetriever(vectorstore=store, search_kwargs={"k": 3}), store


def seed_runbooks(store: Any) -> int:
    docs: list[Document] = []
    for path in sorted(_runbook_dir().glob("*.md")):
        if path.name == "ATTRIBUTION.md":
            continue
        text = path.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip() if text else path.stem
        docs.append(Document(page_content=text, metadata={"title": title, "source": path.name}))
    if docs:
        store.add_documents(docs)
    return len(docs)
