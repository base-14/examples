"""Outbound notification client.

Calls the sibling `litestar-postgres-notify` service over HTTP. The httpx call is
auto-instrumented by `opentelemetry-instrumentation-httpx`, so the outbound
request inherits the active server-span context and propagates `traceparent`
headers — that is how the receiving service's spans end up in the same trace.

The httpx.AsyncClient is constructed once and reused across requests; opening
a fresh client per call is a connection-pool churn anti-pattern in real
systems. The Litestar `on_shutdown` hook (wired in `main.py`) calls `aclose`
to drain the pool cleanly.
"""

import httpx


class NotificationService:
    """Pooled httpx wrapper. Subclassed in tests to record/fail without network."""

    def __init__(self, url: str, timeout: float = 5.0) -> None:
        self.url = url
        self._client: httpx.AsyncClient | None = httpx.AsyncClient(timeout=timeout)

    async def send(self, *, article_id: int, title: str) -> None:
        assert self._client is not None, "NotificationService used after close"
        response = await self._client.post(
            self.url,
            json={"article_id": article_id, "title": title},
        )
        response.raise_for_status()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
