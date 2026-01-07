use axum::{extract::State, http::StatusCode, Json};
use serde_json::{json, Value};

use crate::{
    error::AppResult,
    middleware::AuthUser,
    models::{LoginInput, ProfileResponse, RegisterInput, UserResponse},
    AppState,
};

pub async fn register(
    State(state): State<AppState>,
    Json(input): Json<RegisterInput>,
) -> AppResult<(StatusCode, Json<UserResponse>)> {
    let user = state.auth_service.register(input).await?;

    Ok((StatusCode::CREATED, Json(UserResponse { user })))
}

pub async fn login(
    State(state): State<AppState>,
    Json(input): Json<LoginInput>,
) -> AppResult<Json<UserResponse>> {
    let user = state.auth_service.login(input).await?;

    Ok(Json(UserResponse { user }))
}

pub async fn get_user(
    State(state): State<AppState>,
    AuthUser(user_id): AuthUser,
) -> AppResult<Json<ProfileResponse>> {
    let user = state.auth_service.get_user(user_id).await?;

    Ok(Json(ProfileResponse::from(user)))
}

pub async fn logout() -> Json<Value> {
    Json(json!({ "message": "Logged out successfully" }))
}
