package com.example.service;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.api.metrics.Meter;
import jakarta.annotation.PostConstruct;
import jakarta.inject.Singleton;

@Singleton
public class TelemetryService {

    private LongCounter articlesCreated;

    @PostConstruct
    void init() {
        Meter meter = GlobalOpenTelemetry.getMeter("micronaut-articles");
        articlesCreated = meter.counterBuilder("articles.created")
                .setDescription("Total number of articles created")
                .build();
    }

    public void incrementArticlesCreated() {
        articlesCreated.add(1);
    }
}
