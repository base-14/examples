use serde::Serialize;
use sqlx::{PgPool, Row};
use std::collections::HashMap;
use tracing::{Span, instrument};

use crate::telemetry::JOBS_ENQUEUED;

#[derive(Clone)]
pub struct JobQueue {
    pool: PgPool,
}

impl JobQueue {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    pub fn pool(&self) -> &PgPool {
        &self.pool
    }

    #[instrument(name = "job.enqueue", skip(self, payload))]
    pub async fn enqueue<T: Serialize>(&self, kind: &str, payload: T) -> Result<i64, sqlx::Error> {
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

    fn capture_trace_context(&self) -> Option<serde_json::Value> {
        use opentelemetry::trace::TraceContextExt;
        use tracing_opentelemetry::OpenTelemetrySpanExt;

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
