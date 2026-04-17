from litestar.testing import AsyncTestClient


async def test_health_endpoint_returns_ok(client: AsyncTestClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "litestar-postgres-app"
