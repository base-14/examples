package com.example

import com.example.model.ErrorResponse
import com.example.plugins.configureRouting
import com.example.plugins.configureSerialization
import com.example.repository.ArticleRepository
import com.example.service.NotificationClient
import com.example.service.TelemetryService
import com.zaxxer.hikari.HikariConfig
import com.zaxxer.hikari.HikariDataSource
import io.ktor.http.*
import io.ktor.server.application.*
import io.ktor.server.engine.*
import io.ktor.server.netty.*
import io.ktor.server.plugins.statuspages.*
import io.ktor.server.response.*
import org.flywaydb.core.Flyway
import org.jetbrains.exposed.sql.Database
import org.slf4j.LoggerFactory

private val logger = LoggerFactory.getLogger("com.example.Application")

fun main() {
    embeddedServer(Netty, serverConfig {
        developmentMode = true
        module(Application::module)
    }) {
        connector { port = 8080 }
    }.start(wait = true)
}

fun Application.module() {
    val dataSource = HikariDataSource(HikariConfig().apply {
        jdbcUrl = "jdbc:postgresql://${env("DB_HOST", "localhost")}:${env("DB_PORT", "5432")}/${env("DB_NAME", "ktor_articles")}"
        username = env("DB_USER", "postgres")
        password = env("DB_PASSWORD", "postgres")
        maximumPoolSize = 10
    })

    Flyway.configure()
        .dataSource(dataSource)
        .locations("classpath:db/migration")
        .load()
        .migrate()

    Database.connect(dataSource)

    val articleRepository = ArticleRepository()
    val notificationClient = NotificationClient(env("NOTIFY_URL", "http://localhost:8081"))
    val telemetryService = TelemetryService()

    install(StatusPages) {
        exception<Throwable> { call, cause ->
            logger.error("Unhandled exception", cause)
            call.respond(HttpStatusCode.InternalServerError, ErrorResponse("Internal server error"))
        }
    }

    configureSerialization()
    configureRouting(articleRepository, notificationClient, telemetryService, dataSource)
}

private fun env(name: String, default: String): String =
    System.getenv(name) ?: default
