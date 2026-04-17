"""End-to-end tests for the /api/articles CRUD surface.

These tests intentionally hit the full ASGI stack (controller → repository →
SQLAlchemy → SQLite) so any regression in routing, DTO validation, session
handling, or persistence shows up as a test failure — not a runtime 500.
"""

from litestar.testing import AsyncTestClient


async def test_create_article_returns_201_with_body(
    client: AsyncTestClient,
) -> None:
    payload = {"title": "Observability primer", "body": "spans, metrics, logs"}

    response = await client.post("/api/articles", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["title"] == payload["title"]
    assert body["body"] == payload["body"]
    assert "created_at" in body
    assert "updated_at" in body


async def test_get_article_returns_persisted_record(
    client: AsyncTestClient,
) -> None:
    created = (
        await client.post("/api/articles", json={"title": "T", "body": "B"})
    ).json()

    response = await client.get(f"/api/articles/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_get_article_missing_returns_404(client: AsyncTestClient) -> None:
    response = await client.get("/api/articles/9999")

    assert response.status_code == 404


async def test_list_articles_supports_pagination(
    client: AsyncTestClient,
) -> None:
    for i in range(5):
        await client.post("/api/articles", json={"title": f"t{i}", "body": f"b{i}"})

    page = await client.get("/api/articles?limit=2&offset=2")

    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 2
    assert len(body["items"]) == 2


async def test_update_article_changes_fields(client: AsyncTestClient) -> None:
    created = (
        await client.post("/api/articles", json={"title": "old", "body": "old body"})
    ).json()

    response = await client.put(
        f"/api/articles/{created['id']}",
        json={"title": "new", "body": "new body"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "new"
    assert body["body"] == "new body"
    assert body["updated_at"] >= created["updated_at"]


async def test_update_article_missing_returns_404(
    client: AsyncTestClient,
) -> None:
    response = await client.put("/api/articles/9999", json={"title": "x", "body": "y"})

    assert response.status_code == 404


async def test_delete_article_returns_204_then_404(
    client: AsyncTestClient,
) -> None:
    created = (
        await client.post("/api/articles", json={"title": "tmp", "body": "tmp"})
    ).json()

    delete = await client.delete(f"/api/articles/{created['id']}")
    assert delete.status_code == 204

    follow_up = await client.get(f"/api/articles/{created['id']}")
    assert follow_up.status_code == 404


async def test_delete_article_missing_returns_404(
    client: AsyncTestClient,
) -> None:
    response = await client.delete("/api/articles/9999")

    assert response.status_code == 404
