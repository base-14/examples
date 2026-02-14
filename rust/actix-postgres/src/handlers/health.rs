use actix_web::{HttpResponse, web};
use serde_json::json;
use sqlx::{PgPool, Row};

pub async fn health_check(pool: web::Data<PgPool>) -> HttpResponse {
    let db_status = sqlx::query("SELECT 1 as one")
        .fetch_one(pool.get_ref())
        .await
        .map(|row: sqlx::postgres::PgRow| {
            let _: i32 = row.get("one");
            "healthy"
        })
        .unwrap_or("unhealthy");

    if db_status == "healthy" {
        HttpResponse::Ok().json(json!({
            "status": "ok",
            "database": db_status,
            "service": "actix-postgres",
        }))
    } else {
        HttpResponse::ServiceUnavailable().json(json!({
            "status": "error",
            "database": db_status,
            "service": "actix-postgres",
        }))
    }
}
