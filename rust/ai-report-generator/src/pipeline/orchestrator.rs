use chrono::NaiveDate;
use opentelemetry::trace::TraceContextExt;
use serde::Deserialize;
use sqlx::PgPool;
use tracing_opentelemetry::OpenTelemetrySpanExt;

use crate::db::reports::InsertReport;
use crate::error::AppError;
use crate::llm::LlmClient;
use crate::telemetry::metrics::{REPORT_DATA_POINTS, REPORT_GENERATION_DURATION, REPORT_SECTIONS};

use super::format::{self, FormatParams, Report};
use super::{analyze, generate, retrieve};

#[derive(Debug, Clone, Deserialize)]
pub struct ReportRequest {
    pub indicators: Vec<String>,
    pub start_date: NaiveDate,
    pub end_date: NaiveDate,
}

#[tracing::instrument(
    name = "pipeline report",
    skip(pool, llm_client),
    fields(
        report.id,
        report.indicators_count,
        report.duration_ms,
    )
)]
pub async fn generate_report(
    pool: &PgPool,
    llm_client: &LlmClient,
    model_capable: &str,
    model_fast: &str,
    request: &ReportRequest,
) -> Result<Report, AppError> {
    let start = std::time::Instant::now();

    let span = tracing::Span::current();
    let context = span.context();
    let otel_span = context.span();
    let trace_id = otel_span.span_context().trace_id().to_string();

    // Stage 1: Retrieve data from PostgreSQL
    let data = retrieve::retrieve(
        pool,
        &request.indicators,
        request.start_date,
        request.end_date,
    )
    .await?;

    // Stage 2: Analyze trends via LLM (fast model)
    let analysis = analyze::analyze(llm_client, model_fast, &data.indicators).await?;

    // Stage 3: Generate narrative via LLM (capable model)
    let narrative =
        generate::generate(llm_client, model_capable, &data.indicators, &analysis).await?;

    // Stage 4: Format final report
    let duration = start.elapsed();
    let report = format::format_report(FormatParams {
        retrieve_result: &data,
        analysis: &analysis,
        narrative: &narrative,
        indicators_requested: &request.indicators,
        start_date: request.start_date,
        end_date: request.end_date,
        duration,
        trace_id,
    })?;

    // Persist to database
    let sections_json = serde_json::to_value(&report.sections).unwrap_or_default();
    crate::db::reports::insert_report(
        pool,
        &InsertReport {
            id: report.id,
            title: &report.title,
            executive_summary: &report.executive_summary,
            sections: &sections_json,
            indicators_used: &report.indicators_used,
            time_range_start: report.time_range_start,
            time_range_end: report.time_range_end,
            total_data_points: report.total_data_points as i32,
            total_tokens: report.total_tokens as i32,
            total_cost_usd: report.total_cost_usd,
            providers_used: &report.providers_used,
            generation_duration_ms: report.generation_duration_ms as i32,
            trace_id: Some(&report.trace_id),
        },
    )
    .await
    .map_err(AppError::Database)?;

    // Record domain metrics
    REPORT_GENERATION_DURATION.record(duration.as_secs_f64(), &[]);
    REPORT_DATA_POINTS.record(report.total_data_points as f64, &[]);
    REPORT_SECTIONS.record(report.sections.len() as f64, &[]);

    span.record("report.id", report.id.to_string());
    span.record("report.indicators_count", report.indicators_used.len());
    span.record("report.duration_ms", report.generation_duration_ms);

    Ok(report)
}
