use opentelemetry::{
    global,
    metrics::{Counter, Histogram, Meter},
};
use std::sync::LazyLock;

pub static METER: LazyLock<Meter> = LazyLock::new(|| global::meter("ai-report-generator"));

// --- LLM Gateway Contract Metrics (7 required) ---

const TOKEN_BOUNDARIES: [f64; 14] = [
    1.0, 4.0, 16.0, 64.0, 256.0, 1024.0, 4096.0, 16384.0, 65536.0, 262144.0, 1048576.0, 4194304.0,
    16777216.0, 67108864.0,
];

const DURATION_BOUNDARIES: [f64; 14] = [
    0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92,
];

pub static GEN_AI_INPUT_TOKENS: LazyLock<Histogram<u64>> = LazyLock::new(|| {
    METER
        .u64_histogram("gen_ai.client.inference.operation.input_tokens")
        .with_description("Input tokens per inference call")
        .with_unit("{token}")
        .with_boundaries(TOKEN_BOUNDARIES.to_vec())
        .build()
});

pub static GEN_AI_OUTPUT_TOKENS: LazyLock<Histogram<u64>> = LazyLock::new(|| {
    METER
        .u64_histogram("gen_ai.client.inference.operation.output_tokens")
        .with_description("Output tokens per inference call")
        .with_unit("{token}")
        .with_boundaries(TOKEN_BOUNDARIES.to_vec())
        .build()
});

pub static GEN_AI_INFERENCE_DURATION: LazyLock<Histogram<f64>> = LazyLock::new(|| {
    METER
        .f64_histogram("gen_ai.client.inference.duration")
        .with_description("Wall-clock duration of an inference call")
        .with_unit("s")
        .with_boundaries(DURATION_BOUNDARIES.to_vec())
        .build()
});

pub static GEN_AI_COST: LazyLock<Counter<f64>> = LazyLock::new(|| {
    METER
        .f64_counter("base14.gen_ai.cost")
        .with_description("Estimated cost of LLM operations in USD")
        .with_unit("usd")
        .build()
});

pub static GEN_AI_RETRY_COUNT: LazyLock<Counter<u64>> = LazyLock::new(|| {
    METER
        .u64_counter("base14.gen_ai.retry.count")
        .with_description("Number of retry attempts, excluding the initial attempt")
        .with_unit("{retry}")
        .build()
});

pub static GEN_AI_FALLBACK_COUNT: LazyLock<Counter<u64>> = LazyLock::new(|| {
    METER
        .u64_counter("base14.gen_ai.fallback.count")
        .with_description("Number of LLM fallback activations")
        .with_unit("{fallback}")
        .build()
});

pub static GEN_AI_ERROR_COUNT: LazyLock<Counter<u64>> = LazyLock::new(|| {
    METER
        .u64_counter("base14.gen_ai.error.count")
        .with_description("Number of LLM call errors")
        .with_unit("{error}")
        .build()
});

// --- Domain Metrics ---

pub static REPORT_GENERATION_DURATION: LazyLock<Histogram<f64>> = LazyLock::new(|| {
    METER
        .f64_histogram("base14.report.generation.duration")
        .with_description("Total report generation duration in seconds")
        .with_unit("s")
        .build()
});

pub static REPORT_DATA_POINTS: LazyLock<Histogram<f64>> = LazyLock::new(|| {
    METER
        .f64_histogram("base14.report.data_points")
        .with_description("Number of data points processed per report")
        .with_unit("{point}")
        .build()
});

pub static REPORT_SECTIONS: LazyLock<Histogram<f64>> = LazyLock::new(|| {
    METER
        .f64_histogram("base14.report.sections")
        .with_description("Number of sections generated per report")
        .with_unit("{section}")
        .build()
});

// --- HTTP Metrics ---

pub static HTTP_REQUESTS_TOTAL: LazyLock<Counter<u64>> = LazyLock::new(|| {
    METER
        .u64_counter("base14.http.requests.total")
        .with_description("Total number of HTTP requests")
        .with_unit("{request}")
        .build()
});

pub static HTTP_REQUEST_DURATION: LazyLock<Histogram<f64>> = LazyLock::new(|| {
    METER
        .f64_histogram("base14.http.request.duration")
        .with_description("HTTP request duration in milliseconds")
        .with_unit("ms")
        .with_boundaries(vec![
            1.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0, 10000.0,
        ])
        .build()
});
