use axum::{extract::State, http::StatusCode, Json};
use serde_json::{json, Value};
use sqlx::Row;

use crate::AppState;

pub async fn health_check(State(state): State<AppState>) -> (StatusCode, Json<Value>) {
    let db_status = sqlx::query("SELECT 1 as one")
        .fetch_one(&state.pool)
        .await
        .map(|row: sqlx::postgres::PgRow| {
            let _: i32 = row.get("one");
            "healthy"
        })
        .unwrap_or("unhealthy");

    let status = if db_status == "healthy" {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    };

    (
        status,
        Json(json!({
            "status": if status == StatusCode::OK { "ok" } else { "error" },
            "database": db_status,
            "service": "rust-axum-postgres",
        })),
    )
}
