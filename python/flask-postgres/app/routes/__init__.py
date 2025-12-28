"""API route blueprints."""

from app.routes.articles import articles_bp
from app.routes.auth import auth_bp
from app.routes.health import health_bp


__all__ = ["health_bp", "auth_bp", "articles_bp"]
