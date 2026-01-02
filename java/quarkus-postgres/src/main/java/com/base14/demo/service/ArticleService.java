package com.base14.demo.service;

import com.base14.demo.dto.ArticleDto.ArticleListResponse;
import com.base14.demo.dto.ArticleDto.ArticleResponse;
import com.base14.demo.dto.ArticleDto.CreateArticleRequest;
import com.base14.demo.dto.ArticleDto.UpdateArticleRequest;
import com.base14.demo.entity.Article;
import com.base14.demo.entity.Favorite;
import com.base14.demo.entity.User;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.instrumentation.annotations.WithSpan;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.transaction.Transactional;
import org.jboss.logging.Logger;
import java.text.Normalizer;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

@ApplicationScoped
public class ArticleService {

    private static final Logger LOG = Logger.getLogger(ArticleService.class);
    private static final Pattern NON_ALPHANUMERIC = Pattern.compile("[^a-z0-9]+");

    @Inject
    TelemetryService telemetry;

    @WithSpan("article.create")
    @Transactional
    public Article create(CreateArticleRequest request, Long authorId) {
        Span span = Span.current();

        User author = User.findById(authorId);
        if (author == null) {
            span.setStatus(StatusCode.ERROR, "author not found");
            throw new ServiceException("author not found", 404);
        }

        String slug = generateSlug(request.title());
        if (Article.existsBySlug(slug)) {
            slug = slug + "-" + Instant.now().toEpochMilli();
        }

        Article article = new Article();
        article.slug = slug;
        article.title = request.title();
        article.description = request.description();
        article.body = request.body();
        article.author = author;
        article.persist();

        telemetry.incrementArticlesCreated();
        span.setStatus(StatusCode.OK, "article created");
        LOG.infof("Article created: %s", article.slug);

        return article;
    }

    @WithSpan("article.getBySlug")
    public Article getBySlug(String slug, Long userId) {
        Span span = Span.current();

        Article article = Article.findBySlug(slug);
        if (article == null) {
            span.setStatus(StatusCode.ERROR, "article not found");
            throw new ServiceException("article not found", 404);
        }

        if (userId != null) {
            article.favorited = Favorite.exists(userId, article.id);
        }

        span.setStatus(StatusCode.OK, "article retrieved");
        return article;
    }

    @WithSpan("article.list")
    public ArticleListResponse list(int limit, int offset, Long userId) {
        Span span = Span.current();

        List<Article> articles = Article.listPaginated(limit, offset);
        long totalCount = Article.count();

        if (userId != null) {
            List<Long> favoriteIds = Favorite.findArticleIdsByUser(userId);
            Set<Long> favoriteSet = favoriteIds.stream().collect(Collectors.toSet());
            articles.forEach(a -> a.favorited = favoriteSet.contains(a.id));
        }

        List<ArticleResponse> responses = articles.stream()
                .map(ArticleResponse::from)
                .toList();

        span.setStatus(StatusCode.OK, "articles listed");
        return new ArticleListResponse(responses, (int) totalCount);
    }

    @WithSpan("article.update")
    @Transactional
    public Article update(String slug, UpdateArticleRequest request, Long userId) {
        Span span = Span.current();

        Article article = Article.findBySlug(slug);
        if (article == null) {
            span.setStatus(StatusCode.ERROR, "article not found");
            throw new ServiceException("article not found", 404);
        }

        if (!article.author.id.equals(userId)) {
            span.setStatus(StatusCode.ERROR, "not authorized");
            throw new ServiceException("not authorized to update this article", 403);
        }

        if (request.title() != null) {
            article.title = request.title();
            article.slug = generateSlug(request.title());
        }
        if (request.description() != null) {
            article.description = request.description();
        }
        if (request.body() != null) {
            article.body = request.body();
        }

        span.setStatus(StatusCode.OK, "article updated");
        LOG.infof("Article updated: %s", article.slug);

        return article;
    }

    @WithSpan("article.delete")
    @Transactional
    public void delete(String slug, Long userId) {
        Span span = Span.current();

        Article article = Article.findBySlug(slug);
        if (article == null) {
            span.setStatus(StatusCode.ERROR, "article not found");
            throw new ServiceException("article not found", 404);
        }

        if (!article.author.id.equals(userId)) {
            span.setStatus(StatusCode.ERROR, "not authorized");
            throw new ServiceException("not authorized to delete this article", 403);
        }

        Favorite.delete("article.id", article.id);
        article.delete();

        telemetry.incrementArticlesDeleted();
        span.setStatus(StatusCode.OK, "article deleted");
        LOG.infof("Article deleted: %s", slug);
    }

    @WithSpan("article.favorite")
    @Transactional
    public Article favorite(String slug, Long userId) {
        Span span = Span.current();

        Article article = Article.findBySlug(slug);
        if (article == null) {
            span.setStatus(StatusCode.ERROR, "article not found");
            throw new ServiceException("article not found", 404);
        }

        if (Favorite.exists(userId, article.id)) {
            span.setStatus(StatusCode.ERROR, "already favorited");
            throw new ServiceException("article already favorited", 409);
        }

        User user = User.findById(userId);
        Favorite favorite = new Favorite();
        favorite.user = user;
        favorite.article = article;
        favorite.persist();

        Article.incrementFavorites(article.id);
        article.favoritesCount++;
        article.favorited = true;

        telemetry.incrementFavoritesAdded();
        span.setStatus(StatusCode.OK, "article favorited");
        LOG.infof("Article favorited: %s by user %d", slug, userId);

        return article;
    }

    @WithSpan("article.unfavorite")
    @Transactional
    public Article unfavorite(String slug, Long userId) {
        Span span = Span.current();

        Article article = Article.findBySlug(slug);
        if (article == null) {
            span.setStatus(StatusCode.ERROR, "article not found");
            throw new ServiceException("article not found", 404);
        }

        if (!Favorite.exists(userId, article.id)) {
            span.setStatus(StatusCode.ERROR, "not favorited");
            throw new ServiceException("article not favorited", 409);
        }

        Favorite.deleteByUserAndArticle(userId, article.id);
        Article.decrementFavorites(article.id);
        article.favoritesCount = Math.max(0, article.favoritesCount - 1);
        article.favorited = false;

        telemetry.incrementFavoritesRemoved();
        span.setStatus(StatusCode.OK, "article unfavorited");
        LOG.infof("Article unfavorited: %s by user %d", slug, userId);

        return article;
    }

    private String generateSlug(String title) {
        String normalized = Normalizer.normalize(title.toLowerCase(), Normalizer.Form.NFD);
        String slug = NON_ALPHANUMERIC.matcher(normalized).replaceAll("-");
        return slug.replaceAll("^-|-$", "");
    }
}
