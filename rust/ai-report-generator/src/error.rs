use axum::{
    Json,
    http::StatusCode,
    response::{IntoResponse, Response},
};
use opentelemetry::KeyValue;
use opentelemetry::trace::{Status, TraceContextExt};
use serde_json::json;
use thiserror::Error;
use tracing::Span;
use tracing_opentelemetry::OpenTelemetrySpanExt;

#[derive(Error, Debug)]
pub enum AppError {
    #[error("Validation error: {0}")]
    Validation(String),

    #[error("Not found: {0}")]
    NotFound(String),

    #[error("Database error: {0}")]
    Database(#[from] sqlx::Error),

    #[error("LLM error: {0}")]
    Llm(String),

    #[error("Pipeline error: {0}")]
    Pipeline(String),

    #[error("Internal error: {0}")]
    #[allow(dead_code)]
    Internal(String),
}

fn get_trace_id() -> Option<String> {
    let span = Span::current();
    let context = span.context();
    let span_ref = context.span();
    let span_context = span_ref.span_context();

    if span_context.is_valid() {
        Some(span_context.trace_id().to_string())
    } else {
        None
    }
}

impl AppError {
    fn error_type(&self) -> &'static str {
        match self {
            AppError::Validation(_) => "validation_error",
            AppError::NotFound(_) => "not_found",
            AppError::Database(_) => "database_error",
            AppError::Llm(_) => "llm_error",
            AppError::Pipeline(_) => "pipeline_error",
            AppError::Internal(_) => "internal_error",
        }
    }
}

fn record_on_active_span(error_type: &'static str, message: &str) {
    let span = Span::current();
    span.add_event(
        "exception",
        vec![
            KeyValue::new("exception.type", error_type),
            KeyValue::new("exception.message", message.to_string()),
        ],
    );
    span.set_attribute("error.type", error_type);
    span.set_status(Status::error(message.to_string()));
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        record_on_active_span(self.error_type(), &self.to_string());

        let (status, error_message) = match &self {
            AppError::Validation(msg) => (StatusCode::BAD_REQUEST, msg.clone()),
            AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg.clone()),
            AppError::Database(e) => {
                tracing::error!(error = %e, "Database error");
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "Internal server error".to_string(),
                )
            }
            AppError::Llm(msg) => {
                tracing::error!(error = %msg, "LLM error");
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "Internal server error".to_string(),
                )
            }
            AppError::Pipeline(msg) => {
                tracing::error!(error = %msg, "Pipeline error");
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "Internal server error".to_string(),
                )
            }
            AppError::Internal(msg) => {
                tracing::error!(error = %msg, "Internal error");
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "Internal server error".to_string(),
                )
            }
        };

        let body = if let Some(trace_id) = get_trace_id() {
            json!({
                "error": error_message,
                "status": status.as_u16(),
                "trace_id": trace_id,
            })
        } else {
            json!({
                "error": error_message,
                "status": status.as_u16(),
            })
        };

        (status, Json(body)).into_response()
    }
}

pub type AppResult<T> = Result<T, AppError>;

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::StatusCode;

    #[test]
    fn test_validation_error() {
        let error = AppError::Validation("field is required".to_string());
        assert_eq!(error.to_string(), "Validation error: field is required");
    }

    #[test]
    fn test_not_found_error() {
        let error = AppError::NotFound("Report".to_string());
        assert_eq!(error.to_string(), "Not found: Report");
    }

    #[test]
    fn test_llm_error() {
        let error = AppError::Llm("provider timeout".to_string());
        assert_eq!(error.to_string(), "LLM error: provider timeout");
    }

    #[test]
    fn test_pipeline_error() {
        let error = AppError::Pipeline("stage failed".to_string());
        assert_eq!(error.to_string(), "Pipeline error: stage failed");
    }

    #[test]
    fn test_internal_error() {
        let error = AppError::Internal("unexpected".to_string());
        assert_eq!(error.to_string(), "Internal error: unexpected");
    }

    #[test]
    fn test_error_types() {
        assert_eq!(
            AppError::Validation("test".to_string()).error_type(),
            "validation_error"
        );
        assert_eq!(
            AppError::NotFound("test".to_string()).error_type(),
            "not_found"
        );
        assert_eq!(AppError::Llm("test".to_string()).error_type(), "llm_error");
        assert_eq!(
            AppError::Pipeline("test".to_string()).error_type(),
            "pipeline_error"
        );
        assert_eq!(
            AppError::Internal("test".to_string()).error_type(),
            "internal_error"
        );
    }

    #[test]
    fn test_error_status_codes() {
        let test_cases = vec![
            (
                AppError::Validation("test".to_string()),
                StatusCode::BAD_REQUEST,
            ),
            (
                AppError::NotFound("test".to_string()),
                StatusCode::NOT_FOUND,
            ),
            (
                AppError::Llm("test".to_string()),
                StatusCode::INTERNAL_SERVER_ERROR,
            ),
            (
                AppError::Pipeline("test".to_string()),
                StatusCode::INTERNAL_SERVER_ERROR,
            ),
            (
                AppError::Internal("test".to_string()),
                StatusCode::INTERNAL_SERVER_ERROR,
            ),
        ];

        for (error, expected_status) in test_cases {
            let (status, _) = match &error {
                AppError::Validation(msg) => (StatusCode::BAD_REQUEST, msg.clone()),
                AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg.clone()),
                AppError::Database(_) => (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "Internal server error".to_string(),
                ),
                AppError::Llm(_) => (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "Internal server error".to_string(),
                ),
                AppError::Pipeline(_) => (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "Internal server error".to_string(),
                ),
                AppError::Internal(_) => (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "Internal server error".to_string(),
                ),
            };
            assert_eq!(status, expected_status);
        }
    }

    #[test]
    fn test_app_result_ok() {
        fn returns_ok() -> AppResult<i32> {
            Ok(42)
        }
        let result = returns_ok();
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), 42);
    }

    #[test]
    fn test_app_result_err() {
        fn returns_err() -> AppResult<i32> {
            Err(AppError::NotFound("test".to_string()))
        }
        let result = returns_err();
        assert!(result.is_err());
    }
}
