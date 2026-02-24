use opentelemetry::{
    global,
    metrics::{Counter, Histogram, Meter},
};
use std::sync::LazyLock;

pub static METER: LazyLock<Meter> = LazyLock::new(|| global::meter("ai-report-generator"));

// --- LLM Gateway Contract Metrics (6 required) ---

pub static GEN_AI_TOKEN_USAGE: LazyLock<Histogram<f64>> = LazyLock::new(|| {
    METER
        .f64_histogram("gen_ai.client.token.usage")
        .with_description("Number of tokens used per LLM call")
        .with_unit("{token}")
        .build()
});

pub static GEN_AI_OPERATION_DURATION: LazyLock<Histogram<f64>> = LazyLock::new(|| {
    METER
        .f64_histogram("gen_ai.client.operation.duration")
        .with_description("Duration of LLM operations in seconds")
        .with_unit("s")
        .build()
});

pub static GEN_AI_COST: LazyLock<Counter<f64>> = LazyLock::new(|| {
    METER
        .f64_counter("gen_ai.client.cost")
        .with_description("Estimated cost of LLM operations in USD")
        .with_unit("usd")
        .build()
});

pub static GEN_AI_RETRY_COUNT: LazyLock<Counter<u64>> = LazyLock::new(|| {
    METER
        .u64_counter("gen_ai.client.retry.count")
        .with_description("Number of LLM call retries")
        .with_unit("{retry}")
        .build()
});

pub static GEN_AI_FALLBACK_COUNT: LazyLock<Counter<u64>> = LazyLock::new(|| {
    METER
        .u64_counter("gen_ai.client.fallback.count")
        .with_description("Number of LLM fallback activations")
        .with_unit("{fallback}")
        .build()
});

pub static GEN_AI_ERROR_COUNT: LazyLock<Counter<u64>> = LazyLock::new(|| {
    METER
        .u64_counter("gen_ai.client.error.count")
        .with_description("Number of LLM call errors")
        .with_unit("{error}")
        .build()
});

// --- Domain Metrics ---

pub static REPORT_GENERATION_DURATION: LazyLock<Histogram<f64>> = LazyLock::new(|| {
    METER
        .f64_histogram("report.generation.duration")
        .with_description("Total report generation duration in seconds")
        .with_unit("s")
        .build()
});

pub static REPORT_DATA_POINTS: LazyLock<Histogram<f64>> = LazyLock::new(|| {
    METER
        .f64_histogram("report.data_points")
        .with_description("Number of data points processed per report")
        .with_unit("{point}")
        .build()
});

pub static REPORT_SECTIONS: LazyLock<Histogram<f64>> = LazyLock::new(|| {
    METER
        .f64_histogram("report.sections")
        .with_description("Number of sections generated per report")
        .with_unit("{section}")
        .build()
});

// --- HTTP Metrics ---

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
