package com.example.service

import io.opentelemetry.api.GlobalOpenTelemetry
import io.opentelemetry.api.metrics.LongCounter

class TelemetryService {

    private val articlesCreated: LongCounter = GlobalOpenTelemetry.getMeter("ktor-articles")
        .counterBuilder("articles.created")
        .setDescription("Total number of articles created")
        .build()

    fun incrementArticlesCreated() {
        articlesCreated.add(1)
    }
}
