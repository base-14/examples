use opentelemetry::global;
use opentelemetry::KeyValue;
use opentelemetry_otlp::WithExportConfig;
use opentelemetry_sdk::{
    trace::SdkTracerProvider,
    Resource,
};
use tracing_opentelemetry::OpenTelemetryLayer;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt, EnvFilter, Layer};
use std::time::Duration;

use crate::config::Config;

pub fn init_telemetry(config: &Config) -> anyhow::Result<SdkTracerProvider> {
    let resource = Resource::builder()
        .with_service_name(config.otel_service_name.clone())
        .with_attribute(KeyValue::new("service.version", "1.0.0"))
        .with_attribute(KeyValue::new("service.namespace", "examples"))
        .with_attribute(KeyValue::new("deployment.environment", config.environment.clone()))
        .build();

    let exporter = opentelemetry_otlp::SpanExporter::builder()
        .with_tonic()
        .with_endpoint(&config.otel_exporter_endpoint)
        .with_timeout(Duration::from_secs(10))
        .build()?;

    let tracer_provider = SdkTracerProvider::builder()
        .with_batch_exporter(exporter)
        .with_resource(resource)
        .build();

    global::set_tracer_provider(tracer_provider.clone());

    let tracer = global::tracer(config.otel_service_name.clone());
    let telemetry_layer = OpenTelemetryLayer::new(tracer);

    let env_filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info,sqlx=warn,tower_http=debug"));

    let fmt_layer = if config.is_production() {
        tracing_subscriber::fmt::layer()
            .json()
            .boxed()
    } else {
        tracing_subscriber::fmt::layer()
            .pretty()
            .boxed()
    };

    tracing_subscriber::registry()
        .with(env_filter)
        .with(telemetry_layer)
        .with(fmt_layer)
        .init();

    tracing::info!(
        service = %config.otel_service_name,
        endpoint = %config.otel_exporter_endpoint,
        "Telemetry initialized"
    );

    Ok(tracer_provider)
}
