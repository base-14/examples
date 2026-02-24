use chrono::NaiveDate;
use sqlx::PgPool;

use crate::db::data_points::{IndicatorData, query_indicator_data};
use crate::error::AppError;

#[derive(Debug)]
pub struct RetrieveResult {
    pub indicators: Vec<IndicatorData>,
    pub total_data_points: usize,
}

#[tracing::instrument(
    name = "pipeline_stage retrieve",
    skip(pool),
    fields(
        pipeline.stage = "retrieve",
        report.indicators_count,
        report.data_points,
    )
)]
pub async fn retrieve(
    pool: &PgPool,
    indicator_codes: &[String],
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> Result<RetrieveResult, AppError> {
    let indicators = query_indicator_data(pool, indicator_codes, start_date, end_date)
        .await
        .map_err(AppError::Database)?;

    let total_data_points: usize = indicators.iter().map(|i| i.values.len()).sum();

    let span = tracing::Span::current();
    span.record("report.indicators_count", indicators.len());
    span.record("report.data_points", total_data_points);

    if indicators.is_empty() {
        return Err(AppError::Pipeline(
            "No data found for requested indicators".into(),
        ));
    }

    Ok(RetrieveResult {
        indicators,
        total_data_points,
    })
}
