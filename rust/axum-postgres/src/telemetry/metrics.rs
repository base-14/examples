use opentelemetry::{
    global,
    metrics::{Counter, Histogram, Meter},
};
use std::sync::LazyLock;

pub static METER: LazyLock<Meter> = LazyLock::new(|| global::meter("rust-axum-postgres"));

pub static HTTP_REQUESTS_TOTAL: LazyLock<Counter<u64>> = LazyLock::new(|| {
    METER
        .u64_counter("http.requests.total")
        .with_description("Total number of HTTP requests")
        .with_unit("{request}")
        .build()
});

pub static HTTP_REQUEST_DURATION: LazyLock<Histogram<f64>> = LazyLock::new(|| {
    METER
        .f64_histogram("http.request.duration")
        .with_description("HTTP request duration in milliseconds")
        .with_unit("ms")
        .with_boundaries(vec![
            1.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0, 10000.0,
        ])
        .build()
});

pub static ARTICLES_CREATED: LazyLock<Counter<u64>> = LazyLock::new(|| {
    METER
        .u64_counter("articles.created")
        .with_description("Total articles created")
        .build()
});

pub static ARTICLES_UPDATED: LazyLock<Counter<u64>> = LazyLock::new(|| {
    METER
        .u64_counter("articles.updated")
        .with_description("Total articles updated")
        .build()
});

pub static ARTICLES_DELETED: LazyLock<Counter<u64>> = LazyLock::new(|| {
    METER
        .u64_counter("articles.deleted")
        .with_description("Total articles deleted")
        .build()
});

pub static FAVORITES_ADDED: LazyLock<Counter<u64>> = LazyLock::new(|| {
    METER
        .u64_counter("favorites.added")
        .with_description("Total favorites added")
        .build()
});

pub static FAVORITES_REMOVED: LazyLock<Counter<u64>> = LazyLock::new(|| {
    METER
        .u64_counter("favorites.removed")
        .with_description("Total favorites removed")
        .build()
});

pub static USERS_REGISTERED: LazyLock<Counter<u64>> = LazyLock::new(|| {
    METER
        .u64_counter("users.registered")
        .with_description("Total users registered")
        .build()
});

pub static JOBS_ENQUEUED: LazyLock<Counter<u64>> = LazyLock::new(|| {
    METER
        .u64_counter("jobs.enqueued")
        .with_description("Total jobs enqueued")
        .build()
});

pub static JOBS_COMPLETED: LazyLock<Counter<u64>> = LazyLock::new(|| {
    METER
        .u64_counter("jobs.completed")
        .with_description("Total jobs completed successfully")
        .build()
});

pub static JOBS_FAILED: LazyLock<Counter<u64>> = LazyLock::new(|| {
    METER
        .u64_counter("jobs.failed")
        .with_description("Total jobs failed")
        .build()
});
