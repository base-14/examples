use sqlx::{PgPool, Row};
use tracing::instrument;

use crate::models::Favorite;

#[derive(Clone)]
pub struct FavoriteRepository {
    pool: PgPool,
}

impl FavoriteRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    #[instrument(name = "db.favorite.create", skip(self))]
    pub async fn create(&self, user_id: i32, article_id: i32) -> Result<Favorite, sqlx::Error> {
        sqlx::query_as::<_, Favorite>(
            r#"
            INSERT INTO favorites (user_id, article_id)
            VALUES ($1, $2)
            ON CONFLICT (user_id, article_id) DO UPDATE SET user_id = $1
            RETURNING id, user_id, article_id, created_at
            "#,
        )
        .bind(user_id)
        .bind(article_id)
        .fetch_one(&self.pool)
        .await
    }

    #[instrument(name = "db.favorite.delete", skip(self))]
    pub async fn delete(&self, user_id: i32, article_id: i32) -> Result<bool, sqlx::Error> {
        let result = sqlx::query("DELETE FROM favorites WHERE user_id = $1 AND article_id = $2")
            .bind(user_id)
            .bind(article_id)
            .execute(&self.pool)
            .await?;

        Ok(result.rows_affected() > 0)
    }

    #[instrument(name = "db.favorite.exists", skip(self))]
    pub async fn exists(&self, user_id: i32, article_id: i32) -> Result<bool, sqlx::Error> {
        let row = sqlx::query(
            r#"
            SELECT EXISTS(
                SELECT 1 FROM favorites WHERE user_id = $1 AND article_id = $2
            ) as exists
            "#,
        )
        .bind(user_id)
        .bind(article_id)
        .fetch_one(&self.pool)
        .await?;

        Ok(row.get::<bool, _>("exists"))
    }

    #[instrument(name = "db.favorite.is_favorited_batch", skip(self, article_ids))]
    pub async fn is_favorited_batch(
        &self,
        user_id: i32,
        article_ids: &[i32],
    ) -> Result<Vec<i32>, sqlx::Error> {
        let rows = sqlx::query(
            r#"
            SELECT article_id
            FROM favorites
            WHERE user_id = $1 AND article_id = ANY($2)
            "#,
        )
        .bind(user_id)
        .bind(article_ids)
        .fetch_all(&self.pool)
        .await?;

        Ok(rows.iter().map(|r| r.get::<i32, _>("article_id")).collect())
    }
}
