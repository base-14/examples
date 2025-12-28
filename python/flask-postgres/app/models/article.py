"""Article and Favorite models."""

import time
from datetime import datetime

from slugify import slugify
from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class Article(db.Model):
    """Article content model."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    favorites_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    author: Mapped["User"] = relationship("User", back_populates="articles")  # noqa: F821
    favorited_by: Mapped[list["Favorite"]] = relationship(
        "Favorite", back_populates="article", lazy="dynamic", cascade="all, delete-orphan"
    )

    def generate_slug(self) -> None:
        """Generate a unique slug from the title."""
        base_slug = slugify(self.title) if self.title else "article"
        timestamp = int(time.time() * 1000)
        self.slug = f"{base_slug}-{timestamp}"

    def is_favorited_by(self, user: "User") -> bool:  # noqa: F821
        """Check if this article is favorited by the given user.

        Args:
            user: User to check.

        Returns:
            True if favorited, False otherwise.
        """
        if not user:
            return False
        return (
            db.session.query(Favorite)
            .filter(Favorite.article_id == self.id, Favorite.user_id == user.id)
            .first()
            is not None
        )

    def increment_favorites(self) -> None:
        """Atomically increment favorites count."""
        self.favorites_count = Article.favorites_count + 1

    def decrement_favorites(self) -> None:
        """Atomically decrement favorites count."""
        if self.favorites_count > 0:
            self.favorites_count = Article.favorites_count - 1

    def __repr__(self) -> str:
        return f"<Article {self.slug}>"


class Favorite(db.Model):
    """User-Article favorite relationship model."""

    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "article_id", name="uq_user_article_favorite"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="favorites")  # noqa: F821
    article: Mapped["Article"] = relationship("Article", back_populates="favorited_by")

    def __repr__(self) -> str:
        return f"<Favorite user={self.user_id} article={self.article_id}>"
