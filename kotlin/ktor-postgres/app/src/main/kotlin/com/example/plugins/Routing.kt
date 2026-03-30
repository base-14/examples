package com.example.plugins

import com.example.repository.ArticleRepository
import com.example.routes.articleRoutes
import com.example.routes.healthRoutes
import com.example.service.NotificationClient
import com.example.service.TelemetryService
import com.zaxxer.hikari.HikariDataSource
import io.ktor.server.application.*
import io.ktor.server.routing.*

fun Application.configureRouting(
    articleRepository: ArticleRepository,
    notificationClient: NotificationClient,
    telemetryService: TelemetryService,
    dataSource: HikariDataSource
) {
    routing {
        healthRoutes(dataSource)
        articleRoutes(articleRepository, notificationClient, telemetryService)
    }
}
