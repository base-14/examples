use axum::Json;
use axum::extract::State;
use serde_json::{Value, json};

use crate::AppState;
use crate::llm::GenerateRequest;

pub async fn trigger_llm_error(State(state): State<AppState>) -> Json<Value> {
    let req = GenerateRequest {
        model: "nonexistent-model-99999".to_string(),
        system: String::new(),
        prompt: "test error injection".to_string(),
        temperature: 0.0,
        max_tokens: 1,
        stage: "test".to_string(),
    };

    match state.llm_client.generate(&req).await {
        Ok(_) => Json(json!({"status": "unexpected_success"})),
        Err(e) => Json(json!({
            "status": "error_triggered",
            "error": e.to_string(),
        })),
    }
}
