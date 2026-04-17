from litestar.testing import AsyncTestClient

from src.main import app


async def test_health_endpoint_returns_ok() -> None:
    async with AsyncTestClient(app=app) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "litestar-postgres-notify"}


async def test_notify_accepts_post_and_returns_200() -> None:
    payload = {"article_id": 42, "title": "hello world"}

    async with AsyncTestClient(app=app) as client:
        response = await client.post("/notify", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body["article_id"] == 42
