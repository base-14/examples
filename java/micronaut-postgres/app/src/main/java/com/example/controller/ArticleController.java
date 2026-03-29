package com.example.controller;

import com.example.model.Article;
import com.example.repository.ArticleRepository;
import com.example.service.NotificationClient;
import com.example.service.TelemetryService;
import io.micronaut.data.model.Page;
import io.micronaut.data.model.Pageable;
import io.micronaut.http.HttpResponse;
import io.micronaut.http.HttpStatus;
import io.micronaut.http.annotation.Body;
import io.micronaut.http.annotation.Controller;
import io.micronaut.scheduling.TaskExecutors;
import io.micronaut.scheduling.annotation.ExecuteOn;
import io.micronaut.http.annotation.Delete;
import io.micronaut.http.annotation.Get;
import io.micronaut.http.annotation.PathVariable;
import io.micronaut.http.annotation.Post;
import io.micronaut.http.annotation.Put;
import io.micronaut.http.annotation.QueryValue;
import io.micronaut.serde.annotation.Serdeable;
import io.opentelemetry.api.trace.Span;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import java.time.Instant;
import java.util.Map;
import java.util.Optional;

@Controller("/api/articles")
@ExecuteOn(TaskExecutors.BLOCKING)
public class ArticleController {

    private static final Logger LOG = LoggerFactory.getLogger(ArticleController.class);

    private final ArticleRepository articleRepository;
    private final NotificationClient notificationClient;
    private final TelemetryService telemetryService;

    public ArticleController(ArticleRepository articleRepository,
                             NotificationClient notificationClient,
                             TelemetryService telemetryService) {
        this.articleRepository = articleRepository;
        this.notificationClient = notificationClient;
        this.telemetryService = telemetryService;
    }

    @Get
    public HttpResponse<?> list(@QueryValue(defaultValue = "1") int page,
                                @QueryValue(defaultValue = "10") int per_page) {
        Page<Article> result = articleRepository.findAll(Pageable.from(page - 1, per_page));
        return HttpResponse.ok(Map.of(
                "data", result.getContent(),
                "meta", Map.of(
                        "page", page,
                        "per_page", per_page,
                        "total", result.getTotalSize(),
                        "trace_id", currentTraceId()
                )
        ));
    }

    @Get("/{id}")
    public HttpResponse<?> get(@PathVariable Long id) {
        Optional<Article> article = articleRepository.findById(id);
        if (article.isEmpty()) {
            LOG.warn("Article not found: id={}", id);
            return HttpResponse.status(HttpStatus.NOT_FOUND).body(Map.of(
                    "error", Map.of("code", "NOT_FOUND", "message", "Article not found"),
                    "meta", Map.of("trace_id", currentTraceId())
            ));
        }
        return HttpResponse.ok(Map.of(
                "data", article.get(),
                "meta", Map.of("trace_id", currentTraceId())
        ));
    }

    @Post
    public HttpResponse<?> create(@Body CreateArticleRequest request) {
        if (request.title() == null || request.title().isBlank() ||
            request.body() == null || request.body().isBlank()) {
            LOG.warn("Validation failed: title and body are required");
            return HttpResponse.status(HttpStatus.UNPROCESSABLE_ENTITY).body(Map.of(
                    "error", Map.of("code", "VALIDATION_ERROR", "message", "title and body are required"),
                    "meta", Map.of("trace_id", currentTraceId())
            ));
        }

        try {
            Article article = new Article();
            article.setTitle(request.title());
            article.setBody(request.body());
            article = articleRepository.save(article);

            LOG.info("Article created: id={}, title={}", article.getId(), article.getTitle());
            telemetryService.incrementArticlesCreated();

            try {
                notificationClient.notify(Map.of(
                        "id", article.getId(),
                        "title", article.getTitle(),
                        "event", "article.created"
                ));
            } catch (Exception e) {
                LOG.warn("Failed to notify: {}", e.getMessage());
            }

            return HttpResponse.status(HttpStatus.CREATED).body(Map.of(
                    "data", article,
                    "meta", Map.of("trace_id", currentTraceId())
            ));
        } catch (Exception e) {
            LOG.error("Failed to create article: {}", e.getMessage());
            return HttpResponse.serverError(Map.of(
                    "error", Map.of("code", "INTERNAL_ERROR", "message", "Internal server error"),
                    "meta", Map.of("trace_id", currentTraceId())
            ));
        }
    }

    @Put("/{id}")
    public HttpResponse<?> update(@PathVariable Long id, @Body UpdateArticleRequest request) {
        Optional<Article> existing = articleRepository.findById(id);
        if (existing.isEmpty()) {
            LOG.warn("Article not found for update: id={}", id);
            return HttpResponse.status(HttpStatus.NOT_FOUND).body(Map.of(
                    "error", Map.of("code", "NOT_FOUND", "message", "Article not found"),
                    "meta", Map.of("trace_id", currentTraceId())
            ));
        }
        Article article = existing.get();
        if (request.title() != null) article.setTitle(request.title());
        if (request.body() != null) article.setBody(request.body());
        article.setUpdatedAt(Instant.now());
        article = articleRepository.update(article);

        return HttpResponse.ok(Map.of(
                "data", article,
                "meta", Map.of("trace_id", currentTraceId())
        ));
    }

    @Delete("/{id}")
    public HttpResponse<?> delete(@PathVariable Long id) {
        Optional<Article> existing = articleRepository.findById(id);
        if (existing.isEmpty()) {
            LOG.warn("Article not found for delete: id={}", id);
            return HttpResponse.status(HttpStatus.NOT_FOUND).body(Map.of(
                    "error", Map.of("code", "NOT_FOUND", "message", "Article not found"),
                    "meta", Map.of("trace_id", currentTraceId())
            ));
        }
        articleRepository.deleteById(id);
        return HttpResponse.noContent();
    }

    private String currentTraceId() {
        return Span.current().getSpanContext().getTraceId();
    }

    @Serdeable
    public record CreateArticleRequest(String title, String body) {}

    @Serdeable
    public record UpdateArticleRequest(String title, String body) {}
}
