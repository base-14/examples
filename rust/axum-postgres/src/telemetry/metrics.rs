use once_cell::sync::Lazy;
use opentelemetry::{
    global,
    metrics::{Counter, Meter},
};

pub static METER: Lazy<Meter> = Lazy::new(|| global::meter("rust-axum-postgres"));

pub static ARTICLES_CREATED: Lazy<Counter<u64>> = Lazy::new(|| {
    METER
        .u64_counter("articles.created")
        .with_description("Total articles created")
        .build()
});

pub static ARTICLES_UPDATED: Lazy<Counter<u64>> = Lazy::new(|| {
    METER
        .u64_counter("articles.updated")
        .with_description("Total articles updated")
        .build()
});

pub static ARTICLES_DELETED: Lazy<Counter<u64>> = Lazy::new(|| {
    METER
        .u64_counter("articles.deleted")
        .with_description("Total articles deleted")
        .build()
});

pub static FAVORITES_ADDED: Lazy<Counter<u64>> = Lazy::new(|| {
    METER
        .u64_counter("favorites.added")
        .with_description("Total favorites added")
        .build()
});

pub static FAVORITES_REMOVED: Lazy<Counter<u64>> = Lazy::new(|| {
    METER
        .u64_counter("favorites.removed")
        .with_description("Total favorites removed")
        .build()
});

pub static USERS_REGISTERED: Lazy<Counter<u64>> = Lazy::new(|| {
    METER
        .u64_counter("users.registered")
        .with_description("Total users registered")
        .build()
});

pub static JOBS_ENQUEUED: Lazy<Counter<u64>> = Lazy::new(|| {
    METER
        .u64_counter("jobs.enqueued")
        .with_description("Total jobs enqueued")
        .build()
});

pub static JOBS_COMPLETED: Lazy<Counter<u64>> = Lazy::new(|| {
    METER
        .u64_counter("jobs.completed")
        .with_description("Total jobs completed successfully")
        .build()
});

pub static JOBS_FAILED: Lazy<Counter<u64>> = Lazy::new(|| {
    METER
        .u64_counter("jobs.failed")
        .with_description("Total jobs failed")
        .build()
});
