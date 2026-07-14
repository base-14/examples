"""Agent tools: a RAG retriever tool + three fixture-backed SRE tools.

The non-RAG tools read deterministic data from data/fixtures/services.json so the
example runs offline and the captured trace is reproducible. Replace with real
Scout/Prometheus/Loki queries in production.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from langchain_core.tools import tool


@lru_cache
def _services() -> dict[str, Any]:
    path = Path(__file__).parent / "data" / "fixtures" / "services.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def build_search_runbooks(retriever: Any) -> Any:
    @tool
    def search_runbooks(query: str) -> str:
        """Search the SRE runbook knowledge base for relevant procedures."""
        docs = retriever.invoke(query)
        if not docs:
            return "No matching runbooks found."
        return "\n\n".join(
            f"# {d.metadata.get('title', 'runbook')}\n{d.page_content}" for d in docs
        )

    return search_runbooks


@tool
def query_metrics(service: str, metric: str) -> str:
    """Return a recent metric value for a service."""
    svc = _services().get(service)
    if not svc:
        return f"Unknown service '{service}'."
    val = svc["metrics"].get(metric, "n/a")
    return f"{service} {metric} = {val} (last 5m)"


@tool
def search_logs(service: str, pattern: str) -> str:
    """Search recent logs for a service matching a pattern."""
    svc = _services().get(service)
    if not svc:
        return f"Unknown service '{service}'."
    hits = [ln for ln in svc["logs"] if pattern.lower() in ln.lower()]
    if not hits:
        return f"No log lines matching '{pattern}' for {service}."
    return f"{len(hits)} match(es) for '{pattern}' in {service} logs:\n" + "\n".join(hits)


@tool
def get_service_status(service: str) -> str:
    """Return current deploy/health status for a service."""
    svc = _services().get(service)
    if not svc:
        return f"Unknown service '{service}'."
    st = svc["status"]
    restarts = ", ".join(st.get("recent_restarts", [])) or "none"
    return (
        f"{service}: {st['replicas_healthy']}/{st['replicas_total']} replicas healthy, "
        f"last deploy {st['last_deploy']}, recent restarts: {restarts}"
    )


def build_tools(retriever: Any) -> list[Any]:
    return [build_search_runbooks(retriever), query_metrics, search_logs, get_service_status]
