use sqlx::{PgPool, postgres::PgPoolOptions};

use crate::config::Config;

pub async fn create_pool(config: &Config) -> Result<PgPool, sqlx::Error> {
    let pool = PgPoolOptions::new()
        .max_connections(25)
        .min_connections(5)
        .acquire_timeout(std::time::Duration::from_secs(5))
        .connect(&config.database_url)
        .await?;

    tracing::info!("Database connection pool created");

    sqlx::migrate!("./migrations").run(&pool).await?;

    tracing::info!("Database migrations completed");

    Ok(pool)
}
