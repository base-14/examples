package com.example.service

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.encodeToString
import org.slf4j.LoggerFactory
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse

class NotificationClient(private val notifyUrl: String) {

    private val logger = LoggerFactory.getLogger(NotificationClient::class.java)
    private val httpClient = HttpClient.newHttpClient()

    suspend fun notify(payload: Map<String, String>) {
        withContext(Dispatchers.IO) {
            val json = Json.encodeToString(payload)
            val request = HttpRequest.newBuilder()
                .uri(URI.create("$notifyUrl/notify"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build()
            val response = httpClient.send(request, HttpResponse.BodyHandlers.ofString())
            logger.info("Notification sent: status={}", response.statusCode())
        }
    }
}
