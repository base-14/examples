use sqlx::FromRow;
use time::OffsetDateTime;

#[derive(Debug, Clone, FromRow)]
pub struct Favorite {
    pub id: i32,
    pub user_id: i32,
    pub article_id: i32,
    pub created_at: OffsetDateTime,
}
