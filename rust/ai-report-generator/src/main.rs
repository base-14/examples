use std::net::SocketAddr;
use std::time::Duration;

use axum::Router;
use axum::http::{Request, Response, StatusCode};
use axum::routing::{get, post};
use opentelemetry::KeyValue;
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
mod db;
mod error;
mod llm;
mod pipeline;
mod routes;
mod telemetry;

use std::sync::Arc;

use config::Config;
use telemetry::{HTTP_REQUEST_DURATION, HTTP_REQUESTS_TOTAL, init_telemetry};

#[derive(Clone)]
pub struct AppState {
    pub pool: PgPool,
    pub config: Config,
    pub llm_client: Arc<llm::LlmClient>,
}

#[derive(Clone)]
struct HttpMakeSpan;

impl<B> MakeSpan<B> for HttpMakeSpan {
    fn make_span(&mut self, request: &Request<B>) -> Span {
        let method = request.method().as_str();
        let path = request.uri().path();

        tracing::info_span!(
            "HTTP request",
            otel.name = %format!("{} {}", method, path),
            http.method = %method,
            http.route = %path,
            http.target = %request.uri(),
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
        let status = response.status().as_u16();

        span.record("http.response.status_code", status as i64);

        if status >= 500 {
            span.record("otel.status_code", "ERROR");
        } else {
            span.record("otel.status_code", "OK");
        }

        let latency_ms = latency.as_secs_f64() * 1000.0;
        let status_class = format!("{}xx", status / 100);

        HTTP_REQUESTS_TOTAL.add(
            1,
            &[
                KeyValue::new("http.status_code", status.to_string()),
                KeyValue::new("http.status_class", status_class.clone()),
            ],
        );

        HTTP_REQUEST_DURATION.record(
            latency_ms,
            &[
                KeyValue::new("http.status_code", status.to_string()),
                KeyValue::new("http.status_class", status_class),
            ],
        );

        tracing::info!(
            http.response.status_code = status,
            latency_ms = latency_ms,
            "finished processing request"
        );
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let config = Config::from_env();

    let telemetry_guard = init_telemetry(&config)?;

    tracing::info!(
        port = config.port,
        environment = %config.environment,
        "Starting ai-report-generator"
    );

    let pool = db::create_pool(&config.database_url).await?;

    let primary: Arc<dyn llm::Provider> = match config.llm_provider.as_str() {
        "anthropic" => Arc::new(llm::anthropic::AnthropicProvider::new(
            config.anthropic_api_key.as_deref().unwrap_or(""),
        )),
        "google" => Arc::new(llm::openai::OpenAIProvider::new_google(
            config.google_api_key.as_deref().unwrap_or(""),
        )),
        "ollama" => Arc::new(llm::openai::OpenAIProvider::new_ollama(
            &config.ollama_base_url,
        )),
        _ => Arc::new(llm::openai::OpenAIProvider::new(
            config.openai_api_key.as_deref().unwrap_or(""),
        )),
    };

    let fallback: Option<Arc<dyn llm::Provider>> = match config.fallback_provider.as_str() {
        "anthropic" => Some(Arc::new(llm::anthropic::AnthropicProvider::new(
            config.anthropic_api_key.as_deref().unwrap_or(""),
        ))),
        "openai" => Some(Arc::new(llm::openai::OpenAIProvider::new(
            config.openai_api_key.as_deref().unwrap_or(""),
        ))),
        "google" => Some(Arc::new(llm::openai::OpenAIProvider::new_google(
            config.google_api_key.as_deref().unwrap_or(""),
        ))),
        "ollama" => Some(Arc::new(llm::openai::OpenAIProvider::new_ollama(
            &config.ollama_base_url,
        ))),
        _ => None,
    };

    tracing::info!(
        primary_provider = %config.llm_provider,
        fallback_provider = %config.fallback_provider,
        "LLM client initialized"
    );

    let llm_client = Arc::new(llm::LlmClient {
        primary,
        fallback,
        primary_provider: config.llm_provider.clone(),
        fallback_provider: config.fallback_provider.clone(),
        fallback_model: config.fallback_model.clone(),
    });

    let state = AppState {
        pool,
        config: config.clone(),
        llm_client,
    };

    let app = Router::new()
        .route("/api/health", get(routes::health::health))
        .route("/api/reports", post(routes::reports::create_report))
        .route("/api/reports", get(routes::reports::list_reports))
        .route("/api/reports/{id}", get(routes::reports::get_report))
        .route("/api/indicators", get(routes::indicators::list_indicators))
        .route("/api/test/llm-error", post(routes::test::trigger_llm_error))
        .layer(
            TraceLayer::new_for_http()
                .make_span_with(HttpMakeSpan)
                .on_response(HttpOnResponse),
        )
        .layer(TimeoutLayer::with_status_code(
            StatusCode::REQUEST_TIMEOUT,
            Duration::from_secs(300),
        ))
        .layer(
            CorsLayer::new()
                .allow_origin(Any)
                .allow_methods(Any)
                .allow_headers(Any),
        )
        .with_state(state);

    let addr = SocketAddr::from(([0, 0, 0, 0], config.port));
    let listener = TcpListener::bind(addr).await?;

    tracing::info!(%addr, "Server listening");

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;

    tracing::info!("Server shutdown complete");
    telemetry_guard.shutdown();

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
