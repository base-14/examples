package com.base14.demo.service;

import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.api.metrics.Meter;
import jakarta.annotation.PostConstruct;
import jakarta.enterprise.context.ApplicationScoped;

@ApplicationScoped
public class TelemetryService {

    private LongCounter articlesCreated;
    private LongCounter articlesDeleted;
    private LongCounter favoritesAdded;
    private LongCounter favoritesRemoved;

    @PostConstruct
    void init() {
        Meter meter = GlobalOpenTelemetry.getMeter("quarkus-postgres-api");

        articlesCreated = meter.counterBuilder("articles.created")
                .setDescription("Total number of articles created")
                .build();

        articlesDeleted = meter.counterBuilder("articles.deleted")
                .setDescription("Total number of articles deleted")
                .build();

        favoritesAdded = meter.counterBuilder("favorites.added")
                .setDescription("Total number of favorites added")
                .build();

        favoritesRemoved = meter.counterBuilder("favorites.removed")
                .setDescription("Total number of favorites removed")
                .build();
    }

    public void incrementArticlesCreated() {
        articlesCreated.add(1);
    }

    public void incrementArticlesDeleted() {
        articlesDeleted.add(1);
    }

    public void incrementFavoritesAdded() {
        favoritesAdded.add(1);
    }

    public void incrementFavoritesRemoved() {
        favoritesRemoved.add(1);
    }
}
