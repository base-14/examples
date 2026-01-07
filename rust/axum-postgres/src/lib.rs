pub mod config;
pub mod database;
pub mod error;
pub mod handlers;
pub mod jobs;
pub mod middleware;
pub mod models;
pub mod repository;
pub mod routes;
pub mod services;
pub mod telemetry;

pub use config::Config;

use services::{ArticleService, AuthService};
use sqlx::PgPool;

#[derive(Clone)]
pub struct AppState {
    pub pool: PgPool,
    pub auth_service: AuthService,
    pub article_service: ArticleService,
}
