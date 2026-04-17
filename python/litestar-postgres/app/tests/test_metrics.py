"""Verify the articles.created counter is incremented on success.

We patch the controller's module-level reference rather than constructing a
real OTel MeterProvider — this keeps the test fast and avoids side-effects on
the global meter registry.
"""

from unittest.mock import MagicMock, patch

from litestar.testing import AsyncTestClient


async def test_articles_created_counter_increments_on_post(
    client: AsyncTestClient,
) -> None:
    with patch("src.controllers.article.articles_created") as counter:
        counter.add = MagicMock()

        response = await client.post(
            "/api/articles", json={"title": "metrics", "body": "see counter"}
        )

        assert response.status_code == 201
        counter.add.assert_called_once()
        args, kwargs = counter.add.call_args
        assert args[0] == 1
