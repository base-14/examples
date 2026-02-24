use serde::Serialize;
use sqlx::PgPool;

#[derive(Debug, Clone, Serialize, sqlx::FromRow)]
pub struct Indicator {
    pub id: i32,
    pub code: String,
    pub name: String,
    pub frequency: String,
    pub unit: String,
    pub description: Option<String>,
}

#[tracing::instrument(name = "db.indicators.list", skip(pool))]
pub async fn list_indicators(pool: &PgPool) -> Result<Vec<Indicator>, sqlx::Error> {
    sqlx::query_as::<_, Indicator>(
        "SELECT id, code, name, frequency, unit, description FROM indicators ORDER BY code",
    )
    .fetch_all(pool)
    .await
}

#[allow(dead_code)]
#[tracing::instrument(name = "db.indicators.get_by_code", skip(pool))]
pub async fn get_indicator_by_code(
    pool: &PgPool,
    code: &str,
) -> Result<Option<Indicator>, sqlx::Error> {
    sqlx::query_as::<_, Indicator>(
        "SELECT id, code, name, frequency, unit, description FROM indicators WHERE code = $1",
    )
    .bind(code)
    .fetch_optional(pool)
    .await
}
