use std::env;

#[derive(Debug, Clone)]
pub struct Config {
    pub port: u16,
    pub environment: String,
    pub database_url: String,
    pub llm_provider: String,
    pub llm_model_capable: String,
    pub llm_model_fast: String,
    pub fallback_provider: String,
    pub fallback_model: String,
    pub ollama_base_url: String,
    pub openai_api_key: Option<String>,
    pub anthropic_api_key: Option<String>,
    pub google_api_key: Option<String>,
    pub otel_service_name: String,
    pub otel_exporter_endpoint: String,
    pub default_temperature: f64,
    pub default_max_tokens: u32,
}

impl Config {
    pub fn from_env() -> Self {
        dotenvy::dotenv().ok();

        Self {
            port: env::var("APP_PORT")
                .unwrap_or_else(|_| "8080".to_string())
                .parse()
                .expect("APP_PORT must be a number"),
            environment: env::var("SCOUT_ENVIRONMENT")
                .unwrap_or_else(|_| "development".to_string()),
            database_url: env::var("DATABASE_URL").expect("DATABASE_URL must be set"),
            llm_provider: env::var("LLM_PROVIDER").unwrap_or_else(|_| "openai".to_string()),
            llm_model_capable: env::var("LLM_MODEL_CAPABLE")
                .unwrap_or_else(|_| "gpt-4.1".to_string()),
            llm_model_fast: env::var("LLM_MODEL_FAST")
                .unwrap_or_else(|_| "gpt-4.1-mini".to_string()),
            fallback_provider: env::var("FALLBACK_PROVIDER")
                .unwrap_or_else(|_| "anthropic".to_string()),
            fallback_model: env::var("FALLBACK_MODEL")
                .unwrap_or_else(|_| "claude-haiku-4-5-20251001".to_string()),
            ollama_base_url: env::var("OLLAMA_BASE_URL")
                .unwrap_or_else(|_| "http://localhost:11434".to_string()),
            openai_api_key: env::var("OPENAI_API_KEY").ok(),
            anthropic_api_key: env::var("ANTHROPIC_API_KEY").ok(),
            google_api_key: env::var("GOOGLE_API_KEY").ok(),
            otel_service_name: env::var("OTEL_SERVICE_NAME")
                .unwrap_or_else(|_| "ai-report-generator".to_string()),
            otel_exporter_endpoint: env::var("OTEL_EXPORTER_OTLP_ENDPOINT")
                .unwrap_or_else(|_| "http://localhost:4317".to_string()),
            default_temperature: env::var("DEFAULT_TEMPERATURE")
                .unwrap_or_else(|_| "0.3".to_string())
                .parse()
                .expect("DEFAULT_TEMPERATURE must be a number"),
            default_max_tokens: env::var("DEFAULT_MAX_TOKENS")
                .unwrap_or_else(|_| "4096".to_string())
                .parse()
                .expect("DEFAULT_MAX_TOKENS must be a number"),
        }
    }

    pub fn is_production(&self) -> bool {
        self.environment == "production"
    }
}
