use actix_web::{FromRequest, HttpRequest, dev::Payload, web};
use std::future::{Ready, ready};

use crate::{error::AppError, services::AuthService};

pub struct AuthUser(pub i32);

impl FromRequest for AuthUser {
    type Error = AppError;
    type Future = Ready<Result<Self, Self::Error>>;

    fn from_request(req: &HttpRequest, _payload: &mut Payload) -> Self::Future {
        let result = extract_and_validate(req, false);
        ready(result.map(|id| AuthUser(id.expect("token required"))))
    }
}

pub struct OptionalAuthUser(pub Option<i32>);

impl FromRequest for OptionalAuthUser {
    type Error = AppError;
    type Future = Ready<Result<Self, Self::Error>>;

    fn from_request(req: &HttpRequest, _payload: &mut Payload) -> Self::Future {
        let result = extract_and_validate(req, true);
        ready(result.map(OptionalAuthUser))
    }
}

fn extract_and_validate(req: &HttpRequest, optional: bool) -> Result<Option<i32>, AppError> {
    let auth_service = req
        .app_data::<web::Data<AuthService>>()
        .ok_or(AppError::Internal("AuthService not configured".to_string()))?;

    let token = req
        .headers()
        .get("Authorization")
        .and_then(|value| value.to_str().ok())
        .and_then(|header| header.strip_prefix("Bearer "));

    match token {
        Some(token) => match auth_service.validate_token(token) {
            Ok(user_id) => Ok(Some(user_id)),
            Err(_) if optional => Ok(None),
            Err(e) => Err(e),
        },
        None if optional => Ok(None),
        None => Err(AppError::Unauthorized),
    }
}
