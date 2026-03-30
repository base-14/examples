package com.example.routes

import com.zaxxer.hikari.HikariDataSource
import io.ktor.http.*
import io.ktor.server.response.*
import io.ktor.server.routing.*
import kotlinx.serialization.Serializable

@Serializable
data class HealthResponse(val status: String, val database: String)

fun Routing.healthRoutes(dataSource: HikariDataSource) {
    get("/api/health") {
        try {
            dataSource.connection.use { conn ->
                conn.createStatement().use { it.executeQuery("SELECT 1") }
            }
            call.respond(HealthResponse("healthy", "connected"))
        } catch (e: Exception) {
            call.respond(HttpStatusCode.ServiceUnavailable, HealthResponse("unhealthy", "disconnected"))
        }
    }
}
