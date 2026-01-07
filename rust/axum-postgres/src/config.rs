use std::env;

#[derive(Debug, Clone)]
pub struct Config {
    pub port: u16,
    pub environment: String,
    pub database_url: String,
    pub jwt_secret: String,
    pub jwt_expires_in_hours: i64,
    pub otel_service_name: String,
    pub otel_exporter_endpoint: String,
}

impl Config {
    pub fn from_env() -> Self {
        dotenvy::dotenv().ok();

        Self {
            port: env::var("PORT")
                .unwrap_or_else(|_| "8080".to_string())
                .parse()
                .expect("PORT must be a number"),
            environment: env::var("ENVIRONMENT").unwrap_or_else(|_| "development".to_string()),
            database_url: env::var("DATABASE_URL").expect("DATABASE_URL must be set"),
            jwt_secret: env::var("JWT_SECRET").expect("JWT_SECRET must be set"),
            jwt_expires_in_hours: env::var("JWT_EXPIRES_IN_HOURS")
                .unwrap_or_else(|_| "168".to_string())
                .parse()
                .expect("JWT_EXPIRES_IN_HOURS must be a number"),
            otel_service_name: env::var("OTEL_SERVICE_NAME")
                .unwrap_or_else(|_| "rust-axum-postgres".to_string()),
            otel_exporter_endpoint: env::var("OTEL_EXPORTER_OTLP_ENDPOINT")
                .unwrap_or_else(|_| "http://localhost:4317".to_string()),
        }
    }

    pub fn is_production(&self) -> bool {
        self.environment == "production"
    }
}
