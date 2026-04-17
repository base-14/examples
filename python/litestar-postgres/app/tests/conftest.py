"""Shared pytest fixtures.

Tests run against an in-memory-ish SQLite database (file-backed under tmp_path
so the async driver can share the connection across tasks). The same
SQLAlchemy models work in both SQLite (tests) and PostgreSQL (runtime) — this
keeps the TDD loop fast without dragging in testcontainers.
"""

from collections.abc import AsyncIterator

import pytest
from litestar.testing import AsyncTestClient
from sqlalchemy.ext.asyncio import create_async_engine

from src.main import create_app
from src.models import Base
from src.services.notification import NotificationService


class _NoopNotificationService(NotificationService):
    """Default test notifier — never touches the network."""

    def __init__(self) -> None:
        self.url = "http://noop"
        self._client = None  # skip httpx pool creation

    async def send(self, *, article_id: int, title: str) -> None:
        return None

    async def aclose(self) -> None:
        return None


@pytest.fixture
async def client(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> AsyncIterator[AsyncTestClient]:
    db_path = tmp_path / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("NOTIFY_URL", "http://notify-test.local/notify")

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    app = create_app(notification_service=_NoopNotificationService())
    async with AsyncTestClient(app=app) as c:
        yield c
