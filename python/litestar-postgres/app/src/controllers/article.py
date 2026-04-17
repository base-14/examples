"""Article CRUD controller.

Each handler is a thin shell around the repository. msgspec Structs handle
request validation and response serialisation. The OpenTelemetry ASGI +
SQLAlchemy auto-instrumentation produces an HTTP server span per request and a
nested DB span per query — this is what makes the trace waterfall in Scout
useful for diagnosing slow endpoints.
"""

import logging
from datetime import datetime

import msgspec
from advanced_alchemy.filters import LimitOffset
from litestar import Controller, delete, get, post, put
from litestar.di import Provide
from litestar.exceptions import NotFoundException
from litestar.params import Parameter
from opentelemetry import trace

from src.models import Article
from src.repository import ArticleRepository, provide_article_repo
from src.services.notification import NotificationService
from src.telemetry import articles_created

logger = logging.getLogger(__name__)


class ArticleCreate(msgspec.Struct):
    title: str
    body: str


class ArticleUpdate(msgspec.Struct):
    title: str
    body: str


class ArticleRead(msgspec.Struct):
    id: int
    title: str
    body: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, a: Article) -> "ArticleRead":
        return cls(
            id=a.id,
            title=a.title,
            body=a.body,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )


class ArticleListResponse(msgspec.Struct):
    items: list[ArticleRead]
    total: int
    limit: int
    offset: int


class ArticleController(Controller):
    path = "/api/articles"
    dependencies = {"repo": Provide(provide_article_repo)}

    @post("/")
    async def create(
        self,
        data: ArticleCreate,
        repo: ArticleRepository,
        notification_service: NotificationService,
    ) -> ArticleRead:
        article = await repo.add(
            Article(title=data.title, body=data.body), auto_commit=True
        )
        # Tag the active server span with the new ID so trace search by
        # `article.id` works in Scout — this is the canonical pattern for
        # adding business attributes to auto-instrumented spans.
        trace.get_current_span().set_attribute("article.id", article.id)
        articles_created.add(1)
        logger.info("article created", extra={"article_id": article.id})
        # Fire-and-forget: trace continues into the notify service via the
        # outbound httpx span. We swallow `Exception` (not BaseException) so
        # KeyboardInterrupt/SystemExit still propagate cleanly during shutdown.
        try:
            await notification_service.send(article_id=article.id, title=article.title)
        except Exception as exc:
            logger.warning(
                "notification dispatch failed",
                extra={"article_id": article.id, "error": str(exc)},
            )
        return ArticleRead.from_model(article)

    @get("/{article_id:int}")
    async def get_one(self, article_id: int, repo: ArticleRepository) -> ArticleRead:
        article = await repo.get_one_or_none(id=article_id)
        if article is None:
            raise NotFoundException(detail=f"Article {article_id} not found")
        return ArticleRead.from_model(article)

    @get("/")
    async def list_articles(
        self,
        repo: ArticleRepository,
        limit: int = Parameter(default=10, ge=1, le=100),
        offset: int = Parameter(default=0, ge=0),
    ) -> ArticleListResponse:
        items, total = await repo.list_and_count(
            LimitOffset(limit=limit, offset=offset)
        )
        return ArticleListResponse(
            items=[ArticleRead.from_model(a) for a in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    @put("/{article_id:int}")
    async def update(
        self,
        article_id: int,
        data: ArticleUpdate,
        repo: ArticleRepository,
    ) -> ArticleRead:
        article = await repo.get_one_or_none(id=article_id)
        if article is None:
            raise NotFoundException(detail=f"Article {article_id} not found")
        article.title = data.title
        article.body = data.body
        article = await repo.update(article, auto_commit=True)
        return ArticleRead.from_model(article)

    @delete("/{article_id:int}")
    async def remove(self, article_id: int, repo: ArticleRepository) -> None:
        article = await repo.get_one_or_none(id=article_id)
        if article is None:
            raise NotFoundException(detail=f"Article {article_id} not found")
        await repo.delete(article_id, auto_commit=True)
