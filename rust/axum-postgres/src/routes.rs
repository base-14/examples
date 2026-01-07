use axum::{
    Router,
    routing::{delete, get, post, put},
};

use crate::{AppState, handlers};

pub fn create_router(state: AppState) -> Router {
    Router::new()
        .route("/api/health", get(handlers::health_check))
        .route("/api/register", post(handlers::register))
        .route("/api/login", post(handlers::login))
        .route("/api/user", get(handlers::get_user))
        .route("/api/logout", post(handlers::logout))
        .route("/api/articles", get(handlers::list_articles))
        .route("/api/articles", post(handlers::create_article))
        .route("/api/articles/{slug}", get(handlers::get_article))
        .route("/api/articles/{slug}", put(handlers::update_article))
        .route("/api/articles/{slug}", delete(handlers::delete_article))
        .route(
            "/api/articles/{slug}/favorite",
            post(handlers::favorite_article),
        )
        .route(
            "/api/articles/{slug}/favorite",
            delete(handlers::unfavorite_article),
        )
        .with_state(state)
}
