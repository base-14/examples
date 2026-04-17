"""Repository layer — thin wrapper over advanced_alchemy.

Using `SQLAlchemyAsyncRepository` gives us list/get/add/update/delete plus
filter helpers (`LimitOffset`, etc.) without writing SQL by hand. The
`provide_article_repo` function is wired as a Litestar dependency so each
request gets a repo bound to its own session — keeping transactions isolated.
"""

from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Article


class ArticleRepository(SQLAlchemyAsyncRepository[Article]):
    model_type = Article


async def provide_article_repo(db_session: AsyncSession) -> ArticleRepository:
    return ArticleRepository(session=db_session)
