use axum::{
    Json,
    extract::{Path, Query, State},
};
use serde::Deserialize;
use uuid::Uuid;

use crate::AppState;
use crate::db::reports::ReportRow;
use crate::error::{AppError, AppResult};
use crate::pipeline::{ReportRequest, generate_report};

#[derive(Debug, Deserialize)]
pub struct CreateReportBody {
    pub indicators: Vec<String>,
    pub start_date: String,
    pub end_date: String,
}

#[derive(Debug, Deserialize)]
pub struct ListQuery {
    pub limit: Option<i64>,
    pub offset: Option<i64>,
}

pub async fn create_report(
    State(state): State<AppState>,
    Json(body): Json<CreateReportBody>,
) -> AppResult<Json<serde_json::Value>> {
    if body.indicators.is_empty() {
        return Err(AppError::Validation("indicators must not be empty".into()));
    }

    let start_date = chrono::NaiveDate::parse_from_str(&body.start_date, "%Y-%m-%d")
        .map_err(|_| AppError::Validation("invalid start_date format, use YYYY-MM-DD".into()))?;

    let end_date = chrono::NaiveDate::parse_from_str(&body.end_date, "%Y-%m-%d")
        .map_err(|_| AppError::Validation("invalid end_date format, use YYYY-MM-DD".into()))?;

    if start_date >= end_date {
        return Err(AppError::Validation(
            "start_date must be before end_date".into(),
        ));
    }

    let request = ReportRequest {
        indicators: body.indicators,
        start_date,
        end_date,
    };

    let report = generate_report(
        &state.pool,
        &state.llm_client,
        &state.config.llm_model_capable,
        &state.config.llm_provider,
        &request,
    )
    .await?;

    Ok(Json(serde_json::to_value(report).unwrap()))
}

pub async fn list_reports(
    State(state): State<AppState>,
    Query(params): Query<ListQuery>,
) -> AppResult<Json<Vec<ReportRow>>> {
    let limit = params.limit.unwrap_or(20);
    let offset = params.offset.unwrap_or(0);

    let reports = crate::db::reports::list_reports(&state.pool, limit, offset)
        .await
        .map_err(AppError::Database)?;

    Ok(Json(reports))
}

pub async fn get_report(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> AppResult<Json<ReportRow>> {
    let report = crate::db::reports::get_report(&state.pool, id)
        .await
        .map_err(AppError::Database)?
        .ok_or_else(|| AppError::NotFound(format!("Report {} not found", id)))?;

    Ok(Json(report))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_list_query_defaults() {
        let query: ListQuery = serde_json::from_str("{}").unwrap();
        assert_eq!(query.limit, None);
        assert_eq!(query.offset, None);
    }

    #[test]
    fn test_list_query_with_values() {
        let query: ListQuery = serde_json::from_str(r#"{"limit": 10, "offset": 5}"#).unwrap();
        assert_eq!(query.limit, Some(10));
        assert_eq!(query.offset, Some(5));
    }

    #[test]
    fn test_create_report_body_deserialize() {
        let body: CreateReportBody = serde_json::from_str(
            r#"{"indicators": ["UNRATE", "CPIAUCSL"], "start_date": "2020-01-01", "end_date": "2023-12-31"}"#,
        )
        .unwrap();
        assert_eq!(body.indicators, vec!["UNRATE", "CPIAUCSL"]);
        assert_eq!(body.start_date, "2020-01-01");
        assert_eq!(body.end_date, "2023-12-31");
    }

    #[test]
    fn test_create_report_body_empty_indicators() {
        let body: CreateReportBody = serde_json::from_str(
            r#"{"indicators": [], "start_date": "2020-01-01", "end_date": "2023-12-31"}"#,
        )
        .unwrap();
        assert!(body.indicators.is_empty());
    }
}
