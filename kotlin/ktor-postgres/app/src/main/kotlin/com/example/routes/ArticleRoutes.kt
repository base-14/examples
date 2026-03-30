package com.example.routes

import com.example.model.*
import com.example.repository.ArticleRepository
import com.example.service.NotificationClient
import com.example.service.TelemetryService
import io.ktor.http.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*
import io.opentelemetry.api.trace.Span
import org.slf4j.LoggerFactory

private val logger = LoggerFactory.getLogger("com.example.routes.ArticleRoutes")

fun Routing.articleRoutes(
    repository: ArticleRepository,
    notificationClient: NotificationClient,
    telemetryService: TelemetryService
) {
    route("/api/articles") {
        get {
            val page = (call.queryParameters["page"]?.toIntOrNull() ?: 1).coerceAtLeast(1)
            val perPage = (call.queryParameters["per_page"]?.toIntOrNull() ?: 20).coerceIn(1, 100)
            val (articles, total) = repository.findAll(page, perPage)
            call.respond(ArticleListResponse(
                data = articles,
                meta = TraceMeta(traceId = currentTraceId(), page = page, perPage = perPage, total = total)
            ))
        }

        get("/{id}") {
            val id = call.parameters["id"]?.toLongOrNull()
            if (id == null) {
                logger.warn("Invalid article ID format")
                call.respond(HttpStatusCode.BadRequest, ErrorResponse("Invalid ID", TraceMeta(traceId = currentTraceId())))
                return@get
            }
            val article = repository.findById(id)
            if (article == null) {
                logger.warn("Article not found: id={}", id)
                call.respond(HttpStatusCode.NotFound, ErrorResponse("Article not found", TraceMeta(traceId = currentTraceId())))
                return@get
            }
            call.respond(ArticleResponse(data = article, meta = TraceMeta(traceId = currentTraceId())))
        }

        post {
            val request = try {
                call.receive<CreateArticleRequest>()
            } catch (e: Exception) {
                logger.warn("Invalid request body: {}", e.message)
                call.respond(HttpStatusCode.UnprocessableEntity, ErrorResponse("Invalid request body", TraceMeta(traceId = currentTraceId())))
                return@post
            }

            if (request.title.isNullOrBlank() || request.body.isNullOrBlank()) {
                logger.warn("Validation failed: title and body are required")
                call.respond(HttpStatusCode.UnprocessableEntity, ErrorResponse("title and body are required", TraceMeta(traceId = currentTraceId())))
                return@post
            }

            if (request.title.length > 255) {
                logger.warn("Validation failed: title exceeds 255 characters")
                call.respond(HttpStatusCode.UnprocessableEntity, ErrorResponse("title must be 255 characters or less", TraceMeta(traceId = currentTraceId())))
                return@post
            }

            try {
                val article = repository.create(request.title, request.body)
                telemetryService.incrementArticlesCreated()
                logger.info("Article created: id={}, title={}", article.id, article.title)

                try {
                    notificationClient.notify(mapOf("event" to "article.created", "article_id" to article.id.toString(), "title" to article.title))
                } catch (e: Exception) {
                    logger.warn("Failed to send notification: {}", e.message)
                }

                call.respond(HttpStatusCode.Created, ArticleResponse(data = article, meta = TraceMeta(traceId = currentTraceId())))
            } catch (e: Exception) {
                logger.error("Failed to create article", e)
                call.respond(HttpStatusCode.InternalServerError, ErrorResponse("Internal server error", TraceMeta(traceId = currentTraceId())))
            }
        }

        put("/{id}") {
            val id = call.parameters["id"]?.toLongOrNull()
            if (id == null) {
                logger.warn("Invalid article ID format")
                call.respond(HttpStatusCode.BadRequest, ErrorResponse("Invalid ID", TraceMeta(traceId = currentTraceId())))
                return@put
            }

            val request = try {
                call.receive<UpdateArticleRequest>()
            } catch (e: Exception) {
                logger.warn("Invalid request body: {}", e.message)
                call.respond(HttpStatusCode.UnprocessableEntity, ErrorResponse("Invalid request body", TraceMeta(traceId = currentTraceId())))
                return@put
            }

            val updated = repository.update(id, request.title, request.body)
            if (updated == null) {
                logger.warn("Article not found for update: id={}", id)
                call.respond(HttpStatusCode.NotFound, ErrorResponse("Article not found", TraceMeta(traceId = currentTraceId())))
                return@put
            }
            call.respond(ArticleResponse(data = updated, meta = TraceMeta(traceId = currentTraceId())))
        }

        delete("/{id}") {
            val id = call.parameters["id"]?.toLongOrNull()
            if (id == null) {
                logger.warn("Invalid article ID format")
                call.respond(HttpStatusCode.BadRequest, ErrorResponse("Invalid ID", TraceMeta(traceId = currentTraceId())))
                return@delete
            }
            if (repository.delete(id)) {
                call.respond(HttpStatusCode.NoContent)
            } else {
                logger.warn("Article not found for delete: id={}", id)
                call.respond(HttpStatusCode.NotFound, ErrorResponse("Article not found", TraceMeta(traceId = currentTraceId())))
            }
        }
    }
}

private fun currentTraceId(): String {
    val span = Span.current()
    val ctx = span.spanContext
    return if (ctx.isValid) ctx.traceId else ""
}
