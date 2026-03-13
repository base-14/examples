// Rust Hello World — OpenTelemetry

use opentelemetry::trace::{Status, TraceContextExt, Tracer};
use opentelemetry::{global, KeyValue};
use opentelemetry_appender_tracing::layer::OpenTelemetryTracingBridge;
use opentelemetry_otlp::WithExportConfig;
use opentelemetry_sdk::logs::SdkLoggerProvider;
use opentelemetry_sdk::metrics::SdkMeterProvider;
use opentelemetry_sdk::trace::SdkTracerProvider;
use opentelemetry_sdk::Resource;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;

#[tokio::main]
async fn main() {
    // -- Configuration ----------------------------------------------------------
    // The collector endpoint. Set this to where your OTel collector accepts
    // OTLP/HTTP traffic (default port 4318).
    let endpoint = std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT")
        .expect("Set OTEL_EXPORTER_OTLP_ENDPOINT (e.g. http://localhost:4318)");

    // A Resource identifies your application in the telemetry backend.
    // Every span, log, and metric carries this identity.
    let resource = Resource::builder()
        .with_service_name("hello-world-rust")
        .build();

    // -- Traces -----------------------------------------------------------------
    // A TracerProvider manages the lifecycle of traces. It batches spans and
    // sends them to the collector via the OTLP/HTTP exporter.
    let tracer_provider = SdkTracerProvider::builder()
        .with_resource(resource.clone())
        .with_batch_exporter(
            opentelemetry_otlp::SpanExporter::builder()
                .with_http()
                .with_endpoint(format!("{endpoint}/v1/traces"))
                .build()
                .expect("failed to create span exporter"),
        )
        .build();
    global::set_tracer_provider(tracer_provider.clone());

    // -- Logs -------------------------------------------------------------------
    // A LoggerProvider sends structured logs to the collector. Rust uses a bridge
    // pattern — the `tracing` crate emits logs and the OpenTelemetry bridge
    // forwards them to the collector with trace correlation.
    let logger_provider = SdkLoggerProvider::builder()
        .with_resource(resource.clone())
        .with_batch_exporter(
            opentelemetry_otlp::LogExporter::builder()
                .with_http()
                .with_endpoint(format!("{endpoint}/v1/logs"))
                .build()
                .expect("failed to create log exporter"),
        )
        .build();

    // The bridge layer connects Rust's `tracing` macros (info!, warn!, error!)
    // to OpenTelemetry. Logs emitted inside a span carry the span's trace ID.
    let otel_log_layer = OpenTelemetryTracingBridge::new(&logger_provider);
    // RUST_LOG controls log verbosity (default: info). Set to debug or trace for more detail.
    let env_filter = tracing_subscriber::EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info"));
    tracing_subscriber::registry()
        .with(env_filter)
        .with(otel_log_layer)
        .init();

    // -- Metrics ----------------------------------------------------------------
    // A MeterProvider manages metrics. The periodic reader collects and exports
    // metric data at regular intervals.
    let meter_provider = SdkMeterProvider::builder()
        .with_resource(resource)
        .with_periodic_exporter(
            opentelemetry_otlp::MetricExporter::builder()
                .with_http()
                .with_endpoint(format!("{endpoint}/v1/metrics"))
                .build()
                .expect("failed to create metric exporter"),
        )
        .build();
    global::set_meter_provider(meter_provider.clone());

    let meter = global::meter("hello-world-rust");

    // A counter tracks how many times something happens.
    let hello_counter = meter
        .u64_counter("hello.count")
        .with_description("Number of times the hello-world app has run")
        .build();

    // -- Run --------------------------------------------------------------------
    say_hello(&hello_counter);
    check_disk_space();
    parse_config();

    // -- Shutdown ---------------------------------------------------------------
    // Flush all buffered telemetry to the collector before exiting.
    // Without this, the last batch of spans/logs/metrics may be lost.
    let _ = tracer_provider.shutdown();
    let _ = logger_provider.shutdown();
    let _ = meter_provider.shutdown();

    println!("Done. Check Scout for your trace, log, and metric.");
}

// A normal operation — creates a span with an info log.
fn say_hello(counter: &opentelemetry::metrics::Counter<u64>) {
    let tracer = global::tracer("hello-world-rust");
    tracer.in_span("say-hello", |cx| {
        let span = cx.span();
        span.set_attribute(KeyValue::new("greeting", "Hello, World!"));
        // This log is emitted inside the span, so it carries the span's trace ID.
        // In Scout, you can jump to the trace from a log detail.
        tracing::info!("Hello, World!");
        counter.add(1, &[]);
    });
}

// A degraded operation — creates a span with a warning log.
fn check_disk_space() {
    let tracer = global::tracer("hello-world-rust");
    tracer.in_span("check-disk-space", |cx| {
        let span = cx.span();
        span.set_attribute(KeyValue::new("disk.usage_percent", 92_i64));
        // Warnings show up in Scout with a distinct severity level, making
        // them easy to filter and spot before they become errors.
        tracing::warn!("Disk usage above 90%");
    });
}

// A failed operation — creates a span with an error and exception.
fn parse_config() {
    let tracer = global::tracer("hello-world-rust");
    tracer.in_span("parse-config", |cx| {
        let span = cx.span();
        let error_msg = "invalid config: missing 'database_url'";
        // record_error attaches the error details to the span.
        // set_status marks the span as errored so it stands out in TraceX.
        span.record_error(&std::io::Error::new(std::io::ErrorKind::InvalidData, error_msg));
        span.set_status(Status::error(error_msg.to_string()));
        tracing::error!("Failed to parse configuration: {}", error_msg);
    });
}
