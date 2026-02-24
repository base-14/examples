use chrono::NaiveDate;
use serde::Serialize;
use sqlx::PgPool;

#[derive(Debug, Clone, Serialize, sqlx::FromRow)]
pub struct DataPoint {
    pub observation_date: NaiveDate,
    pub value: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct IndicatorData {
    pub code: String,
    pub name: String,
    pub unit: String,
    pub frequency: String,
    pub values: Vec<DataPoint>,
}

#[tracing::instrument(
    name = "db.data_points.query",
    skip(pool),
    fields(indicator_count, data_point_count)
)]
pub async fn query_indicator_data(
    pool: &PgPool,
    codes: &[String],
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> Result<Vec<IndicatorData>, sqlx::Error> {
    let mut results = Vec::new();
    let span = tracing::Span::current();

    for code in codes {
        let indicator = sqlx::query_as::<_, (i32, String, String, String, String)>(
            "SELECT id, code, name, unit, frequency FROM indicators WHERE code = $1",
        )
        .bind(code)
        .fetch_optional(pool)
        .await?;

        let Some((id, code, name, unit, frequency)) = indicator else {
            continue;
        };

        let values = sqlx::query_as::<_, DataPoint>(
            "SELECT observation_date, value::float8 as value \
             FROM data_points \
             WHERE indicator_id = $1 AND observation_date >= $2 AND observation_date <= $3 \
             ORDER BY observation_date",
        )
        .bind(id)
        .bind(start_date)
        .bind(end_date)
        .fetch_all(pool)
        .await?;

        results.push(IndicatorData {
            code,
            name,
            unit,
            frequency,
            values,
        });
    }

    let total_points: usize = results.iter().map(|d| d.values.len()).sum();
    span.record("indicator_count", results.len());
    span.record("data_point_count", total_points);

    Ok(results)
}
