use actix_web::{App, HttpServer, web};
use tracing_actix_web::TracingLogger;

mod config;
mod database;
mod error;
mod handlers;
mod jobs;
mod middleware;
mod models;
mod repository;
mod routes;
mod services;
mod telemetry;

use config::Config;
use database::create_pool;
use jobs::JobQueue;
use repository::{ArticleRepository, FavoriteRepository, UserRepository};
use services::{ArticleService, AuthService};
use telemetry::init_telemetry;

#[actix_web::main]
async fn main() -> anyhow::Result<()> {
    let config = Config::from_env();

    let telemetry_guard = init_telemetry(&config)?;

    tracing::info!(
        port = config.port,
        environment = %config.environment,
        "Starting server"
    );

    let pool = create_pool(&config).await?;

    let user_repo = UserRepository::new(pool.clone());
    let article_repo = ArticleRepository::new(pool.clone());
    let favorite_repo = FavoriteRepository::new(pool.clone());
    let job_queue = JobQueue::new(pool.clone());

    let auth_service = AuthService::new(user_repo, &config);
    let article_service = ArticleService::new(article_repo, favorite_repo, job_queue);

    let pool_data = web::Data::new(pool);
    let auth_data = web::Data::new(auth_service);
    let article_data = web::Data::new(article_service);

    let bind_addr = format!("0.0.0.0:{}", config.port);

    tracing::info!(addr = %bind_addr, "Server listening");

    HttpServer::new(move || {
        App::new()
            .wrap(TracingLogger::default())
            .wrap(actix_web::middleware::Compress::default())
            .app_data(pool_data.clone())
            .app_data(auth_data.clone())
            .app_data(article_data.clone())
            .configure(routes::configure)
    })
    .bind(&bind_addr)?
    .run()
    .await?;

    tracing::info!("Server shutdown complete");
    telemetry_guard.shutdown();

    Ok(())
}
