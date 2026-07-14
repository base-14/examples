import httpx
import pytest


pytest.importorskip("testcontainers.postgres")


def _ollama_up() -> bool:
    try:
        return httpx.get("http://localhost:11434/api/tags", timeout=2).status_code == 200
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.skipif(not _ollama_up(), reason="needs Ollama with embeddinggemma")
def test_seed_and_search_returns_relevant_runbook():
    from testcontainers.postgres import PostgresContainer

    from runbook_assistant.retriever import build_retriever, seed_runbooks

    # Pass credentials explicitly: testcontainers falls back to POSTGRES_*
    # env vars, and an empty POSTGRES_PASSWORD in the host shell would make the
    # container refuse to initialize.
    with PostgresContainer(
        "pgvector/pgvector:pg18", username="test", password="test", dbname="test"
    ) as pg:
        conn = pg.get_connection_url().replace("psycopg2", "psycopg")
        retriever, store = build_retriever(conn)
        n = seed_runbooks(store)
        assert n >= 12
        docs = retriever.invoke("pods restarting with OOMKilled")
        assert any("OOM" in d.page_content for d in docs)
