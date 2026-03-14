use std::collections::HashMap;
use std::time::Duration;

use opentelemetry::propagation::TextMapPropagator;
use opentelemetry_sdk::propagation::TraceContextPropagator;
use serde::Deserialize;
use sqlx::{PgPool, Row};
use tokio::signal;
use tokio::sync::broadcast;
use tracing::Instrument;
use tracing_opentelemetry::OpenTelemetrySpanExt;

use actix_postgres::config::Config;
use actix_postgres::database::create_pool;
use actix_postgres::jobs::JobQueue;
use actix_postgres::telemetry::{JOBS_COMPLETED, JOBS_FAILED, TelemetryGuard, init_telemetry};

struct Job {
    id: i64,
    kind: String,
    payload: serde_json::Value,
    trace_context: Option<serde_json::Value>,
}

#[derive(Debug, Deserialize)]
struct NotificationPayload {
    article_id: i32,
    title: String,
}

struct NotificationHandler;

impl NotificationHandler {
    #[tracing::instrument(name = "job.notification.handle", skip(job), fields(job_id = job.id))]
    async fn handle(job: &Job) -> Result<(), anyhow::Error> {
        let payload: NotificationPayload = serde_json::from_value(job.payload.clone())?;

        tracing::info!(
            article_id = payload.article_id,
            title = %payload.title,
            "Processing notification for new article"
        );

        tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;

        tracing::info!(
            article_id = payload.article_id,
            "Notification sent successfully"
        );

        Ok(())
    }
}

async fn dequeue(pool: &PgPool) -> Result<Option<Job>, sqlx::Error> {
    let result = sqlx::query(
        r#"
        UPDATE jobs
        SET status = 'processing',
            started_at = NOW(),
            attempts = attempts + 1
        WHERE id = (
            SELECT id FROM jobs
            WHERE status = 'pending'
              AND scheduled_at <= NOW()
              AND attempts < max_attempts
            ORDER BY priority DESC, scheduled_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING id, kind, payload, trace_context
        "#,
    )
    .fetch_optional(pool)
    .await?;

    Ok(result.map(|row| Job {
        id: row.get("id"),
        kind: row.get("kind"),
        payload: row.get("payload"),
        trace_context: row.get("trace_context"),
    }))
}

async fn complete(pool: &PgPool, job_id: i64) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        UPDATE jobs
        SET status = 'completed', completed_at = NOW()
        WHERE id = $1
        "#,
    )
    .bind(job_id)
    .execute(pool)
    .await?;

    JOBS_COMPLETED.add(1, &[]);
    Ok(())
}

async fn fail(pool: &PgPool, job_id: i64, error: &str) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        UPDATE jobs
        SET status = CASE
                WHEN attempts >= max_attempts THEN 'failed'
                ELSE 'pending'
            END,
            failed_at = NOW(),
            error_message = $2
        WHERE id = $1
        "#,
    )
    .bind(job_id)
    .bind(error)
    .execute(pool)
    .await?;

    JOBS_FAILED.add(1, &[]);
    Ok(())
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let config = Config::from_env();

    let _telemetry: TelemetryGuard = init_telemetry(&config)?;

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
    _telemetry.shutdown();

    Ok(())
}

async fn process_job(job_queue: &JobQueue) -> anyhow::Result<()> {
    let pool = job_queue.pool();
    let Some(job) = dequeue(pool).await? else {
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
                complete(pool, job.id).await?;
                tracing::info!(job_id = job.id, "Job completed");
            }
            Err(e) => {
                fail(pool, job.id, &e.to_string()).await?;
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
