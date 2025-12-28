import logging

from django.db import IntegrityError
from opentelemetry import trace
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.telemetry import get_meter, get_tracer
from apps.jobs.tasks import send_article_notification

from .models import Article, Favorite
from .serializers import (
    ArticleCreateSerializer,
    ArticleListSerializer,
    ArticleSerializer,
    ArticleUpdateSerializer,
)

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)
meter = get_meter(__name__)

articles_created = meter.create_counter(
    name="articles.created",
    description="Articles created",
    unit="1",
)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticatedOrReadOnly])
def article_list(request: Request) -> Response:
    if request.method == "GET":
        return list_articles(request)
    return create_article(request)


def list_articles(request: Request) -> Response:
    articles = Article.objects.select_related("author").all()

    search = request.query_params.get("search")
    if search:
        articles = articles.filter(title__icontains=search)

    author = request.query_params.get("author")
    if author:
        articles = articles.filter(author__email=author)

    limit = int(request.query_params.get("limit", 20))
    offset = int(request.query_params.get("offset", 0))
    articles = articles[offset : offset + limit]

    serializer = ArticleListSerializer(articles, many=True, context={"request": request})
    logger.info(f"Listed {len(serializer.data)} articles", extra={"count": len(serializer.data)})
    return Response({"articles": serializer.data, "count": len(serializer.data)})


def create_article(request: Request) -> Response:
    with tracer.start_as_current_span("article.create") as span:
        serializer = ArticleCreateSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Article validation failed: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        article = serializer.save(author=request.user)
        span.set_attribute("article.slug", article.slug)
        span.set_attribute("user.id", request.user.id)

        articles_created.add(1, {"author_id": str(request.user.id)})

        send_article_notification.delay(article.id, "created")

        logger.info(
            f"Article created: {article.slug}",
            extra={"article_slug": article.slug, "author_id": request.user.id},
        )

        return Response(
            ArticleSerializer(article, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAuthenticatedOrReadOnly])
def article_detail(request: Request, slug: str) -> Response:
    try:
        article = Article.objects.select_related("author").get(slug=slug)
    except Article.DoesNotExist:
        return Response({"error": "Article not found"}, status=status.HTTP_404_NOT_FOUND)

    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("article.slug", slug)
        span.set_attribute("article.id", article.id)

    if request.method == "GET":
        return Response(ArticleSerializer(article, context={"request": request}).data)

    if request.method == "PUT":
        return update_article(request, article)

    return delete_article(request, article)


def update_article(request: Request, article: Article) -> Response:
    if article.author_id != request.user.id:
        logger.warning(f"Unauthorized update attempt on {article.slug} by user {request.user.id}")
        return Response(
            {"error": "You can only edit your own articles"},
            status=status.HTTP_403_FORBIDDEN,
        )

    with tracer.start_as_current_span("article.update") as span:
        serializer = ArticleUpdateSerializer(article, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        article = serializer.save()
        span.set_attribute("article.slug", article.slug)

        logger.info(f"Article updated: {article.slug}", extra={"article_slug": article.slug})
        return Response(ArticleSerializer(article, context={"request": request}).data)


def delete_article(request: Request, article: Article) -> Response:
    if article.author_id != request.user.id:
        logger.warning(f"Unauthorized delete attempt on {article.slug} by user {request.user.id}")
        return Response(
            {"error": "You can only delete your own articles"},
            status=status.HTTP_403_FORBIDDEN,
        )

    with tracer.start_as_current_span("article.delete") as span:
        span.set_attribute("article.slug", article.slug)
        slug = article.slug
        article.delete()
        logger.info(f"Article deleted: {slug}", extra={"article_slug": slug})
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST", "DELETE"])
@permission_classes([IsAuthenticated])
def favorite_article(request: Request, slug: str) -> Response:
    try:
        article = Article.objects.get(slug=slug)
    except Article.DoesNotExist:
        return Response({"error": "Article not found"}, status=status.HTTP_404_NOT_FOUND)

    with tracer.start_as_current_span("article.favorite") as span:
        span.set_attribute("article.slug", slug)
        span.set_attribute("user.id", request.user.id)
        span.set_attribute("action", "favorite" if request.method == "POST" else "unfavorite")

        if request.method == "POST":
            try:
                Favorite.objects.create(user=request.user, article=article)
                article.increment_favorites()
            except IntegrityError:
                return Response(
                    {"error": "Already favorited"},
                    status=status.HTTP_409_CONFLICT,
                )
        else:
            deleted, _ = Favorite.objects.filter(user=request.user, article=article).delete()
            if deleted:
                article.decrement_favorites()

        article.refresh_from_db()
        return Response(ArticleSerializer(article, context={"request": request}).data)
