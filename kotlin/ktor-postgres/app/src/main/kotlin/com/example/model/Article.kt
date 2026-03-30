package com.example.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import org.jetbrains.exposed.sql.Table
import org.jetbrains.exposed.sql.kotlin.datetime.timestampWithTimeZone

object Articles : Table("articles") {
    val id = long("id").autoIncrement()
    val title = varchar("title", 255)
    val body = text("body")
    val createdAt = timestampWithTimeZone("created_at")
    val updatedAt = timestampWithTimeZone("updated_at")
    override val primaryKey = PrimaryKey(id)
}

@Serializable
data class ArticleDto(
    val id: Long,
    val title: String,
    val body: String,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String
)

@Serializable
data class CreateArticleRequest(
    val title: String? = null,
    val body: String? = null
)

@Serializable
data class UpdateArticleRequest(
    val title: String? = null,
    val body: String? = null
)

@Serializable
data class TraceMeta(
    @SerialName("trace_id") val traceId: String = "",
    val page: Int? = null,
    @SerialName("per_page") val perPage: Int? = null,
    val total: Long? = null
)

@Serializable
data class ArticleResponse(val data: ArticleDto, val meta: TraceMeta)

@Serializable
data class ArticleListResponse(val data: List<ArticleDto>, val meta: TraceMeta)

@Serializable
data class ErrorResponse(val error: String, val meta: TraceMeta? = null)
