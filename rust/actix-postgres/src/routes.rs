use actix_web::web;

use crate::handlers;

pub fn configure(cfg: &mut web::ServiceConfig) {
    cfg.route("/api/health", web::get().to(handlers::health_check))
        .route("/api/register", web::post().to(handlers::register))
        .route("/api/login", web::post().to(handlers::login))
        .route("/api/user", web::get().to(handlers::get_user))
        .route("/api/logout", web::post().to(handlers::logout))
        .route("/api/articles", web::get().to(handlers::list_articles))
        .route("/api/articles", web::post().to(handlers::create_article))
        .route("/api/articles/{slug}", web::get().to(handlers::get_article))
        .route(
            "/api/articles/{slug}",
            web::put().to(handlers::update_article),
        )
        .route(
            "/api/articles/{slug}",
            web::delete().to(handlers::delete_article),
        )
        .route(
            "/api/articles/{slug}/favorite",
            web::post().to(handlers::favorite_article),
        )
        .route(
            "/api/articles/{slug}/favorite",
            web::delete().to(handlers::unfavorite_article),
        );
}
