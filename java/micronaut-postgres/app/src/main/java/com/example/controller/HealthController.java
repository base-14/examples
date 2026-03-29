package com.example.controller;

import io.micronaut.http.HttpResponse;
import io.micronaut.http.HttpStatus;
import io.micronaut.http.annotation.Controller;
import io.micronaut.http.annotation.Get;
import io.micronaut.scheduling.TaskExecutors;
import io.micronaut.scheduling.annotation.ExecuteOn;
import io.micronaut.transaction.annotation.Transactional;
import jakarta.persistence.EntityManager;
import java.util.Map;

@Controller("/api/health")
@ExecuteOn(TaskExecutors.BLOCKING)
public class HealthController {

    private final EntityManager entityManager;

    public HealthController(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Get
    @Transactional(readOnly = true)
    public HttpResponse<Map<String, String>> health() {
        try {
            entityManager.createNativeQuery("SELECT 1").getSingleResult();
            return HttpResponse.ok(Map.of("status", "healthy", "database", "connected"));
        } catch (Exception e) {
            return HttpResponse.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(Map.of("status", "unhealthy", "database", "disconnected"));
        }
    }
}
