"""pgvector retriever backed by local Ollama embeddings (embeddinggemma)."""

from pathlib import Path
from typing import Any


def _runbook_dir() -> Path:
    return Path(__file__).parent / "data" / "runbooks"


def build_retriever(connection_string: str) -> tuple[Any, Any]:
    from langchain_ollama import OllamaEmbeddings
    from langchain_postgres import PGVector

    from runbook_assistant.config import get_settings

    s = get_settings()
    embeddings = OllamaEmbeddings(model=s.embedding_model, base_url=s.ollama_base_url)
    store = PGVector(
        embeddings=embeddings,
        collection_name="runbooks",
        connection=connection_string,
        use_jsonb=True,
    )
    return store.as_retriever(search_kwargs={"k": 3}), store


def seed_runbooks(store: Any) -> int:
    from langchain_core.documents import Document

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
