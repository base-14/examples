use std::collections::HashMap;

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

#[derive(sqlx::FromRow)]
struct JoinedRow {
    code: String,
    name: String,
    unit: String,
    frequency: String,
    observation_date: NaiveDate,
    value: f64,
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
    let span = tracing::Span::current();

    let rows = sqlx::query_as::<_, JoinedRow>(
        "SELECT i.code, i.name, i.unit, i.frequency, \
                dp.observation_date, dp.value::float8 as value \
         FROM indicators i \
         JOIN data_points dp ON dp.indicator_id = i.id \
         WHERE i.code = ANY($1) \
           AND dp.observation_date >= $2 \
           AND dp.observation_date <= $3 \
         ORDER BY i.code, dp.observation_date",
    )
    .bind(codes)
    .bind(start_date)
    .bind(end_date)
    .fetch_all(pool)
    .await?;

    let mut map: HashMap<String, IndicatorData> = HashMap::new();
    let mut order: Vec<String> = Vec::new();

    for row in rows {
        let entry = map.entry(row.code.clone()).or_insert_with(|| {
            order.push(row.code.clone());
            IndicatorData {
                code: row.code,
                name: row.name,
                unit: row.unit,
                frequency: row.frequency,
                values: Vec::new(),
            }
        });
        entry.values.push(DataPoint {
            observation_date: row.observation_date,
            value: row.value,
        });
    }

    let results: Vec<IndicatorData> = order.into_iter().filter_map(|c| map.remove(&c)).collect();

    let total_points: usize = results.iter().map(|d| d.values.len()).sum();
    span.record("indicator_count", results.len());
    span.record("data_point_count", total_points);

    Ok(results)
}
