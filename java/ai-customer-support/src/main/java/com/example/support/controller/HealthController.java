package com.example.support.controller;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class HealthController {

    @GetMapping("/api/health")
    public Mono<Map<String, Object>> health() {
        return Mono.just(Map.of(
            "status", "ok",
            "service", "ai-customer-support"
        ));
    }
}
