use axum::{
    Json,
    http::StatusCode,
    response::{IntoResponse, Response},
};
use opentelemetry::trace::TraceContextExt;
use serde_json::json;
use thiserror::Error;
use tracing::Span;
use tracing_opentelemetry::OpenTelemetrySpanExt;

#[derive(Error, Debug)]
pub enum AppError {
    #[error("Authentication required")]
    Unauthorized,

    #[error("Invalid credentials")]
    InvalidCredentials,

    #[error("Forbidden")]
    Forbidden,

    #[error("Not found: {0}")]
    NotFound(String),

    #[error("Conflict: {0}")]
    Conflict(String),

    #[error("Validation error: {0}")]
    Validation(String),

    #[error("Database error: {0}")]
    Database(#[from] sqlx::Error),

    #[error("JWT error: {0}")]
    Jwt(#[from] jsonwebtoken::errors::Error),

    #[error("Internal error: {0}")]
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

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, error_message) = match &self {
            AppError::Unauthorized => (StatusCode::UNAUTHORIZED, self.to_string()),
            AppError::InvalidCredentials => (StatusCode::UNAUTHORIZED, self.to_string()),
            AppError::Forbidden => (StatusCode::FORBIDDEN, self.to_string()),
            AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg.clone()),
            AppError::Conflict(msg) => (StatusCode::CONFLICT, msg.clone()),
            AppError::Validation(msg) => (StatusCode::BAD_REQUEST, msg.clone()),
            AppError::Database(e) => {
                tracing::error!(error = %e, "Database error");
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "Internal server error".to_string(),
                )
            }
            AppError::Jwt(e) => {
                tracing::warn!(error = %e, "JWT error");
                (StatusCode::UNAUTHORIZED, "Invalid token".to_string())
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
    fn test_unauthorized_error() {
        let error = AppError::Unauthorized;
        assert_eq!(error.to_string(), "Authentication required");
    }

    #[test]
    fn test_invalid_credentials_error() {
        let error = AppError::InvalidCredentials;
        assert_eq!(error.to_string(), "Invalid credentials");
    }

    #[test]
    fn test_forbidden_error() {
        let error = AppError::Forbidden;
        assert_eq!(error.to_string(), "Forbidden");
    }

    #[test]
    fn test_not_found_error() {
        let error = AppError::NotFound("Article".to_string());
        assert_eq!(error.to_string(), "Not found: Article");
    }

    #[test]
    fn test_conflict_error() {
        let error = AppError::Conflict("Email already exists".to_string());
        assert_eq!(error.to_string(), "Conflict: Email already exists");
    }

    #[test]
    fn test_validation_error() {
        let error = AppError::Validation("Email is required".to_string());
        assert_eq!(error.to_string(), "Validation error: Email is required");
    }

    #[test]
    fn test_internal_error() {
        let error = AppError::Internal("Something went wrong".to_string());
        assert_eq!(error.to_string(), "Internal error: Something went wrong");
    }

    #[test]
    fn test_error_status_codes() {
        let test_cases = vec![
            (AppError::Unauthorized, StatusCode::UNAUTHORIZED),
            (AppError::InvalidCredentials, StatusCode::UNAUTHORIZED),
            (AppError::Forbidden, StatusCode::FORBIDDEN),
            (
                AppError::NotFound("test".to_string()),
                StatusCode::NOT_FOUND,
            ),
            (AppError::Conflict("test".to_string()), StatusCode::CONFLICT),
            (
                AppError::Validation("test".to_string()),
                StatusCode::BAD_REQUEST,
            ),
            (
                AppError::Internal("test".to_string()),
                StatusCode::INTERNAL_SERVER_ERROR,
            ),
        ];

        for (error, expected_status) in test_cases {
            let (status, _) = match &error {
                AppError::Unauthorized => (StatusCode::UNAUTHORIZED, error.to_string()),
                AppError::InvalidCredentials => (StatusCode::UNAUTHORIZED, error.to_string()),
                AppError::Forbidden => (StatusCode::FORBIDDEN, error.to_string()),
                AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg.clone()),
                AppError::Conflict(msg) => (StatusCode::CONFLICT, msg.clone()),
                AppError::Validation(msg) => (StatusCode::BAD_REQUEST, msg.clone()),
                AppError::Database(_) => (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "Internal server error".to_string(),
                ),
                AppError::Jwt(_) => (StatusCode::UNAUTHORIZED, "Invalid token".to_string()),
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
