package com.example.notify

import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.*
import io.ktor.server.application.*
import io.ktor.server.engine.*
import io.ktor.server.netty.*
import io.ktor.server.plugins.contentnegotiation.*
import io.ktor.server.request.*
import io.ktor.server.response.*
import io.ktor.server.routing.*
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import org.slf4j.LoggerFactory

private val logger = LoggerFactory.getLogger("com.example.notify")

@Serializable
data class StatusResponse(val status: String)

fun main() {
    embeddedServer(Netty, serverConfig {
        developmentMode = true
        module(Application::module)
    }) {
        connector { port = 8081 }
    }.start(wait = true)
}

fun Application.module() {
    install(ContentNegotiation) {
        json(Json { ignoreUnknownKeys = true })
    }

    routing {
        get("/api/health") {
            call.respond(StatusResponse("healthy"))
        }

        post("/notify") {
            val body = call.receiveText()
            logger.info("Notification received: {}", body)
            call.respond(HttpStatusCode.OK, StatusResponse("received"))
        }
    }
}
