"""Article-create → notification side-effect tests.

The notification call is fire-and-forget from the client's perspective: a 201
should come back even if the notify service is unreachable. We verify both
paths by swapping in a fake NotificationService via the app factory.
"""

from collections.abc import AsyncIterator

import pytest
from litestar.testing import AsyncTestClient
from sqlalchemy.ext.asyncio import create_async_engine

from src.main import create_app
from src.models import Base
from src.services.notification import NotificationService


class RecordingNotificationService(NotificationService):
    def __init__(self) -> None:
        self.url = "http://test/notify"
        self._client = None
        self.calls: list[dict] = []

    async def send(self, *, article_id: int, title: str) -> None:
        self.calls.append({"article_id": article_id, "title": title})

    async def aclose(self) -> None:
        return None


class FailingNotificationService(NotificationService):
    def __init__(self) -> None:
        self.url = "http://test/notify"
        self._client = None

    async def send(self, *, article_id: int, title: str) -> None:
        raise RuntimeError("notify down")

    async def aclose(self) -> None:
        return None


@pytest.fixture
async def recorder(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> AsyncIterator[tuple[AsyncTestClient, RecordingNotificationService]]:
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    monkeypatch.setenv("DATABASE_URL", db_url)
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    rec = RecordingNotificationService()
    app = create_app(notification_service=rec)
    async with AsyncTestClient(app=app) as c:
        yield c, rec


@pytest.fixture
async def failing_notifier(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> AsyncIterator[AsyncTestClient]:
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    monkeypatch.setenv("DATABASE_URL", db_url)
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    app = create_app(notification_service=FailingNotificationService())
    async with AsyncTestClient(app=app) as c:
        yield c


async def test_create_article_dispatches_notification(
    recorder: tuple[AsyncTestClient, RecordingNotificationService],
) -> None:
    client, rec = recorder

    response = await client.post(
        "/api/articles", json={"title": "trace me", "body": "..."}
    )

    assert response.status_code == 201
    article_id = response.json()["id"]
    assert rec.calls == [{"article_id": article_id, "title": "trace me"}]


async def test_create_article_returns_201_when_notification_fails(
    failing_notifier: AsyncTestClient,
) -> None:
    response = await failing_notifier.post(
        "/api/articles", json={"title": "still ok", "body": "..."}
    )

    assert response.status_code == 201
