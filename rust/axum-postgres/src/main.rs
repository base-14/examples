use std::net::SocketAddr;
use std::time::Duration;

use axum::http::{Request, Response, StatusCode};
use sqlx::PgPool;
use tokio::net::TcpListener;
use tokio::signal;
use tower_http::{
    cors::{Any, CorsLayer},
    timeout::TimeoutLayer,
    trace::{MakeSpan, OnResponse, TraceLayer},
};
use tracing::Span;

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

#[derive(Clone)]
pub struct AppState {
    pub pool: PgPool,
    pub auth_service: AuthService,
    pub article_service: ArticleService,
}

#[derive(Clone)]
struct HttpMakeSpan;

impl<B> MakeSpan<B> for HttpMakeSpan {
    fn make_span(&mut self, request: &Request<B>) -> Span {
        let method = request.method().as_str();
        let uri = request.uri();
        let path = uri.path();

        tracing::info_span!(
            "HTTP request",
            otel.name = %format!("{} {}", method, path),
            http.method = %method,
            http.route = %path,
            http.target = %uri,
            http.scheme = "http",
            http.flavor = ?request.version(),
            http.user_agent = request.headers()
                .get("user-agent")
                .and_then(|v| v.to_str().ok())
                .unwrap_or(""),
            http.response.status_code = tracing::field::Empty,
            otel.status_code = tracing::field::Empty,
        )
    }
}

#[derive(Clone)]
struct HttpOnResponse;

impl<B> OnResponse<B> for HttpOnResponse {
    fn on_response(self, response: &Response<B>, latency: Duration, span: &Span) {
        let status = response.status().as_u16() as i64;
        span.record("http.response.status_code", status);

        // Set OTel status code based on HTTP status
        if status >= 500 {
            span.record("otel.status_code", "ERROR");
        } else {
            span.record("otel.status_code", "OK");
        }

        tracing::info!(
            http.response.status_code = status,
            latency_ms = latency.as_millis() as i64,
            "finished processing request"
        );
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let config = Config::from_env();

    let _tracer_provider = init_telemetry(&config)?;

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

    let state = AppState {
        pool,
        auth_service,
        article_service,
    };

    let app = routes::create_router(state)
        .layer(
            TraceLayer::new_for_http()
                .make_span_with(HttpMakeSpan)
                .on_response(HttpOnResponse),
        )
        .layer(TimeoutLayer::with_status_code(StatusCode::REQUEST_TIMEOUT, Duration::from_secs(30)))
        .layer(
            CorsLayer::new()
                .allow_origin(Any)
                .allow_methods(Any)
                .allow_headers(Any),
        );

    let addr = SocketAddr::from(([0, 0, 0, 0], config.port));
    let listener = TcpListener::bind(addr).await?;

    tracing::info!(%addr, "Server listening");

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;

    tracing::info!("Server shutdown complete");

    Ok(())
}

async fn shutdown_signal() {
    let ctrl_c = async {
        signal::ctrl_c()
            .await
            .expect("Failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("Failed to install signal handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }

    tracing::info!("Shutdown signal received");
}
