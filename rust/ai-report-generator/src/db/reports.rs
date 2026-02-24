use chrono::{DateTime, NaiveDate, Utc};
use serde::Serialize;
use sqlx::PgPool;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, sqlx::FromRow)]
pub struct ReportRow {
    pub id: Uuid,
    pub title: String,
    pub executive_summary: String,
    pub sections: serde_json::Value,
    pub indicators_used: Vec<String>,
    pub time_range_start: NaiveDate,
    pub time_range_end: NaiveDate,
    pub total_data_points: i32,
    pub total_tokens: Option<i32>,
    pub total_cost_usd: Option<f64>,
    pub providers_used: Vec<String>,
    pub generation_duration_ms: Option<i32>,
    pub trace_id: Option<String>,
    pub status: String,
    pub created_at: Option<DateTime<Utc>>,
}

pub struct InsertReport<'a> {
    pub id: Uuid,
    pub title: &'a str,
    pub executive_summary: &'a str,
    pub sections: &'a serde_json::Value,
    pub indicators_used: &'a [String],
    pub time_range_start: NaiveDate,
    pub time_range_end: NaiveDate,
    pub total_data_points: i32,
    pub total_tokens: i32,
    pub total_cost_usd: f64,
    pub providers_used: &'a [String],
    pub generation_duration_ms: i32,
    pub trace_id: Option<&'a str>,
}

#[tracing::instrument(name = "db.reports.insert", skip_all)]
pub async fn insert_report(pool: &PgPool, params: &InsertReport<'_>) -> Result<Uuid, sqlx::Error> {
    let row: (Uuid,) = sqlx::query_as(
        "INSERT INTO reports \
         (id, title, executive_summary, sections, indicators_used, \
          time_range_start, time_range_end, total_data_points, total_tokens, \
          total_cost_usd, providers_used, generation_duration_ms, trace_id) \
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13) \
         RETURNING id",
    )
    .bind(params.id)
    .bind(params.title)
    .bind(params.executive_summary)
    .bind(params.sections)
    .bind(params.indicators_used)
    .bind(params.time_range_start)
    .bind(params.time_range_end)
    .bind(params.total_data_points)
    .bind(params.total_tokens)
    .bind(params.total_cost_usd)
    .bind(params.providers_used)
    .bind(params.generation_duration_ms)
    .bind(params.trace_id)
    .fetch_one(pool)
    .await?;

    Ok(row.0)
}

#[tracing::instrument(name = "db.reports.get", skip(pool))]
pub async fn get_report(pool: &PgPool, id: Uuid) -> Result<Option<ReportRow>, sqlx::Error> {
    sqlx::query_as::<_, ReportRow>(
        "SELECT id, title, executive_summary, sections, indicators_used, \
         time_range_start, time_range_end, total_data_points, total_tokens, \
         total_cost_usd::float8 as total_cost_usd, providers_used, \
         generation_duration_ms, trace_id, status, created_at \
         FROM reports WHERE id = $1",
    )
    .bind(id)
    .fetch_optional(pool)
    .await
}

#[tracing::instrument(name = "db.reports.list", skip(pool))]
pub async fn list_reports(
    pool: &PgPool,
    limit: i64,
    offset: i64,
) -> Result<Vec<ReportRow>, sqlx::Error> {
    sqlx::query_as::<_, ReportRow>(
        "SELECT id, title, executive_summary, sections, indicators_used, \
         time_range_start, time_range_end, total_data_points, total_tokens, \
         total_cost_usd::float8 as total_cost_usd, providers_used, \
         generation_duration_ms, trace_id, status, created_at \
         FROM reports ORDER BY created_at DESC LIMIT $1 OFFSET $2",
    )
    .bind(limit)
    .bind(offset)
    .fetch_all(pool)
    .await
}
