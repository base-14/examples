use axum::Json;
use serde_json::{Value, json};

pub async fn health() -> Json<Value> {
    Json(json!({
        "status": "ok",
        "service": "ai-report-generator",
        "version": "1.0.0"
    }))
}
