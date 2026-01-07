use serde::{Deserialize, Serialize};
use sqlx::{PgPool, Row};
use std::collections::HashMap;
use tracing::{instrument, Span};

use crate::telemetry::{JOBS_COMPLETED, JOBS_ENQUEUED, JOBS_FAILED};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Job {
    pub id: i64,
    pub kind: String,
    pub payload: serde_json::Value,
    pub status: String,
    pub attempts: i32,
    pub trace_context: Option<serde_json::Value>,
}

#[derive(Clone)]
pub struct JobQueue {
    pool: PgPool,
}

impl JobQueue {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    #[instrument(name = "job.enqueue", skip(self, payload))]
    pub async fn enqueue<T: Serialize>(
        &self,
        kind: &str,
        payload: T,
    ) -> Result<i64, sqlx::Error> {
        let trace_context = self.capture_trace_context();
        let payload_json = serde_json::to_value(&payload).unwrap_or(serde_json::Value::Null);

        let row = sqlx::query(
            r#"
            INSERT INTO jobs (kind, payload, trace_context)
            VALUES ($1, $2, $3)
            RETURNING id
            "#,
        )
        .bind(kind)
        .bind(&payload_json)
        .bind(&trace_context)
        .fetch_one(&self.pool)
        .await?;

        let job_id: i64 = row.get("id");

        JOBS_ENQUEUED.add(1, &[]);
        tracing::info!(job_id, kind, "Job enqueued");

        Ok(job_id)
    }

    #[instrument(name = "job.enqueue_notification", skip(self))]
    pub async fn enqueue_notification(
        &self,
        article_id: i32,
        title: &str,
    ) -> Result<i64, sqlx::Error> {
        let payload = serde_json::json!({
            "article_id": article_id,
            "title": title,
        });

        self.enqueue("notification", payload).await
    }

    pub async fn dequeue(&self) -> Result<Option<Job>, sqlx::Error> {
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
            RETURNING id, kind, payload, status, attempts, trace_context
            "#,
        )
        .fetch_optional(&self.pool)
        .await?;

        Ok(result.map(|row| Job {
            id: row.get("id"),
            kind: row.get("kind"),
            payload: row.get("payload"),
            status: row.get("status"),
            attempts: row.get("attempts"),
            trace_context: row.get("trace_context"),
        }))
    }

    pub async fn complete(&self, job_id: i64) -> Result<(), sqlx::Error> {
        sqlx::query(
            r#"
            UPDATE jobs
            SET status = 'completed', completed_at = NOW()
            WHERE id = $1
            "#,
        )
        .bind(job_id)
        .execute(&self.pool)
        .await?;

        JOBS_COMPLETED.add(1, &[]);
        Ok(())
    }

    pub async fn fail(&self, job_id: i64, error: &str) -> Result<(), sqlx::Error> {
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
        .execute(&self.pool)
        .await?;

        JOBS_FAILED.add(1, &[]);
        Ok(())
    }

    fn capture_trace_context(&self) -> Option<serde_json::Value> {
        use tracing_opentelemetry::OpenTelemetrySpanExt;
        use opentelemetry::trace::TraceContextExt;

        let span = Span::current();
        let context = span.context();
        let otel_span = context.span();
        let span_context = otel_span.span_context();

        if span_context.is_valid() {
            let mut carrier = HashMap::new();
            carrier.insert(
                "traceparent".to_string(),
                format!(
                    "00-{}-{}-{:02x}",
                    span_context.trace_id(),
                    span_context.span_id(),
                    span_context.trace_flags().to_u8()
                ),
            );
            Some(serde_json::to_value(&carrier).unwrap_or(serde_json::Value::Null))
        } else {
            None
        }
    }
}
