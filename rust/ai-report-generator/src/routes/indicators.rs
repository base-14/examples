use axum::{Json, extract::State};

use crate::AppState;
use crate::db::indicators::Indicator;
use crate::error::{AppError, AppResult};

pub async fn list_indicators(State(state): State<AppState>) -> AppResult<Json<Vec<Indicator>>> {
    let indicators = crate::db::indicators::list_indicators(&state.pool)
        .await
        .map_err(AppError::Database)?;

    Ok(Json(indicators))
}
