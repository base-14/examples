use axum::{
    extract::FromRequestParts,
    http::{header::AUTHORIZATION, request::Parts},
};

use crate::{error::AppError, AppState};

pub struct AuthUser(pub i32);

impl FromRequestParts<AppState> for AuthUser {
    type Rejection = AppError;

    async fn from_request_parts(parts: &mut Parts, state: &AppState) -> Result<Self, Self::Rejection> {
        let token = extract_token(parts)?;
        let user_id = state.auth_service.validate_token(&token)?;
        Ok(AuthUser(user_id))
    }
}

pub struct OptionalAuthUser(pub Option<i32>);

impl FromRequestParts<AppState> for OptionalAuthUser {
    type Rejection = AppError;

    async fn from_request_parts(parts: &mut Parts, state: &AppState) -> Result<Self, Self::Rejection> {
        match extract_token(parts) {
            Ok(token) => {
                match state.auth_service.validate_token(&token) {
                    Ok(user_id) => Ok(OptionalAuthUser(Some(user_id))),
                    Err(_) => Ok(OptionalAuthUser(None)),
                }
            }
            Err(_) => Ok(OptionalAuthUser(None)),
        }
    }
}

fn extract_token(parts: &Parts) -> Result<String, AppError> {
    let auth_header = parts
        .headers
        .get(AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .ok_or(AppError::Unauthorized)?;

    if !auth_header.starts_with("Bearer ") {
        return Err(AppError::Unauthorized);
    }

    Ok(auth_header[7..].to_string())
}
