use std::collections::HashMap;
use std::time::Duration;

use opentelemetry::propagation::TextMapPropagator;
use opentelemetry_sdk::propagation::TraceContextPropagator;
use tokio::signal;
use tokio::sync::broadcast;
use tracing::Instrument;
use tracing_opentelemetry::OpenTelemetrySpanExt;

mod config {
    pub use actix_postgres::config::*;
}
mod database {
    pub use actix_postgres::database::*;
}
mod telemetry {
    pub use actix_postgres::telemetry::*;
}
mod jobs {
    pub use actix_postgres::jobs::*;
}

use config::Config;
use database::create_pool;
use jobs::{JobQueue, NotificationHandler};
use telemetry::init_telemetry;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let config = Config::from_env();

    let telemetry_guard = init_telemetry(&config)?;

    tracing::info!(
        environment = %config.environment,
        "Starting worker"
    );

    let pool = create_pool(&config).await?;
    let job_queue = JobQueue::new(pool);

    let (shutdown_tx, _) = broadcast::channel::<()>(1);

    let worker_handle = {
        let job_queue = job_queue.clone();
        let mut shutdown_rx = shutdown_tx.subscribe();

        tokio::spawn(async move {
            let mut interval = tokio::time::interval(Duration::from_secs(1));

            loop {
                tokio::select! {
                    _ = interval.tick() => {
                        if let Err(e) = process_job(&job_queue).await {
                            tracing::error!(error = %e, "Error processing job");
                        }
                    }
                    _ = shutdown_rx.recv() => {
                        tracing::info!("Worker received shutdown signal");
                        break;
                    }
                }
            }
        })
    };

    shutdown_signal().await;
    let _ = shutdown_tx.send(());

    worker_handle.await?;

    tracing::info!("Worker shutdown complete");
    telemetry_guard.shutdown();

    Ok(())
}

async fn process_job(job_queue: &JobQueue) -> anyhow::Result<()> {
    let Some(job) = job_queue.dequeue().await? else {
        return Ok(());
    };

    let parent_context = extract_trace_context(&job.trace_context);

    let span = tracing::info_span!(
        "job.process",
        job_id = job.id,
        job_kind = %job.kind,
    );
    let _ = span.set_parent(parent_context);

    async {
        tracing::info!(job_id = job.id, kind = %job.kind, "Processing job");

        let result = match job.kind.as_str() {
            "notification" => NotificationHandler::handle(&job).await,
            _ => {
                tracing::warn!(job_id = job.id, kind = %job.kind, "Unknown job kind");
                Err(anyhow::anyhow!("Unknown job kind: {}", job.kind))
            }
        };

        match result {
            Ok(()) => {
                job_queue.complete(job.id).await?;
                tracing::info!(job_id = job.id, "Job completed");
            }
            Err(e) => {
                job_queue.fail(job.id, &e.to_string()).await?;
                tracing::error!(job_id = job.id, error = %e, "Job failed");
            }
        }

        Ok(())
    }
    .instrument(span)
    .await
}

fn extract_trace_context(trace_context: &Option<serde_json::Value>) -> opentelemetry::Context {
    let Some(ctx_value) = trace_context else {
        return opentelemetry::Context::new();
    };

    let carrier: HashMap<String, String> = match serde_json::from_value(ctx_value.clone()) {
        Ok(c) => c,
        Err(_) => return opentelemetry::Context::new(),
    };

    let propagator = TraceContextPropagator::new();
    propagator.extract(&carrier)
}

async fn shutdown_signal() {
    let ctrl_c = async {
        signal::ctrl_c()
            .await
            .expect("Failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("Failed to install signal handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }

    tracing::info!("Shutdown signal received");
}
