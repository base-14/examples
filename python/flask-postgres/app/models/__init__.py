"""Database models."""

from app.models.article import Article, Favorite
from app.models.user import User


__all__ = ["User", "Article", "Favorite"]
