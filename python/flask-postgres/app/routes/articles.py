"""Article CRUD endpoints."""

import logging

from flask import Blueprint, g, jsonify, request
from marshmallow import ValidationError

from app.errors import error_response
from app.extensions import db
from app.middleware.auth import token_optional, token_required
from app.models import Article, Favorite
from app.schemas import ArticleCreateSchema, ArticleSchema, ArticleUpdateSchema
from app.telemetry import get_meter, get_tracer


logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)
meter = get_meter(__name__)

articles_created = meter.create_counter(
    name="articles.created",
    description="Articles created",
    unit="1",
)

articles_bp = Blueprint("articles", __name__, url_prefix="/api/articles")


@articles_bp.route("/", methods=["GET"])
@token_optional
def list_articles():
    """List articles with optional search and pagination.

    Query params:
        search: Search term for title
        page: Page number (default 1)
        per_page: Items per page (default 20)

    Returns:
        JSON response with paginated articles.
    """
    search = request.args.get("search", "")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    query = db.session.query(Article)

    if search:
        query = query.filter(Article.title.ilike(f"%{search}%"))

    query = query.order_by(Article.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)  # type: ignore[attr-defined]

    # Serialize with favorited status
    current_user = getattr(g, "current_user", None)
    articles_data = []
    for article in pagination.items:
        article_dict = ArticleSchema().dump(article)
        article_dict["favorited"] = article.is_favorited_by(current_user)
        articles_data.append(article_dict)

    return jsonify(
        {
            "articles": articles_data,
            "total": pagination.total,
            "page": page,
            "per_page": per_page,
        }
    )


@articles_bp.route("/", methods=["POST"])
@token_required
def create_article():
    """Create a new article.

    Returns:
        JSON response with created article.
    """
    with tracer.start_as_current_span("article.create") as span:
        # Validate request data
        schema = ArticleCreateSchema()
        try:
            data = schema.load(request.get_json() or {})
        except ValidationError as err:
            return jsonify(err.messages), 400

        # Create article
        article = Article(
            title=data["title"],
            description=data.get("description", ""),
            body=data["body"],
            author_id=g.current_user.id,
        )
        article.generate_slug()

        db.session.add(article)
        db.session.commit()

        span.set_attribute("user.id", g.current_user.id)
        span.set_attribute("article.slug", article.slug)

        articles_created.add(1, {"author_id": str(g.current_user.id)})
        logger.info(f"Article created: {article.slug}", extra={"user_id": g.current_user.id})

        # Trigger background job for notification
        from app.jobs.tasks import send_article_notification

        send_article_notification.delay(article.id, "created")

        article_dict = ArticleSchema().dump(article)
        article_dict["favorited"] = False

        return jsonify(article_dict), 201


@articles_bp.route("/<slug>", methods=["GET"])
@token_optional
def get_article(slug: str):
    """Get a single article by slug.

    Args:
        slug: Article slug.

    Returns:
        JSON response with article data.
    """
    article = db.session.query(Article).filter(Article.slug == slug).first()
    if not article:
        return error_response("Article not found", 404)

    current_user = getattr(g, "current_user", None)
    article_dict = ArticleSchema().dump(article)
    article_dict["favorited"] = article.is_favorited_by(current_user)

    return jsonify(article_dict)


@articles_bp.route("/<slug>", methods=["PUT"])
@token_required
def update_article(slug: str):
    """Update an article.

    Args:
        slug: Article slug.

    Returns:
        JSON response with updated article.
    """
    with tracer.start_as_current_span("article.update") as span:
        article = db.session.query(Article).filter(Article.slug == slug).first()
        if not article:
            return error_response("Article not found", 404)

        # Check ownership
        if article.author_id != g.current_user.id:
            span.set_attribute("auth.status", "forbidden")
            return error_response("You can only update your own articles", 403)

        # Validate request data
        schema = ArticleUpdateSchema()
        try:
            data = schema.load(request.get_json() or {})
        except ValidationError as err:
            return jsonify(err.messages), 400

        # Update fields
        if "title" in data:
            article.title = data["title"]
        if "description" in data:
            article.description = data["description"]
        if "body" in data:
            article.body = data["body"]

        db.session.commit()

        span.set_attribute("article.slug", article.slug)
        logger.info(f"Article updated: {article.slug}", extra={"user_id": g.current_user.id})

        article_dict = ArticleSchema().dump(article)
        article_dict["favorited"] = article.is_favorited_by(g.current_user)

        return jsonify(article_dict)


@articles_bp.route("/<slug>", methods=["DELETE"])
@token_required
def delete_article(slug: str):
    """Delete an article.

    Args:
        slug: Article slug.

    Returns:
        Empty response with 204 status.
    """
    with tracer.start_as_current_span("article.delete") as span:
        article = db.session.query(Article).filter(Article.slug == slug).first()
        if not article:
            return error_response("Article not found", 404)

        # Check ownership
        if article.author_id != g.current_user.id:
            span.set_attribute("auth.status", "forbidden")
            return error_response("You can only delete your own articles", 403)

        span.set_attribute("article.slug", article.slug)

        db.session.delete(article)
        db.session.commit()

        logger.info(f"Article deleted: {slug}", extra={"user_id": g.current_user.id})

        return "", 204


@articles_bp.route("/<slug>/favorite", methods=["POST"])
@token_required
def favorite_article(slug: str):
    """Favorite an article.

    Args:
        slug: Article slug.

    Returns:
        JSON response with updated article.
    """
    with tracer.start_as_current_span("article.favorite") as span:
        article = db.session.query(Article).filter(Article.slug == slug).first()
        if not article:
            return error_response("Article not found", 404)

        # Check if already favorited
        existing = (
            db.session.query(Favorite)
            .filter(Favorite.user_id == g.current_user.id, Favorite.article_id == article.id)
            .first()
        )

        if existing:
            # Already favorited - return current state
            article_dict = ArticleSchema().dump(article)
            article_dict["favorited"] = True
            return jsonify(article_dict)

        # Create favorite
        favorite = Favorite(user_id=g.current_user.id, article_id=article.id)
        article.increment_favorites()

        db.session.add(favorite)
        db.session.commit()

        # Refresh to get updated count
        db.session.refresh(article)

        span.set_attribute("article.slug", article.slug)
        logger.info(f"Article favorited: {slug}", extra={"user_id": g.current_user.id})

        article_dict = ArticleSchema().dump(article)
        article_dict["favorited"] = True

        return jsonify(article_dict)


@articles_bp.route("/<slug>/favorite", methods=["DELETE"])
@token_required
def unfavorite_article(slug: str):
    """Unfavorite an article.

    Args:
        slug: Article slug.

    Returns:
        JSON response with updated article.
    """
    with tracer.start_as_current_span("article.unfavorite") as span:
        article = db.session.query(Article).filter(Article.slug == slug).first()
        if not article:
            return error_response("Article not found", 404)

        # Find favorite
        favorite = (
            db.session.query(Favorite)
            .filter(Favorite.user_id == g.current_user.id, Favorite.article_id == article.id)
            .first()
        )

        if favorite:
            article.decrement_favorites()
            db.session.delete(favorite)
            db.session.commit()

            # Refresh to get updated count
            db.session.refresh(article)

        span.set_attribute("article.slug", article.slug)
        logger.info(f"Article unfavorited: {slug}", extra={"user_id": g.current_user.id})

        article_dict = ArticleSchema().dump(article)
        article_dict["favorited"] = False

        return jsonify(article_dict)
