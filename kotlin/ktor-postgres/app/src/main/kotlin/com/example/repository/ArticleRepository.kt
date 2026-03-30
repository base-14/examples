package com.example.repository

import com.example.model.ArticleDto
import com.example.model.Articles
import kotlinx.coroutines.Dispatchers
import org.jetbrains.exposed.sql.*
import org.jetbrains.exposed.sql.SqlExpressionBuilder.eq
import org.jetbrains.exposed.sql.transactions.experimental.newSuspendedTransaction
import java.time.OffsetDateTime

class ArticleRepository {

    suspend fun findAll(page: Int, perPage: Int): Pair<List<ArticleDto>, Long> = dbQuery {
        val total = Articles.selectAll().count()
        val articles = Articles.selectAll()
            .orderBy(Articles.createdAt, SortOrder.DESC)
            .limit(perPage)
            .offset((page.toLong() - 1) * perPage.toLong())
            .map { it.toDto() }
        articles to total
    }

    suspend fun findById(id: Long): ArticleDto? = dbQuery {
        Articles.selectAll().where { Articles.id eq id }
            .singleOrNull()?.toDto()
    }

    suspend fun create(title: String, body: String): ArticleDto = dbQuery {
        val now = OffsetDateTime.now()
        val id = Articles.insert {
            it[Articles.title] = title
            it[Articles.body] = body
            it[createdAt] = now
            it[updatedAt] = now
        }[Articles.id]
        ArticleDto(id = id, title = title, body = body, createdAt = now.toString(), updatedAt = now.toString())
    }

    suspend fun update(id: Long, title: String?, body: String?): ArticleDto? = dbQuery {
        Articles.selectAll().where { Articles.id eq id }.singleOrNull() ?: return@dbQuery null
        if (title == null && body == null) {
            return@dbQuery Articles.selectAll().where { Articles.id eq id }.single().toDto()
        }
        val now = OffsetDateTime.now()
        Articles.update({ Articles.id eq id }) {
            if (title != null) it[Articles.title] = title
            if (body != null) it[Articles.body] = body
            it[updatedAt] = now
        }
        Articles.selectAll().where { Articles.id eq id }.single().toDto()
    }

    suspend fun delete(id: Long): Boolean = dbQuery {
        Articles.deleteWhere { Articles.id eq id } > 0
    }

    private suspend fun <T> dbQuery(block: suspend () -> T): T =
        newSuspendedTransaction(Dispatchers.IO) { block() }

    private fun ResultRow.toDto() = ArticleDto(
        id = this[Articles.id],
        title = this[Articles.title],
        body = this[Articles.body],
        createdAt = this[Articles.createdAt].toString(),
        updatedAt = this[Articles.updatedAt].toString()
    )
}
