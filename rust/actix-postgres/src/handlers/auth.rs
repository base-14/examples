use actix_web::{HttpResponse, web};
use serde_json::json;

use crate::{
    error::AppResult,
    middleware::AuthUser,
    models::{LoginInput, ProfileResponse, RegisterInput, UserResponse},
    services::AuthService,
};

pub async fn register(
    auth_service: web::Data<AuthService>,
    input: web::Json<RegisterInput>,
) -> AppResult<HttpResponse> {
    let user = auth_service.register(input.into_inner()).await?;

    Ok(HttpResponse::Created().json(UserResponse { user }))
}

pub async fn login(
    auth_service: web::Data<AuthService>,
    input: web::Json<LoginInput>,
) -> AppResult<HttpResponse> {
    let user = auth_service.login(input.into_inner()).await?;

    Ok(HttpResponse::Ok().json(UserResponse { user }))
}

pub async fn get_user(
    auth_service: web::Data<AuthService>,
    auth: AuthUser,
) -> AppResult<HttpResponse> {
    let user = auth_service.get_user(auth.0).await?;

    Ok(HttpResponse::Ok().json(ProfileResponse::from(user)))
}

pub async fn logout() -> HttpResponse {
    HttpResponse::Ok().json(json!({ "message": "Logged out successfully" }))
}
