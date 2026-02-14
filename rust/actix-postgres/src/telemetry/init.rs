use opentelemetry::KeyValue;
use opentelemetry::global;
use opentelemetry_appender_tracing::layer::OpenTelemetryTracingBridge;
use opentelemetry_otlp::WithExportConfig;
use opentelemetry_sdk::{Resource, logs::SdkLoggerProvider, trace::SdkTracerProvider};
use std::time::Duration;
use tracing_opentelemetry::OpenTelemetryLayer;
use tracing_subscriber::{EnvFilter, Layer, layer::SubscriberExt, util::SubscriberInitExt};

use crate::config::Config;

pub struct TelemetryGuard {
    pub tracer_provider: SdkTracerProvider,
    pub logger_provider: SdkLoggerProvider,
}

impl TelemetryGuard {
    pub fn shutdown(&self) {
        if let Err(e) = self.tracer_provider.shutdown() {
            eprintln!("Error shutting down tracer provider: {e}");
        }
        if let Err(e) = self.logger_provider.shutdown() {
            eprintln!("Error shutting down logger provider: {e}");
        }
    }
}

pub fn init_telemetry(config: &Config) -> anyhow::Result<TelemetryGuard> {
    let resource = Resource::builder()
        .with_service_name(config.otel_service_name.clone())
        .with_attribute(KeyValue::new("service.version", "1.0.0"))
        .with_attribute(KeyValue::new("service.namespace", "examples"))
        .with_attribute(KeyValue::new(
            "deployment.environment",
            config.environment.clone(),
        ))
        .build();

    let trace_exporter = opentelemetry_otlp::SpanExporter::builder()
        .with_tonic()
        .with_endpoint(&config.otel_exporter_endpoint)
        .with_timeout(Duration::from_secs(10))
        .build()?;

    let tracer_provider = SdkTracerProvider::builder()
        .with_batch_exporter(trace_exporter)
        .with_resource(resource.clone())
        .build();

    global::set_tracer_provider(tracer_provider.clone());

    let log_exporter = opentelemetry_otlp::LogExporter::builder()
        .with_tonic()
        .with_endpoint(&config.otel_exporter_endpoint)
        .with_timeout(Duration::from_secs(10))
        .build()?;

    let logger_provider = SdkLoggerProvider::builder()
        .with_batch_exporter(log_exporter)
        .with_resource(resource)
        .build();

    let otel_log_layer = OpenTelemetryTracingBridge::new(&logger_provider);

    let tracer = global::tracer(config.otel_service_name.clone());
    let telemetry_layer = OpenTelemetryLayer::new(tracer);

    let env_filter =
        EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info,sqlx=warn"));

    let fmt_layer = if config.is_production() {
        tracing_subscriber::fmt::layer().json().boxed()
    } else {
        tracing_subscriber::fmt::layer().pretty().boxed()
    };

    tracing_subscriber::registry()
        .with(env_filter)
        .with(telemetry_layer)
        .with(otel_log_layer)
        .with(fmt_layer)
        .init();

    tracing::info!(
        service = %config.otel_service_name,
        endpoint = %config.otel_exporter_endpoint,
        "Telemetry initialized with OTLP trace and log export"
    );

    Ok(TelemetryGuard {
        tracer_provider,
        logger_provider,
    })
}
